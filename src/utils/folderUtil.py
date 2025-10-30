"""
폴더 관련 유틸리티 함수들
"""

import json
import re
import shutil
from pathlib import Path

from src.config.logConfig import setup_logging

logger = setup_logging(__name__)


def normalize_site_code(site_code: str) -> str:
    """
    사이트 코드를 표준화된 형태로 정규화합니다.

    Args:
        site_code: 원본 사이트 코드 (예: btp_enhanced, kibo_advanced)

    Returns:
        정규화된 사이트 코드 (예: btp, kibo)
    """
    try:
        if not site_code or not isinstance(site_code, str):
            return "unknown"

        normalized = site_code.strip().lower()

        # 특수문자 정리 (접미사 제거 전에 먼저 수행)
        normalized = normalized.replace("-", "_")  # 하이픈을 언더스코어로 통일

        # 제거할 접미사들 정의 (우선순위 순서 - 긴 것부터)
        suffixes_to_remove = [
            "_enhanced",
            "_advanced",
            "_improved",
            "_updated",
            "_premium",
            "_latest",
            "_final",
            "_plus",
            "_pro",
            "_new",
            "_v3",
            "_v2",
        ]

        # 타임스탬프 패턴 제거 (YYYYMMDD_HHMMSS 형태)
        import re

        timestamp_pattern = r"_\d{8}_\d{6}$"
        if re.search(timestamp_pattern, normalized):
            normalized = re.sub(timestamp_pattern, "", normalized)
            logger.debug(f"타임스탬프 제거: '{site_code}' -> '{normalized}'")

        # 접미사 제거 (여러 번 적용하여 복합 접미사 처리)
        original_normalized = normalized
        max_iterations = 3  # 무한 루프 방지

        for iteration in range(max_iterations):
            old_normalized = normalized
            for suffix in suffixes_to_remove:
                if normalized.endswith(suffix):
                    before_removal = normalized
                    normalized = normalized[: -len(suffix)]
                    logger.debug(
                        f"사이트 코드 정규화 (반복 {iteration+1}): '{before_removal}' -> '{normalized}' (제거된 접미사: '{suffix}')"
                    )
                    break

            # 더 이상 변경이 없으면 중단
            if normalized == old_normalized:
                break

        # 연속된 언더스코어 제거
        while "__" in normalized:
            normalized = normalized.replace("__", "_")

        # 앞뒤 언더스코어 제거
        normalized = normalized.strip("_")

        # 빈 문자열이 된 경우나 접미사만 있었던 경우 기본값 사용
        if not normalized or normalized in [
            "enhanced",
            "advanced",
            "improved",
            "updated",
            "premium",
            "latest",
            "final",
            "plus",
            "pro",
            "new",
            "v2",
            "v3",
        ]:
            normalized = "unknown"
            logger.warning(
                f"사이트 코드 정규화 후 빈 문자열이거나 접미사만 존재: '{site_code}' -> '{normalized}'"
            )

        # 변경사항이 있을 때만 로깅
        if normalized != original_normalized:
            logger.info(f"사이트 코드 정규화: '{site_code}' -> '{normalized}'")

        return normalized

    except Exception as e:
        logger.error(f"사이트 코드 정규화 중 오류: {site_code} - {str(e)}")
        return site_code.lower() if isinstance(site_code, str) else "unknown"


def determine_folder_type(folder_name: str) -> tuple[str, str]:
    """
    폴더명을 분석하여 타입을 판단합니다.

    Args:
        folder_name: 폴더명

    Returns:
        Tuple[folder_type, display_name]
        - folder_type: 'TITLE' 또는 'POST_NO'
        - display_name: 표시할 이름 (제목 또는 폴더명)
    """
    try:
        # 게시물 번호 패턴들
        post_number_patterns = [
            r"^\d+$",  # 순수 숫자 (예: 12345)
            r"^[A-Z]+_\d+$",  # 코드_숫자 (예: PBLN_000000000110001)
            r"^\d{4}-\d+$",  # 년도-번호 (예: 2024-001)
            r"^NO\d+$",  # NO+숫자 (예: NO12345)
            r"^[A-Z]{2,4}\d{6,}$",  # 접두사+긴숫자 (예: BIZ20240101)
            r"^\d{8,}$",  # 8자리 이상 숫자 (예: 20240315001)
        ]

        # 패턴 매칭 검사
        for pattern in post_number_patterns:
            if re.match(pattern, folder_name.strip()):
                logger.info(f"게시물 번호로 판단됨: {folder_name} (패턴: {pattern})")
                return "POST_NO", folder_name

        # 한글이 포함되어 있고 충분히 길면 제목으로 판단
        if len(folder_name) > 10 and any(
            "\u3131" <= char <= "\u3163" or "\uac00" <= char <= "\ud7a3"
            for char in folder_name
        ):
            logger.info(f"공고제목으로 판단됨: {folder_name}")
            return "TITLE", folder_name

        # 영문+숫자 조합이지만 제목처럼 보이는 경우 (공백 포함, 특수문자 포함 등)
        if (
            any(char in folder_name for char in [" ", "-", "_", "(", ")", "[", "]"])
            and len(folder_name) > 15
        ):
            logger.info(f"영문 제목으로 판단됨: {folder_name}")
            return "TITLE", folder_name

        # 기본값: 짧거나 애매한 경우 게시물 번호로 간주
        if len(folder_name) <= 10:
            logger.info(f"짧은 문자열로 게시물 번호로 판단됨: {folder_name}")
            return "POST_NO", folder_name

        # 그 외의 경우 제목으로 처리
        logger.info(f"기본값으로 공고제목으로 판단됨: {folder_name}")
        return "TITLE", folder_name

    except Exception as e:
        import traceback

        logger.error(
            f"폴더 타입 판단 중 오류: {folder_name} - {str(e)}\n{traceback.format_exc()}"
        )
        # 오류 발생 시 안전하게 제목으로 처리
        return "TITLE", folder_name


