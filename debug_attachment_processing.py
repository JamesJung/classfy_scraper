#!/usr/bin/env python3
"""
첨부파일 처리 디버그 스크립트
Linux 환경에서 첨부파일이 처리되지 않는 문제 진단용
"""

import os
import sys
import platform
from pathlib import Path
import logging
import traceback

# 로깅 설정
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_environment():
    """실행 환경 확인"""
    print("\n" + "="*60)
    print("실행 환경 정보")
    print("="*60)
    print(f"운영체제: {platform.system()} {platform.release()}")
    print(f"Python 버전: {sys.version}")
    print(f"현재 디렉토리: {os.getcwd()}")
    print(f"실행 경로: {sys.executable}")
    print()

def check_dependencies():
    """필수 의존성 확인"""
    print("\n" + "="*60)
    print("의존성 확인")
    print("="*60)
    
    dependencies = {
        'pypandoc': False,
        'pdfplumber': False,
        'docling': False,
        'markitdown': False,
        'PIL': False,
        'pytesseract': False,
        'cv2': False,
    }
    
    for module_name in dependencies:
        try:
            if module_name == 'PIL':
                import PIL
                dependencies[module_name] = PIL.__version__
            elif module_name == 'cv2':
                import cv2
                dependencies[module_name] = cv2.__version__
            elif module_name == 'pytesseract':
                import pytesseract
                dependencies[module_name] = pytesseract.get_tesseract_version()
            else:
                module = __import__(module_name)
                dependencies[module_name] = getattr(module, '__version__', 'Installed')
            print(f"✅ {module_name}: {dependencies[module_name]}")
        except ImportError as e:
            print(f"❌ {module_name}: Not installed ({e})")
        except Exception as e:
            print(f"⚠️ {module_name}: Error checking ({e})")
    
    # 시스템 명령어 확인
    print("\n시스템 명령어 확인:")
    commands = ['pandoc', 'tesseract', 'hwp5txt']
    for cmd in commands:
        result = os.system(f"which {cmd} > /dev/null 2>&1")
        if result == 0:
            print(f"✅ {cmd}: Found")
        else:
            print(f"❌ {cmd}: Not found")
    
    return dependencies

def test_attachment_processor():
    """AttachmentProcessor 클래스 테스트"""
    print("\n" + "="*60)
    print("AttachmentProcessor 테스트")
    print("="*60)
    
    try:
        # AttachmentProcessor import 시도
        logger.info("AttachmentProcessor import 시도...")
        from src.utils.attachmentProcessor import AttachmentProcessor
        logger.info("✅ AttachmentProcessor import 성공")
        
        # 인스턴스 생성
        logger.info("AttachmentProcessor 인스턴스 생성...")
        processor = AttachmentProcessor()
        logger.info("✅ 인스턴스 생성 성공")
        
        # OCR 프로세서 확인
        if hasattr(processor, 'ocr_processor'):
            if processor.ocr_processor is None:
                logger.warning("⚠️ OCR processor가 None입니다")
            else:
                logger.info("✅ OCR processor 활성화됨")
        
        return processor
        
    except ImportError as e:
        logger.error(f"❌ AttachmentProcessor import 실패: {e}")
        logger.error(traceback.format_exc())
        return None
    except Exception as e:
        logger.error(f"❌ AttachmentProcessor 생성 실패: {e}")
        logger.error(traceback.format_exc())
        return None

def find_test_directory(base_path: str = "eminwon_data_new/2025-09-28"):
    """테스트용 디렉토리 찾기"""
    print("\n" + "="*60)
    print("테스트 디렉토리 검색")
    print("="*60)
    
    base = Path(base_path)
    if not base.exists():
        logger.error(f"❌ 디렉토리가 없습니다: {base_path}")
        return None
    
    # 첨부파일이 있는 디렉토리 찾기
    test_dirs = []
    for region_dir in base.iterdir():
        if region_dir.is_dir():
            for announce_dir in region_dir.iterdir():
                if announce_dir.is_dir():
                    attachments_dir = announce_dir / "attachments"
                    if attachments_dir.exists():
                        files = list(attachments_dir.iterdir())
                        if files:
                            test_dirs.append({
                                'path': announce_dir,
                                'attachments': len(files),
                                'files': [f.name for f in files[:3]]  # 처음 3개만
                            })
                            if len(test_dirs) >= 3:  # 3개만 찾기
                                break
            if len(test_dirs) >= 3:
                break
    
    if test_dirs:
        print(f"✅ {len(test_dirs)}개의 테스트 디렉토리 발견:")
        for td in test_dirs:
            print(f"  - {td['path']}")
            print(f"    첨부파일: {td['attachments']}개")
            print(f"    예시: {', '.join(td['files'])}")
        return test_dirs[0]['path']
    else:
        logger.error("❌ 첨부파일이 있는 디렉토리를 찾을 수 없습니다")
        return None

def test_file_processing(processor, test_path):
    """실제 파일 처리 테스트"""
    print("\n" + "="*60)
    print("파일 처리 테스트")
    print("="*60)
    
    if not processor or not test_path:
        logger.error("테스트를 실행할 수 없습니다")
        return
    
    attachments_dir = test_path / "attachments"
    
    # 첫 번째 파일로 테스트
    test_file = None
    for f in attachments_dir.iterdir():
        if f.is_file() and f.suffix.lower() in ['.pdf', '.hwp', '.png', '.jpg']:
            test_file = f
            break
    
    if not test_file:
        logger.error("테스트할 파일이 없습니다")
        return
    
    logger.info(f"테스트 파일: {test_file.name} ({test_file.suffix})")
    
    try:
        logger.info("process_single_file 호출...")
        content = processor.process_single_file(test_file)
        
        if content:
            logger.info(f"✅ 처리 성공! 내용 길이: {len(content)} 문자")
            logger.info(f"처음 100자: {content[:100]}...")
            
            # .md 파일 저장 테스트
            md_path = attachments_dir / f"{test_file.stem}.md"
            logger.info(f"MD 파일 저장 테스트: {md_path}")
            try:
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info("✅ MD 파일 저장 성공")
            except Exception as e:
                logger.error(f"❌ MD 파일 저장 실패: {e}")
        else:
            logger.warning("⚠️ 처리는 성공했지만 내용이 비어있습니다")
            
    except Exception as e:
        logger.error(f"❌ 파일 처리 실패: {e}")
        logger.error(traceback.format_exc())

def main():
    """메인 함수"""
    print("\n" + "="*80)
    print("첨부파일 처리 디버그 스크립트")
    print("="*80)
    
    # 1. 환경 확인
    check_environment()
    
    # 2. 의존성 확인
    deps = check_dependencies()
    
    # 3. AttachmentProcessor 테스트
    processor = test_attachment_processor()
    
    # 4. 테스트 디렉토리 찾기
    test_path = find_test_directory()
    
    # 5. 실제 파일 처리 테스트
    if processor and test_path:
        test_file_processing(processor, test_path)
    
    print("\n" + "="*80)
    print("디버그 완료")
    print("="*80)
    print("\n문제가 발견되면 위 로그를 확인하세요.")
    print("특히 다음 사항을 확인하세요:")
    print("1. 필수 패키지 설치 여부 (pypandoc, pdfplumber, tesseract 등)")
    print("2. 시스템 명령어 설치 여부 (pandoc, tesseract)")
    print("3. AttachmentProcessor import 오류")
    print("4. 파일 권한 문제")

if __name__ == "__main__":
    main()