import json
import os
import re
import shutil
import sys
import traceback
from contextlib import closing
from pathlib import Path

from src.config.config import ConfigManager
from src.config.constants import (
    APL_MTHD_CD,
    INDST_CD,
    PRF_RSTR_DV_CD,
    RCPT_INST_CD,
    RCPT_INST_CTGR_CD,
    SPOT_TRG_AREA_CD,
    SPOT_TRG_DV_CD,
    SPOT_TRG_STRTUP_DV_CD,
    SPOT_TYP_DV_CD,
)
from src.config.logConfig import setup_logging
from src.utils.lazy_imports import get_hwp_libraries

# hwp5 라이브러리 커스텀 패치 적용 (UnderlineStyle 값 15 지원)
try:
    from src.utils import hwp5_custom
    # import 시 자동으로 패치 적용됨
except Exception as e:
    # 패치 실패해도 계속 진행 (fallback 방법 사용 가능)
    import logging
    logging.getLogger(__name__).warning(f"hwp5 커스텀 패치 적용 실패: {e}")

# Heavy libraries moved to lazy imports for faster startup
# These will be imported only when the respective functions are called:
# - markitdown.MarkItDown
# - pdfminer.*
# - marker.*
# - langchain_community.*
# - hwp5.*
# - gethwp
from src.utils.timerUtil import Timer

# Constants moved to lazy import for faster startup


def remove_javascript_content(text: str) -> str:
    """
    텍스트에서 JavaScript 관련 내용을 제거합니다.

    Args:
        text: 원본 텍스트

    Returns:
        JavaScript 내용이 제거된 텍스트
    """
    # JavaScript 코드 블록 제거 (```javascript 또는 ```js)
    text = re.sub(
        r"```(?:javascript|js)\s*\n.*?\n```", "", text, flags=re.DOTALL | re.IGNORECASE
    )

    # 인라인 JavaScript 코드 제거 (`javascript` 또는 `js`)
    text = re.sub(r"`(?:javascript|js):[^`]*`", "", text, flags=re.IGNORECASE)

    # <script> 태그 제거
    text = re.sub(
        r"<script\b[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE
    )

    # JavaScript 관련 키워드가 포함된 라인 제거
    js_keywords = [
        "function",
        "var ",
        "let ",
        "const ",
        "document.",
        "window.",
        "console.",
        "alert(",
        "addEventListener",
    ]
    lines = text.split("\n")
    filtered_lines = []

    for line in lines:
        line_lower = line.lower().strip()
        # JavaScript 키워드가 포함된 라인인지 확인
        contains_js = any(keyword in line_lower for keyword in js_keywords)

        # JavaScript 관련 라인이 아니거나, 문서 내용의 일부인 경우 유지
        if (
            not contains_js
            or line.strip().startswith("#")
            or line.strip().startswith("-")
        ):
            filtered_lines.append(line)

    return "\n".join(filtered_lines)


# 로깅 설정
logger = setup_logging(__name__)
config = ConfigManager().get_config()

# 파일 처리 관련 상수
OUTPUT_DIR = Path(config["directories"]["output_dir"])


def get_converted_pdf_path(md_file: Path) -> Path | None:
    """
    변환된 PDF 파일 경로를 반환합니다.

    Args:
        md_file: 마크다운 파일 경로

    Returns:
        변환된 PDF 파일 경로 또는 None
    """
    try:
        temp_dir = md_file.parent / "temp"
        converted_files = list(temp_dir.glob(f"pdf_{md_file.stem}_*.md"))
        return converted_files[0] if converted_files else None
    except Exception as e:
        logger.error(
            f"PDF 변환 경로 탐색 중 오류: {md_file} - {str(e)}\n{traceback.format_exc()}"
        )
        return None


def get_converted_hwp_path(md_file: Path) -> Path | None:
    """
    변환된 HWP 파일 경로를 반환합니다.

    Args:
        md_file: 마크다운 파일 경로

    Returns:
        변환된 HWP 파일 경로 또는 None
    """
    try:
        temp_dir = md_file.parent / "temp"
        converted_files = list(temp_dir.glob(f"hwp_{md_file.stem}_*.html"))
        return converted_files[0] if converted_files else None
    except Exception as e:
        logger.error(
            f"HWP 변환 경로 탐색 중 오류: {md_file} - {str(e)}\n{traceback.format_exc()}"
        )
        return None


def read_json_file(file_path: Path) -> str:
    """
    JSON 파일을 읽어서 문자열로 반환합니다.

    Args:
        file_path: JSON 파일 경로

    Returns:
        JSON 문자열
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            raw_data = json.load(f)
            if "originalData" in raw_data:
                del raw_data["originalData"]
            data = json.dumps(raw_data, ensure_ascii=False, indent=2)
            return data
    except Exception as e:
        logger.error(
            f"Error reading json file {file_path}: {e}\n{traceback.format_exc()}"
        )
        sys.exit(1)


def read_md_file(file_path: Path, enable_ocr: bool = True) -> str:
    """
    마크다운 파일을 읽어서 문자열로 반환합니다.
    OCR이 활성화된 경우 이미지에서 텍스트를 추출하여 추가합니다.

    Args:
        file_path: 마크다운 파일 경로
        enable_ocr: 이미지 OCR 처리 여부

    Returns:
        마크다운 문자열 (OCR 텍스트 포함, 특수문자 정리됨)
    """
    try:
        from src.utils.lazy_imports import get_langchain_libraries
        from src.utils.textCleaner import clean_extracted_text

        # ProcessedDataManager handles text saving now

        try:
            langchain_libs = get_langchain_libraries()
            UnstructuredMarkdownLoader = langchain_libs["UnstructuredMarkdownLoader"]

            loader = UnstructuredMarkdownLoader(file_path)
            documents = loader.load()

            # Document 객체들의 page_content를 결합
            data = "\n".join([doc.page_content for doc in documents])
        except Exception as langchain_error:
            logger.warning(
                f"LangChain 라이브러리 사용 실패, 직접 파일 읽기로 폴백: {langchain_error}"
            )
            # 폴백: 직접 파일 읽기
            with open(file_path, encoding="utf-8") as f:
                data = f.read()

        # JavaScript 관련 내용 제거
        data = remove_javascript_content(data)

        # MD 파일 전용 내용 정리 (헤더, 푸터, 네비게이션 등 제거)
        try:
            from src.utils.mdContentCleaner import clean_md_content

            data = clean_md_content(data)
            logger.debug(f"MD 내용 정리 완료: {file_path.name}")
        except Exception as md_clean_error:
            logger.warning(f"MD 내용 정리 실패, 기본 처리 진행: {md_clean_error}")

        # 특수문자 정리 (EXTRACTED_TEXT용)
        data = clean_extracted_text(data)

        # ProcessedDataManager가 이제 텍스트 저장을 처리합니다

        # OCR 처리가 활성화된 경우
        if enable_ocr:
            try:
                from src.utils.imageOcrUtil import (
                    _has_images_in_markdown,
                    extract_images_from_markdown,
                )

                # 원본 마크다운 내용 읽기
                with open(file_path, encoding="utf-8") as f:
                    md_content = f.read()

                # 이미지가 있는지 먼저 확인
                if _has_images_in_markdown(md_content, file_path):
                    logger.info(
                        f"MD 파일에 이미지 발견: {file_path.name} - OCR 처리 시작"
                    )

                    # 이미지에서 텍스트 추출
                    ocr_texts = extract_images_from_markdown(md_content, file_path)

                    if ocr_texts:
                        # OCR 텍스트를 마크다운 끝에 추가 (정리된 텍스트로)
                        ocr_section = "\n\n## 이미지에서 추출된 텍스트\n\n"
                        for i, text in enumerate(ocr_texts, 1):
                            # OCR 텍스트도 특수문자 정리
                            cleaned_ocr_text = clean_extracted_text(text)
                            ocr_section += f"### 이미지 {i}\n{cleaned_ocr_text}\n\n"

                        data += ocr_section
                        logger.info(
                            f"MD 파일에 OCR 텍스트 추가: {len(ocr_texts)}개 이미지"
                        )
                    else:
                        logger.info(
                            f"MD 파일에 이미지가 있지만 OCR 텍스트 추출 실패: {file_path.name}"
                        )
                else:
                    logger.debug(
                        f"MD 파일에 이미지가 없어서 OCR 처리 건너뛰기: {file_path.name}"
                    )

            except Exception as ocr_error:
                logger.warning(f"OCR 처리 중 오류 (무시하고 계속): {ocr_error}")

        logger.debug(f"Successfully read attachment md file: {file_path}")
        return data
    except Exception as e:
        logger.error(f"Error reading attachment md file {file_path}: {e}")
        logger.warning(f"MD 파일 읽기 실패, 빈 문자열 반환: {file_path}")
        return ""  # 에러 시 빈 문자열 반환으로 전체 프로세스 중단 방지


def read_txt_file(file_path: Path) -> str:
    """
    TXT 파일을 읽어서 문자열로 반환합니다.

    Args:
        file_path: TXT 파일 경로

    Returns:
        TXT 파일 내용 문자열
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # 텍스트 정리
        from src.utils.textCleaner import clean_extracted_text

        cleaned_content = clean_extracted_text(content)

        # ProcessedDataManager가 이제 텍스트 저장을 처리합니다

        logger.debug(
            f"TXT 파일 읽기 성공 (텍스트 길이: {len(cleaned_content)}자): {file_path}"
        )
        return cleaned_content

    except Exception as e:
        logger.error(f"TXT 파일 읽기 오류: {file_path} - {e}")
        return ""