def clean_announcement_title(title: str) -> str:
    """
    공고제목에서 불필요한 정보를 제거하여 깔끔하게 정리합니다.

    Args:
        title: 원본 공고제목

    Returns:
        정리된 공고제목
    """
    try:
        import re

        cleaned_title = title.strip()
        original_title = cleaned_title

        # 1. 날짜 및 시간 정보 패턴들 제거
        datetime_patterns = [
            # 기존 복잡한 날짜 패턴들
            r"\(~\d{1,2}\.\d{1,2}\.\([가-힣]\)\s*\d{4}\)",  # (~1.23.(목) 1800)
            r"\(~\d{1,2}\.\d{1,2}\.\s*\d{4}\)",  # (~1.23. 1800)
            r"\(~\d{4}-\d{1,2}-\d{1,2}\s*\d{4}\)",  # (~2024-01-23 1800)
            r"\(~\d{4}\.\d{1,2}\.\d{1,2}\s*\d{4}\)",  # (~2024.01.23 1800)
            r"\(\d{4}\.\d{1,2}\.\d{1,2}~\d{4}\.\d{1,2}\.\d{1,2}\)",  # (2024.01.01~2024.01.31)
            r"\(\d{4}-\d{1,2}-\d{1,2}~\d{4}-\d{1,2}-\d{1,2}\)",  # (2024-01-01~2024-01-31)
            # 추가 날짜/시간 패턴들
            r"\(\d{4}년\s*\d{1,2}월\s*\d{1,2}일\)",  # (2024년 1월 23일)
            r"\(\d{1,2}/\d{1,2}\)",  # (1/23)
            r"\(\d{1,2}\.\d{1,2}\)",  # (01.23)
            r"\(\d{1,2}:\d{2}\)",  # (14:00)
            r"\(\d{4}\)",  # (1400)
            r"\(오전\s*\d{1,2}시\)",  # (오전 9시)
            r"\(오후\s*\d{1,2}시\)",  # (오후 2시)
            r"\([가-힣]요일\)",  # (월요일)
            r"\([가-힣]\)",  # (월)
        ]

        for pattern in datetime_patterns:
            cleaned_title = re.sub(pattern, "", cleaned_title)

        # 2. 접수/처리 관련 패턴 제거
        process_patterns = [
            r"\(온라인\s*접수\)",  # (온라인 접수)
            r"\(방문\s*접수\)",  # (방문 접수)
            r"\(우편\s*접수\)",  # (우편 접수)
            r"\(마감\)",  # (마감)
            r"\(연장\)",  # (연장)
            r"\(조기\s*마감\)",  # (조기마감)
            r"\(신청\)",  # (신청)
            r"\(접수중\)",  # (접수중)
            r"\(모집중\)",  # (모집중)
            r"\(모집\)",  # (모집)
        ]

        for pattern in process_patterns:
            cleaned_title = re.sub(pattern, "", cleaned_title)

        # 3. 차수/버전 관련 패턴 제거
        version_patterns = [
            r"\(\d+차\)",  # (1차), (2차)
            r"\(\d+차\s*변경\)",  # (2차변경)
            r"\(\d+차\s*개정\)",  # (6차 개정)
            r"\(수정\)",  # (수정)
            r"\(재공고\)",  # (재공고)
            r"\(변경\s*공고\)",  # (변경공고)
            r"\(추가\)",  # (추가)
            r"\(보완\)",  # (보완)
            r"\(개정\)",  # (개정)
        ]

        for pattern in version_patterns:
            cleaned_title = re.sub(pattern, "", cleaned_title)

        # 4. 상태/우선순위 패턴 제거
        status_patterns = [
            r"\(긴급\)",  # (긴급)
            r"\(중요\)",  # (중요)
            r"\(필독\)",  # (필독)
            r"\(신규\)",  # (신규)
            r"\(업데이트\)",  # (업데이트)
            r"\(최신\)",  # (최신)
            r"\(확정\)",  # (확정)
            r"\(예정\)",  # (예정)
            r"\(잠정\)",  # (잠정)
        ]

        for pattern in status_patterns:
            cleaned_title = re.sub(pattern, "", cleaned_title)

        # 5. 파일/형식 관련 패턴 제거
        file_patterns = [
            r"\(PDF\)",  # (PDF)
            r"\(첨부\s*파일\)",  # (첨부파일)
            r"\(파일\s*다운로드\)",  # (파일다운로드)
            r"\[공고\]",  # [공고]
            r"\[안내\]",  # [안내]
            r"\[알림\]",  # [알림]
            r"\[공지\]",  # [공지]
            r"\[모집\]",  # [모집]
        ]

        for pattern in file_patterns:
            cleaned_title = re.sub(pattern, "", cleaned_title)

        # 6. 번호 패턴 제거
        number_patterns = [
            r"^\d{3,}_",  # 시작 부분의 "062_"
            r"^\d{3,}\.\s*",  # 시작 부분의 "001. "
            r"^No\.\s*\d+\s*",  # 시작 부분의 "No.123 "
            r"^#\d+\s*",  # 시작 부분의 "#456 "
            r"\(조회수[:：]\s*\d+\)",  # (조회수: 123)
            r"\(다운로드[:：]\s*\d+\)",  # (다운로드: 45)
        ]

        for pattern in number_patterns:
            cleaned_title = re.sub(pattern, "", cleaned_title)

        # 7. 괄호 내 짧은 내용 제거 (3자 이하)
        cleaned_title = re.sub(r"\([^)]{1,3}\)", "", cleaned_title)
        cleaned_title = re.sub(r"\[[^\]]{1,3}\]", "", cleaned_title)

        # 8. 연속된 특수문자 정리
        cleaned_title = re.sub(
            r"[-_]{2,}", "-", cleaned_title
        )  # 연속된 하이픈/언더스코어
        cleaned_title = re.sub(r"[.]{2,}", "", cleaned_title)  # 연속된 마침표
        cleaned_title = re.sub(r"\s+", " ", cleaned_title)  # 연속된 공백

        # 9. 빈 괄호/대괄호 제거
        cleaned_title = re.sub(r"\(\s*\)", "", cleaned_title)  # 빈 괄호
        cleaned_title = re.sub(r"\[\s*\]", "", cleaned_title)  # 빈 대괄호

        # 10. 앞뒤 불필요한 문자 제거
        cleaned_title = cleaned_title.strip()
        cleaned_title = cleaned_title.strip(" -_.,[](){}")
        cleaned_title = cleaned_title.strip()

        # 11. 최종 정리: 의미없는 접두사 제거
        meaningless_prefixes = [
            r"^공고\s*[:：]\s*",  # "공고: "
            r"^안내\s*[:：]\s*",  # "안내: "
            r"^알림\s*[:：]\s*",  # "알림: "
            r"^모집\s*[:：]\s*",  # "모집: "
        ]

        for pattern in meaningless_prefixes:
            cleaned_title = re.sub(pattern, "", cleaned_title)

        # 최종 공백 정리
        cleaned_title = cleaned_title.strip()

        # 로깅: 변경사항이 있을 때만
        if cleaned_title != original_title:
            logger.info(f"공고제목 정리: '{original_title}' → '{cleaned_title}'")

        # 빈 문자열이 된 경우 원본 반환
        if not cleaned_title.strip():
            logger.warning(
                f"공고제목 정리 후 빈 문자열이 됨, 원본 사용: '{original_title}'"
            )
            return original_title

        return cleaned_title

    except Exception as e:
        logger.error(f"공고제목 정리 중 오류: {title} - {str(e)}")
        return title  # 오류 시 원본 반환


