#!/usr/bin/env python3

"""
Eminwon 증분 수집 오케스트레이터

Node.js 스크래퍼와 연동하여 새로운 공고만 수집하는 시스템
1. Node.js로 리스트 수집
2. DB와 비교하여 새 공고 필터링
3. 새 공고만 Node.js로 다운로드 요청
4. DB 업데이트
"""

import os
import json
import subprocess
import mysql.connector
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import hashlib
import argparse
import logging
import sys


class EminwonIncrementalOrchestrator:
    def __init__(self, test_mode=False, specific_regions=None, verbose=False):
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

        # Load eminwon.json configuration
        with open("node/scraper/eminwon.json", "r", encoding="utf-8") as f:
            self.eminwon_config = json.load(f)

        # Set up directories
        today = datetime.now().strftime("%Y-%m-%d")
        self.output_dir = Path(f"eminwon_data_new/{today}")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Node.js paths
        self.node_path = "node"
        self.list_collector_path = (
            "node/scraper/eminwon_incremental_v2.js"  # 새 버전 사용
        )
        self.detail_scraper_path = (
            "node/scraper/eminwon_detail_scraper.js"  # 개별 URL 처리용
        )

        # Statistics
        self.stats = {
            "total_checked": 0,
            "new_found": 0,
            "downloaded": 0,
            "errors": 0,
            "duplicates": 0,
        }

        self.test_mode = test_mode
        self.specific_regions = specific_regions
        self.verbose = verbose
        self.pages = 3  # 기본 페이지 수

        # Setup logging
        self.setup_logging()

    def setup_logging(self):
        """Setup logging configuration"""
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
        logging.basicConfig(
            level=logging.DEBUG if self.test_mode else logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(
                    f'logs/orchestrator_{datetime.now().strftime("%Y%m%d")}.log'
                ),
            ],
        )
        self.logger = logging.getLogger(__name__)

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
            if not Path(self.list_collector_path).exists():
                raise Exception(
                    f"List collector script not found: {self.list_collector_path}"
                )
            if not Path(self.detail_scraper_path).exists():
                raise Exception(
                    f"Detail scraper script not found: {self.detail_scraper_path}"
                )

            return True
        except Exception as e:
            self.logger.error(f"Dependency check failed: {e}")
            return False

    def collect_list_from_node(self, region, pages=None):
        """Call Node.js script to collect announcement list"""
        try:
            self.logger.info(f"Collecting list for {region} ({pages} pages)...")

            # Run Node.js list collector
            result = subprocess.run(
                [
                    self.node_path,
                    self.list_collector_path,
                    "--region",
                    region,
                    "--pages",
                    str(pages),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                self.logger.error(f"Node.js error for {region}: {result.stderr}")
                return []

            # Parse JSON output (stdout contains JSON, stderr contains logs)
            # Display Node.js debug output (from stderr)
            if result.stderr and (self.test_mode or self.verbose):
                # Show the Node.js debug output
                self.logger.info(f"\n=== Node.js 수집 로그 ({region}) ===")
                for line in result.stderr.split('\n'):
                    if '수집된 공고 목록' in line:
                        # Start of announcement list
                        self.logger.info(line)
                    elif line.strip() and ('===' in line or '[' in line):
                        self.logger.info(f"  {line}")
            
            try:
                data = json.loads(result.stdout)
                if data.get("status") == "success":
                    announcements = data.get("data", [])
                    self.logger.info(
                        f"Collected {len(announcements)} announcements from {region}"
                    )
                    
                    # Show collected announcement titles in debug/verbose mode
                    if (self.test_mode or self.verbose) and announcements:
                        self.logger.info("Collected announcements summary:")
                        for idx, ann in enumerate(announcements[:10], 1):  # Show first 10
                            self.logger.info(f"  {idx}. [{ann.get('id')}] {ann.get('title')[:50]}... ({ann.get('date')})")
                        if len(announcements) > 10:
                            self.logger.info(f"  ... and {len(announcements) - 10} more")
                    
                    return announcements
                else:
                    self.logger.error(f"Collection failed for {region}")
                    return []
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON from Node.js: {e}")
                self.logger.debug(f"stdout: {result.stdout[:500]}")
                return []

        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout collecting list for {region}")
            return []
        except Exception as e:
            self.logger.error(f"Error collecting list for {region}: {e}")
            return []

    def check_url_exists_in_db(self, url):
        """Check if URL already exists in database"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()

        # URL에서 announcement_id 추출 (더 정확한 중복 체크)
        import re

        id_match = re.search(r"not_ancmt_mgt_no=(\d+)", url)

        if id_match:
            announcement_id = id_match.group(1)
            # announcement_id로도 체크
            cursor.execute(
                """
                SELECT id FROM eminwon_url_registry 
                WHERE announcement_url = %s OR announcement_id = %s
            """,
                (url, announcement_id),
            )
        else:
            cursor.execute(
                """
                SELECT id FROM eminwon_url_registry 
                WHERE announcement_url = %s
            """,
                (url,),
            )

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        return result is not None

    def filter_new_announcements(self, announcements):
        """Filter announcements to find only new ones"""
        new_announcements = []
        duplicate_details = []

        for ann in announcements:
            url = ann.get("url")
            if not url:
                continue

            if not self.check_url_exists_in_db(url):
                new_announcements.append(ann)
                self.stats["new_found"] += 1
                if self.verbose or self.test_mode:
                    self.logger.info(f"  ✅ NEW: [{ann.get('id')}] {ann.get('title')[:50]}...")
            else:
                self.stats["duplicates"] += 1
                duplicate_details.append(ann)
                if self.verbose or self.test_mode:
                    self.logger.info(f"  ⏭️  DUPLICATE: [{ann.get('id')}] {ann.get('title')[:50]}...")

        # Summary of filtering results
        if self.verbose or self.test_mode:
            self.logger.info(f"\n📊 필터링 결과: 신규 {len(new_announcements)}개, 중복 {len(duplicate_details)}개")

        return new_announcements

    def download_announcement_detail(self, region, announcement, index=None):
        """Call Node.js script to download announcement detail"""
        try:
            ann_id = announcement.get("id")
            title = announcement.get("title", "")

            if self.verbose or self.test_mode:
                self.logger.info(
                    f"\n  📥 다운로드 시도 #{index if index else '?'}: [{ann_id}] {title[:50]}..."
                )

            # Prepare output directory with index if provided
            safe_title = "".join(
                c for c in title if c.isalnum() or c in (" ", "-", "_")
            )[:100]
            if index:
                # 인덱스_공고번호_제목 형식
                folder_name = f"{str(index).zfill(3)}_{ann_id}_{safe_title}"
            else:
                folder_name = f"{ann_id}_{safe_title}"

            # Run Node.js detail scraper with title and date
            cmd = [
                self.node_path,
                self.detail_scraper_path,
                "--region",
                region,
                "--url",
                announcement.get("url"),
                "--output-dir",
                str(self.output_dir / region),
                "--folder-name",
                folder_name,
            ]

            # Add title and date if available (properly escaped)
            ann_title = announcement.get("title", "")
            ann_date = announcement.get("date", "")

            if ann_title:
                cmd.extend(["--title", ann_title])
            if ann_date:
                cmd.extend(["--date", ann_date])

            # Debug: log the actual command
            self.logger.debug(
                f"Command: {' '.join(cmd[:8])}... --title '{ann_title}' --date '{ann_date}'"
            )

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                self.logger.info(f"  ✅ DOWNLOADED: [{ann_id}] {title[:50]}...")
                self.stats["downloaded"] += 1

                # Parse actual title from Node.js output
                actual_title = None
                try:
                    # Node.js가 JSON으로 출력한 결과 파싱
                    for line in result.stdout.split("\n"):
                        if line.strip().startswith("{") and '"actualTitle"' in line:
                            import json

                            data = json.loads(line)
                            actual_title = data.get("actualTitle")
                            break
                except Exception as e:
                    self.logger.debug(f"Could not parse actual title: {e}")

                # Use actual title if found, otherwise use list title
                if actual_title and actual_title != "제목 없음":
                    # Create new folder name with actual title
                    safe_actual_title = "".join(
                        c for c in actual_title if c.isalnum() or c in (" ", "-", "_")
                    )[:100]
                    if index:
                        # 인덱스_공고번호_실제제목 형식 유지
                        new_folder_name = (
                            f"{str(index).zfill(3)}_{ann_id}_{safe_actual_title}"
                        )
                    else:
                        new_folder_name = f"{ann_id}_{safe_actual_title}"

                    # Rename folder if different
                    if new_folder_name != folder_name:
                        old_path = self.output_dir / region / folder_name
                        new_path = self.output_dir / region / new_folder_name

                        if old_path.exists():
                            import shutil

                            shutil.move(str(old_path), str(new_path))
                            self.logger.info(
                                f"Renamed folder: {folder_name} -> {new_folder_name}"
                            )
                            folder_name = new_folder_name

                # Save to database with final folder name
                self.save_to_database(region, announcement, folder_name)
                return True
            else:
                self.logger.error(f"  ❌ FAILED: [{ann_id}] {title[:50]}...")
                if self.verbose or self.test_mode:
                    self.logger.debug(f"    Error: {result.stderr[:200]}")
                self.stats["errors"] += 1
                return False

        except subprocess.TimeoutExpired:
            self.logger.error(
                f"Timeout downloading: {announcement.get('title', 'Unknown')[:30]}"
            )
            self.stats["errors"] += 1
            return False
        except Exception as e:
            self.logger.error(f"Error downloading announcement: {e}")
            self.stats["errors"] += 1
            return False

    def save_to_database(self, region, announcement, folder_name):
        """Save announcement info to database"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()

        try:
            # Generate content hash (simplified - you may want to hash actual content)
            content_hash = hashlib.sha256(
                f"{announcement.get('id')}_{announcement.get('title')}".encode()
            ).hexdigest()

            # 지역명 정규화 (구, 시, 군 제거하여 DB와 일치시킴)
            normalized_region = region
            if region.endswith("구"):
                normalized_region = region[:-1]
            elif region.endswith("시") and len(region) > 2:
                normalized_region = region[:-1]
            elif region.endswith("군"):
                normalized_region = region[:-1]

            # Normalize text to NFC (standard Korean form)
            import unicodedata

            insert_sql = """
            INSERT INTO eminwon_url_registry 
            (region, folder_name, announcement_url, announcement_id, title, post_date, content_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            last_checked_date = CURRENT_TIMESTAMP
            """

            # 날짜 처리 (빈 문자열은 None으로)
            post_date = announcement.get("date")
            if post_date and post_date.strip():
                post_date = post_date.strip()
            else:
                post_date = None

            cursor.execute(
                insert_sql,
                (
                    unicodedata.normalize(
                        "NFC", normalized_region
                    ),  # NFC normalized region
                    unicodedata.normalize("NFC", folder_name),
                    announcement.get("url"),
                    announcement.get("id"),
                    unicodedata.normalize("NFC", announcement.get("title", "")),
                    post_date,
                    content_hash,
                ),
            )

            conn.commit()

        except Exception as e:
            self.logger.error(f"Database error: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    def process_region(self, region):
        """Process a single region"""
        region_stats = {"checked": 0, "new": 0, "downloaded": 0}

        try:
            # 1. Collect list from Node.js
            pages = (
                self.pages if hasattr(self, "pages") else (1 if self.test_mode else 3)
            )
            announcements = self.collect_list_from_node(region, pages)

            if not announcements:
                self.logger.warning(f"No announcements collected for {region}")
                return region_stats

            region_stats["checked"] = len(announcements)
            self.stats["total_checked"] += len(announcements)

            # 2. Filter new announcements
            new_announcements = self.filter_new_announcements(announcements)
            region_stats["new"] = len(new_announcements)

            if not new_announcements:
                self.logger.info(f"No new announcements for {region}")
                return region_stats

            self.logger.info(
                f"Found {len(new_announcements)} new announcements for {region}"
            )

            # 3. Download new announcements with index
            if self.verbose or self.test_mode:
                self.logger.info(f"\n🔽 다운로드 시작 ({len(new_announcements)}개)...")
            
            for idx, ann in enumerate(new_announcements, start=1):
                if self.test_mode and region_stats["downloaded"] >= 2:
                    self.logger.info(f"  ⚠️  테스트 모드: 2개 제한에 도달")
                    break

                if self.download_announcement_detail(region, ann, index=idx):
                    region_stats["downloaded"] += 1

            # Processing summary for this region
            if self.verbose or self.test_mode:
                self.logger.info(f"\n📋 {region} 처리 결과:")
                self.logger.info(f"  - 확인됨: {region_stats['checked']}개")
                self.logger.info(f"  - 신규: {region_stats['new']}개")
                self.logger.info(f"  - 다운로드 성공: {region_stats['downloaded']}개")
                self.logger.info(f"  - 중복: {region_stats['checked'] - region_stats['new']}개")

            return region_stats

        except Exception as e:
            self.logger.error(f"Error processing region {region}: {e}")
            return region_stats

    def run(self):
        """Main execution method"""
        self.logger.info("=" * 80)
        self.logger.info(
            "Starting Eminwon Incremental Collection (Node.js Integration)"
        )
        self.logger.info("=" * 80)

        # Check dependencies
        if not self.check_node_dependencies():
            self.logger.error("Dependency check failed. Exiting.")
            return False

        # Filter regions if specified
        if self.specific_regions:
            regions_to_process = {
                k: v
                for k, v in self.eminwon_config.items()
                if k in self.specific_regions
            }
        else:
            regions_to_process = self.eminwon_config

        self.logger.info(f"Processing {len(regions_to_process)} regions...")

        # Process regions
        if self.test_mode or len(regions_to_process) <= 5:
            # Sequential processing for test mode or small batches
            for region in regions_to_process:
                self.logger.info(f"\n{'='*40}")
                self.logger.info(f"Processing: {region}")
                self.logger.info(f"{'='*40}")
                stats = self.process_region(region)
                self.logger.info(
                    f"Results: Checked={stats['checked']}, New={stats['new']}, Downloaded={stats['downloaded']}"
                )
        else:
            # Parallel processing for production
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(self.process_region, region): region
                    for region in regions_to_process
                }

                for future in tqdm(
                    as_completed(futures), total=len(futures), desc="Processing regions"
                ):
                    region = futures[future]
                    try:
                        stats = future.result(timeout=300)
                        if stats["new"] > 0:
                            tqdm.write(
                                f"✓ {region:15} - New: {stats['new']:3}, Downloaded: {stats['downloaded']:3}"
                            )
                    except Exception as e:
                        self.logger.error(f"Failed processing {region}: {e}")

        # Print summary
        self.logger.info("\n" + "=" * 80)
        self.logger.info("Collection Summary:")
        self.logger.info("=" * 80)
        self.logger.info(
            f"Total announcements checked: {self.stats['total_checked']:,}"
        )
        self.logger.info(f"New announcements found: {self.stats['new_found']:,}")
        self.logger.info(f"Successfully downloaded: {self.stats['downloaded']:,}")
        self.logger.info(f"Duplicates (already in DB): {self.stats['duplicates']:,}")
        self.logger.info(f"Errors: {self.stats['errors']:,}")
        self.logger.info("=" * 80)

        # Save statistics
        stats_file = self.output_dir / "collection_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "stats": self.stats,
                    "regions_processed": len(regions_to_process),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        return True


def main():
    parser = argparse.ArgumentParser(description="Eminwon Incremental Orchestrator")
    parser.add_argument("--test", action="store_true", help="Run in test mode")
    parser.add_argument(
        "--regions",
        nargs="+",
        help="Specific regions to process (e.g., --regions 청주시 가평군)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=3,
        help="Number of pages to collect per region (default: 3)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed Node.js collection logs",
    )

    args = parser.parse_args()

    orchestrator = EminwonIncrementalOrchestrator(
        test_mode=args.test, 
        specific_regions=args.regions,
        verbose=args.verbose
    )

    # 페이지 수 설정 (테스트 모드면 1, 아니면 지정값 또는 기본값 3)
    if args.test:
        orchestrator.pages = 1
    else:
        orchestrator.pages = args.pages

    success = orchestrator.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
