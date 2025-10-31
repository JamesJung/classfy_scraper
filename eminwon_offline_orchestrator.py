#!/usr/bin/env python3

"""
Eminwon 오프라인 오케스트레이터
DB 연결 없이 Node.js 스크래퍼만 사용해서 데이터 수집
"""

import os
import json
import subprocess
import argparse
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

class EminwonOfflineOrchestrator:
    def __init__(self, test_mode=False, specific_regions=None, verbose=False, max_workers=3, target_date=None):
        # Load environment variables
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        # Set up directories
        today = datetime.now().strftime("%Y-%m-%d")
        
        # .env에서 EMINWON_OUTPUT_BASE_DIR 설정 읽기, 없으면 기본값 사용
        output_base = os.environ.get("EMINWON_OUTPUT_BASE_DIR", "batch_eminwon_result_offline")
        # offline 버전은 _offline suffix 추가
        if not output_base.endswith("_offline"):
            output_base = f"{output_base}_offline"
        
        self.output_base_dir = Path(f"{output_base}/{today}")
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        
        # Node.js paths
        self.node_path = "node"
        self.eminwon_scraper_path = "node/scraper/eminwon_scraper.js"
        
        # 기본 지역 목록 (테스트용)
        self.default_regions = [
            "가평군", "청주시", "서울특별시", "부산광역시", "대구광역시"
        ]
        
        # Statistics
        self.stats = {
            "total_regions": 0,
            "success_regions": 0,
            "failed_regions": 0,
            "total_collected": 0,
            "errors": []
        }
        
        self.test_mode = test_mode
        self.specific_regions = specific_regions or self.default_regions
        self.verbose = verbose
        self.max_workers = max_workers
        self.target_date = target_date or datetime.now().strftime('%Y%m%d')
        
        # Setup logging
        self.setup_logging()
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
        
        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f'eminwon_offline_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        
        logging.basicConfig(
            level=logging.DEBUG if self.test_mode else logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_file, encoding='utf-8')
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
            if not Path(self.eminwon_scraper_path).exists():
                raise Exception(f"Scraper script not found: {self.eminwon_scraper_path}")

            return True
        except Exception as e:
            self.logger.error(f"Dependency check failed: {e}")
            return False
    
    def extract_collected_count(self, output_text):
        """Extract collected count from scraper output"""
        try:
            import re
            # Look for patterns like "N개 수집 완료" or "N개 공고 수집"
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
    
    def process_region(self, region):
        """Process a single region"""
        start_time = datetime.now()
        
        try:
            self.logger.info(f"Processing {region} from {self.target_date}")
            
            # Create output directory for this region
            output_dir = self.output_base_dir / region
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Build command for eminwon_scraper.js
            cmd_args = [
                self.node_path,
                self.eminwon_scraper_path,
                "--region",
                region,
                "--date",
                self.target_date,
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
                timeout=300,  # 5분 타임아웃
            )
            
            end_time = datetime.now()
            collected_count = 0
            
            if result.returncode == 0:
                # Success - extract collected count
                collected_count = self.extract_collected_count(result.stderr + result.stdout)
                
                self.logger.info(f"✅ {region}: {collected_count}개 수집 완료")
                self.stats['success_regions'] += 1
                self.stats['total_collected'] += collected_count
                
                return {'status': 'success', 'collected': collected_count, 'region': region}
            else:
                # Scraper failed
                error_msg = f"Scraper failed: {result.stderr[:200] if result.stderr else 'Unknown error'}"
                self.logger.error(f"❌ {region}: {error_msg}")
                
                self.stats['failed_regions'] += 1
                self.stats['errors'].append(f"{region}: {error_msg}")
                
                return {'status': 'failed', 'error': error_msg, 'region': region}
                
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout after 5 minutes"
            self.logger.error(f"⏰ {region}: {error_msg}")
            
            self.stats['failed_regions'] += 1
            self.stats['errors'].append(f"{region}: {error_msg}")
            
            return {'status': 'timeout', 'error': error_msg, 'region': region}
            
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            self.logger.error(f"💥 {region}: {error_msg}")
            
            self.stats['failed_regions'] += 1
            self.stats['errors'].append(f"{region}: {error_msg}")
            
            return {'status': 'error', 'error': error_msg, 'region': region}
    
    def run(self):
        """Main execution method"""
        self.logger.info("=" * 80)
        self.logger.info("Starting Eminwon Offline Collection")
        self.logger.info(f"Target Date: {self.target_date}")
        self.logger.info(f"Output Directory: {self.output_base_dir}")
        self.logger.info("=" * 80)

        # Check dependencies
        if not self.check_node_dependencies():
            self.logger.error("Dependency check failed. Exiting.")
            return False

        regions_to_process = self.specific_regions
        self.stats['total_regions'] = len(regions_to_process)
        
        self.logger.info(f"Processing {len(regions_to_process)} regions...")
        
        # Process regions
        if self.test_mode or len(regions_to_process) <= 3:
            # Sequential processing for test mode or small batches
            self.logger.info("Using sequential processing")
            for region in regions_to_process:
                result = self.process_region(region)
                if self.verbose:
                    self.logger.info(f"Result for {result['region']}: {result['status']}")
        else:
            # Parallel processing
            self.logger.info(f"Using parallel processing with {self.max_workers} workers")
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all tasks
                future_to_region = {
                    executor.submit(self.process_region, region): region
                    for region in regions_to_process
                }

                # Process results as they complete
                for future in tqdm(as_completed(future_to_region), total=len(future_to_region), 
                                 desc="Processing regions"):
                    region = future_to_region[future]
                    try:
                        result = future.result(timeout=360)  # 6분 타임아웃
                        if result['status'] == 'success':
                            tqdm.write(f"✅ {region}: {result.get('collected', 0)}개 수집")
                        else:
                            tqdm.write(f"❌ {region}: {result['status']}")
                    except Exception as e:
                        self.logger.error(f"Failed processing {region}: {e}")
                        self.stats['failed_regions'] += 1

        # Print summary
        self.print_summary()

        return self.stats['failed_regions'] == 0
    
    def print_summary(self):
        """Print execution summary"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("EXECUTION SUMMARY")
        self.logger.info("=" * 80)
        self.logger.info(f"Target Date: {self.target_date}")
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
    parser = argparse.ArgumentParser(description="Eminwon Offline Orchestrator")
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
        help="Target date in YYYYMMDD format (e.g., 20241025). If not specified, uses today",
    )

    args = parser.parse_args()

    orchestrator = EminwonOfflineOrchestrator(
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