def _extract_title_from_html(html_file: Path) -> str:
    """
    HTML 파일에서 제목을 추출합니다.

    Args:
        html_file: HTML 파일 경로

    Returns:
        추출된 제목 또는 빈 문자열
    """
    try:
        if not html_file.exists():
            return ""

        content = html_file.read_text(encoding="utf-8")

        # BeautifulSoup을 사용한 HTML 파싱
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(content, "html.parser")

            # 1. <h1> 태그에서 제목 추출 (최우선)
            h1_tag = soup.find("h1")
            if h1_tag and h1_tag.get_text(strip=True):
                title = h1_tag.get_text(strip=True)
                if len(title) >= 10:  # 최소 길이 검증
                    return title

            # 2. <title> 태그에서 제목 추출
            title_tag = soup.find("title")
            if title_tag and title_tag.get_text(strip=True):
                title = title_tag.get_text(strip=True)
                if len(title) >= 10:
                    return title

            # 3. 메타 태그에서 제목 추출
            meta_title = soup.find("meta", {"name": "title"})
            if meta_title and meta_title.get("content"):
                title = meta_title["content"].strip()
                if len(title) >= 10:
                    return title

            # 4. Open Graph 제목 추출
            og_title = soup.find("meta", {"property": "og:title"})
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()
                if len(title) >= 10:
                    return title

            # 5. <h2> 태그에서 제목 추출 (대안)
            h2_tag = soup.find("h2")
            if h2_tag and h2_tag.get_text(strip=True):
                title = h2_tag.get_text(strip=True)
                if len(title) >= 10:
                    return title

        except ImportError:
            logger.warning(
                "BeautifulSoup 라이브러리가 없습니다. 정규식으로 HTML 파싱을 시도합니다."
            )

            # BeautifulSoup 없이 정규식으로 파싱
            # 1. <h1> 태그
            h1_match = re.search(
                r"<h1[^>]*>(.*?)</h1>", content, re.IGNORECASE | re.DOTALL
            )
            if h1_match:
                title = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
                if len(title) >= 10:
                    return title

            # 2. <title> 태그
            title_match = re.search(
                r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL
            )
            if title_match:
                title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
                if len(title) >= 10:
                    return title

            # 3. <h2> 태그
            h2_match = re.search(
                r"<h2[^>]*>(.*?)</h2>", content, re.IGNORECASE | re.DOTALL
            )
            if h2_match:
                title = re.sub(r"<[^>]+>", "", h2_match.group(1)).strip()
                if len(title) >= 10:
                    return title

        return ""

    except Exception as e:
        logger.error(f"HTML 파일 제목 추출 중 오류: {html_file} - {str(e)}")
        return ""