def read_html_file(file_path: Path) -> str:
    """
    HTML/XHTML 파일을 읽어서 문자열로 반환합니다.
    MarkItDown을 우선 사용하고, 실패 시 UnstructuredHTMLLoader를 대안으로 사용

    Args:
        file_path: HTML/XHTML 파일 경로

    Returns:
        HTML에서 추출된 텍스트 문자열
    """
    try:
        # 1차 시도: MarkItDown 사용 (메인 방법)
        logger.debug(f"MarkItDown으로 HTML 변환 시도: {file_path}")

        try:
            from markitdown import MarkItDown
            markitdown = MarkItDown()
            result = markitdown.convert(str(file_path))
        except (ImportError, AttributeError) as e:
            # NumPy 버전 충돌 등으로 markitdown import 실패 시
            logger.warning(f"MarkItDown import 실패 (NumPy 호환성 문제 가능): {e}")
            logger.info("BeautifulSoup로 대체하여 HTML 처리")
            result = None

        if result and result.text_content and len(result.text_content.strip()) > 50:
            content = result.text_content.strip()

            # 텍스트 품질 검증
            korean_chars = sum(1 for c in content if 0xAC00 <= ord(c) <= 0xD7AF)
            chinese_chars = sum(1 for c in content if 0x4E00 <= ord(c) <= 0x9FFF)
            # 키릴 문자 범위 추가 (U+0400~U+04FF: Cyrillic, U+0500~U+052F: Cyrillic Supplement)
            cyrillic_chars = sum(1 for c in content if 0x0400 <= ord(c) <= 0x052F)
            total_meaningful_chars = len(
                [c for c in content if c.strip() and c.isalpha()]
            )

            if total_meaningful_chars > 0:
                korean_ratio = korean_chars / total_meaningful_chars
                chinese_ratio = chinese_chars / total_meaningful_chars
                cyrillic_ratio = cyrillic_chars / total_meaningful_chars

                # 중국어 또는 키릴 문자 감지 시 인코딩 문제로 판단 (임계값 낮춤: 10% -> 1%)
                if (chinese_ratio > korean_ratio and chinese_ratio > 0.01) or \
                   (cyrillic_ratio > 0.01):  # 키릴은 1%만 있어도 복구 시도
                    logger.warning(
                        f"인코딩 문제 감지됨 - 한글: {korean_ratio:.2%}, 중국어: {chinese_ratio:.2%}, 키릴: {cyrillic_ratio:.2%}: {file_path}"
                    )
                    # 인코딩 복구 시도
                    content = fix_hwp_encoding(content)

            logger.info(
                f"MarkItDown으로 HTML 변환 성공 (텍스트 길이: {len(content)}자): {file_path}"
            )
            return content
        else:
            logger.warning(f"MarkItDown 변환 결과가 부족함: {file_path}")

    except Exception as e:
        logger.warning(f"MarkItDown HTML 변환 실패: {file_path} - {e}")

    # 2차 시도: UnstructuredHTMLLoader 사용 (폴백 방법)
    try:
        logger.debug(f"UnstructuredHTMLLoader로 HTML 변환 시도 (폴백): {file_path}")

        # Heavy library - lazy import for performance
        from langchain_community.document_loaders import UnstructuredHTMLLoader

        loader = UnstructuredHTMLLoader(file_path)
        documents = loader.load()

        # Document 객체들의 page_content를 결합하여 텍스트 추출
        if documents:
            content = "\n".join([doc.page_content for doc in documents])

            # 텍스트 품질 검증
            if len(content.strip()) > 50:
                # 한글 문자 비율 확인 (인코딩 문제 감지)
                korean_chars = sum(1 for c in content if 0xAC00 <= ord(c) <= 0xD7AF)
                chinese_chars = sum(1 for c in content if 0x4E00 <= ord(c) <= 0x9FFF)
                # 키릴 문자 범위 추가 (U+0400~U+04FF: Cyrillic, U+0500~U+052F: Cyrillic Supplement)
                cyrillic_chars = sum(1 for c in content if 0x0400 <= ord(c) <= 0x052F)
                total_meaningful_chars = len(
                    [c for c in content if c.strip() and c.isalpha()]
                )

                if total_meaningful_chars > 0:
                    korean_ratio = korean_chars / total_meaningful_chars
                    chinese_ratio = chinese_chars / total_meaningful_chars
                    cyrillic_ratio = cyrillic_chars / total_meaningful_chars

                    # 중국어 또는 키릴 문자 감지 시 인코딩 문제로 판단 (임계값 낮춤: 10% -> 1%)
                    if (chinese_ratio > korean_ratio and chinese_ratio > 0.01) or \
                       (cyrillic_ratio > 0.01):  # 키릴은 1%만 있어도 복구 시도
                        logger.warning(
                            f"인코딩 문제 감지됨 - 한글: {korean_ratio:.2%}, 중국어: {chinese_ratio:.2%}, 키릴: {cyrillic_ratio:.2%}: {file_path}"
                        )

                        # 인코딩 복구 시도
                        content = fix_hwp_encoding(content)

                logger.info(
                    f"UnstructuredHTMLLoader로 HTML 변환 성공 (폴백) (텍스트 길이: {len(content)}자): {file_path}"
                )
                return content
            else:
                logger.warning(
                    f"추출된 텍스트가 너무 짧음 ({len(content)}자): {file_path}"
                )
                return content
        else:
            logger.warning(f"HTML 로더에서 Document 객체를 반환하지 않음: {file_path}")
            return ""

    except Exception as e:
        logger.error(f"UnstructuredHTMLLoader HTML 파일 읽기 오류: {file_path} - {e}")
        return ""


def fix_hwp_encoding(text: str) -> str:
    """
    HWP 파일에서 추출된 텍스트의 인코딩 문제를 수정합니다.
    한글이 중국어 문자 또는 키릴 문자로 잘못 변환된 경우 복구를 시도합니다.

    Args:
        text: 인코딩 문제가 있을 수 있는 텍스트

    Returns:
        인코딩이 수정된 텍스트
    """
    try:
        # 원본 텍스트가 너무 짧으면 그대로 반환
        if len(text.strip()) < 10:
            return text

        # 키릴 문자 비율 확인
        cyrillic_chars = sum(1 for c in text if 0x0400 <= ord(c) <= 0x052F)
        total_chars = len([c for c in text if c.strip() and c.isalpha()])
        cyrillic_ratio = cyrillic_chars / total_chars if total_chars > 0 else 0.0

        # 여러 인코딩 복구 방법 시도
        recovery_methods = [
            # 방법 1: UTF-8 -> EUC-KR -> UTF-8 재변환
            lambda t: t.encode("latin1").decode("euc-kr", errors="ignore"),
            # 방법 2: CP949 재변환
            lambda t: t.encode("latin1").decode("cp949", errors="ignore"),
            # 방법 3: 바이트 레벨에서 직접 변환
            lambda t: _direct_byte_conversion(t),
        ]

        # 키릴 문자가 있으면 키릴 복구 시도를 먼저 추가 (임계값 낮춤: 10% -> 1%)
        if cyrillic_ratio > 0.01:
            logger.info(f"키릴 문자 감지됨 ({cyrillic_ratio:.2%}), 키릴->한글 복구 시도")
            recovery_methods.insert(0, lambda t: _recover_from_cyrillic(t))

        best_text = text
        best_korean_ratio = _calculate_korean_ratio(text)

        for method in recovery_methods:
            try:
                recovered_text = method(text)
                if (
                    recovered_text and len(recovered_text) > len(text) * 0.8
                ):  # 너무 많이 손실되지 않았다면
                    korean_ratio = _calculate_korean_ratio(recovered_text)

                    # 한글 비율이 개선되었다면 채택
                    if korean_ratio > best_korean_ratio + 0.1:  # 10% 이상 개선
                        best_text = recovered_text
                        best_korean_ratio = korean_ratio
                        logger.info(
                            f"인코딩 복구 성공 - 한글 비율: {best_korean_ratio:.2%}"
                        )

            except Exception as e:
                logger.debug(f"인코딩 복구 방법 실패: {e}")
                continue

        return best_text

    except Exception as e:
        logger.error(f"인코딩 복구 중 오류: {e}")
        return text


def _calculate_korean_ratio(text: str) -> float:
    """텍스트에서 한글 문자의 비율을 계산합니다."""
    if not text:
        return 0.0

    korean_chars = sum(1 for c in text if 0xAC00 <= ord(c) <= 0xD7AF)
    total_chars = len([c for c in text if c.strip() and c.isalpha()])

    return korean_chars / total_chars if total_chars > 0 else 0.0


def _detect_pdf_encoding(pdf_path: str) -> str:
    """
    PDF 파일의 인코딩을 자동으로 감지합니다.

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        감지된 인코딩 이름 (예: 'utf-8', 'euc-kr', 'cp949' 등) 또는 None
    """
    try:
        # chardet 라이브러리 사용 (설치 필요: pip install chardet)
        try:
            import chardet
        except ImportError:
            logger.debug("chardet 라이브러리가 없어 기본 인코딩 감지만 수행")
            # chardet 없이도 작동하도록 기본 인코딩 목록 시도
            return _detect_encoding_fallback(pdf_path)

        # PDF 파일의 일부를 읽어서 인코딩 감지
        with open(pdf_path, 'rb') as f:
            # PDF 헤더 건너뛰기
            raw_data = f.read(10240)  # 처음 10KB 읽기

            # PDF 스트림 객체 찾기 (실제 텍스트 내용)
            stream_start = raw_data.find(b'stream')
            if stream_start > 0:
                # stream 이후 데이터부터 분석
                raw_data = raw_data[stream_start:]

            # chardet로 인코딩 감지
            result = chardet.detect(raw_data)
            detected_encoding = result['encoding']
            confidence = result['confidence']

            if detected_encoding and confidence > 0.7:
                logger.info(f"PDF 인코딩 감지 성공: {detected_encoding} (신뢰도: {confidence:.2%})")
                return detected_encoding
            else:
                logger.warning(f"PDF 인코딩 감지 신뢰도 낮음: {detected_encoding} ({confidence:.2%})")
                # 신뢰도가 낮으면 폴백 방식 시도
                return _detect_encoding_fallback(pdf_path)

    except Exception as e:
        logger.warning(f"PDF 인코딩 감지 실패: {e}")
        return _detect_encoding_fallback(pdf_path)


def _detect_encoding_fallback(pdf_path: str) -> str:
    """
    chardet 없이 일반적인 인코딩을 순서대로 시도하여 감지합니다.

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        작동하는 인코딩 이름 또는 None
    """
    # 한국어 PDF에서 자주 사용되는 인코딩 순서
    encodings_to_try = [
        'utf-8',
        'cp949',      # Windows 한글 (EUC-KR 확장)
        'euc-kr',     # 유닉스/리눅스 한글
        'utf-16',
        'iso-8859-1', # Latin-1
        'cp1252',     # Windows Western Europe
        'gbk',        # 중국어 간체
        'big5',       # 중국어 번체
        'shift-jis',  # 일본어
    ]

    try:
        with open(pdf_path, 'rb') as f:
            raw_data = f.read(10240)

            # 한글이 포함되어 있는지 확인할 샘플 추출
            for encoding in encodings_to_try:
                try:
                    # 디코딩 시도
                    decoded = raw_data.decode(encoding, errors='strict')

                    # 한글이 포함되어 있는지 확인
                    korean_ratio = _calculate_korean_ratio(decoded)

                    if korean_ratio > 0.1:  # 10% 이상 한글이면 성공
                        logger.info(f"폴백 인코딩 감지 성공: {encoding} (한글 비율: {korean_ratio:.2%})")
                        return encoding
                    elif encoding == 'utf-8' and not any(ord(c) > 127 for c in decoded if c.strip()):
                        # ASCII 범위만 있으면 UTF-8로 간주
                        logger.info(f"ASCII 전용 파일, UTF-8 사용: {encoding}")
                        return encoding

                except (UnicodeDecodeError, UnicodeError):
                    # 이 인코딩은 맞지 않음, 다음 시도
                    continue

        logger.warning("모든 인코딩 시도 실패, UTF-8 기본값 사용")
        return 'utf-8'

    except Exception as e:
        logger.error(f"폴백 인코딩 감지 중 오류: {e}")
        return 'utf-8'


def _direct_byte_conversion(text: str) -> str:
    """바이트 레벨에서 직접 변환을 시도합니다."""
    try:
        # 실제 HWP 파일에서 발견된 중국어 문자를 한글로 직접 매핑
        chinese_to_korean_map = {
            # 실제 파일에서 발견된 오류 사례들
            "捤": "첨",
            "獥": "부",
            "汤": "탕",
            "捯": "도",
            "摂": "섭",
            "浧": "영",
            # 추가 매핑 (일반적인 오류 패턴)
            "氠": "",  # 빈 문자로 처리
            "瑢": "",  # 빈 문자로 처리
            "漠": "",  # 빈 문자로 처리
            "杳": "",
            "氠瑢": "",  # 패턴으로 제거
            "氠瑢    ": "",  # 공백 포함 패턴
            "    汤捯": "",  # 공백 포함 패턴
            "漠杳": "",  # 패턴으로 제거
            # 한글 매핑 (자주 발견되는 패턴)
            "재": "재",
            "단": "단",
            "법": "법",
            "인": "인",
            "부": "부",
            "산": "산",
            "테": "테",
            "크": "크",
            "노": "노",
            "파": "파",
            "공": "공",
            "고": "고",
            "제": "제",
            "호": "호",
            # 일반적인 중국어-한글 매핑
            "中": "중",
            "国": "국",
            "企": "기",
            "业": "업",
            "技": "기",
            "术": "술",
            "支": "지",
            "持": "지",
            "金": "금",
            "额": "액",
            "项": "항",
            "目": "목",
            "申": "신",
            "请": "청",
            "方": "방",
            "法": "법",
            "选": "선",
            "择": "택",
            "条": "조",
            "件": "건",
            "内": "내",
            "容": "용",
            "要": "요",
            "求": "구",
        }

        result = text

        # 패턴별로 제거/교체
        for chinese, korean in chinese_to_korean_map.items():
            result = result.replace(chinese, korean)

        # 연속된 공백 정리
        import re

        result = re.sub(r"\s+", " ", result)
        result = result.strip()

        return result

    except Exception:
        return text


