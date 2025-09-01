"""
EXTRACTED_TEXT 필드에서 원하지 않는 특수문자를 제거하는 유틸리티

특수문자 제거 대상:
- CJK 표의문자 범위의 의미없는 문자들 (氠瑢, 捤獥, 汤捯湰灧慤桥 등)
- 제어 문자 및 비표시 문자
- 파일 변환 과정에서 생성된 노이즈 문자
- 깨진 인코딩으로 인한 특수문자

보존 대상:
- 한글 문자 (가-힣, ㄱ-ㅎ, ㅏ-ㅣ)
- 영문자 (A-Z, a-z)
- 숫자 (0-9)
- 기본 구두점 및 공백
- 일반적인 한국어 문서에서 사용되는 기호들
"""

import re
import unicodedata

from src.config.logConfig import setup_logging

logger = setup_logging(__name__)

# 의미있는 문자 패턴 정의
MEANINGFUL_PATTERNS = [
    r"[가-힣]",  # 한글 완성형
    r"[ㄱ-ㅎㅏ-ㅣ]",  # 한글 자모
    r"[A-Za-z0-9]",  # 영문자, 숫자
    r"[\s\n\r\t]",  # 공백 문자들
    r'[.,;:!?\'"()\[\]{}<>/\\|~`@#$%^&*+=\-_]',  # 기본 구두점 및 기호
    r"[·※○●△▲□■◇◆▼▽◁▷]",  # 한국어 문서에서 자주 사용되는 기호
    r"[①②③④⑤⑥⑦⑧⑨⑩]",  # 원문자 숫자
    r"[ⅰⅱⅲⅳⅴ]",  # 로마 숫자
    r"[→←↑↓]",  # 화살표
    r"[℃℉％]",  # 단위 기호
]

# 제거 대상 문자 패턴 정의
REMOVAL_PATTERNS = [
    # CJK 표의문자 중 의미없는 문자들 (변환 노이즈)
    r"[氠瑢捤獥汤捯湰灧慤桥]",
    # 기타 변환 노이즈로 자주 발생하는 문자들
    r"[矞硥潥啫樠桵猠摮]",
    # 제어 문자 (0x00-0x1F, 0x7F-0x9F)
    r"[\x00-\x1F\x7F-\x9F]",
    # 잘못된 UTF-8 바이트 시퀀스로 인한 특수문자
    r"[￿�]",
    # 폰트 렌더링 문제로 인한 특수문자
    r"[\uE000-\uF8FF]",  # Private Use Area
    # 기타 알려진 노이즈 문자들
    r"[\u2028\u2029\uFEFF]",  # Line/Paragraph separators, BOM
]


def is_meaningful_char(char: str) -> bool:
    """
    문자가 의미있는 문자인지 확인합니다.

    Args:
        char: 검사할 문자 (단일 문자)

    Returns:
        bool: 의미있는 문자이면 True, 아니면 False
    """
    if not char or len(char) != 1:
        return False

    # 의미있는 패턴 중 하나에 매칭되는지 확인
    for pattern in MEANINGFUL_PATTERNS:
        if re.match(pattern, char):
            return True

    # 유니코드 카테고리 기반 추가 검사
    category = unicodedata.category(char)

    # 문자(Letter), 숫자(Number), 구두점(Punctuation), 기호(Symbol)의 일부는 허용
    if category.startswith(("L", "N")):  # Letter, Number
        return True

    if category in ("Pc", "Pd", "Pe", "Pf", "Pi", "Po", "Ps"):  # Punctuation
        return True

    if category in ("Sc", "Sk", "Sm", "So"):  # Symbol
        # 하지만 CJK 범위의 기호는 검토 필요
        code_point = ord(char)
        # CJK 표의문자 범위 (U+4E00-U+9FFF) 내의 기호는 제외
        if 0x4E00 <= code_point <= 0x9FFF:
            return False
        return True

    return False


def should_remove_char(char: str) -> bool:
    """
    문자가 제거 대상인지 확인합니다.

    Args:
        char: 검사할 문자 (단일 문자)

    Returns:
        bool: 제거해야 하는 문자이면 True, 아니면 False
    """
    if not char or len(char) != 1:
        return True

    # 제거 패턴 중 하나에 매칭되는지 확인
    for pattern in REMOVAL_PATTERNS:
        if re.match(pattern, char):
            return True

    return False