def _extract_title_from_md(md_file: Path) -> str:
    """
    MD 파일에서 제목을 추출합니다.

    Args:
        md_file: MD 파일 경로

    Returns:
        추출된 제목 또는 빈 문자열
    """
    try:
        if not md_file.exists():
            return ""

        content = md_file.read_text(encoding="utf-8")

        # 1. 첫 번째 # 헤더 찾기 (최우선)
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
            if len(title) >= 10:
                return title

        # 2. 두 번째 줄의 === 언더라인 제목 찾기
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.strip().startswith("=") and i > 0:
                prev_line = lines[i - 1].strip()
                if prev_line and len(prev_line) >= 10:
                    return prev_line

        # 3. ### 헤더 찾기 (대안)
        title_match = re.search(r"^###\s+(.+)$", content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
            if len(title) >= 10:
                return title

        return ""

    except Exception as e:
        logger.error(f"MD 파일 제목 추출 중 오류: {md_file} - {str(e)}")
        return ""


def _extract_title_from_json(json_file: Path) -> str:
    """
    JSON 파일에서 제목을 추출합니다.

    Args:
        json_file: JSON 파일 경로

    Returns:
        추출된 제목 또는 빈 문자열
    """
    try:
        if not json_file.exists():
            return ""

        import json

        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            # 일반적인 제목 필드들 확인 (우선순위 순서)
            title_fields = [
                "SBVT_TITLE",
                "title",
                "TITLE",
                "제목",
                "name",
                "subject",
                "announcement_title",
                "supportBusinessTitle",
                "announcementTitle",
                "business_title",
                "project_title",
                "program_title",
            ]

            for field in title_fields:
                if field in data and data[field]:
                    title = str(data[field]).strip()
                    if len(title) >= 10:
                        return title

        return ""

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"JSON 파일 제목 추출 중 오류: {json_file} - {str(e)}")
        return ""


def _extract_title_from_pdf(pdf_file: Path) -> str:
    """
    PDF 파일에서 제목을 추출합니다.

    Args:
        pdf_file: PDF 파일 경로

    Returns:
        추출된 제목 또는 빈 문자열
    """
    try:
        if not pdf_file.exists():
            return ""

        try:
            import PyPDF2

            with open(pdf_file, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)

                # 1. PDF 메타데이터에서 제목 추출
                if pdf_reader.metadata and pdf_reader.metadata.get("/Title"):
                    title = pdf_reader.metadata["/Title"].strip()
                    if len(title) >= 10:
                        return title

                # 2. 첫 페이지 텍스트에서 제목 추출
                if len(pdf_reader.pages) > 0:
                    first_page = pdf_reader.pages[0]
                    text = first_page.extract_text()

                    # 첫 번째 줄에서 제목 추출
                    lines = text.split("\n")
                    for line in lines[:5]:  # 처음 5줄만 확인
                        line = line.strip()
                        if line and len(line) >= 10:
                            # 공고, 사업, 지원 등의 키워드가 포함된 경우 제목으로 판단
                            if any(
                                keyword in line
                                for keyword in [
                                    "공고",
                                    "사업",
                                    "지원",
                                    "모집",
                                    "과제",
                                    "프로그램",
                                ]
                            ):
                                return line

                    # 키워드가 없는 경우 가장 긴 줄을 제목으로 추정
                    longest_line = max(lines[:5], key=len, default="").strip()
                    if len(longest_line) >= 10:
                        return longest_line

        except ImportError:
            logger.warning("PyPDF2 라이브러리가 없습니다. pdfminer로 시도합니다.")

            try:
                from pdfminer.high_level import extract_text

                text = extract_text(pdf_file)

                lines = text.split("\n")
                for line in lines[:5]:  # 처음 5줄만 확인
                    line = line.strip()
                    if line and len(line) >= 10:
                        if any(
                            keyword in line
                            for keyword in [
                                "공고",
                                "사업",
                                "지원",
                                "모집",
                                "과제",
                                "프로그램",
                            ]
                        ):
                            return line

                longest_line = max(lines[:5], key=len, default="").strip()
                if len(longest_line) >= 10:
                    return longest_line

            except ImportError:
                logger.warning(
                    "pdfminer 라이브러리도 없습니다. PDF 제목 추출을 건너뜁니다."
                )

        return ""

    except Exception as e:
        logger.error(f"PDF 파일 제목 추출 중 오류: {pdf_file} - {str(e)}")
        return ""


def _extract_title_from_hwp(hwp_file: Path) -> str:
    """
    HWP 파일에서 제목을 추출합니다.

    Args:
        hwp_file: HWP 파일 경로

    Returns:
        추출된 제목 또는 빈 문자열
    """
    try:
        if not hwp_file.exists():
            return ""

        try:
            from pyhwp.hwp5 import storage

            # HWP 파일 읽기
            with storage.open(hwp_file) as hwp:
                # 문서 텍스트 추출
                text_lines = []
                for record in hwp.bodytext.section(0):
                    if hasattr(record, "text"):
                        text_lines.append(record.text)

                # 첫 번째 줄에서 제목 추출
                if text_lines:
                    first_line = text_lines[0].strip()
                    if len(first_line) >= 10:
                        return first_line

        except ImportError:
            logger.warning("pyhwp 라이브러리가 없습니다. HWP 제목 추출을 건너뜁니다.")

        return ""

    except Exception as e:
        logger.error(f"HWP 파일 제목 추출 중 오류: {hwp_file} - {str(e)}")
        return ""


