"""
URL Key 생성 유틸리티

origin_url에서 고유 식별자(url_key)를 추출하는 유틸리티입니다.
중복 URL 저장을 방지하기 위해 사용됩니다.
"""

import hashlib
from urllib.parse import urlparse, parse_qs
from typing import Optional


def extract_url_key(url: str) -> Optional[str]:
    """
    URL에서 고유 식별자를 추출합니다.

    Args:
        url: 원본 URL

    Returns:
        str: 고유 식별자 (도메인|파라미터=값 형식)
        None: URL이 없거나 잘못된 경우

    Examples:
        >>> extract_url_key("https://www.k-startup.go.kr/web/contents/bizpbanc-deadline.do?schM=view&pbancSn=172173")
        'www.k-startup.go.kr|pbancSn=172173'

        >>> extract_url_key("https://www.jcon.or.kr/board/view.php?nttId=4005&bbsId=BBSMSTR_000000000001")
        'www.jcon.or.kr|nttId=4005'

        >>> extract_url_key("https://www.bcci.or.kr/kr/index.php?pCode=notice&mode=view&idx=7703")
        'www.bcci.or.kr|idx=7703'
    """
    if not url or not isinstance(url, str) or url.strip() == '':
        return None

    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        path = parsed.path
        query = parse_qs(parsed.query)

        # 고유 ID로 사용될 수 있는 query parameter 키 목록 (우선순위 순)
        id_params = [
            # 국가기관 표준
            'nttId', 'NttId', 'NTTID',  # 게시글 ID
            'bbsId', 'BbsId', 'BBSID',  # 게시판 ID

            # K-Startup
            'pbancSn',  # 공고일련번호
            'searchBusinessSn',  # 사업일련번호
            'searchDtlAncmSn',  # 상세공고일련번호

            # 일반적인 ID 파라미터
            'id', 'ID',
            'seq', 'SEQ',
            'no', 'NO', 'num', 'NUM',
            'idx', 'IDX', 'index', 'INDEX',

            # 게시판 관련
            'articleId', 'article_id',
            'boardId', 'board_id', 'boardNo',
            'noticeId', 'notice_id',
            'postId', 'post_id',
            'contentId', 'content_id',
            'wr_id',  # gnuboard

            # 기타
            'pn',  # page number
            'bidNtceNo',  # 입찰공고번호
            'annoNo',  # 공고번호
            'dtlBizId',  # 사업상세ID
        ]

        # 1. Query parameter에서 ID 추출
        for param in id_params:
            if param in query and query[param]:
                value = query[param][0]
                return f"{domain}|{param}={value}"

        # 2. Path에서 숫자 ID 추출 (예: /board/123, /notice/456)
        path_parts = [p for p in path.split('/') if p]
        if path_parts:
            # 마지막 부분이 숫자인 경우
            if path_parts[-1].isdigit():
                return f"{domain}|path={path_parts[-1]}"

            # .do, .jsp 등의 확장자 제거 후 확인
            last_part = path_parts[-1].split('.')[0]
            if last_part.isdigit():
                return f"{domain}|path={last_part}"

        # 3. 전체 query string이 있는 경우
        if parsed.query:
            # query string이 너무 길면 해시값 사용 (200자 초과)
            if len(parsed.query) > 200:
                query_hash = hashlib.md5(parsed.query.encode()).hexdigest()[:16]
                return f"{domain}|query_hash={query_hash}"
            return f"{domain}|query={parsed.query}"

        # 4. 전체 path (고유 ID를 찾지 못한 경우)
        if path and path != '/':
            # path가 너무 길면 해시값 사용 (200자 초과)
            if len(path) > 200:
                path_hash = hashlib.md5(path.encode()).hexdigest()[:16]
                return f"{domain}|path_hash={path_hash}"
            return f"{domain}|{path}"

        # 5. 도메인만 (최후의 수단)
        return f"{domain}|root"

    except Exception as e:
        # 오류 발생 시 원본 URL을 해시값으로
        print(f"URL 파싱 오류: {url} - {e}")
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return f"error|{url_hash}"


def is_valid_url_key(url_key: Optional[str]) -> bool:
    """
    URL Key가 유효한지 확인합니다.

    Args:
        url_key: 검증할 URL Key

    Returns:
        bool: 유효하면 True, 아니면 False
    """
    if not url_key or not isinstance(url_key, str):
        return False

    # 최소한 도메인|키=값 형식이어야 함
    if '|' not in url_key:
        return False

    parts = url_key.split('|', 1)
    if len(parts) != 2:
        return False

    domain, key_value = parts

    # 도메인은 비어있으면 안됨
    if not domain or domain.strip() == '':
        return False

    # 키-값도 비어있으면 안됨
    if not key_value or key_value.strip() == '':
        return False

    return True


def get_url_domain(url_key: str) -> Optional[str]:
    """
    URL Key에서 도메인을 추출합니다.

    Args:
        url_key: URL Key

    Returns:
        str: 도메인
        None: 잘못된 URL Key

    Example:
        >>> get_url_domain("www.k-startup.go.kr|pbancSn=172173")
        'www.k-startup.go.kr'
    """
    if not is_valid_url_key(url_key):
        return None

    return url_key.split('|', 1)[0]


def get_url_param(url_key: str) -> Optional[str]:
    """
    URL Key에서 파라미터 부분을 추출합니다.

    Args:
        url_key: URL Key

    Returns:
        str: 파라미터 부분
        None: 잘못된 URL Key

    Example:
        >>> get_url_param("www.k-startup.go.kr|pbancSn=172173")
        'pbancSn=172173'
    """
    if not is_valid_url_key(url_key):
        return None

    return url_key.split('|', 1)[1]


# 사용 예제
if __name__ == "__main__":
    # 테스트 URL 목록
    test_urls = [
        "https://www.k-startup.go.kr/web/contents/bizpbanc-deadline.do?schM=view&pbancSn=172173",
        "https://www.jcon.or.kr/board/view.php?nttId=4005&bbsId=BBSMSTR_000000000001&pageId=C000000016",
        "https://www.bcci.or.kr/kr/index.php?pCode=notice&mode=view&idx=7703",
        "https://www.daegu.go.kr/index.do?menu_id=00940170&menu_link=/front/daeguSidoGosi/daeguSidoGosiView.do",
        "https://www.smart-factory.kr/usr/bg/ba/ma/bsnsPblanc",
        "http://sido.jeju.go.kr/citynet/jsp/sap/SAPGosiBizProcess.do?command=searchList&flag=gosiGL",
    ]

    print("URL Key 추출 테스트")
    print("=" * 80)

    for url in test_urls:
        url_key = extract_url_key(url)
        print(f"\nURL: {url}")
        print(f"Key: {url_key}")
        print(f"Valid: {is_valid_url_key(url_key)}")
        if url_key:
            print(f"Domain: {get_url_domain(url_key)}")
            print(f"Param: {get_url_param(url_key)}")
