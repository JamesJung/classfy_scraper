#!/usr/bin/env python3
"""
공고 처리 메인 프로그램 - 2개 워커 병렬 처리 버전

사용법:
    python announcement_processor_parallel.py --site-code [사이트코드] [옵션들]
    
예시:
    python announcement_processor_parallel.py --site-code acci --data data.origin
    python announcement_processor_parallel.py --site-code cbt --workers 2
"""

import argparse
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.config import ConfigManager
from src.config.logConfig import setup_logging
from src.utils.attachmentProcessor import AttachmentProcessor
from src.utils.ollamaClient import AnnouncementAnalyzer
from src.models.announcementDatabase import AnnouncementDatabaseManager, create_announcement_tables
from src.utils.announcementFilter import AnnouncementFilter

logger = setup_logging(__name__)
config = ConfigManager().get_config()

@dataclass
class ProcessingTask:
    """처리 작업 정보"""
    directory_path: Path
    site_code: str
    folder_name: str
    attach_force: bool
    force: bool
    task_id: str

@dataclass
class ProcessingResult:
    """처리 결과 정보"""
    task_id: str
    folder_name: str
    success: bool
    error_message: Optional[str] = None
    processing_time: float = 0.0

class ParallelAnnouncementProcessor:
    """병렬 처리 버전의 공고 처리 클래스 (2개 워커 최적화)"""
    
    def __init__(self, attach_force: bool = False, max_workers: int = 2):
        self.attach_force = attach_force
        self.max_workers = max_workers
        
        # 스레드별 인스턴스를 위한 ThreadLocal 저장소
        self._local = threading.local()
        
        # 전역 DB 매니저 (연결 풀링용)
        self.global_db_manager = AnnouncementDatabaseManager()
        
        # 데이터베이스 테이블 생성 (없는 경우)
        self._ensure_database_tables()
        
        # 제외 키워드 로드 (한 번만)
        self.exclusion_keywords = self._load_exclusion_keywords()
        
        # 통계 추적용
        self._stats_lock = threading.Lock()
        self._processing_stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'skipped_tasks': 0,
            'start_time': None,
            'active_workers': 0
        }
    
    def _get_local_instances(self):
        """스레드별 로컬 인스턴스들을 가져옵니다."""
        if not hasattr(self._local, 'initialized'):
            # 각 스레드마다 별도의 인스턴스 생성
            self._local.attachment_processor = AttachmentProcessor()
            self._local.announcement_analyzer = AnnouncementAnalyzer()
            self._local.db_manager = AnnouncementDatabaseManager()
            self._local.filter = AnnouncementFilter()
            self._local.initialized = True
            
            logger.info(f"스레드별 인스턴스 초기화 완료: {threading.current_thread().name}")
        
        return (
            self._local.attachment_processor,
            self._local.announcement_analyzer,
            self._local.db_manager,
            self._local.filter
        )
    
    def _ensure_database_tables(self):
        """데이터베이스 테이블이 존재하는지 확인하고 생성합니다."""
        try:
            if self.global_db_manager.test_connection():
                self.global_db_manager.create_tables()
                logger.info("데이터베이스 테이블 확인/생성 완료")
            else:
                logger.warning("데이터베이스 연결 실패 - 계속 진행합니다 (DB 저장 불가)")
        except Exception as e:
            logger.warning(f"데이터베이스 초기화 실패: {e} - 계속 진행합니다 (DB 저장 불가)")
    
    def _load_exclusion_keywords(self) -> List[Dict[str, Any]]:
        """데이터베이스에서 제외 키워드를 로드합니다."""
        try:
            from sqlalchemy import text
            
            with self.global_db_manager.SessionLocal() as session:
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
    
    def _update_stats(self, stat_name: str, increment: int = 1):
        """통계를 스레드 안전하게 업데이트합니다."""
        with self._stats_lock:
            self._processing_stats[stat_name] += increment
    
    def _print_progress(self, completed: int, total: int, worker_name: str, folder_name: str, elapsed: float):
        """진행 상황을 출력합니다."""
        progress_pct = (completed / total) * 100 if total > 0 else 0
        print(f"[{worker_name}] [{completed}/{total} : {progress_pct:.1f}%] {folder_name} ({elapsed:.1f}초)")
    
    def process_single_directory(self, task: ProcessingTask) -> ProcessingResult:
        """단일 디렉토리를 처리합니다 (스레드 안전)."""
        worker_name = threading.current_thread().name
        start_time = time.time()
        
        try:
            # 스레드별 인스턴스 가져오기
            attachment_processor, announcement_analyzer, db_manager, filter_instance = self._get_local_instances()
            
            logger.info(f"[{worker_name}] 디렉토리 처리 시작: {task.folder_name}")
            
            # 중복 처리 체크 (force 옵션이 없을 때만)
            if not task.force:
                if db_manager.is_already_processed(task.folder_name, task.site_code):
                    elapsed = time.time() - start_time
                    logger.info(f"[{worker_name}] 이미 처리된 폴더 건너뜀: {task.folder_name}")
                    return ProcessingResult(
                        task_id=task.task_id,
                        folder_name=task.folder_name,
                        success=True,
                        processing_time=elapsed
                    )
            
            # 실제 처리 로직 실행 (기존 process_directory_with_custom_name과 동일)
            success = self._process_directory_core(
                task, attachment_processor, announcement_analyzer, db_manager, filter_instance
            )
            
            elapsed = time.time() - start_time
            
            return ProcessingResult(
                task_id=task.task_id,
                folder_name=task.folder_name,
                success=success,
                processing_time=elapsed
            )
            
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = f"처리 중 예외 발생: {str(e)}"
            logger.error(f"[{worker_name}] {error_msg} ({task.folder_name})")
            
            return ProcessingResult(
                task_id=task.task_id,
                folder_name=task.folder_name,
                success=False,
                error_message=error_msg,
                processing_time=elapsed
            )
    
    def _process_directory_core(self, task: ProcessingTask, attachment_processor, announcement_analyzer, db_manager, filter_instance) -> bool:
        """디렉토리 처리 핵심 로직 (스레드별 인스턴스 사용)"""
        directory_path = task.directory_path
        site_code = task.site_code
        folder_name = task.folder_name
        attach_force = task.attach_force
        force = task.force
        
        try:
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
                        status="ollama", error_message=f"content.md 읽기 실패: {e}",
                        db_manager=db_manager
                    )
            else:
                logger.warning(f"content.md 파일이 없음: {content_md_path}")
            
            # 3. 첨부파일 처리 (content.md와 분리)
            try:
                combined_content, attachment_filenames = self._process_attachments_separately(
                    directory_path, attach_force, attachment_processor
                )
                
                if not content_md.strip() and not combined_content.strip():
                    logger.warning("처리할 내용이 없음")
                    return self._save_processing_result(
                        folder_name, site_code, content_md, combined_content,
                        attachment_filenames=attachment_filenames,
                        status="ollama", error_message="처리할 내용이 없음",
                        db_manager=db_manager
                    )
                
                logger.info(f"첨부파일 내용 처리 완료: {len(combined_content)} 문자, 파일 {len(attachment_filenames)}개")
                
            except Exception as e:
                logger.error(f"첨부파일 처리 실패: {e}")
                return self._save_processing_result(
                    folder_name, site_code, content_md, "",
                    attachment_filenames=[],
                    status="ollama", error_message=f"첨부파일 처리 실패: {e}",
                    db_manager=db_manager
                )
            
            # 4. 제외 키워드가 있는 경우 제외 처리
            if excluded_keywords:
                exclusion_msg = f"제외 키워드가 입력되어 있습니다: {', '.join(excluded_keywords)}"
                logger.info(f"제외 처리: {folder_name} - {exclusion_msg}")
                
                return self._save_processing_result(
                    folder_name, site_code, content_md, combined_content,
                    attachment_filenames=attachment_filenames,
                    status="제외", exclusion_keywords=excluded_keywords,
                    exclusion_reason=exclusion_msg,
                    db_manager=db_manager
                )
            
            # 5. 데이터베이스에 1차 저장 (status: ollama)
            record_id = self._save_processing_result(
                folder_name, site_code, content_md, combined_content, 
                attachment_filenames=attachment_filenames,
                status="ollama", force=True,  # force 옵션은 항상 UPSERT로 처리
                db_manager=db_manager
            )

            # 5.5. 제목에서 "지원" 키워드 확인 (Ollama 분석 전 조기 반환)
            if content_md.strip():
                extracted_title = self._extract_title_from_content(content_md)
                logger.info(f"추출된 제목: {extracted_title}")
                
                if "지원" in extracted_title:
                    logger.info(f"제목에 '지원' 키워드 발견: {extracted_title}")
                    print(f"  ✅ 제목에 '지원' 키워드 발견: {extracted_title[:50]}...")
                    
                    # 바로 성공 처리하고 다음 공고로 이동
                    return self._update_processing_result_simple(
                        record_id, status="성공", error_message="제목에 지원이라는 글자 있음",
                        db_manager=db_manager
                    )
            
            # 6. content_md로 첫번째 ollama 분석
            print("  📋 1차 Ollama 분석 중 (content.md)...")
            first_response = None
            
            if content_md.strip():
                first_response, first_prompt = self._analyze_with_ollama(content_md, announcement_analyzer)
                
                # EXTRACTED_TARGET이 있는지 확인
                def has_valid_target(response):
                    if not response:
                        return False
                    target = response.get("EXTRACTED_TARGET", "")
                    return target and target not in ["정보 없음", "해당없음", ""]
                
                if has_valid_target(first_response):
                    # 성공: 최종 응답으로 사용
                    logger.info("1차 분석 성공 - content.md에서 EXTRACTED_TARGET 추출됨")
                    return self._update_processing_result(
                        record_id, first_response, first_prompt, status="성공",
                        db_manager=db_manager
                    )
            
            # 7. combined_content로 두번째 ollama 분석
            print("  📋 2차 Ollama 분석 중 (첨부파일)...")
            second_response = None
            
            if combined_content.strip():
                second_response, second_prompt = self._analyze_with_ollama(combined_content, announcement_analyzer)
                
                # 최종 상태 결정 로직
                final_status = self._determine_final_status(first_response, second_response)
                
                return self._update_processing_result(
                    record_id, second_response, second_prompt, 
                    first_response=first_response, status=final_status,
                    db_manager=db_manager
                )
            else:
                # combined_content가 없는 경우 1차 결과만 사용
                final_status = self._determine_final_status(first_response, None)
                return self._update_processing_result(
                    record_id, first_response, first_prompt if first_response else "", 
                    status=final_status,
                    db_manager=db_manager
                )
                
        except Exception as e:
            logger.error(f"디렉토리 처리 중 예상치 못한 오류: {e}")
            return self._save_processing_result(
                folder_name, site_code, "", "",
                status="ollama", error_message=f"예상치 못한 오류: {e}",
                db_manager=db_manager
            )
    
    def process_site_directories_parallel(self, base_dir: Path, site_code: str, recursive: bool = False, force: bool = False, attach_force: bool = False) -> Dict[str, int]:
        """특정 사이트의 모든 디렉토리를 병렬로 처리합니다."""
        # 처리할 디렉토리 목록 찾기
        target_directories = self._find_target_directories(base_dir, site_code, recursive, force)
        
        if not target_directories:
            logger.warning("처리할 디렉토리가 없습니다.")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        
        total_count = len(target_directories)
        site_dir = base_dir / site_code
        
        # 작업 목록 생성
        tasks = []
        for i, directory in enumerate(target_directories):
            relative_path = directory.relative_to(site_dir)
            folder_name = str(relative_path).replace("/", "_")  # 슬래시를 언더스코어로 변경
            
            task = ProcessingTask(
                directory_path=directory,
                site_code=site_code,
                folder_name=folder_name,
                attach_force=attach_force,
                force=force,
                task_id=f"{site_code}_{i}"
            )
            tasks.append(task)
        
        # 병렬 처리 실행
        return self._execute_parallel_processing(tasks, site_code)
    
    def _execute_parallel_processing(self, tasks: List[ProcessingTask], context_name: str = "") -> Dict[str, int]:
        """작업 목록을 병렬로 처리합니다."""
        total_count = len(tasks)
        results = {"total": total_count, "success": 0, "failed": 0, "skipped": 0}
        
        if total_count == 0:
            return results
        
        start_time = time.time()
        processed_count = 0
        
        print(f"\n🚀 병렬 처리 시작: {context_name} ({total_count}개 작업, {self.max_workers}개 워커)")
        print(f"{'='*60}")
        
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="Worker") as executor:
            # 모든 작업을 submit
            future_to_task = {executor.submit(self.process_single_directory, task): task for task in tasks}
            
            # 완료되는 대로 결과 처리
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                processed_count += 1
                
                try:
                    result = future.result()
                    
                    if result.success:
                        results["success"] += 1
                        status_icon = "✅"
                        status_text = "성공"
                    else:
                        results["failed"] += 1
                        status_icon = "❌"
                        status_text = f"실패: {result.error_message or 'Unknown error'}"
                    
                    progress_pct = (processed_count / total_count) * 100
                    print(f"[{processed_count}/{total_count} : {progress_pct:.1f}%] {status_icon} {result.folder_name} ({result.processing_time:.1f}초)")
                    
                except Exception as e:
                    results["failed"] += 1
                    print(f"[{processed_count}/{total_count}] ❌ {task.folder_name} - 예외: {str(e)[:50]}...")
                    logger.error(f"Future 처리 중 오류: {e}")
        
        total_elapsed = time.time() - start_time
        
        print(f"\n{'='*60}")
        print(f"🎉 병렬 처리 완료: {context_name}")
        print(f"전체: {results['total']}, 성공: {results['success']}, 실패: {results['failed']}")
        print(f"소요 시간: {total_elapsed:.1f}초 ({total_elapsed/60:.1f}분)")
        if results['success'] > 0:
            avg_time = total_elapsed / results['success']
            print(f"성공한 항목당 평균 시간: {avg_time:.1f}초")
        
        # 성능 향상 계산 (순차 대비 추정)
        if results['success'] > 0:
            estimated_sequential_time = total_elapsed * self.max_workers  # 대략적 추정
            speedup_ratio = estimated_sequential_time / total_elapsed
            print(f"예상 성능 향상: {speedup_ratio:.2f}x (대략적 추정)")
        
        print(f"{'='*60}")
        
        return results
    
    # 기존 AnnouncementProcessor의 헬퍼 메서드들을 복사 (스레드 안전성 고려)
    def _find_target_directories(self, base_dir: Path, site_code: str, recursive: bool = False, force: bool = False) -> List[Path]:
        """처리할 대상 디렉토리들을 찾습니다."""
        site_dir = base_dir / site_code
        
        if not site_dir.exists():
            logger.error(f"사이트 디렉토리가 없음: {site_dir}")
            return []
        
        target_directories = []
        
        if recursive:
            logger.info(f"재귀적 디렉토리 검색 시작: {site_dir}")
            
            for root_path in site_dir.rglob("*"):
                if root_path.is_dir():
                    has_content_md = (root_path / "content.md").exists()
                    has_attachments = (root_path / "attachments").exists() and any((root_path / "attachments").iterdir())
                    
                    if has_content_md or has_attachments:
                        target_directories.append(root_path)
                        logger.debug(f"대상 디렉토리 발견: {root_path.relative_to(site_dir)}")
        else:
            all_directories = [d for d in site_dir.iterdir() if d.is_dir()]
            target_directories = sorted(all_directories, key=self._natural_sort_key)
        
        logger.info(f"발견된 전체 디렉토리: {len(target_directories)}개")
        
        if target_directories:
            logger.info(f"첫 5개 폴더: {[d.name for d in target_directories[:5]]}")
        
        if not force:
            processed_folders = set(self.global_db_manager.get_processed_folders(site_code))
            
            filtered_directories = []
            for directory in target_directories:
                relative_path = directory.relative_to(site_dir)
                folder_name = str(relative_path).replace("/", "_")  # 슬래시를 언더스코어로 변경
                
                if folder_name not in processed_folders:
                    filtered_directories.append(directory)
                else:
                    logger.debug(f"이미 처리된 폴더 건너뜀: {folder_name}")
            
            logger.info(f"전체 발견된 디렉토리: {len(target_directories)}개")
            logger.info(f"처리 대상 디렉토리: {len(filtered_directories)}개")
            logger.info(f"이미 처리된 폴더: {len(processed_folders)}개")
            
            return filtered_directories
        else:
            logger.info(f"--force 옵션: 모든 디렉토리 처리 ({len(target_directories)}개)")
            return target_directories
    
    def _check_exclusion_keywords(self, folder_name: str) -> List[str]:
        """폴더명에서 제외 키워드를 체크합니다."""
        matched_keywords = []
        
        for keyword_info in self.exclusion_keywords:
            keyword = keyword_info['keyword'].lower()
            if keyword in folder_name.lower():
                matched_keywords.append(keyword_info['keyword'])
                logger.debug(f"제외 키워드 매칭: '{keyword}' in '{folder_name}'")
        
        return matched_keywords
    
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
    
    def _natural_sort_key(self, path: Path) -> tuple:
        """폴더명의 숫자 부분을 기준으로 자연 정렬을 위한 키를 생성합니다."""
        import re
        
        folder_name = path.name
        match = re.match(r'^(\d+)_(.*)$', folder_name)
        if match:
            number = int(match.group(1))
            title = match.group(2)
            return (number, title)
        else:
            return (float('inf'), folder_name)
    
    def _process_attachments_separately(self, directory_path: Path, attach_force: bool, attachment_processor) -> Tuple[str, List[str]]:
        """첨부파일들을 처리하여 내용을 결합하고 파일명 목록을 반환합니다."""
        attachments_dir = directory_path / "attachments"
        
        if not attachments_dir.exists():
            return "", []
        
        combined_content = ""
        attachment_filenames = []
        
        supported_extensions = {'.pdf', '.hwp', '.hwpx', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.pptx', '.docx', '.xlsx'}
        target_keywords = ['양식', '서류', '신청서', '동의서']

        for file_path in attachments_dir.iterdir():
            if file_path.is_file():
                file_extension = file_path.suffix.lower()
                filename = file_path.stem
                
                lowercase_filename = filename.lower()
                
                if any(keyword in lowercase_filename for keyword in target_keywords):                
                    logger.info(f"양식, 신청서 등은 SKIP===={filename}")
                    continue

                if not file_extension or file_extension not in supported_extensions:
                    logger.debug(f"지원하지 않는 파일 형식 건너뜀: {file_path.name}")
                    continue
                
                attachment_filenames.append(file_path.name)  # 전체 파일명 (확장자 포함)
                logger.debug(f"첨부파일 처리 시작: {file_path.name}")
                
                md_file_path = attachments_dir / f"{filename}.md"
                
                if not attach_force and md_file_path.exists():
                    try:
                        with open(md_file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        if content.strip():
                            combined_content += f"\n\n=== {filename}.md ===\n{content}"
                            logger.debug(f"첨부파일 .md 읽기 성공: {filename}.md ({len(content)} 문자)")
                        else:
                            logger.warning(f"첨부파일 .md 내용이 비어있음: {filename}.md")
                    except Exception as e:
                        logger.error(f"첨부파일 .md 읽기 실패: {e}")
                else:
                    if attach_force and md_file_path.exists():
                        logger.info(f"--attach-force: 기존 .md 파일 무시하고 재변환: {file_path.name}")
                    else:
                        logger.info(f"첨부파일 변환 시작: {file_path.name}")
                        
                    try:
                        content = attachment_processor.process_single_file(file_path)
                        
                        if content and content.strip():
                            combined_content += f"\n\n=== {file_path.name} ===\n{content}"
                            logger.info(f"첨부파일 변환 성공: {file_path.name} ({len(content)} 문자)")
                            
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
    
    def _analyze_with_ollama(self, content: str, announcement_analyzer) -> Tuple[Optional[Dict[str, Any]], str]:
        """Ollama를 통해 내용을 분석합니다."""
        try:
            return announcement_analyzer.analyze_announcement(content)
        except Exception as e:
            logger.error(f"Ollama 분석 중 오류: {e}")
            return None, ""
    
    def _determine_final_status(self, first_response: Optional[Dict[str, Any]], second_response: Optional[Dict[str, Any]]) -> str:
        """1차, 2차 응답을 기반으로 최종 상태를 결정합니다."""
        
        def has_valid_target(response):
            if not response:
                return False
            target = response.get("EXTRACTED_TARGET", "")
            return target and target not in ["정보 없음", "해당없음", ""]
        
        if has_valid_target(first_response) or has_valid_target(second_response):
            return "성공"
        
        first_no_info = not first_response or not has_valid_target(first_response)
        second_no_info = not second_response or not has_valid_target(second_response)
        
        if first_no_info and second_no_info:
            return "completed"
        
        return "ollama"
    
    def _get_best_value_from_responses(self, first_response: Optional[Dict[str, Any]], second_response: Optional[Dict[str, Any]], key: str) -> str:
        """first_response와 second_response 중에서 유효한 값이 있는 것을 반환합니다."""
        
        def is_valid_value(value):
            return value and value not in ["정보 없음", "해당없음", ""]
        
        if first_response and key in first_response:
            first_value = first_response.get(key, "")
            if is_valid_value(first_value):
                logger.debug(f"{key} 값을 first_response에서 사용: {first_value}")
                return first_value
        
        if second_response and key in second_response:
            second_value = second_response.get(key, "")
            if is_valid_value(second_value):
                logger.debug(f"{key} 값을 second_response에서 사용: {second_value}")
                return second_value
        
        return ""
    
    def _format_date_to_standard(self, date_str: str) -> Optional[str]:
        """날짜 문자열을 YYYY-MM-DD 형태로 변환합니다."""
        import re

        if not date_str or date_str in ["정보 없음", "해당없음", ""]:
            return None

        # 마크다운 볼드(**) 먼저 제거
        date_str = re.sub(r'\*+', '', date_str).strip()

        clean_date = re.sub(r'[^\d\.\-/]', '', date_str.strip())
        
        if re.match(r'^\d{4}-\d{2}-\d{2}$', clean_date):
            return clean_date
        
        match = re.match(r'^(\d{4})\.(\d{2})\.(\d{2})$', clean_date)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
        match = re.match(r'^(\d{4})(\d{2})(\d{2})$', clean_date)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
        match = re.match(r'^(\d{4})/(\d{2})/(\d{2})$', clean_date)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
        year_month_day = re.search(r'(\d{4})년?\s*(\d{1,2})월?\s*(\d{1,2})일?', date_str)
        if year_month_day:
            year = year_month_day.group(1)
            month = year_month_day.group(2).zfill(2)
            day = year_month_day.group(3).zfill(2)
            return f"{year}-{month}-{day}"
        
        numbers_only = re.sub(r'[^\d]', '', date_str)
        if len(numbers_only) == 8:
            return f"{numbers_only[:4]}-{numbers_only[4:6]}-{numbers_only[6:8]}"
        
        logger.debug(f"날짜 변환 실패: '{date_str}' -> None")
        return None
    
    # 데이터베이스 관련 메서드들 (스레드 안전성을 위해 db_manager 파라미터 추가)
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
        force: bool = False,
        db_manager=None
    ) -> Optional[int]:
        """처리 결과를 데이터베이스에 저장합니다."""
        try:
            from sqlalchemy import text
            
            with db_manager.SessionLocal() as session:
                if force:
                    sql = text("""
                        INSERT INTO announcement_processing (
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
                    sql = text("""
                        INSERT INTO announcement_processing (
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
        error_message: str = None,
        db_manager=None
    ) -> bool:
        """간단한 상태 업데이트 (제목 기반 처리용)"""
        try:
            from sqlalchemy import text
            
            with db_manager.SessionLocal() as session:
                sql = text("""
                    UPDATE announcement_processing SET
                        processing_status = :processing_status,
                        error_message = :error_message,
                        updated_at = NOW()
                    WHERE id = :record_id
                """)
                
                params = {
                    'record_id': record_id,
                    'processing_status': status,
                    'error_message': error_message
                }
                
                session.execute(sql, params)
                session.commit()
                
                logger.info(f"간단한 처리 결과 업데이트 완료: ID {record_id}, 상태: {status}")
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
        status: str = "ollama",
        db_manager=None
    ) -> bool:
        """기존 레코드에 Ollama 분석 결과를 업데이트합니다."""
        try:
            from sqlalchemy import text
            
            with db_manager.SessionLocal() as session:
                extracted_data = {}
                if ollama_response:
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
                        'formatted_announcement_date': self._format_date_to_standard(extracted_announcement_date)
                    }
                
                sql = text("""
                    UPDATE announcement_processing SET
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
                
                if ollama_response:
                    self._display_ollama_results(ollama_response)
                
                return True
                
        except Exception as e:
            logger.error(f"처리 결과 업데이트 실패: {e}")
            return False
    
    def _display_ollama_results(self, ollama_response: Dict[str, Any]):
        """Ollama 분석 결과를 화면에 표시합니다."""
        print("  🤖 Ollama 분석 결과:")
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


def get_directory_and_site_code(args) -> Tuple[Path, str]:
    """명령행 인자 또는 환경변수에서 디렉토리와 사이트코드를 가져옵니다."""
    
    if args.data:
        directory_name = args.data
    else:
        directory_name = os.getenv("DEFAULT_DIR", "data")
    
    if not args.site_code:
        logger.error("사이트 코드가 지정되지 않았습니다.")
        sys.exit(1)
    
    site_code = args.site_code
    
    current_dir = Path.cwd()
    base_directory = current_dir / directory_name
    
    if not base_directory.exists():
        logger.error(f"디렉토리가 존재하지 않습니다: {base_directory}")
        sys.exit(1)
    
    logger.info(f"기본 디렉토리: {base_directory}")
    logger.info(f"사이트 코드: {site_code}")
    
    return base_directory, site_code


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="공고 첨부파일 처리 및 분석 프로그램 - 병렬 처리 버전",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python announcement_processor_parallel.py --site-code acci --data data.enhanced
  python announcement_processor_parallel.py --site-code cbt --data data.origin --workers 4
  python announcement_processor_parallel.py --site-code acci  # 환경변수 DEFAULT_DIR 사용
  python announcement_processor_parallel.py --site-code acci --data data.enhanced -r  # 재귀적 처리
  python announcement_processor_parallel.py --site-code acci --attach-force  # 첨부파일 강제 재처리
        """
    )
    
    parser.add_argument(
        "--data", 
        type=str,
        help="데이터 디렉토리명 (기본값: 환경변수 DEFAULT_DIR 또는 'data')"
    )
    
    parser.add_argument(
        "--site-code", 
        type=str,
        required=True,
        help="사이트 코드 (필수, 예: acci, cbt, andongcci 등)"
    )
    
    parser.add_argument(
        "--workers", 
        type=int,
        default=2,
        help="병렬 처리에 사용할 워커 수 (기본값: 2, 권장: 2)"
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
        # 디렉토리와 사이트코드 결정
        base_directory, site_code = get_directory_and_site_code(args)
        
        # 프로세서 초기화
        logger.info(f"병렬 공고 처리 프로그램 시작 (워커 수: {args.workers})")
        processor = ParallelAnnouncementProcessor(
            attach_force=args.attach_force,
            max_workers=args.workers
        )
        
        # 병렬 처리 실행
        results = processor.process_site_directories_parallel(
            base_directory, site_code, args.recursive, args.force, args.attach_force
        )
        
        # 최종 결과 출력
        print(f"\n=== 최종 요약 ===")
        print(f"워커 수: {args.workers}개")
        print(f"사이트 코드: {site_code}")
        print(f"전체 대상: {results['total']}개")
        print(f"처리 성공: {results['success']}개") 
        print(f"처리 실패: {results['failed']}개")
        print(f"건너뛴 항목: {results['skipped']}개")
        
        if results['failed'] > 0:
            print(f"\n실패한 항목이 {results['failed']}개 있습니다. 로그를 확인해주세요.")
            sys.exit(1)
        else:
            print("\n🎉 모든 병렬 처리가 완료되었습니다!")
            sys.exit(0)
            
    except KeyboardInterrupt:
        logger.info("사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()