def _extract_title_from_hwpx(hwpx_file: Path) -> str:
    """
    HWPX 파일에서 제목을 추출합니다.

    Args:
        hwpx_file: HWPX 파일 경로

    Returns:
        추출된 제목 또는 빈 문자열
    """
    try:
        if not hwpx_file.exists():
            return ""

        try:
            import xml.etree.ElementTree as ET
            import zipfile

            # HWPX는 ZIP 파일 형태
            with zipfile.ZipFile(hwpx_file, "r") as zip_file:
                # contents.xml 파일에서 텍스트 추출
                if "contents.xml" in zip_file.namelist():
                    with zip_file.open("contents.xml") as xml_file:
                        root = ET.parse(xml_file).getroot()

                        # 첫 번째 텍스트 노드에서 제목 추출
                        for text_elem in root.iter():
                            if text_elem.text and text_elem.text.strip():
                                text = text_elem.text.strip()
                                if len(text) >= 10:
                                    return text

        except Exception as e:
            logger.warning(f"HWPX XML 파싱 중 오류: {e}")

        return ""

    except Exception as e:
        logger.error(f"HWPX 파일 제목 추출 중 오류: {hwpx_file} - {str(e)}")
        return ""


def extract_title_from_files(files_dict: dict) -> str:
    """
    파일들에서 실제 공고제목을 추출합니다.
    폴더명이 게시물 번호인 경우 파일 내용에서 제목을 찾습니다.

    Args:
        files_dict: 파일 타입별 파일 목록

    Returns:
        추출된 제목 또는 빈 문자열
    """
    try:
        # 1. HTML 파일에서 제목 추출 시도 (최우선)
        if "html" in files_dict and files_dict["html"]:
            title = _extract_title_from_html(files_dict["html"][0])
            if title:
                logger.info(f"HTML 파일에서 제목 추출: {title}")
                return title

        # 2. MD 파일에서 제목 추출 시도
        if "md" in files_dict and files_dict["md"]:
            title = _extract_title_from_md(files_dict["md"][0])
            if title:
                logger.info(f"MD 파일에서 제목 추출: {title}")
                return title

        # 3. JSON 파일에서 제목 추출 시도
        if "json" in files_dict and files_dict["json"]:
            title = _extract_title_from_json(files_dict["json"][0])
            if title:
                logger.info(f"JSON 파일에서 제목 추출: {title}")
                return title

        # 4. PDF 파일에서 제목 추출 시도
        if "pdf" in files_dict and files_dict["pdf"]:
            title = _extract_title_from_pdf(files_dict["pdf"][0])
            if title:
                logger.info(f"PDF 파일에서 제목 추출: {title}")
                return title

        # 5. HWP 파일에서 제목 추출 시도
        if "hwp" in files_dict and files_dict["hwp"]:
            title = _extract_title_from_hwp(files_dict["hwp"][0])
            if title:
                logger.info(f"HWP 파일에서 제목 추출: {title}")
                return title

        # 6. HWPX 파일에서 제목 추출 시도
        if "hwpx" in files_dict and files_dict["hwpx"]:
            title = _extract_title_from_hwpx(files_dict["hwpx"][0])
            if title:
                logger.info(f"HWPX 파일에서 제목 추출: {title}")
                return title

        logger.warning("파일에서 제목을 추출할 수 없습니다")
        return ""

    except Exception as e:
        logger.error(f"제목 추출 중 오류: {e}")
        return ""


def move_folder_realtime(
    source_folder: Path, is_success: bool, base_data_dir: Path = None
) -> bool:
    """
    처리 결과에 따라 폴더를 실시간으로 성공/실패 디렉토리로 이동시킵니다.

    Args:
        source_folder: 이동할 원본 폴더 경로
        is_success: 처리 성공 여부 (True: 성공, False: 실패)
        base_data_dir: 기본 데이터 디렉토리 (None이면 source_folder의 부모 디렉토리 사용)

    Returns:
        이동 성공 여부
    """
    try:
        if not source_folder.exists():
            logger.warning(f"원본 폴더가 존재하지 않습니다: {source_folder}")
            return False

        # 기본 디렉토리 설정 (data 폴더와 동일한 깊이에 생성)
        if base_data_dir is None:
            # data 폴더의 부모 디렉토리를 기준으로 설정
            # source_folder: /path/to/data/{site_code}/{folder_name}
            # source_folder.parent: /path/to/data/{site_code}
            # source_folder.parent.parent: /path/to/data
            # source_folder.parent.parent.parent: /path/to (data와 동일 깊이)
            base_data_dir = source_folder.parent.parent.parent

        # 목적지 디렉토리 설정
        if is_success:
            dest_base_dir = base_data_dir / "data_result_success"
            status_text = "성공"
        else:
            dest_base_dir = base_data_dir / "data_result_failure"
            status_text = "실패"

        # 목적지 디렉토리 생성
        dest_base_dir.mkdir(parents=True, exist_ok=True)

        # 사이트 코드별 하위 디렉토리 구조 유지 (정규화된 사이트 코드 사용)
        original_site_code = source_folder.parent.name
        site_code = normalize_site_code(original_site_code)
        dest_site_dir = dest_base_dir / site_code
        dest_site_dir.mkdir(parents=True, exist_ok=True)

        # 최종 목적지 경로
        dest_folder = dest_site_dir / source_folder.name

        # 이미 존재하는 경우 중복 처리
        if dest_folder.exists():
            counter = 1
            original_name = source_folder.name
            while dest_folder.exists():
                dest_folder = dest_site_dir / f"{original_name}_{counter}"
                counter += 1

        # 폴더 이동 실행
        shutil.move(str(source_folder), str(dest_folder))

        logger.info(f"폴더 이동 {status_text}: {source_folder} -> {dest_folder}")
        logger.debug(
            f"경로 상세: base_data_dir={base_data_dir}, dest_base_dir={dest_base_dir}, original_site_code={original_site_code}, normalized_site_code={site_code}"
        )
        return True

    except Exception as e:
        logger.error(f"폴더 이동 실패: {source_folder} -> {e}")
        return False


