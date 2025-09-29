#!/usr/bin/env python3
"""
통합 배치 오케스트레이터 - 향상된 로깅 버전
파일 로깅과 Node.js 출력 실시간 표시 지원
"""

import json
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime
import logging
import time
from typing import Dict, List, Optional, Tuple
import mysql.connector
from mysql.connector import Error
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse

def setup_logging(debug=False, log_file=None):
    """로깅 설정 - 콘솔과 파일 동시 출력"""
    
    # 로그 포맷
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # 기본 로거 설정
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # 기존 핸들러 제거
    logger.handlers.clear()
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_formatter = logging.Formatter(log_format, date_format)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 파일 핸들러 (옵션)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # 파일에는 항상 DEBUG 레벨 저장
        file_formatter = logging.Formatter(log_format, date_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        logging.info(f"로그 파일: {log_file}")
    
    return logger

class HomepageGosiBatchOrchestratorEnhanced:
    def __init__(self, data_dir: str = "scraped_data", max_workers: int = 4, 
                 show_node_output: bool = False):
        self.data_dir = Path(data_dir)
        self.max_workers = max_workers
        self.show_node_output = show_node_output  # Node.js 출력 실시간 표시 여부
        self.stats = {
            "sites_processed": 0,
            "total_new_items": 0,
            "total_downloads": 0,
            "total_failures": 0,
            "sites_with_errors": [],
        }

        # Node.js 스크립트 경로
        self.base_dir = Path(__file__).parent
        self.node_dir = self.base_dir / "node"
        self.list_collector_script = self.node_dir / "general_list_collector.js"
        self.detail_downloader_script = self.node_dir / "general_detail_downloader.js"
        self.configs_dir = self.node_dir / "configs"

        # Python 처리 스크립트
        self.pre_processor_script = self.base_dir / "announcement_pre_processor.py"

        # DB 연결 정보
        self.db_config = self._load_db_config()

    def _load_db_config(self) -> Dict:
        """환경 변수에서 DB 설정 로드"""
        from dotenv import load_dotenv
        load_dotenv()

        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 3306)),
            "user": os.getenv("DB_USER", "scraper"),
            "password": os.getenv("DB_PASSWORD"),
            "database": os.getenv("DB_NAME", "opendata"),
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
        }

    def run_list_collection_live(self, site: Dict) -> Optional[Dict]:
        """리스트 수집 실행 - 실시간 출력 버전"""
        site_code = site['site_code']
        pages = site.get('daily_pages', 3)

        logging.info(f"[{site_code}] 리스트 수집 시작 (페이지: {pages})")

        try:
            cmd = [
                "node",
                str(self.list_collector_script),
                site_code,
                "--pages", str(pages),
            ]
            
            logging.debug(f"[{site_code}] 실행 명령: {' '.join(cmd)}")
            logging.debug(f"[{site_code}] 작업 디렉토리: {self.node_dir}")

            if self.show_node_output:
                # 실시간 출력 모드
                logging.info(f"[{site_code}] Node.js 출력 시작 -----")
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(self.node_dir),
                    bufsize=1  # 라인 버퍼링
                )
                
                output_lines = []
                for line in process.stdout:
                    line = line.rstrip()
                    if line:
                        print(f"  [NODE] {line}")  # 실시간 출력
                        output_lines.append(line)
                
                process.wait()
                output = '\n'.join(output_lines)
                
                logging.info(f"[{site_code}] Node.js 출력 종료 -----")
                
                if process.returncode != 0:
                    logging.error(f"[{site_code}] 리스트 수집 실패 (종료코드: {process.returncode})")
                    return None
                    
            else:
                # 기존 방식 (캡처만)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(self.node_dir)
                )
                
                if result.returncode != 0:
                    logging.error(f"[{site_code}] 리스트 수집 실패: {result.stderr}")
                    return None
                
                output = result.stdout

            # JSON 출력 파싱
            if 'JSON_OUTPUT_START' in output and 'JSON_OUTPUT_END' in output:
                json_str = output.split('JSON_OUTPUT_START')[1].split('JSON_OUTPUT_END')[0].strip()
                return json.loads(json_str)

            # 기본 통계 추출
            stats = {
                'siteCode': site_code,
                'stats': {
                    'newItems': 0,
                    'duplicates': 0,
                    'totalItems': 0
                }
            }

            for line in output.split('\n'):
                if '신규:' in line:
                    stats['stats']['newItems'] = int(line.split('신규:')[1].split('개')[0].strip())
                elif '중복:' in line:
                    stats['stats']['duplicates'] = int(line.split('중복:')[1].split('개')[0].strip())

            return stats

        except Exception as e:
            logging.error(f"[{site_code}] 리스트 수집 오류: {e}")
            return None

    def run_batch(self, site_codes: Optional[List[str]] = None):
        """배치 실행 - 향상된 버전"""
        start_time = time.time()
        
        print("\n" + "="*60)
        print(f"통합 배치 처리 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        # 활성 사이트 목록 조회
        sites = self.get_active_sites()
        
        if site_codes:
            sites = [s for s in sites if s['site_code'] in site_codes]
        
        if not sites:
            logging.warning("처리할 사이트가 없습니다")
            return
        
        print(f"처리 대상: {len(sites)}개 사이트")
        print(f"Node.js 출력: {'표시' if self.show_node_output else '숨김'}")
        print()
        
        # 사이트별 처리
        for idx, site in enumerate(sites, 1):
            print(f"\n[{idx}/{len(sites)}] {site['site_code']} 처리 중...")
            
            # 리스트 수집 (실시간 출력 옵션)
            result = self.run_list_collection_live(site) if self.show_node_output else self.run_list_collection(site)
            
            if result and result.get('stats', {}).get('newItems', 0) > 0:
                # 상세 다운로드 등 추가 처리...
                pass
        
        elapsed_time = int(time.time() - start_time)
        
        print("\n" + "="*60)
        print(f"배치 처리 완료")
        print("="*60)
        print(f"처리 시간: {elapsed_time//60}분 {elapsed_time%60}초")

    def get_active_sites(self) -> List[Dict]:
        """활성화된 사이트 목록 조회"""
        sites = []
        
        if not self.configs_dir.exists():
            logging.error(f"설정 디렉토리가 없습니다: {self.configs_dir}")
            return sites
        
        for config_file in self.configs_dir.glob("*.json"):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    sites.append({
                        'site_code': config.get("siteCode", config_file.stem),
                        'site_name': config.get("siteName"),
                        'config_file': config_file.name,
                        'daily_pages': config.get("dailyPages", 3)
                    })
            except Exception as e:
                logging.error(f"설정 파일 로드 실패 {config_file}: {e}")
        
        return sorted(sites, key=lambda x: x['site_code'])
    
    def run_list_collection(self, site):
        """기존 리스트 수집 메소드 (호환성 유지)"""
        # 기존 구현...
        pass

def main():
    parser = argparse.ArgumentParser(description="통합 스크래퍼 배치 처리 - 향상된 버전")
    parser.add_argument("--sites", nargs="+", help="처리할 사이트 코드")
    parser.add_argument("--workers", type=int, default=4, help="병렬 워커 수")
    parser.add_argument("--data-dir", default="scraped_data", help="데이터 디렉토리")
    parser.add_argument("--debug", action="store_true", help="디버그 로그 출력")
    parser.add_argument("--log-file", help="로그 파일 경로 (예: logs/batch_20250924.log)")
    parser.add_argument("--show-node", action="store_true", 
                       help="Node.js 출력 실시간 표시")
    
    args = parser.parse_args()
    
    # 로그 설정
    if args.log_file:
        log_dir = Path(args.log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
    
    setup_logging(debug=args.debug, log_file=args.log_file)
    
    if args.debug:
        logging.debug("디버그 모드 활성화")
        logging.debug(f"명령줄 인자: {args}")
    
    # 오케스트레이터 실행
    orchestrator = HomepageGosiBatchOrchestratorEnhanced(
        data_dir=args.data_dir,
        max_workers=args.workers,
        show_node_output=args.show_node or args.debug  # 디버그 모드에서는 자동으로 Node 출력 표시
    )
    
    orchestrator.run_batch(site_codes=args.sites)

if __name__ == "__main__":
    main()