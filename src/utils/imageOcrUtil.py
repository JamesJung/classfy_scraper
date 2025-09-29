"""
이미지 OCR 처리 유틸리티
MD 파일의 data:image와 이미지 경로에서 텍스트를 추출합니다.
"""

import base64
import io
from math import log
import re
from pathlib import Path

# 선택적 import - OCR 기능을 사용할 때만 로드
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    easyocr = None

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

    # 타입 어노테이션을 위한 더미 클래스 생성
    class DummyImage:
        class Image:
            pass

    Image = DummyImage

try:
    from src.config.logConfig import setup_logging
except ImportError:
    # 절대 import 시도
    import sys
    from pathlib import Path

    # 프로젝트 루트를 path에 추가
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    from src.config.logConfig import setup_logging

logger = setup_logging(__name__)


class ImageOCRProcessor:
    """이미지 OCR 처리를 담당하는 클래스"""

    def __init__(self, lazy_init=True):
        """OCR 리더 초기화 (한국어, 영어 지원)

        Args:
            lazy_init: True이면 지연 초기화, False이면 즉시 초기화
        """
        self.reader = None
        self.use_tesseract = TESSERACT_AVAILABLE
        self.tesseract_lang = 'kor+eng'  # 한국어 + 영어

        if not lazy_init:
            self._initialize_reader()

    def _initialize_reader(self):
        """OCR 리더를 지연 초기화합니다."""
        try:
            # Tesseract 사용 가능 여부 확인
            if TESSERACT_AVAILABLE:
                try:
                    # Tesseract 바이너리 확인
                    pytesseract.get_tesseract_version()
                    logger.info("Tesseract OCR 사용 가능")
                    self.use_tesseract = True
                except Exception as e:
                    logger.warning(f"Tesseract 바이너리를 찾을 수 없습니다: {e}")
                    logger.warning("Tesseract를 설치하세요: sudo apt-get install tesseract-ocr tesseract-ocr-kor")
                    self.use_tesseract = False

            # Tesseract를 사용할 수 없으면 EasyOCR로 폴백
            if not self.use_tesseract:
                if not EASYOCR_AVAILABLE:
                    logger.error(
                        "Tesseract와 EasyOCR 모두 사용할 수 없습니다. pytesseract 또는 easyocr를 설치해주세요."
                    )
                    self.reader = None
                    return

                if self.reader is None:
                    logger.info("EasyOCR 리더 초기화 중... (한국어, 영어) - Fallback mode")
                    self.reader = easyocr.Reader(["ko", "en"], gpu=True)
                    logger.info("EasyOCR 리더 초기화 완료")
        except Exception as e:
            logger.error(f"OCR 리더 초기화 실패: {e}")
            self.reader = None

    def extract_text_from_data_image(self, data_url: str) -> str | None:
        """
        data:image URL에서 텍스트를 추출합니다.

        Args:
            data_url: data:image/...;base64,... 형식의 URL

        Returns:
            추출된 텍스트 또는 None
        """
        try:
            # data:image URL 파싱
            if not data_url.startswith("data:image/"):
                logger.warning(f"잘못된 data:image URL 형식: {data_url[:50]}...")
                return None

            # base64 데이터 추출
            if "base64," not in data_url:
                logger.warning("base64 데이터를 찾을 수 없습니다")
                return None

            base64_data = data_url.split("base64,")[1]

            # base64 디코딩
            image_data = base64.b64decode(base64_data)

            # PIL Image로 변환
            if not PIL_AVAILABLE:
                logger.error(
                    "PIL(Pillow) 패키지가 설치되지 않았습니다. pip install Pillow로 설치해주세요."
                )
                return None

            from PIL import Image as PILImage

            image = PILImage.open(io.BytesIO(image_data))

            # OCR 실행
            text = self._perform_ocr(image)

            if text:
                logger.info(f"data:image에서 텍스트 추출 성공: {len(text)} 문자")
                return text
            else:
                logger.warning("data:image에서 텍스트를 추출할 수 없습니다")
                return None

        except Exception as e:
            logger.error(f"data:image OCR 처리 중 오류: {e}")
            return None

    def extract_text_from_image_file(
        self, image_path: Path, base_dir: Path
    ) -> str | None:
        """
        이미지 파일에서 텍스트를 추출합니다.

        Args:
            image_path: 이미지 파일 경로 (상대 또는 절대)
            base_dir: 기준 디렉토리 (MD 파일이 있는 디렉토리)

        Returns:
            추출된 텍스트 또는 None
        """
        try:
            # 경로가 이미 존재하는 파일이면 그대로 사용
            if image_path.exists():
                full_path = image_path
            # 절대 경로인 경우
            elif image_path.is_absolute():
                full_path = image_path
            # 상대 경로인 경우 base_dir과 결합
            else:
                full_path = base_dir / image_path

            # 파일 존재 확인
            if not full_path.exists():
                logger.warning(f"이미지 파일을 찾을 수 없습니다: {full_path}")
                return None

            # 이미지 파일 로드
            if not PIL_AVAILABLE:
                logger.error(
                    "PIL(Pillow) 패키지가 설치되지 않았습니다. pip install Pillow로 설치해주세요."
                )
                return None

            from PIL import Image as PILImage

            image = PILImage.open(full_path)

            # OCR 실행
            text = self._perform_ocr(image)

            if text:
                logger.info(
                    f"이미지 파일에서 텍스트 추출 성공: {full_path.name}, {len(text)} 문자"
                )

                # ProcessedDataManager가 이제 텍스트 저장을 처리합니다

                return text
            else:
                logger.warning(
                    f"이미지 파일에서 텍스트를 추출할 수 없습니다: {full_path.name}"
                )
                return None

        except Exception as e:
            logger.error(f"이미지 파일 OCR 처리 중 오류 ({image_path}): {e}")
            return None

    def _perform_ocr(self, image: Image.Image) -> str | None:
        """
        PIL Image에 대해 OCR을 수행합니다.
        Tesseract를 우선 시도하고, 실패시 EasyOCR로 폴백합니다.

        Args:
            image: PIL Image 객체

        Returns:
            추출된 텍스트 또는 None
        """
        try:
            # 입력 타입 검증
            if not hasattr(image, "mode"):
                logger.error("잘못된 입력 타입입니다. PIL Image 객체가 필요합니다.")
                return None

            # RGB 모드로 변환 (RGBA, P 등 다른 모드 대응)
            if image.mode != "RGB":
                image = image.convert("RGB")

            # 1. Tesseract 시도
            if self.use_tesseract and TESSERACT_AVAILABLE:
                try:
                    logger.debug("Tesseract OCR 실행 중...")
                    # Tesseract 설정
                    custom_config = r'--oem 3 --psm 6'  # OEM 3: Default, PSM 6: 균일한 텍스트 블록

                    # Tesseract OCR 실행
                    text = pytesseract.image_to_string(
                        image,
                        lang=self.tesseract_lang,
                        config=custom_config
                    )

                    if text and text.strip():
                        logger.debug(f"Tesseract OCR 성공: {len(text.strip())} 문자 추출")
                        return text.strip()
                    else:
                        logger.debug("Tesseract OCR에서 텍스트를 찾지 못함, EasyOCR로 폴백")

                except Exception as tesseract_error:
                    logger.warning(f"Tesseract OCR 실패, EasyOCR로 폴백: {tesseract_error}")

            # 2. EasyOCR 폴백
            if not self.use_tesseract or not TESSERACT_AVAILABLE:
                if self.reader is None:
                    self._initialize_reader()

                if self.reader is None:
                    logger.error("OCR 리더가 초기화되지 않았습니다")
                    return None

                try:
                    logger.debug("EasyOCR 실행 중...")
                    # PIL Image를 numpy 배열로 변환
                    import numpy as np
                    image_array = np.array(image)

                    # EasyOCR에 numpy 배열 전달
                    results = self.reader.readtext(image_array)
                    if not results:
                        logger.debug("EasyOCR에서 텍스트를 찾지 못함")
                        return None

                    # 결과 텍스트 결합
                    extracted_texts = []
                    for bbox, text, confidence in results:
                        # 신뢰도가 0.5 이상인 텍스트만 사용
                        if confidence >= 0.5:
                            extracted_texts.append(text.strip())

                    if extracted_texts:
                        combined_text = " ".join(extracted_texts)
                        logger.debug(f"EasyOCR 성공: {len(combined_text)} 문자 추출")
                        return combined_text

                except Exception as easyocr_error:
                    logger.error(f"EasyOCR 실행 중 오류: {easyocr_error}")

            return None

        except Exception as e:
            logger.error(f"OCR 실행 중 오류: {e}")
            return None