def move_folder_on_processing_complete(
    source_folder: Path, is_success: bool, site_code: str = None
) -> bool:
    """
    처리 완료 시점에 폴더를 이동시킵니다. (기존 main.py 로직과 호환)

    Args:
        source_folder: 이동할 원본 폴더 경로
        is_success: 처리 성공 여부
        site_code: 사이트 코드 (None이면 자동 추출)

    Returns:
        이동 성공 여부
    """
    try:
        if site_code is None:
            site_code = source_folder.parent.name

        return move_folder_realtime(source_folder, is_success)

    except Exception as e:
        logger.error(f"처리 완료 시 폴더 이동 실패: {e}")
        return False


def create_processing_marker(folder_path: Path) -> bool:
    """
    처리 중임을 표시하는 마커 파일을 생성합니다.
    처리 시작 시간을 기록합니다.

    Args:
        folder_path: 처리 중인 폴더 경로

    Returns:
        마커 파일 생성 성공 여부
    """
    try:
        from datetime import datetime

        marker_file = folder_path / ".processing"
        # 처리 시작 시간을 파일에 기록
        start_time = datetime.now().isoformat()
        marker_file.write_text(f"STARTED: {start_time}\nFOLDER: {folder_path.name}")
        logger.debug(f"처리 마커 파일 생성: {marker_file}")
        return True
    except Exception as e:
        logger.error(f"처리 마커 파일 생성 실패: {e}")
        return False


def remove_processing_marker(folder_path: Path) -> bool:
    """
    처리 완료 시 마커 파일을 제거합니다.

    Args:
        folder_path: 처리 완료된 폴더 경로

    Returns:
        마커 파일 제거 성공 여부
    """
    try:
        marker_file = folder_path / ".processing"
        if marker_file.exists():
            marker_file.unlink()
            logger.debug(f"처리 마커 파일 제거: {marker_file}")
        return True
    except Exception as e:
        logger.error(f"처리 마커 파일 제거 실패: {e}")
        return False


def cleanup_stale_processing_markers(base_path: Path, max_age_hours: int = 24) -> int:
    """
    오래된 .processing 파일들을 정리합니다.

    Args:
        base_path: 검색할 기본 경로
        max_age_hours: 최대 유지 시간 (시간)

    Returns:
        정리된 파일 수
    """
    import time

    cleaned_count = 0
    cutoff_time = time.time() - (max_age_hours * 3600)

    try:
        # .processing 파일들을 찾아서 정리
        for processing_file in base_path.rglob(".processing"):
            try:
                # 파일 수정 시간 확인
                if processing_file.stat().st_mtime < cutoff_time:
                    processing_file.unlink()
                    cleaned_count += 1
                    logger.info(f"오래된 처리 마커 파일 정리: {processing_file}")
            except Exception as e:
                logger.warning(f"처리 마커 파일 정리 실패: {processing_file} - {e}")

    except Exception as e:
        logger.error(f"오래된 처리 마커 파일 정리 중 오류: {e}")

    if cleaned_count > 0:
        logger.info(f"오래된 처리 마커 파일 {cleaned_count}개 정리 완료")

    return cleaned_count


def is_folder_being_processed(folder_path: Path) -> bool:
    """
    폴더가 현재 처리 중인지 확인합니다.

    Args:
        folder_path: 확인할 폴더 경로

    Returns:
        처리 중인지 여부
    """
    try:
        marker_file = folder_path / ".processing"
        return marker_file.exists()
    except Exception as e:
        logger.error(f"처리 상태 확인 실패: {e}")
        return False


def detect_directory_pattern(folder_path: Path) -> str:
    """
    디렉토리의 구조 패턴을 감지합니다.

    Args:
        folder_path: 분석할 디렉토리 경로

    Returns:
        패턴 타입: "standard", "koita", "seoultp", "bizinfo"
    """
    try:
        if not folder_path.exists() or not folder_path.is_dir():
            logger.warning(f"유효하지 않은 디렉토리: {folder_path}")
            return "standard"

        # bizInfo 패턴 감지: 폴더명이 PBLN_숫자이고 상위에 동일명 JSON 파일 존재
        folder_name = folder_path.name
        if folder_name.startswith("PBLN_"):
            json_file = folder_path.parent / f"{folder_name}.json"
            if json_file.exists():
                logger.info(
                    f"bizInfo 패턴 감지: {folder_path} (PBLN_* 폴더 + JSON 파일)"
                )
                return "bizInfo"

        # koita 패턴 감지: metadata.json 존재하고 attachments 폴더도 있어야 함
        metadata_json = folder_path / "metadata.json"
        attachments_dir = folder_path / "attachments"
        if (
            metadata_json.exists()
            and attachments_dir.exists()
            and attachments_dir.is_dir()
        ):
            logger.info(
                f"koita 패턴 감지: {folder_path} (metadata.json + attachments/)"
            )
            return "koita"
        elif metadata_json.exists():
            logger.warning(
                f"metadata.json 있지만 attachments/ 폴더 없음: {folder_path} - standard 패턴으로 처리"
            )

        # seoultp 패턴 감지: 디렉토리에서 숫자.md 파일들이 직접 존재
        numbered_md_files = list(folder_path.glob("[0-9]*.md"))
        if (
            numbered_md_files and len(numbered_md_files) > 5
        ):  # 충분한 수의 숫자.md 파일이 있어야 seoultp 패턴
            logger.info(
                f"seoultp 패턴 감지: {folder_path} ({len(numbered_md_files)}개 숫자.md 파일)"
            )
            return "seoultp"

        # 기본값: standard 패턴
        logger.debug(f"standard 패턴 감지: {folder_path}")
        return "standard"

    except Exception as e:
        logger.error(f"디렉토리 패턴 감지 중 오류: {folder_path} - {e}")
        return "standard"


