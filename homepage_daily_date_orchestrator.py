#!/usr/bin/env python3

"""
Homepage 날짜 기반 일일 수집 오케스트레이터

homepage_site_announcement_date 테이블을 기반으로
각 site의 latest_announcement_date 이후 데이터를 수집하는 시스템

1. homepage_site_announcement_date 테이블에서 site_code, latest_announcement_date 읽기
2. 각 스크래퍼를 날짜 옵션으로 실행 (node/scraper/{site_code}_scraper.js)
3. 성공시 latest_announcement_date 업데이트
4. batch_scraper_summary와 batch_scraper_result에 로깅
"""

import os
import json
import subprocess
import mysql.connector
import re
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import hashlib
import argparse
import logging
import sys
import uuid


class HomepageDailyDateOrchestrator:
    def __init__(self, test_mode=False, specific_sites=None, verbose=False, max_workers=3, override_date=None):
        # Database configuration
        import os

        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        self.db_config = {
            "host": os.environ.get("DB_HOST"),
            "user": os.environ.get("DB_USER"),
            "password": os.environ.get("DB_PASSWORD"),
            "database": os.environ.get("DB_NAME"),
            "port": int(os.environ.get("DB_PORT")),
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
        }

        # Set up directories
        today = datetime.now().strftime("%Y-%m-%d")

        # .env에서 HOMEPAGE_OUTPUT_BASE_DIR 설정 읽기, 없으면 기본값 사용
        output_base = os.environ.get("HOMEPAGE_OUTPUT_BASE_DIR", "batch_homepage_result")
        self.output_base_dir = Path(f"{output_base}/{today}")
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

        # Node.js paths
        self.node_path = "node"
        self.scraper_base_path = "node/scraper"

        # Statistics
        self.stats = {
            "total_sites": 0,
            "success_sites": 0,
            "failed_sites": 0,
            "skipped_sites": 0,
            "total_collected": 0,
            "errors": []
        }

        self.test_mode = test_mode
        self.specific_sites = specific_sites or []
        self.verbose = verbose
        self.max_workers = max_workers
        self.override_date = override_date  # 날짜 강제 지정 옵션

        # Batch execution ID for tracking
        self.batch_id = str(uuid.uuid4())[:8]
        self.batch_start_time = datetime.now()

        # Setup logging
        self.setup_logging()

    def setup_logging(self):
        """Setup logging configuration"""
        log_format = "%(asctime)s - %(levelname)s - %(message)s"

        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / f'homepage_daily_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'

        logging.basicConfig(
            level=logging.DEBUG if self.test_mode else logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_file, encoding='utf-8')
            ],
        )
        self.logger = logging.getLogger(__name__)


    def get_sites_to_process(self):
        """Get sites from homepage_site_announcement_date table"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor(dictionary=True)

        try:
            if self.specific_sites:
                # Filter by specific sites
                placeholders = ','.join(['%s'] * len(self.specific_sites))
                query = f"""
                    SELECT site_code, latest_announcement_date
                    FROM homepage_site_announcement_date
                    WHERE site_code IN ({placeholders})
                    ORDER BY site_code
                """
                cursor.execute(query, self.specific_sites)
            else:
                # Get all sites
                query = """
                    SELECT site_code, latest_announcement_date
                    FROM homepage_site_announcement_date
                    ORDER BY site_code
                """
                cursor.execute(query)

            sites = cursor.fetchall()
            self.logger.info(f"Found {len(sites)} sites to process")

            if self.verbose:
                for site in sites[:5]:  # Show first 5
                    self.logger.info(f"  {site['site_code']}: {site['latest_announcement_date']}")
                if len(sites) > 5:
                    self.logger.info(f"  ... and {len(sites) - 5} more sites")

            return sites

        except Exception as e:
            self.logger.error(f"Error getting sites from database: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def start_batch_summary(self, total_sites):
        """Start batch summary record"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()

        try:
            batch_date = self.batch_start_time.date()

            # Use INSERT ... ON DUPLICATE KEY UPDATE to handle same-day reruns
            # Note: batch_end_time is set to batch_start_time initially (NOT NULL constraint)
            cursor.execute("""
                INSERT INTO batch_scraper_summary
                (batch_date, scraper_type, total_scrapers, success_count, failed_count,
                 total_folder_count, batch_start_time, batch_end_time, batch_duration)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    total_scrapers = %s,
                    batch_start_time = %s,
                    batch_end_time = %s,
                    success_count = 0,
                    failed_count = 0,
                    total_folder_count = 0
            """, (
                batch_date,
                'homepage',
                total_sites,
                0,  # success_count
                0,  # failed_count
                0,  # total_folder_count
                self.batch_start_time,
                self.batch_start_time,  # batch_end_time (temporary, updated on finish)
                0,  # batch_duration
                total_sites,  # For ON DUPLICATE KEY UPDATE
                self.batch_start_time,  # For ON DUPLICATE KEY UPDATE
                self.batch_start_time  # For ON DUPLICATE KEY UPDATE
            ))

            conn.commit()
            self.logger.info(f"Started batch summary for {batch_date} with {total_sites} sites")

        except Exception as e:
            self.logger.error(f"Error starting batch summary: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    def finish_batch_summary(self, status='completed'):
        """Finish batch summary record"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()

        try:
            batch_date = self.batch_start_time.date()
            batch_end_time = datetime.now()
            batch_duration = (batch_end_time - self.batch_start_time).total_seconds()

            cursor.execute("""
                UPDATE batch_scraper_summary
                SET batch_end_time = %s,
                    batch_duration = %s,
                    success_count = %s,
                    failed_count = %s,
                    total_folder_count = %s
                WHERE batch_date = %s AND scraper_type = %s
            """, (
                batch_end_time,
                batch_duration,
                self.stats['success_sites'],
                self.stats['failed_sites'],
                self.stats['total_collected'],
                batch_date,
                'homepage'
            ))
            conn.commit()
            self.logger.info(f"Finished batch summary for {batch_date}: {status} "
                           f"({self.stats['success_sites']} success, {self.stats['failed_sites']} failed)")

        except Exception as e:
            self.logger.error(f"Error finishing batch summary: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    def log_scraper_result(self, site_code, target_date, start_time,
                          end_time, status, folder_count=0, error_message=None):
        """Log individual scraper result to batch_scraper_results table"""
        conn = None
        cursor = None

        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()

            # Calculate durations
            batch_duration = (datetime.now() - self.batch_start_time).total_seconds()
            site_duration = (end_time - start_time).total_seconds() if end_time and start_time else 0

            # Get batch date
            batch_date = self.batch_start_time.date()

            cursor.execute("""
                INSERT INTO batch_scraper_results
                (batch_date, batch_start_time, batch_end_time, batch_duration,
                 scraper_type, site_code, site_start_time, site_end_time,
                 site_duration, folder_count, status, error_message, latest_announcement_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                batch_date,
                self.batch_start_time,
                datetime.now(),
                batch_duration,
                'homepage',
                site_code,
                start_time,
                end_time,
                site_duration,
                folder_count,
                status,
                error_message,
                target_date if status == 'success' else None
            ))
            conn.commit()
            self.logger.debug(f"Logged scraper result for {site_code}: {status}")

        except Exception as e:
            self.logger.error(f"Error logging scraper result for {site_code}: {e}")
            if conn:
                conn.rollback()
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_latest_announcement_date(self, site_code, new_date):
        """Update latest_announcement_date for successful scraping"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE homepage_site_announcement_date
                SET latest_announcement_date = %s, last_updated = CURRENT_TIMESTAMP
                WHERE site_code = %s
            """, (new_date, site_code))

            if cursor.rowcount > 0:
                conn.commit()
                self.logger.info(f"Updated {site_code} latest_announcement_date to {new_date}")
                return True
            else:
                self.logger.warning(f"No rows updated for site_code: {site_code}")
                return False

        except Exception as e:
            self.logger.error(f"Error updating latest_announcement_date for {site_code}: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def extract_collected_count(self, output_text):
        """Extract collected count from scraper output"""
        try:
            # Look for patterns from Node.js homepage scraper output
            patterns = [
                r'처리된 공고 수:\s*(\d+)',
                r'(\d+)개 수집 완료',
                r'(\d+)개 공고 수집',
                r'수집된 공고:\s*(\d+)개?',
                r'총\s*(\d+)개의 공고',
                r'생성된 폴더:\s*(\d+)개?',
                r'폴더 생성 완료:\s*(\d+)개?',
                r'저장된 공고 수:\s*(\d+)',
                r'Downloaded\s+(\d+)\s+announcements?',
                r'Created\s+(\d+)\s+folders?',
                r'Saved\s+(\d+)\s+files?',
                r'스크래핑\s+완료:\s*(\d+)개',
                r'공고\s+(\d+)개\s+다운로드'
            ]

            for pattern in patterns:
                match = re.search(pattern, output_text)
                if match:
                    count = int(match.group(1))
                    if self.verbose:
                        self.logger.debug(f"Extracted count: {count} using pattern: {pattern}")
                    return count

            # If no pattern matched, log the output for debugging
            if self.verbose:
                self.logger.debug(f"Could not extract count from output. First 500 chars: {output_text[:500]}")

            return 0
        except Exception as e:
            self.logger.error(f"Error extracting collected count: {e}")
            return 0

    def process_site(self, site_info):
        """Process a single site with date-based collection"""
        site_code = site_info['site_code']
        latest_date = site_info['latest_announcement_date']

        start_time = datetime.now()

        try:
            # 날짜 결정: override_date가 있으면 사용, 없으면 latest_announcement_date 사용
            if self.override_date:
                target_date = self.override_date
                self.logger.info(f"Processing {site_code} from {target_date} (override)")
            else:
                target_date = latest_date
                self.logger.info(f"Processing {site_code} from {target_date} (latest)")

            # Convert target_date to string format for scraper (YYYY-MM-DD)
            if isinstance(target_date, str):
                if len(target_date) == 8:  # YYYYMMDD format
                    # Convert YYYYMMDD to YYYY-MM-DD
                    target_date_str = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"
                else:  # Already YYYY-MM-DD format
                    target_date_str = target_date
            else:
                target_date_str = target_date.strftime('%Y-%m-%d')

            # Scraper script path
            scraper_script = Path(self.scraper_base_path) / f"{site_code}_scraper.js"

            # Check if scraper script exists
            if not scraper_script.exists():
                error_msg = f"Scraper script not found: {scraper_script}"
                self.logger.error(f"❌ {site_code}: {error_msg}")

                end_time = datetime.now()
                self.stats['failed_sites'] += 1
                self.stats['errors'].append(f"{site_code}: {error_msg}")

                self.log_scraper_result(
                    site_code, target_date, start_time, end_time,
                    'error', 0, error_msg
                )

                return {'status': 'error', 'error': error_msg, 'site': site_code}

            # Use output directory directly (no site-code subdirectory)
            output_dir = self.output_base_dir

            # Build command for homepage scraper
            cmd_args = [
                self.node_path,
                str(scraper_script),
                "--site",
                site_code,
                "--date",
                target_date_str,
                "--output",
                str(output_dir)
            ]

            if self.verbose:
                self.logger.info(f"Running: {' '.join(cmd_args)}")

            # Run the scraper
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=600,  # 10분 타임아웃
            )

            end_time = datetime.now()
            collected_count = 0

            if result.returncode == 0:
                # Success - extract collected count
                scraper_output = result.stderr + result.stdout
                collected_count = self.extract_collected_count(scraper_output)

                # Log scraper output if verbose mode or if count is 0 (debugging)
                if self.verbose or collected_count == 0:
                    self.logger.info(f"Scraper output for {site_code} (extracted count: {collected_count}):\n{scraper_output[:1000]}")

                self.logger.info(f"✅ {site_code}: {collected_count}개 수집 완료")

                # Update latest_announcement_date only if collected_count > 0
                if collected_count > 0:
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    if self.update_latest_announcement_date(site_code, today_str):
                        self.logger.info(f"Updated {site_code} latest_announcement_date to {today_str}")
                    else:
                        self.logger.warning(f"Failed to update {site_code} latest_announcement_date")
                else:
                    self.logger.info(f"{site_code}: No new announcements, latest_announcement_date not updated")

                # Always count as success and log result
                self.stats['success_sites'] += 1
                self.stats['total_collected'] += collected_count

                # Log success result
                self.log_scraper_result(
                    site_code, target_date, start_time, end_time,
                    'success', collected_count, None
                )

                return {'status': 'success', 'collected': collected_count, 'site': site_code}
            else:
                # Scraper failed
                error_msg = f"Scraper failed: {result.stderr[:200] if result.stderr else 'Unknown error'}"
                self.logger.error(f"❌ {site_code}: {error_msg}")

                self.stats['failed_sites'] += 1
                self.stats['errors'].append(f"{site_code}: {error_msg}")

                self.log_scraper_result(
                    site_code, target_date, start_time, end_time,
                    'failed', 0, error_msg
                )

                return {'status': 'failed', 'error': error_msg, 'site': site_code}

        except subprocess.TimeoutExpired:
            end_time = datetime.now()
            error_msg = f"Timeout after 10 minutes"
            self.logger.error(f"⏰ {site_code}: {error_msg}")

            self.stats['failed_sites'] += 1
            self.stats['errors'].append(f"{site_code}: {error_msg}")

            self.log_scraper_result(
                site_code, target_date, start_time, end_time,
                'timeout', 0, error_msg
            )

            return {'status': 'timeout', 'error': error_msg, 'site': site_code}

        except Exception as e:
            end_time = datetime.now()
            error_msg = f"Exception: {str(e)}"
            self.logger.error(f"💥 {site_code}: {error_msg}")

            self.stats['failed_sites'] += 1
            self.stats['errors'].append(f"{site_code}: {error_msg}")

            self.log_scraper_result(
                site_code, target_date, start_time, end_time,
                'error', 0, error_msg
            )

            return {'status': 'error', 'error': error_msg, 'site': site_code}

    def check_node_dependencies(self):
        """Check if Node.js and required scripts are available"""
        try:
            # Check Node.js
            result = subprocess.run(
                ["node", "--version"], capture_output=True, text=True
            )
            if result.returncode != 0:
                raise Exception("Node.js not found")
            self.logger.info(f"Node.js version: {result.stdout.strip()}")

            # Check scraper directory exists
            if not Path(self.scraper_base_path).exists():
                raise Exception(f"Scraper directory not found: {self.scraper_base_path}")

            return True
        except Exception as e:
            self.logger.error(f"Dependency check failed: {e}")
            return False

    def run(self):
        """Main execution method"""
        self.logger.info("=" * 80)
        self.logger.info("Starting Homepage Daily Date-based Collection")
        self.logger.info(f"Batch ID: {self.batch_id}")
        self.logger.info(f"Output Directory: {self.output_base_dir}")
        self.logger.info("=" * 80)

        # Check dependencies
        if not self.check_node_dependencies():
            self.logger.error("Dependency check failed. Exiting.")
            return False

        # Get sites to process
        sites = self.get_sites_to_process()
        if not sites:
            self.logger.error("No sites found to process")
            return False

        self.stats['total_sites'] = len(sites)

        # Start batch summary
        self.start_batch_summary(len(sites))

        # Process sites
        if self.test_mode or len(sites) <= 3:
            # Sequential processing for test mode or small batches
            self.logger.info("Using sequential processing")
            for site in sites:
                result = self.process_site(site)
                if self.verbose:
                    self.logger.info(f"Result for {result['site']}: {result['status']}")
        else:
            # Parallel processing
            self.logger.info(f"Using parallel processing with {self.max_workers} workers")
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all tasks
                future_to_site = {
                    executor.submit(self.process_site, site): site['site_code']
                    for site in sites
                }

                # Process results as they complete
                for future in tqdm(as_completed(future_to_site), total=len(future_to_site),
                                 desc="Processing sites"):
                    site_code = future_to_site[future]
                    try:
                        result = future.result(timeout=660)  # 11분 타임아웃
                        if result['status'] == 'success':
                            tqdm.write(f"✅ {site_code}: {result.get('collected', 0)}개 수집")
                        else:
                            tqdm.write(f"❌ {site_code}: {result['status']}")
                    except Exception as e:
                        self.logger.error(f"Failed processing {site_code}: {e}")
                        self.stats['failed_sites'] += 1

        # Finish batch summary
        batch_status = 'completed' if self.stats['failed_sites'] == 0 else 'completed_with_errors'
        self.finish_batch_summary(batch_status)

        # Print summary
        self.print_summary()

        return self.stats['failed_sites'] == 0

    def print_summary(self):
        """Print execution summary"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("EXECUTION SUMMARY")
        self.logger.info("=" * 80)
        self.logger.info(f"Batch ID: {self.batch_id}")
        self.logger.info(f"Total Sites: {self.stats['total_sites']}")
        self.logger.info(f"Success: {self.stats['success_sites']}")
        self.logger.info(f"Failed: {self.stats['failed_sites']}")
        self.logger.info(f"Skipped: {self.stats['skipped_sites']}")
        self.logger.info(f"Total Collected: {self.stats['total_collected']:,}")

        if self.stats['errors']:
            self.logger.info(f"\nErrors ({len(self.stats['errors'])}):")
            for error in self.stats['errors'][:10]:  # Show first 10 errors
                self.logger.info(f"  - {error}")
            if len(self.stats['errors']) > 10:
                self.logger.info(f"  ... and {len(self.stats['errors']) - 10} more errors")

        elapsed = datetime.now() - self.batch_start_time
        self.logger.info(f"\nElapsed Time: {elapsed}")
        self.logger.info(f"Output Directory: {self.output_base_dir}")
        self.logger.info("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Homepage Daily Date-based Orchestrator")
    parser.add_argument("--test", action="store_true", help="Run in test mode")
    parser.add_argument(
        "--sites",
        nargs="+",
        help="Specific sites to process (e.g., --sites andong anseong)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Number of parallel workers (default: 3)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed logs",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Override date in YYYYMMDD or YYYY-MM-DD format (e.g., 20241025 or 2024-10-25). If not specified, uses latest_announcement_date from DB",
    )

    args = parser.parse_args()

    orchestrator = HomepageDailyDateOrchestrator(
        test_mode=args.test,
        specific_sites=args.sites,
        verbose=args.verbose,
        max_workers=args.workers,
        override_date=args.date
    )

    success = orchestrator.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
