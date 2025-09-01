#!/usr/bin/env python3
"""
공고 처리 프로그램 - LangExtract 필드별 추출 버전

기존 모듈을 최대한 재사용하되, 실제 데이터 추출 부분만 LangExtract를 사용합니다.
각 필드(지원대상, 시행기관, 제목, 지원내용, 지원금액, 등록일, 접수기간, 모집일정)를 
개별적으로 추출하여 정확도를 높입니다.

사용법:
    python announcement_processor_langextract.py [디렉토리명] [사이트코드]
    
예시:
    python announcement_processor_langextract.py data.origin cbt
    python announcement_processor_langextract.py --data data.enhanced --site-code acci
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
from src.utils.langextractClient import LangExtractFieldAnalyzer

logger = setup_logging(__name__)
config = ConfigManager().get_config()


class AnnouncementProcessorLangExtract:
    """공고 처리 메인 클래스 - LangExtract 필드별 추출"""
    
    def __init__(self):
        self.attachment_processor = AttachmentProcessor()
        self.field_analyzer = LangExtractFieldAnalyzer()
    
    def process_directory(self, directory_path: Path, site_code: str) -> bool:
        """
        단일 디렉토리를 처리합니다. (LangExtract 사용)
        
        Args:
            directory_path: 처리할 디렉토리 경로
            site_code: 사이트 코드
            
        Returns:
            처리 성공 여부
        """
        folder_name = directory_path.name
        logger.info(f"디렉토리 처리 시작 (LangExtract): {folder_name}")
        
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
                    return False
            else:
                logger.warning(f"content.md 파일이 없음: {content_md_path}")
            
            # 2. 첨부파일 처리 및 전체 내용 결합
            try:
                combined_content = self.attachment_processor.get_all_content(directory_path)
                
                if not combined_content.strip():
                    logger.warning("처리할 내용이 없음")
                    return False
                
                logger.info(f"전체 내용 결합 완료: {len(combined_content)} 문자")
                
            except Exception as e:
                logger.error(f"첨부파일 처리 실패: {e}")
                return False
            
            # 3. 첨부파일 정보 수집
            attachment_info = self._collect_attachment_info(directory_path)
            
            # 4. LangExtract를 통한 필드별 정보 추출
            print("  📋 LangExtract 분석 중...")
            try:
                extracted_fields = self.field_analyzer.extract_all_fields(combined_content)
                
                # 5. 추출 결과를 화면에 출력
                self._display_extraction_results(folder_name, site_code, extracted_fields, attachment_info)
                
                logger.info("LangExtract 분석 완료")
                return True
                
            except Exception as e:
                print(f"  ❌ LangExtract 분석 오류: {str(e)[:100]}...")
                logger.error(f"LangExtract 분석 중 오류: {e}")
                return False
                
        except Exception as e:
            logger.error(f"디렉토리 처리 중 예상치 못한 오류: {e}")
            return False
    
    def _collect_attachment_info(self, directory_path: Path) -> List[Dict[str, Any]]:
        """첨부파일 정보를 수집합니다. (기존 로직 재사용)"""
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
        """파일 확장자에 따른 변환 방법을 추정합니다. (기존 로직 재사용)"""
        ext_lower = file_extension.lower()
        
        if ext_lower == '.pdf':
            return 'pdf_docling'
        elif ext_lower in ['.hwp', '.hwpx']:
            return 'hwp_markdown'
        elif ext_lower in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
            return 'ocr'
        else:
            return 'unknown'
    
    def _display_extraction_results(self, folder_name: str, site_code: str, extracted_fields: Dict[str, str], attachment_info: List[Dict[str, Any]]):
        """추출 결과를 화면에 출력합니다."""
        
        print(f"\n{'='*80}")
        print(f"📄 폴더: {folder_name} (사이트: {site_code})")
        print(f"{'='*80}")
        
        # LangExtract 필드별 추출 결과 출력
        print("\n🤖 LangExtract 필드별 추출 결과:")
        print("-" * 60)
        
        field_icons = {
            "제목": "📝",
            "시행기관": "🏛️", 
            "지원대상": "👥",
            "지원내용": "📋",
            "지원금액": "💰",
            "등록일": "📅",
            "접수기간": "⏰",
            "모집일정": "🗓️"
        }
        
        print(extracted_fields.items)
        
        for field, value in extracted_fields.items():
            icon = field_icons.get(field, "📌")
            status = "✓" if value != "찾을 수 없음" else "✗"
            
            print(value)

            if value != "찾을 수 없음":
                # 긴 내용은 잘라서 표시
                #display_value = value[:100] + "..." if len(value) > 100 else value
                display_value = value
                print(f"  {status} {icon} {field}: {display_value}")
            else:
                print(f"  {status} {icon} {field}: 찾을 수 없음")
        
        # 첨부파일 정보 출력
        if attachment_info:
            print(f"\n📎 첨부파일 정보:")
            print("-" * 60)
            for i, file_info in enumerate(attachment_info, 1):
                filename = file_info["filename"]
                extension = file_info["file_extension"]
                size_mb = file_info["file_size"] / (1024 * 1024)
                conversion_status = "✓" if file_info["conversion_success"] else "✗"
                
                print(f"  [{i}] {filename}{extension} ({size_mb:.1f}MB) - {conversion_status} {file_info['conversion_method']}")
        
        print(f"\n{'='*80}")
    
    def process_single_directory(self, directory_path: str, site_code: str) -> bool:
        """
        단일 디렉토리를 처리하는 편의 함수
        
        Args:
            directory_path: 처리할 디렉토리 경로 (문자열)
            site_code: 사이트 코드
            
        Returns:
            처리 성공 여부
        """
        path = Path(directory_path)
        if not path.exists():
            logger.error(f"디렉토리가 존재하지 않음: {directory_path}")
            return False
        
        return self.process_directory(path, site_code)
    
    def process_site_directories(self, base_dir: Path, site_code: str, recursive: bool = False) -> Dict[str, int]:
        """
        특정 사이트의 모든 디렉토리를 LangExtract로 처리합니다.
        
        Args:
            base_dir: 기본 디렉토리
            site_code: 사이트 코드
            recursive: 재귀적 처리 여부
            
        Returns:
            처리 결과 통계
        """
        # 처리할 디렉토리 목록 찾기
        target_directories = self._find_target_directories(base_dir, site_code, recursive)
        
        if not target_directories:
            logger.warning("처리할 디렉토리가 없습니다.")
            return {"total": 0, "success": 0, "failed": 0}
        
        total_count = len(target_directories)
        results = {"total": total_count, "success": 0, "failed": 0}
        
        print(f"\n{'='*80}")
        print(f"LangExtract 기반 공고 처리 시작: {site_code} ({total_count}개 폴더)")
        print(f"{'='*80}")
        
        # 시작 시간 기록
        start_time = time.time()
        
        for i, directory in enumerate(target_directories, 1):
            try:
                # 개별 항목 시작 시간
                item_start_time = time.time()
                
                folder_name = directory.name
                progress_pct = (i / total_count) * 100
                print(f"\n[{i}/{total_count} : {progress_pct:.1f}%] 처리 중: {folder_name}")
                
                success = self.process_directory(directory, site_code)
                
                # 개별 항목 처리 시간 계산
                item_elapsed = time.time() - item_start_time
                
                if success:
                    results["success"] += 1
                    print(f"  ✓ LangExtract 처리 완료 ({item_elapsed:.1f}초)")
                else:
                    results["failed"] += 1
                    print(f"  ✗ LangExtract 처리 실패 ({item_elapsed:.1f}초)")
                    
            except Exception as e:
                error_elapsed = time.time() - item_start_time
                results["failed"] += 1
                print(f"  ✗ 예외 발생: {str(e)[:100]}... ({error_elapsed:.1f}초)")
                logger.error(f"처리 중 오류 ({directory}): {e}")
        
        # 종료 시간 및 통계 계산
        end_time = time.time()
        total_elapsed = end_time - start_time
        
        print(f"\n{'='*80}")
        print(f"LangExtract 처리 완료: {results['success']}/{total_count} 성공 ({(results['success']/total_count)*100:.1f}%)")
        print(f"실패: {results['failed']}")
        print(f"")
        print(f"📊 처리 시간 통계:")
        print(f"   총 소요 시간: {total_elapsed:.1f}초 ({total_elapsed/60:.1f}분)")
        
        if total_count > 0:
            avg_time_per_item = total_elapsed / total_count
            print(f"   항목당 평균 시간: {avg_time_per_item:.1f}초")
        
        print(f"{'='*80}")
        
        logger.info(f"LangExtract 처리 완료 - 전체: {results['total']}, 성공: {results['success']}, 실패: {results['failed']}")
        
        return results
    
    def _find_target_directories(self, base_dir: Path, site_code: str, recursive: bool = False) -> List[Path]:
        """
        처리할 대상 디렉토리들을 찾습니다. (기존 로직 재사용)
        
        Args:
            base_dir: 기본 디렉토리
            site_code: 사이트 코드
            recursive: 재귀적 검색 여부
            
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
        
        logger.info(f"발견된 디렉토리: {len(target_directories)}개")
        return target_directories