def get_koita_metadata(folder_path: Path) -> dict:
    """
    koita 패턴 디렉토리에서 metadata.json을 읽어옵니다.

    Args:
        folder_path: koita 패턴 디렉토리 경로

    Returns:
        메타데이터 딕셔너리 또는 빈 딕셔너리
    """
    try:
        metadata_file = folder_path / "metadata.json"
        if not metadata_file.exists():
            return {}

        with open(metadata_file, encoding="utf-8") as f:
            data = json.load(f)

        # koita_metadata 구조에서 실제 데이터 추출
        if isinstance(data, dict) and "koita_metadata" in data:
            metadata = data["koita_metadata"]
            logger.info(f"koita 메타데이터 로드 완료: {folder_path}")
            return metadata
        else:
            logger.warning(f"koita_metadata 키가 없는 JSON 파일: {metadata_file}")
            return data if isinstance(data, dict) else {}

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"koita 메타데이터 읽기 실패: {folder_path} - {e}")
        return {}


def get_seoultp_file_mapping(folder_path: Path) -> list[tuple[Path, Path]]:
    """
    seoultp 패턴에서 숫자.md 파일과 대응하는 숫자/ 디렉토리의 매핑을 반환합니다.

    Args:
        folder_path: seoultp 패턴이 포함된 디렉토리 경로

    Returns:
        (md_file, corresponding_dir) 튜플의 리스트
    """
    try:
        mappings = []

        # 숫자.md 파일들 찾기
        numbered_md_files = list(folder_path.glob("[0-9]*.md"))

        for md_file in numbered_md_files:
            # 파일명에서 숫자 부분 추출
            base_name = md_file.stem  # 확장자 제거

            # 대응하는 디렉토리 찾기
            corresponding_dir = folder_path / base_name

            if corresponding_dir.exists() and corresponding_dir.is_dir():
                mappings.append((md_file, corresponding_dir))
                logger.debug(
                    f"seoultp 매핑 발견: {md_file.name} <-> {corresponding_dir.name}/"
                )
            else:
                # 디렉토리가 없어도 md 파일은 처리 대상에 포함
                mappings.append((md_file, None))
                logger.debug(f"seoultp md 파일만 존재: {md_file.name}")

        logger.info(f"seoultp 파일 매핑 완료: {len(mappings)}개 쌍")
        return mappings

    except Exception as e:
        logger.error(f"seoultp 파일 매핑 생성 실패: {folder_path} - {e}")
        return []


def extract_title_from_koita_metadata(metadata: dict) -> str:
    """
    koita 메타데이터에서 제목을 추출합니다.

    Args:
        metadata: koita 메타데이터 딕셔너리

    Returns:
        추출된 제목 또는 빈 문자열
    """
    try:
        # title 필드에서 직접 추출
        if "title" in metadata and metadata["title"]:
            title = str(metadata["title"]).strip()
            if title:
                logger.info(f"koita 제목 추출: {title}")
                return title

        # 다른 가능한 제목 필드들 확인
        title_fields = ["announcement_title", "subject", "name"]
        for field in title_fields:
            if field in metadata and metadata[field]:
                title = str(metadata[field]).strip()
                if title:
                    logger.info(f"koita 제목 추출 ({field}): {title}")
                    return title

        logger.warning("koita 메타데이터에서 제목을 찾을 수 없음")
        return ""

    except Exception as e:
        logger.error(f"koita 제목 추출 중 오류: {e}")
        return ""


def extract_title_from_seoultp_md(md_file: Path) -> str:
    """
    seoultp 패턴의 숫자.md 파일에서 제목을 추출합니다.

    Args:
        md_file: 숫자.md 파일 경로

    Returns:
        추출된 제목 또는 빈 문자열
    """
    try:
        if not md_file.exists():
            return ""

        content = md_file.read_text(encoding="utf-8")

        # 1. 첫 번째 # 헤더 찾기 (최우선)
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
            if len(title) >= 10:
                logger.info(f"seoultp 제목 추출 (# 헤더): {title}")
                return title

        # 2. HTML 제목 태그에서 추출
        title_patterns = [
            r"<title[^>]*>(.*?)</title>",
            r"제목[^>]*>(.*?)<",
            r"<h1[^>]*>(.*?)</h1>",
            r"<h2[^>]*>(.*?)</h2>",
        ]

        for pattern in title_patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
                if len(title) >= 10:
                    logger.info(f"seoultp 제목 추출 (HTML): {title}")
                    return title

        # 3. 첫 번째 긴 텍스트 줄에서 제목 추정
        lines = content.split("\n")
        for line in lines[:10]:  # 처음 10줄만 확인
            line = line.strip()
            # HTML 태그나 JavaScript 제거
            clean_line = re.sub(r"<[^>]+>", "", line)
            clean_line = re.sub(r"function\s+\w+\([^)]*\)", "", clean_line)
            clean_line = clean_line.strip()

            if len(clean_line) >= 15 and any(
                keyword in clean_line
                for keyword in ["공고", "사업", "지원", "모집", "과제", "프로그램"]
            ):
                logger.info(f"seoultp 제목 추출 (텍스트 라인): {clean_line}")
                return clean_line

        logger.warning(f"seoultp md 파일에서 제목을 찾을 수 없음: {md_file}")
        return ""

    except Exception as e:
        logger.error(f"seoultp md 파일 제목 추출 중 오류: {md_file} - {e}")
        return ""


