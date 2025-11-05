#!/usr/bin/env python3
"""
공고 사전 처리 프로그램

사용법:
    python announcement_pre_processor.py -d [디렉토리명] --site-code [사이트코드]

예시:
    python announcement_pre_processor.py -d scraped_data --site-code site001
    python announcement_pre_processor.py -d eminwon_data --site-code emw001
"""

import sys
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.config import ConfigManager

from src.config.logConfig import setup_logging

from src.models.announcementPrvDatabase import AnnouncementPrvDatabaseManager
from src.utils.domainKeyExtractor import DomainKeyExtractor

logger = setup_logging(__name__)

config = ConfigManager().get_config()


class AnnouncementPreProcessor:
    """공고 사전 처리 메인 클래스"""

    def __init__(
        self,
        site_type: str,
        attach_force: bool = False,
        site_code: str = None,
        lazy_init: bool = False,
    ):
        # lazy_init 옵션이 True면 AttachmentProcessor를 나중에 초기화
        self._lazy_init = lazy_init
        self._attachment_processor = None

        if not lazy_init:
            # AttachmentProcessor를 지연 import
            from src.utils.attachmentProcessor import AttachmentProcessor

            self._attachment_processor = AttachmentProcessor()

        self.db_manager = AnnouncementPrvDatabaseManager()
        self.attach_force = attach_force
        self.site_type = site_type
        self.site_code = site_code  # site_code를 인스턴스 변수로 저장

        # URL 정규화를 위한 DomainKeyExtractor 초기화
        # SQLAlchemy engine에서 DB 연결 정보 추출
        db_url = self.db_manager.engine.url
        db_config = {
            'host': db_url.host,
            'user': db_url.username,
            'password': db_url.password,
            'database': db_url.database,
            'port': db_url.port or 3306,
            'charset': 'utf8mb4'
        }
        self.url_key_extractor = DomainKeyExtractor(db_config=db_config)

        # 데이터베이스 테이블 생성 (없는 경우)
        self._ensure_database_tables()

        # 제외 키워드 로드
        self.exclusion_keywords = self._load_exclusion_keywords()

    @property
    def attachment_processor(self):
        """지연 초기화를 위한 property"""
        if self._lazy_init and self._attachment_processor is None:
            logger.info("지연 초기화: AttachmentProcessor 생성")
            try:
                # 지연 import
                from src.utils.attachmentProcessor import AttachmentProcessor

                self._attachment_processor = AttachmentProcessor()
            except Exception as e:
                logger.error(f"AttachmentProcessor 초기화 실패: {e}")
                # 실패 시 None 반환하여 호출자가 처리하도록 함
                return None
        return self._attachment_processor

    def _ensure_database_tables(self):
        """데이터베이스 테이블이 존재하는지 확인하고 생성합니다."""
        try:
            if self.db_manager.test_connection():
                # announcement_pre_processing 테이블 생성
                from sqlalchemy import text

                with self.db_manager.SessionLocal() as session:
                    session.execute(
                        text(
                            """
                        CREATE TABLE IF NOT EXISTS announcement_pre_processing (
                            id INT PRIMARY KEY AUTO_INCREMENT,
                            folder_name VARCHAR(255) UNIQUE,
                            site_type VARCHAR(50),
                            site_code VARCHAR(50),
                            content_md LONGTEXT,
                            combined_content LONGTEXT,
                            attachment_filenames TEXT,
                            attachment_files_list JSON,
                            exclusion_keyword TEXT,
                            exclusion_reason TEXT,
                            title VARCHAR(500),
                            origin_url VARCHAR(1000),
                            scraping_url VARCHAR(1000),
                            announcement_date VARCHAR(50),
                            processing_status VARCHAR(50),
                            error_message TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_site_code (site_code),
                            INDEX idx_processing_status (processing_status),
                            INDEX idx_origin_url (origin_url),
                            INDEX idx_scraping_url (scraping_url)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                        )
                    )
                    session.commit()
                logger.info("데이터베이스 테이블 확인/생성 완료")
            else:
                logger.warning(
                    "데이터베이스 연결 실패 - 계속 진행합니다 (DB 저장 불가)"
                )
        except Exception as e:
            logger.warning(
                f"데이터베이스 초기화 실패: {e} - 계속 진행합니다 (DB 저장 불가)"
            )

    def _load_exclusion_keywords(self) -> List[Dict[str, Any]]:
        """데이터베이스에서 제외 키워드를 로드합니다."""
        try:
            from sqlalchemy import text

            with self.db_manager.SessionLocal() as session:
                result = session.execute(
                    text(
                        """
                    SELECT EXCLUSION_ID, KEYWORD, DESCRIPTION
                    FROM EXCLUSION_KEYWORDS
                    WHERE IS_ACTIVE = TRUE
                    ORDER BY EXCLUSION_ID
                """
                    )
                )

                keywords = []
                for row in result:
                    keywords.append(
                        {"id": row[0], "keyword": row[1], "description": row[2]}
                    )

                logger.info(f"제외 키워드 로드 완료: {len(keywords)}개")
                return keywords

        except Exception as e:
            logger.warning(f"제외 키워드 로드 실패: {e}")
            return []

    def process_directory(self, directory_path: Path, site_code: str) -> bool:
        """
        단일 디렉토리를 처리합니다.

        Args:
            directory_path: 처리할 디렉토리 경로
            site_code: 사이트 코드

        Returns:
            처리 성공 여부
        """
        folder_name = directory_path.name
        return self.process_directory_with_custom_name(
            directory_path, site_code, folder_name
        )

    def _find_target_directories(
        self, base_dir: Path, site_code: str, force: bool = False
    ) -> List[Path]:
        """
        처리할 대상 디렉토리들을 찾습니다.

        Args:
            base_dir: 기본 디렉토리
            site_code: 사이트 코드
            force: 이미 처리된 항목도 다시 처리할지 여부

        Returns:
            처리 대상 디렉토리 목록
        """
        site_dir = base_dir / site_code

        if not site_dir.exists():
            logger.error(f"사이트 디렉토리가 없음: {site_dir}")
            return []

        target_directories = []

        # 모든 하위 디렉토리에서 content.md, JSON 파일 또는 attachments 폴더가 있는 디렉토리 찾기
        logger.info(f"디렉토리 검색 시작: {site_dir}")

        # bizInfo, smes24, kStartUp은 플랫 구조 (직접 하위 디렉토리만 검색)
        if site_code in ["bizInfo", "smes24", "kStartUp"]:
            # 직접 하위 디렉토리만 검색 (더 빠름)
            # 모든 API 사이트는 content.md가 반드시 있어야 함
            for root_path in site_dir.iterdir():
                if root_path.is_dir():
                    has_content_md = (root_path / "content.md").exists()

                    if has_content_md:
                        # content.md가 있는 디렉토리만 처리
                        target_directories.append(root_path)
                        logger.debug(
                            f"대상 디렉토리 발견: {root_path.relative_to(site_dir)}"
                        )
                    else:
                        # content.md가 없는 디렉토리는 건너뛰기
                        logger.debug(
                            f"{site_code} 디렉토리 건너뛰기 (content.md 없음): {root_path.relative_to(site_dir)}"
                        )
        else:
            # 다른 사이트는 재귀적으로 검색 (중첩 구조 가능)
            for root_path in site_dir.rglob("*"):
                if root_path.is_dir():
                    # content.md 파일이 있거나 attachments 폴더가 있거나 JSON 파일이 있는 디렉토리만 대상으로 함
                    has_content_md = (root_path / "content.md").exists()
                    has_json = bool(list(root_path.glob("*.json")))
                    # attachments 폴더 확인 최적화
                    attachments_dir = root_path / "attachments"
                    has_attachments = False
                    if attachments_dir.exists():
                        # 첫 번째 파일만 확인 (전체 디렉토리 순회 방지)
                        try:
                            next(attachments_dir.iterdir())
                            has_attachments = True
                        except StopIteration:
                            has_attachments = False

                    if has_content_md or has_attachments or has_json:
                        target_directories.append(root_path)
                        logger.debug(
                            f"대상 디렉토리 발견: {root_path.relative_to(site_dir)}"
                        )

        # 폴더명으로 정렬
        target_directories = sorted(target_directories, key=self._natural_sort_key)

        logger.info(f"발견된 전체 디렉토리: {len(target_directories)}개")

        # 처음 몇 개 폴더명 로깅
        if target_directories:
            logger.info(f"첫 5개 폴더: {[d.name for d in target_directories[:5]]}")

        # force 옵션이 없을 때만 이미 처리된 폴더 제외
        if not force:
            processed_folders = set(self._get_processed_folders(site_code))

            filtered_directories = []
            for directory in target_directories:
                # 사이트 디렉토리로부터의 상대 경로를 폴더명으로 사용
                relative_path = directory.relative_to(site_dir)
                folder_name = self._normalize_korean_text(
                    str(relative_path).replace("/", "_")
                )

                if folder_name not in processed_folders:
                    filtered_directories.append(directory)
                else:
                    logger.debug(f"이미 처리된 폴더 건너뜀: {folder_name}")

            logger.info(f"전체 발견된 디렉토리: {len(target_directories)}개")
            logger.info(f"처리 대상 디렉토리: {len(filtered_directories)}개")
            logger.info(f"이미 처리된 폴더: {len(processed_folders)}개")

            return filtered_directories
        else:
            # force 옵션이 있으면 모든 디렉토리 반환
            logger.info(
                f"--force 옵션: 모든 디렉토리 처리 ({len(target_directories)}개)"
            )
            return target_directories

    def _get_processed_folders(self, site_code: str) -> List[str]:
        """이미 처리된 폴더 목록을 가져옵니다."""
        try:
            from sqlalchemy import text

            with self.db_manager.SessionLocal() as session:
                result = session.execute(
                    text(
                        """
                    SELECT folder_name 
                    FROM announcement_pre_processing 
                    WHERE site_code = :site_code
                """
                    ),
                    {"site_code": site_code},
                )

                return [row[0] for row in result]

        except Exception as e:
            logger.error(f"처리된 폴더 목록 조회 실패: {e}")
            return []

    def process_site_directories(
        self, base_dir: Path, site_code: str, force: bool = False
    ) -> Dict[str, int]:
        """
        특정 사이트의 모든 디렉토리를 처리합니다.

        Args:
            base_dir: 기본 디렉토리
            site_code: 사이트 코드
            force: 이미 처리된 항목도 다시 처리할지 여부

        Returns:
            처리 결과 통계
        """

        # 처리할 디렉토리 목록 찾기
        target_directories = self._find_target_directories(base_dir, site_code, force)

        if not target_directories:
            logger.warning("처리할 디렉토리가 없습니다.")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

        total_count = len(target_directories)
        results = {"total": total_count, "success": 0, "failed": 0, "skipped": 0}
        site_dir = base_dir / site_code

        print(f"\n{'='*60}")
        print(
            f"공고 처리 시작: {site_code} (Site Type: {self.site_type}) ({total_count}개 폴더)"
        )
        print(f"{'='*60}")

        # 시작 시간 기록
        start_time = time.time()

        for i, directory in enumerate(target_directories, 1):
            try:
                # 개별 항목 시작 시간
                item_start_time = time.time()

                # 사이트 디렉토리로부터의 상대 경로를 폴더명으로 사용
                relative_path = directory.relative_to(site_dir)
                folder_name = self._normalize_korean_text(
                    str(relative_path).replace("/", "_")
                )

                progress_pct = (i / total_count) * 100
                print(f"\n[{i}/{total_count} : {progress_pct:.1f}%] {folder_name}")

                # 이미 처리된 항목 확인 (force 옵션이 없을 때만)
                if not force and self._is_already_processed(folder_name, site_code):
                    skip_elapsed = time.time() - item_start_time
                    print(f"  ✓ 이미 처리됨, 건너뜀 ({skip_elapsed:.1f}초)")
                    results["skipped"] += 1
                    continue
                elif force and self._is_already_processed(folder_name, site_code):
                    print("  🔄 이미 처리됨, --force 옵션으로 재처리")

                success = self.process_directory_with_custom_name(
                    directory, site_code, folder_name, force
                )

                # 개별 항목 처리 시간 계산
                item_elapsed = time.time() - item_start_time

                if success:
                    results["success"] += 1
                    print(f"  ✓ 처리 완료 ({item_elapsed:.1f}초)")
                else:
                    results["failed"] += 1
                    print(f"  ✗ 처리 실패 ({item_elapsed:.1f}초)")

            except Exception as e:
                error_elapsed = time.time() - item_start_time
                results["failed"] += 1
                print(f"  ✗ 예외 발생: {str(e)[:100]}... ({error_elapsed:.1f}초)")
                logger.error(f"처리 중 오류 ({directory}): {e}")

        # 종료 시간 및 통계 계산
        end_time = time.time()
        total_elapsed = end_time - start_time
        processed_count = results["success"] + results["failed"]

        print(f"\n{'='*60}")
        print(
            f"처리 완료: {results['success']}/{total_count} 성공 ({(results['success']/total_count)*100:.1f}%)"
        )
        print(f"건너뜀: {results['skipped']}, 실패: {results['failed']}")
        print(f"")
        print(f"📊 처리 시간 통계:")
        print(f"   총 소요 시간: {total_elapsed:.1f}초 ({total_elapsed/60:.1f}분)")

        if processed_count > 0:
            avg_time_per_item = total_elapsed / processed_count
            print(f"   처리한 항목당 평균 시간: {avg_time_per_item:.1f}초")

        if results["success"] > 0:
            avg_time_per_success = total_elapsed / results["success"]
            print(f"   성공한 항목당 평균 시간: {avg_time_per_success:.1f}초")

        print(f"{'='*60}")

        logger.info(
            f"처리 완료 - 전체: {results['total']}, 성공: {results['success']}, 실패: {results['failed']}, 건너뜀: {results['skipped']}"
        )

        return results

    def process_directory_with_custom_name(
        self,
        directory_path: Path,
        site_code: str,
        folder_name: str,
        force: bool = False,
    ) -> bool:
        """
        사용자 정의 폴더명으로 디렉토리를 처리합니다.

        Args:
            directory_path: 처리할 디렉토리 경로
            site_code: 사이트 코드
            folder_name: 데이터베이스에 저장할 폴더명
            force: 이미 처리된 항목도 다시 처리할지 여부

        Returns:
            처리 성공 여부
        """
        logger.info(f"디렉토리 처리 시작: {folder_name} (site_code: {site_code})")

        try:
            # 0. folder_name 중복 체크 (force 옵션이 없을 때만)
            if not force:
                if self._check_folder_name_exists(folder_name, site_code):
                    logger.info(f"이미 처리된 폴더 건너뜀: {folder_name}")
                    return True  # 성공으로 처리 (이미 처리됨)

            # 1. 제외 키워드 체크
            excluded_keywords = []
            excluded_keywords = self._check_exclusion_keywords(folder_name)

            # 2. 특수 사이트 처리 (모두 content.md 읽기)
            content_md = ""
            title = None
            origin_url = None
            scraping_url = None
            announcement_date = None

            if site_code in ["kStartUp", "bizInfo", "smes24"]:
                # kStartUp, bizInfo, smes24는 content.md를 읽고, JSON에서 날짜 정보만 보완
                content_md_path = directory_path / "content.md"
                if content_md_path.exists():
                    try:
                        with open(content_md_path, "r", encoding="utf-8") as f:
                            content_md = f.read()
                        logger.info(f"content.md 읽기 완료: {len(content_md)} 문자")

                        # DO_NOT_PROCESS 플래그 확인 (구 데이터 건너뛰기)
                        if "DO_NOT_PROCESS" in content_md:
                            logger.info(f"⏭️  건너뜀 (ARCHIVED): {folder_name} - DO_NOT_PROCESS 플래그 감지")
                            return False

                        # content.md에서 기본 정보 추출
                        title = self._extract_title_from_content(content_md)
                        origin_url = self._extract_origin_url_from_content(content_md)
                        scraping_url = self._extract_scraping_url_from_content(content_md)

                        # JSON 파일에서 announcement_date 보완 (우선순위: announcement.json → data.json → 기타)
                        priority_json_names = ["announcement.json", "data.json", "info.json"]
                        json_file_to_use = None

                        # 우선순위 파일 먼저 확인
                        for json_name in priority_json_names:
                            json_path = directory_path / json_name
                            if json_path.exists():
                                json_file_to_use = json_path
                                logger.debug(f"우선순위 JSON 파일 발견: {json_name}")
                                break

                        # 우선순위 파일이 없으면 첫 번째 JSON 사용
                        if not json_file_to_use:
                            json_files = list(directory_path.glob("*.json"))
                            if json_files:
                                json_file_to_use = json_files[0]
                                logger.debug(f"일반 JSON 파일 사용: {json_file_to_use.name}")

                        if json_file_to_use:
                            try:
                                with open(json_file_to_use, "r", encoding="utf-8") as f:
                                    json_data = json.load(f)
                                announcement_date_raw = json_data.get(
                                    "announcementDate", ""
                                )
                                if announcement_date_raw:
                                    announcement_date = self._convert_to_yyyymmdd(
                                        announcement_date_raw
                                    )
                                else:
                                    # JSON에 없으면 content.md에서 추출
                                    announcement_date_raw = self._extract_announcement_date_from_content(
                                        content_md
                                    )
                                    if announcement_date_raw:
                                        announcement_date = self._convert_to_yyyymmdd(announcement_date_raw)
                            except Exception as e:
                                logger.warning(
                                    f"{site_code} JSON 날짜 추출 실패, content.md 사용: {e}"
                                )
                                announcement_date_raw = self._extract_announcement_date_from_content(
                                    content_md
                                )
                                if announcement_date_raw:
                                    announcement_date = self._convert_to_yyyymmdd(announcement_date_raw)
                        else:
                            # JSON 파일이 없으면 content.md에서 추출
                            announcement_date_raw = self._extract_announcement_date_from_content(content_md)
                            if announcement_date_raw:
                                announcement_date = self._convert_to_yyyymmdd(announcement_date_raw)

                    except Exception as e:
                        logger.error(f"content.md 읽기 실패: {e}")
                        return self._save_processing_result(
                            folder_name,
                            site_code,
                            content_md,
                            "",
                            url_key=None,
                            status="error",
                            error_message=f"content.md 읽기 실패: {e}",
                        )
                else:
                    logger.warning(f"content.md 파일이 없음: {content_md_path}")

            else:
                # 일반 사이트 처리 (기존 로직)
                content_md_path = directory_path / "content.md"
                if content_md_path.exists():
                    try:
                        with open(content_md_path, "r", encoding="utf-8") as f:
                            content_md = f.read()
                        logger.info(f"content.md 읽기 완료: {len(content_md)} 문자")

                        # DO_NOT_PROCESS 플래그 확인 (구 데이터 건너뛰기)
                        if "DO_NOT_PROCESS" in content_md:
                            logger.info(f"⏭️  건너뜀 (ARCHIVED): {folder_name} - DO_NOT_PROCESS 플래그 감지")
                            return False
                    except Exception as e:
                        logger.error(f"content.md 읽기 실패: {e}")
                        return self._save_processing_result(
                            folder_name,
                            site_code,
                            content_md,
                            "",
                            url_key=None,
                            status="error",
                            error_message=f"content.md 읽기 실패: {e}",
                        )
                else:
                    logger.warning(f"content.md 파일이 없음: {content_md_path}")

            # 3. content.md에서 정보 추출
            # 일반 사이트의 경우만 content.md에서 정보 추출 (API 사이트는 이미 추출함)
            if site_code not in ["kStartUp", "bizInfo", "smes24"]:
                title = self._extract_title_from_content(content_md)
                origin_url = self._extract_origin_url_from_content(content_md)
                announcement_date_raw = self._extract_announcement_date_from_content(content_md)
                if announcement_date_raw:
                    announcement_date = self._convert_to_yyyymmdd(announcement_date_raw)

            # 3.5. origin_url에서 url_key 추출 (URL 정규화)
            # 우선순위 1: domain_key_config 사용
            # 우선순위 2: 폴백 정규화 (쿼리 파라미터 정렬)
            url_key = None
            if origin_url:
                try:
                    # 1순위: domain_key_config에서 도메인 설정 조회
                    url_key = self.url_key_extractor.extract_url_key(origin_url, site_code)
                    if url_key:
                        logger.debug(f"✓ URL 정규화 완료 (domain_key_config 사용): {origin_url[:80]}... → {url_key}")
                    else:
                        # 2순위: domain_key_config에 도메인 없음 → 폴백 정규화
                        logger.warning(
                            f"⚠️  도메인 설정 없음 (domain_key_config), 폴백 정규화 수행: {origin_url[:80]}..."
                        )
                        url_key = self._fallback_normalize_url(origin_url)
                        logger.info(f"✓ 폴백 정규화 적용: {url_key}")
                except Exception as e:
                    logger.error(f"❌ URL 정규화 중 오류: {e}")
                    # 예외 발생 시에도 폴백 정규화 시도
                    if origin_url:
                        url_key = self._fallback_normalize_url(origin_url)
                        logger.info(f"✓ 예외 후 폴백 정규화: {url_key}")
                    else:
                        logger.warning("origin_url이 없어 URL 정규화 불가")
                        url_key = None

            # 4. 첨부파일 처리 (content.md와 분리)
            combined_content = ""
            attachment_filenames = []
            attachment_files_info = []
            attachment_error = None

            try:
                combined_content, attachment_filenames, attachment_files_info = (
                    self._process_attachments_separately(directory_path)
                )
                logger.info(
                    f"첨부파일 내용 처리 완료: {len(combined_content)} 문자, 파일 {len(attachment_filenames)}개"
                )
            except Exception as e:
                # 첨부파일 처리 실패를 기록하지만 계속 진행
                attachment_error = str(e)
                logger.error(f"첨부파일 처리 중 예외 발생 (계속 진행): {e}")
                # 빈 값으로 설정하고 계속 진행
                combined_content = ""
                attachment_filenames = []
                attachment_files_info = []

            # content.md와 combined_content 모두 없는 경우에만 에러 처리
            if not content_md.strip() and not combined_content.strip():
                logger.warning("처리할 내용이 없음")
                error_msg = "처리할 내용이 없음"
                if attachment_error:
                    error_msg += f" (첨부파일 오류: {attachment_error})"
                return self._save_processing_result(
                    folder_name,
                    site_code,
                    content_md,
                    combined_content,
                    attachment_filenames=attachment_filenames,
                    attachment_files_info=attachment_files_info,
                    url_key=url_key,
                    status="error",
                    error_message=error_msg,
                )

            # 5. 제외 키워드가 있는 경우 제외 처리
            if excluded_keywords:
                exclusion_msg = (
                    f"제외 키워드가 입력되어 있습니다: {', '.join(excluded_keywords)}"
                )
                logger.info(f"제외 처리: {folder_name} - {exclusion_msg}")

                return self._save_processing_result(
                    folder_name,
                    site_code,
                    content_md,
                    combined_content,
                    attachment_filenames=attachment_filenames,
                    attachment_files_info=attachment_files_info,
                    status="제외",
                    title=title,
                    announcement_date=announcement_date,
                    origin_url=origin_url,
                    url_key=url_key,
                    scraping_url=scraping_url,
                    exclusion_keywords=excluded_keywords,
                    exclusion_reason=exclusion_msg,
                )

            # 6. 데이터베이스에 저장 (URL 정규화 적용)
            record_id = self._save_processing_result(
                folder_name,
                site_code,
                content_md,
                combined_content,
                attachment_filenames=attachment_filenames,
                attachment_files_info=attachment_files_info,
                title=title,
                announcement_date=announcement_date,
                origin_url=origin_url,
                url_key=url_key,
                scraping_url=scraping_url,
                status="성공",
                force=force,
            )

            if record_id:
                logger.info(f"디렉토리 처리 완료: {folder_name}")
                return True
            else:
                logger.error(f"디렉토리 처리 실패: {folder_name}")
                return False

        except Exception as e:
            logger.error(f"디렉토리 처리 중 예상치 못한 오류: {e}")
            result = self._save_processing_result(
                folder_name,
                site_code,
                "",
                "",
                url_key=None,
                status="error",
                error_message=f"예상치 못한 오류: {e}",
            )
            return result is not None

    def _check_exclusion_keywords(self, folder_name: str) -> List[str]:
        """폴더명에서 제외 키워드를 체크합니다."""
        matched_keywords = []

        for keyword_info in self.exclusion_keywords:
            keyword = keyword_info["keyword"].lower()
            if keyword in folder_name.lower():
                matched_keywords.append(keyword_info["keyword"])
                logger.debug(f"제외 키워드 매칭: '{keyword}' in '{folder_name}'")

        return matched_keywords

    def _check_folder_name_exists(self, folder_name: str, site_code: str) -> bool:
        """folder_name이 데이터베이스에 이미 존재하는지 확인합니다."""
        try:
            from sqlalchemy import text

            with self.db_manager.SessionLocal() as session:
                result = session.execute(
                    text(
                        """
                    SELECT COUNT(*) FROM announcement_pre_processing 
                    WHERE folder_name = :folder_name AND site_code = :site_code
                """
                    ),
                    {"folder_name": folder_name, "site_code": site_code},
                )

                count = result.scalar()
                exists = count > 0

                if exists:
                    logger.debug(f"folder_name 중복 발견: {folder_name}")

                return exists

        except Exception as e:
            logger.error(f"folder_name 중복 체크 실패: {e}")
            return False

    def _check_origin_url_exists(self, origin_url: str, site_code: str) -> bool:
        """origin_url이 데이터베이스에 이미 존재하는지 확인합니다."""
        try:
            from sqlalchemy import text

            with self.db_manager.SessionLocal() as session:
                result = session.execute(
                    text(
                        """
                    SELECT COUNT(*) FROM announcement_pre_processing 
                    WHERE origin_url = :origin_url AND site_code = :site_code
                """
                    ),
                    {"origin_url": origin_url, "site_code": site_code},
                )

                count = result.scalar()
                exists = count > 0

                if exists:
                    logger.debug(f"origin_url 중복 발견: {origin_url}")

                return exists

        except Exception as e:
            logger.error(f"origin_url 중복 체크 실패: {e}")
            return False

    def _is_already_processed(self, folder_name: str, site_code: str) -> bool:
        """폴더가 이미 처리되었는지 확인합니다."""
        return self._check_folder_name_exists(folder_name, site_code)

    def _extract_title_from_content(self, content_md: str) -> str:
        """content.md에서 제목을 추출합니다."""
        if not content_md:
            return ""

        lines = content_md.split("\n")

        # 첫 번째 비어있지 않은 줄을 찾기
        for line in lines[:10]:  # 상위 10줄만 확인
            line = line.strip()
            if line:
                # # 마크다운 헤더 제거
                if line.startswith("#"):
                    title = line.lstrip("#").strip()
                    logger.debug(f"마크다운 헤더에서 제목 추출: {title}")
                    return title

                # **제목**: 패턴 확인 (마크다운 볼드)
                if line.startswith("**제목**:"):
                    title = line.replace("**제목**:", "").strip()
                    logger.debug(f"**제목** 패턴에서 제목 추출: {title}")
                    return title

                # 제목:, 공고명: 패턴 확인
                for prefix in ["제목:", "공고명:", "공고 제목:", "제목 :"]:
                    if line.lower().startswith(prefix.lower()):
                        title = line[len(prefix) :].strip()
                        logger.debug(f"{prefix} 패턴에서 제목 추출: {title}")
                        return title

                # 일반 텍스트인 경우 그대로 제목으로 사용 (첫 번째 줄)
                logger.debug(f"첫 번째 줄을 제목으로 사용: {line}")
                return line

        return ""

    def _extract_origin_url_from_content(self, content_md: str) -> str:
        """content.md에서 원본 URL을 추출합니다."""
        if not content_md:
            return ""

        # 원본 URL 패턴 찾기
        origin_patterns = [
            r"\*\*원본 URL\*\*[:\s]*(.+?)(?:\n|$)",
            r"원본 URL[:\s]*(.+?)(?:\n|$)",
            r"원본[:\s]*(.+?)(?:\n|$)",
            r"(https?://[^\s\)]+(?:\.go\.kr|\.or\.kr)[^\s\)]*)",
        ]

        for pattern in origin_patterns:
            matches = re.findall(pattern, content_md, re.IGNORECASE)
            if matches:
                url = matches[0].strip()
                if url and url.startswith("http"):
                    logger.debug(f"원본 URL 추출 성공: {url[:50]}...")
                    return url

        logger.debug("content.md에서 원본 URL을 찾을 수 없음")
        return ""

    def _extract_scraping_url_from_content(self, content_md: str) -> str:
        """content.md에서 스크래핑 URL을 추출합니다."""
        if not content_md:
            return ""

        # 스크래핑 URL 패턴 찾기
        scraping_patterns = [
            r"\*\*스크래핑 URL\*\*[:\s]*(.+?)(?:\n|$)",
            r"스크래핑 URL[:\s]*(.+?)(?:\n|$)",
            r"\*\*수집 URL\*\*[:\s]*(.+?)(?:\n|$)",
            r"수집 URL[:\s]*(.+?)(?:\n|$)",
        ]

        for pattern in scraping_patterns:
            matches = re.findall(pattern, content_md, re.IGNORECASE)
            if matches:
                url = matches[0].strip()
                if url and url.startswith("http"):
                    logger.debug(f"스크래핑 URL 추출 성공: {url[:50]}...")
                    return url

        logger.debug("content.md에서 스크래핑 URL을 찾을 수 없음")
        return ""

    def _extract_announcement_date_from_content(self, content_md: str) -> str:
        """content.md에서 공고일을 문자열로 추출합니다."""
        if not content_md:
            return ""

        # 작성일 패턴 찾기 (마크다운 형식)
        # 콜론(:) 뒤의 날짜만 정확히 캡처
        date_patterns = [
            r"\*\*작성일\*\*:\s*([^\n]+)",  # **작성일**: 날짜
            r"\*\*작성일\*\*:\*\*\s*([^\n]+)",  # **작성일:**: 날짜
            r"작성일:\s*([^\n]+)",  # 작성일: 날짜
            r"\*\*등록일\*\*:\s*([^\n]+)",  # **등록일**: 날짜
            r"\*\*등록일\*\*:\*\*\s*([^\n]+)",  # **등록일:**: 날짜
            r"등록일:\s*([^\n]+)",  # 등록일: 날짜
            r"\*\*공고일\*\*:\s*([^\n]+)",  # **공고일**: 날짜
            r"\*\*공고일\*\*:\*\*\s*([^\n]+)",  # **공고일:**: 날짜
            r"공고일:\s*([^\n]+)",  # 공고일: 날짜
        ]

        for pattern in date_patterns:
            matches = re.findall(pattern, content_md, re.IGNORECASE)
            if matches:
                date_str = matches[0].strip()
                if date_str:
                    # 마크다운 볼드(**) 제거
                    date_str = re.sub(r"\*+", "", date_str).strip()
                    # 추가적인 정리 (공백 제거 등)
                    date_str = date_str.strip()

                    # 날짜 형식 검증 (최소한 연도가 포함되어야 함)
                    if re.search(r"\d{4}", date_str):
                        logger.debug(f"공고일 추출 성공: {date_str}")
                        return date_str

        logger.debug("content.md에서 공고일을 찾을 수 없음")
        return ""

    def _extract_attachment_urls_from_content(
        self, directory_path: Path
    ) -> Dict[str, str]:
        """content.md에서 첨부파일 다운로드 URL을 추출합니다."""
        content_md_path = directory_path / "content.md"
        attachment_urls = {}

        if not content_md_path.exists():
            return attachment_urls

        try:
            with open(content_md_path, "r", encoding="utf-8") as f:
                content = f.read()

            # **첨부파일**: 섹션 찾기
            # 수정: 모든 첨부파일 라인을 추출하도록 패턴 개선
            attachments_section = re.search(
                r"\*\*첨부파일\*\*:\s*\n+((?:.*\n?)*?)(?=\n\*\*|\Z)",
                content,
                re.MULTILINE,
            )

            if attachments_section:
                attachments_text = attachments_section.group(1)

                # 모든 줄을 처리하여 번호. 파일명:URL 패턴 찾기
                lines = attachments_text.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # 번호. 파일명:URL 패턴 (콜론 앞뒤 공백 허용)
                    match = re.match(r"^\d+\.\s*(.+?)\s*:\s*(https?://\S+)", line)
                    if match:
                        filename = match.group(1).strip()
                        url = match.group(2).strip()
                        attachment_urls[filename] = url
                        logger.debug(f"첨부파일 URL 매핑: {filename} -> {url[:50]}...")

            logger.info(
                f"첨부파일 URL 추출 완료: {len(attachment_urls)}개, 키: {list(attachment_urls.keys())}"
            )

        except Exception as e:
            logger.error(f"첨부파일 URL 추출 실패: {e}")

        return attachment_urls

    def _normalize_korean_text(self, text: str) -> str:
        """한글 텍스트를 NFC(Composed) 형태로 정규화합니다."""
        return unicodedata.normalize("NFC", text)

    def _natural_sort_key(self, path: Path) -> tuple:
        """폴더명의 숫자 부분을 기준으로 자연 정렬을 위한 키를 생성합니다."""
        import re

        folder_name = path.name
        # 숫자_제목 패턴에서 숫자 부분 추출
        match = re.match(r"^(\d+)_(.*)$", folder_name)
        if match:
            number = int(match.group(1))
            title = match.group(2)
            return (number, title)
        else:
            # 숫자로 시작하지 않는 경우는 맨 뒤로
            return (float("inf"), folder_name)

    def _process_attachments_separately(
        self, directory_path: Path
    ) -> tuple[str, List[str], List[Dict[str, Any]]]:
        """첨부파일들을 처리하여 내용을 결합하고 파일명 목록을 반휘합니다."""
        attachments_dir = directory_path / "attachments"

        if not attachments_dir.exists():
            return "", [], []

        combined_content = ""
        attachment_filenames = []
        attachment_files_info = []

        # content.md에서 파일 다운로드 URL 추출
        attachment_urls = self._extract_attachment_urls_from_content(directory_path)

        # 처리 가능한 확장자 정의 (Excel 파일 제외)
        supported_extensions = {
            ".pdf",
            ".hwp",
            ".hwpx",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".bmp",
            ".webp",
            ".pptx",
            ".docx",
            ".md",
            ".zip",  # ZIP 파일 지원 추가
        }

        target_keywords = ["양식", "서류", "신청서", "동의서"]

        # 파일들을 우선순위에 따라 분류
        priority_files = []  # 지원/공고 키워드가 있는 파일들
        normal_files = []  # 일반 파일들

        # 모든 파일을 먼저 검사하여 분류
        for file_path in attachments_dir.iterdir():
            if file_path.is_file():
                file_extension = file_path.suffix.lower()
                filename = file_path.stem
                lowercase_filename = filename.lower()

                # 지원하는 확장자만 처리
                if file_extension and file_extension in supported_extensions:
                    # 양식, 서류 등 제외 키워드 체크
                    if any(
                        keyword in lowercase_filename for keyword in target_keywords
                    ):
                        continue

                    # 지원/공고 키워드가 있는지 확인
                    if "지원" in lowercase_filename or "공고" in lowercase_filename:
                        priority_files.append(file_path)
                        logger.info(
                            f"우선순위 파일 발견 (지원/공고 키워드): {file_path.name}"
                        )
                    else:
                        normal_files.append(file_path)

        # 우선순위 파일들을 먼저 처리, 그 다음 일반 파일들 처리
        all_files_ordered = priority_files + normal_files

        for file_path in all_files_ordered:
            # 이미 위에서 필터링 했으므로 바로 처리
            file_extension = file_path.suffix.lower()
            filename = file_path.stem

            logger.info(f"filename===={filename}{file_extension}")

            attachment_filenames.append(self._normalize_korean_text(file_path.name))
            logger.info(f"첨부파일 처리 시작: {file_path.name}")

            # 파일 정보 수집 (모든 파일에 대해)
            # URL 매칭 시도 - 파일명으로 먼저 시도, 없으면 stem으로 시도
            download_url = attachment_urls.get(file_path.name, "")
            if not download_url:
                # 확장자 없는 이름으로도 시도
                download_url = attachment_urls.get(file_path.stem, "")

            if download_url:
                logger.debug(
                    f"URL 매칭 성공: {file_path.name} -> {download_url[:50]}..."
                )
            else:
                logger.debug(
                    f"URL 매칭 실패: {file_path.name}, 가능한 키: {list(attachment_urls.keys())[:3]}"
                )

            file_info = {
                "filename": file_path.name,  # 확장자 포함된 전체 파일명
                "file_size": (file_path.stat().st_size if file_path.exists() else 0),
                "conversion_success": False,
                "conversion_method": self._guess_conversion_method(file_extension),
                "download_url": download_url,  # 다운로드 URL 추가
            }

            # md 파일이 아닌 경우만 attachment_files_info에 추가
            if file_extension != ".md":
                attachment_files_info.append(file_info)

            # 이미 .md 파일인 경우 직접 읽기
            if file_extension == ".md":
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if content.strip():
                        combined_content += f"\n\n=== {self._normalize_korean_text(file_path.name)} ===\n{content}"
                        logger.info(
                            f"첨부파일 .md 직접 읽기 성공: {file_path.name} ({len(content)} 문자)"
                        )
                        file_info["conversion_success"] = True
                    else:
                        logger.warning(
                            f"첨부파일 .md 내용이 비어있음: {file_path.name}"
                        )
                except Exception as e:
                    logger.error(f"첨부파일 .md 직접 읽기 실패: {e}")
                continue

            # 첨부파일명.md 파일이 있는지 확인
            md_file_path = attachments_dir / f"{filename}.md"
            logger.debug(f"md_file_path: {md_file_path}")

            # attach_force가 True이면 기존 .md 파일을 무시하고 원본에서 재변환
            if not self.attach_force and md_file_path.exists():
                # .md 파일이 있으면 그것을 읽음
                try:
                    with open(md_file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if content.strip():
                        combined_content += f"\n\n=== {self._normalize_korean_text(filename)}.md ===\n{content}"
                        logger.debug(
                            f"첨부파일 .md 읽기 성공: {filename}.md ({len(content)} 문자)"
                        )
                        file_info["conversion_success"] = True
                    else:
                        logger.warning(f"첨부파일 .md 내용이 비어있음: {filename}.md")
                except Exception as e:
                    logger.error(f"첨부파일 .md 읽기 실패: {e}")
            else:
                # .md 파일이 없거나 attach_force가 True이면 원본 파일을 변환
                if self.attach_force and md_file_path.exists():
                    logger.info(
                        f"--attach-force: 기존 .md 파일 무시하고 재변환: {file_path.name}"
                    )
                else:
                    logger.info(f"첨부파일 변환 시작: {file_path.name}")

                try:
                    # attachment_processor가 None인 경우 처리
                    if self.attachment_processor is None:
                        logger.warning(
                            f"AttachmentProcessor를 사용할 수 없어 파일 건너뜀: {file_path.name}"
                        )
                        continue

                    content = self.attachment_processor.process_single_file(file_path)

                    if content and content.strip():
                        combined_content += f"\n\n=== {self._normalize_korean_text(file_path.name)} ===\n{content}"
                        logger.info(
                            f"첨부파일 변환 성공: {file_path.name} ({len(content)} 문자)"
                        )
                        file_info["conversion_success"] = True

                        # 변환된 내용을 .md 파일로 저장
                        try:
                            with open(md_file_path, "w", encoding="utf-8") as f:
                                f.write(content)
                            logger.debug(f"변환된 내용을 .md로 저장: {md_file_path}")
                        except Exception as save_e:
                            logger.warning(f".md 파일 저장 실패: {save_e}")
                    else:
                        logger.warning(f"첨부파일에서 내용 추출 실패: {file_path.name}")

                except Exception as e:
                    error_msg = str(e)
                    if (
                        "Invalid code point" in error_msg
                        or "PDFSyntaxError" in error_msg
                        or "No /Root object" in error_msg
                    ):
                        logger.warning(f"손상된 PDF 파일 건너뛰기: {file_path.name}")
                    elif "UnicodeDecodeError" in error_msg:
                        logger.warning(f"인코딩 문제로 파일 건너뛰기: {file_path.name}")
                    else:
                        logger.error(f"첨부파일 변환 실패 ({file_path.name}): {e}")

                    # 변환 실패한 파일 정보 기록
                    file_info["conversion_success"] = False
                    file_info["error_message"] = error_msg[
                        :200
                    ]  # 오류 메시지 일부만 저장

        logger.info(
            f"첨부파일 처리 완료: {len(attachment_filenames)}개 파일, {len(combined_content)} 문자"
        )
        return combined_content.strip(), attachment_filenames, attachment_files_info

    def _guess_conversion_method(self, file_extension: str) -> str:
        """파일 확장자에 따른 변환 방법을 추정합니다."""
        ext_lower = file_extension.lower()

        if ext_lower == ".pdf":
            return "pdf_docling"
        elif ext_lower in [".hwp", ".hwpx"]:
            return "hwp_markdown"
        elif ext_lower in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]:
            return "ocr"
        else:
            return "unknown"

    def _convert_to_yyyymmdd(self, date_str: str) -> str:
        """날짜 문자열을 YYYYMMDD 포맷으로 변환합니다."""
        try:
            # 다양한 날짜 포맷 시도
            from datetime import datetime

            # 가능한 날짜 포맷들
            date_formats = [
                "%Y-%m-%d",
                "%Y.%m.%d",
                "%Y/%m/%d",
                "%Y%m%d",
                "%Y년 %m월 %d일",
                "%Y-%m-%d %H:%M:%S",
                "%Y.%m.%d %H:%M:%S",
            ]

            for fmt in date_formats:
                try:
                    dt = datetime.strptime(date_str.strip(), fmt)
                    return dt.strftime("%Y%m%d")  # YYYYMMDD 형식
                except ValueError:
                    continue

            # 모든 포맷 실패시 원본 반환
            logger.warning(f"날짜 변환 실패, 원본 반환: {date_str}")
            return date_str

        except Exception as e:
            logger.error(f"날짜 변환 중 오류: {e}")
            return date_str

    def _fallback_normalize_url(self, url: str | None) -> str | None:
        """
        도메인 설정이 없을 때 최소한의 URL 정규화를 수행합니다.

        ⚠️ 주의: domain_key_config에 도메인이 있으면 이 메서드는 사용되지 않습니다.
        domain_key_config가 우선순위 1이고, 이것은 폴백(fallback)입니다.

        ⚠️ 중요: domain_key_config와 DomainKeyExtractor와 동일하게 알파벳 순으로 정렬합니다!
        URL 파라미터 순서와 무관하게 동일한 키를 생성하여 중복 감지 정확도를 향상시킵니다.

        ⚠️ 페이지네이션/검색 파라미터 자동 제외: page, pageIndex, searchCnd 등은 url_key에서 제외됩니다.

        동작:
        1. URL을 파싱하여 도메인과 쿼리 파라미터 추출
        2. 페이지네이션/검색 파라미터 제외
        3. 남은 파라미터를 **알파벳 순으로 정렬**
        4. "domain|key1=val1&key2=val2" 형식으로 반환 (정렬된 순서)

        Args:
            url: 원본 URL (None 가능)

        Returns:
            정규화된 URL 키 또는 None

        Examples:
            >>> _fallback_normalize_url("https://example.com?b=2&a=1")
            'example.com|a=1&b=2'  # ← 알파벳 정렬됨

            >>> _fallback_normalize_url("https://example.com?nttId=123&page=1")
            'example.com|nttId=123'  # ← page 제외됨

            >>> _fallback_normalize_url("https://example.com/path?id=1")
            'example.com|id=1'

            >>> _fallback_normalize_url(None)
            None
        """
        if not url:
            return None

        try:
            from urllib.parse import urlparse, parse_qsl

            # 제외할 페이지네이션/검색/정렬 파라미터 목록
            EXCLUDED_PARAMS = {
                # 페이지네이션 (기존)
                'page', 'pageNo', 'pageNum', 'pageIndex', 'pageSize', 'pageUnit',
                'offset', 'limit', 'start', 'Start', 'end',
                'currentPage', 'curPage', 'pageNumber', 'pn',
                'ofr_pageSize',

                # 페이지네이션 (Phase 10 추가 - 누락된 변형)
                'homepage_pbs_yn',    # 16,095개
                'cpage',              # 2,497개
                'startPage',          # 1,348개
                'q_currPage',         # 728개
                'pageLine',           # 438개
                'pageCd',             # 390개
                'recordCountPerPage', # 227개
                'pageId',             # 205개
                'page_id',            # 196개
                'pageid',             # 196개
                'GotoPage',           # 149개
                'q_rowPerPage',       # 51개

                # 검색 관련
                'search', 'searchWord', 'searchType', 'searchCategory',
                'searchCnd', 'searchKrwd', 'searchGosiSe', 'search_type',
                'keyword', 'query', 'q',

                # Phase 15 추가: 게시판 검색/카테고리 파라미터
                'searchCtgry',        # 검색 카테고리 (원주, 보은, 영월, 태백 등)
                'integrDeptCode',     # 통합 부서 코드 (원주, 보은, 영월 등)
                'searchCnd2',         # 검색 조건 2 (서귀포)
                'depNm',              # 부서명 (서귀포)

                # 정렬 관련
                'sort', 'order', 'orderBy', 'sortField', 'sortOrder',
                # 뷰 모드
                'view', 'viewMode', 'display', 'listType',
            }

            parsed = urlparse(url)
            domain = parsed.netloc

            if not domain:
                logger.warning(f"도메인 추출 실패, 원본 URL 반환: {url}")
                return url

            # 쿼리 파라미터 파싱 (빈 값도 포함)
            params = parse_qsl(parsed.query, keep_blank_values=True)

            if params:
                # ✅ 페이지네이션/검색 파라미터 제외
                filtered_params = [(k, v) for k, v in params if k not in EXCLUDED_PARAMS]

                if filtered_params:
                    # ✅ 알파벳 순으로 정렬하여 파라미터 순서 무관하게 동일한 키 생성
                    # domain_key_config와 DomainKeyExtractor도 동일하게 알파벳 정렬 사용
                    sorted_params = sorted(filtered_params)
                    param_str = "&".join(f"{k}={v}" for k, v in sorted_params)
                    normalized_key = f"{domain}|{param_str}"

                    # 제외된 파라미터가 있으면 로그 남김
                    excluded_count = len(params) - len(filtered_params)
                    if excluded_count > 0:
                        excluded_keys = [k for k, v in params if k in EXCLUDED_PARAMS]
                        logger.debug(f"페이지네이션 파라미터 {excluded_count}개 제외: {excluded_keys}")
                else:
                    # 모든 파라미터가 페이지네이션이면 경로로 폴백
                    if parsed.path and parsed.path != '/':
                        normalized_key = f"{domain}|path={parsed.path}"
                    else:
                        normalized_key = f"{domain}|no_params"
                    logger.warning(f"모든 파라미터가 페이지네이션! 경로 사용: {url}")
            else:
                # 쿼리 파라미터 없으면 경로 포함
                if parsed.path and parsed.path != '/':
                    normalized_key = f"{domain}|path={parsed.path}"
                else:
                    # 경로도 없으면 도메인만
                    normalized_key = f"{domain}|no_params"

            logger.info(f"✓ 폴백 정규화 완료: {url[:80]}... → {normalized_key}")
            return normalized_key

        except Exception as e:
            logger.error(f"폴백 정규화 중 오류, 원본 반환: {e}")
            return url

    def _update_api_url_registry(
        self, session, origin_url: str, preprocessing_id: int, site_code: str,
        scraping_url: str = None, url_key_hash: str = None
    ) -> bool:
        """
        api_url_registry 테이블의 preprocessing_id를 업데이트합니다.

        Args:
            session: SQLAlchemy 세션
            origin_url: 원본 URL
            preprocessing_id: announcement_pre_processing 테이블의 ID
            site_code: 사이트 코드
            scraping_url: 스크래핑 URL (API 사이트의 경우 우선 매칭)
            url_key_hash: 정규화된 URL 해시 (가장 우선적으로 매칭)

        Returns:
            업데이트 성공 여부
        """
        try:
            from sqlalchemy import text

            # API 사이트만 처리
            if site_code not in ["kStartUp", "bizInfo", "smes24"]:
                logger.debug(f"API 사이트가 아니므로 api_url_registry 업데이트 건너뜀: {site_code}")
                return True

            # ⚠️ 테이블 컬럼 구조:
            # - api_url_registry.announcement_url: 공고 URL (bizInfo, smes24 사용)
            # - api_url_registry.scrap_url: 스크래핑 URL (kStartUp 사용)
            # - api_url_registry.url_key_hash: 정규화된 URL 해시 (우선 매칭)

            # 🆕 0순위: url_key_hash로 매칭 (가장 정확, 쿼리 파라미터 순서 무관)
            if url_key_hash:
                try:
                    update_sql = text("""
                        UPDATE api_url_registry
                        SET preprocessing_id = :preprocessing_id,
                            update_at = NOW()
                        WHERE url_key_hash = :url_key_hash
                        AND site_code = :site_code
                        LIMIT 1
                    """)

                    result = session.execute(
                        update_sql,
                        {
                            "preprocessing_id": preprocessing_id,
                            "url_key_hash": url_key_hash,
                            "site_code": site_code
                        }
                    )

                    rows_affected = result.rowcount
                    if rows_affected > 0:
                        logger.info(
                            f"✅ api_url_registry 업데이트 성공 ({site_code}, url_key_hash): "
                            f"hash={url_key_hash[:16]}..., preprocessing_id={preprocessing_id}"
                        )
                        return True
                    else:
                        logger.debug(
                            f"url_key_hash로 매칭 실패, 문자열 매칭으로 폴백: {url_key_hash[:16]}..."
                        )
                except Exception as e:
                    # url_key_hash 컬럼이 없을 수 있음 (에러 무시하고 기존 로직으로 폴백)
                    logger.debug(f"url_key_hash 매칭 실패 (컬럼 없을 수 있음), 문자열 매칭으로 폴백: {e}")

            if site_code == "kStartUp":
                # kStartUp: scrap_url 컬럼 사용 (announcement_url은 신뢰할 수 없음)
                if not scraping_url:
                    logger.debug("kStartUp: scraping_url이 없어 api_url_registry 업데이트 불가")
                    return False

                update_sql = text("""
                    UPDATE api_url_registry
                    SET preprocessing_id = :preprocessing_id,
                        update_at = NOW()
                    WHERE scrap_url = :scraping_url
                    LIMIT 1
                """)

                result = session.execute(
                    update_sql,
                    {
                        "preprocessing_id": preprocessing_id,
                        "scraping_url": scraping_url
                    }
                )

                rows_affected = result.rowcount
                if rows_affected > 0:
                    logger.info(
                        f"api_url_registry 업데이트 성공 (kStartUp, scrap_url): "
                        f"url={scraping_url[:50]}..., preprocessing_id={preprocessing_id}"
                    )
                    return True
                else:
                    logger.debug(
                        f"api_url_registry에 매칭되는 레코드 없음 (kStartUp, scrap_url): "
                        f"scraping_url={scraping_url[:50]}..."
                    )
                    return False

            else:
                # bizInfo, smes24: announcement_url 컬럼 사용
                # 우선순위: scraping_url → origin_url

                # 1차 시도: scraping_url로 매칭
                if scraping_url:
                    update_sql = text("""
                        UPDATE api_url_registry
                        SET preprocessing_id = :preprocessing_id,
                            update_at = NOW()
                        WHERE announcement_url = :scraping_url
                        LIMIT 1
                    """)

                    result = session.execute(
                        update_sql,
                        {
                            "preprocessing_id": preprocessing_id,
                            "scraping_url": scraping_url
                        }
                    )

                    rows_affected = result.rowcount
                    if rows_affected > 0:
                        logger.info(
                            f"api_url_registry 업데이트 성공 ({site_code}, announcement_url with scraping_url): "
                            f"url={scraping_url[:50]}..., preprocessing_id={preprocessing_id}"
                        )
                        return True

                # 2차 시도: origin_url로 매칭 (scraping_url로 실패한 경우)
                if origin_url:
                    update_sql = text("""
                        UPDATE api_url_registry
                        SET preprocessing_id = :preprocessing_id,
                            update_at = NOW()
                        WHERE announcement_url = :origin_url
                        LIMIT 1
                    """)

                    result = session.execute(
                        update_sql,
                        {
                            "preprocessing_id": preprocessing_id,
                            "origin_url": origin_url
                        }
                    )
                    # commit은 _save_processing_result에서 한 번만 수행

                    rows_affected = result.rowcount
                    if rows_affected > 0:
                        logger.info(
                            f"api_url_registry 업데이트 성공 ({site_code}, announcement_url with origin_url): "
                            f"url={origin_url[:50]}..., preprocessing_id={preprocessing_id}"
                        )
                        return True

                # 둘 다 실패
                logger.debug(
                    f"api_url_registry에 매칭되는 레코드 없음 ({site_code}, announcement_url): "
                    f"scraping_url={scraping_url[:50] if scraping_url else 'None'}..., "
                    f"origin_url={origin_url[:50] if origin_url else 'None'}..."
                )
                return False

        except Exception as e:
            # 테이블이 존재하지 않거나 컬럼이 없는 경우 경고만 출력
            logger.warning(f"api_url_registry 업데이트 실패 (무시하고 계속): {e}")
            return False

    def _get_priority(self, site_type: str) -> int:
        """
        site_type의 우선순위를 반환합니다.
        높을수록 우선순위 높음.

        Args:
            site_type: 사이트 타입 (Eminwon, Homepage, Scraper, api_scrap 등)

        Returns:
            우선순위 값 (0-3)
        """
        priority_map = {
            'Eminwon': 3,
            'Homepage': 3,
            'Scraper': 3,
            'api_scrap': 1,
            'Unknown': 0,
        }
        return priority_map.get(site_type, 0)

    def _log_api_url_processing(
        self,
        session,
        site_code: str,
        url_key: str,
        url_key_hash: str,
        processing_status: str,
        announcement_id: str = None,
        announcement_url: str = None,
        scraping_url: str = None,
        preprocessing_id: int = None,
        existing_preprocessing_id: int = None,
        api_url_registry_id: int = None,
        existing_site_type: str = None,
        existing_site_code: str = None,
        duplicate_reason: dict = None,
        error_message: str = None,
        title: str = None,
        folder_name: str = None,
    ) -> bool:
        """
        API URL 처리 시도를 로그에 기록합니다.

        Args:
            session: SQLAlchemy 세션
            site_code: 사이트 코드 (kStartUp, bizInfo, smes24, prv_* 등)
            url_key: 정규화된 URL 키
            url_key_hash: URL 키 해시 (MD5)
            processing_status: 처리 상태
                - 'new_inserted': 새로 삽입됨
                - 'duplicate_updated': 중복이지만 업데이트됨 (우선순위 높음)
                - 'duplicate_skipped': 중복이라 스킵됨 (우선순위 낮음)
                - 'duplicate_preserved': 기존 데이터 유지됨
                - 'failed': 처리 실패
                - 'no_url_key': URL 정규화 실패
            preprocessing_id: 생성/업데이트된 레코드 ID
            existing_preprocessing_id: 이미 존재하던 레코드 ID
            existing_site_type: 기존 레코드의 site_type
            existing_site_code: 기존 레코드의 site_code
            duplicate_reason: 중복 사유 (dict)
            error_message: 오류 메시지
            title: 공고 제목
            folder_name: 폴더명

        Returns:
            로그 기록 성공 여부
        """
        try:
            from sqlalchemy import text
            import json

            # duplicate_reason을 JSON으로 변환
            duplicate_reason_json = None
            if duplicate_reason:
                duplicate_reason_json = json.dumps(duplicate_reason, ensure_ascii=False)

            sql = text("""
                INSERT INTO api_url_processing_log (
                    site_code,
                    announcement_id,
                    announcement_url,
                    scraping_url,
                    url_key,
                    url_key_hash,
                    processing_status,
                    preprocessing_id,
                    existing_preprocessing_id,
                    api_url_registry_id,
                    existing_site_type,
                    existing_site_code,
                    duplicate_reason,
                    error_message,
                    title,
                    folder_name,
                    created_at
                ) VALUES (
                    :site_code,
                    :announcement_id,
                    :announcement_url,
                    :scraping_url,
                    :url_key,
                    :url_key_hash,
                    :processing_status,
                    :preprocessing_id,
                    :existing_preprocessing_id,
                    :api_url_registry_id,
                    :existing_site_type,
                    :existing_site_code,
                    :duplicate_reason,
                    :error_message,
                    :title,
                    :folder_name,
                    NOW()
                )
            """)

            session.execute(sql, {
                "site_code": site_code,
                "announcement_id": announcement_id,
                "announcement_url": announcement_url,
                "scraping_url": scraping_url,
                "url_key": url_key,
                "url_key_hash": url_key_hash,
                "processing_status": processing_status,
                "preprocessing_id": preprocessing_id,
                "existing_preprocessing_id": existing_preprocessing_id,
                "api_url_registry_id": api_url_registry_id,
                "existing_site_type": existing_site_type,
                "existing_site_code": existing_site_code,
                "duplicate_reason": duplicate_reason_json,
                "error_message": error_message,
                "title": title,
                "folder_name": folder_name,
            })

            logger.debug(
                f"API URL 처리 로그 기록: site_code={site_code}, "
                f"status={processing_status}, url_key_hash={url_key_hash[:16] if url_key_hash else 'None'}..."
            )
            return True

        except Exception as e:
            logger.warning(f"API URL 처리 로그 기록 실패 (무시하고 계속): {e}")
            return False

    def _log_announcement_duplicate(
        self,
        session,
        preprocessing_id: int,
        url_key_hash: str,
        duplicate_type: str,
        site_code: str,
        folder_name: str,
        domain: str = None,
        domain_configured: bool = False,
        existing_record: dict = None,
        error_message: str = None,
    ) -> bool:
        """
        announcement_duplicate_log 테이블에 중복 처리 로그를 기록합니다.

        Args:
            session: SQLAlchemy 세션
            preprocessing_id: 저장/업데이트된 레코드 ID
            url_key_hash: URL 키 해시 (MD5) - domain_key_config 없으면 NULL
            duplicate_type: 중복 유형
                - 'unconfigured_domain': domain_key_config에 설정 없음
                - 'new_inserted': 신규 삽입 (domain_key_config 있고 중복 없음)
                - 'replaced': 기존 데이터 교체 (우선순위 높음)
                - 'kept_existing': 기존 데이터 유지 (우선순위 낮음)
                - 'same_type_duplicate': 동일 타입 재수집 (우선순위 동일)
                - 'error': 처리 중 오류
            site_code: 사이트 코드
            folder_name: 폴더명
            domain: 도메인명
            domain_configured: domain_key_config에 설정 여부
            existing_record: 기존 레코드 정보 (중복 시)
            error_message: 에러 메시지 (오류 시)

        Returns:
            로그 기록 성공 여부
        """
        try:
            from sqlalchemy import text
            import json
            from datetime import datetime

            # 우선순위 계산
            new_priority = self._get_priority(self.site_type)
            existing_priority = None
            existing_preprocessing_id = None
            existing_site_type = None
            existing_site_code = None
            duplicate_detail = None

            # 기존 레코드 정보 추출
            if existing_record:
                existing_preprocessing_id = existing_record.get('id')
                existing_site_type = existing_record.get('site_type')
                existing_site_code = existing_record.get('site_code')
                existing_priority = self._get_priority(existing_site_type)

                # 상세 정보 JSON 생성
                if duplicate_type == 'replaced':
                    decision = '기존 데이터 교체'
                    reason = f'우선순위 높음: {self.site_type}({new_priority}) > {existing_site_type}({existing_priority})'
                elif duplicate_type == 'kept_existing':
                    decision = '기존 데이터 유지'
                    reason = f'우선순위 낮음: {self.site_type}({new_priority}) < {existing_site_type}({existing_priority})'
                elif duplicate_type == 'same_type_duplicate':
                    decision = '최신 데이터로 업데이트'
                    reason = f'우선순위 동일: {self.site_type}({new_priority}) = {existing_site_type}({existing_priority})'
                else:
                    decision = '알 수 없음'
                    reason = f'duplicate_type={duplicate_type}'

                duplicate_detail = {
                    'decision': decision,
                    'reason': reason,
                    'existing_folder': existing_record.get('folder_name'),
                    'existing_url_key': existing_record.get('url_key'),
                    'priority_comparison': f'{new_priority} vs {existing_priority}',
                    'domain': domain,
                    'domain_configured': domain_configured,
                    'timestamp': datetime.now().isoformat()
                }

            elif duplicate_type == 'unconfigured_domain':
                # domain_key_config에 없는 경우
                duplicate_detail = {
                    'decision': '신규 등록 (domain_key_config 없음)',
                    'reason': 'domain_key_config 테이블에 설정이 없어서 중복 체크 생략',
                    'domain': domain,
                    'domain_configured': False,
                    'timestamp': datetime.now().isoformat()
                }

            elif duplicate_type == 'new_inserted':
                # domain_key_config에 있지만 url_key_hash 중복 없음
                duplicate_detail = {
                    'decision': '신규 등록',
                    'reason': 'url_key_hash 중복 없음',
                    'domain': domain,
                    'domain_configured': domain_configured,
                    'timestamp': datetime.now().isoformat()
                }

            # 기존 폴더명 추출
            existing_folder_name = None
            if existing_record:
                existing_folder_name = existing_record.get('folder_name')

            # announcement_duplicate_log INSERT
            sql = text("""
                INSERT INTO announcement_duplicate_log (
                    preprocessing_id,
                    existing_preprocessing_id,
                    duplicate_type,
                    url_key_hash,
                    new_site_type,
                    new_site_code,
                    existing_site_type,
                    existing_site_code,
                    new_priority,
                    existing_priority,
                    new_folder_name,
                    existing_folder_name,
                    duplicate_detail,
                    error_message
                ) VALUES (
                    :preprocessing_id,
                    :existing_preprocessing_id,
                    :duplicate_type,
                    :url_key_hash,
                    :new_site_type,
                    :new_site_code,
                    :existing_site_type,
                    :existing_site_code,
                    :new_priority,
                    :existing_priority,
                    :new_folder_name,
                    :existing_folder_name,
                    :duplicate_detail,
                    :error_message
                )
            """)

            # JSON 직렬화
            duplicate_detail_json = None
            if duplicate_detail:
                duplicate_detail_json = json.dumps(duplicate_detail, ensure_ascii=False)

            # 파라미터 바인딩
            params = {
                'preprocessing_id': preprocessing_id,
                'existing_preprocessing_id': existing_preprocessing_id,
                'duplicate_type': duplicate_type,
                'url_key_hash': url_key_hash,  # unconfigured_domain일 때 NULL
                'new_site_type': self.site_type,
                'new_site_code': site_code,
                'existing_site_type': existing_site_type,
                'existing_site_code': existing_site_code,
                'new_priority': new_priority,
                'existing_priority': existing_priority,
                'new_folder_name': folder_name,
                'existing_folder_name': existing_folder_name,
                'duplicate_detail': duplicate_detail_json,
                'error_message': error_message
            }

            # 실행
            session.execute(sql, params)
            # session.commit()는 호출하지 않음 (상위 함수에서 commit)

            logger.debug(
                f"중복 로그 기록 완료: {duplicate_type} - "
                f"preprocessing_id={preprocessing_id}, "
                f"domain_configured={domain_configured}, "
                f"url_key_hash={url_key_hash[:16] if url_key_hash else 'None'}..."
            )

            return True

        except Exception as e:
            logger.error(f"중복 로그 기록 실패: {e}")
            # 로그 기록 실패해도 메인 처리는 계속 진행
            return False

    def _save_processing_result(
        self,
        folder_name: str,
        site_code: str,
        content_md: str,
        combined_content: str,
        attachment_filenames: List[str] = None,
        status: str = "성공",
        exclusion_keywords: List[str] = None,
        exclusion_reason: str = None,
        error_message: str = None,
        force: bool = False,
        title: str = None,
        origin_url: str = None,
        url_key: str = None,
        scraping_url: str = None,
        announcement_date: str = None,
        attachment_files_info: List[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """처리 결과를 데이터베이스에 저장합니다."""
        try:
            from sqlalchemy import text

            with self.db_manager.SessionLocal() as session:
                # ================================================
                # 🆕 예외 케이스: smes24 + bizinfo URL 중복 체크
                # ================================================
                # smes24의 origin_url이 bizInfo의 scraping_url과 일치하면 스킵
                if site_code == 'smes24' and origin_url and 'bizinfo.go.kr' in origin_url.lower():
                    try:
                        existing_bizinfo = session.execute(
                            text("""
                                SELECT id, site_type, site_code, folder_name, url_key, created_at
                                FROM announcement_pre_processing
                                WHERE scraping_url = :origin_url
                                AND site_code = 'bizInfo'
                                LIMIT 1
                            """),
                            {"origin_url": origin_url}
                        ).fetchone()

                        if existing_bizinfo:
                            logger.info(
                                f"🚫 중복 스킵 (예외 로직): smes24 origin_url이 bizInfo scraping_url과 일치\n"
                                f"   smes24 folder: {folder_name}\n"
                                f"   origin_url: {origin_url[:100]}...\n"
                                f"   기존 bizInfo: ID={existing_bizinfo.id}, folder={existing_bizinfo.folder_name}\n"
                                f"   기존 url_key: {existing_bizinfo.url_key}\n"
                                f"   → bizInfo 우선 (지자체 원본 데이터 유지)"
                            )

                            return existing_bizinfo.id  # 기존 ID 반환하고 종료

                    except Exception as e:
                        logger.error(f"예외 케이스 중복 체크 실패 (계속 진행): {e}")
                        # 에러 발생 시 기존 로직으로 폴백

                # UPSERT 실행 전에 기존 레코드 조회 (우선순위 비교를 위해)
                existing_record_before_upsert = None
                if force and url_key:
                    try:
                        existing_record_before_upsert = session.execute(
                            text("""
                                SELECT id, site_type, site_code, folder_name
                                FROM announcement_pre_processing
                                WHERE url_key = :url_key
                                LIMIT 1
                            """),
                            {"url_key": url_key}
                        ).fetchone()

                        if existing_record_before_upsert:
                            logger.debug(
                                f"UPSERT 전 기존 레코드 발견: ID={existing_record_before_upsert.id}, "
                                f"site_type={existing_record_before_upsert.site_type}, "
                                f"site_code={existing_record_before_upsert.site_code}"
                            )
                    except Exception as e:
                        logger.warning(f"UPSERT 전 기존 레코드 조회 실패 (무시하고 계속): {e}")

                if force:
                    # UPSERT 로직 with site_type 우선순위 (지자체 > API)
                    sql = text(
                        """
                        INSERT INTO announcement_pre_processing (
                            folder_name, site_type, site_code, content_md, combined_content,
                            attachment_filenames, attachment_files_list, exclusion_keyword, exclusion_reason,
                            title, origin_url, url_key, scraping_url, announcement_date,
                            processing_status, error_message, created_at, updated_at
                        ) VALUES (
                            :folder_name, :site_type, :site_code, :content_md, :combined_content,
                            :attachment_filenames, :attachment_files_list, :exclusion_keyword, :exclusion_reason,
                            :title, :origin_url, :url_key, :scraping_url, :announcement_date,
                            :processing_status, :error_message, NOW(), NOW()
                        )
                        ON DUPLICATE KEY UPDATE
                            site_type = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(site_type),
                                site_type
                            ),
                            content_md = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(content_md),
                                content_md
                            ),
                            combined_content = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(combined_content),
                                combined_content
                            ),
                            attachment_filenames = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(attachment_filenames),
                                attachment_filenames
                            ),
                            attachment_files_list = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(attachment_files_list),
                                attachment_files_list
                            ),
                            exclusion_keyword = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(exclusion_keyword),
                                exclusion_keyword
                            ),
                            exclusion_reason = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(exclusion_reason),
                                exclusion_reason
                            ),
                            processing_status = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(processing_status),
                                processing_status
                            ),
                            title = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(title),
                                title
                            ),
                            origin_url = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(origin_url),
                                origin_url
                            ),
                            url_key = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(url_key),
                                url_key
                            ),
                            scraping_url = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(scraping_url),
                                scraping_url
                            ),
                            announcement_date = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(announcement_date),
                                announcement_date
                            ),
                            error_message = IF(
                                VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
                                site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
                                VALUES(error_message),
                                error_message
                            ),
                            updated_at = NOW()
                    """
                    )
                else:
                    # 일반 INSERT with UPSERT (중복 처리)
                    sql = text(
                        """
                        INSERT INTO announcement_pre_processing (
                            folder_name, site_type, site_code, content_md, combined_content,
                            attachment_filenames, attachment_files_list, exclusion_keyword, exclusion_reason,
                            title, origin_url, url_key, scraping_url, announcement_date,
                            processing_status, error_message, created_at, updated_at
                        ) VALUES (
                            :folder_name, :site_type, :site_code, :content_md, :combined_content,
                            :attachment_filenames, :attachment_files_list, :exclusion_keyword, :exclusion_reason,
                            :title, :origin_url, :url_key, :scraping_url, :announcement_date,
                            :processing_status, :error_message, NOW(), NOW()
                        )
                        ON DUPLICATE KEY UPDATE
                            folder_name = VALUES(folder_name),
                            site_type = VALUES(site_type),
                            site_code = VALUES(site_code),
                            content_md = VALUES(content_md),
                            combined_content = VALUES(combined_content),
                            attachment_filenames = VALUES(attachment_filenames),
                            attachment_files_list = VALUES(attachment_files_list),
                            exclusion_keyword = VALUES(exclusion_keyword),
                            exclusion_reason = VALUES(exclusion_reason),
                            title = VALUES(title),
                            origin_url = VALUES(origin_url),
                            url_key = VALUES(url_key),
                            scraping_url = VALUES(scraping_url),
                            announcement_date = VALUES(announcement_date),
                            processing_status = VALUES(processing_status),
                            error_message = VALUES(error_message),
                            updated_at = NOW()
                    """
                    )

                # JSON으로 직렬화
                attachment_files_json = (
                    json.dumps(attachment_files_info, ensure_ascii=False)
                    if attachment_files_info
                    else None
                )

                # Homepage 또는 Eminwon인 경우 DB에 저장할 site_code에 "prv_" 접두사 추가
                # 단, 원본 site_code는 변경하지 않음 (API 업데이트 등에서 사용)
                db_site_code = ("prv_" + site_code) if self.site_type in ("Homepage", "Eminwon") else site_code

                params = {
                    "folder_name": folder_name,
                    "site_type": self.site_type,
                    "site_code": db_site_code,
                    "content_md": content_md,
                    "combined_content": combined_content,
                    "attachment_filenames": (
                        ", ".join(attachment_filenames)
                        if attachment_filenames
                        else None
                    ),
                    "attachment_files_list": attachment_files_json,
                    "exclusion_keyword": (
                        ", ".join(exclusion_keywords) if exclusion_keywords else None
                    ),
                    "exclusion_reason": exclusion_reason,
                    "title": title,
                    "origin_url": origin_url,
                    "url_key": url_key,
                    "scraping_url": scraping_url,
                    "announcement_date": announcement_date,
                    "processing_status": status,
                    "error_message": error_message,
                }

                result = session.execute(sql, params)
                record_id = result.lastrowid
                affected_rows = result.rowcount

                # ================================================
                # 🔧 url_key_hash 조회 (GENERATED COLUMN이므로 DB에서 자동 생성)
                # ================================================
                # url_key가 있는 경우 DB에서 자동 생성된 url_key_hash 조회
                url_key_hash = None
                if url_key:
                    url_key_hash_result = session.execute(
                        text("SELECT url_key_hash FROM announcement_pre_processing WHERE id = :id"),
                        {"id": record_id}
                    ).fetchone()
                    if url_key_hash_result:
                        url_key_hash = url_key_hash_result.url_key_hash
                        logger.debug(f"DB 생성 url_key_hash: {url_key_hash[:16]}... (record_id={record_id})")
                    else:
                        logger.warning(f"url_key_hash 조회 실패: record_id={record_id}")

                # ================================================
                # 🆕 API URL 처리 로그 기록
                # ================================================
                # url_key가 없으면 'no_url_key' 상태로 기록
                if not url_key:
                    # ================================================
                    # 🆕 api_url_processing_log 기록 (삭제 예정)
                    # ================================================
                    self._log_api_url_processing(
                        session=session,
                        site_code=db_site_code,  # ← site_code → db_site_code (일관성)
                        url_key=None,
                        url_key_hash=None,
                        processing_status='no_url_key',
                        preprocessing_id=record_id,
                        title=title,
                        folder_name=folder_name,
                        error_message="URL 정규화 실패 (url_key 없음)"
                    )

                    # ================================================
                    # 🆕 announcement_duplicate_log 기록 (신규)
                    # ================================================
                    # url_key가 없음 → domain_key_config에 설정 없음 or URL 추출 실패
                    from urllib.parse import urlparse
                    domain = None
                    if origin_url:
                        try:
                            parsed_url = urlparse(origin_url)
                            domain = parsed_url.netloc
                        except Exception as e:
                            logger.warning(f"URL 파싱 실패: {origin_url}, {e}")

                    self._log_announcement_duplicate(
                        session=session,
                        preprocessing_id=record_id,
                        url_key_hash=None,
                        duplicate_type='unconfigured_domain',  # domain_key_config 없거나 URL 추출 실패
                        site_code=db_site_code,
                        folder_name=folder_name,
                        domain=domain,
                        domain_configured=False,
                        existing_record=None,
                        error_message="URL 정규화 실패 (url_key 없음)"
                    )
                else:
                    # ⚠️ url_key_hash는 GENERATED COLUMN이므로 이미 위에서 DB 조회로 취득함
                    # (line 2037-2047에서 조회)

                    # domain_key_config 확인
                    from urllib.parse import urlparse
                    parsed_url = urlparse(origin_url)
                    domain = parsed_url.netloc
                    domain_has_config = self.url_key_extractor.get_domain_config(domain, parsed_url.path)

                    # 처리 상태 결정
                    processing_status = None
                    existing_preprocessing_id = None
                    existing_site_type = None
                    existing_site_code = None
                    duplicate_reason = None

                    # domain_key_config 확인 및 처리
                    if not domain_has_config:
                        # domain_key_config에 없는 경우 (API 외부 도메인 등)
                        logger.debug(
                            f"domain_key_config 없음: domain={domain}, url_key={url_key[:50]}... "
                            f"fallback으로 url_key 생성됨"
                        )
                        processing_status = 'new_inserted'  # domain_key_config 없어도 신규로 처리
                        duplicate_reason = {
                            "reason": f"domain_key_config not found, treated as new (domain={domain})",
                            "domain": domain,
                            "url_key": url_key
                        }

                    # domain_key_config 있는 경우: 정상 중복 체크
                    elif affected_rows == 1:
                        # 새로 INSERT됨
                        processing_status = 'new_inserted'  # ← 중복 체크 결과 (duplicate_type용)
                        logger.debug(f"새 레코드 삽입: ID={record_id}, url_key_hash={url_key_hash[:16]}...")

                    elif affected_rows == 2:
                        # UPDATE됨 (ON DUPLICATE KEY UPDATE 실행)
                        logger.debug(f"중복 감지 (affected_rows=2): url_key_hash={url_key_hash[:16]}...")

                        # UPSERT 전에 조회한 기존 레코드 정보 사용
                        if existing_record_before_upsert:
                            # 업데이트 전의 정확한 값으로 우선순위 비교
                            existing_site_type = existing_record_before_upsert.site_type
                            existing_site_code = existing_record_before_upsert.site_code
                            existing_preprocessing_id = existing_record_before_upsert.id

                            # 우선순위 비교
                            current_priority = self._get_priority(self.site_type)
                            existing_priority = self._get_priority(existing_site_type)

                            if current_priority > existing_priority:
                                # 현재가 더 높은 우선순위 → 업데이트됨
                                processing_status = 'duplicate_updated'
                                duplicate_reason = {
                                    "reason": f"{self.site_type} (priority {current_priority}) > {existing_site_type} (priority {existing_priority})",
                                    "current_priority": current_priority,
                                    "existing_priority": existing_priority,
                                    "updated": True
                                }
                                logger.info(
                                    f"✓ 우선순위 높음: {self.site_type}({current_priority}) > "
                                    f"{existing_site_type}({existing_priority}) → 업데이트됨"
                                )
                            elif current_priority == existing_priority:
                                # 같은 우선순위 → 업데이트됨 (최신 데이터 우선)
                                processing_status = 'duplicate_updated'
                                duplicate_reason = {
                                    "reason": f"{self.site_type} (priority {current_priority}) == {existing_site_type} (priority {existing_priority}), 최신 데이터 우선",
                                    "current_priority": current_priority,
                                    "existing_priority": existing_priority,
                                    "updated": True
                                }
                                logger.info(
                                    f"✓ 우선순위 동일: {self.site_type}({current_priority}) == "
                                    f"{existing_site_type}({existing_priority}) → 업데이트됨 (최신 데이터)"
                                )
                            else:
                                # 현재가 더 낮은 우선순위 → 기존 유지
                                processing_status = 'duplicate_preserved'
                                duplicate_reason = {
                                    "reason": f"{self.site_type} (priority {current_priority}) < {existing_site_type} (priority {existing_priority})",
                                    "current_priority": current_priority,
                                    "existing_priority": existing_priority,
                                    "updated": False
                                }
                                logger.info(
                                    f"⚠️  우선순위 낮음: {self.site_type}({current_priority}) < "
                                    f"{existing_site_type}({existing_priority}) → 기존 데이터 유지"
                                )
                        else:
                            # UPSERT 전 조회 실패 → 업데이트됨으로 간주
                            processing_status = 'duplicate_updated'
                            duplicate_reason = {"reason": "UPSERT 전 기존 레코드 조회 실패, 업데이트됨으로 간주"}
                            logger.warning("UPSERT 전 기존 레코드 조회 실패, 업데이트됨으로 간주")

                    else:
                        # 예상치 못한 경우
                        processing_status = 'failed'
                        duplicate_reason = {"reason": f"Unexpected affected_rows: {affected_rows}"}
                        logger.warning(f"예상치 못한 affected_rows: {affected_rows}")

                    # 로그 기록
                    if processing_status:
                        # ================================================
                        # 🆕 api_url_processing_log 기록 (삭제 예정)
                        # ================================================
                        self._log_api_url_processing(
                            session=session,
                            site_code=db_site_code,  # ← site_code → db_site_code (일관성)
                            url_key=url_key,
                            url_key_hash=url_key_hash,
                            processing_status=processing_status,
                            announcement_url=origin_url,
                            scraping_url=scraping_url,
                            preprocessing_id=record_id,
                            existing_preprocessing_id=existing_preprocessing_id,
                            existing_site_type=existing_site_type,
                            existing_site_code=existing_site_code,
                            duplicate_reason=duplicate_reason,
                            title=title,
                            folder_name=folder_name
                        )

                        # ================================================
                        # 🆕 announcement_duplicate_log 기록 (신규)
                        # ================================================
                        # ⚠️ 중요: processing_status는 "중복 체크 결과"를 나타내는 내부 변수
                        #          announcement_pre_processing.processing_status 컬럼과는 다름!
                        # processing_status 값:
                        #   - 'new_inserted': affected_rows=1 (신규 INSERT)
                        #   - 'duplicate_updated': affected_rows=2 (UPDATE됨)
                        #   - 'duplicate_preserved': affected_rows=2 + 우선순위 낮음
                        #   - 'failed': affected_rows 예상치 못한 값

                        # duplicate_type 매핑
                        duplicate_type_map = {
                            'new_inserted': 'new_inserted',
                            'duplicate_updated': 'replaced',  # 기본값 (우선순위 비교로 세부화)
                            'duplicate_preserved': 'kept_existing',
                            'failed': 'error'
                        }

                        # duplicate_type 결정
                        announcement_duplicate_type = duplicate_type_map.get(processing_status, 'unknown')  # 기본값을 'unknown'으로 변경

                        # duplicate_updated의 경우 우선순위 비교로 세부 타입 결정
                        if processing_status == 'duplicate_updated' and existing_record_before_upsert:
                            current_priority = self._get_priority(self.site_type)
                            existing_priority_value = self._get_priority(existing_record_before_upsert.site_type)

                            if current_priority == existing_priority_value:
                                # 우선순위 동일 → same_type_duplicate
                                announcement_duplicate_type = 'same_type_duplicate'
                            elif current_priority > existing_priority_value:
                                # 우선순위 높음 → replaced
                                announcement_duplicate_type = 'replaced'
                            # current_priority < existing_priority_value는 이론적으로 발생하지 않음 (UPSERT 조건상)

                        # existing_record dict 준비
                        existing_record_dict = None
                        if existing_record_before_upsert:
                            existing_record_dict = {
                                'id': existing_record_before_upsert.id,
                                'site_type': existing_record_before_upsert.site_type,
                                'site_code': existing_record_before_upsert.site_code,
                                'folder_name': existing_record_before_upsert.folder_name,
                                'url_key': url_key  # url_key는 동일
                            }

                        # announcement_duplicate_log 기록
                        self._log_announcement_duplicate(
                            session=session,
                            preprocessing_id=record_id,
                            url_key_hash=url_key_hash,
                            duplicate_type=announcement_duplicate_type,
                            site_code=db_site_code,
                            folder_name=folder_name,
                            domain=domain,
                            domain_configured=True,  # url_key가 있으므로 domain_key_config 있음
                            existing_record=existing_record_dict,
                            error_message=None
                        )

                # API 사이트인 경우 api_url_registry 테이블 업데이트 (commit 전에 실행)
                api_registry_updated = False
                if origin_url:
                    api_registry_updated = self._update_api_url_registry(
                        session, origin_url, record_id, db_site_code, scraping_url,
                        url_key_hash=url_key_hash  # 🆕 url_key_hash 추가
                    )

                    # API 사이트인데 api_url_registry 업데이트 실패 시 경고
                    if not api_registry_updated and db_site_code in ["kStartUp", "bizInfo", "smes24"]:
                        logger.warning(
                            f"⚠️  API 사이트이지만 api_url_registry 업데이트 실패: "
                            f"site_code={db_site_code}, origin_url={origin_url[:80]}..."
                        )

                # 모든 변경사항을 한 번에 커밋
                session.commit()
                logger.info(f"처리 결과 저장 완료: ID {record_id}, 상태: {status}")

                return record_id

        except Exception as e:
            logger.error(f"처리 결과 저장 실패: {e}")
            return None


def determine_site_type(directory_name: str, site_code: str) -> str:
    """디렉토리명과 사이트 코드에서 site_type을 결정합니다."""
    # 절대 경로 정규화 (대소문자 구분 없이)
    dir_lower = directory_name.lower()

    # 특수 API 사이트 체크
    if site_code in ["kStartUp", "bizInfo", "smes24"]:
        return "api_scrap"

    # 프로덕션 환경 경로 체크 (/home/zium/moabojo/incremental/*)
    if "/incremental/api" in dir_lower or "\\incremental\\api" in dir_lower:
        return "api_scrap"
    elif "/incremental/eminwon" in dir_lower or "\\incremental\\eminwon" in dir_lower:
        return "Eminwon"
    elif "/incremental/homepage" in dir_lower or "\\incremental\\homepage" in dir_lower:
        return "Homepage"
    elif "/incremental/btp" in dir_lower or "\\incremental\\btp" in dir_lower:
        return "Scraper"

    # 기존 개발 환경 경로 체크 (하위 호환성)
    elif "scraped" in dir_lower:
        return "Homepage"
    elif "eminwon" in dir_lower:
        return "Eminwon"
    elif "data_dir" in dir_lower:
        return "Scraper"

    else:
        return "Unknown"


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="공고 사전 처리 프로그램",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python announcement_pre_processor.py -d scraped_data --site-code site001
  python announcement_pre_processor.py -d eminwon_data --site-code emw001
  python announcement_pre_processor.py -d scraped_data --site-code site001 --force
  python announcement_pre_processor.py -d eminwon_data --site-code emw001 --attach-force
        """,
    )

    parser.add_argument(
        "-d", "--directory", type=str, required=True, help="데이터 디렉토리명 (필수)"
    )

    parser.add_argument(
        "--site-code", type=str, required=True, help="사이트 코드 (필수)"
    )

    parser.add_argument(
        "--force", action="store_true", help="이미 처리된 항목도 다시 처리"
    )

    parser.add_argument(
        "--attach-force",
        action="store_true",
        help="첨부파일 강제 재처리 (기존 .md 파일 무시하고 원본 파일에서 다시 변환)",
    )

    args = parser.parse_args()

    try:
        # 기본 디렉토리 결정
        current_dir = Path.cwd()
        base_directory = current_dir / args.directory

        if not base_directory.exists():
            logger.error(f"디렉토리가 존재하지 않습니다: {base_directory}")
            sys.exit(1)

        # site_type 결정 (절대 경로 사용)
        site_type = determine_site_type(str(base_directory), args.site_code)

        # Unknown site_type 검증
        if site_type == "Unknown":
            logger.error(
                f"\n{'='*60}\n"
                f"❌ site_type을 결정할 수 없습니다.\n"
                f"{'='*60}\n"
                f"입력 정보:\n"
                f"  - directory: {args.directory}\n"
                f"  - site_code: {args.site_code}\n"
                f"\n"
                f"지원되는 디렉토리 패턴:\n"
                f"  프로덕션:\n"
                f"    - /incremental/api → api_scrap\n"
                f"    - /incremental/eminwon → Eminwon\n"
                f"    - /incremental/homepage → Homepage\n"
                f"    - /incremental/btp → Scraper\n"
                f"\n"
                f"  개발 환경:\n"
                f"    - 'scraped' 포함 → Homepage\n"
                f"    - 'eminwon' 포함 → Eminwon\n"
                f"    - 'data_dir' 포함 → Scraper\n"
                f"\n"
                f"  특수 사이트:\n"
                f"    - site_code: kStartUp, bizInfo, smes24 → api_scrap\n"
                f"{'='*60}\n"
            )
            sys.exit(1)

        logger.info(f"기본 디렉토리: {base_directory}")
        logger.info(f"Site Type: {site_type}")
        logger.info(f"Site Code: {args.site_code}")

        # 프로세서 초기화
        logger.info("공고 사전 처리 프로그램 시작")

        processor = AnnouncementPreProcessor(
            site_type=site_type,
            attach_force=args.attach_force,
            site_code=args.site_code,
            lazy_init=False,
        )

        # 사이트 디렉토리 처리 실행
        results = processor.process_site_directories(
            base_directory, args.site_code, args.force
        )

        # 결과 출력
        print(f"\n=== 최종 요약 ===")
        print(f"전체 대상: {results['total']}개")
        print(f"처리 성공: {results['success']}개")
        print(f"처리 실패: {results['failed']}개")
        print(f"건너뛴 항목: {results['skipped']}개")

        if results["failed"] > 0:
            print(
                f"\n실패한 항목이 {results['failed']}개 있습니다. 로그를 확인해주세요."
            )
            sys.exit(1)
        else:
            print("\n모든 처리가 완료되었습니다!")
            sys.exit(0)

    except KeyboardInterrupt:
        logger.info("사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