def _recover_from_cyrillic(text: str) -> str:
    """
    키릴 문자로 잘못 인코딩된 한글 텍스트를 복구합니다.

    HWP 파일에서 HTML 변환 시 한글 EUC-KR/CP949 바이트가
    키릴 문자(Cyrillic)로 잘못 해석된 경우를 처리합니다.

    예: 'лҸ…мқј көӯм ң' (키릴) -> '독일 조명 및' (한글)

    Args:
        text: 키릴 문자가 포함된 텍스트

    Returns:
        복구된 텍스트 (실패 시 원본)
    """
    try:
        # UTF-8 바이트를 얻음
        utf8_bytes = text.encode('utf-8')

        # 방법 1: UTF-8 바이트를 ISO-8859-1로 디코딩 후 EUC-KR로 재해석
        try:
            # UTF-8 -> ISO-8859-1 (바이트 값 보존) -> EUC-KR
            latin1_text = utf8_bytes.decode('iso-8859-1')
            recovered = latin1_text.encode('iso-8859-1').decode('euc-kr', errors='ignore')

            # 복구 결과 검증 - 한글이 포함되어 있는지 확인 (임계값 낮춤: 10자 -> 1자)
            korean_chars = sum(1 for c in recovered if 0xAC00 <= ord(c) <= 0xD7AF)
            if korean_chars > 1:  # 최소 1자 이상 한글이 있어야 성공으로 간주
                logger.info(f"키릴->한글 복구 성공 (방법1: ISO-8859-1->EUC-KR): {korean_chars}자 한글 복구")
                return recovered
        except Exception as e:
            logger.debug(f"키릴 복구 방법1 실패: {e}")

        # 방법 2: CP949 시도
        try:
            latin1_text = utf8_bytes.decode('iso-8859-1')
            recovered = latin1_text.encode('iso-8859-1').decode('cp949', errors='ignore')

            korean_chars = sum(1 for c in recovered if 0xAC00 <= ord(c) <= 0xD7AF)
            if korean_chars > 1:  # 임계값 낮춤: 10자 -> 1자
                logger.info(f"키릴->한글 복구 성공 (방법2: ISO-8859-1->CP949): {korean_chars}자 한글 복구")
                return recovered
        except Exception as e:
            logger.debug(f"키릴 복구 방법2 실패: {e}")

        # 방법 3: Windows-1251 (키릴 인코딩) -> EUC-KR
        try:
            # 현재 UTF-8 문자열을 Windows-1251 바이트로 재해석
            cp1251_bytes = text.encode('cp1251', errors='ignore')
            recovered = cp1251_bytes.decode('euc-kr', errors='ignore')

            korean_chars = sum(1 for c in recovered if 0xAC00 <= ord(c) <= 0xD7AF)
            if korean_chars > 1:  # 임계값 낮춤: 10자 -> 1자
                logger.info(f"키릴->한글 복구 성공 (방법3: CP1251->EUC-KR): {korean_chars}자 한글 복구")
                return recovered
        except Exception as e:
            logger.debug(f"키릴 복구 방법3 실패: {e}")

        logger.warning("키릴 복구 실패 - 원본 반환")
        return text

    except Exception as e:
        logger.error(f"키릴 복구 중 오류: {e}")
        return text


def should_exclude_file(file_path: Path) -> bool:
    """
    파일명에 제외 키워드가 포함되어 있는지 확인합니다.

    Args:
        file_path: 검사할 파일 경로

    Returns:
        bool: 제외해야 하는 파일이면 True, 아니면 False
    """
    import re

    filename = file_path.name
    filename_lower = filename.lower()

    # 공고 관련 파일은 항상 포함 (우선순위 최상위)
    if "공고" in filename_lower:
        logger.info(f"공고 파일 포함: {filename}")
        return False

    # 1. 정규식 패턴으로 복잡한 패턴 검사
    regex_patterns = [
        # r"붙임\s*\d+",  # 붙임1, 붙임 1, 붙임2 등
        # r"별첨\s*\d+",  # 별첨1, 별첨 1, 별첨2 등
        r"별지\s*\d+",  # 별지1, 별지 1, 별지2 등
        r"부록\s*\d+",  # 부록1, 부록 1, 부록2 등
        # r"\[서식\d*[-\d]*\]",  # [서식1], [서식2], [서식2-7] 등
        # r"\(서식\d*[-\d]*\)",  # (서식1), (서식2), (서식2-7) 등
        # r"서식\s*\d+[-\d]*",  # 서식1, 서식2, 서식2-7 등
        r"양식\s*\d+[-\d]*",  # 양식1, 양식2, 양식2-7 등
        r"첨부\s*문서",  # 첨부문서, 첨부 문서
        r"첨부\s*서류",  # 첨부서류, 첨부 서류
        r"첨부\s*자료",  # 첨부자료, 첨부 자료
        r"매뉴얼\s*\d+",  # 매뉴얼1
    ]

    found_patterns = []
    for pattern in regex_patterns:
        if re.search(pattern, filename, re.IGNORECASE):
            found_patterns.append(pattern)

    if found_patterns:
        logger.info(f"파일 제외 - 패턴 매칭: {filename} -> {found_patterns}")
        return True

    # 2. 우선순위 키워드 시스템 (중요한 파일은 제외하지 않음)
    priority_keywords = [
        # 공고 관련 (최우선)
        "공고문",
        "공고",
        "공문",
        "모집공고",
        "선정공고",
        "발표공고",
        # 사업 관련
        "사업",
        "지원사업",
        "보조사업",
        "지원",
        "보조금",
        "보조",
        # 신청/모집 관련
        "모집",
        "신청",
        "참여",
        "접수",
        # 계획/제안 관련
        "계획서",
        "제안서",
        "사업계획",
        "추진계획",
    ]

    # 우선순위 키워드가 있으면 제외하지 않음
    for priority in priority_keywords:
        if priority in filename_lower:
            logger.info(f"파일 포함 - 우선순위 키워드 발견: {filename} -> [{priority}]")
            return False

    # 3. 기본 키워드 검사 (우선순위 키워드가 없는 경우만)
    exclude_keywords = [
        # 기본 서식/양식 관련
        "서식",
        "양식",
        "form",
        "template",
        "템플릿",
        # 첨부/별첨 관련
        "별첨",
        "첨부",
        "별표",
        "참고자료",
        "참조",
        "별지",
        "부록",
        # 신청서 관련 (확장)
        "신청서",
        "신청양식",
        "신청서양식",
        "입주신청서",
        "참가신청서",
        "지원신청서",
        "접수신청서",
        "등록신청서",
        "회원신청서",
        "가입신청서",
        # 첨부 관련 확장
        "첨부문서",
        "첨부서류",
        "첨부자료",
        # 기타 제외 대상
        "예시",
        "샘플",
        "sample",
        "example",
        "안내서",
        "가이드",
        "guide",
        "manual",
        "매뉴얼",
        "체크리스트",
        "checklist",
        "점검표",
        "계획서템플릿",
        "제안서템플릿",
        "보고서템플릿",
        # FAQ는 더 구체적으로 (단독 FAQ 파일만)
        "faq.",
        "_faq",
        "faq_",
        "자주묻는질문",
    ]

    found_exclude_keywords = []
    for exclude in exclude_keywords:
        if exclude in filename_lower:
            found_exclude_keywords.append(exclude)

    if found_exclude_keywords:
        logger.info(
            f"파일 제외 - 제외 키워드 발견: {filename} -> {found_exclude_keywords}"
        )
        return True

    return False


def normalize_text(text: str) -> str:
    """
    텍스트를 정규화합니다 (소문자화, 공백 제거, 특수문자 제거).

    Args:
        text: 정규화할 텍스트

    Returns:
        정규화된 텍스트
    """
    if not text:
        return ""

    # 소문자화 및 공백 제거
    normalized = text.lower().replace(" ", "")

    # 특수문자 제거 (알파벳, 숫자, 한글만 유지)
    normalized = "".join(c for c in normalized if c.isalnum() or c in "가-힣")

    return normalized


def convert_code_info():
    """
    코드 상수 값들을 문자열로 반환합니다.

    Returns:
        str: 코드 정보가 포함된 문자열
    """

    # 코드 사전 목록
    code_dicts = {
        "소관기관코드 (RCPT_INST_CD)": RCPT_INST_CD,
        "소관기관유형코드 (RCPT_INST_CTGR_CD)": RCPT_INST_CTGR_CD,
        "지원대상구분코드 (SPOT_TRG_DV_CD)": SPOT_TRG_DV_CD,
        "지원대상창업구분코드 (SPOT_TRG_STRTUP_DV_CD)": SPOT_TRG_STRTUP_DV_CD,
        "지원대상지역코드 (SPOT_TRG_AREA_CD)": SPOT_TRG_AREA_CD,
        "신청방법코드 (APL_MTHD_CD)": APL_MTHD_CD,
        "우대제한구분코드 (PRF_RSTR_DV_CD)": PRF_RSTR_DV_CD,
        "업종코드 (INDST_CD)": INDST_CD,
        "지원분야구분코드 (SPOT_TYP_DV_CD)": SPOT_TYP_DV_CD,
    }

    # 모든 코드 정보를 문자열로 생성
    code_info_str = ""
    for title, code_dict in code_dicts.items():
        code_info_str += f"- {title}\n"
        for name, code in code_dict.items():
            code_info_str += f"    - {name} : {code}\n"
        code_info_str += "\n"

    # 마지막 줄바꿈 하나 제거
    return code_info_str.rstrip()


def listToStr(data) -> str:
    """
    리스트를 문자열로 변환합니다. (타입 안전성 개선)

    Args:
        data: 변환할 데이터 (리스트, 문자열, 또는 기타)

    Returns:
        문자열
    """
    # None 체크
    if data is None:
        return ""

    # 이미 문자열인 경우 그대로 반환 (중요!)
    if isinstance(data, str):
        return data

    # 리스트가 아닌 경우 문자열로 변환
    if not isinstance(data, (list, tuple)):
        return str(data)

    # 빈 리스트 체크
    if len(data) == 0:
        return ""

    # 배열이 개별 문자로 분리된 경우 감지 및 복원
    if len(data) > 10 and all(len(str(item)) <= 3 for item in data):
        # 대부분의 요소가 3자 이하이면 문자열이 분리된 것으로 판단
        result = "".join(str(item) for item in data)
    else:
        # 정상적인 배열인 경우 쉼표로 연결
        result = ", ".join(str(item) for item in data if item)

    return result


def strToInt(data) -> int:
    """
    문자열을 정수로 변환합니다.

    Args:
        data: 변환할 문자열 또는 정수

    Returns:
        정수
    """
    if data is None:
        return 0
    if isinstance(data, int):
        return data
    if isinstance(data, str) and (data == "" or data == "null"):
        return 0
    if isinstance(data, str) and len(data) == 0:
        return 0
    try:
        return int(data)
    except (ValueError, TypeError):
        return 0


