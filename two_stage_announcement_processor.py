"""
2단계 Ollama 공고 처리기

기존 소스를 참조하여 2단계 Ollama 처리를 구현:
1단계: 간단한 정보 추출 (지원대상, 지원금액, 제목 등)
2단계: 개인이 아닌 경우 정밀한 구조화된 데이터 추출
"""

import os
import sys
import time
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any

# 환경변수 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 프로젝트 루트 경로 추가
current_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(current_dir))

try:
    from src.config.config import ConfigManager
    from src.config.logConfig import setup_logging
    from src.utils.twoStageOllamaClient import TwoStageOllamaClient
    from src.utils.attachmentProcessor import AttachmentProcessor
    from src.models.twoStageDatabase import TwoStageDatabaseManager
except ImportError as e:
    print(f"Import 오류: {e}")
    print("필요한 모듈들을 확인해주세요.")
    sys.exit(1)

# 로깅 설정
import logging
log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO)
logger = setup_logging(__name__, log_level)


class TwoStageAnnouncementProcessor:
    """2단계 Ollama 공고 처리기"""
    
    def __init__(self, input_dir: str, force: bool = False):
        self.input_dir = Path(input_dir)
        self.force = force
        
        # 구성 요소 초기화
        self.config = ConfigManager().get_config()
        self.db_manager = TwoStageDatabaseManager()
        self.attachment_processor = AttachmentProcessor()
        self.ollama_client = TwoStageOllamaClient()
        
        logger.info(f"2단계 공고 처리기 초기화 완료")
        logger.info(f"입력 디렉토리: {self.input_dir}")
        logger.info(f"강제 처리: {self.force}")
    
    def _find_target_directories(self, site_code: str, recursive: bool = False, force: bool = False) -> List[Path]:
        """
        처리할 대상 디렉토리들을 찾습니다.
        
        Args:
            site_code: 사이트 코드
            recursive: 재귀적 검색 여부
            force: 이미 처리된 항목도 포함할지 여부
            
        Returns:
            처리할 디렉토리 경로 리스트
        """
        logger.info(f"사이트 {site_code}의 대상 디렉토리 검색 중 (재귀적: {recursive})")
        
        site_path = self.input_dir / site_code
        if not site_path.exists():
            logger.warning(f"사이트 디렉토리를 찾을 수 없음: {site_path}")
            return []
        
        target_dirs = []
        
        if recursive:
            # 재귀적으로 content.md나 attachments 폴더가 있는 디렉토리 찾기
            for root_path in site_path.rglob("*"):
                if root_path.is_dir():
                    # content.md 파일이 있거나 attachments 폴더가 있는 디렉토리 찾기
                    has_content = (root_path / "content.md").exists()
                    has_attachments = (root_path / "attachments").exists() and (root_path / "attachments").is_dir()
                    
                    if has_content or has_attachments:
                        # 사이트 디렉토리로부터의 상대 경로를 폴더명으로 사용
                        relative_path = root_path.relative_to(site_path)
                        folder_name = str(relative_path).replace("/", "_")
                        
                        if force or not self.db_manager.is_already_processed(folder_name, site_code):
                            target_dirs.append(root_path)
                            logger.debug(f"재귀 검색으로 발견: {folder_name}")
                        else:
                            logger.debug(f"이미 처리된 폴더 건너뜀: {folder_name}")
        else:
            # 비재귀적으로 직접 하위 디렉토리만 검색
            for item in site_path.iterdir():
                if item.is_dir():
                    folder_name = item.name
                    if force or not self.db_manager.is_already_processed(folder_name, site_code):
                        target_dirs.append(item)
                    else:
                        logger.debug(f"이미 처리된 폴더 건너뜀: {folder_name}")
        
        logger.info(f"발견된 대상 디렉토리: {len(target_dirs)}개")
        return sorted(target_dirs)
    
    def _read_content_and_attachments(self, folder_path: Path) -> tuple[str, str]:
        """content.md와 첨부파일들을 읽어서 반환합니다 (attachment_files 테이블 저장은 생략)."""
        logger.debug(f"폴더 내용 읽기: {folder_path}")
        
        # content.md 읽기
        content_md_path = folder_path / "content.md"
        content_md = ""
        if content_md_path.exists():
            try:
                with open(content_md_path, 'r', encoding='utf-8') as f:
                    content_md = f.read()
                logger.debug(f"content.md 읽기 성공: {len(content_md)} 문자")
            except Exception as e:
                logger.error(f"content.md 읽기 실패: {e}")
        else:
            logger.warning(f"content.md 파일이 없음: {content_md_path}")
        
        # 첨부파일들과 결합된 내용 가져오기
        combined_content = self.attachment_processor.get_all_content(folder_path)
        
        logger.debug(f"결합된 내용 길이: {len(combined_content)} 문자")
        
        return content_md, combined_content
    
    def _save_processing_results(self, folder_name: str, site_code: str, content_md: str, 
                               combined_content: str, ollama_result: Dict[str, Any]) -> Optional[int]:
        """전체 처리 결과를 데이터베이스에 저장합니다."""
        try:
            logger.debug("처리 결과 데이터베이스 저장 중...")
            
            stage1_result = ollama_result["stage1_result"]
            stage1_prompt = ollama_result["stage1_prompt"]
            stage1_duration = ollama_result["stage1_duration"]
            
            stage2_result = ollama_result.get("stage2_result")
            stage2_prompt = ollama_result.get("stage2_prompt", "")
            stage2_duration = ollama_result.get("stage2_duration", 0.0)
            stage2_executed = ollama_result.get("stage2_executed", False)
            
            # 전체 결과 저장
            record_id = self.db_manager.save_processing_result(
                folder_name=folder_name,
                site_code=site_code,
                content_md=content_md,
                combined_content=combined_content,
                stage1_result=stage1_result,
                stage1_prompt=stage1_prompt,
                stage1_duration=stage1_duration,
                stage2_result=stage2_result,
                stage2_prompt=stage2_prompt,
                stage2_duration=stage2_duration,
                stage2_executed=stage2_executed,
                update_if_exists=self.force
            )
            
            if record_id:
                logger.info(f"처리 결과 저장 완료: ID {record_id}")
            else:
                logger.error("처리 결과 저장 실패")
                
            return record_id
                    
        except Exception as e:
            logger.error(f"처리 결과 저장 중 오류: {e}")
            return None
    
    def _process_single_folder(self, folder_path: Path, site_code: str) -> bool:
        """단일 폴더를 처리합니다."""
        folder_name = folder_path.name
        logger.info(f"폴더 처리 시작: {folder_name}")
        
        record_id = None
        
        try:
            # 1. content.md와 첨부파일 읽기 (attachment_files 테이블 저장은 생략)
            content_md, combined_content = self._read_content_and_attachments(folder_path)
            
            if not combined_content.strip():
                logger.warning(f"처리할 내용이 없음: {folder_name}")
                return False
            
            # 2. 파일 읽기 완료 후 초기 레코드 생성 (먼저 INSERT)
            logger.info("📍 데이터베이스 초기 레코드 생성 중...")
            record_id = self.db_manager.create_initial_record(
                folder_name=folder_name,
                site_code=site_code,
                content_md=content_md,
                combined_content=combined_content,
                update_if_exists=self.force
            )
            
            if not record_id:
                logger.error(f"초기 레코드 생성 실패: {folder_name}")
                return False
            
            logger.info(f"✅ 초기 레코드 생성 완료: ID {record_id}")
            
            # 3. 1단계 Ollama 처리
            logger.info("🤖 1단계 Ollama 분석 시작...")
            stage1_result, stage1_prompt, stage1_duration = self.ollama_client.stage1_simple_analysis(combined_content)
            
            # 4. 1단계 완료 후 UPDATE
            logger.info("📍 1단계 결과로 데이터베이스 업데이트 중...")
            if not self.db_manager.update_stage1_result(record_id, stage1_result, stage1_prompt, stage1_duration):
                logger.error(f"1단계 결과 업데이트 실패: {folder_name}")
                return False
            
            logger.info(f"✅ 1단계 결과 업데이트 완료 ({stage1_duration:.2f}초)")
            
            # 5. 2단계 실행 여부 판단
            target_classification = stage1_result.get("지원대상분류", [])
            if not target_classification:
                target_classification = []
            
            # "개인"만 있는 경우가 아니면 2단계 실행
            should_run_stage2 = not (len(target_classification) == 1 and "개인" in target_classification)
            
            if should_run_stage2:
                # 6. 2단계 Ollama 처리
                logger.info("🤖 2단계 Ollama 분석 시작...")
                stage2_result, stage2_prompt, stage2_duration = self.ollama_client.stage2_format_analysis(combined_content)
                
                # 7. 2단계 완료 후 UPDATE
                logger.info("📍 2단계 결과로 데이터베이스 업데이트 중...")
                if not self.db_manager.update_stage2_result(record_id, stage2_result, stage2_prompt, stage2_duration):
                    logger.error(f"2단계 결과 업데이트 실패: {folder_name}")
                    return False
                
                logger.info(f"✅ 2단계 결과 업데이트 완료 ({stage2_duration:.2f}초)")
                total_duration = stage1_duration + stage2_duration
            else:
                # 8. 2단계 없이 완료 처리
                logger.info("지원대상이 개인이므로 2단계 생략")
                if not self.db_manager.mark_completed_without_stage2(record_id):
                    logger.error(f"완료 처리 실패: {folder_name}")
                    return False
                
                logger.info("✅ 2단계 없이 완료 처리")
                total_duration = stage1_duration
            
            logger.info(f"폴더 처리 완료: {folder_name} (총 {total_duration:.2f}초)")
            return True
            
        except Exception as e:
            logger.error(f"폴더 처리 중 오류 ({folder_name}): {e}")
            
            # 이미 레코드가 생성된 경우 오류 상태로 업데이트
            if record_id:
                try:
                    with self.db_manager.SessionLocal() as session:
                        from src.models.twoStageDatabase import TwoStageAnnouncementProcessing
                        record = session.get(TwoStageAnnouncementProcessing, record_id)
                        if record:
                            record.processing_status = "failed"
                            record.error_message = str(e)
                            session.commit()
                            logger.info(f"레코드를 오류 상태로 업데이트: ID {record_id}")
                except Exception as update_error:
                    logger.error(f"오류 상태 업데이트 실패: {update_error}")
            else:
                # 레코드가 생성되지 않은 경우 오류 정보 저장
                self.db_manager.save_processing_error(
                    folder_name=folder_name,
                    site_code=site_code,
                    error_message=str(e)
                )
            return False
    
    def process_site_directories(self, site_codes: List[str] = None, recursive: bool = False) -> Dict[str, int]:
        """
        특정 사이트의 모든 디렉토리를 처리합니다.
        
        Args:
            site_codes: 처리할 사이트 코드 리스트
            recursive: 재귀적 처리 여부
            
        Returns:
            처리 결과 통계
        """
        if site_codes is None:
            site_codes = [item.name for item in self.input_dir.iterdir() 
                         if item.is_dir() and not item.name.startswith('.')]
        
        logger.info(f"처리할 사이트: {site_codes}")
        
        all_results = {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        
        for site_code in site_codes:
            logger.info(f"\\n{'='*50}")
            logger.info(f"사이트 처리 시작: {site_code}")
            logger.info(f"{'='*50}")
            
            target_directories = self._find_target_directories(site_code, recursive=recursive, force=self.force)
            total_count = len(target_directories)
            
            if total_count == 0:
                logger.info(f"사이트 {site_code}에 처리할 디렉토리가 없음")
                continue
            
            results = {"total": total_count, "success": 0, "failed": 0, "skipped": 0}
            site_dir = self.input_dir / site_code
            
            print(f"\\n{'='*60}")
            print(f"2단계 공고 처리 시작: {site_code} ({total_count}개 폴더)")
            print(f"{'='*60}")
            
            total_start_time = time.time()
            
            for i, directory in enumerate(target_directories, 1):
                try:
                    # 개별 항목 시작 시간
                    item_start_time = time.time()
                    
                    # 사이트 디렉토리로부터의 상대 경로를 폴더명으로 사용
                    relative_path = directory.relative_to(site_dir)
                    folder_name = str(relative_path).replace("/", "_")  # 슬래시를 언더스코어로 변경
                    
                    progress_pct = (i / total_count) * 100
                    
                    print(f"\\n[{i}/{total_count} : {progress_pct:.1f}%] {folder_name}")
                    print("🤖 2단계 Ollama 분석 중...")
                    
                    if self._process_single_folder(directory, site_code):
                        results["success"] += 1
                        print("✅ 2단계 처리 완료")
                    else:
                        results["failed"] += 1
                        print("❌ 2단계 처리 실패")
                    
                    item_duration = time.time() - item_start_time
                    print(f"⏱️ 소요시간: {item_duration:.2f}초")
                    
                except Exception as e:
                    logger.error(f"폴더 처리 중 예외 발생 ({directory}): {e}")
                    results["failed"] += 1
                    print("❌ 처리 중 예외 발생")
            
            # 사이트별 결과 업데이트
            all_results["total"] += results["total"]
            all_results["success"] += results["success"] 
            all_results["failed"] += results["failed"]
            all_results["skipped"] += results["skipped"]
            
            # 사이트 처리 완료 통계
            total_duration = time.time() - total_start_time
            avg_duration = total_duration / total_count if total_count > 0 else 0
            
            print(f"\\n{'='*60}")
            print(f"사이트 {site_code} 2단계 처리 완료")
            print(f"{'='*60}")
            print(f"📊 처리 결과:")
            print(f"  - 성공: {results['success']}건")
            print(f"  - 실패: {results['failed']}건")  
            print(f"  - 전체: {results['total']}건")
            print(f"⏱️ 시간 통계:")
            print(f"  - 총 소요시간: {total_duration:.2f}초")
            print(f"  - 평균 소요시간: {avg_duration:.2f}초/건")
        
        return all_results


def get_directory_and_site_code(args):
    """디렉토리 이름과 사이트 코드를 결정합니다."""
    # 데이터 디렉토리 결정
    if args.data:
        directory_name = args.data
    else:
        directory_name = os.getenv("DEFAULT_DIR", "data")
    
    if not directory_name:
        logger.error("데이터 디렉토리를 지정해주세요 (--data 옵션 또는 DEFAULT_DIR 환경변수)")
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
        description="2단계 Ollama 공고 처리 프로그램",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python two_stage_announcement_processor.py --data data.enhanced --site-code acci
  python two_stage_announcement_processor.py --data data.origin --site-code cbt
  python two_stage_announcement_processor.py --site-code acci  # 환경변수 DEFAULT_DIR 사용
  python two_stage_announcement_processor.py --data data.enhanced --site-code acci -r  # 재귀적 처리
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
        logger.info("2단계 Ollama 공고 처리 프로그램 시작")
        processor = TwoStageAnnouncementProcessor(
            input_dir=str(base_directory),
            force=args.force
        )
        
        # 처리 실행
        results = processor.process_site_directories(
            site_codes=[site_code], 
            recursive=args.recursive
        )
        
        # 결과 출력
        print(f"\n=== 최종 요약 ===")
        print(f"전체 대상: {results.get('total', 0)}개")
        print(f"처리 성공: {results.get('success', 0)}개") 
        print(f"처리 실패: {results.get('failed', 0)}개")
        print(f"건너뛴 항목: {results.get('skipped', 0)}개")
        
        if results.get('failed', 0) > 0:
            print(f"\n실패한 항목이 {results['failed']}개 있습니다. 로그를 확인해주세요.")
            sys.exit(1)
        else:
            print("\n모든 2단계 처리가 완료되었습니다!")
            sys.exit(0)
            
    except KeyboardInterrupt:
        logger.info("사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류: {e}")
        import traceback
        logger.error(f"상세 오류: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()