def is_prv_site(site_code: str) -> bool:
    """
    prv 사이트 코드인지 확인합니다.

    Args:
        site_code: 사이트 코드

    Returns:
        prv 사이트 여부
    """
    return str(site_code).lower().strip() == "prv"


def get_prv_announcement_folders(site_dir: Path) -> list[tuple[Path, str, str, str]]:
    """
    prv 사이트의 공고 폴더들을 [시도]/[시군구]/공고디렉토리 패턴으로 스캔합니다.

    Args:
        site_dir: prv 사이트 디렉토리 경로 (data.origin/prv)

    Returns:
        [(공고폴더경로, 시도명, 시군구명, 공고폴더명)] 튜플 리스트
    """
    try:
        announcement_folders = []

        if not site_dir.exists() or not site_dir.is_dir():
            logger.warning(f"prv 사이트 디렉토리가 존재하지 않음: {site_dir}")
            return announcement_folders

        # 1단계: 시도 디렉토리 스캔
        for sido_dir in site_dir.iterdir():
            if not sido_dir.is_dir() or sido_dir.name.startswith("."):
                continue

            sido_name = sido_dir.name
            logger.debug(f"prv 시도 디렉토리 스캔: {sido_name}")

            # 2단계: 시군구 디렉토리 스캔
            for sigungu_dir in sido_dir.iterdir():
                if not sigungu_dir.is_dir() or sigungu_dir.name.startswith("."):
                    continue

                sigungu_name = sigungu_dir.name
                logger.debug(f"prv 시군구 디렉토리 스캔: {sido_name}/{sigungu_name}")

                # 3단계: 공고 디렉토리 스캔
                for announcement_dir in sigungu_dir.iterdir():
                    if (
                        not announcement_dir.is_dir()
                        or announcement_dir.name.startswith(".")
                    ):
                        continue

                    # 처리 마커가 있는 폴더는 건너뛰기
                    if is_folder_being_processed(announcement_dir):
                        continue

                    # 공고 폴더로 판단 (숫자_제목 형태 또는 일반 디렉토리)
                    announcement_name = announcement_dir.name
                    announcement_folders.append(
                        (announcement_dir, sido_name, sigungu_name, announcement_name)
                    )
                    logger.debug(
                        f"prv 공고 폴더 발견: {sido_name}/{sigungu_name}/{announcement_name}"
                    )

        logger.info(
            f"prv 사이트 공고 폴더 스캔 완료: {len(announcement_folders)}개 발견"
        )
        return announcement_folders

    except Exception as e:
        logger.error(f"prv 사이트 공고 폴더 스캔 중 오류: {site_dir} - {e}")
        return []


def get_prv_relative_folder_path(
    announcement_folder: Path, sido_name: str = None, sigungu_name: str = None
) -> str:
    """
    prv 사이트 공고 폴더의 상대 경로를 생성합니다.

    Args:
        announcement_folder: 공고 폴더 경로
        sido_name: 시도명 (None이면 자동 추출)
        sigungu_name: 시군구명 (None이면 자동 추출)

    Returns:
        상대 경로 (data.origin/prv/시도/시군구/공고폴더)
    """
    try:
        # 시도/시군구명 자동 추출
        if sido_name is None or sigungu_name is None:
            parts = announcement_folder.parts
            if len(parts) >= 3:
                # [.../prv/시도/시군구/공고폴더] 패턴에서 추출
                prv_index = next(
                    (i for i, part in enumerate(parts) if part == "prv"), None
                )
                if prv_index is not None and len(parts) > prv_index + 3:
                    sido_name = parts[prv_index + 1]
                    sigungu_name = parts[prv_index + 2]
                else:
                    logger.warning(
                        f"prv 경로 패턴에서 시도/시군구 추출 실패: {announcement_folder}"
                    )
                    return f"data.origin/prv/{announcement_folder.name}"
            else:
                logger.warning(f"prv 경로가 너무 짧음: {announcement_folder}")
                return f"data.origin/prv/{announcement_folder.name}"

        relative_path = (
            f"data.origin/prv/{sido_name}/{sigungu_name}/{announcement_folder.name}"
        )
        logger.debug(f"prv 상대 경로 생성: {relative_path}")
        return relative_path

    except Exception as e:
        logger.error(f"prv 상대 경로 생성 중 오류: {announcement_folder} - {e}")
        return f"data.origin/prv/{announcement_folder.name}"


def extract_prv_location_info(announcement_folder: Path) -> tuple[str, str]:
    """
    prv 공고 폴더에서 시도/시군구 정보를 추출합니다.

    Args:
        announcement_folder: prv 공고 폴더 경로

    Returns:
        (시도명, 시군구명) 튜플
    """
    try:
        parts = announcement_folder.parts
        prv_index = next((i for i, part in enumerate(parts) if part == "prv"), None)

        if prv_index is not None and len(parts) > prv_index + 3:
            sido_name = parts[prv_index + 1]
            sigungu_name = parts[prv_index + 2]
            return sido_name, sigungu_name
        else:
            logger.warning(f"prv 경로에서 위치 정보 추출 실패: {announcement_folder}")
            return "알 수 없는 시도", "알 수 없는 시군구"

    except Exception as e:
        logger.error(f"prv 위치 정보 추출 중 오류: {announcement_folder} - {e}")
        return "알 수 없는 시도", "알 수 없는 시군구"