def extract_images_from_markdown(md_content: str, md_file_path: Path) -> list[str]:
    """
    마크다운 내용에서 이미지를 찾아 OCR로 텍스트를 추출합니다.

    Args:
        md_content: 마크다운 파일 내용
        md_file_path: 마크다운 파일 경로 (이미지 상대경로 해석용)

    Returns:
        추출된 텍스트들의 리스트
    """
    # 먼저 이미지가 있는지 확인
    if not _has_images_in_markdown(md_content, md_file_path):
        logger.info("마크다운에 처리할 이미지가 없어서 OCR 처리를 건너뜁니다")
        return []

    # 이미지가 있을 때만 OCR 프로세서 초기화
    logger.info("이미지 발견됨 - OCR 프로세서 초기화 시작")
    ocr_processor = ImageOCRProcessor(lazy_init=False)
    extracted_texts = []
    base_dir = md_file_path.parent

    try:
        # 1. data:image URL 패턴 찾기
        data_image_pattern = r"!\[.*?\]\((data:image/[^)]+)\)"
        data_images = re.findall(data_image_pattern, md_content)

        for data_url in data_images:
            logger.info(f"data:image URL 발견: {data_url[:50]}...")
            text = ocr_processor.extract_text_from_data_image(data_url)
            if text:
                extracted_texts.append(text)

        # 2. 일반 이미지 경로 패턴 찾기 (data:image 제외)
        image_pattern = r"!\[.*?\]\(([^)]+)\)"
        all_images = re.findall(image_pattern, md_content)

        # data:image가 아닌 실제 파일 경로만 필터링
        image_paths = [img for img in all_images if not img.startswith("data:image/")]

        for img_path in image_paths:
            logger.info(f"이미지 파일 경로 발견: {img_path}")
            image_path = Path(img_path)
            text = ocr_processor.extract_text_from_image_file(image_path, base_dir)
            if text:
                extracted_texts.append(text)

        # 3. HTML img 태그도 처리
        html_img_pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>'
        html_images = re.findall(html_img_pattern, md_content)

        for img_src in html_images:
            if img_src.startswith("data:image/"):
                logger.info(f"HTML data:image 발견: {img_src[:50]}...")
                text = ocr_processor.extract_text_from_data_image(img_src)
                if text:
                    extracted_texts.append(text)
            else:
                logger.info(f"HTML 이미지 파일 경로 발견: {img_src}")
                image_path = Path(img_src)
                text = ocr_processor.extract_text_from_image_file(image_path, base_dir)
                if text:
                    extracted_texts.append(text)

        if extracted_texts:
            logger.info(f"총 {len(extracted_texts)}개의 이미지에서 텍스트 추출 완료")
        else:
            logger.info("처리 가능한 이미지에서 텍스트를 추출하지 못했습니다")

        logger.info(f"extracted_texts: {extracted_texts}")

        return extracted_texts

    except Exception as e:
        logger.error(f"마크다운 이미지 처리 중 오류: {e}")
        return extracted_texts