def get_directory_and_site_code(args) -> tuple[Path, str]:
    """명령행 인자 또는 환경변수에서 디렉토리와 사이트코드를 가져옵니다. (기존 로직 재사용)"""
    
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
        description="LangExtract 기반 공고 필드별 추출 프로그램",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python announcement_processor_langextract.py --data data.enhanced --site-code acci
  python announcement_processor_langextract.py --data data.origin --site-code cbt
  python announcement_processor_langextract.py --site-code acci  # 환경변수 DEFAULT_DIR 사용
  python announcement_processor_langextract.py --data data.enhanced --site-code acci -r  # 재귀적 처리
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
        "-r", "--recursive",
        action="store_true",
        help="하위 디렉토리를 재귀적으로 처리 (모든 하위 경로의 content.md나 attachments를 찾아서 처리)"
    )
    
    # 단일 디렉토리 처리용 옵션
    parser.add_argument(
        "--single",
        type=str,
        help="단일 디렉토리만 처리 (전체 경로 지정)"
    )
    
    args = parser.parse_args()
    
    try:
        # 프로세서 초기화
        logger.info("LangExtract 기반 공고 처리 프로그램 시작")
        processor = AnnouncementProcessorLangExtract()
        
        # LangExtract + Ollama 연결 테스트
        print("🔗 LangExtract + Ollama 연결 테스트 중...")
        if not processor.field_analyzer.test_ollama_connection():
            print("❌ LangExtract + Ollama 연결 실패")
            print("다음을 확인해주세요:")
            print("1. Ollama가 실행 중인지 확인")
            print("2. ollama serve 명령으로 서버 시작") 
            print(f"3. 모델이 설치되었는지: ollama pull {processor.field_analyzer.model_id}")
            print(f"4. API URL이 올바른지: {processor.field_analyzer.model_url}")
            sys.exit(1)
        
        print("✓ LangExtract + Ollama 연결 성공")
        
        # 단일 디렉토리 처리 모드
        if args.single:
            logger.info(f"단일 디렉토리 처리 모드: {args.single}")
            success = processor.process_single_directory(args.single, args.site_code)
            
            if success:
                print("\n✅ 단일 디렉토리 처리 완료!")
                sys.exit(0)
            else:
                print("\n❌ 단일 디렉토리 처리 실패!")
                sys.exit(1)
        
        # 다중 디렉토리 처리 모드
        base_directory, site_code = get_directory_and_site_code(args)
        
        # 처리 실행
        results = processor.process_site_directories(base_directory, site_code, args.recursive)
        
        # 결과 출력
        print(f"\n=== 최종 요약 ===")
        print(f"전체 대상: {results['total']}개")
        print(f"처리 성공: {results['success']}개") 
        print(f"처리 실패: {results['failed']}개")
        
        if results['failed'] > 0:
            print(f"\n실패한 항목이 {results['failed']}개 있습니다. 로그를 확인해주세요.")
            sys.exit(1)
        else:
            print("\n모든 LangExtract 처리가 완료되었습니다!")
            sys.exit(0)
            
    except KeyboardInterrupt:
        logger.info("사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()