def convert_pdf_to_md_docling(pdf_path: str, output_path: str = None) -> bool:
    """
    Docling을 사용하여 PDF 파일을 Markdown으로 변환합니다.
    표 구조 보존과 OCR 기능을 최우선으로 설정합니다.

    Args:
        pdf_path (str): 변환할 PDF 파일 경로
        output_path (str, optional): 출력할 마크다운 파일 경로

    Returns:
        bool: 변환 성공 여부
    """
    try:
        # 제외할 키워드 검사 (서식, 양식 등)
        if should_exclude_file(Path(pdf_path)):
            return False

        with Timer(f"PDF 파일 변환 (Docling): {pdf_path}", totalTimeChk=False):
            try:
                from docling.document_converter import (
                    DocumentConverter,
                    PdfFormatOption,
                )
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import (
                    OcrOptions,
                    PdfPipelineOptions,
                    TableStructureOptions,
                )

                logger.info("!!docling IMPORT!!!")
            except ImportError as e:
                logger.error(f"Docling 라이브러리를 import할 수 없습니다: {e}")
                logger.info("pip install docling을 실행해주세요")
                return False

            # 표 구조 보존 옵션 설정 (사용자 요구사항)
            try:
                table_options = TableStructureOptions(
                    do_cell_matching=False,  # 셀 매칭 활성화
                )

                pipeline_options = PdfPipelineOptions(
                    do_table_structure=True,  # 표 구조 인식 활성화
                    table_structure_options=table_options,
                )

                pipeline_options.do_ocr = True
                pipeline_options.ocr_options.use_gpu = False

                pdf_format_options = PdfFormatOption(pipeline_options=pipeline_options)
                converter = DocumentConverter(
                    format_options={InputFormat.PDF: pdf_format_options}
                )
                logger.info("표 구조 인식 활성화된 DocumentConverter 생성 완료")
            except Exception as opt_error:
                logger.warning(f"고급 옵션 설정 실패, 기본 변환기 사용: {opt_error}")
                converter = DocumentConverter()

            # PDF 파일 유효성 검사 (개선된 버전)
            try:
                with open(pdf_path, "rb") as f:
                    header = f.read(4)
                    if header != b"%PDF":
                        logger.warning(
                            f"유효하지 않은 PDF 파일 (헤더 불일치): {pdf_path}"
                        )
                        return False

                    # PDF 파일 구조 기본 검사 - 더 큰 범위를 검사하거나 건너뛰기
                    # Root 객체는 파일 어디에나 있을 수 있으므로 전체 파일을 검사하거나
                    # 또는 이 검사를 건너뛰고 변환 시도를 하는 것이 더 좋을 수 있음
                    file_size = os.path.getsize(pdf_path)
                    if file_size > 0:
                        # 파일이 비어있지 않으면 변환 시도
                        f.seek(0)
                        # 파일이 너무 크면 처음 10KB만 확인, 작으면 전체 확인
                        check_size = min(10240, file_size)  # 10KB 또는 파일 전체
                        content = f.read(check_size)

                        # Root 객체가 없어도 경고만 출력하고 변환 시도
                        if b"/Root" not in content:
                            logger.warning(
                                f"PDF 파일에 Root 객체가 처음 {check_size}바이트 내에 없음: {pdf_path}"
                            )
                            logger.info(
                                "Root 객체가 뒤쪽에 있을 수 있으니 변환 시도를 계속합니다..."
                            )
                            # return False를 제거하여 변환 계속 진행
                    else:
                        logger.error(f"PDF 파일이 비어있음: {pdf_path}")
                        return False

            except Exception as e:
                logger.error(f"PDF 파일 읽기 실패: {e}")
                # 읽기 실패해도 변환은 시도해볼 수 있음
                logger.info("PDF 파일 읽기 실패했지만 변환 시도를 계속합니다...")

            # PDF 변환 실행
            try:
                conversion_result = converter.convert(pdf_path)

                # Markdown으로 내보내기
                markdown_content = conversion_result.document.export_to_markdown()
                # logger.info(markdown_content)

                # 내용이 비어있는지 확인
                if not markdown_content or not markdown_content.strip():
                    logger.warning(f"Docling 변환 결과가 비어있음: {pdf_path}")
                    return convert_pdf_to_md_markitdown_fallback(pdf_path, output_path)

                # 파일에 저장
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(markdown_content)

                logger.info(f"Docling PDF 변환 완료: {output_path}")
                return True

            except UnicodeDecodeError as ude:
                logger.warning(f"Docling PDF 인코딩 오류 감지: {pdf_path} - {ude}")

                # 인코딩 자동 감지 및 재시도
                detected_encoding = _detect_pdf_encoding(pdf_path)
                if detected_encoding and detected_encoding.lower() != 'utf-8':
                    logger.info(f"감지된 인코딩: {detected_encoding}, 재변환 시도")
                    try:
                        # 감지된 인코딩으로 PDF 재처리 시도
                        conversion_result = converter.convert(pdf_path)
                        markdown_content = conversion_result.document.export_to_markdown()

                        if markdown_content and markdown_content.strip():
                            # 인코딩 수정 후 저장
                            try:
                                # 감지된 인코딩으로 디코드 후 UTF-8로 재인코딩
                                if isinstance(markdown_content, bytes):
                                    markdown_content = markdown_content.decode(detected_encoding, errors='replace')

                                with open(output_path, "w", encoding="utf-8") as f:
                                    f.write(markdown_content)

                                logger.info(f"인코딩 수정 후 Docling 변환 완료: {output_path}")
                                return True
                            except Exception as enc_e:
                                logger.warning(f"인코딩 변환 실패: {enc_e}")
                    except Exception as retry_e:
                        logger.warning(f"인코딩 수정 후 재시도 실패: {retry_e}")

                logger.info(f"인코딩 오류로 markitdown 폴백: {pdf_path}")
                return convert_pdf_to_md_markitdown_fallback(pdf_path, output_path)
            except Exception as conv_e:
                logger.warning(f"Docling 변환 실행 중 오류: {pdf_path} - {conv_e}")
                logger.info(f"Docling 변환 실패, markitdown 폴백: {pdf_path}")
                return convert_pdf_to_md_markitdown_fallback(pdf_path, output_path)

    except UnicodeDecodeError as e:
        logger.warning(f"Docling PDF 인코딩 오류: {pdf_path} - {e}")
        logger.info(f"인코딩 오류로 markitdown 폴백: {pdf_path}")
        return convert_pdf_to_md_markitdown_fallback(pdf_path, output_path)
    except Exception as e:
        logger.error(f"Docling PDF 변환 중 오류 발생: {e}")
        # 기존 markitdown으로 폴백
        logger.info(f"Docling 변환 실패, markitdown으로 폴백: {pdf_path}")
        return convert_pdf_to_md_markitdown_fallback(pdf_path, output_path)


def convert_pdf_to_md_markitdown_fallback(
    pdf_path: str, output_path: str = None
) -> bool:
    """
    기존 markitdown을 사용한 PDF 변환 (Docling 실패시 폴백용)

    Args:
        pdf_path (str): 변환할 PDF 파일 경로
        output_path (str, optional): 출력할 마크다운 파일 경로

    Returns:
        bool: 변환 성공 여부
    """
    try:
        try:
            from markitdown import MarkItDown
        except (ImportError, AttributeError) as e:
            logger.warning(f"MarkItDown import 실패 (NumPy 호환성 문제 가능): {e}")
            logger.info("MarkItDown 없이 다른 방법으로 PDF 처리")
            return False

        # PDF 파일 존재 및 크기 확인
        if not os.path.exists(pdf_path):
            logger.error(f"PDF 파일이 존재하지 않음: {pdf_path}")
            return False

        file_size = os.path.getsize(pdf_path)
        if file_size == 0:
            logger.error(f"PDF 파일이 비어있음: {pdf_path}")
            return False

        if file_size > 100 * 1024 * 1024:  # 100MB 제한
            logger.warning(f"PDF 파일이 너무 큼 (>100MB): {pdf_path}")
            return False

        ## markitdown START ##
        md = MarkItDown(enable_plugins=False)

        result = md.convert(pdf_path)

        # 변환 결과 검증
        if not result or not hasattr(result, "text_content") or not result.text_content:
            logger.warning(f"Markitdown 변환 결과가 비어있음: {pdf_path}")
            return False

        # 내용이 너무 짧으면 변환 실패로 간주
        if len(result.text_content.strip()) < 10:
            logger.warning(f"Markitdown 변환 결과가 너무 짧음: {pdf_path}")
            return False

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result.text_content)

        logger.info(f"Markitdown 폴백 변환 완료: {output_path}")
        return True

    except UnicodeDecodeError as e:
        logger.error(f"Markitdown 유니코드 디코딩 오류: {e}")
        return False
    except Exception as e:
        error_msg = str(e)
        if "PDFSyntaxError" in error_msg or "No /Root object" in error_msg:
            logger.warning(f"손상된 PDF 파일로 변환 불가: {pdf_path}")
        elif "Invalid code point" in error_msg:
            logger.warning(f"잘못된 코드 포인트로 변환 불가: {pdf_path}")
        elif "File conversion failed" in error_msg:
            logger.warning(f"PDF 변환기에서 파일 변환 실패: {pdf_path}")
        else:
            logger.error(
                f"Markitdown 폴백 변환 중 예상치 못한 오류: {e}\n{traceback.format_exc()}"
            )
        return False


def convert_pdf_to_md_markitdown(pdf_path: str, output_path: str = None) -> bool:
    """
    기존 markitdown을 사용한 PDF 변환 (하위 호환성 유지)
    """
    return convert_pdf_to_md_markitdown_fallback(pdf_path, output_path)


def find_pdf_files(directory: str, md_file: str = None) -> list[str]:
    """
    지정된 디렉토리에서 PDF 파일을 찾습니다.
    절대 경로와 상대 경로를 모두 지원합니다.
    프로젝트 루트의 data 폴더도 검색합니다.

    Args:
        directory (str): 검색할 디렉토리 경로 (절대 경로 또는 상대 경로)
        md_filename (str, optional): 마크다운 파일명 (data 폴더 검색용)

    Returns:
        list[str]: 발견된 PDF 파일들의 절대 경로 리스트
    """
    try:
        pdf_files = []

        pdf_dir_path = Path(directory) / md_file

        for root, _, files in os.walk(pdf_dir_path):
            for file in files:
                try:
                    if file.lower().endswith(".pdf"):
                        pdf_files.append(os.path.abspath(os.path.join(root, file)))
                except Exception as e:
                    logger.error(
                        f"PDF 파일 처리 중 오류: {file} - {str(e)}\n{traceback.format_exc()}"
                    )
                    continue

        return pdf_files

    except Exception as e:
        logger.error(
            f"PDF 파일 검색 중 오류: {directory}/{md_file} - {str(e)}\n{traceback.format_exc()}"
        )
        return []


def find_hwp_files(directory: str, md_file: str = None) -> list[str]:
    """
    지정된 디렉토리에서 HWP 파일을 찾습니다.
    절대 경로와 상대 경로를 모두 지원합니다.
    프로젝트 루트의 data 폴더도 검색합니다.

    Args:
        directory (str): 검색할 디렉토리 경로 (절대 경로 또는 상대 경로)
        md_filename (str, optional): 마크다운 파일명 (data 폴더 검색용)

    Returns:
        list[str]: 발견된 HWP 파일들의 절대 경로 리스트
    """
    try:
        hwp_files = []

        hwp_dir_path = Path(directory) / md_file

        for root, _, files in os.walk(hwp_dir_path):
            for file in files:
                try:
                    if file.lower().endswith((".hwp", ".hwpx")):
                        hwp_files.append(os.path.abspath(os.path.join(root, file)))
                except Exception as e:
                    logger.error(
                        f"HWP 파일 처리 중 오류: {file} - {str(e)}\n{traceback.format_exc()}"
                    )
                    continue

        if not hwp_files:
            logger.warning(f"HWP 파일을 찾을 수 없습니다: {hwp_dir_path}")

        return hwp_files

    except Exception as e:
        logger.error(
            f"HWP 파일 검색 중 오류: {directory}/{md_file} - {str(e)}\n{traceback.format_exc()}"
        )
        return []


def convert_text_to_markdown(text: str) -> str:
    """
    추출된 텍스트를 Markdown 형식으로 변환합니다.

    Args:
        text (str): 변환할 텍스트
    Returns:
        str: Markdown 형식으로 변환된 텍스트
    """
    try:
        lines = text.split("\n")
        markdown_lines = []
        in_list = False

        for line in lines:
            try:
                # 빈 줄 처리
                if not line.strip():
                    markdown_lines.append("")
                    in_list = False
                    continue

                # 제목 처리 (숫자로 시작하는 제목)
                if re.match(r"^\d+\.", line.strip()):
                    markdown_lines.append(f"## {line}")
                    continue

                # 목록 처리
                if line.strip().startswith("•") or line.strip().startswith("-"):
                    if not in_list:
                        markdown_lines.append("")
                    markdown_lines.append(line.replace("•", "-"))
                    in_list = True
                    continue

                # 일반 텍스트
                if in_list:
                    markdown_lines.append("")
                    in_list = False
                markdown_lines.append(line)

            except Exception as line_e:
                logger.error(
                    f"마크다운 변환 중 라인 처리 오류: {line} - {str(line_e)}\n{traceback.format_exc()}"
                )
                # 오류 발생 라인은 그대로 추가
                markdown_lines.append(line)

        return "\n".join(markdown_lines)

    except Exception as e:
        logger.error(
            f"텍스트 마크다운 변환 중 오류: {str(e)}\n{traceback.format_exc()}"
        )
        # 오류 발생 시 원본 텍스트 반환
        return text