def _has_images_in_markdown(md_content: str, md_file_path: Path) -> bool:
    """
    마크다운에 처리 가능한 이미지가 있는지 확인합니다.

    Args:
        md_content: 마크다운 파일 내용
        md_file_path: 마크다운 파일 경로

    Returns:
        처리 가능한 이미지가 있으면 True
    """
    try:
        base_dir = md_file_path.parent

        # 1. data:image URL 확인
        data_image_pattern = r"data:image/[^)]+"
        if re.search(data_image_pattern, md_content):
            logger.debug("data:image URL 발견됨")
            return True

        # 2. 이미지 파일 경로 확인
        image_pattern = r"!\[.*?\]\(([^)]+)\)"
        all_images = re.findall(image_pattern, md_content)

        # data:image가 아닌 실제 파일 경로만 확인
        image_paths = [img for img in all_images if not img.startswith("data:image/")]

        for img_path in image_paths:
            image_path = Path(img_path)
            if image_path.is_absolute():
                full_path = image_path
            else:
                full_path = base_dir / image_path

            if full_path.exists():
                logger.debug(f"이미지 파일 발견됨: {img_path}")
                return True

        # 3. HTML img 태그 확인
        html_img_pattern = r'<img[^>]+src=["\']([^"\'>]+)["\'][^>]*>'
        html_images = re.findall(html_img_pattern, md_content)

        for img_src in html_images:
            if img_src.startswith("data:image/"):
                logger.debug("HTML data:image 발견됨")
                return True
            else:
                image_path = Path(img_src)
                if image_path.is_absolute():
                    full_path = image_path
                else:
                    full_path = base_dir / image_path

                if full_path.exists():
                    logger.debug(f"HTML 이미지 파일 발견됨: {img_src}")
                    return True

        return False

    except Exception as e:
        logger.warning(f"이미지 존재 확인 중 오류: {e}")
        return False


def extract_text_from_image(image_path: str) -> str | None:
    """
    이미지 파일에서 텍스트를 추출하는 독립 함수 (간단한 인터페이스)

    Args:
        image_path: 이미지 파일 경로 (문자열)

    Returns:
        추출된 텍스트 또는 None
    """
    try:
        image_path_obj = Path(image_path)
        if not image_path_obj.exists():
            logger.warning(f"이미지 파일을 찾을 수 없습니다: {image_path}")
            return None

        # ImageOCRProcessor 인스턴스 생성 및 처리
        processor = ImageOCRProcessor(lazy_init=False)
        return processor.extract_text_from_image_file(
            image_path_obj, image_path_obj.parent
        )

    except Exception as e:
        logger.error(f"이미지 텍스트 추출 중 오류: {image_path} - {e}")
        return None


def find_image_files_in_directory(
    directory: Path, common_extensions: list[str] = None
) -> list[Path]:
    """
    디렉토리에서 이미지 파일들을 찾습니다.

    Args:
        directory: 검색할 디렉토리
        common_extensions: 찾을 이미지 확장자들

    Returns:
        발견된 이미지 파일 경로들
    """
    if common_extensions is None:
        common_extensions = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]

    image_files = []
    try:
        for ext in common_extensions:
            pattern = f"*{ext}"
            found_files = list(directory.glob(pattern))
            found_files.extend(list(directory.glob(pattern.upper())))
            image_files.extend(found_files)

        return sorted(set(image_files))  # 중복 제거 및 정렬

    except Exception as e:
        logger.error(f"디렉토리 이미지 검색 중 오류 ({directory}): {e}")
        return []
