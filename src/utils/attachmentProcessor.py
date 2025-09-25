"""
공고 첨부파일 처리 유틸리티

디렉토리 구조:
{title_directory}/
├── content.md
└── attachments/
    ├── file1.pdf
    ├── file2.hwp
    ├── file3.png
    └── ...

기존 convertUtil.py와 imageOcrUtil.py 기능을 활용하여
첨부파일들을 텍스트로 변환하고 {filename}.md 파일로 저장합니다.
"""

import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional

try:
    from src.config.config import ConfigManager
    from src.config.logConfig import setup_logging
    from src.utils.convertUtil import (
        convert_pdf_to_md_docling,
        convert_pdf_to_md_markitdown,
        convert_hwp_to_markdown,
        process_hwp_with_fallback,
        find_pdf_files,
        find_hwp_files
    )
    try:
        from src.utils.imageOcrUtil import ImageOCRProcessor, find_image_files_in_directory
        OCR_AVAILABLE = True
    except ImportError:
        OCR_AVAILABLE = False
        ImageOCRProcessor = None
        find_image_files_in_directory = None
        
except ImportError as e:
    # 절대 import 시도
    import sys
    from pathlib import Path
    
    # 프로젝트 루트를 path에 추가
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    
    from src.config.config import ConfigManager
    from src.config.logConfig import setup_logging
    from src.utils.convertUtil import (
        convert_pdf_to_md_docling,
        convert_pdf_to_md_markitdown,
        convert_hwp_to_markdown,
        process_hwp_with_fallback,
        find_pdf_files,
        find_hwp_files
    )
    try:
        from src.utils.imageOcrUtil import ImageOCRProcessor, find_image_files_in_directory
        OCR_AVAILABLE = True
    except ImportError:
        OCR_AVAILABLE = False
        ImageOCRProcessor = None
        find_image_files_in_directory = None

logger = setup_logging(__name__)
config = ConfigManager().get_config()