# def hwpx_to_hwp(hwpx_file, hwp_file=None):
#     """
#     hwpx → hwp 변환 (한 줄 호출)

#     Usage:
#         hwpx_to_hwp("문서.hwpx")  # 자동으로 문서.hwp 생성
#         hwpx_to_hwp("문서.hwpx", "결과.hwp")
#     """
#     try:
#         from pyhwpx import Hwp

#         if hwp_file is None:
#             hwp_file = hwpx_file.replace('.hwpx', '.hwp')

#         hwp = Hwp(visible=False)
#         hwp.open(hwpx_file)
#         hwp.save_as(hwp_file, format="HWP")
#         hwp.quit()

#         logger.info(f"✅ {hwpx_file} → {hwp_file}")
#         return True

#     except Exception as e:
#         logger.error(f"❌ 실패: {e}")
#         return False

# def hwpx_to_html(hwpx_file, html_file=None):
#     """
#     hwpx → html 변환 (한 줄 호출)

#     Usage:
#         hwpx_to_html("문서.hwpx")  # 자동으로 문서.html 생성
#         hwpx_to_html("문서.hwpx", "결과.html")
#     """
#     try:
#         from pyhwpx import Hwp

#         if html_file is None:
#             html_file = hwpx_file.replace('.hwpx', '.html')

#         hwp = Hwp(visible=False)
#         hwp.open(hwpx_file)
#         hwp.save_as(html_file, format="HTML")
#         hwp.quit()

#         logger.info(f"✅ {hwpx_file} → {html_file}")
#         return True

#     except Exception as e:
#         logger.error(f"❌ 실패: {e}")
#         return False


def convert_html_to_md_markitdown(html_path: str, output_path: str = None) -> bool:
    """
    HTML 파일을 Markdown으로 변환합니다.

    Args:
        pdf_path (str): 변환할 PDF 파일 경로
        output_path (str, optional): 출력할 마크다운 파일 경로.
            None인 경우 PDF 파일과 동일한 위치에 저장됩니다.

    Returns:
        bool: 변환 성공 여부
    """
    try:
        try:
            from markitdown import MarkItDown
        except (ImportError, AttributeError) as e:
            logger.warning(f"MarkItDown import 실패 (NumPy 호환성 문제 가능): {e}")
            return False

        ## markitdown START ##
        md = MarkItDown(enable_plugins=False)
        result = md.convert(html_path)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result.text_content)
        ## markitdown END ##

        logger.info(f"변환 완료: {output_path}")
        return True

    except Exception as e:
        logger.error(f"변환 중 오류 발생: {e}\n{traceback.format_exc()}")
        return False


def convert_pdf_to_html_pdfminder(pdf_path: str, output_path: str = None) -> bool:
    """
    PDF 파일을 Markdown으로 변환합니다.

    Args:
        pdf_path (str): 변환할 PDF 파일 경로
        output_path (str, optional): 출력할 마크다운 파일 경로.
            None인 경우 PDF 파일과 동일한 위치에 저장됩니다.

    Returns:
        bool: 변환 성공 여부
    """
    try:
        from pdfminer.converter import HTMLConverter
        from pdfminer.layout import LAParams
        from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
        from pdfminer.pdfpage import PDFPage

        rsrcmgr = PDFResourceManager()
        laparams = LAParams()

        # 파일로 바로 저장
        with (
            open(pdf_path, "rb") as fp,
            open(output_path, "w", encoding="utf-8") as outfp,
        ):
            device = HTMLConverter(rsrcmgr, outfp, laparams=laparams)
            interpreter = PDFPageInterpreter(rsrcmgr, device)
            for page in PDFPage.get_pages(fp, check_extractable=True):
                interpreter.process_page(page)
            device.close()

        logger.info(f"변환 완료: {output_path}")
        return True

    except Exception as e:
        logger.error(f"변환 중 오류 발생: {e}\n{traceback.format_exc()}")
        return False


def convert_pdf_to_text_simple(pdf_path: str, output_path: str = None) -> bool:
    """
    PDFMiner를 사용해 PDF에서 텍스트를 간단히 추출합니다.

    Args:
        pdf_path (str): 변환할 PDF 파일 경로
        output_path (str): 출력할 텍스트 파일 경로

    Returns:
        bool: 변환 성공 여부
    """
    try:
        # 색상 오류를 완전히 무시하는 환경 설정
        import os

        os.environ["PDFMINER_IGNORE_COLOR_ERRORS"] = "1"

        # PDFMiner 설정으로 색상 관련 오류 방지
        from pdfminer.high_level import extract_text
        from pdfminer.layout import LAParams

        # 색상 관련 오류를 무시하는 설정
        laparams = LAParams(
            line_margin=0.5,
            word_margin=0.1,
            char_margin=2.0,
            boxes_flow=0.5,
            detect_vertical=True,
            all_texts=True,
        )

        # 색상 관련 경고 무시
        import warnings

        warnings.filterwarnings("ignore", category=UserWarning, module="pdfminer")
        warnings.filterwarnings("ignore", message=".*color.*", category=UserWarning)

        # 색상 오류를 완전히 우회하는 패치 적용
        try:
            from pdfminer.pdfcolor import PDFColorSpace

            original_set_gray = PDFColorSpace.set_gray

            def safe_set_gray(self, gray):
                try:
                    return original_set_gray(self, gray)
                except (ValueError, TypeError):
                    # 색상 오류 무시
                    return None

            PDFColorSpace.set_gray = safe_set_gray

            # 추가 색상 관련 메서드들도 패치
            if hasattr(PDFColorSpace, "set_rgb"):
                original_set_rgb = PDFColorSpace.set_rgb

                def safe_set_rgb(self, r, g, b):
                    try:
                        return original_set_rgb(self, r, g, b)
                    except (ValueError, TypeError):
                        return None

                PDFColorSpace.set_rgb = safe_set_rgb

            if hasattr(PDFColorSpace, "set_cmyk"):
                original_set_cmyk = PDFColorSpace.set_cmyk

                def safe_set_cmyk(self, c, m, y, k):
                    try:
                        return original_set_cmyk(self, c, m, y, k)
                    except (ValueError, TypeError):
                        return None

                PDFColorSpace.set_cmyk = safe_set_cmyk

            # 색상 공간 초기화 메서드도 패치
            if hasattr(PDFColorSpace, "__init__"):
                original_init = PDFColorSpace.__init__

                def safe_init(self, *args, **kwargs):
                    try:
                        return original_init(self, *args, **kwargs)
                    except (ValueError, TypeError):
                        # 기본값으로 초기화
                        self.name = "DeviceGray"
                        self.ncomponents = 1
                        return None

                PDFColorSpace.__init__ = safe_init

        except ImportError:
            pass  # PDFMiner 버전에 따라 없을 수 있음

        try:
            # 색상 관련 오류를 무시하고 텍스트 추출
            try:
                text = extract_text(pdf_path, laparams=laparams)
            except Exception as color_error:
                # 색상 관련 오류인지 확인
                error_msg = str(color_error).lower()
                if any(
                    keyword in error_msg
                    for keyword in [
                        "color",
                        "gray",
                        "stroke",
                        "invalid float",
                        "p67",
                        "pa1",
                        "pa2",
                    ]
                ):
                    logger.warning(
                        f"색상 관련 오류 감지, 대안 방법으로 재시도: {color_error}"
                    )
                    # 대안 방법으로 재시도
                    text = extract_text(pdf_path, laparams=laparams, codec="utf-8")
                else:
                    raise color_error
        except Exception as page_error:
            logger.warning(
                f"PDFMiner 텍스트 추출 중 오류 (색상 관련 오류일 수 있음): {page_error}"
            )

            # 색상 오류인 경우 더 안전한 방법으로 재시도
            try:
                from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
                from pdfminer.converter import TextConverter
                from pdfminer.pdfpage import PDFPage
                import io
                import warnings

                # 색상 관련 경고 무시
                warnings.filterwarnings(
                    "ignore", category=UserWarning, module="pdfminer"
                )
                warnings.filterwarnings(
                    "ignore", message=".*color.*", category=UserWarning
                )
                warnings.filterwarnings(
                    "ignore", message=".*gray.*", category=UserWarning
                )
                warnings.filterwarnings(
                    "ignore", message=".*stroke.*", category=UserWarning
                )

                # 색상 처리를 완전히 비활성화한 설정
                rsrcmgr = PDFResourceManager()
                retstr = io.StringIO()
                device = TextConverter(rsrcmgr, retstr, laparams=laparams)

                with open(pdf_path, "rb") as fp:
                    interpreter = PDFPageInterpreter(rsrcmgr, device)
                    for page in PDFPage.get_pages(fp, check_extractable=True):
                        try:
                            interpreter.process_page(page)
                        except Exception as page_ex:
                            # 색상 관련 오류인지 확인 (더 포괄적으로)
                            error_msg = str(page_ex).lower()
                            color_keywords = [
                                "color",
                                "gray",
                                "stroke",
                                "invalid float",
                                "p67",
                                "pa1",
                                "pa2",
                                "non-stroke",
                            ]
                            if any(keyword in error_msg for keyword in color_keywords):
                                logger.debug(
                                    f"색상 관련 오류 무시하고 계속 진행: {page_ex}"
                                )
                                continue
                            else:
                                logger.debug(f"페이지 처리 중 오류 무시: {page_ex}")
                                continue
                    device.close()
                    text = retstr.getvalue()
                    retstr.close()

                if not text.strip():
                    raise Exception("텍스트 추출 실패")

            except Exception as fallback_error:
                logger.error(f"PDF 텍스트 추출 fallback도 실패: {fallback_error}")
                return False
        logger.debug(f"PDF 원본 추출 텍스트 길이: {len(text)} 문자")

        # 텍스트 정리
        cleaned_text = text.strip()
        if len(cleaned_text) == 0:
            logger.warning(
                f"추출된 텍스트가 비어있음 - PDF가 스캔된 이미지이거나 보호된 파일일 수 있습니다: {pdf_path}"
            )

            # 대안적인 방법으로 시도
            try:
                logger.info("대안적인 PDF 텍스트 추출 시도 중...")
                import PyPDF2

                with open(pdf_path, "rb") as file:
                    reader = PyPDF2.PdfReader(file)
                    alt_text = ""
                    for page_num in range(len(reader.pages)):
                        page = reader.pages[page_num]
                        alt_text += page.extract_text() + "\n"

                    if alt_text.strip():
                        cleaned_text = alt_text.strip()
                        logger.info(
                            f"PyPDF2로 텍스트 추출 성공: {len(cleaned_text)} 문자"
                        )
                    else:
                        logger.warning("PyPDF2로도 텍스트 추출 실패")
                        return False

            except ImportError:
                logger.warning("PyPDF2가 설치되지 않음 - pip install PyPDF2")
                return False
            except Exception as alt_error:
                logger.error(f"대안적인 PDF 텍스트 추출 실패: {alt_error}")
                return False

        # 길이 제한 제거 - 모든 텍스트 허용
        logger.debug(f"추출된 텍스트 길이: {len(cleaned_text)} 문자")

        # output_path 미지정 시 텍스트 직접 반환
        if output_path is None:
            return cleaned_text

        # 파일로 저장 (output_path 지정된 경우)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(cleaned_text)

        # ProcessedDataManager가 이제 텍스트 저장을 처리합니다

        # 정리 - high-level API 사용시 별도 정리 불필요

        logger.info(f"PDF 텍스트 추출 완료: {output_path} ({len(cleaned_text)} 문자)")
        return True

    except Exception as e:
        logger.error(f"PDF 텍스트 추출 중 오류: {e}\n{traceback.format_exc()}")
        return "" if output_path is None else False


# marker-pdf 함수 제거됨 - 처리 속도 문제로 비활성화


