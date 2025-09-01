"""
데이터 처리 유틸리티

공고 데이터 후처리를 위한 함수들을 제공합니다.
"""

import re
from datetime import datetime
from typing import Optional, Tuple
from urllib.parse import urlparse

try:
    from src.config.logConfig import setup_logging
except ImportError:
    import sys
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    from src.config.logConfig import setup_logging

logger = setup_logging(__name__)


def format_date_to_standard(date_string: str) -> Optional[str]:
    """
    다양한 형태의 날짜 문자열을 YYYY-MM-DD 형태로 표준화합니다.
    
    Args:
        date_string: 원본 날짜 문자열
        
    Returns:
        표준화된 날짜 문자열 (YYYY-MM-DD) 또는 None
    """
    if not date_string or date_string.strip() in ["정보 없음", "", "없음", "-"]:
        return None
    
    # 숫자만 추출
    numbers = re.findall(r'\d+', date_string)
    
    if len(numbers) < 3:
        logger.warning(f"날짜 파싱 실패 - 숫자 부족: {date_string}")
        return None
    
    try:
        # 년, 월, 일 추출
        year, month, day = map(int, numbers[:3])
        
        # 년도 보정 (2자리 년도인 경우)
        if year < 50:
            year += 2000
        elif year < 100:
            year += 1900
        elif year < 1900:
            year += 2000
        
        # 유효성 검사
        if year < 1900 or year > 2100:
            logger.warning(f"유효하지 않은 년도: {year} from {date_string}")
            return None
            
        if month < 1 or month > 12:
            logger.warning(f"유효하지 않은 월: {month} from {date_string}")
            return None
            
        if day < 1 or day > 31:
            logger.warning(f"유효하지 않은 일: {day} from {date_string}")
            return None
        
        # datetime으로 유효성 재확인
        formatted_date = datetime(year, month, day)
        result = formatted_date.strftime("%Y-%m-%d")
        
        logger.debug(f"날짜 표준화: {date_string} -> {result}")
        return result
        
    except ValueError as e:
        logger.warning(f"날짜 변환 실패: {date_string} - {e}")
        return None


def extract_url_from_content(content: str) -> Optional[str]:
    """
    본문에서 원본 URL을 추출합니다.
    
    Args:
        content: 본문 내용
        
    Returns:
        추출된 URL 또는 None
    """
    if not content:
        return None
    
    # URL 패턴들 정의  
    url_patterns = [
        # HTTP/HTTPS URL (한국어 문자를 만나면 중단)
        r'https?://[^\s<>"\'가-힣]+',
        # 괄호나 따옴표로 둘러싸인 URL
        r'[\(\[]*(https?://[^\s<>"\'가-힣]+)[\)\]]*',
        # "자세한 내용:", "원본:", "링크:" 등 다음에 오는 URL
        r'(?:자세한\s*내용|원본|링크|URL|홈페이지|사이트)\s*[:：]\s*(https?://[^\s<>"\'가-힣]+)',
        # ※ 이나 * 다음에 오는 URL
        r'[※*]\s*(https?://[^\s<>"\'가-힣]+)',
    ]
    
    for pattern in url_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            # 첫 번째 매치를 사용
            url = matches[0] if isinstance(matches[0], str) else matches[0][0] if matches[0] else None
            if url:
                # URL 정제
                url = url.strip('.,;)')
                # 유효한 URL인지 확인
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc:
                    logger.debug(f"URL 추출 성공: {url}")
                    return url
    
    logger.debug("URL 추출 실패")
    return None


def analyze_target_type_and_small_business(target_description: str) -> Tuple[Optional[str], Optional[bool]]:
    """
    지원대상 설명을 분석하여 개인/기업 구분과 소상공인 해당 여부를 판단합니다.
    
    Args:
        target_description: 지원대상 설명 텍스트
        
    Returns:
        (target_type, is_small_business) 튜플
        - target_type: "individual", "company", None
        - is_small_business: True/False/None
    """
    if not target_description or target_description.strip() in ["정보 없음", "", "없음", "-"]:
        return None, None
    
    target_text = target_description.lower()
    target_type = None
    is_small_business = None
    
    # 개인/기업 판단 키워드
    individual_keywords = [
        "개인", "개별", "자연인", "사람", "시민", "주민", "청년", "청소년", "학생", "구직자",
        "취업자", "근로자", "직장인", "예술가", "창작자", "작가", "개인사업자"
    ]
    
    company_keywords = [
        "기업", "회사", "법인", "단체", "조합", "협회", "업체", "사업자", "사업체", "업소",
        "점포", "상점", "매장", "공장", "제조업", "서비스업", "음식점", "카페", "식당",
        "중소기업", "소기업", "벤처기업", "스타트업", "협동조합"
    ]
    
    # 소상공인 판단 키워드
    small_business_keywords = [
        "소상공인", "소기업", "영세", "소규모", "자영업", "개인사업", "상점", "점포", "매장",
        "음식점", "카페", "식당", "미용실", "이발소", "세탁소", "편의점", "슈퍼", "마트",
        "떡집", "빵집", "횟집", "치킨집", "피자집", "족발", "보쌈", "분식", "김밥",
        "생계형", "적합업종", "근로자.*10.*미만", "근로자.*5.*미만", "10명.*미만", "5명.*미만"
    ]
    
    # 규모/매출 기준 키워드 (소상공인 판단)
    small_business_size_patterns = [
        r"근로자.*\d+.*미만",
        r"직원.*\d+.*미만", 
        r"종업원.*\d+.*미만",
        r"\d+명.*미만",
        r"매출.*\d+억.*이하",
        r"매출.*\d+억.*미만",
        r"연매출.*\d+억",
        r"상시.*근로자.*\d+.*미만"
    ]
    
    # 개인/기업 판단
    individual_score = sum(1 for keyword in individual_keywords if keyword in target_text)
    company_score = sum(1 for keyword in company_keywords if keyword in target_text)
    
    if company_score > individual_score:
        target_type = "company"
    elif individual_score > company_score:
        target_type = "individual"
    else:
        # 동점인 경우 더 구체적인 판단
        if any(keyword in target_text for keyword in ["법인", "기업", "회사", "업체"]):
            target_type = "company"
        elif any(keyword in target_text for keyword in ["개인", "자연인", "시민"]):
            target_type = "individual"
    
    # 소상공인 판단 (기업인 경우만)
    if target_type == "company":
        small_business_score = sum(1 for keyword in small_business_keywords if keyword in target_text)
        
        # 규모 기준 패턴 확인
        size_match = any(re.search(pattern, target_text) for pattern in small_business_size_patterns)
        
        if small_business_score > 0 or size_match:
            is_small_business = True
        else:
            # 중소기업이라는 언급은 있지만 소상공인 특정 키워드가 없는 경우
            if "중소기업" in target_text and small_business_score == 0:
                is_small_business = False  # 중소기업이지만 소상공인은 아닌 것으로 판단
            else:
                is_small_business = None  # 판단 불가
    
    logger.debug(f"지원대상 분석: {target_description[:50]}... -> type: {target_type}, small_business: {is_small_business}")
    
    return target_type, is_small_business