class AttachmentProcessor:
    """공고 첨부파일을 처리하는 클래스"""
    
    def __init__(self):
        self.supported_extensions = {
            'pdf': ['.pdf'],
            'hwp': ['.hwp', '.hwpx'],
            'image': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'],
            'office': ['.pptx', '.docx', '.xlsx']
        }
        self.ocr_processor = None
    
    def process_directory_attachments(self, directory_path: Path) -> Dict[str, str]:
        """
        디렉토리의 첨부파일들을 처리합니다.
        
        Args:
            directory_path: 처리할 디렉토리 경로
            
        Returns:
            {filename: converted_content} 형태의 딕셔너리
        """
        logger.info(f"첨부파일 처리 시작: {directory_path}")
        
        attachments_dir = directory_path / "attachments"
        
        if not attachments_dir.exists():
            logger.info(f"attachments 디렉토리가 없음: {attachments_dir}")
            return {}
        
        results = {}
        
        # PDF 파일 처리
        pdf_results = self._process_pdf_files(attachments_dir)
        results.update(pdf_results)
        
        # HWP 파일 처리
        hwp_results = self._process_hwp_files(attachments_dir)
        results.update(hwp_results)
        
        # 이미지 파일 처리
        image_results = self._process_image_files(attachments_dir)
        results.update(image_results)
        
        # Office 파일 처리 (pptx, docx, xlsx)
        office_results = self._process_office_files(attachments_dir)
        results.update(office_results)
        
        # 결과를 .md 파일로 저장
        self._save_converted_files(directory_path, results)
        
        logger.info(f"첨부파일 처리 완료: {len(results)}개 파일 변환됨")
        return results
    
    def process_single_file(self, file_path: Path) -> Optional[str]:
        """단일 파일을 처리하여 텍스트 내용을 반환합니다."""

        logger.info(f"단일 파일을 처리하여 텍스트 내용을 반환합니다. ====> {file_path}")

        try:
            file_extension = file_path.suffix.lower()
            filename = file_path.stem
            
            if file_extension == '.pdf':
                return self._process_single_pdf(file_path)
            elif file_extension in ['.hwp', '.hwpx']:
                return self._process_single_hwp(file_path)
            elif file_extension in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
                return self._process_single_image(file_path)
            elif file_extension in ['.pptx', '.docx', '.xlsx']:
                return self._process_single_office(file_path)
            else:
                logger.warning(f"지원하지 않는 파일 형식: {file_extension}")
                return None
                
        except Exception as e:
            logger.error(f"단일 파일 처리 실패 ({file_path}): {e}")
            return None
    
    def _process_single_pdf(self, pdf_file: Path) -> Optional[str]:
        """단일 PDF 파일을 처리합니다."""
        try:
            filename = pdf_file.stem
            temp_output = pdf_file.parent / f"{filename}_temp.md"
            
            # 1차 시도: docling
            success = False
            try:
                success = convert_pdf_to_md_docling(str(pdf_file), str(temp_output))
            except Exception as e:
                logger.warning(f"PDF docling 변환 실패 ({pdf_file.name}): {e}")
            
            # 2차 시도: markitdown
            if not success:
                try:
                    success = convert_pdf_to_md_markitdown(str(pdf_file), str(temp_output))
                except Exception as e:
                    logger.warning(f"PDF markitdown 변환 실패 ({pdf_file.name}): {e}")
            
            # 변환된 내용 읽기
            if success and temp_output.exists():
                try:
                    with open(temp_output, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # 임시 파일 삭제
                    temp_output.unlink()
                    return content
                except Exception as e:
                    logger.error(f"변환된 PDF 내용 읽기 실패: {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"PDF 파일 처리 실패 ({pdf_file}): {e}")
            return None
    
    def _process_single_hwp(self, hwp_file: Path) -> Optional[str]:
        """단일 HWP 파일을 처리합니다."""

        logger.info('단일 HWP FILE 처리')

        try:
            # 마크다운 파일 경로 생성
            md_path = hwp_file.parent / f"{hwp_file.stem}.md"

            # 먼저 마크다운 변환 시도
            if convert_hwp_to_markdown(hwp_file, md_path):
                if md_path.exists():
                    with open(md_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if content and content.strip():
                        logger.info(f"HWP 파일 마크다운 변환 성공: {hwp_file.name}")
                        return content

            # 마크다운 변환 실패 시 fallback으로 텍스트 추출
            logger.info(f"마크다운 변환 실패, fallback 텍스트 추출 시도: {hwp_file.name}")
            content = process_hwp_with_fallback(hwp_file)

            if content and content.strip():
                return content
            else:
                logger.warning(f"HWP 파일에서 내용 추출 실패: {hwp_file.name}")
                return None

        except Exception as e:
            logger.error(f"HWP 파일 처리 실패 ({hwp_file}): {e}")
            return None
    
    def _process_single_image(self, image_file: Path) -> Optional[str]:
        """단일 이미지 파일을 처리합니다."""
        try:
            if not OCR_AVAILABLE:
                logger.warning("OCR 기능을 사용할 수 없음")
                return None
            
            processor = ImageOCRProcessor(lazy_init=False)
            
            # 이미지가 절대 경로인 경우 부모 디렉토리를 base_dir로 사용
            base_dir = image_file.parent
            content = processor.extract_text_from_image_file(image_file, base_dir)
            
            if content and content.strip():
                logger.info(f"이미지에서 텍스트 추출 성공: {image_file.name} ({len(content)} 문자)")
                return content
            else:
                logger.warning(f"이미지에서 텍스트 추출 실패: {image_file.name}")
                return None
                
        except Exception as e:
            logger.error(f"이미지 파일 처리 실패 ({image_file}): {e}")
            return None
    
    def _process_single_office(self, office_file: Path) -> Optional[str]:
        """단일 Office 파일(pptx, docx, xlsx)을 처리합니다."""
        try:
            from markitdown import MarkItDown
            
            md = MarkItDown()
            result = md.convert(str(office_file))
            
            if result and result.text_content and result.text_content.strip():
                return result.text_content
            else:
                logger.warning(f"Office 파일에서 내용 추출 실패: {office_file.name}")
                return None
                
        except Exception as e:
            logger.error(f"Office 파일 처리 실패 ({office_file}): {e}")
            return None
    
    def _process_pdf_files(self, attachments_dir: Path) -> Dict[str, str]:
        """PDF 파일들을 처리합니다."""
        results = {}
        
        try:
            # 직접 glob을 사용하여 PDF 파일 찾기 (기존 함수 문제 우회)
            pdf_files = list(attachments_dir.glob("*.pdf"))
            
            for pdf_file in pdf_files:
                filename = pdf_file.stem
                
                logger.info(f"PDF 파일 처리 중: {pdf_file.name}")
                
                # 임시 출력 파일 경로
                temp_output = attachments_dir / f"{filename}_temp.md"
                
                # 기존 변환 함수 사용 (우선순위: docling -> markitdown)
                success = False
                
                # 1차 시도: docling
                try:
                    success = convert_pdf_to_md_docling(str(pdf_file), str(temp_output))
                except Exception as e:
                    logger.warning(f"PDF docling 변환 실패 ({pdf_file.name}): {e}")
                
                # 2차 시도: markitdown
                if not success:
                    try:
                        success = convert_pdf_to_md_markitdown(str(pdf_file), str(temp_output))
                    except Exception as e:
                        logger.warning(f"PDF markitdown 변환 실패 ({pdf_file.name}): {e}")
                
                # 변환된 내용 읽기
                if success and temp_output.exists():
                    try:
                        with open(temp_output, 'r', encoding='utf-8') as f:
                            content = f.read()
                        results[filename] = content
                        logger.info(f"PDF 변환 성공: {pdf_file.name}")
                    except Exception as e:
                        logger.error(f"PDF 변환 파일 읽기 실패 ({pdf_file.name}): {e}")
                    finally:
                        # 임시 파일 삭제
                        if temp_output.exists():
                            temp_output.unlink()
                else:
                    logger.error(f"PDF 변환 실패: {pdf_file.name}")
                    
        except Exception as e:
            logger.error(f"PDF 파일 처리 중 오류: {e}")
            
        return results
    
    def _process_hwp_files(self, attachments_dir: Path) -> Dict[str, str]:
        """HWP 파일들을 처리합니다."""
        results = {}
        
        try:
            # 직접 glob을 사용하여 HWP 파일 찾기 (기존 함수 문제 우회)
            hwp_files = list(attachments_dir.glob("*.hwp")) + list(attachments_dir.glob("*.hwpx"))
            
            for hwp_file in hwp_files:
                filename = hwp_file.stem
                
                logger.info(f"HWP 파일 처리 중: {hwp_file.name}")
                
                # 임시 출력 파일 경로
                temp_output = attachments_dir / f"{filename}_temp.md"
                
                # 기존 변환 함수 사용
                success = False
                
                try:
                    success = convert_hwp_to_markdown(hwp_file, temp_output)
                except Exception as e:
                    logger.warning(f"HWP 마크다운 변환 실패 ({hwp_file.name}): {e}")
                
                # 마크다운 변환 실패 시 텍스트 추출 시도
                if not success:
                    try:
                        text_content = process_hwp_with_fallback(hwp_file)
                        if text_content:
                            results[filename] = text_content
                            logger.info(f"HWP 텍스트 추출 성공: {hwp_file.name}")
                            continue
                    except Exception as e:
                        logger.warning(f"HWP 텍스트 추출 실패 ({hwp_file.name}): {e}")
                
                # 변환된 내용 읽기
                if success and temp_output.exists():
                    try:
                        with open(temp_output, 'r', encoding='utf-8') as f:
                            content = f.read()
                        results[filename] = content
                        logger.info(f"HWP 변환 성공: {hwp_file.name}")
                    except Exception as e:
                        logger.error(f"HWP 변환 파일 읽기 실패 ({hwp_file.name}): {e}")
                    finally:
                        # 임시 파일 삭제
                        if temp_output.exists():
                            temp_output.unlink()
                else:
                    logger.error(f"HWP 변환 실패: {hwp_file.name}")
                    
        except Exception as e:
            logger.error(f"HWP 파일 처리 중 오류: {e}")
            
        return results
    
    def _process_image_files(self, attachments_dir: Path) -> Dict[str, str]:
        """이미지 파일들을 OCR로 처리합니다."""
        results = {}
        
        try:
            if not OCR_AVAILABLE:
                logger.warning("OCR 기능이 사용 불가능합니다. 이미지 파일을 건너뜁니다.")
                return results
            
            # 기존 함수 활용하여 이미지 파일 찾기
            image_files = find_image_files_in_directory(attachments_dir)
            
            if not image_files:
                logger.info("처리할 이미지 파일이 없음")
                return results
            
            # OCR 프로세서 지연 초기화
            if self.ocr_processor is None:
                logger.info("OCR 프로세서 초기화 중...")
                self.ocr_processor = ImageOCRProcessor(lazy_init=False)
            
            for image_file in image_files:
                filename = image_file.stem
                
                logger.info(f"이미지 파일 OCR 처리 중: {image_file.name}")
                
                try:
                    # 기존 OCR 함수 사용
                    extracted_text = self.ocr_processor.extract_text_from_image_file(
                        image_file, attachments_dir
                    )
                    
                    if extracted_text and extracted_text.strip():
                        results[filename] = extracted_text
                        logger.info(f"이미지 OCR 성공: {image_file.name}, {len(extracted_text)} 문자")
                    else:
                        logger.warning(f"이미지에서 텍스트를 추출할 수 없음: {image_file.name}")
                        
                except Exception as e:
                    logger.error(f"이미지 OCR 처리 실패 ({image_file.name}): {e}")
                    
        except Exception as e:
            logger.error(f"이미지 파일 처리 중 오류: {e}")
            
        return results
    
    def _process_office_files(self, attachments_dir: Path) -> Dict[str, str]:
        """Office 파일들(pptx, docx, xlsx)을 처리합니다."""
        results = {}
        
        try:
            # Office 파일 찾기
            office_files = []
            for ext in ['.pptx', '.docx', '.xlsx']:
                office_files.extend(list(attachments_dir.glob(f"*{ext}")))
            
            for office_file in office_files:
                filename = office_file.stem
                
                logger.info(f"Office 파일 처리 중: {office_file.name}")
                
                try:
                    content = self._process_single_office(office_file)
                    
                    if content and content.strip():
                        results[filename] = content
                        logger.info(f"Office 변환 성공: {office_file.name}")
                    else:
                        logger.error(f"Office 변환 실패: {office_file.name}")
                        
                except Exception as e:
                    logger.error(f"Office 파일 처리 실패 ({office_file.name}): {e}")
                    
        except Exception as e:
            logger.error(f"Office 파일 처리 중 오류: {e}")
            
        return results
    
    def _save_converted_files(self, directory_path: Path, results: Dict[str, str]) -> None:
        """변환된 내용을 .md 파일로 저장합니다."""
        try:
            for filename, content in results.items():
                output_file = directory_path / f"{filename}.md"
                
                try:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.info(f"변환 파일 저장 완료: {output_file.name}")
                except Exception as e:
                    logger.error(f"파일 저장 실패 ({filename}.md): {e}")
                    
        except Exception as e:
            logger.error(f"변환 파일 저장 중 오류: {e}")
    
    def get_all_content(self, directory_path: Path) -> str:
        """
        content.md와 모든 첨부파일 내용을 출처 명시와 함께 결합하여 반환합니다.
        
        Args:
            directory_path: 처리할 디렉토리 경로
            
        Returns:
            출처가 명시된 결합된 모든 내용
        """
        all_content = []
        
        # content.md 읽기
        content_md = directory_path / "content.md"
        if content_md.exists():
            try:
                with open(content_md, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if content:
                    content_section = f"content.md: {content}"
                    all_content.append(content_section)
                    logger.info("content.md 내용 추가됨")
            except Exception as e:
                logger.error(f"content.md 읽기 실패: {e}")
        
        # 첨부파일 처리 및 내용 추가
        attachment_results = self.process_directory_attachments(directory_path)
        
        for filename, content in attachment_results.items():
            if content.strip():  # 내용이 있는 경우만 추가
                # 파일 확장자 정보도 함께 표시
                attachments_dir = directory_path / "attachments"
                original_files = list(attachments_dir.glob(f"{filename}.*"))
                file_extension = original_files[0].suffix if original_files else ""
                
                # 첨부파일 내용을 명확하게 구분하여 표시
                attachment_section = f"첨부파일 {filename}{file_extension}:\n{content.strip()}"
                all_content.append(attachment_section)
        
        combined_content = "\n\n".join(all_content)
        logger.info(f"출처 명시된 전체 내용 결합 완료: {len(combined_content)} 문자")
        
        return combined_content


def process_single_directory(directory_path: str | Path) -> Tuple[str, Dict[str, str]]:
    """
    단일 디렉토리의 첨부파일을 처리합니다.
    
    Args:
        directory_path: 처리할 디렉토리 경로
        
    Returns:
        (전체_결합_내용, 첨부파일_변환_결과) 튜플
    """
    if isinstance(directory_path, str):
        directory_path = Path(directory_path)
    
    processor = AttachmentProcessor()
    
    # 모든 내용 가져오기 (content.md + 첨부파일들)
    combined_content = processor.get_all_content(directory_path)
    
    # 첨부파일 변환 결과만 따로 가져오기
    attachment_results = processor.process_directory_attachments(directory_path)
    
    return combined_content, attachment_results


if __name__ == "__main__":
    # 테스트용
    test_dir = Path("/Users/jin/classfy_scraper/data.enhanced/acci/002_『제조기업-기술기업 밋업데이(Meet-up Day)』수요조사 실시")
    
    if test_dir.exists():
        combined, attachments = process_single_directory(test_dir)
        print(f"결합된 내용 길이: {len(combined)}")
        print(f"처리된 첨부파일: {list(attachments.keys())}")
    else:
        print(f"테스트 디렉토리가 존재하지 않음: {test_dir}")