def convert_pdf_with_ocr(pdf_path: str, output_path: str = None) -> bool:
    """
    PDF에서 이미지를 추출하고 OCR로 텍스트를 추출하여 마크다운으로 저장합니다.

    Args:
        pdf_path (str): 변환할 PDF 파일 경로
        output_path (str): 출력할 마크다운 파일 경로

    Returns:
        bool: 변환 성공 여부
    """
    try:
        # 제외할 키워드 검사
        if should_exclude_file(Path(pdf_path)):
            return False

        logger.info(f"PDF OCR 처리 시작: {pdf_path}")

        # PDF에서 이미지 추출
        images = extract_images_from_pdf(pdf_path)
        if not images:
            logger.warning(f"PDF에서 이미지 추출 실패: {pdf_path}")
            return False

        # OCR로 텍스트 추출
        markdown_content = []
        markdown_content.append("# PDF OCR 처리 결과\n")

        for i, image in enumerate(images):
            logger.info(f"이미지 {i+1}/{len(images)} OCR 처리 중...")

            # OCR 처리
            text = perform_ocr_on_image(image)
            if text and len(text.strip()) > 10:
                markdown_content.append(f"## 페이지 {i+1}\n")
                markdown_content.append(f"{text}\n\n")

        # 마크다운 파일로 저장
        if (
            markdown_content and len(markdown_content) > 1
        ):  # 헤더 외에 내용이 있는지 확인
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(markdown_content))

            logger.info(f"PDF OCR 변환 완료: {output_path}")
            return True
        else:
            logger.warning(f"OCR 결과가 부족함: {pdf_path}")
            return False

    except Exception as e:
        logger.warning(f"PDF OCR 처리 중 오류: {e}")
        return False


def extract_images_from_pdf(pdf_path: str) -> list:
    """
    PDF에서 이미지를 추출합니다.

    Args:
        pdf_path (str): PDF 파일 경로

    Returns:
        list: 추출된 이미지 객체 리스트
    """
    try:
        import fitz  # PyMuPDF

        images = []
        doc = fitz.open(pdf_path)

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)

            # 페이지를 이미지로 변환 (해상도 높게)
            mat = fitz.Matrix(2.0, 2.0)  # 2배 확대
            pix = page.get_pixmap(matrix=mat)

            # PIL Image로 변환
            import io

            from PIL import Image

            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))
            images.append(image)

        doc.close()
        logger.info(f"PDF에서 {len(images)}개 이미지 추출 완료")
        return images

    except Exception as e:
        logger.error(f"이미지 추출 중 오류: {e}")
        return []


def perform_ocr_on_image(image) -> str:
    """
    이미지에서 OCR로 텍스트를 추출합니다.

    Args:
        image: PIL Image 객체

    Returns:
        str: 추출된 텍스트
    """
    # 1차 시도: EasyOCR (우선순위 1)
    try:
        import easyocr
        import numpy as np

        # PIL Image를 numpy array로 변환
        img_array = np.array(image)

        # EasyOCR 리더 초기화 (한국어 + 영어)
        logger.info("EasyOCR 실행 중... (우선순위 1)")
        reader = easyocr.Reader(["ko", "en"], gpu=True)  # GPU 사용 활성화

        # OCR 수행
        results = reader.readtext(img_array)

        # 결과 정리
        lines = []
        for bbox, text, confidence in results:
            if confidence > 0.2 and len(text.strip()) > 1:  # 신뢰도 30% 이상 (지역명 등 포함)
                lines.append(text.strip())

        if lines:
            cleaned_text = "\n".join(lines)  # 줄바꿈으로 결합하여 레이아웃 보존

            # 표 형태 감지 및 마크다운 테이블로 변환 시도
            if "|" in cleaned_text or "\t" in cleaned_text:
                cleaned_text = format_as_markdown_table(cleaned_text)

            logger.info(f"EasyOCR 성공: {len(lines)}개 텍스트 추출")
            return cleaned_text

    except Exception as e:
        logger.warning(f"EasyOCR 실패, Tesseract로 폴백: {e}")

    # 2차 시도: Tesseract OCR (폴백)
    try:
        import pytesseract

        logger.info("Tesseract OCR 실행 중... (폴백)")
        # 한국어 + 영어 OCR 처리
        text = pytesseract.image_to_string(image, lang="kor+eng")

        if text and len(text.strip()) > 10:
            # 텍스트 정리
            lines = []
            for line in text.split("\n"):
                line = line.strip()
                if line and len(line) > 1:  # 의미있는 줄만 추가
                    lines.append(line)

            # 마크다운 형식으로 정리
            cleaned_text = "\n".join(lines)

            # 표 형태 감지 및 마크다운 테이블로 변환 시도
            if "|" in cleaned_text or "\t" in cleaned_text:
                cleaned_text = format_as_markdown_table(cleaned_text)

            logger.info(f"Tesseract 폴백 성공: {len(lines)}개 텍스트 추출")
            return cleaned_text

    except Exception as e:
        logger.warning(f"Tesseract OCR 폴백 실패: {e}")

    logger.error("모든 OCR 방법 실패")
    return ""


def markdown_to_plain_text(markdown_content: str) -> str:
    """
    마크다운 콘텐츠를 순수 텍스트로 변환합니다.
    extracted_text.txt 파일에는 마크다운 문법이 제거된 순수 텍스트만 들어가야 합니다.

    Args:
        markdown_content: 마크다운 형식의 텍스트

    Returns:
        순수 텍스트 (마크다운 문법 제거)
    """
    if not markdown_content:
        return ""

    text = markdown_content

    # 코드 블록 제거 (``` 또는 ~~~ 블록)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"~~~[\s\S]*?~~~", "", text)

    # 인라인 코드 제거 (`code`)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 헤더 마크다운 제거 (# ## ### 등)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # 볼드/이탤릭 마크다운 제거 (**text**, *text*, __text__, _text_)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # **bold**
    text = re.sub(r"\*([^*]+)\*", r"\1", text)  # *italic*
    text = re.sub(r"__([^_]+)__", r"\1", text)  # __bold__
    text = re.sub(r"_([^_]+)_", r"\1", text)  # _italic_

    # 링크 마크다운 제거 [text](url)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # 이미지 마크다운 제거 ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

    # 리스트 마커 제거 (- * + 1. 2. 등)
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)  # - * +
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)  # 1. 2. 3.

    # 인용문 마크다운 제거 (> text)
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)

    # 수평선 제거 (---, ***, ___)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # 테이블 구분자 제거 (|-----|-----|)
    text = re.sub(r"^\|[-:\s|]+\|\s*$", "", text, flags=re.MULTILINE)

    # 테이블 파이프 제거 (| cell | cell |)
    text = re.sub(r"^\|(.+)\|\s*$", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"\|", " ", text)  # 남은 파이프들을 공백으로

    # 여러 연속된 공백을 하나로 합치기
    text = re.sub(r"\s+", " ", text)

    # 여러 연속된 줄바꿈을 최대 2개로 제한
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    # 앞뒤 공백 제거
    text = text.strip()

    return text


def format_as_markdown_table(text: str) -> str:
    """
    텍스트를 마크다운 테이블 형식으로 변환 시도

    Args:
        text (str): 원본 텍스트

    Returns:
        str: 마크다운 테이블 또는 원본 텍스트
    """
    try:
        lines = text.split("\n")
        table_lines = []

        for line in lines:
            if "|" in line or "\t" in line:
                # 구분자로 분할
                if "\t" in line:
                    cols = [col.strip() for col in line.split("\t") if col.strip()]
                else:
                    cols = [col.strip() for col in line.split("|") if col.strip()]

                if len(cols) > 1:
                    table_lines.append("| " + " | ".join(cols) + " |")

        if len(table_lines) > 1:
            # 헤더와 구분선 추가
            header = table_lines[0]
            separator = "|" + "---|" * (header.count("|") - 1)

            return header + "\n" + separator + "\n" + "\n".join(table_lines[1:])

        return text

    except Exception:
        return text


def _convert_hwp_with_gethwp(hwp_file_path: Path, output_dir: Path) -> bool:
    """
    gethwp.read_hwp()를 사용하여 HWP 파일을 HTML로 변환하는 내부 헬퍼 함수.
    구형 HWP 포맷(HWP 3.0, HWP 96 등)을 처리합니다.

    Args:
        hwp_file_path: HWP 파일 경로
        output_dir: 출력 디렉토리

    Returns:
        bool: 변환 성공 시 True, 실패 시 False
    """
    try:
        # HWP 라이브러리 지연 로딩
        hwp_libs = get_hwp_libraries()
        hwp_custom = hwp_libs["hwp_custom"]

        # hwp_custom.read_hwp() 호출 (gethwp.read_hwp()를 래핑)
        hwp_text = hwp_custom.read_hwp(str(hwp_file_path))

        if hwp_text and hwp_text.strip():
            # 추출된 텍스트를 HTML 형태로 저장
            import html

            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{hwp_file_path.stem}</title>
</head>
<body>
    <pre>{html.escape(hwp_text)}</pre>
</body>
</html>"""
            # output_dir 생성 및 index.xhtml 저장
            output_dir.mkdir(parents=True, exist_ok=True)
            html_file = output_dir / "index.xhtml"
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(
                f"gethwp.read_hwp() 변환 성공: {hwp_file_path.name} → {html_file}"
            )
            return True
        else:
            logger.debug(
                f"gethwp.read_hwp() 텍스트 추출 실패: {hwp_file_path.name}"
            )
            return False
    except Exception as e:
        logger.debug(
            f"gethwp.read_hwp() 실패: {hwp_file_path.name} - {e}"
        )
        return False


def _convert_hwpx_file_to_html(hwpx_file_path: Path, output_dir: Path) -> bool:
    """
    HWPX 파일을 HTML로 변환하는 내부 헬퍼 함수.

    Args:
        hwpx_file_path: HWPX 파일 경로
        output_dir: 출력 디렉토리

    Returns:
        bool: 변환 성공 시 True, 실패 시 False
    """
    try:
        hwpx_text = convert_hwpx_to_text(hwpx_file_path)
        if hwpx_text and hwpx_text.strip():
            # 추출된 텍스트를 HTML 형태로 저장
            import html

            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{hwpx_file_path.stem}</title>
</head>
<body>
    <pre>{html.escape(hwpx_text)}</pre>
</body>
</html>"""
            # output_dir 생성 및 index.xhtml 저장
            output_dir.mkdir(parents=True, exist_ok=True)
            html_file = output_dir / "index.xhtml"
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(
                f"HWPX 파일 변환 성공: {hwpx_file_path.name} → {html_file}"
            )
            return True
        else:
            logger.warning(
                f"HWPX 텍스트 추출 실패: {hwpx_file_path.name}"
            )
            return False
    except Exception as e:
        logger.warning(
            f"HWPX 변환 실패: {hwpx_file_path.name} - {e}"
        )
        return False