# 가이드 문서 및 무관한 섹션 패턴 정의
GUIDE_SECTION_PATTERNS = [
    r"소상공인\s*확인\s*기준.*?(?=\n\n|\n[가-힣]{2,}|\Z)",
    r"중소기업기본법\s*시행령.*?(?=\n\n|\n[가-힣]{2,}|\Z)",
    r"별표\s*[0-9]+.*?제조업.*?(?=\n\n|\n[가-힣]{2,}|\Z)",
    r"업종\s*분류표.*?(?=\n\n|\n[가-힣]{2,}|\Z)",
    r"확인방법.*?(?=\n\n|\n[가-힣]{2,}|\Z)",
    r"첨부.*?(?:파일|서류|문서).*?(?=\n\n|\n[가-힣]{2,}|\Z)",
    r"참고.*?(?:자료|사항).*?(?=\n\n|\n[가-힣]{2,}|\Z)",
]

# 날짜 패턴 (업종코드로 오인식 방지)
DATE_PATTERNS = [
    r"\d{4}[\.\-/]\d{1,2}[\.\-/]\d{1,2}",  # 2021.03.31, 2021-03-31, 2021/03/31
    r"\d{1,2}[\.\-/]\d{1,2}[\.\-/]\d{4}",  # 03.31.2021, 03-31-2021, 03/31/2021
    r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일",  # 2021년 3월 31일
]


