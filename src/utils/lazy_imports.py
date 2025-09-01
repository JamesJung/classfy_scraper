"""
무거운 라이브러리 지연 로딩 유틸리티
Heavy Library Lazy Loading Utility

무거운 외부 라이브러리들을 실제 필요한 시점에 로딩하여 초기화 시간을 단축합니다.
"""

import threading
from collections.abc import Callable
from functools import wraps
from typing import Any

from src.config.logConfig import setup_logging

# 로깅 설정
logger = setup_logging(__name__)


class LazyImport:
    """
    지연 로딩 임포트 관리자
    스레드 안전한 방식으로 라이브러리를 필요 시점에 로딩
    """

    def __init__(self, module_name: str, import_func: Callable[[], Any]):
        """
        지연 임포트 초기화

        Args:
            module_name: 모듈 이름 (로깅용)
            import_func: 실제 임포트를 수행하는 함수
        """
        self.module_name = module_name
        self.import_func = import_func
        self._module: Any | None = None
        self._lock = threading.Lock()
        self._import_attempted = False

    def get(self) -> Any:
        """
        모듈을 지연 로딩으로 반환

        Returns:
            로딩된 모듈 객체
        """
        if self._module is None and not self._import_attempted:
            with self._lock:
                if self._module is None and not self._import_attempted:
                    try:
                        logger.info(f"지연 로딩 시작: {self.module_name}")
                        self._module = self.import_func()
                        logger.info(f"지연 로딩 완료: {self.module_name}")
                    except Exception as e:
                        logger.error(f"지연 로딩 실패: {self.module_name} - {e}")
                        raise
                    finally:
                        self._import_attempted = True

        return self._module

    def is_loaded(self) -> bool:
        """
        모듈이 로딩되었는지 확인

        Returns:
            로딩 여부
        """
        return self._module is not None


# 지연 로딩할 무거운 라이브러리들
class HeavyLibraries:
    """무거운 라이브러리들의 지연 로딩 관리"""

    # PDF 처리 라이브러리
    @staticmethod
    def _import_pdf_libraries():
        from marker.config.parser import ConfigParser
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from markitdown import MarkItDown
        from pdfminer.converter import HTMLConverter, TextConverter
        from pdfminer.layout import LAParams
        from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
        from pdfminer.pdfpage import PDFPage

        return {
            "MarkItDown": MarkItDown,
            "PDFResourceManager": PDFResourceManager,
            "PDFPageInterpreter": PDFPageInterpreter,
            "HTMLConverter": HTMLConverter,
            "TextConverter": TextConverter,
            "LAParams": LAParams,
            "PDFPage": PDFPage,
            "PdfConverter": PdfConverter,
            "create_model_dict": create_model_dict,
            "ConfigParser": ConfigParser,
        }

    # HWP 처리 라이브러리 (커스텀 구현 포함)
    @staticmethod
    def _import_hwp_libraries():
        try:
            # 커스텀 HWP 모듈 import (read_hwpx 개선 버전 포함)
            from hwp5.dataio import ParseError
            from hwp5.errors import InvalidHwp5FileError
            from hwp5.hwp5html import HTMLTransform

            # 기존 hwp5 라이브러리들
            from hwp5.xmlmodel import Hwp5File

            from src.utils import hwp_custom

            return {
                "gethwp": hwp_custom,  # 커스텀 HWP 모듈을 gethwp 대신 사용
                "Hwp5File": Hwp5File,
                "HTMLTransform": HTMLTransform,
                "ParseError": ParseError,
                "InvalidHwp5FileError": InvalidHwp5FileError,
                "hwp5_available": True,
            }
        except ImportError as e:
            logger.warning(f"hwp5 라이브러리를 가져올 수 없습니다: {e}")
            # hwp5가 없어도 기본적인 커스텀 HWP 처리는 가능
            from src.utils import hwp_custom
            
            return {
                "gethwp": hwp_custom,
                "Hwp5File": None,
                "HTMLTransform": None, 
                "ParseError": Exception,  # 기본 Exception으로 대체
                "InvalidHwp5FileError": Exception,  # 기본 Exception으로 대체
                "hwp5_available": False,
            }

    # LangChain 라이브러리
    @staticmethod
    def _import_langchain_libraries():
        from langchain_community.document_loaders import (
            UnstructuredHTMLLoader,
            UnstructuredMarkdownLoader,
        )

        return {
            "UnstructuredMarkdownLoader": UnstructuredMarkdownLoader,
            "UnstructuredHTMLLoader": UnstructuredHTMLLoader,
        }

    # 이미지 OCR 라이브러리 (만약 있다면)
    @staticmethod
    def _import_ocr_libraries():
        try:
            # OCR 라이브러리가 있다면 여기에 추가
            # import pytesseract
            # import PIL
            return {}
        except ImportError:
            return {}


# 지연 로딩 인스턴스들
pdf_libraries = LazyImport("PDF Libraries", HeavyLibraries._import_pdf_libraries)
hwp_libraries = LazyImport("HWP Libraries", HeavyLibraries._import_hwp_libraries)
langchain_libraries = LazyImport(
    "LangChain Libraries", HeavyLibraries._import_langchain_libraries
)
ocr_libraries = LazyImport("OCR Libraries", HeavyLibraries._import_ocr_libraries)


def lazy_import(library_type: str):
    """
    지연 로딩 데코레이터

    Args:
        library_type: 라이브러리 타입 ('pdf', 'hwp', 'langchain', 'ocr')
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 필요한 라이브러리를 로딩
            if library_type == "pdf":
                pdf_libraries.get()
            elif library_type == "hwp":
                hwp_libraries.get()
            elif library_type == "langchain":
                langchain_libraries.get()
            elif library_type == "ocr":
                ocr_libraries.get()

            return func(*args, **kwargs)

        return wrapper

    return decorator


def get_pdf_libraries() -> dict[str, Any]:
    """PDF 처리 라이브러리들을 지연 로딩으로 반환"""
    return pdf_libraries.get()


def get_hwp_libraries() -> dict[str, Any]:
    """HWP 처리 라이브러리들을 지연 로딩으로 반환"""
    return hwp_libraries.get()


def get_langchain_libraries() -> dict[str, Any]:
    """LangChain 라이브러리들을 지연 로딩으로 반환"""
    return langchain_libraries.get()


def get_ocr_libraries() -> dict[str, Any]:
    """OCR 라이브러리들을 지연 로딩으로 반환"""
    return ocr_libraries.get()


def get_loading_status() -> dict[str, bool]:
    """
    모든 라이브러리의 로딩 상태 반환

    Returns:
        라이브러리별 로딩 상태
    """
    return {
        "pdf_libraries": pdf_libraries.is_loaded(),
        "hwp_libraries": hwp_libraries.is_loaded(),
        "langchain_libraries": langchain_libraries.is_loaded(),
        "ocr_libraries": ocr_libraries.is_loaded(),
    }


def preload_all_libraries():
    """
    모든 라이브러리를 미리 로딩 (옵션)
    개발/테스트 환경에서 사용
    """
    logger.info("모든 라이브러리 미리 로딩 시작...")

    try:
        get_pdf_libraries()
        get_hwp_libraries()
        get_langchain_libraries()
        get_ocr_libraries()
        logger.info("모든 라이브러리 미리 로딩 완료")
    except Exception as e:
        logger.error(f"라이브러리 미리 로딩 중 오류: {e}")
        raise