def convert_hwp_to_html(hwp_file_path: Path, output_dir: Path) -> bool:
    """
    HWP/HWPX 파일을 HTML 형태로 변환합니다.
    확장자에 따라 적절한 처리 방법을 선택합니다:

    .hwpx 파일:
        → HWPX 처리 (hwp_custom.read_hwpx)

    .hwp 파일 (3단계 fallback):
        1단계: HWP5 (hwp5 라이브러리) 시도
        2단계: gethwp.read_hwp() 시도 (구형 HWP)
        3단계: HWPX fallback (잘못된 확장자 처리)

    Args:
        hwp_file_path (Path): 변환할 HWP/HWPX 파일의 경로. pathlib.Path 객체여야 합니다.
        output_dir (Path): 변환된 파일들이 저장될 출력 디렉토리. pathlib.Path 객체여야 합니다.

    Returns:
        bool: 변환 성공 시 True, 실패 시 False.
    """
    # Heavy libraries - lazy import for performance
    from hwp5.dataio import ParseError
    from hwp5.errors import InvalidHwp5FileError
    from hwp5.hwp5html import HTMLTransform
    from hwp5.xmlmodel import Hwp5File

    if not hwp_file_path.exists():
        logger.error(f"오류: HWP 파일을 찾을 수 없습니다: {hwp_file_path}")
        return False

    if not hwp_file_path.is_file():
        logger.error(f"오류: '{hwp_file_path}'은(는) 파일이 아닙니다.")
        return False

    # 파일 확장자 확인
    file_ext = hwp_file_path.suffix.lower()
    if file_ext not in [".hwp", ".hwpx"]:
        logger.error(
            f"오류: 지원하지 않는 파일 확장자: {hwp_file_path.name} (확장자: {file_ext})"
        )
        return False

    # 파일 크기 확인 (너무 큰 파일은 제한)
    file_size = hwp_file_path.stat().st_size
    max_size = 50 * 1024 * 1024  # 50MB 제한
    if file_size > max_size:
        logger.warning(
            f"HWP 파일 크기가 너무 큽니다: {file_size / 1024 / 1024:.1f}MB (최대 {max_size / 1024 / 1024}MB)"
        )
        return False

    try:
        with Timer(f"HWP 파일 변환: {hwp_file_path.name}", totalTimeChk=False):
            # 출력 디렉토리 준비 (HWP 변환 파일과 llm_response만 삭제, extracted_text.txt는 보존)
            if output_dir.exists():
                try:
                    deleted_count = 0
                    # HWP 변환 관련 파일만 선택적 삭제
                    for file_pattern in [
                        "*.xhtml",
                        "*.css",
                        "*.html",
                        "llm_response_*.json",
                    ]:
                        for file in output_dir.glob(file_pattern):
                            file.unlink()
                            deleted_count += 1

                    if deleted_count > 0:
                        logger.debug(
                            f"기존 HWP 변환 파일 {deleted_count}개 삭제, extracted_text.txt는 보존"
                        )
                    else:
                        logger.debug(f"삭제할 HWP 변환 파일 없음")
                except OSError as e:
                    logger.error(f"오류: HWP 변환 파일 삭제 실패 '{output_dir}': {e}")
                    return False

            output_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"새 출력 디렉토리 '{output_dir}'을(를) 생성했습니다.")

            # 확장자에 따른 처리 분기
            if file_ext == ".hwpx":
                # HWPX 파일 처리
                logger.debug(f"HWPX 파일 처리: {hwp_file_path.name}")
                return _convert_hwpx_file_to_html(hwp_file_path, output_dir)
            else:
                # .hwp 파일 처리: HWP5 → gethwp.read_hwp → HWPX fallback (3단계)
                logger.debug(f"HWP 파일 처리: {hwp_file_path.name}")

                # 1단계: HWP5 (OLE2) 포맷 시도
                try:
                    with closing(Hwp5File(str(hwp_file_path))) as hwp5file:
                        # 파일이 정상적으로 열리는지 확인
                        if not hasattr(hwp5file, "header"):
                            logger.warning(f"유효하지 않은 HWP5 파일 구조: {hwp_file_path}")
                        else:
                            logger.debug(f"HWP5 파일 읽기 시작: {hwp_file_path.name}")

                            # HTMLTransform 객체 생성 및 변환
                            html_transform = HTMLTransform()
                            html_transform.transform_hwp5_to_dir(hwp5file, str(output_dir))

                            # 변환 결과 확인
                            index_file = output_dir / "index.xhtml"
                            if index_file.exists() and index_file.stat().st_size > 0:
                                logger.info(f"HWP5 파일 변환 성공: {hwp_file_path.name}")
                                return True
                            else:
                                logger.warning(
                                    f"HWP5 변환 파일이 생성되지 않음: {index_file}"
                                )

                except (ParseError, InvalidHwp5FileError) as e:
                    logger.info(f"HWP5 포맷 아님 (2단계 fallback 진행): {hwp_file_path.name}")
                    logger.debug(f"HWP5 오류 상세: {e}")

                try:
                    # 2단계: gethwp.read_hwp() 시도 (구형 HWP 포맷)
                    logger.info(f"gethwp.read_hwp() 시도: {hwp_file_path.name}")
                    hwp_text_result = _convert_hwp_with_gethwp(hwp_file_path, output_dir)
                    if hwp_text_result:
                        return True

                    # 3단계: HWPX fallback 시도 (.hwp 확장자지만 실제로는 HWPX일 가능성)
                    logger.info(f"HWPX fallback 시도: {hwp_file_path.name}")
                    return _convert_hwpx_file_to_html(hwp_file_path, output_dir)
                except Exception as transform_error:
                    # XML 파싱 오류 구체적 처리
                    import xml.parsers.expat

                    if isinstance(transform_error, xml.parsers.expat.ExpatError):
                        logger.error(f"XML 파싱 오류: {hwp_file_path.name}")
                        logger.error(
                            f"  오류 위치: line {getattr(transform_error, 'lineno', '?')}, column {getattr(transform_error, 'offset', '?')}"
                        )
                        logger.error(f"  오류 메시지: {transform_error}")
                        logger.warning(
                            "  → XML 속성값에 유효하지 않은 문자가 포함되어 있습니다."
                        )
                    else:
                        logger.error(
                            f"HWP 변환 중 오류: {hwp_file_path.name} - {transform_error}"
                        )
                    return False

    except MemoryError:
        logger.error(f"HWP 파일 변환 중 메모리 부족: {hwp_file_path.name}")
        return False
    except TimeoutError:
        logger.error(f"HWP 파일 변환 시간 초과: {hwp_file_path.name}")
        return False
    except Exception as e:
        logger.error(f"HWP 파일 변환 중 예상치 못한 오류: {hwp_file_path.name} - {e}")
        logger.debug(f"오류 상세: {traceback.format_exc()}")
        return False


def convert_file_to_text(file_path: Path, file_type: str) -> str | None:
    """
    파일 타입에 따라 적절한 변환 함수를 호출하여 텍스트를 추출합니다.

    Args:
        file_path (Path): 변환할 파일 경로
        file_type (str): 파일 타입 ('pdf', 'hwp', 'hwpx')

    Returns:
        Optional[str]: 추출된 텍스트 문자열. 실패 시 None.
    """

    logger.info("convert_file_to_text")

    try:
        if file_type.lower() == "pdf":
            # PDF 파일 처리
            from tempfile import NamedTemporaryFile

            with NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as temp_file:
                temp_path = temp_file.name

            success = convert_pdf_to_text_simple(str(file_path), temp_path)
            if success:
                with open(temp_path, encoding="utf-8") as f:
                    text = f.read()
                os.unlink(temp_path)  # 임시 파일 삭제
                return text
            else:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                return None

        elif file_type.lower() == "hwpx":
            # HWPX 파일 처리
            return convert_hwpx_to_text(file_path)

        elif file_type.lower() == "hwp":
            # HWP 파일 처리 - 기존 로직 활용
            from tempfile import NamedTemporaryFile

            with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as temp_file:
                temp_path = temp_file.name

            success = convert_hwp_to_markdown(file_path, Path(temp_path))
            if success:
                with open(temp_path, encoding="utf-8") as f:
                    text = f.read()
                os.unlink(temp_path)  # 임시 파일 삭제
                return text
            else:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                return None
        else:
            logger.warning(f"지원하지 않는 파일 타입: {file_type}")
            return None

    except Exception as e:
        logger.error(f"파일 변환 중 오류: {file_path.name} ({file_type}) - {e}")
        return None


def convert_hwp_to_markdown(hwp_file_path: Path, output_path: Path) -> bool:
    """
    HWP 파일을 Markdown으로 변환합니다.
    HTML 변환을 우선 시도하고, 키릴 문자 감지 시 hwp5txt로 재시도합니다.

    변환 순서:
    1. HTML 변환 (hwp5html → MarkItDown)
       → 키릴 문자 감지 시: hwp5txt로 재변환 시도
    2. MarkItDown (fallback)
    3. 직접 텍스트 추출 (gethwp)

    Args:
        hwp_file_path: 변환할 HWP 파일 경로
        output_path: 출력할 Markdown 파일 경로

    Returns:
        bool: 변환 성공 시 True, 실패 시 False
    """

    logger.info("!!!!!!!!convert_hwp_to_markdown!!!!!!!!")
    try:
        if not hwp_file_path.exists():
            logger.error(f"HWP 파일을 찾을 수 없습니다: {hwp_file_path}")
            return False

        # .hwpx 파일인 경우 직접 처리
        if hwp_file_path.suffix.lower() == ".hwpx":
            logger.info(f"HWPX 파일 처리: {hwp_file_path.name}")
            try:
                hwpx_text = convert_hwpx_to_text(hwp_file_path)
                if hwpx_text and hwpx_text.strip():
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(hwpx_text)
                    logger.info(
                        f"HWPX 파일 텍스트 추출 성공: {hwp_file_path.name} → {output_path.name}"
                    )
                    return True
                else:
                    logger.warning(f"HWPX 파일 텍스트 추출 실패: {hwp_file_path.name}")
                    return False
            except Exception as e:
                logger.error(f"HWPX 파일 처리 중 오류: {hwp_file_path.name} - {e}")
                return False

        # .hwp 확장자지만 OLE2 서명이 아닌 경우(HWPX로 잘못 저장된 사례) 우선 처리
        try:
            if hwp_file_path.suffix.lower() == ".hwp" and not is_valid_hwp_file(
                hwp_file_path
            ):
                logger.warning(
                    f"HWP 파일이 OLE2 시그니처가 아님(실제는 HWPX일 가능성): {hwp_file_path.name}"
                )
                # HWPX 텍스트 추출 시도 후, 결과를 Markdown 파일로 저장
                hwpx_text = convert_hwpx_to_text(hwp_file_path)
                if hwpx_text and hwpx_text.strip():
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(hwpx_text)
                    logger.info(
                        f"HWPX-유사 파일 텍스트 추출 성공: {hwp_file_path.name} → {output_path.name}"
                    )
                    return True
                else:
                    logger.warning(
                        f"HWPX-유사 파일 텍스트 추출 실패: {hwp_file_path.name} — 일반 경로로 계속"
                    )
        except Exception as sig_check_error:
            logger.debug(f"HWP 서명 점검 중 오류(무시): {sig_check_error}")

        # 1차 시도: HTML 변환
        try:
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as temp_dir:
                temp_output_dir = Path(temp_dir)
                if convert_hwp_to_html(hwp_file_path, temp_output_dir):
                    html_file = temp_output_dir / "index.xhtml"
                    logger.info(f"HWP HTML path: {temp_output_dir}")
                    if html_file.exists():
                        content = read_html_file(html_file)
                        if content and len(content.strip()) > 50:
                            # 키릴 문자 인코딩 문제 검증
                            has_issue, message = has_cyrillic_encoding_issue(content)
                            if has_issue:
                                logger.warning(
                                    f"HTML 변환 시 키릴 문자 인코딩 문제 감지: {hwp_file_path.name} - {message}"
                                )
                                # hwp5txt로 재시도
                                logger.info(f"hwp5txt로 재변환 시도: {hwp_file_path.name}")
                                try:
                                    import subprocess
                                    result = subprocess.run(
                                        ['hwp5txt', str(hwp_file_path)],
                                        capture_output=True,
                                        timeout=30,
                                        check=False
                                    )

                                    if result.returncode == 0:
                                        text = result.stdout.decode('utf-8', errors='replace')

                                        if text and len(text.strip()) > 50:
                                            # 키릴 문자 재검증
                                            has_issue_retry, message_retry = has_cyrillic_encoding_issue(text)

                                            if not has_issue_retry:
                                                # 텍스트 정리
                                                from src.utils.textCleaner import clean_extracted_text
                                                cleaned_text = clean_extracted_text(text)

                                                with open(output_path, "w", encoding="utf-8") as f:
                                                    f.write(cleaned_text)

                                                logger.info(
                                                    f"hwp5txt 재변환 성공 (키릴 문제 해결): {hwp_file_path.name} → {output_path.name}"
                                                )
                                                return True
                                            else:
                                                logger.warning(
                                                    f"hwp5txt 재변환에도 키릴 문자 발견: {message_retry}, HTML 결과 사용"
                                                )
                                except Exception as retry_error:
                                    logger.warning(f"hwp5txt 재변환 실패: {retry_error}, HTML 결과 사용")

                            with open(output_path, "w", encoding="utf-8") as f:
                                f.write(content)
                            logger.info(
                                f"HWP HTML 변환 성공: {hwp_file_path.name} -> {output_path.name} ->{output_path}"
                            )
                            return True
        except Exception as e:
            logger.info(f"HTML 변환 실패: {e}")

        # 3차 시도: MarkItDown 변환 (HWP는 지원하지 않지만 시도)
        try:
            try:
                from markitdown import MarkItDown
                markitdown = MarkItDown()
            except (ImportError, AttributeError) as e:
                logger.warning(f"MarkItDown import 실패 (NumPy 호환성 문제 가능): {e}")
                raise ImportError("MarkItDown 사용 불가")
            result = markitdown.convert(str(hwp_file_path))

            if result and result.text_content:
                # 키릴 문자 인코딩 문제 검증
                has_issue, message = has_cyrillic_encoding_issue(result.text_content)
                if has_issue:
                    logger.warning(
                        f"MarkItDown 변환 시 키릴 문자 인코딩 문제 감지: {hwp_file_path.name} - {message}"
                    )
                    # 다음 방법으로 fallback
                    raise ValueError(f"Cyrillic encoding issue: {message}")

                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(result.text_content)
                logger.info(
                    f"HWP MarkItDown 변환 성공: {hwp_file_path.name} -> {output_path.name}"
                )
                return True
        except Exception as e:
            logger.info(f"MarkItDown 변환 실패: {e}")

        # 3차 시도: 직접 텍스트 추출 (대체 방법)
        try:
            text_content = extract_hwp_text_fallback(hwp_file_path)
            if text_content:
                # 키릴 문자 인코딩 문제 검증
                has_issue, message = has_cyrillic_encoding_issue(text_content)
                if has_issue:
                    logger.error(
                        f"직접 텍스트 추출 시 키릴 문자 인코딩 문제 감지: {hwp_file_path.name} - {message}"
                    )
                    # 문제가 있어도 저장은 하되, 에러 로그 남김

                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(text_content)
                logger.info(
                    f"HWP 직접 텍스트 추출 성공: {hwp_file_path.name} -> {output_path.name}"
                )
                return True
        except Exception as e:
            logger.warning(f"HWP 직접 텍스트 추출 실패: {e}")

        return False

    except Exception as e:
        logger.error(f"HWP 파일 변환 중 오류: {hwp_file_path} - {e}")
        return False


