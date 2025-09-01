#!/usr/bin/env python3
"""
공고 처리 메인 프로그램 - RAG 시스템 통합 버전

ChromaDB를 이용한 RAG(Retrieval-Augmented Generation) 시스템을 통해
기존 공고 데이터를 활용하여 더 정확한 분석을 수행합니다.

사용법:
    python announcement_processor_rag.py [디렉토리명] [사이트코드]
    
예시:
    python announcement_processor_rag.py data.origin cbt
    python announcement_processor_rag.py  # 환경변수 사용
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.config import ConfigManager
from src.config.logConfig import setup_logging
from src.utils.attachmentProcessor import AttachmentProcessor
from src.utils.ollamaClientRag import AnnouncementAnalyzerRAG
from src.models.announcementDatabaseRag import AnnouncementDatabaseManagerRAG, create_announcement_tables

logger = setup_logging(__name__)
config = ConfigManager().get_config()


class AnnouncementProcessorRAG:
    """공고 처리 메인 클래스 - RAG 시스템 통합"""
    
    def __init__(self):
        self.attachment_processor = AttachmentProcessor()
        self.announcement_analyzer = AnnouncementAnalyzerRAG()
        self.db_manager = AnnouncementDatabaseManagerRAG()
        
        # 데이터베이스 테이블 생성 (없는 경우)
        self._ensure_database_tables()
    
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
    
    def process_directory(self, directory_path: Path, site_code: str) -> bool:
        """
        단일 디렉토리를 처리합니다. (RAG 시스템 적용)
        
        Args:
            directory_path: 처리할 디렉토리 경로
            site_code: 사이트 코드
            
        Returns:
            처리 성공 여부
        """
        folder_name = directory_path.name
        logger.info(f"디렉토리 처리 시작 (RAG): {folder_name}")
        
        try:
            # 1. content.md 파일 읽기
            content_md_path = directory_path / "content.md"
            content_md = ""
            
            if content_md_path.exists():
                try:
                    with open(content_md_path, 'r', encoding='utf-8') as f:
                        content_md = f.read()
                    logger.info(f"content.md 읽기 완료: {len(content_md)} 문자")
                except Exception as e:
                    logger.error(f"content.md 읽기 실패: {e}")
                    self.db_manager.save_processing_error(
                        folder_name, site_code, f"content.md 읽기 실패: {e}"
                    )
                    return False
            else:
                logger.warning(f"content.md 파일이 없음: {content_md_path}")
            
            # 2. 첨부파일 처리 및 전체 내용 결합
            try:
                combined_content = self.attachment_processor.get_all_content(directory_path)
                
                if not combined_content.strip():
                    logger.warning("처리할 내용이 없음")
                    self.db_manager.save_processing_error(
                        folder_name, site_code, "처리할 내용이 없음", content_md
                    )
                    return False
                
                logger.info(f"전체 내용 결합 완료: {len(combined_content)} 문자")
                
            except Exception as e:
                logger.error(f"첨부파일 처리 실패: {e}")
                self.db_manager.save_processing_error(
                    folder_name, site_code, f"첨부파일 처리 실패: {e}", content_md
                )
                return False
            
            # 3. RAG 기반 Ollama 분석
            print("  🔍 RAG 기반 Ollama 분석 중...")
            try:
                ollama_response, ollama_prompt, rag_context = self.announcement_analyzer.analyze_announcement_with_rag(
                    combined_content, site_code
                )
                
                # 분석 실패 확인
                if "error" in ollama_response:
                    error_msg = ollama_response["error"]
                    print(f"  ❌ RAG Ollama 분석 실패: {error_msg}")
                    logger.error(f"RAG Ollama 분석 실패: {error_msg}")
                    
                    # 실패해도 프롬프트와 기본 정보는 저장
                    try:
                        record_id = self.db_manager.save_announcement_processing(
                            folder_name=folder_name,
                            site_code=site_code,
                            content_md=content_md,
                            combined_content=combined_content,
                            ollama_response=ollama_response,  # 에러 정보 포함
                            ollama_prompt=ollama_prompt,
                            attachment_files=[],
                            rag_context=rag_context,
                            update_if_exists=True,
                            processing_status="failed",  # 실패 상태로 직접 설정
                            error_message=error_msg
                        )
                        
                        if record_id:
                            logger.info(f"실패 정보 저장 완료: ID {record_id}")
                        
                    except Exception as save_error:
                        logger.error(f"실패 정보 저장 중 오류: {save_error}")
                        self.db_manager.save_processing_error(
                            folder_name, site_code, f"RAG Ollama 분석 실패: {error_msg}", 
                            content_md, combined_content
                        )
                    
                    return False
                
                # RAG 분석 결과를 화면에 표시
                print("  🤖 RAG 기반 Ollama 분석 결과:")
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
                
                if rag_context and rag_context.get("similar_announcements"):
                    print(f"     🔍 유사 공고 참조: {len(rag_context['similar_announcements'])}개")
                    
                logger.info("RAG 기반 Ollama 분석 완료")
                
            except Exception as e:
                print(f"  ❌ RAG Ollama 분석 오류: {str(e)[:100]}...")
                logger.error(f"RAG Ollama 분석 중 오류: {e}")
                self.db_manager.save_processing_error(
                    folder_name, site_code, f"RAG Ollama 분석 오류: {e}", 
                    content_md, combined_content
                )
                return False
            
            # 4. 첨부파일 정보 수집
            attachment_info = self._collect_attachment_info(directory_path)
            
            # 5. 데이터베이스에 저장 (RAG 컨텍스트 포함)
            try:
                record_id = self.db_manager.save_announcement_processing(
                    folder_name=folder_name,
                    site_code=site_code,
                    content_md=content_md,
                    combined_content=combined_content,
                    ollama_response=ollama_response,
                    ollama_prompt=ollama_prompt,
                    attachment_files=attachment_info,
                    rag_context=rag_context,
                    update_if_exists=True  # UPSERT 로직 사용
                )
                
                if record_id:
                    logger.info(f"RAG 데이터베이스 저장 완료: ID {record_id}")
                    
                    # ChromaDB에 벡터 임베딩 저장
                    self.db_manager.store_vector_embedding(
                        record_id, combined_content, ollama_response, site_code
                    )
                    
                    return True
                else:
                    logger.error("RAG 데이터베이스 저장 실패")
                    return False
                    
            except Exception as e:
                logger.error(f"RAG 데이터베이스 저장 중 오류: {e}")
                return False
                
        except Exception as e:
            logger.error(f"디렉토리 처리 중 예상치 못한 오류: {e}")
            self.db_manager.save_processing_error(
                folder_name, site_code, f"예상치 못한 오류: {e}"
            )
            return False
    
    def _collect_attachment_info(self, directory_path: Path) -> List[Dict[str, Any]]:
        """첨부파일 정보를 수집합니다."""
        attachment_info = []
        attachments_dir = directory_path / "attachments"
        
        if not attachments_dir.exists():
            return attachment_info
        
        try:
            # 첨부파일 처리 결과 가져오기
            attachment_results = self.attachment_processor.process_directory_attachments(directory_path)
            
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
                    converted_content = attachment_results.get(filename, "")
                    conversion_success = bool(converted_content)
                    
                    # 변환 방법 추정
                    conversion_method = self._guess_conversion_method(file_extension)
                    
                    attachment_info.append({
                        "filename": filename,
                        "file_extension": file_extension,
                        "file_path": str(file_path),
                        "file_size": file_size,
                        "converted_content": converted_content,
                        "conversion_method": conversion_method,
                        "conversion_success": conversion_success
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
            # 기본 동작: 사이트 디렉토리의 직접 하위 디렉토리만 검색
            target_directories = [
                d for d in site_dir.iterdir() 
                if d.is_dir()
            ]
        
        # force 옵션이 없을 때만 이미 처리된 폴더 제외
        if not force:
            processed_folders = set(self.db_manager.get_processed_folders(site_code))
            
            filtered_directories = []
            for directory in target_directories:
                # 사이트 디렉토리로부터의 상대 경로를 폴더명으로 사용
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
            # force 옵션이 있으면 모든 디렉토리 반환
            logger.info(f"--force 옵션: 모든 디렉토리 처리 ({len(target_directories)}개)")
            return target_directories
    
    def process_site_directories(self, base_dir: Path, site_code: str, recursive: bool = False, force: bool = False) -> Dict[str, int]:
        """
        특정 사이트의 모든 디렉토리를 RAG 시스템으로 처리합니다.
        
        Args:
            base_dir: 기본 디렉토리
            site_code: 사이트 코드
            recursive: 재귀적 처리 여부
            force: 이미 처리된 항목도 다시 처리할지 여부
            
        Returns:
            처리 결과 통계
        """
        # 처리할 디렉토리 목록 찾기
        target_directories = self._find_target_directories(base_dir, site_code, recursive, force)
        
        if not target_directories:
            logger.warning("처리할 디렉토리가 없습니다.")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        
        total_count = len(target_directories)
        results = {"total": total_count, "success": 0, "failed": 0, "skipped": 0}
        site_dir = base_dir / site_code
        
        print(f"\n{'='*60}")
        print(f"RAG 기반 공고 처리 시작: {site_code} ({total_count}개 폴더)")
        print(f"{'='*60}")
        
        # 시작 시간 기록
        start_time = time.time()
        
        for i, directory in enumerate(target_directories, 1):
            try:
                # 개별 항목 시작 시간
                item_start_time = time.time()
                
                # 사이트 디렉토리로부터의 상대 경로를 폴더명으로 사용
                relative_path = directory.relative_to(site_dir)
                folder_name = str(relative_path).replace("/", "_")  # 슬래시를 언더스코어로 변경
                
                progress_pct = (i / total_count) * 100
                print(f"\n[{i}/{total_count} : {progress_pct:.1f}%] {folder_name}")
                
                # 이미 처리된 항목 확인 (force 옵션이 없을 때만)
                if not force and self.db_manager.is_already_processed(folder_name, site_code):
                    skip_elapsed = time.time() - item_start_time
                    print(f"  ✓ 이미 처리됨, 건너뜀 ({skip_elapsed:.1f}초)")
                    results["skipped"] += 1
                    continue
                elif force and self.db_manager.is_already_processed(folder_name, site_code):
                    print("  🔄 이미 처리됨, --force 옵션으로 재처리")
                
                success = self.process_directory_with_custom_name(directory, site_code, folder_name)
                
                # 개별 항목 처리 시간 계산
                item_elapsed = time.time() - item_start_time
                
                if success:
                    results["success"] += 1
                    print(f"  ✓ RAG 처리 완료 ({item_elapsed:.1f}초)")
                else:
                    results["failed"] += 1
                    print(f"  ✗ RAG 처리 실패 ({item_elapsed:.1f}초)")
                    
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
        print(f"RAG 처리 완료: {results['success']}/{total_count} 성공 ({(results['success']/total_count)*100:.1f}%)")
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
        
        logger.info(f"RAG 처리 완료 - 전체: {results['total']}, 성공: {results['success']}, 실패: {results['failed']}, 건너뜀: {results['skipped']}")
        
        return results
    
    def process_directory_with_custom_name(self, directory_path: Path, site_code: str, folder_name: str) -> bool:
        """
        사용자 정의 폴더명으로 디렉토리를 RAG 시스템으로 처리합니다.
        
        Args:
            directory_path: 처리할 디렉토리 경로
            site_code: 사이트 코드
            folder_name: 데이터베이스에 저장할 폴더명
            
        Returns:
            처리 성공 여부
        """
        return self.process_directory(directory_path, site_code)


def get_directory_and_site_code(args) -> tuple[Path, str]:
    """명령행 인자 또는 환경변수에서 디렉토리와 사이트코드를 가져옵니다."""
    
    # 디렉토리 결정
    if args.data:
        directory_name = args.data
    else:
        # 환경변수에서 가져오기
        directory_name = os.getenv("DEFAULT_DIR", "data")
    
    # 사이트 코드 결정
    if not args.site_code:
        logger.error("사이트 코드가 지정되지 않았습니다.")
        sys.exit(1)
    
    site_code = args.site_code
    
    # 현재 디렉토리 기준으로 경로 생성
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
        description="RAG 기반 공고 첨부파일 처리 및 분석 프로그램",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python announcement_processor_rag.py --data data.enhanced --site-code acci
  python announcement_processor_rag.py --data data.origin --site-code cbt
  python announcement_processor_rag.py --site-code acci  # 환경변수 DEFAULT_DIR 사용
  python announcement_processor_rag.py --data data.enhanced --site-code acci -r  # 재귀적 처리
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
    
    args = parser.parse_args()
    
    try:
        # 디렉토리와 사이트코드 결정
        base_directory, site_code = get_directory_and_site_code(args)
        
        # 프로세서 초기화
        logger.info("RAG 기반 공고 처리 프로그램 시작")
        processor = AnnouncementProcessorRAG()
        
        # 처리 실행
        results = processor.process_site_directories(base_directory, site_code, args.recursive, args.force)
        
        # 결과 출력
        print(f"\n=== 최종 요약 ===")
        print(f"전체 대상: {results['total']}개")
        print(f"처리 성공: {results['success']}개") 
        print(f"처리 실패: {results['failed']}개")
        print(f"건너뛴 항목: {results['skipped']}개")
        
        if results['failed'] > 0:
            print(f"\n실패한 항목이 {results['failed']}개 있습니다. 로그를 확인해주세요.")
            sys.exit(1)
        else:
            print("\n모든 RAG 처리가 완료되었습니다!")
            sys.exit(0)
            
    except KeyboardInterrupt:
        logger.info("사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()