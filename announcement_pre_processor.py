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

logger = setup_logging(__name__)

config = ConfigManager().get_config()


class AnnouncementPreProcessor:
    """공고 사전 처리 메인 클래스"""

    def __init__(self, site_type: str, attach_force: bool = False, site_code: str = None, lazy_init: bool = False):
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
                            announcement_date VARCHAR(50),
                            processing_status VARCHAR(50),
                            error_message TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_site_code (site_code),
                            INDEX idx_processing_status (processing_status),
                            INDEX idx_origin_url (origin_url)
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

        # bizInfo, sme, kStartUp은 플랫 구조 (직접 하위 디렉토리만 검색)
        if site_code in ["bizInfo", "sme", "kStartUp"]:
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
            title = "정보 없음"
            origin_url = "정보 없음"
            announcement_date = "정보 없음"

            if site_code in ["kStartUp", "bizInfo", "sme"]:
                # kStartUp, bizInfo, sme는 content.md를 읽고, JSON에서 날짜 정보만 보완
                content_md_path = directory_path / "content.md"
                if content_md_path.exists():
                    try:
                        with open(content_md_path, "r", encoding="utf-8") as f:
                            content_md = f.read()
                        logger.info(f"content.md 읽기 완료: {len(content_md)} 문자")

                        # content.md에서 기본 정보 추출
                        title = self._extract_title_from_content(content_md) or "정보 없음"
                        origin_url = self._extract_origin_url_from_content(content_md) or "정보 없음"

                        # JSON 파일에서 announcement_date 보완
                        json_files = list(directory_path.glob("*.json"))
                        if json_files:
                            try:
                                with open(json_files[0], "r", encoding="utf-8") as f:
                                    json_data = json.load(f)
                                announcement_date_raw = json_data.get("announcementDate", "")
                                if announcement_date_raw:
                                    announcement_date = self._convert_to_yyyymmdd(announcement_date_raw)
                                else:
                                    # JSON에 없으면 content.md에서 추출
                                    announcement_date = self._extract_announcement_date_from_content(content_md) or "정보 없음"
                            except Exception as e:
                                logger.warning(f"{site_code} JSON 날짜 추출 실패, content.md 사용: {e}")
                                announcement_date = self._extract_announcement_date_from_content(content_md) or "정보 없음"
                        else:
                            # JSON 파일이 없으면 content.md에서 추출
                            announcement_date = self._extract_announcement_date_from_content(content_md) or "정보 없음"

                    except Exception as e:
                        logger.error(f"content.md 읽기 실패: {e}")
                        return self._save_processing_result(
                            folder_name,
                            site_code,
                            content_md,
                            "",
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
                    except Exception as e:
                        logger.error(f"content.md 읽기 실패: {e}")
                        return self._save_processing_result(
                            folder_name,
                            site_code,
                            content_md,
                            "",
                            status="error",
                            error_message=f"content.md 읽기 실패: {e}",
                        )
                else:
                    logger.warning(f"content.md 파일이 없음: {content_md_path}")

            # 3. content.md만으로 기본 검증
            if not content_md.strip():
                logger.warning("content.md 내용이 없음")
                return self._save_processing_result(
                    folder_name,
                    site_code,
                    content_md,
                    "",
                    attachment_filenames=[],
                    status="error",
                    error_message="content.md 내용이 없음",
                )

            # 일반 사이트의 경우만 content.md에서 정보 추출 (API 사이트는 이미 추출함)
            if site_code not in ["kStartUp", "bizInfo", "sme"]:
                title = self._extract_title_from_content(content_md) or "정보 없음"
                origin_url = self._extract_origin_url_from_content(content_md) or "정보 없음"
                announcement_date = self._extract_announcement_date_from_content(content_md) or "정보 없음"

            # 3.5. origin_url 중복 체크
            is_duplicate_url = False
            if origin_url and origin_url != "정보 없음":
                is_duplicate_url = self._check_origin_url_exists(origin_url, site_code)

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
                    exclusion_keywords=excluded_keywords,
                    exclusion_reason=exclusion_msg,
                )

            # 6. 데이터베이스에 저장 (중복 URL 여부에 따라 상태 결정)
            final_status = "중복" if is_duplicate_url else "성공"

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
                status=final_status,
                force=force,
            )

            if is_duplicate_url:
                logger.info(f"origin_url 중복으로 '중복' 상태로 저장: {folder_name}")

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
                    date_str = re.sub(r'\*+', '', date_str).strip()
                    # 추가적인 정리 (공백 제거 등)
                    date_str = date_str.strip()

                    # 날짜 형식 검증 (최소한 연도가 포함되어야 함)
                    if re.search(r'\d{4}', date_str):
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
            attachments_section = re.search(
                r"\*\*첨부파일\*\*:\s*\n+(.*?)(?=\n\*\*|$)",
                content,
                re.DOTALL | re.MULTILINE,
            )

            if attachments_section:
                attachments_text = attachments_section.group(1)

                # 모든 줄을 처리하여 번호. 파일명:URL 패턴 찾기
                lines = attachments_text.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # 번호. 파일명:URL 패턴
                    match = re.match(r"^\d+\.\s*(.+?):(https?://[^\s]+)", line)
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
        normal_files = []    # 일반 파일들
        
        # 모든 파일을 먼저 검사하여 분류
        for file_path in attachments_dir.iterdir():
            if file_path.is_file():
                file_extension = file_path.suffix.lower()
                filename = file_path.stem
                lowercase_filename = filename.lower()
                
                # 지원하는 확장자만 처리
                if file_extension and file_extension in supported_extensions:
                    # 양식, 서류 등 제외 키워드 체크
                    if any(keyword in lowercase_filename for keyword in target_keywords):
                        continue
                    
                    # 지원/공고 키워드가 있는지 확인
                    if "지원" in lowercase_filename or "공고" in lowercase_filename:
                        priority_files.append(file_path)
                        logger.info(f"우선순위 파일 발견 (지원/공고 키워드): {file_path.name}")
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
                "file_size": (
                    file_path.stat().st_size if file_path.exists() else 0
                ),
                "conversion_success": False,
                "conversion_method": self._guess_conversion_method(
                    file_extension
                ),
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
                        logger.warning(
                            f"첨부파일 .md 내용이 비어있음: {filename}.md"
                        )
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
                        logger.warning(f"AttachmentProcessor를 사용할 수 없어 파일 건너뜀: {file_path.name}")
                        continue
                        
                    content = self.attachment_processor.process_single_file(
                        file_path
                    )

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
                            logger.debug(
                                f"변환된 내용을 .md로 저장: {md_file_path}"
                            )
                        except Exception as save_e:
                            logger.warning(f".md 파일 저장 실패: {save_e}")
                    else:
                        logger.warning(
                            f"첨부파일에서 내용 추출 실패: {file_path.name}"
                        )

                except Exception as e:
                    error_msg = str(e)
                    if "Invalid code point" in error_msg or "PDFSyntaxError" in error_msg or "No /Root object" in error_msg:
                        logger.warning(f"손상된 PDF 파일 건너뛰기: {file_path.name}")
                    elif "UnicodeDecodeError" in error_msg:
                        logger.warning(f"인코딩 문제로 파일 건너뛰기: {file_path.name}")
                    else:
                        logger.error(f"첨부파일 변환 실패 ({file_path.name}): {e}")

                    # 변환 실패한 파일 정보 기록
                    file_info["conversion_success"] = False
                    file_info["error_message"] = error_msg[:200]  # 오류 메시지 일부만 저장

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
                    return dt.strftime("%Y%m%d")
                except ValueError:
                    continue

            # 모든 포맷 실패시 원본 반환
            logger.warning(f"날짜 변환 실패, 원본 반환: {date_str}")
            return date_str

        except Exception as e:
            logger.error(f"날짜 변환 중 오류: {e}")
            return date_str

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
        announcement_date: str = None,
        attachment_files_info: List[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """처리 결과를 데이터베이스에 저장합니다."""
        try:
            from sqlalchemy import text

            with self.db_manager.SessionLocal() as session:
                if force:
                    # UPSERT 로직
                    sql = text(
                        """
                        INSERT INTO announcement_pre_processing (
                            folder_name, site_type, site_code, content_md, combined_content,
                            attachment_filenames, attachment_files_list, exclusion_keyword, exclusion_reason, 
                            title, origin_url, announcement_date,
                            processing_status, error_message, created_at, updated_at
                        ) VALUES (
                            :folder_name, :site_type, :site_code, :content_md, :combined_content,
                            :attachment_filenames, :attachment_files_list, :exclusion_keyword, :exclusion_reason, 
                            :title, :origin_url, :announcement_date,
                            :processing_status, :error_message, NOW(), NOW()
                        )
                        ON DUPLICATE KEY UPDATE
                            site_type = VALUES(site_type),
                            content_md = VALUES(content_md),
                            combined_content = VALUES(combined_content),
                            attachment_filenames = VALUES(attachment_filenames),
                            attachment_files_list = VALUES(attachment_files_list),
                            exclusion_keyword = VALUES(exclusion_keyword),
                            exclusion_reason = VALUES(exclusion_reason),
                            processing_status = VALUES(processing_status),
                            title = VALUES(title),
                            origin_url = VALUES(origin_url),
                            announcement_date = VALUES(announcement_date),
                            error_message = VALUES(error_message),
                            updated_at = NOW()
                    """
                    )
                else:
                    # 일반 INSERT
                    sql = text(
                        """
                        INSERT INTO announcement_pre_processing (
                            folder_name, site_type, site_code, content_md, combined_content,
                            attachment_filenames, attachment_files_list, exclusion_keyword, exclusion_reason, 
                            title, origin_url, announcement_date,
                            processing_status, error_message, created_at, updated_at
                        ) VALUES (
                            :folder_name, :site_type, :site_code, :content_md, :combined_content,
                            :attachment_filenames, :attachment_files_list, :exclusion_keyword, :exclusion_reason, 
                            :title, :origin_url, :announcement_date,
                            :processing_status, :error_message, NOW(), NOW()
                        )
                    """
                    )

                # JSON으로 직렬화
                attachment_files_json = (
                    json.dumps(attachment_files_info, ensure_ascii=False)
                    if attachment_files_info
                    else None
                )

                params = {
                    "folder_name": folder_name,
                    "site_type": self.site_type,
                    "site_code": site_code,
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
                    "announcement_date": announcement_date,
                    "processing_status": status,
                    "error_message": error_message,
                }

                result = session.execute(sql, params)
                session.commit()

                record_id = result.lastrowid
                logger.info(f"처리 결과 저장 완료: ID {record_id}, 상태: {status}")
                return record_id

        except Exception as e:
            logger.error(f"처리 결과 저장 실패: {e}")
            return None


def determine_site_type(directory_name: str, site_code: str) -> str:
    """디렉토리명과 사이트 코드에서 site_type을 결정합니다."""
    # 특수 API 사이트 체크
    if site_code in ["kStartUp", "bizInfo", "sme"]:
        return "api_scrap"
    elif "scraped" in directory_name.lower():
        return "Homepage"
    elif "eminwon" in directory_name.lower():
        return "Eminwon"
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

        # site_type 결정
        site_type = determine_site_type(args.directory, args.site_code)

        logger.info(f"기본 디렉토리: {base_directory}")
        logger.info(f"Site Type: {site_type}")
        logger.info(f"Site Code: {args.site_code}")

        # 프로세서 초기화
        logger.info("공고 사전 처리 프로그램 시작")

        processor = AnnouncementPreProcessor(
            site_type=site_type,
            attach_force=args.attach_force,
            site_code=args.site_code,
            lazy_init=False
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