def convert_hwpx_to_text(hwpx_file_path: Path) -> str | None:
    """
    HWPX 파일에서 텍스트를 추출합니다.
    gethwp 라이브러리를 사용하여 HWPX 파일의 텍스트 내용을 추출합니다.

    Args:
        hwpx_file_path (Path): 변환할 HWPX 파일의 경로.

    Returns:
        Optional[str]: 추출된 텍스트 문자열. 실패 시 None.
    """
    if not isinstance(hwpx_file_path, Path):
        logger.error(
            f"오류: 'hwpx_file_path'는 pathlib.Path 객체여야 합니다. 현재 타입: {type(hwpx_file_path)}"
        )
        return None

    # 제외 파일 체크 (첨부문서, 신청서 등)
    if should_exclude_file(hwpx_file_path):
        logger.info(f"HWPX 파일 제외됨: {hwpx_file_path.name}")
        return None

    if not hwpx_file_path.exists() or not hwpx_file_path.is_file():
        logger.error(
            f"오류: HWPX 파일을 찾을 수 없거나 파일이 아닙니다: {hwpx_file_path}"
        )
        return None

    # 파일 크기 확인 (너무 큰 파일은 제한)
    file_size = hwpx_file_path.stat().st_size
    max_size = 30 * 1024 * 1024  # 30MB 제한
    if file_size > max_size:
        logger.warning(
            f"HWPX 파일 크기가 너무 큽니다: {file_size / 1024 / 1024:.1f}MB (최대 {max_size / 1024 / 1024}MB)"
        )
        return None

    logger.debug(f"HWPX 파일 '{hwpx_file_path.name}'의 텍스트 추출을 시작합니다.")

    try:
        with Timer(f"HWPX 파일 텍스트 추출: {hwpx_file_path.name}", totalTimeChk=False):
            # HWP 라이브러리 지연 로딩
            hwp_libs = get_hwp_libraries()
            gethwp = hwp_libs["gethwp"]

            # gethwp로 텍스트 추출 시도
            extracted_text = gethwp.read_hwpx(str(hwpx_file_path))

            if isinstance(extracted_text, str) and extracted_text.strip():
                # 텍스트 정리
                cleaned_text = extracted_text.strip()
                # 길이 제한 제거 - 모든 추출 텍스트 허용
                if len(cleaned_text) == 0:
                    logger.warning(
                        f"HWPX 파일 '{hwpx_file_path.name}'에서 추출된 텍스트가 비어있습니다"
                    )
                    return None

                logger.debug(f"HWPX 텍스트 추출 완료: {len(cleaned_text)}자")

                # ProcessedDataManager가 이제 텍스트 저장을 처리합니다

                logger.info(
                    f"HWPX 파일 '{hwpx_file_path.name}'에서 텍스트 추출 성공 ({len(cleaned_text)}자)"
                )
                return cleaned_text
            else:
                logger.warning(
                    f"HWPX 파일 '{hwpx_file_path.name}'에서 유효한 텍스트를 추출할 수 없습니다."
                )
                return None

    except MemoryError:
        logger.error(f"HWPX 파일 텍스트 추출 중 메모리 부족: {hwpx_file_path.name}")
        return None
    except Exception as e:
        logger.error(f"HWPX 파일 '{hwpx_file_path.name}' 텍스트 추출 중 오류 발생: {e}")
        logger.debug(f"HWPX 텍스트 추출 오류 상세: {traceback.format_exc()}")
        return None


def clean_hwp_extracted_text(text: str) -> str:
    """
    HWP에서 추출된 텍스트의 깨진 문자를 정리합니다.

    Args:
        text: 원본 HWP 추출 텍스트

    Returns:
        정리된 텍스트
    """
    if not text:
        return ""

    # 1. 제어 문자 및 비표준 유니코드 문자 제거
    control_chars = re.compile(r"[\u0000-\u001F\u007F-\u009F\uFFFE\uFFFF]")
    text = control_chars.sub("", text)

    # 2. 특정 패턴의 깨진 문자 제거
    corrupted_patterns = [
        r"[\u0002\u0003\u0004\u0005\u0006\u0007\u0008\u0009\u000A\u000B\u000C\u000D\u000E\u000F]+",
        r"[\u4E00-\u9FFF]{1,3}(?=\u0000)",  # 한자 뒤에 null 문자가 오는 패턴
        r"\u0000+",  # 연속된 null 문자
        r"[\u0010-\u001F]+",  # 추가 제어 문자
    ]

    for pattern in corrupted_patterns:
        text = re.sub(pattern, "", text)

    # 3. HWP 특수 문자 패턴 정리
    hwp_special_chars = [
        r"[氠瑢汤捯捤獥]+",  # HWP 테이블 관련 특수 문자
        r"[漠杳]+",  # 기타 HWP 특수 문자
    ]

    for pattern in hwp_special_chars:
        text = re.sub(pattern, "", text)

    # 4. 연속된 공백 및 줄바꿈 정리
    text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)  # 3개 이상의 연속 줄바꿈을 2개로
    text = re.sub(r"[ \t]+", " ", text)  # 연속된 공백을 하나로

    # 5. 빈 줄 과다 제거
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def has_cyrillic_encoding_issue(text: str, threshold: float = 0.01) -> tuple[bool, str]:
    """
    텍스트에 키릴 문자 인코딩 문제가 있는지 검사합니다.

    Args:
        text: 검사할 텍스트
        threshold: 키릴 문자 비율 임계값 (기본 1%)

    Returns:
        tuple[bool, str]: (문제 발견 여부, 상세 메시지)
    """
    if not text or len(text) == 0:
        return False, "Empty text"

    # 키릴 문자 (러시아어) 패턴
    cyrillic_pattern = r'[А-Яа-яЁё]'
    cyrillic_matches = re.findall(cyrillic_pattern, text)
    cyrillic_count = len(cyrillic_matches)

    total_chars = len(text)
    cyrillic_ratio = cyrillic_count / total_chars if total_chars > 0 else 0

    if cyrillic_ratio > threshold:
        message = f"Cyrillic encoding issue detected: {cyrillic_count}/{total_chars} chars ({cyrillic_ratio*100:.2f}%)"
        return True, message

    return False, "OK"


def is_valid_hwp_file(hwp_file_path: Path) -> bool:
    """
    HWP 파일의 유효성을 간단히 검사합니다.
    """
    try:
        if not hwp_file_path.exists() or hwp_file_path.stat().st_size == 0:
            return False

        # HWP 파일의 시작 바이트 확인 (OLE2 구조체)
        with open(hwp_file_path, "rb") as f:
            header = f.read(8)
            # OLE2 signature: D0CF11E0A1B11AE1
            if len(header) < 8 or header[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                logger.warning(f"HWP 파일 시그니처 불일치: {hwp_file_path.name}")
                return False

        return True

    except Exception as e:
        logger.warning(f"HWP 파일 유효성 검사 실패: {hwp_file_path.name} - {e}")
        return False


def process_hwp_with_fallback(
    hwp_file_path: Path, temp_output_dir: Path = None
) -> str | None:
    """HWP 파일 처리 - fallback 포함 (announcementClassifier 및 processManager 호환성)"""
    # temp_output_dir 인수는 호환성을 위해 받지만 현재 구현에서는 사용하지 않음
    return extract_hwp_text_fallback(hwp_file_path)


def extract_hwp_text_fallback(hwp_file_path: Path) -> str | None:
    """
    HWP 파일에서 텍스트 추출을 위한 대체 방법.
    주 변환 방법이 실패한 경우 사용됩니다.
    """

    # 중복 호출 방지: convert_hwp_to_markdown()를 호출하지 않고 직접 텍스트 추출
    logger.info(f"Fallback HWP 텍스트 추출 시작: {hwp_file_path.name}")

    # HWPX 파일인 경우 직접 처리
    if hwp_file_path.suffix.lower() == ".hwpx":
        try:
            return convert_hwpx_to_text(hwp_file_path)
        except Exception as e:
            logger.error(f"Fallback HWPX 텍스트 추출 실패: {hwp_file_path.name} - {e}")
            return None

    # 2025.09.03  기존 소스. 현재  extracted_text = gethwp.read_hwp(str(hwp_file_path))
    # 이걸로만 하고 있다. 이 부분은 failback이다.
    try:
        # 파일 유효성 사전 검사
        if not is_valid_hwp_file(hwp_file_path):
            logger.warning(
                f"HWP 파일 유효성 검사 실패, 처리 건너뜀: {hwp_file_path.name}"
            )
            return None

        # Heavy library - lazy import for performance
        import gethwp

        # gethwp로 HWP 파일 텍스트 추출 시도
        if hwp_file_path.suffix.lower() == ".hwp":
            logger.info(f"HWP 파일 대체 텍스트 추출 시도: {hwp_file_path.name}")
            extracted_text = gethwp.read_hwp(str(hwp_file_path))

            if isinstance(extracted_text, str) and extracted_text.strip():
                # 깨진 문자 정리 적용
                cleaned_text = clean_hwp_extracted_text(extracted_text)
                if len(cleaned_text) >= 10:
                    logger.info(
                        f"HWP 파일 대체 방법으로 텍스트 추출 성공: {hwp_file_path.name} ({len(cleaned_text)}자)"
                    )
                    return cleaned_text

        # 다른 라이브러리 시도 가능 위치
        logger.warning(f"HWP 파일 대체 텍스트 추출 실패: {hwp_file_path.name}")
        return None

    except Exception as e:
        logger.error(f"HWP 파일 대체 텍스트 추출 중 오류: {hwp_file_path.name} - {e}")
        return None
