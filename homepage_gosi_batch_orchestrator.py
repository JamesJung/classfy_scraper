#!/usr/bin/env python3
"""
통합 배치 오케스트레이터
314개 개별 스크래퍼를 위한 일일 배치 처리
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


# 로깅 설정은 나중에 main에서 처리
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
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)  # 파일에는 항상 DEBUG 레벨 저장
        file_formatter = logging.Formatter(log_format, date_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        logging.info(f"로그 파일: {log_file}")

    return logger


class HomepageGosiBatchOrchestrator:
    def __init__(
        self,
        data_dir: str = "scraped_batch_data",
        max_workers: int = 4,
        show_node_output: bool = False,
    ):
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
        # orchestrator가 classfy_scraper 루트에 있으므로 node 디렉토리는 하위에 있음
        self.base_dir = Path(__file__).parent
        self.node_dir = self.base_dir / "node"
        self.list_collector_script = self.node_dir / "homepage_gosi_list_collector.js"
        self.detail_downloader_script = (
            self.node_dir / "homepage_gosi_detail_downloader.js"
        )
        self.configs_dir = self.node_dir / "configs"

        # Python 처리 스크립트 (같은 디렉토리)
        self.pre_processor_script = self.base_dir / "announcement_pre_processor.py"

        # DB 연결 정보
        self.db_config = self._load_db_config()

    def _load_db_config(self) -> Dict:
        """환경 변수에서 DB 설정 로드"""
        from dotenv import load_dotenv

        load_dotenv()

        return {
            "host": os.environ.get("DB_HOST"),
            "user": os.environ.get("DB_USER"),
            "password": os.environ.get("DB_PASSWORD"),
            "database": os.environ.get("DB_NAME"),
            "port": int(os.environ.get("DB_PORT")),
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
        }

    def get_active_sites(self) -> List[Dict]:
        """활성화된 사이트 목록 조회"""
        sites = []

        # configs 디렉토리 확인
        if not self.configs_dir.exists():
            logging.error(f"설정 디렉토리가 없습니다: {self.configs_dir}")
            return sites

        logging.info(f"설정 디렉토리: {self.configs_dir}")

        # configs 디렉토리에서 설정 파일 찾기
        for config_file in self.configs_dir.glob("*.json"):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    site_code = config.get("siteCode", config_file.stem)

                    sites.append(
                        {
                            "site_code": site_code,
                            "site_name": config.get("siteName", site_code),
                            "config_file": config_file.name,
                            "daily_pages": config.get("dailyPages", 3),
                        }
                    )
            except Exception as e:
                logging.error(f"설정 파일 로드 실패 {config_file}: {e}")

        # DB에서 추가 설정 가져오기 (있는 경우)
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT site_code, site_name, daily_pages, priority
                FROM homepage_gosi_site_config
                WHERE is_active = TRUE
                ORDER BY priority, site_code
            """
            )

            db_sites = cursor.fetchall()

            # DB 설정으로 업데이트
            site_map = {s["site_code"]: s for s in sites}
            for db_site in db_sites:
                if db_site["site_code"] in site_map:
                    site_map[db_site["site_code"]]["daily_pages"] = db_site[
                        "daily_pages"
                    ]

            cursor.close()
            conn.close()

        except Error as e:
            logging.warning(f"DB 설정 조회 실패 (기본값 사용): {e}")

        return sorted(sites, key=lambda x: x["site_code"])

    def run_list_collection(self, site: Dict) -> Optional[Dict]:
        """리스트 수집 실행"""
        site_code = site["site_code"]
        pages = site.get("daily_pages", 3)

        logging.info(f"[{site_code}] 리스트 수집 시작 (페이지: {pages})")

        try:
            cmd = [
                "node",
                str(self.list_collector_script),
                site_code,
                "--pages",
                str(pages),
            ]

            # 디버깅 로그
            logging.debug(f"[{site_code}] 실행 명령: {' '.join(cmd)}")
            logging.debug(f"[{site_code}] 작업 디렉토리: {self.node_dir}")

            if self.show_node_output:
                # 실시간 출력 모드
                logging.info(f"[{site_code}] === Node.js 출력 시작 ===")

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(self.node_dir),
                    bufsize=1,  # 라인 버퍼링
                )

                output_lines = []
                for line in process.stdout:
                    line = line.rstrip()
                    if line:
                        print(f"  [NODE] {line}")  # 실시간 출력
                        logging.debug(f"  [NODE] {line}")  # 파일에도 저장
                        output_lines.append(line)

                process.wait()
                result_stdout = "\n".join(output_lines)
                result_returncode = process.returncode

                logging.info(f"[{site_code}] === Node.js 출력 종료 ===")

            else:
                # 기존 방식 (캡처만)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(self.node_dir),
                )
                result_stdout = result.stdout
                result_returncode = result.returncode

            # 실행 결과 로그
            if result_returncode != 0:
                logging.debug(
                    f"[{site_code}] 리스트 수집 실패 - 종료코드: {result_returncode}"
                )
                logging.debug(
                    f"[{site_code}] OUTPUT: {result_stdout[:500]}"
                )  # 첫 500자만
                logging.error(f"[{site_code}] 리스트 수집 실패")
                return None

            # JSON 출력 파싱
            output = result_stdout
            if "JSON_OUTPUT_START" in output and "JSON_OUTPUT_END" in output:
                json_str = (
                    output.split("JSON_OUTPUT_START")[1]
                    .split("JSON_OUTPUT_END")[0]
                    .strip()
                )
                return json.loads(json_str)

            # 기본 통계 추출
            stats = {
                "siteCode": site_code,
                "stats": {"newItems": 0, "duplicates": 0, "totalItems": 0},
            }

            # 로그에서 통계 추출
            for line in output.split("\n"):
                if "신규:" in line:
                    stats["stats"]["newItems"] = int(
                        line.split("신규:")[1].split("개")[0].strip()
                    )
                elif "중복:" in line:
                    stats["stats"]["duplicates"] = int(
                        line.split("중복:")[1].split("개")[0].strip()
                    )

            return stats

        except subprocess.TimeoutExpired:
            logging.error(f"[{site_code}] 리스트 수집 타임아웃")
        except Exception as e:
            logging.error(f"[{site_code}] 리스트 수집 오류: {e}")

        return None

    def run_detail_download(self, site_code: str, limit: int = 100) -> bool:
        """상세 다운로드 실행"""
        logging.info(f"[{site_code}] 상세 다운로드 시작 (최대: {limit}개)")

        try:
            cmd = [
                "node",
                str(self.detail_downloader_script),
                site_code,
                "--limit",
                str(limit),
            ]

            # 디버깅 로그
            logging.debug(f"[{site_code}] 다운로드 명령: {' '.join(cmd)}")
            logging.debug(f"[{site_code}] 작업 디렉토리: {self.node_dir}")

            if self.show_node_output:
                # 실시간 출력 모드
                logging.info(f"[{site_code}] === Node.js 다운로드 출력 시작 ===")

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(self.node_dir),
                    bufsize=1,
                )

                output_lines = []
                for line in process.stdout:
                    line = line.rstrip()
                    if line:
                        print(f"  [NODE] {line}")
                        logging.debug(f"  [NODE] {line}")
                        output_lines.append(line)

                process.wait()
                result_stdout = "\n".join(output_lines)
                result_returncode = process.returncode

                logging.info(f"[{site_code}] === Node.js 다운로드 출력 종료 ===")

            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=1800,  # 30분
                    cwd=str(self.node_dir),
                )
                result_stdout = result.stdout
                result_returncode = result.returncode

            # 실행 결과 로그
            if result_returncode != 0:
                logging.debug(
                    f"[{site_code}] 다운로드 실패 - 종료코드: {result_returncode}"
                )
                logging.debug(f"[{site_code}] OUTPUT: {result_stdout[:500]}")
                logging.error(f"[{site_code}] 상세 다운로드 실패")
                return False

            # 성공 통계 추출
            output = result_stdout

            # 전체 출력 로그 (디버그 모드)
            logging.debug(f"[{site_code}] 다운로드 출력:\n{output[:1000]}")

            for line in output.split("\n"):
                if "성공:" in line:
                    success_count = int(line.split("성공:")[1].split("개")[0].strip())
                    self.stats["total_downloads"] += success_count
                    logging.info(f"[{site_code}] 다운로드 완료: {success_count}개")
                elif "실패:" in line:
                    failed_count = int(line.split("실패:")[1].split("개")[0].strip())
                    if failed_count > 0:
                        logging.warning(
                            f"[{site_code}] 다운로드 실패: {failed_count}개"
                        )

            return True

        except subprocess.TimeoutExpired:
            logging.error(f"[{site_code}] 상세 다운로드 타임아웃")
        except Exception as e:
            logging.error(f"[{site_code}] 상세 다운로드 오류: {e}")

        return False

    def run_pre_processing(self, site_code: str) -> bool:
        """announcement_pre_processor.py 실행"""
        site_dir = self.data_dir / site_code

        if not site_dir.exists():
            logging.warning(f"[{site_code}] 데이터 디렉토리 없음: {site_dir}")
            return False

        logging.info(f"[{site_code}] 공고 전처리 시작")

        try:
            cmd = [
                sys.executable,
                str(self.pre_processor_script),
                "-d",
                str(site_dir),
                "--site-code",
                site_code,
                "--force",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10분
                cwd=str(self.pre_processor_script.parent),
            )

            if result.returncode != 0:
                logging.error(f"[{site_code}] 전처리 실패: {result.stderr}")
                return False

            logging.info(f"[{site_code}] 전처리 완료")
            return True

        except subprocess.TimeoutExpired:
            logging.error(f"[{site_code}] 전처리 타임아웃")
        except Exception as e:
            logging.error(f"[{site_code}] 전처리 오류: {e}")

        return False

    def process_site(self, site: Dict) -> Tuple[str, bool, Dict]:
        """단일 사이트 처리 (리스트 → 다운로드 → 전처리)"""
        site_code = site["site_code"]
        result = {"new_items": 0, "downloads": 0, "errors": []}

        try:
            # 1. 리스트 수집
            list_result = self.run_list_collection(site)
            if not list_result:
                result["errors"].append("리스트 수집 실패")
                return site_code, False, result

            new_items = list_result.get("stats", {}).get("newItems", 0)
            result["new_items"] = new_items

            if new_items == 0:
                logging.info(f"[{site_code}] 신규 항목 없음")
                return site_code, True, result

            # 2. 상세 다운로드
            if not self.run_detail_download(site_code, limit=new_items):
                result["errors"].append("상세 다운로드 실패")
                return site_code, False, result

            # 3. 전처리
            if not self.run_pre_processing(site_code):
                result["errors"].append("전처리 실패")
                # 전처리 실패는 경고로 처리
                logging.warning(f"[{site_code}] 전처리 실패했지만 계속 진행")

            return site_code, True, result

        except Exception as e:
            logging.error(f"[{site_code}] 처리 중 오류: {e}")
            result["errors"].append(str(e))
            return site_code, False, result

    def save_batch_log(self):
        """배치 실행 로그 DB 저장"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO homepage_gosi_processing_log 
                (run_date, run_type, total_checked, new_found, downloaded, failed)
                VALUES (CURDATE(), 'daily', %s, %s, %s, %s)
            """,
                (
                    self.stats["sites_processed"],
                    self.stats["total_new_items"],
                    self.stats["total_downloads"],
                    self.stats["total_failures"],
                ),
            )

            conn.commit()
            cursor.close()
            conn.close()

            logging.info("배치 로그 저장 완료")

        except Error as e:
            logging.error(f"배치 로그 저장 실패: {e}")

    def run_batch(self, site_codes: Optional[List[str]] = None):
        """배치 실행"""
        start_time = time.time()

        print("\n" + "=" * 60)
        print(f"통합 배치 처리 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # 활성 사이트 목록 조회
        sites = self.get_active_sites()

        print(f"sites==== {sites}")
        # 특정 사이트만 처리
        if site_codes:
            sites = [s for s in sites if s["site_code"] in site_codes]

        if not sites:
            logging.warning("처리할 사이트가 없습니다")
            return

        print(f"처리 대상: {len(sites)}개 사이트")
        print(f"워커 수: {self.max_workers}")
        print()

        # 병렬 처리
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.process_site, site): site for site in sites}

            completed = 0
            for future in as_completed(futures):
                site = futures[future]
                site_code, success, result = future.result()

                completed += 1
                self.stats["sites_processed"] += 1

                if success:
                    self.stats["total_new_items"] += result["new_items"]
                    print(
                        f"[{completed}/{len(sites)}] ✓ {site_code}: {result['new_items']}개 신규"
                    )
                else:
                    self.stats["total_failures"] += 1
                    self.stats["sites_with_errors"].append(site_code)
                    print(
                        f"[{completed}/{len(sites)}] ✗ {site_code}: {', '.join(result['errors'])}"
                    )

        # 통계 출력
        elapsed_time = int(time.time() - start_time)

        print("\n" + "=" * 60)
        print("배치 처리 완료")
        print("=" * 60)
        print(f"처리 시간: {elapsed_time//60}분 {elapsed_time%60}초")
        print(f"처리 사이트: {self.stats['sites_processed']}개")
        print(f"신규 항목: {self.stats['total_new_items']}개")
        print(f"다운로드: {self.stats['total_downloads']}개")
        print(f"실패: {self.stats['total_failures']}개")

        if self.stats["sites_with_errors"]:
            print(f"오류 사이트: {', '.join(self.stats['sites_with_errors'])}")

        # DB 로그 저장
        self.save_batch_log()