def remove_guide_sections(text: str) -> str:
    """
    가이드 문서 섹션을 제거합니다.

    Args:
        text: 원본 텍스트

    Returns:
        str: 가이드 섹션이 제거된 텍스트
    """
    if not text:
        return ""

    cleaned_text = text
    removed_sections = []

    # 가이드 섹션 패턴 제거
    for pattern in GUIDE_SECTION_PATTERNS:
        matches = re.findall(pattern, cleaned_text, re.DOTALL | re.IGNORECASE)
        if matches:
            removed_sections.extend(matches)
            cleaned_text = re.sub(
                pattern, "", cleaned_text, flags=re.DOTALL | re.IGNORECASE
            )

    # 제조업 관련 업종 분류 테이블 제거
    manufacturing_table_pattern = r"(?:식료품|음료|섬유|화학|금속|기계|전자|자동차).*?제조업.*?C\d+.*?(?=\n\n|\n[가-힣]{2,}|\Z)"
    matches = re.findall(
        manufacturing_table_pattern, cleaned_text, re.DOTALL | re.IGNORECASE
    )
    if matches:
        removed_sections.extend(matches)
        cleaned_text = re.sub(
            manufacturing_table_pattern,
            "",
            cleaned_text,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # 로깅
    if removed_sections:
        logger.info(f"가이드 섹션 제거: {len(removed_sections)}개 섹션 제거됨")
        for i, section in enumerate(removed_sections[:3]):  # 처음 3개만 로깅
            logger.debug(f"제거된 섹션 {i+1}: {section[:100]}...")

    return cleaned_text.strip()


def mask_date_patterns(text: str) -> str:
    """
    날짜 패턴을 마스킹하여 업종코드로 오인식되는 것을 방지합니다.

    Args:
        text: 원본 텍스트

    Returns:
        str: 날짜 패턴이 마스킹된 텍스트
    """
    if not text:
        return ""

    masked_text = text
    date_replacements = []

    for pattern in DATE_PATTERNS:
        matches = re.findall(pattern, masked_text)
        if matches:
            for match in matches:
                # 날짜를 [날짜]로 마스킹
                replacement = f"[날짜_{match}]"
                masked_text = masked_text.replace(match, replacement)
                date_replacements.append((match, replacement))

    # 로깅
    if date_replacements:
        logger.debug(f"날짜 패턴 마스킹: {len(date_replacements)}개 날짜 마스킹됨")

    return masked_text


def clean_extracted_text(text: str | None, remove_guides: bool = True) -> str:
    """
    EXTRACTED_TEXT에서 원하지 않는 특수문자 및 가이드 문서를 제거합니다.

    Args:
        text: 정리할 텍스트
        remove_guides: 가이드 섹션 제거 여부 (기본값: True)

    Returns:
        str: 정리된 텍스트
    """
    if not text or not isinstance(text, str):
        return ""

    # 단계별 정리 과정
    original_length = len(text)
    cleaned_text = text

    # 0단계: 가이드 문서 섹션 제거 (새로 추가)
    if remove_guides:
        cleaned_text = remove_guide_sections(cleaned_text)
        cleaned_text = mask_date_patterns(cleaned_text)

    # 1단계: 명시적 제거 패턴 적용
    removed_chars = set()

    for pattern in REMOVAL_PATTERNS:
        matches = re.findall(pattern, cleaned_text)
        if matches:
            removed_chars.update(matches)
            cleaned_text = re.sub(pattern, "", cleaned_text)

    # 2단계: 문자별 검증
    final_chars = []
    additional_removed = set()

    for char in cleaned_text:
        if should_remove_char(char):
            additional_removed.add(char)
            continue

        if is_meaningful_char(char):
            final_chars.append(char)
        else:
            # 의미없는 문자로 판단되는 경우
            code_point = ord(char)

            # CJK 표의문자 범위 내의 알려지지 않은 문자들 제거
            if 0x4E00 <= code_point <= 0x9FFF:
                # 하지만 일반적인 한자는 보존 (한국어 문서에서 가끔 사용됨)
                try:
                    char_name = unicodedata.name(char, "")
                    # 'CJK IDEOGRAPH'로 시작하는 일반적인 한자는 보존
                    if char_name.startswith("CJK IDEOGRAPH"):
                        final_chars.append(char)
                    else:
                        additional_removed.add(char)
                except ValueError:
                    # 이름을 찾을 수 없는 문자는 제거
                    additional_removed.add(char)
            else:
                additional_removed.add(char)

    # 3단계: 연속된 공백 정리
    result = "".join(final_chars)
    result = re.sub(r"\s+", " ", result)  # 연속된 공백을 하나로
    result = result.strip()  # 앞뒤 공백 제거

    # 로깅
    final_length = len(result)
    if removed_chars or additional_removed:
        all_removed = removed_chars.union(additional_removed)
        logger.debug(f"텍스트 정리 완료: {original_length} -> {final_length} 문자")
        logger.debug(
            f"제거된 특수문자: {list(all_removed)[:20]}..."
        )  # 처음 20개만 로깅

    return result


def analyze_text_characters(text: str, max_chars: int = 100) -> dict:
    """
    텍스트의 문자 구성을 분석합니다. (디버깅용)

    Args:
        text: 분석할 텍스트
        max_chars: 분석할 최대 문자 수

    Returns:
        dict: 문자 분석 결과
    """
    if not text:
        return {"total_chars": 0, "character_categories": {}, "suspicious_chars": []}

    char_categories = {}
    suspicious_chars = []
    analyzed_chars = text[:max_chars]

    for char in analyzed_chars:
        # 유니코드 카테고리 분석
        category = unicodedata.category(char)
        char_categories[category] = char_categories.get(category, 0) + 1

        # 의심스러운 문자 찾기
        if should_remove_char(char) or not is_meaningful_char(char):
            char_info = {
                "char": char,
                "unicode": f"U+{ord(char):04X}",
                "category": category,
                "name": unicodedata.name(char, "UNKNOWN"),
            }
            if char_info not in suspicious_chars:
                suspicious_chars.append(char_info)

    return {
        "total_chars": len(text),
        "analyzed_chars": len(analyzed_chars),
        "character_categories": char_categories,
        "suspicious_chars": suspicious_chars[:20],  # 처음 20개만
    }


def preview_cleaning(text: str, max_length: int = 500) -> dict:
    """
    텍스트 정리 결과를 미리보기합니다. (디버깅용)

    Args:
        text: 원본 텍스트
        max_length: 미리보기할 최대 길이

    Returns:
        dict: 정리 전후 비교 결과
    """
    if not text:
        return {"original": "", "cleaned": "", "changes": []}

    original_preview = text[:max_length]
    cleaned_preview = clean_extracted_text(text)[:max_length]

    # 변경 사항 찾기
    changes = []
    original_chars = set(original_preview)
    cleaned_chars = set(cleaned_preview)
    removed_chars = original_chars - cleaned_chars

    for char in removed_chars:
        changes.append(
            {
                "removed_char": char,
                "unicode": f"U+{ord(char):04X}",
                "name": unicodedata.name(char, "UNKNOWN"),
            }
        )

    return {
        "original": original_preview,
        "cleaned": cleaned_preview,
        "original_length": len(text),
        "cleaned_length": len(clean_extracted_text(text)),
        "changes": changes[:20],  # 처음 20개만
    }
