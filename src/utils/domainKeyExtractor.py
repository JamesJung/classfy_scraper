"""
도메인별 URL 키 추출기
=====================

목적:
- 도메인별로 정의된 키 파라미터를 사용하여 URL에서 고유 식별자 추출
- domain_key_config 테이블의 설정을 동적으로 적용
- 단일/다중 키 파라미터 모두 지원

특징:
- LRU 캐시로 도메인 설정 캐싱 (DB 쿼리 최소화)
- 단일 키, 이중 키, 삼중+ 키 모두 지원
- 쿼리 파라미터 및 경로 기반 추출 지원
"""

import json
import re
from functools import lru_cache
from typing import Optional, List, Dict, Tuple
from urllib.parse import urlparse, parse_qs
import mysql.connector
from mysql.connector import pooling


class DomainKeyExtractor:
    """도메인별 URL 키 추출기"""

    def __init__(self, db_connection_pool=None, db_config=None):
        """
        Args:
            db_connection_pool: MySQL connection pool (선택)
            db_config: DB 설정 딕셔너리 (pool 없을 때)
        """
        self.pool = db_connection_pool
        self.db_config = db_config

        # 폴백용 기본 우선순위 (DB 설정 없을 때)
        self.fallback_priority = [
            'pbancSn', 'bltSeq', 'nttId', 'bbsId', 'menuId',
            'articleNo', 'boardId', 'contentId', 'srnID'
        ]

    def _get_connection(self):
        """DB 연결 획득"""
        if self.pool:
            return self.pool.get_connection()
        elif self.db_config:
            return mysql.connector.connect(**self.db_config)
        else:
            raise ValueError("DB connection pool or config required")

    @lru_cache(maxsize=2000)
    def get_domain_configs(self, domain: str) -> List[Dict]:
        """
        도메인의 모든 설정 조회 (게시판별 설정 포함, 캐시됨)

        Args:
            domain: 도메인 (예: www.k-startup.go.kr)

        Returns:
            [{
                'domain': 'www.k-startup.go.kr',
                'site_code': 'kStartUp',
                'key_params': ['pbancSn'],
                'extraction_method': 'query_params',
                'path_pattern': None
            }, ...]
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT
                    domain,
                    site_code,
                    key_params,
                    extraction_method,
                    path_pattern
                FROM domain_key_config
                WHERE domain = %s AND is_active = TRUE
                ORDER BY
                    CASE
                        WHEN path_pattern IS NOT NULL THEN 1
                        ELSE 2
                    END
            """, (domain,))

            results = cursor.fetchall()
            cursor.close()
            conn.close()

            if results:
                # JSON 문자열을 리스트로 변환
                for result in results:
                    result['key_params'] = json.loads(result['key_params'])

            return results if results else []

        except Exception as e:
            print(f"⚠️  도메인 설정 조회 실패: {domain} - {e}")
            return []

    def get_domain_config(self, domain: str, path: str = None) -> Optional[Dict]:
        """
        도메인 설정 조회 (경로 매칭 지원)

        Args:
            domain: 도메인 (예: www.suwon.go.kr)
            path: URL 경로 (예: /BD_ofrView.do)

        Returns:
            매칭된 설정 또는 None
        """
        configs = self.get_domain_configs(domain)

        if not configs:
            return None

        # 1. path_pattern이 있는 설정 중 매칭되는 것 찾기
        if path:
            for config in configs:
                if config.get('path_pattern'):
                    # path가 path_pattern으로 시작하는지 확인
                    if path.startswith(config['path_pattern']):
                        return config

        # 2. path_pattern이 없는 기본 설정 찾기
        for config in configs:
            if not config.get('path_pattern'):
                return config

        # 3. path_pattern만 있고 매칭 안되면 첫 번째 설정 반환
        return configs[0] if configs else None

    def extract_url_key(self, url: str, site_code: Optional[str] = None) -> Optional[str]:
        """
        URL에서 고유 키 추출 (게시판별 설정 지원)

        Args:
            url: 전체 URL
            site_code: 사이트 코드 (선택, 도메인 매칭 실패시 사용)

        Returns:
            URL 키 문자열 (예: "www.k-startup.go.kr|pbancSn=172173")
            또는 None (키 추출 실패)

        Examples:
            >>> extractor.extract_url_key("https://www.k-startup.go.kr/web/contents/bizpbanc.do?pbancSn=172173")
            'www.k-startup.go.kr|pbancSn=172173'

            >>> extractor.extract_url_key("https://www.suwon.go.kr/BD_ofrView.do?notAncmtMgtNo=145363")
            'www.suwon.go.kr|notAncmtMgtNo=145363'

            >>> extractor.extract_url_key("https://www.suwon.go.kr/BD_board.view.do?seq=12345&bbsCd=1042")
            'www.suwon.go.kr|seq=12345&bbsCd=1042'
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            path = parsed.path
            query_params = parse_qs(parsed.query)

            # 1. 도메인 설정 조회 (경로 매칭 지원)
            config = self.get_domain_config(domain, path)

            if config:
                # 설정된 방법으로 추출
                if config['extraction_method'] == 'query_params':
                    return self._extract_by_query_params(domain, query_params, config['key_params'])
                elif config['extraction_method'] == 'path_pattern':
                    return self._extract_by_path_pattern(domain, path, config['path_pattern'])
                elif config['extraction_method'] == 'mixed':
                    return self._extract_mixed(domain, parsed, query_params, config)

            # 2. 설정 없으면 폴백 로직
            return self._extract_by_fallback(domain, query_params)

        except Exception as e:
            print(f"⚠️  URL 키 추출 실패: {url} - {e}")
            return None

    def _extract_by_query_params(
        self, domain: str, query_params: Dict, key_params: List[str]
    ) -> Optional[str]:
        """
        쿼리 파라미터 기반 키 추출 (가장 일반적)

        Args:
            domain: 도메인
            query_params: parse_qs 결과
            key_params: 필수 키 파라미터 리스트 (예: ['nttId', 'bbsId'])

        Returns:
            URL 키 또는 None
        """
        key_parts = []

        for param in key_params:
            if param in query_params and query_params[param]:
                value = query_params[param][0]  # 첫 번째 값 사용
                key_parts.append(f"{param}={value}")
            else:
                # 필수 파라미터 누락
                print(f"⚠️  필수 파라미터 누락: {domain} - {param}")
                return None

        if key_parts:
            return f"{domain}|{'&'.join(key_parts)}"

        return None

    def _extract_by_path_pattern(
        self, domain: str, path: str, pattern: str
    ) -> Optional[str]:
        """
        경로 패턴 기반 키 추출

        Args:
            domain: 도메인
            path: URL 경로
            pattern: 정규표현식 패턴

        Returns:
            URL 키 또는 None
        """
        if not pattern:
            return None

        match = re.search(pattern, path)
        if match:
            # 매칭된 그룹들을 키로 사용
            groups = match.groups()
            if groups:
                key_value = '_'.join(str(g) for g in groups)
                return f"{domain}|{key_value}"

        return None

    def _extract_mixed(
        self, domain: str, parsed, query_params: Dict, config: Dict
    ) -> Optional[str]:
        """
        경로 + 쿼리 파라미터 혼합 추출

        Args:
            domain: 도메인
            parsed: urlparse 결과
            query_params: 쿼리 파라미터
            config: 도메인 설정

        Returns:
            URL 키 또는 None
        """
        # 경로에서 추출
        path_key = self._extract_by_path_pattern(domain, parsed.path, config['path_pattern'])

        # 쿼리에서 추출
        query_key = self._extract_by_query_params(domain, query_params, config['key_params'])

        if path_key and query_key:
            return f"{path_key}_{query_key}"
        elif path_key:
            return path_key
        elif query_key:
            return query_key

        return None

    def _extract_by_fallback(self, domain: str, query_params: Dict) -> Optional[str]:
        """
        폴백 로직: DB 설정 없을 때 우선순위 기반 추출

        Args:
            domain: 도메인
            query_params: 쿼리 파라미터

        Returns:
            URL 키 또는 None
        """
        for param in self.fallback_priority:
            if param in query_params and query_params[param]:
                value = query_params[param][0]
                return f"{domain}|{param}={value}"

        # 우선순위에 없으면 첫 번째 파라미터 사용
        if query_params:
            first_param = list(query_params.keys())[0]
            first_value = query_params[first_param][0]
            return f"{domain}|{first_param}={first_value}"

        return None

    def bulk_extract(self, urls: List[str]) -> List[Tuple[str, Optional[str]]]:
        """
        여러 URL에서 키 일괄 추출

        Args:
            urls: URL 리스트

        Returns:
            [(url, url_key), ...] 튜플 리스트
        """
        results = []
        for url in urls:
            url_key = self.extract_url_key(url)
            results.append((url, url_key))
        return results

    def validate_url_key(self, url: str, expected_key: str) -> bool:
        """
        URL에서 추출한 키가 예상값과 일치하는지 검증

        Args:
            url: URL
            expected_key: 예상 키

        Returns:
            일치 여부
        """
        extracted_key = self.extract_url_key(url)
        return extracted_key == expected_key

    def clear_cache(self):
        """도메인 설정 캐시 클리어"""
        self.get_domain_configs.cache_clear()
        print("✅ 도메인 설정 캐시 클리어 완료")

    def get_cache_info(self) -> Dict:
        """캐시 통계 조회"""
        cache_info = self.get_domain_configs.cache_info()
        return {
            'hits': cache_info.hits,
            'misses': cache_info.misses,
            'maxsize': cache_info.maxsize,
            'currsize': cache_info.currsize,
            'hit_rate': cache_info.hits / (cache_info.hits + cache_info.misses)
                if (cache_info.hits + cache_info.misses) > 0 else 0
        }


# =====================================================
# 사용 예시
# =====================================================

if __name__ == "__main__":
    # DB 설정
    db_config = {
        'host': 'localhost',
        'user': 'root',
        'password': 'your_password',
        'database': 'subvention'
    }

    # Extractor 초기화
    extractor = DomainKeyExtractor(db_config=db_config)

    # 테스트 URL들
    test_urls = [
        # 단일 키
        "https://www.k-startup.go.kr/web/contents/bizpbanc-deadline.do?pbancSn=172173",
        "https://www.bizinfo.go.kr/web/lay1/program/S1T294C295/business/retrieveBusinessDetail.do?bltSeq=1234567",

        # 이중 키
        "https://www.daegu.go.kr/dgcontent/index.do?menu_id=00940170&nttId=123456&bbsId=789",
        "https://www.seoul.go.kr/news/news_report.do?nttId=98765&menuId=548",

        # 삼중 키
        "https://www.gyeongnam.go.kr/board/view.gyeong?nttId=111&bbsId=222&categoryId=333"
    ]

    print("=" * 60)
    print("URL 키 추출 테스트")
    print("=" * 60)

    for url in test_urls:
        url_key = extractor.extract_url_key(url)
        print(f"\n원본 URL:")
        print(f"  {url}")
        print(f"추출된 키:")
        print(f"  {url_key}")

    # 캐시 통계
    print("\n" + "=" * 60)
    print("캐시 통계")
    print("=" * 60)
    cache_info = extractor.get_cache_info()
    print(f"  Hits: {cache_info['hits']}")
    print(f"  Misses: {cache_info['misses']}")
    print(f"  Hit Rate: {cache_info['hit_rate']:.2%}")
    print(f"  Cache Size: {cache_info['currsize']}/{cache_info['maxsize']}")
