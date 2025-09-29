#!/usr/bin/env python3
"""
각 사이트의 다운로드된 최신 공고를 기준으로 DB 초기화
scraped_data 폴더를 읽어서 각 사이트의 최신 10개 공고를 DB에 등록
"""

import os
import sys
import json
import subprocess
import mysql.connector
from pathlib import Path
from datetime import datetime, timedelta
import re
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

load_dotenv()


class IncrementalDBInitializer:
    def __init__(self, data_dir: str = "scraped_data"):
        self.data_dir = Path(data_dir)
        self.node_dir = Path(__file__).parent / "node"
        self.configs_dir = self.node_dir / "configs"
        self.stats = {}

        # DB 연결 설정
        self.db_config = {
            "host": os.environ.get("DB_HOST"),
            "user": os.environ.get("DB_USER"),
            "password": os.environ.get("DB_PASSWORD"),
            "database": os.environ.get("DB_NAME"),
            "port": int(os.environ.get("DB_PORT", 3306)),
            "charset": "utf8mb4",
        }

    def get_site_name(self, site_code: str) -> str:
        """config 파일에서 siteName 읽기"""
        config_file = self.configs_dir / f"{site_code}.json"

        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("siteName", site_code.upper())
            except Exception as e:
                logging.warning(f"[{site_code}] config 파일 읽기 오류: {e}")

        return site_code.upper()  # 기본값: 사이트 코드 대문자

    def get_site_codes(self) -> List[str]:
        """scraped_data 하위 폴더에서 사이트 코드 추출"""
        site_codes = []

        if not self.data_dir.exists():
            logging.error(f"디렉토리가 없습니다: {self.data_dir}")
            return site_codes

        for item in self.data_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                site_codes.append(item.name)

        return sorted(site_codes)

    def get_recent_announcements(self, site_code: str, count: int = 10) -> List[Dict]:
        """사이트의 최신 다운로드된 공고 정보 추출"""
        site_dir = self.data_dir / site_code
        announcements = []

        if not site_dir.exists():
            return announcements

        # 폴더명 패턴: 001_제목, 002_제목 등
        folders = []
        for folder in site_dir.iterdir():
            if folder.is_dir() and re.match(r"^\d{3}_", folder.name):
                folders.append(folder)

        # 번호 기준으로 정렬 (오름차순 - 001이 가장 최신)
        folders.sort(key=lambda x: int(x.name[:3]))

        # 최신 n개 폴더에서 정보 추출
        for folder in folders[:count]:
            content_file = folder / "content.md"
            if content_file.exists():
                # 제목 추출 (폴더명에서)
                title = folder.name[4:].replace("_", " ")

                # content.md에서 날짜 추출 시도
                try:
                    with open(content_file, "r", encoding="utf-8") as f:
                        content = f.read()

                    # URL 추출 (다양한 패턴 시도)
                    url = None
                    url_patterns = [
                        r"\*\*원본 URL\*\*:\s*(.+)",  # **원본 URL**: 형식
                        r"# 상세 URL\s*[:：]\s*(.+)",  # # 상세 URL : 형식
                        r"상세 URL\s*[:：]\s*(.+)",  # 상세 URL: 형식
                    ]

                    for pattern in url_patterns:
                        url_match = re.search(pattern, content)
                        if url_match:
                            url = url_match.group(1).strip()
                            break

                    # announcement_id 추출 (URL에서)
                    announcement_id = None
                    if url:
                        # extract_announcement_id 메서드 사용 (site_code 전달)
                        announcement_id = self.extract_announcement_id(url, site_code)

                    # 날짜 추출 (다양한 패턴 시도)
                    date = None
                    # URL 부분을 제외한 본문만 추출 (원본 URL 라인 이후부터)
                    content_lines = content.split('\n')
                    # "**원본 URL**" 라인을 찾아서 그 이후부터 검색
                    url_line_index = -1
                    for i, line in enumerate(content_lines):
                        if '원본 URL' in line or 'URL' in line:
                            url_line_index = i
                            break
                    
                    if url_line_index >= 0:
                        content_without_url = '\n'.join(content_lines[url_line_index+1:])
                    else:
                        content_without_url = content
                    
                    date_patterns = [
                        r"작성일\s*[:：]\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2})",
                        r"등록일\s*[:：]\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2})",
                        r"게시일\s*[:：]\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2})",
                        r"(\d{4}[-./]\d{1,2}[-./]\d{1,2})",  # 단순 날짜 패턴
                    ]

                    for pattern in date_patterns:
                        date_match = re.search(pattern, content_without_url)
                        if date_match:
                            date = date_match.group(1)
                            # 날짜 정규화
                            date = date.replace("/", "-").replace(".", "-")
                            
                            # 날짜 범위인 경우 (예: 2025-06-02~2025-12-31) 첫 번째 날짜만 추출
                            if '~' in date:
                                date = date.split('~')[0].strip()
                            
                            break

                    announcements.append(
                        {
                            "folder_num": int(folder.name[:3]),
                            "title": title,
                            "date": date,
                            "url": url,
                            "announcement_id": announcement_id,
                            "folder_name": folder.name,
                        }
                    )

                except Exception as e:
                    logging.warning(f"파일 읽기 오류 {content_file}: {e}")

        return announcements

    def run_list_collector_with_early_stop(
        self, site_code: str, downloaded: List[Dict], max_pages: int = 20
    ) -> Tuple[List[Dict], Optional[int]]:
        """homepage_gosi_list_collector.js를 페이지별로 실행하여 1/2 이상 매칭시 조기 종료"""
        threshold = len(downloaded) // 2  # 다운로드된 공고의 1/2

        # downloaded가 없거나 적으면 날짜 기반 조기 종료 사용
        use_date_based_stop = len(downloaded) < 10
        consecutive_no_match = 0  # 연속으로 매칭 없는 페이지 수

        logging.info(
            f"[{site_code}] 리스트 수집 시작 (최대 {max_pages}페이지, {threshold}/{len(downloaded)}개 매칭시 조기 종료)"
        )
        if use_date_based_stop:
            logging.info(
                f"[{site_code}] downloaded 항목이 적어 날짜 기반 조기 종료 사용"
            )

        all_collected = []
        matched_items = []
        one_month_ago = datetime.now() - timedelta(days=30)

        for page in range(1, max_pages + 1):
            try:
                # 한 페이지씩 수집 (--start-page와 --pages로 특정 페이지만 가져오기)
                cmd = [
                    "node",
                    str(self.node_dir / "homepage_gosi_list_collector.js"),
                    site_code,
                    "--start-page",
                    str(page),
                    "--pages",
                    str(page),
                    "--no-insert",  # DB INSERT 없이 조회만 수행
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(self.node_dir),
                )

                if result.returncode != 0:
                    logging.warning(f"[{site_code}] {page}페이지 수집 실패")
                    break

                # JSON 출력 파싱
                output = result.stdout
                if "JSON_OUTPUT_START" in output and "JSON_OUTPUT_END" in output:
                    json_str = (
                        output.split("JSON_OUTPUT_START")[1]
                        .split("JSON_OUTPUT_END")[0]
                        .strip()
                    )
                    data = json.loads(json_str)

                    # 이번 페이지의 항목들 (no-db 모드에서는 allItems 사용)
                    page_items = data.get("allItems", data.get("newItems", []))
                    if not page_items:
                        logging.info(
                            f"[{site_code}] {page}페이지에 더 이상 항목이 없음"
                        )
                        break

                    logging.info(
                        f"[{site_code}] {page}페이지: {len(page_items)}개 항목 수집"
                    )

                    # 디버깅: 수집된 항목 출력
                    for idx, item in enumerate(page_items[:10], 1):
                        logging.info(
                            f"  [{idx}] {item.get('title', 'N/A')[:60]}... ({item.get('date', 'N/A')})"
                        )

                    # 이번 페이지의 모든 항목을 누적
                    all_collected.extend(page_items)

                    # 다운로드된 공고와 비교하여 매칭 찾기
                    for web_item in page_items:
                        for dl_item in downloaded:
                            if self.is_matching(dl_item, web_item):
                                # 중복 체크 (이미 매칭된 항목은 제외)
                                if not any(
                                    m["url"] == web_item["url"] for m in matched_items
                                ):
                                    # 다운로드된 공고의 announcement_id와 folder_name을 웹 항목에 추가
                                    enriched_item = web_item.copy()
                                    enriched_item["announcement_id"] = dl_item.get(
                                        "announcement_id"
                                    )
                                    enriched_item["folder_name"] = dl_item.get(
                                        "folder_name"
                                    )
                                    matched_items.append(enriched_item)

                                    logging.info(
                                        f"[{site_code}] 매칭 발견 ({len(matched_items)}/{len(downloaded)}): {web_item.get('title', '')[:50]}... [폴더: {dl_item.get('folder_name', 'N/A')}]"
                                    )

                    # 1/2 이상 매칭되면 조기 종료
                    if len(matched_items) >= threshold:
                        logging.info(
                            f"[{site_code}] {page}페이지에서 {len(matched_items)}/{len(downloaded)}개 매칭 (임계값: {threshold}) - 조기 종료"
                        )
                        return all_collected, matched_items

            except Exception as e:
                logging.error(f"[{site_code}] {page}페이지 수집 오류: {e}")
                break

        # 매칭이 임계값 미만
        if matched_items:
            logging.warning(
                f"[{site_code}] {len(matched_items)}/{len(downloaded)}개 매칭 (임계값 {threshold} 미달)"
            )
        return all_collected, None

    def run_list_collector(self, site_code: str, pages: int = 20) -> List[Dict]:
        """homepage_gosi_list_collector.js 실행하여 리스트 수집 (기존 방식)"""
        logging.info(f"[{site_code}] 리스트 수집 시작 (최대 {pages}페이지)")

        try:
            cmd = [
                "node",
                str(self.node_dir / "homepage_gosi_list_collector.js"),
                site_code,
                "--pages",
                str(pages),
                "--verbose",
                "--no-db",  # DB 저장 없이 리스트만 반환
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300, cwd=str(self.node_dir)
            )

            if result.returncode != 0:
                logging.error(f"[{site_code}] 리스트 수집 실패")
                return []

            # JSON 출력 파싱
            output = result.stdout
            if "JSON_OUTPUT_START" in output and "JSON_OUTPUT_END" in output:
                json_str = (
                    output.split("JSON_OUTPUT_START")[1]
                    .split("JSON_OUTPUT_END")[0]
                    .strip()
                )
                data = json.loads(json_str)

                # 항목들 반환 (no-db 모드에서는 allItems 사용)
                items = data.get("allItems", data.get("newItems", []))
                logging.info(f"[{site_code}] {len(items)}개 항목 수집")
                return items

        except Exception as e:
            logging.error(f"[{site_code}] 리스트 수집 오류: {e}")

        return []

    def normalize_title(self, title: str) -> str:
        """제목 정규화 (비교용)"""
        if not title:
            return ""
        # 특수문자, 공백 제거하여 비교
        return re.sub(r"[^가-힣a-zA-Z0-9]", "", title)

    def is_matching(self, downloaded_item: Dict, web_item: Dict) -> bool:
        """다운로드된 공고와 웹 리스트 항목이 매칭되는지 확인"""
        # 제목 비교
        dl_title = self.normalize_title(downloaded_item.get("title", ""))
        web_title = self.normalize_title(web_item.get("title", ""))

        # logging.info(f"title == {dl_title}, {web_title}")

        if not dl_title or not web_title:
            # logging.info("TITLE 내역이 없음")
            return False

        if dl_title != web_title:
            # logging.info("TITLE 이 같지 않음.")
            return False

        # return True

        # 확인 결과 같은 제목의 공고가 날짜가 다른게 있어서 날짜는 체크를 뺀다.
        # 제목이 일치하면 날짜도 확인 (있는 경우)
        dl_date = downloaded_item.get("date")
        web_date = web_item.get("date")

        if dl_date and web_date:
            # 날짜 정규화 (., /, - 모두 -로 통일)
            dl_date_norm = dl_date.replace(".", "-").replace("/", "-")
            web_date_norm = web_date.replace(".", "-").replace("/", "-")
            return dl_date_norm == web_date_norm
        else:
            # 날짜가 없으면 제목만으로 매칭
            return True

    def find_matching_point(
        self, downloaded: List[Dict], collected: List[Dict]
    ) -> Optional[int]:
        """다운로드된 공고와 수집된 리스트에서 매칭 지점 찾기 (기존 방식)"""
        if not downloaded or not collected:
            return None

        # 가장 최신 다운로드된 공고 정보
        latest = downloaded[0]

        # 수집된 리스트에서 매칭 찾기
        for idx, item in enumerate(collected):
            if self.is_matching(latest, item):
                return idx

        return None

    def detect_changing_params(self, urls: List[str]) -> Optional[List[str]]:
        """여러 URL을 비교하여 변경되는 파라미터 찾기"""
        if len(urls) < 2:
            return None

        from urllib.parse import urlparse, parse_qs

        # 각 URL의 파라미터 추출
        all_params = []
        for url in urls:
            try:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                # 각 파라미터의 첫 번째 값만 사용
                param_dict = {k: v[0] if v else "" for k, v in params.items()}
                all_params.append(param_dict)
            except:
                continue

        if len(all_params) < 2:
            return None

        # 모든 URL에 공통으로 존재하는 파라미터 찾기
        common_params = set(all_params[0].keys())
        for params in all_params[1:]:
            common_params &= set(params.keys())

        # 공통 파라미터 중에서 값이 변경되는 파라미터 찾기
        changing_params = []
        for param in common_params:
            values = [params[param] for params in all_params]
            # 값이 모두 다르면 변경되는 파라미터
            if len(set(values)) == len(values):
                changing_params.append(param)

        return changing_params if changing_params else None

    def update_config_announcement_pattern(
        self, site_code: str, url_params: List[str]
    ) -> bool:
        """config 파일의 announcementIdPattern.urlParams 업데이트"""
        config_file = self.configs_dir / f"{site_code}.json"

        if not config_file.exists():
            return False

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            # announcementIdPattern 업데이트
            if "announcementIdPattern" not in config:
                config["announcementIdPattern"] = {}

            config["announcementIdPattern"]["urlParams"] = url_params
            config["announcementIdPattern"][
                "description"
            ] = "URL에서 공고 ID를 추출하는 파라미터 목록 (자동 감지)"

            # 파일에 저장
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)

            logging.info(
                f"[{site_code}] config 파일 업데이트 완료: urlParams={url_params}"
            )
            return True

        except Exception as e:
            logging.warning(f"[{site_code}] config 파일 업데이트 오류: {e}")
            return False

    def extract_announcement_id(self, url: str, site_code: str = None) -> Optional[str]:
        """URL에서 announcement_id 추출 (2단계 방식)

        1단계: config 파일의 announcementIdPattern.urlParams에서 추출
        2단계: config에 없으면 DB에서 기존 URL 조회하여 변경되는 파라미터 분석 후 config 업데이트
        """
        if not url:
            return None

        # 1단계: config 파일에서 announcementIdPattern.urlParams 읽기
        url_params = None
        if site_code:
            config_file = self.configs_dir / f"{site_code}.json"
            if config_file.exists():
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)

                    # announcementIdPattern.urlParams 추출
                    url_params = config.get("announcementIdPattern", {}).get(
                        "urlParams", []
                    )

                    if url_params:
                        # urlParams에 명시된 파라미터들을 순서대로 시도
                        for param_name in url_params:
                            # 파라미터=값 패턴으로 추출 (값은 숫자만이 아닐 수 있음)
                            pattern = rf"{re.escape(param_name)}=([^&\s]+)"
                            match = re.search(pattern, url)
                            if match:
                                return match.group(1)
                except Exception as e:
                    logging.warning(f"[{site_code}] config 파일 읽기 오류: {e}")

        # 2단계: config에 없거나 추출 실패하면 DB에서 기존 URL 조회하여 분석
        if site_code and (not url_params or not url_params):
            try:
                conn = mysql.connector.connect(**self.db_config)
                cursor = conn.cursor()

                # 해당 site_code의 기존 URL 2개 이상 조회
                cursor.execute(
                    """SELECT announcement_url FROM homepage_gosi_url_registry 
                       WHERE site_code = %s AND announcement_url IS NOT NULL 
                       LIMIT 5""",
                    (site_code,),
                )

                existing_urls = [row[0] for row in cursor.fetchall()]
                cursor.close()
                conn.close()

                # 현재 URL도 포함하여 분석
                if existing_urls:
                    existing_urls.append(url)

                    # 변경되는 파라미터 감지
                    changing_params = self.detect_changing_params(existing_urls)

                    if changing_params:
                        logging.info(
                            f"[{site_code}] 변경되는 파라미터 감지: {changing_params}"
                        )

                        # config 파일 업데이트
                        self.update_config_announcement_pattern(
                            site_code, changing_params
                        )

                        # 현재 URL에서 첫 번째 변경 파라미터로 ID 추출
                        for param_name in changing_params:
                            pattern = rf"{re.escape(param_name)}=([^&\s]+)"
                            match = re.search(pattern, url)
                            if match:
                                return match.group(1)

            except Exception as e:
                logging.warning(f"[{site_code}] DB 조회 오류: {e}")

        # 3단계: 여전히 실패하면 기존 패턴 폴백
        id_patterns = [
            r"notAncmtMgtNo=([^&\s]+)",
            r"articleSeq=([^&\s]+)",
            r"boardSeq=([^&\s]+)",
            r"seq=([^&\s]+)",
            r"idx=([^&\s]+)",
            r"no=([^&\s]+)",
            r"dataSid=([^&\s]+)",
            r"nttId=([^&\s]+)",
        ]

        for pattern in id_patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def save_to_db(self, site_code: str, items: List[Dict], status: str = "completed"):
        """DB에 항목 저장"""
        if not items:
            return

        # config에서 siteName 가져오기
        site_name = self.get_site_name(site_code)

        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()

            saved_count = 0
            for item in items:
                try:
                    # announcement_id가 없으면 URL에서 추출 시도
                    announcement_id = item.get("announcement_id")
                    if not announcement_id:
                        announcement_id = self.extract_announcement_id(
                            item.get("url", ""), site_code
                        )

                    # 중복 체크
                    cursor.execute(
                        "SELECT id FROM homepage_gosi_url_registry WHERE site_code = %s AND announcement_url = %s",
                        (site_code, item["url"]),
                    )

                    if cursor.fetchone():
                        # 이미 존재하면 status, announcement_id, folder_name 업데이트
                        cursor.execute(
                            "UPDATE homepage_gosi_url_registry SET status = %s, site_name = %s, announcement_id = %s, folder_name = %s WHERE site_code = %s AND announcement_url = %s",
                            (
                                status,
                                site_name,
                                announcement_id,
                                item.get("folder_name"),
                                site_code,
                                item["url"],
                            ),
                        )
                    else:
                        # 새로 추가
                        cursor.execute(
                            """INSERT INTO homepage_gosi_url_registry 
                            (site_code, site_name, announcement_url, announcement_id, title, post_date, status, folder_name, first_seen_date)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                            (
                                site_code,
                                site_name,  # config에서 가져온 siteName 사용
                                item["url"],
                                announcement_id,
                                item["title"][:500] if item.get("title") else None,
                                item.get("date"),
                                status,
                                item.get("folder_name"),
                            ),
                        )
                    saved_count += 1

                except Exception as e:
                    logging.warning(f"항목 저장 오류: {e}")

            conn.commit()
            cursor.close()
            conn.close()

            logging.info(f"[{site_code}] DB에 {saved_count}개 항목 저장/업데이트")

        except Exception as e:
            logging.error(f"[{site_code}] DB 저장 오류: {e}")

    def process_site(self, site_code: str, use_early_stop: bool = True) -> Dict:
        """단일 사이트 처리"""
        logging.info(f"\n{'='*60}")
        logging.info(f"[{site_code}] 처리 시작")

        result = {
            "site_code": site_code,
            "downloaded_count": 0,
            "collected_count": 0,
            "matched_count": 0,
            "saved_count": 0,
            "pages_collected": 0,
        }

        try:
            # 1. 다운로드된 최신 10개 공고 읽기 (scraped_data/{site_code})
            downloaded = self.get_recent_announcements(site_code, count=10)
            result["downloaded_count"] = len(downloaded)

            if not downloaded:
                logging.warning(f"[{site_code}] 다운로드된 공고가 없습니다")
                # 다운로드된 공고가 없으면 전체를 pending으로 수집
                collected = self.run_list_collector(site_code, pages=20)
                result["collected_count"] = len(collected)
                if collected:
                    self.save_to_db(site_code, collected[:20], status="pending")
                    result["saved_count"] = min(len(collected), 20)
                return result

            logging.info(
                f"[{site_code}] 다운로드된 최신 {len(downloaded)}개 공고 읽기 완료"
            )
            for i, item in enumerate(downloaded[:3]):
                logging.info(
                    f"  {i+1}. {item['title'][:50]}... ({item.get('date', 'N/A')})"
                )

            # 2. 리스트 수집 (페이지별로 수집하며 매칭 찾으면 조기 종료)
            if use_early_stop:
                collected, matched_items = self.run_list_collector_with_early_stop(
                    site_code, downloaded, max_pages=20
                )
                result["collected_count"] = len(collected)

                # 3. 결과 처리
                if matched_items is None:
                    logging.warning(
                        f"[{site_code}] 매칭 지점을 찾을 수 없습니다 (20페이지 검색 완료)"
                    )
                    # 매칭이 안되어도 다운로드된 항목들은 completed로 저장
                    self.save_to_db(site_code, downloaded, status="completed")
                    result["saved_count"] = len(downloaded)
                    logging.info(
                        f"[{site_code}] 다운로드된 {len(downloaded)}개 항목을 completed로 저장"
                    )
                else:
                    # 매칭 성공 - 매칭된 항목들을 DB에 INSERT
                    logging.info(f"[{site_code}] {len(matched_items)}개 매칭 항목 발견")
                    result["matched_count"] = len(matched_items)

                    # 매칭된 항목들을 completed로 저장
                    self.save_to_db(site_code, matched_items, status="completed")
                    result["saved_count"] = len(matched_items)
                    logging.info(
                        f"[{site_code}] 매칭된 {len(matched_items)}개 항목을 completed로 저장 완료"
                    )

            else:
                # 기존 방식: 한번에 20페이지 수집
                collected = self.run_list_collector(site_code, pages=20)
                result["collected_count"] = len(collected)

                if not collected:
                    logging.warning(f"[{site_code}] 수집된 리스트가 없습니다")
                    return result

                # 매칭 지점 찾기 (기존 로직)
                match_idx = self.find_matching_point(downloaded, collected)

                if match_idx is None:
                    logging.warning(f"[{site_code}] 매칭 지점을 찾을 수 없습니다")
                    self.save_to_db(site_code, downloaded, status="completed")
                    result["saved_count"] = len(downloaded)
                else:
                    logging.info(f"[{site_code}] 매칭 지점: {match_idx}번째 항목")
                    result["matched_count"] = match_idx
                    self.save_to_db(site_code, downloaded, status="completed")
                    result["saved_count"] = len(downloaded)

        except Exception as e:
            logging.error(f"[{site_code}] 처리 오류: {e}")
            import traceback

            logging.error(traceback.format_exc())

        return result

    def save_stats(self, stats: Dict):
        """통계를 파일로 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stats_file = Path(f"incremental_init_stats_{timestamp}.txt")

        with open(stats_file, "w", encoding="utf-8") as f:
            f.write(f"증분 초기화 통계\n")
            f.write(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n\n")

            total_matched = 0
            total_saved = 0
            for site_code, result in stats.items():
                matched = result.get("matched_count", 0)
                saved = result.get("saved_count", 0)

                if matched > 0:
                    f.write(f"{site_code}: {matched}개 매칭, {saved}개 저장\n")
                    total_matched += matched
                else:
                    f.write(f"{site_code}: 매칭 실패 (저장: {saved}개)\n")

                total_saved += saved

            f.write(f"\n{'='*60}\n")
            f.write(f"총 사이트: {len(stats)}개\n")
            f.write(f"총 매칭: {total_matched}개\n")
            f.write(f"총 저장: {total_saved}개\n")

        logging.info(f"통계 파일 생성: {stats_file}")
        return stats_file

    def run(self):
        """전체 프로세스 실행"""
        logging.info("=" * 60)
        logging.info("증분 DB 초기화 시작")
        logging.info("=" * 60)

        # 사이트 코드 추출
        site_codes = self.get_site_codes()
        logging.info(f"발견된 사이트: {len(site_codes)}개")

        if not site_codes:
            logging.error("처리할 사이트가 없습니다")
            return

        # 각 사이트 처리 (조기 종료 활성화)
        all_stats = {}
        for site_code in site_codes:
            result = self.process_site(site_code, use_early_stop=True)
            all_stats[site_code] = result

        # 통계 저장
        self.save_stats(all_stats)

        # 요약 출력
        logging.info("\n" + "=" * 60)
        logging.info("처리 완료 요약")
        logging.info("=" * 60)

        total_matched = sum(r.get("matched_count", 0) for r in all_stats.values())
        total_saved = sum(r.get("saved_count", 0) for r in all_stats.values())

        logging.info(f"처리 사이트: {len(all_stats)}개")
        logging.info(f"총 매칭 항목: {total_matched}개")
        logging.info(f"DB 저장 항목: {total_saved}개")


def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description="증분 DB 초기화")
    parser.add_argument("--data-dir", default="scraped_data", help="데이터 디렉토리")
    parser.add_argument("--sites", nargs="+", help="특정 사이트만 처리")
    parser.add_argument(
        "--no-early-stop",
        action="store_true",
        help="조기 종료 비활성화 (전체 페이지 수집)",
    )

    args = parser.parse_args()

    initializer = IncrementalDBInitializer(data_dir=args.data_dir)

    if args.sites:
        # 특정 사이트만 처리
        for site_code in args.sites:
            result = initializer.process_site(
                site_code, use_early_stop=not args.no_early_stop
            )
            print(
                f"{site_code}: 매칭 {result.get('matched_count', 0)}개, 수집 {result['collected_count']}개, 저장 {result['saved_count']}개"
            )
    else:
        # 전체 처리
        initializer.run()


if __name__ == "__main__":
    main()
