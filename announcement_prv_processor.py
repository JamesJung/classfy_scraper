#!/usr/bin/env python3
"""
공고 처리 메인 프로그램

사용법:
    python announcement_prv_processor.py [디렉토리명] [사이트코드]
    
예시:
    python announcement_prv_processor.py data.origin cbt
    python announcement_prv_processor.py  # 환경변수 사용
"""

import argparse
import json
import os
import sys
import time
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.config import ConfigManager
from src.config.logConfig import setup_logging
from src.utils.attachmentProcessor import AttachmentProcessor
from src.utils.ollamaClient import AnnouncementPrvAnalyzer
from src.models.announcementPrvDatabase import AnnouncementPrvDatabaseManager, create_announcement_prv_tables
from src.utils.announcementFilter import AnnouncementFilter

logger = setup_logging(__name__)
config = ConfigManager().get_config()


class AnnouncementPrvProcessor:
    """공고 처리 메인 클래스"""
    
    def __init__(self, attach_force: bool = False):
        self.attachment_processor = AttachmentProcessor()
        self.announcement_analyzer = AnnouncementPrvAnalyzer()
        self.db_manager = AnnouncementPrvDatabaseManager()
        self.filter = AnnouncementFilter()
        self.attach_force = attach_force
        
        # 데이터베이스 테이블 생성 (없는 경우)
        self._ensure_database_tables()
        
        # 제외 키워드 로드
        self.exclusion_keywords = self._load_exclusion_keywords()
    
    def _ensure_database_tables(self):
        """데이터베이스 테이블이 존재하는지 확인하고 생성합니다."""
        try:
            if self.db_manager.test_connection():
                self.db_manager.create_tables()
                logger.info("데이터베이스 테이블 확인/생성 완료")
            else:
                logger.warning("데이터베이스 연결 실패 - 계속 진행합니다 (DB 저장 불가)")
        except Exception as e:
            logger.warning(f"데이터베이스 초기화 실패: {e} - 계속 진행합니다 (DB 저장 불가)")
    
    def _load_exclusion_keywords(self) -> List[Dict[str, Any]]:
        """데이터베이스에서 제외 키워드를 로드합니다."""
        try:
            from sqlalchemy import text
            
            with self.db_manager.SessionLocal() as session:
                result = session.execute(text("""
                    SELECT EXCLUSION_ID, KEYWORD, DESCRIPTION
                    FROM EXCLUSION_KEYWORDS
                    WHERE IS_ACTIVE = TRUE
                    ORDER BY EXCLUSION_ID
                """))
                
                keywords = []
                for row in result:
                    keywords.append({
                        'id': row[0],
                        'keyword': row[1],
                        'description': row[2]
                    })
                
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
        return self.process_directory_with_custom_name(directory_path, site_code, folder_name)
    
    def _collect_attachment_info(self, directory_path: Path) -> List[Dict[str, Any]]:
        """첨부파일 정보를 수집합니다."""
        attachment_info = []
        attachments_dir = directory_path / "attachments"
        
        if not attachments_dir.exists():
            return attachment_info
        
        try:
            # 첨부파일 처리 결과 가져오기
            # attachment_results = self.attachment_processor.process_directory_attachments(directory_path)
            
            # 실제 파일들과 매칭
            for file_path in attachments_dir.iterdir():
                if file_path.is_file():
                    filename = file_path.stem
                    file_extension = file_path.suffix
                    
                    # 파일 크기 가져오기
                    try:
                        file_size = file_path.stat().st_size
                    except:
                        file_size = 0
                    
                    # 변환 결과 찾기
                    # converted_content = attachment_results.get(filename, "")
                    # conversion_success = bool(converted_content)
                    
                    # 변환 방법 추정
                    # conversion_method = self._guess_conversion_method(file_extension)
                    
                    attachment_info.append({
                        "filename": filename,
                        "file_extension": file_extension,
                        "file_path": str(file_path),
                        "file_size": file_size,
                        # "converted_content": converted_content,
                        # "conversion_method": conversion_method,
                        # "conversion_success": conversion_success
                    })
            
            logger.info(f"첨부파일 정보 수집 완료: {len(attachment_info)}개")
            
        except Exception as e:
            logger.error(f"첨부파일 정보 수집 중 오류: {e}")
        
        return attachment_info
    
    def _guess_conversion_method(self, file_extension: str) -> str:
        """파일 확장자에 따른 변환 방법을 추정합니다."""
        ext_lower = file_extension.lower()
        
        if ext_lower == '.pdf':
            return 'pdf_docling'
        elif ext_lower in ['.hwp', '.hwpx']:
            return 'hwp_markdown'
        elif ext_lower in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
            return 'ocr'
        else:
            return 'unknown'
    
    def _find_target_directories(self, base_dir: Path, site_code: str, recursive: bool = False, force: bool = False) -> List[Path]:
        """
        처리할 대상 디렉토리들을 찾습니다.
        
        Args:
            base_dir: 기본 디렉토리
            site_code: 사이트 코드
            recursive: 재귀적 검색 여부
            force: 이미 처리된 항목도 다시 처리할지 여부
            
        Returns:
            처리 대상 디렉토리 목록
        """
        site_dir = base_dir / site_code
        
        if not site_dir.exists():
            logger.error(f"사이트 디렉토리가 없음: {site_dir}")
            return []
        
        target_directories = []
        
        if recursive:
            # 재귀적으로 모든 하위 디렉토리에서 content.md 또는 attachments 폴더가 있는 디렉토리 찾기
            logger.info(f"재귀적 디렉토리 검색 시작: {site_dir}")
            
            for root_path in site_dir.rglob("*"):
                if root_path.is_dir():
                    # content.md 파일이 있거나 attachments 폴더가 있는 디렉토리만 대상으로 함
                    has_content_md = (root_path / "content.md").exists()
                    has_attachments = (root_path / "attachments").exists() and any((root_path / "attachments").iterdir())
                    
                    if has_content_md or has_attachments:
                        target_directories.append(root_path)
                        logger.debug(f"대상 디렉토리 발견: {root_path.relative_to(site_dir)}")
        else:
            # 기본 동작: 사이트 디렉토리의 직접 하위 디렉토리만 검색하고 폴더명으로 정렬
            all_directories = [d for d in site_dir.iterdir() if d.is_dir()]
            target_directories = sorted(all_directories, key=self._natural_sort_key)
        
        logger.info(f"발견된 전체 디렉토리: {len(target_directories)}개")
        
        # 처음 몇 개 폴더명 로깅
        if target_directories:
            logger.info(f"첫 5개 폴더: {[d.name for d in target_directories[:5]]}")
        
        # force 옵션이 없을 때만 이미 처리된 폴더 제외 (DB에서 prv로 저장된 데이터 조회)
        if not force:
            processed_folders = set(self.db_manager.get_processed_folders("prv"))
            
            filtered_directories = []
            for directory in target_directories:
                # 사이트 디렉토리로부터의 상대 경로를 폴더명으로 사용
                relative_path = directory.relative_to(site_dir)
                folder_name = self._normalize_korean_text(str(relative_path).replace("/", "_"))  # 슬래시를 언더스코어로 변경
                
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
            logger.info(f"--force 옵션: 모든 디렉토리 처리 ({len(target_directories)}개)")
            return target_directories
    
    def _find_prv_target_directories(self, city_dir: Path, recursive: bool = False, force: bool = False) -> List[Path]:
        """
        PRV의 특정 시군 디렉토리에서 처리할 대상 디렉토리들을 찾습니다.
        
        Args:
            city_dir: 시군 디렉토리 경로 (예: prv1/경기도/가평군)
            recursive: 재귀적 검색 여부
            force: 이미 처리된 항목도 다시 처리할지 여부
            
        Returns:
            처리 대상 디렉토리 목록
        """
        if not city_dir.exists():
            logger.error(f"시군 디렉토리가 없음: {city_dir}")
            return []
        
        target_directories = []
        
        if recursive:
            # 재귀적으로 모든 하위 디렉토리에서 content.md 또는 attachments 폴더가 있는 디렉토리 찾기
            logger.info(f"재귀적 디렉토리 검색 시작: {city_dir}")
            
            for root_path in city_dir.rglob("*"):
                if root_path.is_dir():
                    # content.md 파일이 있거나 attachments 폴더가 있는 디렉토리만 대상으로 함
                    has_content_md = (root_path / "content.md").exists()
                    has_attachments = (root_path / "attachments").exists() and any((root_path / "attachments").iterdir())
                    
                    if has_content_md or has_attachments:
                        target_directories.append(root_path)
                        logger.debug(f"대상 디렉토리 발견: {root_path.relative_to(city_dir)}")
        else:
            # 기본 동작: 시군 디렉토리의 직접 하위 디렉토리만 검색하고 폴더명으로 정렬
            all_directories = [d for d in city_dir.iterdir() if d.is_dir()]
            target_directories = sorted(all_directories, key=self._natural_sort_key)
        
        logger.info(f"시군 {city_dir.name}에서 발견된 공고 디렉토리: {len(target_directories)}개")
        
        # 처음 몇 개 폴더명 로깅
        if target_directories:
            logger.debug(f"첫 5개 공고 폴더: {[d.name for d in target_directories[:5]]}")
        
        # force 옵션이 없을 때만 이미 처리된 폴더 제외 (DB에서 prv로 저장된 데이터 조회)
        if not force:
            processed_folders = set(self.db_manager.get_processed_folders("prv"))
            
            filtered_directories = []
            for directory in target_directories:
                # 시군 경로를 포함한 폴더명 생성 (DB 저장 시와 동일한 방식)
                city_path_from_base = str(city_dir).split('/')[-2:] # 지역/시군 추출
                city_path = '/'.join(city_path_from_base)
                relative_path = directory.relative_to(city_dir)
                folder_name = self._normalize_korean_text(f"{city_path.replace('/', '_')}_{str(relative_path).replace('/', '_')}")
                
                if folder_name not in processed_folders:
                    filtered_directories.append(directory)
                else:
                    logger.debug(f"이미 처리된 폴더 건너뜀: {folder_name}")
            
            logger.info(f"시군 {city_dir.name} - 전체 발견: {len(target_directories)}개, 처리 대상: {len(filtered_directories)}개")
            
            return filtered_directories
        else:
            # force 옵션이 있으면 모든 디렉토리 반환
            logger.info(f"--force 옵션: 시군 {city_dir.name}의 모든 디렉토리 처리 ({len(target_directories)}개)")
            return target_directories
    
    def process_all_sites(self, base_dir: Path, recursive: bool = False, force: bool = False, attach_force: bool = False) -> Dict[str, int]:
        """
        base_dir 내의 모든 사이트 디렉토리를 처리합니다.
        
        Args:
            base_dir: 기본 디렉토리 (여러 사이트 디렉토리를 포함)
            recursive: 재귀적 처리 여부
            force: 이미 처리된 항목도 다시 처리할지 여부
            attach_force: 첨부파일 강제 재처리 여부
            
        Returns:
            전체 처리 결과 통계
        """
        if not base_dir.exists():
            logger.error(f"기본 디렉토리가 없음: {base_dir}")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        
        # base_dir 내의 모든 사이트 디렉토리 찾기
        site_directories = [d for d in base_dir.iterdir() if d.is_dir()]

        if not site_directories:
            logger.warning("처리할 사이트 디렉토리가 없습니다.")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        
        # 전체 결과 통계
        total_results = {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        
        print(f"\n{'='*80}")
        print(f"다중 사이트 공고 처리 시작: {len(site_directories)}개 사이트")
        print(f"발견된 사이트: {[d.name for d in site_directories]}")
        print(f"{'='*80}")
        
        # 전체 시작 시간 기록
        overall_start_time = time.time()
        
        # PRV는 2depth 구조: 지역/시군/공고 
        for region_idx, region_dir in enumerate(site_directories, 1):
            region_name = region_dir.name
            
            print(f"\n🌍 [{region_idx}/{len(site_directories)}] 지역 처리 시작: {region_name}")
            print(f"{'─'*60}")
            
            # 각 지역의 시군 디렉토리들 찾기
            city_directories = [d for d in region_dir.iterdir() if d.is_dir()]
            
            if not city_directories:
                print(f"   ⚠️ {region_name}에 시군 디렉토리가 없습니다.")
                continue
                
            region_start_time = time.time()
            region_results = {"total": 0, "success": 0, "failed": 0, "skipped": 0}
            
            for city_idx, city_dir in enumerate(city_directories, 1):
                city_name = city_dir.name
                site_code = "prv"  # PRV 프로세서는 site_code를 "prv"로 고정
                
                print(f"\n🏘️  [{city_idx}/{len(city_directories)}] 시군 처리: {region_name}/{city_name} (DB저장: {site_code})")
                
                city_start_time = time.time()
                
                # 개별 시군 처리 - 2depth 경로 전달
                city_path = f"{region_name}/{city_name}"
                city_results = self.process_prv_city_directories(base_dir, city_path, recursive, force, attach_force)
                
                # 시군별 결과를 지역 결과에 합산
                region_results["total"] += city_results["total"]
                region_results["success"] += city_results["success"]
                region_results["failed"] += city_results["failed"]
                region_results["skipped"] += city_results["skipped"]
                
                city_elapsed = time.time() - city_start_time
                
                print(f"     ✅ {city_name} 완료: 성공 {city_results['success']}, 실패 {city_results['failed']}, 건너뛴 {city_results['skipped']} ({city_elapsed:.1f}초)")
            
            # 지역별 결과를 전체 결과에 합산
            total_results["total"] += region_results["total"]
            total_results["success"] += region_results["success"]
            total_results["failed"] += region_results["failed"]
            total_results["skipped"] += region_results["skipped"]
            
            region_elapsed = time.time() - region_start_time
            
            print(f"\n✅ 지역 '{region_name}' 처리 완료 ({region_elapsed:.1f}초)")
            print(f"   전체 성공: {region_results['success']}, 실패: {region_results['failed']}, 건너뛴: {region_results['skipped']}")
        
        # 전체 처리 시간 계산
        overall_elapsed = time.time() - overall_start_time
        
        print(f"\n{'='*80}")
        print(f"🎉 전체 사이트 처리 완료!")
        print(f"{'='*80}")
        print(f"처리한 사이트: {len(site_directories)}개")
        print(f"전체 대상: {total_results['total']}개")
        print(f"처리 성공: {total_results['success']}개 ({(total_results['success']/max(total_results['total'], 1))*100:.1f}%)")
        print(f"처리 실패: {total_results['failed']}개")
        print(f"건너뛴 항목: {total_results['skipped']}개")
        print(f"")
        print(f"📊 전체 처리 시간: {overall_elapsed:.1f}초 ({overall_elapsed/60:.1f}분)")
        if total_results['total'] > 0:
            avg_time = overall_elapsed / total_results['total']
            print(f"항목당 평균 시간: {avg_time:.1f}초")
        print(f"{'='*80}")
        
        return total_results
        
    def process_site_directories(self, base_dir: Path, site_code: str, recursive: bool = False, force: bool = False, attach_force: bool = False) -> Dict[str, int]:
        """
        특정 사이트의 모든 디렉토리를 처리합니다.
        
        Args:
            base_dir: 기본 디렉토리
            site_code: 실제 사이트 디렉토리명
            recursive: 재귀적 처리 여부
            force: 이미 처리된 항목도 다시 처리할지 여부
            attach_force: 첨부파일 강제 재처리 여부
            
        Returns:
            처리 결과 통계
        """
        # PRV 프로세서에서는 DB에 "prv"로 저장
        db_site_code = "prv"
        
        # 처리할 디렉토리 목록 찾기
        target_directories = self._find_target_directories(base_dir, site_code, recursive, force)
        
        if not target_directories:
            logger.warning("처리할 디렉토리가 없습니다.")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        
        total_count = len(target_directories)
        results = {"total": total_count, "success": 0, "failed": 0, "skipped": 0}
        site_dir = base_dir / site_code
        
        print(f"\n{'='*60}")
        print(f"공고 처리 시작: {site_code} (DB: {db_site_code}) ({total_count}개 폴더)")
        print(f"{'='*60}")
        
        # 시작 시간 기록
        start_time = time.time()
        
        for i, directory in enumerate(target_directories, 1):
            try:
                # 개별 항목 시작 시간
                item_start_time = time.time()
                
                # 사이트 디렉토리로부터의 상대 경로를 폴더명으로 사용
                relative_path = directory.relative_to(site_dir)
                folder_name = self._normalize_korean_text(str(relative_path).replace("/", "_"))  # 슬래시를 언더스코어로 변경
                
                progress_pct = (i / total_count) * 100
                print(f"\n[{i}/{total_count} : {progress_pct:.1f}%] {folder_name}")
                
                # 이미 처리된 항목 확인 (force 옵션이 없을 때만)
                if not force and self.db_manager.is_already_processed(folder_name, db_site_code):
                    skip_elapsed = time.time() - item_start_time
                    print(f"  ✓ 이미 처리됨, 건너뜀 ({skip_elapsed:.1f}초)")
                    results["skipped"] += 1
                    continue
                elif force and self.db_manager.is_already_processed(folder_name, db_site_code):
                    print("  🔄 이미 처리됨, --force 옵션으로 재처리")
                
                success = self.process_directory_with_custom_name(directory, db_site_code, folder_name, attach_force, force)
                
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
        processed_count = results['success'] + results['failed']  # 실제 처리한 개수 (건너뛴 것 제외)
        
        print(f"\n{'='*60}")
        print(f"처리 완료: {results['success']}/{total_count} 성공 ({(results['success']/total_count)*100:.1f}%)")
        print(f"건너뜀: {results['skipped']}, 실패: {results['failed']}")
        print(f"")
        print(f"📊 처리 시간 통계:")
        print(f"   총 소요 시간: {total_elapsed:.1f}초 ({total_elapsed/60:.1f}분)")
        
        if processed_count > 0:
            avg_time_per_item = total_elapsed / processed_count
            print(f"   처리한 항목당 평균 시간: {avg_time_per_item:.1f}초")
        
        if results['success'] > 0:
            avg_time_per_success = total_elapsed / results['success'] 
            print(f"   성공한 항목당 평균 시간: {avg_time_per_success:.1f}초")
        
        print(f"{'='*60}")
        
        logger.info(f"처리 완료 - 전체: {results['total']}, 성공: {results['success']}, 실패: {results['failed']}, 건너뜀: {results['skipped']}")
        
        return results
    
    def process_prv_city_directories(self, base_dir: Path, city_path: str, recursive: bool = False, force: bool = False, attach_force: bool = False) -> Dict[str, int]:
        """
        PRV 2depth 구조에서 특정 시군의 디렉토리들을 처리합니다.
        
        Args:
            base_dir: 기본 디렉토리 
            city_path: 시군 경로 (예: "경기도/가평군")
            recursive: 재귀적 처리 여부
            force: 이미 처리된 항목도 다시 처리할지 여부
            attach_force: 첨부파일 강제 재처리 여부
            
        Returns:
            처리 결과 통계
        """
        # PRV 프로세서에서는 DB에 "prv"로 저장
        db_site_code = "prv"
        
        # 실제 시군 디렉토리 경로
        city_dir = base_dir / city_path
        
        if not city_dir.exists():
            logger.warning(f"시군 디렉토리가 없음: {city_dir}")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        
        # 처리할 디렉토리 목록 찾기 (시군 디렉토리 내의 공고 폴더들)
        target_directories = self._find_prv_target_directories(city_dir, recursive, force)
        
        if not target_directories:
            logger.warning(f"처리할 공고 디렉토리가 없음: {city_dir}")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        
        total_count = len(target_directories)
        results = {"total": total_count, "success": 0, "failed": 0, "skipped": 0}
        
        for i, directory in enumerate(target_directories, 1):
            try:
                # 개별 항목 시작 시간
                item_start_time = time.time()
                
                # 시군 디렉토리로부터의 상대 경로를 폴더명으로 사용하되, 시군 경로도 포함
                relative_path = directory.relative_to(city_dir)
                folder_name = self._normalize_korean_text(f"{city_path.replace('/', '_')}_{str(relative_path).replace('/', '_')}")
                
                progress_pct = (i / total_count) * 100
                print(f"     [{i}/{total_count} : {progress_pct:.1f}%] {relative_path.name}")
                
                # 이미 처리된 항목 확인 (force 옵션이 없을 때만)
                if not force and self.db_manager.is_already_processed(folder_name, db_site_code):
                    skip_elapsed = time.time() - item_start_time
                    print(f"       ✓ 이미 처리됨, 건너뜀 ({skip_elapsed:.1f}초)")
                    results["skipped"] += 1
                    continue
                elif force and self.db_manager.is_already_processed(folder_name, db_site_code):
                    print("       🔄 이미 처리됨, --force 옵션으로 재처리")
                
                success = self.process_directory_with_custom_name(directory, db_site_code, folder_name, attach_force, force)
                
                # 개별 항목 처리 시간 계산
                item_elapsed = time.time() - item_start_time
                
                if success:
                    results["success"] += 1
                    print(f"       ✓ 처리 완료 ({item_elapsed:.1f}초)")
                else:
                    results["failed"] += 1
                    print(f"       ✗ 처리 실패 ({item_elapsed:.1f}초)")
                    
            except Exception as e:
                error_elapsed = time.time() - item_start_time
                results["failed"] += 1
                print(f"       ✗ 예외 발생: {str(e)[:50]}... ({error_elapsed:.1f}초)")
                logger.error(f"처리 중 오류 ({directory}): {e}")
        
        logger.info(f"시군 처리 완료 - 전체: {results['total']}, 성공: {results['success']}, 실패: {results['failed']}, 건너뜀: {results['skipped']}")
        
        return results
    
    def process_directory_with_custom_name(self, directory_path: Path, site_code: str, folder_name: str, attach_force: bool = False, force: bool = False) -> bool:
        """
        사용자 정의 폴더명으로 디렉토리를 처리합니다.
        
        Args:
            directory_path: 처리할 디렉토리 경로
            site_code: 사이트 코드
            folder_name: 데이터베이스에 저장할 폴더명
            attach_force: 첨부파일 강제 재처리 여부
            force: 이미 처리된 항목도 다시 처리할지 여부
            
        Returns:
            처리 성공 여부
        """
        logger.info(f"디렉토리 처리 시작: {folder_name}")
        
        try:
            # 0. 중복 처리 체크 (force 옵션이 없을 때만)
            if not force:
                if self.db_manager.is_already_processed(folder_name, site_code):
                    logger.info(f"이미 처리된 폴더 건너뜀: {folder_name}")
                    return True  # 성공으로 처리 (이미 처리됨)
            
            # 1. 제외 키워드 체크
            excluded_keywords = self._check_exclusion_keywords(folder_name)
            
            # 2. content.md 파일 읽기
            content_md_path = directory_path / "content.md"
            content_md = ""
            
            if content_md_path.exists():
                try:
                    with open(content_md_path, 'r', encoding='utf-8') as f:
                        content_md = f.read()
                    logger.info(f"content.md 읽기 완료: {len(content_md)} 문자")
                except Exception as e:
                    logger.error(f"content.md 읽기 실패: {e}")
                    return self._save_processing_result(
                        folder_name, site_code, content_md, "", 
                        status="ollama", error_message=f"content.md 읽기 실패: {e}"
                    )
            else:
                logger.warning(f"content.md 파일이 없음: {content_md_path}")
            
            # 3. content.md만으로 기본 검증
            if not content_md.strip():
                logger.warning("content.md 내용이 없음")
                return self._save_processing_result(
                    folder_name, site_code, content_md, "",
                    attachment_filenames=[],
                    status="ollama", error_message="content.md 내용이 없음"
                )
            
            # 4. 제외 키워드가 있는 경우 제외 처리
            if excluded_keywords:
                exclusion_msg = f"제외 키워드가 입력되어 있습니다: {', '.join(excluded_keywords)}"
                logger.info(f"제외 처리: {folder_name} - {exclusion_msg}")
                
                return self._save_processing_result(
                    folder_name, site_code, content_md, "",
                    attachment_filenames=[],
                    status="제외", exclusion_keywords=excluded_keywords,
                    exclusion_reason=exclusion_msg
                )
            
            # 5. 데이터베이스에 1차 저장 (content.md만으로 status: ollama)
            record_id = self._save_processing_result(
                folder_name, site_code, content_md, "", 
                attachment_filenames=[],
                status="ollama", force=True  # force 옵션은 항상 UPSERT로 처리
            )

            #2025.09.03 TEMP  나중에 이거 풀어야 함. 테스트를 위해  잠시              
            # if not record_id:
            #     logger.error("1차 저장 실패")
            #     return False
            
            # 5.5. 제목에서 "지원" 키워드 확인 (Ollama 분석 전 조기 반환)
            if content_md.strip():
                extracted_title = self._extract_title_from_content(content_md)
                logger.info(f"추출된 제목: {extracted_title}")
                
                if "지원" in extracted_title:
                    logger.info(f"제목에 '지원' 키워드 발견: {extracted_title}")
                    print(f"  ✅ 제목에 '지원' 키워드 발견: {extracted_title[:50]}...")
                    
                    # 바로 성공 처리하고 다음 공고로 이동
                    return self._update_processing_result_simple(
                        record_id, status="성공", error_message="제목에 지원이라는 글자 있음"
                    )
            
            # 6. content_md로 첫번째 ollama 분석
            print("  📋 1차 Ollama 분석 중 (content.md)...")
            first_response = None
            first_prompt = ""
            
            # IS_SUPPORT_PROGRAM 확인
            def is_support_program(response):
                if not response:
                    return False
                return response.get("IS_SUPPORT_PROGRAM", False) == True
            
            first_response, first_prompt = self._analyze_with_ollama(content_md)
            
            # 7. 1차 분석 결과에 따른 처리
            if not is_support_program(first_response):
                # IS_SUPPORT_PROGRAM=false면 완료 (첨부파일 처리 안함)
                logger.info("1차 분석 완료 - 지원사업이 아님 (IS_SUPPORT_PROGRAM=false)")
                return self._update_processing_result(
                    record_id, first_response, first_prompt, status="성공"
                )
            
            # 8. 지원사업인 경우 첨부파일 처리 시작
            logger.info("1차 분석 결과: 지원사업 확인됨 - 첨부파일 처리 시작")
            print("  📂 첨부파일 변환 중...")
            
            combined_content = ""
            attachment_filenames = []
            
            try:
                combined_content, attachment_filenames = self._process_attachments_separately(directory_path, attach_force)
                logger.info(f"첨부파일 내용 처리 완료: {len(combined_content)} 문자, 파일 {len(attachment_filenames)}개")
                
                # 첨부파일 정보를 데이터베이스에 업데이트
                self._update_attachment_info(record_id, combined_content, attachment_filenames)
                
            except Exception as e:
                logger.error(f"첨부파일 처리 실패: {e}")
                # 첨부파일 처리 실패해도 1차 분석 결과로 진행
                combined_content = ""
                attachment_filenames = []
            
            # 9. EXTRACTED_TARGET 확인 및 2차 분석 필요성 판단
            def has_valid_target(response):
                if not response:
                    return False
                target = response.get("EXTRACTED_TARGET", "")
                return target and target not in ["정보 없음", "해당없음", ""]
            
            if has_valid_target(first_response):
                # 성공: 1차 분석에서 이미 지원대상 정보가 있으면 완료
                logger.info("1차 분석에서 EXTRACTED_TARGET 추출됨 - 완료")
                return self._update_processing_result(
                    record_id, first_response, first_prompt, status="성공"
                )
            
            # 10. 2차 ollama 분석 (지원사업이지만 지원대상 정보가 부족한 경우)
            if combined_content.strip():
                print("  📋 2차 Ollama 분석 중 (첨부파일만)...")
                logger.info("2차 분석 시작 - 지원사업이지만 지원대상 정보 부족, 첨부파일만으로 재분석")
                
                # 첨부파일 내용만으로 2차 분석
                second_response, second_prompt = self._analyze_with_ollama(combined_content)
                
                # 최종 상태 결정 로직
                final_status = self._determine_final_status(first_response, second_response)
                
                return self._update_processing_result(
                    record_id, second_response, second_prompt, 
                    first_response=first_response, status=final_status
                )
            else:
                # 2차 분석이 필요하지만 첨부파일 내용이 없는 경우
                logger.info("2차 분석 필요하지만 첨부파일 내용 없음 - 1차 결과만 사용")
                final_status = self._determine_final_status(first_response, None)
                return self._update_processing_result(
                    record_id, first_response, first_prompt, status=final_status
                )
                
        except Exception as e:
            logger.error(f"디렉토리 처리 중 예상치 못한 오류: {e}")
            return self._save_processing_result(
                folder_name, site_code, "", "",
                status="ollama", error_message=f"예상치 못한 오류: {e}"
            )
    
    def _check_exclusion_keywords(self, folder_name: str) -> List[str]:
        """폴더명에서 제외 키워드를 체크합니다."""
        matched_keywords = []
        
        for keyword_info in self.exclusion_keywords:
            keyword = keyword_info['keyword'].lower()
            if keyword in folder_name.lower():
                matched_keywords.append(keyword_info['keyword'])
                logger.debug(f"제외 키워드 매칭: '{keyword}' in '{folder_name}'")
        
        return matched_keywords
    
    def _determine_final_status(self, first_response: Optional[Dict[str, Any]], second_response: Optional[Dict[str, Any]]) -> str:
        """1차, 2차 응답을 기반으로 최종 상태를 결정합니다."""
        
        # EXTRACTED_TARGET이 유효한 값인지 확인하는 함수
        def has_valid_target(response):
            if not response:
                return False
            target = response.get("EXTRACTED_TARGET", "")
            return target and target not in ["정보 없음", "해당없음", ""]
        
        # 1차 또는 2차에서 EXTRACTED_TARGET이 있으면 성공
        if has_valid_target(first_response) or has_valid_target(second_response):
            return "성공"
        
        # 1차, 2차 모두 정보 없음인 경우 completed
        first_no_info = not first_response or not has_valid_target(first_response)
        second_no_info = not second_response or not has_valid_target(second_response)
        
        if first_no_info and second_no_info:
            return "completed"
        
        # 기본값
        return "ollama"
    
    def _format_date_to_standard(self, date_str: str) -> Optional[str]:
        """날짜 문자열을 YYYY-MM-DD 형태로 변환합니다."""
        import re
        
        if not date_str or date_str in ["정보 없음", "해당없음", ""]:
            return None
        
        # 공백과 특수문자 제거
        clean_date = re.sub(r'[^\d\.\-/]', '', date_str.strip())
        
        # YYYY-MM-DD 패턴 (이미 표준 형태)
        if re.match(r'^\d{4}-\d{2}-\d{2}$', clean_date):
            return clean_date
        
        # YYYY.MM.DD 패턴
        match = re.match(r'^(\d{4})\.(\d{2})\.(\d{2})$', clean_date)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
        # YYYYMMDD 패턴
        match = re.match(r'^(\d{4})(\d{2})(\d{2})$', clean_date)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
        # YYYY/MM/DD 패턴
        match = re.match(r'^(\d{4})/(\d{2})/(\d{2})$', clean_date)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
        # 더 복잡한 패턴들 처리
        # 예: 2024년 12월 25일
        year_month_day = re.search(r'(\d{4})년?\s*(\d{1,2})월?\s*(\d{1,2})일?', date_str)
        if year_month_day:
            year = year_month_day.group(1)
            month = year_month_day.group(2).zfill(2)
            day = year_month_day.group(3).zfill(2)
            return f"{year}-{month}-{day}"
        
        # 숫자만 8자리인 경우 (YYYYMMDD)
        numbers_only = re.sub(r'[^\d]', '', date_str)
        if len(numbers_only) == 8:
            return f"{numbers_only[:4]}-{numbers_only[4:6]}-{numbers_only[6:8]}"
        
        logger.debug(f"날짜 변환 실패: '{date_str}' -> None")
        return None
    
    def _get_best_value_from_responses(self, first_response: Optional[Dict[str, Any]], second_response: Optional[Dict[str, Any]], key: str) -> str:
        """first_response와 second_response 중에서 유효한 값이 있는 것을 반환합니다."""
        
        def is_valid_value(value):
            return value and value not in ["정보 없음", "해당없음", ""]
        
        # first_response에서 값 확인 (우선순위)
        if first_response and key in first_response:
            first_value = first_response.get(key, "")
            if is_valid_value(first_value):
                logger.debug(f"{key} 값을 first_response에서 사용: {first_value}")
                return first_value
        
        # second_response에서 값 확인
        if second_response and key in second_response:
            second_value = second_response.get(key, "")
            if is_valid_value(second_value):
                logger.debug(f"{key} 값을 second_response에서 사용: {second_value}")
                return second_value
        
        # 둘 다 없으면 빈 문자열 반환
        return ""
    
    def _extract_title_from_content(self, content_md: str) -> str:
        """content.md에서 제목을 추출합니다."""
        if not content_md:
            return ""
        
        lines = content_md.split('\n')
        
        # 첫 번째 비어있지 않은 줄을 찾기
        for line in lines[:10]:  # 상위 10줄만 확인
            line = line.strip()
            if line:
                # # 마크다운 헤더 제거
                if line.startswith('#'):
                    title = line.lstrip('#').strip()
                    logger.debug(f"마크다운 헤더에서 제목 추출: {title}")
                    return title
                
                # 제목:, 공고명: 패턴 확인
                for prefix in ['제목:', '공고명:', '공고 제목:', '제목 :']:
                    if line.lower().startswith(prefix.lower()):
                        title = line[len(prefix):].strip()
                        logger.debug(f"{prefix} 패턴에서 제목 추출: {title}")
                        return title
                
                # 일반 텍스트인 경우 그대로 제목으로 사용 (첫 번째 줄)
                logger.debug(f"첫 번째 줄을 제목으로 사용: {line}")
                return line
        
        return ""
    
    def _normalize_korean_text(self, text: str) -> str:
        """한글 텍스트를 NFC(Composed) 형태로 정규화합니다.
        
        macOS는 NFD(Decomposed) 형태를 사용하여 한글이 자음과 모음으로 분리되어 저장되지만,
        윈도우에서는 NFC(Composed) 형태로 표시해야 한글이 올바르게 보입니다.
        """
        return unicodedata.normalize('NFC', text)
    
    def _natural_sort_key(self, path: Path) -> tuple:
        """폴더명의 숫자 부분을 기준으로 자연 정렬을 위한 키를 생성합니다."""
        import re
        
        folder_name = path.name
        # 숫자_제목 패턴에서 숫자 부분 추출
        match = re.match(r'^(\d+)_(.*)$', folder_name)
        if match:
            number = int(match.group(1))
            title = match.group(2)
            return (number, title)
        else:
            # 숫자로 시작하지 않는 경우는 맨 뒤로
            return (float('inf'), folder_name)
    
    def _process_attachments_separately(self, directory_path: Path, attach_force: bool = False) -> tuple[str, List[str]]:
        """첨부파일들을 처리하여 내용을 결합하고 파일명 목록을 반환합니다."""
        attachments_dir = directory_path / "attachments"
        
        if not attachments_dir.exists():
            return "", []
        
        combined_content = ""
        attachment_filenames = []
        
        # 처리 가능한 확장자 정의
        supported_extensions = {'.pdf', '.hwp', '.hwpx', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.pptx', '.docx', '.xlsx', '.md'}
        
        target_keywords = ['양식', '서류', '신청서', '동의서']

        for file_path in attachments_dir.iterdir():
            if file_path.is_file():
                file_extension = file_path.suffix.lower()
                filename = file_path.stem
                

                logger.info(f"filename===={filename}")
                lowercase_filename = filename.lower()
                
                if any(keyword in lowercase_filename for keyword in target_keywords):                
                    logger.info(f"양식, 신청서 등은 SKIP===={filename}")
                    continue; 

                # 확장자가 없거나 지원하지 않는 파일은 건너뛰기
                if not file_extension or file_extension not in supported_extensions:
                    logger.debug(f"지원하지 않는 파일 형식 건너뜀: {file_path.name}")
                    continue
                
                attachment_filenames.append(self._normalize_korean_text(file_path.name))  # 전체 파일명 (확장자 포함)
                logger.debug(f"첨부파일 처리 시작: {file_path.name}")
                
                # 이미 .md 파일인 경우 직접 읽기
                if file_extension == '.md':
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        if content.strip():  # 내용이 있는 경우만 추가
                            combined_content += f"\n\n=== {self._normalize_korean_text(file_path.name)} ===\n{content}"
                            logger.debug(f"첨부파일 .md 직접 읽기 성공: {file_path.name} ({len(content)} 문자)")
                        else:
                            logger.warning(f"첨부파일 .md 내용이 비어있음: {file_path.name}")
                    except Exception as e:
                        logger.error(f"첨부파일 .md 직접 읽기 실패: {e}")
                    continue  # .md 파일 처리 완료, 다음 파일로
                
                # 첨부파일명.md 파일이 있는지 확인 (다른 확장자 파일들을 위한)
                md_file_path = attachments_dir / f"{filename}.md"
                
                # attach_force가 True이면 기존 .md 파일을 무시하고 원본에서 재변환
                if not attach_force and md_file_path.exists():
                    # .md 파일이 있으면 그것을 읽음
                    try:
                        with open(md_file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        if content.strip():  # 내용이 있는 경우만 추가
                            combined_content += f"\n\n=== {self._normalize_korean_text(filename)}.md ===\n{content}"
                            logger.debug(f"첨부파일 .md 읽기 성공: {filename}.md ({len(content)} 문자)")
                        else:
                            logger.warning(f"첨부파일 .md 내용이 비어있음: {filename}.md")
                    except Exception as e:
                        logger.error(f"첨부파일 .md 읽기 실패: {e}")
                else:
                    # .md 파일이 없거나 attach_force가 True이면 원본 파일을 변환
                    if attach_force and md_file_path.exists():
                        logger.info(f"--attach-force: 기존 .md 파일 무시하고 재변환: {file_path.name}")
                    else:
                        logger.info(f"첨부파일 변환 시작: {file_path.name}")
                        
                    try:
                        content = self.attachment_processor.process_single_file(file_path)
                        
                        if content and content.strip():
                            combined_content += f"\n\n=== {self._normalize_korean_text(file_path.name)} ===\n{content}"
                            logger.info(f"첨부파일 변환 성공: {file_path.name} ({len(content)} 문자)")
                            
                            # 변환된 내용을 .md 파일로 저장
                            try:
                                with open(md_file_path, 'w', encoding='utf-8') as f:
                                    f.write(content)
                                logger.debug(f"변환된 내용을 .md로 저장: {md_file_path}")
                            except Exception as save_e:
                                logger.warning(f".md 파일 저장 실패: {save_e}")
                        else:
                            logger.warning(f"첨부파일에서 내용 추출 실패: {file_path.name}")
                        
                    except Exception as e:
                        logger.error(f"첨부파일 변환 실패 ({file_path}): {e}")
        
        logger.info(f"첨부파일 처리 완료: {len(attachment_filenames)}개 파일, {len(combined_content)} 문자")
        return combined_content.strip(), attachment_filenames
    
    def _analyze_with_ollama(self, content: str) -> tuple[Optional[Dict[str, Any]], str]:
        """Ollama를 통해 내용을 분석합니다."""
        try:
            return self.announcement_analyzer.analyze_announcement(content)
        except Exception as e:
            logger.error(f"Ollama 분석 중 오류: {e}")
            return None, ""
    
    def _save_processing_result(
        self, 
        folder_name: str, 
        site_code: str, 
        content_md: str, 
        combined_content: str,
        attachment_filenames: List[str] = None,
        status: str = "ollama",
        exclusion_keywords: List[str] = None,
        exclusion_reason: str = None,
        error_message: str = None,
        force: bool = False
    ) -> Optional[int]:
        """처리 결과를 데이터베이스에 저장합니다."""
        try:
            from sqlalchemy import text
            
            with self.db_manager.SessionLocal() as session:
                if force:
                    # UPSERT 로직
                    sql = text("""
                        INSERT INTO announcement_prv_processing (
                            folder_name, site_code, content_md, combined_content,
                            attachment_filenames, exclusion_keyword, exclusion_reason, 
                            processing_status, error_message, created_at, updated_at
                        ) VALUES (
                            :folder_name, :site_code, :content_md, :combined_content,
                            :attachment_filenames, :exclusion_keyword, :exclusion_reason, 
                            :processing_status, :error_message, NOW(), NOW()
                        )
                        ON DUPLICATE KEY UPDATE
                            content_md = VALUES(content_md),
                            combined_content = VALUES(combined_content),
                            attachment_filenames = VALUES(attachment_filenames),
                            exclusion_keyword = VALUES(exclusion_keyword),
                            exclusion_reason = VALUES(exclusion_reason),
                            processing_status = VALUES(processing_status),
                            error_message = VALUES(error_message),
                            updated_at = NOW()
                    """)
                else:
                    # 일반 INSERT
                    sql = text("""
                        INSERT INTO announcement_prv_processing (
                            folder_name, site_code, content_md, combined_content,
                            attachment_filenames, exclusion_keyword, exclusion_reason, 
                            processing_status, error_message, created_at, updated_at
                        ) VALUES (
                            :folder_name, :site_code, :content_md, :combined_content,
                            :attachment_filenames, :exclusion_keyword, :exclusion_reason, 
                            :processing_status, :error_message, NOW(), NOW()
                        )
                    """)
                
                params = {
                    'folder_name': folder_name,
                    'site_code': site_code,
                    'content_md': content_md,
                    'combined_content': combined_content,
                    'attachment_filenames': ', '.join(attachment_filenames) if attachment_filenames else None,
                    'exclusion_keyword': ', '.join(exclusion_keywords) if exclusion_keywords else None,
                    'exclusion_reason': exclusion_reason,
                    'processing_status': status,
                    'error_message': error_message
                }
                
                result = session.execute(sql, params)
                session.commit()
                
                record_id = result.lastrowid
                logger.info(f"처리 결과 저장 완료: ID {record_id}, 상태: {status}")
                return record_id
                
        except Exception as e:
            logger.error(f"처리 결과 저장 실패: {e}")
            return None
    
    def _update_processing_result_simple(
        self,
        record_id: int,
        status: str = "성공",
        error_message: str = None
    ) -> bool:
        """간단한 상태 업데이트 (제목 기반 처리용)"""
        try:
            from sqlalchemy import text
            
            with self.db_manager.SessionLocal() as session:
                sql = text("""
                    UPDATE announcement_prv_processing SET
                        processing_status = :processing_status,
                        error_message = :error_message,
                        is_support_program = :is_support_program,
                        support_program_reason = :support_program_reason,
                        updated_at = NOW()
                    WHERE id = :record_id
                """)
                
                params = {
                    'record_id': record_id,
                    'processing_status': status,
                    'error_message': error_message,
                    'is_support_program': 1,
                    'support_program_reason': '제목에 지원이라는 단어 들어감'
                }
                
                session.execute(sql, params)
                session.commit()
                
                logger.info(f"간단한 처리 결과 업데이트 완료: ID {record_id}, 상태: {status}, 지원사업: True")
                return True
                
        except Exception as e:
            logger.error(f"간단한 처리 결과 업데이트 실패: {e}")
            return False
    
    def _update_processing_result(
        self,
        record_id: int,
        ollama_response: Optional[Dict[str, Any]],
        ollama_prompt: str,
        first_response: Optional[Dict[str, Any]] = None,
        status: str = "ollama"
    ) -> bool:
        """기존 레코드에 Ollama 분석 결과를 업데이트합니다."""
        try:
            from sqlalchemy import text
            
            with self.db_manager.SessionLocal() as session:
                # 추출된 데이터 준비
                extracted_data = {}
                if ollama_response:
                    # URL과 날짜는 first_response와 ollama_response 중 값이 있는 것을 우선 사용
                    extracted_url = self._get_best_value_from_responses(first_response, ollama_response, "EXTRACTED_URL")
                    extracted_announcement_date = self._get_best_value_from_responses(first_response, ollama_response, "EXTRACTED_ANNOUNCEMENT_DATE")
                    
                    extracted_data = {
                        'extracted_title': ollama_response.get("EXTRACTED_TITLE", "정보 없음"),
                        'extracted_target': ollama_response.get("EXTRACTED_TARGET", "정보 없음"),
                        'extracted_target_type': ollama_response.get("EXTRACTED_TARGET_TYPE", "정보 없음"),
                        'extracted_amount': ollama_response.get("EXTRACTED_AMOUNT", "정보 없음"),
                        'extracted_period': ollama_response.get("EXTRACTED_PERIOD", "정보 없음"),
                        'extracted_schedule': ollama_response.get("EXTRACTED_SCHEDULE", "정보 없음"),
                        'extracted_content': ollama_response.get("EXTRACTED_CONTENT", "정보 없음"),
                        'extracted_announcement_date': extracted_announcement_date,
                        'original_url': extracted_url,
                        'formatted_announcement_date': self._format_date_to_standard(extracted_announcement_date),
                        'extracted_gov24_url': ollama_response.get("EXTRACTED_GOV24_URL", "정보 없음"),
                        'extracted_origin_url': ollama_response.get("EXTRACTED_ORIGIN_URL", "정보 없음"),
                        'is_support_program': ollama_response.get("IS_SUPPORT_PROGRAM"),
                        'support_program_reason': ollama_response.get("SUPPORT_PROGRAM_REASON", "정보 없음")
                    }
                
                sql = text("""
                    UPDATE announcement_prv_processing SET
                        ollama_first_response = :ollama_first_response,
                        ollama_response = :ollama_response,
                        ollama_prompt = :ollama_prompt,
                        extracted_title = :extracted_title,
                        extracted_target = :extracted_target,
                        extracted_target_type = :extracted_target_type,
                        extracted_amount = :extracted_amount,
                        extracted_period = :extracted_period,
                        extracted_schedule = :extracted_schedule,
                        extracted_content = :extracted_content,
                        extracted_announcement_date = :extracted_announcement_date,
                        original_url = :original_url,
                        formatted_announcement_date = :formatted_announcement_date,
                        extracted_gov24_url = :extracted_gov24_url,
                        extracted_origin_url = :extracted_origin_url,
                        is_support_program = :is_support_program,
                        support_program_reason = :support_program_reason,
                        processing_status = :processing_status,
                        updated_at = NOW()
                    WHERE id = :record_id
                """)
                
                params = {
                    'record_id': record_id,
                    'ollama_first_response': json.dumps(first_response, ensure_ascii=False) if first_response else None,
                    'ollama_response': json.dumps(ollama_response, ensure_ascii=False) if ollama_response else None,
                    'ollama_prompt': ollama_prompt,
                    'processing_status': status,
                    **extracted_data
                }
                
                session.execute(sql, params)
                session.commit()
                
                logger.info(f"처리 결과 업데이트 완료: ID {record_id}, 상태: {status}")
                
                # 화면에 결과 표시
                if ollama_response:
                    self._display_ollama_results(ollama_response)
                
                return True
                
        except Exception as e:
            logger.error(f"처리 결과 업데이트 실패: {e}")
            return False

    def _update_attachment_info(self, record_id: int, combined_content: str, attachment_filenames: List[str]) -> bool:
        """첨부파일 정보를 데이터베이스에 업데이트합니다."""
        try:
            with self.db_manager.SessionLocal() as session:
                from sqlalchemy import text
                
                # 첨부파일 정보만 업데이트
                sql = text("""
                    UPDATE announcement_prv_processing 
                    SET combined_content = :combined_content,
                        attachment_filenames = :attachment_filenames,
                        updated_at = NOW()
                    WHERE id = :record_id
                """)
                
                filenames_str = json.dumps(attachment_filenames, ensure_ascii=False) if attachment_filenames else ""
                
                session.execute(sql, {
                    'record_id': record_id,
                    'combined_content': combined_content,
                    'attachment_filenames': filenames_str
                })
                session.commit()
                
                logger.info(f"첨부파일 정보 업데이트 완료: ID {record_id}")
                return True
                
        except Exception as e:
            logger.error(f"첨부파일 정보 업데이트 실패: {e}")
            return False
    
    def _display_ollama_results(self, ollama_response: Dict[str, Any]):
        """Ollama 분석 결과를 화면에 표시합니다."""
        print(f"  🤖 Ollama 분석 결과: ==== {ollama_response}")

        # IS_SUPPORT_PROGRAM 확인 및 출력
        if "IS_SUPPORT_PROGRAM" in ollama_response:
            if ollama_response.get('IS_SUPPORT_PROGRAM') == True:
                print("     ✅ 지원사업입니다.")
                if "SUPPORT_PROGRAM_REASON" in ollama_response and ollama_response["SUPPORT_PROGRAM_REASON"]:
                    print(f"     📝 지원사업 판단 근거: {ollama_response['SUPPORT_PROGRAM_REASON'][:100]}...")
            else:
                print("     ❌ 지원사업이 아닙니다.")

        if "EXTRACTED_TARGET" in ollama_response and ollama_response["EXTRACTED_TARGET"]:
            print(f"     📌 지원대상: {ollama_response['EXTRACTED_TARGET'][:100]}...")
        if "EXTRACTED_TARGET_TYPE" in ollama_response and ollama_response["EXTRACTED_TARGET_TYPE"]:
            print(f"     🏷️ 지원대상분류: {ollama_response['EXTRACTED_TARGET_TYPE'][:50]}...")
        if "EXTRACTED_AMOUNT" in ollama_response and ollama_response["EXTRACTED_AMOUNT"]:
            print(f"     💰 지원금액: {ollama_response['EXTRACTED_AMOUNT'][:100]}...")
        if "EXTRACTED_TITLE" in ollama_response and ollama_response["EXTRACTED_TITLE"]:
            print(f"     📝 제목: {ollama_response['EXTRACTED_TITLE'][:100]}...")
        if "EXTRACTED_ANNOUNCEMENT_DATE" in ollama_response and ollama_response["EXTRACTED_ANNOUNCEMENT_DATE"]:
            print(f"     📅 등록일: {ollama_response['EXTRACTED_ANNOUNCEMENT_DATE'][:50]}...")


def get_base_directory(args) -> Path:
    """명령행 인자 또는 환경변수에서 기본 디렉토리를 가져옵니다."""
    
    # 디렉토리 결정
    if args.data:
        directory_name = args.data
    else:
        # 환경변수에서 가져오기
        directory_name = os.getenv("DEFAULT_DIR", "data")
    
    # 현재 디렉토리 기준으로 경로 생성
    current_dir = Path.cwd()
    base_directory = current_dir / directory_name
    
    if not base_directory.exists():
        logger.error(f"디렉토리가 존재하지 않습니다: {base_directory}")
        sys.exit(1)
    
    logger.info(f"기본 디렉토리: {base_directory}")
    
    return base_directory


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="공고 첨부파일 처리 및 분석 프로그램",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python announcement_prv_processor.py --data data.enhanced
  python announcement_prv_processor.py --data data.origin
  python announcement_prv_processor.py  # 환경변수 DEFAULT_DIR 사용
  python announcement_prv_processor.py --data data.enhanced -r  # 재귀적 처리
  python announcement_prv_processor.py --data data.enhanced --attach-force  # 첨부파일 강제 재처리
        """
    )
    
    parser.add_argument(
        "--data", 
        type=str,
        help="데이터 디렉토리명 (기본값: 환경변수 DEFAULT_DIR 또는 'data')"
    )
    
    
    parser.add_argument(
        "--skip-processed", 
        action="store_true", 
        help="이미 처리된 항목 건너뛰기 (기본 동작)"
    )
    
    parser.add_argument(
        "--force", 
        action="store_true", 
        help="이미 처리된 항목도 다시 처리"
    )
    
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="하위 디렉토리를 재귀적으로 처리 (모든 하위 경로의 content.md나 attachments를 찾아서 처리)"
    )
    
    parser.add_argument(
        "--attach-force",
        action="store_true",
        help="첨부파일 강제 재처리 (기존 .md 파일 무시하고 원본 파일에서 다시 변환)"
    )
    
    args = parser.parse_args()
    
    try:
        # 기본 디렉토리 결정
        base_directory = get_base_directory(args)
        
        # 프로세서 초기화
        logger.info("다중 사이트 공고 처리 프로그램 시작")
        processor = AnnouncementPrvProcessor(attach_force=args.attach_force)
        
        # 모든 사이트 처리 실행
        results = processor.process_all_sites(base_directory, args.recursive, args.force, args.attach_force)
        
        # 결과 출력 (process_site_directories에서 이미 상세 출력됨)
        print(f"\n=== 최종 요약 ===")
        print(f"전체 대상: {results['total']}개")
        print(f"처리 성공: {results['success']}개") 
        print(f"처리 실패: {results['failed']}개")
        print(f"건너뛴 항목: {results['skipped']}개")
        
        if results['failed'] > 0:
            print(f"\n실패한 항목이 {results['failed']}개 있습니다. 로그를 확인해주세요.")
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