def main():
    parser = argparse.ArgumentParser(description="통합 스크래퍼 배치 처리")
    parser.add_argument("--sites", nargs="+", help="처리할 사이트 코드 (미지정시 전체)")
    parser.add_argument("--workers", type=int, default=4, help="병렬 워커 수 (기본: 4)")
    parser.add_argument(
        "--data-dir",
        default="scraped_batch_data",
        help="데이터 디렉토리 (기본: scraped_batch_data)",
    )
    parser.add_argument("--debug", action="store_true", help="디버그 로그 출력")
    parser.add_argument(
        "--log-file", help="로그 파일 경로 (예: logs/batch_20250924.log)"
    )
    parser.add_argument(
        "--show-node", action="store_true", help="Node.js 출력 실시간 표시"
    )

    args = parser.parse_args()

    # 로그 디렉토리 생성
    if args.log_file:
        log_dir = Path(args.log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)

    # 로깅 설정
    setup_logging(debug=args.debug, log_file=args.log_file)

    # 디버그 모드 설정
    if args.debug:
        logging.debug("디버그 모드 활성화")
        logging.debug(f"명령줄 인자: {args}")

    orchestrator = HomepageGosiBatchOrchestrator(
        data_dir=args.data_dir,
        max_workers=args.workers,
        show_node_output=args.show_node
        or args.debug,  # 디버그 모드에서는 자동으로 Node 출력 표시
    )

    orchestrator.run_batch(site_codes=args.sites)


if __name__ == "__main__":
    main()
