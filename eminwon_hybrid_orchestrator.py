#!/usr/bin/env python3

"""
Eminwon Hybrid 오케스트레이터
DB 연결 시도 → 실패하면 오프라인 모드로 fallback
"""

import os
import json
import subprocess
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

class EminwonHybridOrchestrator:
    def __init__(self, test_mode=False, specific_regions=None, verbose=False, max_workers=3, target_date=None):
        # Database configuration
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
            "port": int(os.environ.get("DB_PORT", 3306)),
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
        }

        # Set up directories
        today = datetime.now().strftime("%Y-%m-%d")
        self.output_base_dir = Path(f"batch_eminwon_result/{today}")
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        
        # Node.js paths
        self.node_path = "node"
        self.eminwon_scraper_path = "node/scraper/eminwon_scraper.js"
        
        # Fallback 지역 목록 (DB 연결 실패 시 사용)
        self.fallback_regions = [
            "가평군", "청주시", "부산광역시", "대구광역시", "서울특별시",
            "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종시"
        ]
        
        # Statistics
        self.stats = {
            "total_regions": 0,
            "success_regions": 0,
            "failed_regions": 0,
            "total_collected": 0,
            "errors": [],
            "db_mode": None  # 'connected', 'offline'
        }
        
        self.test_mode = test_mode
        self.specific_regions = specific_regions
        self.verbose = verbose
        self.max_workers = max_workers
        self.target_date = target_date
        
        # Setup logging
        self.setup_logging()
        
        # DB 연결 상태 확인
        self.db_connected = self.test_db_connection()
        if self.db_connected:
            self.stats['db_mode'] = 'connected'
            self.logger.info("✅ DB 연결 성공 - 증분 수집 모드")
        else:
            self.stats['db_mode'] = 'offline' 
            self.logger.warning("⚠️ DB 연결 실패 - 오프라인 모드로 실행")
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
        
        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f'eminwon_hybrid_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        
        logging.basicConfig(
            level=logging.DEBUG if self.test_mode else logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_file, encoding='utf-8')
            ],
        )
        self.logger = logging.getLogger(__name__)
    
    def test_db_connection(self):
        """Test database connection"""
        try:
            import mysql.connector
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            self.logger.debug(f"DB 연결 실패: {e}")
            return False
    
    def get_regions_from_db(self):
        """DB에서 지역 목록과 마지막 수집 날짜 조회"""
        if not self.db_connected:
            return None
        
        try:
            import mysql.connector
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor(dictionary=True)
            
            if self.specific_regions:
                # Filter by specific regions
                placeholders = ','.join(['%s'] * len(self.specific_regions))
                query = f"""
                    SELECT site_code, host_url, latest_announcement_date 
                    FROM eminwon_site_announcement_date 
                    WHERE site_code IN ({placeholders})
                    ORDER BY site_code
                """
                cursor.execute(query, self.specific_regions)
            else:
                # Get all regions
                query = """
                    SELECT site_code, host_url, latest_announcement_date 
                    FROM eminwon_site_announcement_date 
                    ORDER BY site_code
                """
                cursor.execute(query)
            
            regions = cursor.fetchall()
            cursor.close()
            conn.close()
            
            self.logger.info(f"DB에서 {len(regions)}개 지역 정보 조회 성공")
            return regions
            
        except Exception as e:
            self.logger.error(f"DB 조회 실패: {e}")
            return None
    
    def get_regions_fallback(self):
        """DB 연결 실패 시 fallback 지역 목록"""
        regions = []
        region_list = self.specific_regions or self.fallback_regions
        
        # 기본 날짜 설정 (7일 전)
        default_date = self.target_date or (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        for region in region_list:
            regions.append({
                'site_code': region,
                'host_url': f'https://eminwon.{region.lower()}.go.kr',  # 추정
                'latest_announcement_date': default_date
            })
        
        self.logger.info(f"Fallback 모드: {len(regions)}개 지역, 기준 날짜: {default_date}")
        return regions
    
    def normalize_region_name(self, region: str) -> str:
        """지역명 정규화 - 시/군/구 제거"""
        import re
        normalized = re.sub(r"(시|군|구)$", "", region)
        return normalized
    
    def extract_collected_count(self, output_text):
        """Extract collected count from scraper output"""
        try:
            import re
            patterns = [
                r'(\d+)개 수집 완료',
                r'(\d+)개 공고 수집',
                r'수집된 공고: (\d+)개',
                r'총 (\d+)개의 공고'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, output_text)
                if match:
                    return int(match.group(1))
            
            return 0
        except Exception:
            return 0
    
    def update_latest_announcement_date(self, site_code, new_date):
        """Update latest_announcement_date for successful scraping"""
        if not self.db_connected:
            self.logger.debug(f"오프라인 모드: {site_code} 날짜 업데이트 건너뛰기")
            return True
        
        try:
            import mysql.connector
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE eminwon_site_announcement_date 
                SET latest_announcement_date = %s, last_updated = CURRENT_TIMESTAMP
                WHERE site_code = %s
            """, (new_date, site_code))
            
            if cursor.rowcount > 0:
                conn.commit()
                self.logger.info(f"✅ {site_code} 최신 날짜 업데이트: {new_date}")
                result = True
            else:
                self.logger.warning(f"⚠️ {site_code} 업데이트 실패: 해당 행 없음")
                result = False
            
            cursor.close()
            conn.close()
            return result
            
        except Exception as e:
            self.logger.error(f"❌ {site_code} 날짜 업데이트 실패: {e}")
            return False
    
    def process_region(self, region_info):
        """Process a single region"""
        site_code = region_info['site_code']
        latest_date = region_info['latest_announcement_date']
        
        start_time = datetime.now()
        
        try:
            # 날짜 결정: target_date가 있으면 사용, 없으면 latest_announcement_date 사용
            if self.target_date:
                target_date = self.target_date
                self.logger.info(f"Processing {site_code} from {target_date} (override)")
            else:
                target_date = latest_date
                self.logger.info(f"Processing {site_code} from {target_date} (latest)")
            
            # Convert target_date to string format for scraper
            if isinstance(target_date, str):
                if len(target_date) == 8:  # YYYYMMDD format
                    target_date_str = target_date
                else:  # YYYY-MM-DD format
                    target_date_str = target_date.replace('-', '')
            else:
                target_date_str = target_date.strftime('%Y%m%d')
            
            # Create output directory for this region
            normalized_region = self.normalize_region_name(site_code)
            output_dir = self.output_base_dir / normalized_region
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Build command for eminwon_scraper.js
            cmd_args = [
                self.node_path,
                self.eminwon_scraper_path,
                "--region",
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
                collected_count = self.extract_collected_count(result.stderr + result.stdout)
                
                self.logger.info(f"✅ {site_code}: {collected_count}개 수집 완료")
                
                # Update latest_announcement_date to today (DB 연결 시에만)
                today_str = datetime.now().strftime('%Y-%m-%d')
                if self.update_latest_announcement_date(site_code, today_str):
                    self.stats['success_regions'] += 1
                    self.stats['total_collected'] += collected_count
                    return {'status': 'success', 'collected': collected_count, 'region': site_code}
                else:
                    # DB 업데이트 실패해도 오프라인 모드에서는 성공으로 처리
                    if not self.db_connected:
                        self.stats['success_regions'] += 1
                        self.stats['total_collected'] += collected_count
                        return {'status': 'success', 'collected': collected_count, 'region': site_code}
                    else:
                        self.stats['failed_regions'] += 1
                        error_msg = f"DB update failed for {site_code}"
                        self.stats['errors'].append(error_msg)
                        return {'status': 'failed', 'error': error_msg, 'region': site_code}
            else:
                # Scraper failed
                error_msg = f"Scraper failed: {result.stderr[:200] if result.stderr else 'Unknown error'}"
                self.logger.error(f"❌ {site_code}: {error_msg}")
                
                self.stats['failed_regions'] += 1
                self.stats['errors'].append(f"{site_code}: {error_msg}")
                
                return {'status': 'failed', 'error': error_msg, 'region': site_code}
                
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout after 10 minutes"
            self.logger.error(f"⏰ {site_code}: {error_msg}")
            
            self.stats['failed_regions'] += 1
            self.stats['errors'].append(f"{site_code}: {error_msg}")
            
            return {'status': 'timeout', 'error': error_msg, 'region': site_code}
            
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            self.logger.error(f"💥 {site_code}: {error_msg}")
            
            self.stats['failed_regions'] += 1
            self.stats['errors'].append(f"{site_code}: {error_msg}")
            
            return {'status': 'error', 'error': error_msg, 'region': site_code}
    
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

            # Check scripts exist
            if not Path(self.eminwon_scraper_path).exists():
                raise Exception(f"Scraper script not found: {self.eminwon_scraper_path}")

            return True
        except Exception as e:
            self.logger.error(f"Dependency check failed: {e}")
            return False
    
    def run(self):
        """Main execution method"""
        self.logger.info("=" * 80)
        self.logger.info("Starting Eminwon Hybrid Collection")
        self.logger.info(f"Mode: {'DB Connected' if self.db_connected else 'Offline'}")
        self.logger.info(f"Output Directory: {self.output_base_dir}")
        self.logger.info("=" * 80)

        # Check dependencies
        if not self.check_node_dependencies():
            self.logger.error("Dependency check failed. Exiting.")
            return False

        # Get regions to process
        if self.db_connected:
            regions = self.get_regions_from_db()
            if not regions:
                self.logger.warning("DB 조회 실패, fallback 모드로 전환")
                regions = self.get_regions_fallback()
        else:
            regions = self.get_regions_fallback()
        
        if not regions:
            self.logger.error("No regions found to process")
            return False

        self.stats['total_regions'] = len(regions)
        
        # Process regions
        if self.test_mode or len(regions) <= 3:
            # Sequential processing for test mode or small batches
            self.logger.info("Using sequential processing")
            for region in regions:
                result = self.process_region(region)
                if self.verbose:
                    self.logger.info(f"Result for {result['region']}: {result['status']}")
        else:
            # Parallel processing
            self.logger.info(f"Using parallel processing with {self.max_workers} workers")
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all tasks
                future_to_region = {
                    executor.submit(self.process_region, region): region['site_code']
                    for region in regions
                }

                # Process results as they complete
                for future in tqdm(as_completed(future_to_region), total=len(future_to_region), 
                                 desc="Processing regions"):
                    region_code = future_to_region[future]
                    try:
                        result = future.result(timeout=660)  # 11분 타임아웃
                        if result['status'] == 'success':
                            tqdm.write(f"✅ {region_code}: {result.get('collected', 0)}개 수집")
                        else:
                            tqdm.write(f"❌ {region_code}: {result['status']}")
                    except Exception as e:
                        self.logger.error(f"Failed processing {region_code}: {e}")
                        self.stats['failed_regions'] += 1

        # Print summary
        self.print_summary()

        return self.stats['failed_regions'] == 0
    
    def print_summary(self):
        """Print execution summary"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("EXECUTION SUMMARY")
        self.logger.info("=" * 80)
        self.logger.info(f"Mode: {self.stats['db_mode']}")
        self.logger.info(f"Total Regions: {self.stats['total_regions']}")
        self.logger.info(f"Success: {self.stats['success_regions']}")
        self.logger.info(f"Failed: {self.stats['failed_regions']}")
        self.logger.info(f"Total Collected: {self.stats['total_collected']:,}")
        
        if self.stats['errors']:
            self.logger.info(f"\nErrors ({len(self.stats['errors'])}):")
            for error in self.stats['errors'][:10]:  # Show first 10 errors
                self.logger.info(f"  - {error}")
            if len(self.stats['errors']) > 10:
                self.logger.info(f"  ... and {len(self.stats['errors']) - 10} more errors")
        
        self.logger.info(f"\nOutput Directory: {self.output_base_dir}")
        self.logger.info("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Eminwon Hybrid Orchestrator")
    parser.add_argument("--test", action="store_true", help="Run in test mode")
    parser.add_argument(
        "--regions",
        nargs="+",
        help="Specific regions to process (e.g., --regions 청주시 가평군)",
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

    orchestrator = EminwonHybridOrchestrator(
        test_mode=args.test,
        specific_regions=args.regions,
        verbose=args.verbose,
        max_workers=args.workers,
        target_date=args.date
    )

    success = orchestrator.run()
    exit(0 if success else 1)


if __name__ == "__main__":
    main()