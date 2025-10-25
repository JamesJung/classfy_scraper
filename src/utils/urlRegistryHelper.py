"""
URL Registry Helper

사이트별 URL 레지스트리 관리를 위한 헬퍼 클래스
스크래퍼에서 쉽게 사용할 수 있도록 설계됨
"""

import mysql.connector
from typing import Optional, Dict, List
from datetime import datetime
from .urlKeyUtil import extract_url_key
from urllib.parse import urlparse


class URLRegistryHelper:
    """URL 레지스트리 관리 헬퍼"""

    def __init__(self, db_connection):
        """
        Args:
            db_connection: MySQL connection 객체
        """
        self.conn = db_connection
        self.cursor = self.conn.cursor(dictionary=True)

    def register_url(
        self,
        site_code: str,
        origin_url: str,
        announcement_id: Optional[int] = None,
        auto_commit: bool = True
    ) -> Dict:
        """
        URL을 레지스트리에 등록하고 중복 여부를 반환합니다.

        Args:
            site_code: 사이트 코드
            origin_url: 원본 URL
            announcement_id: announcement_pre_processing.id
            auto_commit: 자동 커밋 여부

        Returns:
            dict: {
                'is_duplicate': bool,  # 기존에 존재하던 URL인지
                'url_key': str,        # 생성된 URL 키
                'registry_id': int,    # url_registry.id
                'collection_count': int  # 수집 시도 횟수
            }
        """
        if not origin_url or origin_url.strip() == '':
            return {
                'is_duplicate': False,
                'url_key': None,
                'registry_id': None,
                'collection_count': 0,
                'error': 'Empty URL'
            }

        # url_key 생성
        url_key = extract_url_key(origin_url)
        if not url_key:
            return {
                'is_duplicate': False,
                'url_key': None,
                'registry_id': None,
                'collection_count': 0,
                'error': 'Failed to extract URL key'
            }

        # url_key 파싱
        components = self._parse_url_key(url_key)

        try:
            # 먼저 기존 존재 여부 확인
            check_query = """
                SELECT id, collection_count
                FROM url_registry
                WHERE site_code = %s AND url_key = %s
            """
            self.cursor.execute(check_query, (site_code, url_key))
            existing = self.cursor.fetchone()

            is_duplicate = existing is not None

            # INSERT ON DUPLICATE KEY UPDATE
            query = """
                INSERT INTO url_registry (
                    site_code, url_key, origin_url,
                    url_domain, url_param_type, url_param_value,
                    announcement_id, collection_count
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, 1
                )
                ON DUPLICATE KEY UPDATE
                    collection_count = collection_count + 1,
                    last_collected_at = CURRENT_TIMESTAMP,
                    announcement_id = COALESCE(VALUES(announcement_id), announcement_id)
            """

            self.cursor.execute(query, (
                site_code,
                url_key,
                origin_url,
                components['domain'],
                components['param_type'],
                components['param_value'],
                announcement_id
            ))

            if auto_commit:
                self.conn.commit()

            # 등록 후 정보 조회
            self.cursor.execute(check_query, (site_code, url_key))
            result = self.cursor.fetchone()

            return {
                'is_duplicate': is_duplicate,
                'url_key': url_key,
                'registry_id': result['id'] if result else None,
                'collection_count': result['collection_count'] if result else 1
            }

        except Exception as e:
            if auto_commit:
                self.conn.rollback()
            return {
                'is_duplicate': False,
                'url_key': url_key,
                'registry_id': None,
                'collection_count': 0,
                'error': str(e)
            }

    def is_url_registered(self, site_code: str, origin_url: str) -> bool:
        """
        URL이 이미 등록되어 있는지 확인

        Args:
            site_code: 사이트 코드
            origin_url: 원본 URL

        Returns:
            bool: 등록되어 있으면 True
        """
        url_key = extract_url_key(origin_url)
        if not url_key:
            return False

        query = """
            SELECT COUNT(*) as count
            FROM url_registry
            WHERE site_code = %s AND url_key = %s
        """
        self.cursor.execute(query, (site_code, url_key))
        result = self.cursor.fetchone()

        return result['count'] > 0 if result else False

    def get_site_statistics(self, site_code: str) -> Dict:
        """
        특정 사이트의 통계 조회

        Args:
            site_code: 사이트 코드

        Returns:
            dict: 통계 정보
        """
        query = """
            SELECT
                COUNT(*) as total_urls,
                COUNT(DISTINCT url_domain) as unique_domains,
                SUM(collection_count) as total_collections,
                COUNT(CASE WHEN collection_count > 1 THEN 1 END) as duplicate_attempts,
                MIN(first_collected_at) as first_collection,
                MAX(last_collected_at) as last_collection,
                COUNT(CASE WHEN is_active = TRUE THEN 1 END) as active_urls
            FROM url_registry
            WHERE site_code = %s
        """
        self.cursor.execute(query, (site_code,))
        result = self.cursor.fetchone()

        return result if result else {}

    def get_recent_urls(
        self,
        site_code: str,
        limit: int = 10,
        only_new: bool = False
    ) -> List[Dict]:
        """
        최근 등록된 URL 목록 조회

        Args:
            site_code: 사이트 코드
            limit: 조회 개수
            only_new: True면 오늘 등록된 것만

        Returns:
            list: URL 정보 리스트
        """
        date_filter = ""
        if only_new:
            date_filter = "AND DATE(first_collected_at) = CURDATE()"

        query = f"""
            SELECT
                id, url_key, origin_url,
                url_param_type, url_param_value,
                collection_count,
                first_collected_at,
                last_collected_at,
                announcement_id
            FROM url_registry
            WHERE site_code = %s {date_filter}
            ORDER BY first_collected_at DESC
            LIMIT %s
        """
        self.cursor.execute(query, (site_code, limit))

        return self.cursor.fetchall()

    def update_url_status(
        self,
        site_code: str,
        url_key: str,
        is_active: bool,
        status: Optional[str] = None,
        notes: Optional[str] = None
    ) -> bool:
        """
        URL 상태 업데이트

        Args:
            site_code: 사이트 코드
            url_key: URL 키
            is_active: 활성 여부
            status: 상태 메시지
            notes: 비고

        Returns:
            bool: 성공 여부
        """
        try:
            query = """
                UPDATE url_registry
                SET is_active = %s,
                    last_check_status = %s,
                    notes = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE site_code = %s AND url_key = %s
            """
            self.cursor.execute(query, (is_active, status, notes, site_code, url_key))
            self.conn.commit()

            return self.cursor.rowcount > 0

        except Exception as e:
            self.conn.rollback()
            print(f"상태 업데이트 실패: {e}")
            return False

    def _parse_url_key(self, url_key: str) -> Dict:
        """
        url_key를 파싱하여 구성요소 추출

        Args:
            url_key: 'domain|param=value' 형식

        Returns:
            dict: {domain, param_type, param_value}
        """
        if not url_key or '|' not in url_key:
            return {
                'domain': None,
                'param_type': None,
                'param_value': None
            }

        parts = url_key.split('|', 1)
        domain = parts[0]
        param_part = parts[1]

        param_type = None
        param_value = None

        if '=' in param_part:
            param_type, param_value = param_part.split('=', 1)
        else:
            param_type = param_part

        return {
            'domain': domain,
            'param_type': param_type,
            'param_value': param_value
        }

    def close(self):
        """커서 닫기"""
        if self.cursor:
            self.cursor.close()


# 사용 예제
if __name__ == "__main__":
    import mysql.connector
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # DB 연결
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        charset='utf8mb4'
    )

    # Helper 사용
    helper = URLRegistryHelper(conn)

    # 테스트 URL 등록
    test_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-deadline.do?pbancSn=172173"
    result = helper.register_url('kStartUp', test_url, announcement_id=123)

    print("등록 결과:", result)
    print("중복 여부:", result['is_duplicate'])

    # 통계 조회
    stats = helper.get_site_statistics('kStartUp')
    print("\n사이트 통계:", stats)

    # 최근 URL 조회
    recent = helper.get_recent_urls('kStartUp', limit=5)
    print(f"\n최근 URL {len(recent)}개:")
    for url_info in recent:
        print(f"  - {url_info['url_key']} (수집: {url_info['collection_count']}회)")

    helper.close()
    conn.close()
