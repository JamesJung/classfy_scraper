"""
URL 레지스트리 관리자
===================

목적:
- 스크래핑 URL 등록 및 추적
- API URL 중복 제거 (스크래핑 데이터 우선)
- 최종 URL 레지스트리 통합 관리

특징:
- DomainKeyExtractor 통합 (도메인별 키 추출)
- 스크래핑 우선순위 보장
- 자동 Hash 생성 및 중복 검사
- 트랜잭션 안전성
"""

import json
from typing import Optional, Dict, List, Tuple
from datetime import datetime
import mysql.connector
from mysql.connector import pooling

from .domainKeyExtractor import DomainKeyExtractor


class UrlRegistryManager:
    """URL 레지스트리 통합 관리자"""

    def __init__(self, db_connection_pool=None, db_config=None):
        """
        Args:
            db_connection_pool: MySQL connection pool
            db_config: DB 설정 딕셔너리
        """
        self.pool = db_connection_pool
        self.db_config = db_config

        # DomainKeyExtractor 초기화
        self.key_extractor = DomainKeyExtractor(
            db_connection_pool=db_connection_pool,
            db_config=db_config
        )

    def _get_connection(self):
        """DB 연결 획득"""
        if self.pool:
            return self.pool.get_connection()
        elif self.db_config:
            return mysql.connector.connect(**self.db_config)
        else:
            raise ValueError("DB connection pool or config required")

    # =====================================================
    # 스크래핑 URL 관리
    # =====================================================

    def register_scraped_url(
        self,
        url: str,
        site_code: str,
        announcement_id: Optional[int] = None,
        processing_status: str = 'pending'
    ) -> Dict:
        """
        스크래핑 URL 등록

        Args:
            url: 전체 URL
            site_code: 사이트 코드
            announcement_id: 공고 ID (처리 완료시)
            processing_status: 처리 상태

        Returns:
            {
                'is_new': True/False,
                'registry_id': int,
                'url_key': str,
                'collection_count': int
            }
        """
        # URL 키 추출
        url_key = self.key_extractor.extract_url_key(url, site_code)
        if not url_key:
            raise ValueError(f"URL 키 추출 실패: {url}")

        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            # INSERT ... ON DUPLICATE KEY UPDATE
            cursor.execute("""
                INSERT INTO scraped_url_registry (
                    site_code, url_key, origin_url,
                    processing_status, announcement_id
                ) VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    collection_count = collection_count + 1,
                    last_collected_at = CURRENT_TIMESTAMP,
                    processing_status = VALUES(processing_status),
                    announcement_id = COALESCE(VALUES(announcement_id), announcement_id)
            """, (site_code, url_key, url, processing_status, announcement_id))

            is_new = cursor.rowcount == 1

            # 등록된 레코드 조회
            cursor.execute("""
                SELECT id, collection_count
                FROM scraped_url_registry
                WHERE site_code = %s AND url_key_hash = MD5(%s)
            """, (site_code, url_key))

            result = cursor.fetchone()
            conn.commit()

            return {
                'is_new': is_new,
                'registry_id': result['id'],
                'url_key': url_key,
                'collection_count': result['collection_count']
            }

        except Exception as e:
            conn.rollback()
            raise Exception(f"스크래핑 URL 등록 실패: {e}")
        finally:
            cursor.close()
            conn.close()

    def update_scraped_status(
        self,
        url_key: str,
        site_code: str,
        status: str,
        announcement_id: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """
        스크래핑 URL 상태 업데이트

        Args:
            url_key: URL 키
            site_code: 사이트 코드
            status: 'processing', 'completed', 'failed'
            announcement_id: 공고 ID (완료시)
            error_message: 오류 메시지 (실패시)

        Returns:
            성공 여부
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if status == 'completed':
                cursor.execute("""
                    UPDATE scraped_url_registry
                    SET processing_status = 'completed',
                        announcement_id = %s,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE url_key_hash = MD5(%s)
                      AND site_code = %s
                """, (announcement_id, url_key, site_code))

            elif status == 'failed':
                cursor.execute("""
                    UPDATE scraped_url_registry
                    SET processing_status = 'failed',
                        retry_count = retry_count + 1,
                        last_error = %s
                    WHERE url_key_hash = MD5(%s)
                      AND site_code = %s
                """, (error_message, url_key, site_code))

            elif status == 'processing':
                cursor.execute("""
                    UPDATE scraped_url_registry
                    SET processing_status = 'processing',
                        retry_count = retry_count + 1
                    WHERE url_key_hash = MD5(%s)
                      AND site_code = %s
                """, (url_key, site_code))

            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            conn.rollback()
            raise Exception(f"상태 업데이트 실패: {e}")
        finally:
            cursor.close()
            conn.close()

    def get_pending_scraped_urls(
        self,
        site_code: str,
        limit: int = 100
    ) -> List[Dict]:
        """
        대기중인 스크래핑 URL 조회

        Args:
            site_code: 사이트 코드
            limit: 최대 개수

        Returns:
            [{'id', 'url_key', 'origin_url', 'retry_count'}, ...]
        """
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT id, url_key, origin_url, retry_count
                FROM scraped_url_registry
                WHERE site_code = %s
                  AND processing_status = 'pending'
                ORDER BY first_collected_at
                LIMIT %s
            """, (site_code, limit))

            return cursor.fetchall()

        finally:
            cursor.close()
            conn.close()

    # =====================================================
    # API URL 중복 제거
    # =====================================================

    def receive_api_urls(
        self,
        api_data_list: List[Dict],
        api_source: str,
        api_batch_id: str
    ) -> int:
        """
        API URL 일괄 수신 (임시 저장)

        Args:
            api_data_list: [{'url': str, 'raw_data': dict}, ...]
            api_source: API 출처
            api_batch_id: 배치 ID

        Returns:
            수신 개수
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            inserted_count = 0

            for api_data in api_data_list:
                url = api_data['url']
                raw_data = api_data.get('raw_data', {})

                # URL 키 추출
                url_key = self.key_extractor.extract_url_key(url)
                if not url_key:
                    print(f"⚠️  URL 키 추출 실패 (건너뜀): {url}")
                    continue

                # API 버퍼에 저장
                cursor.execute("""
                    INSERT INTO api_url_buffer (
                        url_key, origin_url, api_source,
                        api_batch_id, api_raw_data
                    ) VALUES (%s, %s, %s, %s, %s)
                """, (
                    url_key, url,
                    api_source, api_batch_id,
                    json.dumps(raw_data, ensure_ascii=False)
                ))

                inserted_count += 1

            conn.commit()
            print(f"✅ API 데이터 {inserted_count}개 수신 완료")
            return inserted_count

        except Exception as e:
            conn.rollback()
            raise Exception(f"API URL 수신 실패: {e}")
        finally:
            cursor.close()
            conn.close()

    def deduplicate_api_urls(self, api_batch_id: str) -> Dict:
        """
        API URL 중복 제거 (스크래핑 데이터 우선!)

        Args:
            api_batch_id: API 배치 ID

        Returns:
            {
                'total': int,
                'duplicate': int,
                'unique': int,
                'scraped_pending': int
            }
        """
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            # 최적화된 단일 쿼리로 중복 검사
            cursor.execute("""
                SELECT
                    a.id as api_id,
                    a.url_key_hash,
                    a.url_key,
                    s.id as scraped_id,
                    s.processing_status
                FROM api_url_buffer a
                LEFT JOIN scraped_url_registry s
                    ON a.url_key_hash = s.url_key_hash
                WHERE a.api_batch_id = %s
                  AND a.dedup_status = 'pending'
            """, (api_batch_id,))

            api_urls = cursor.fetchall()

            stats = {
                'total': len(api_urls),
                'duplicate': 0,
                'unique': 0,
                'scraped_pending': 0
            }

            for api_url in api_urls:
                if api_url['scraped_id']:
                    # 스크래핑 데이터 존재!
                    if api_url['processing_status'] == 'completed':
                        # 완료 → API 버림!
                        cursor.execute("""
                            UPDATE api_url_buffer
                            SET dedup_status = 'duplicate',
                                scraped_url_id = %s,
                                dedup_checked_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (api_url['scraped_id'], api_url['api_id']))
                        stats['duplicate'] += 1

                    else:
                        # 진행중 → API 대기
                        cursor.execute("""
                            UPDATE api_url_buffer
                            SET dedup_status = 'scraped_pending',
                                scraped_url_id = %s,
                                dedup_checked_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (api_url['scraped_id'], api_url['api_id']))
                        stats['scraped_pending'] += 1

                else:
                    # 스크래핑 없음 → API 유효!
                    cursor.execute("""
                        UPDATE api_url_buffer
                        SET dedup_status = 'unique',
                            dedup_checked_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (api_url['api_id'],))
                    stats['unique'] += 1

            conn.commit()

            print(f"\n중복 제거 완료:")
            print(f"  - 전체: {stats['total']}개")
            print(f"  - 중복 (버림): {stats['duplicate']}개")
            print(f"  - 대기: {stats['scraped_pending']}개")
            print(f"  - 신규: {stats['unique']}개")

            return stats

        except Exception as e:
            conn.rollback()
            raise Exception(f"중복 제거 실패: {e}")
        finally:
            cursor.close()
            conn.close()

    def get_unique_api_urls(
        self,
        api_batch_id: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        신규 API URL 조회 (스크래핑 안 된 것만)

        Args:
            api_batch_id: API 배치 ID
            limit: 최대 개수

        Returns:
            [{'id', 'url_key', 'origin_url', 'api_raw_data'}, ...]
        """
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            query = """
                SELECT id, url_key, origin_url, api_raw_data
                FROM api_url_buffer
                WHERE api_batch_id = %s
                  AND dedup_status = 'unique'
                ORDER BY received_at
            """

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query, (api_batch_id,))
            return cursor.fetchall()

        finally:
            cursor.close()
            conn.close()

    def mark_api_url_processed(
        self,
        api_url_id: int,
        announcement_id: int
    ) -> bool:
        """
        API URL 처리 완료 표시

        Args:
            api_url_id: api_url_buffer.id
            announcement_id: 생성된 공고 ID

        Returns:
            성공 여부
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE api_url_buffer
                SET processed_at = CURRENT_TIMESTAMP,
                    announcement_id = %s
                WHERE id = %s
            """, (announcement_id, api_url_id))

            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            conn.rollback()
            raise Exception(f"API URL 처리 완료 표시 실패: {e}")
        finally:
            cursor.close()
            conn.close()

    # =====================================================
    # 최종 레지스트리 관리
    # =====================================================

    def register_to_final(
        self,
        url_key: str,
        origin_url: str,
        data_source: str,
        announcement_id: int,
        site_code: str,
        scraped_url_id: Optional[int] = None,
        api_url_id: Optional[int] = None
    ) -> Optional[int]:
        """
        최종 레지스트리에 등록

        Args:
            url_key: URL 키
            origin_url: 원본 URL
            data_source: 'scraper' or 'api'
            announcement_id: 공고 ID
            site_code: 사이트 코드
            scraped_url_id: scraped_url_registry.id
            api_url_id: api_url_buffer.id

        Returns:
            final_url_registry.id or None (중복시)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT IGNORE INTO final_url_registry (
                    url_key, origin_url, data_source,
                    announcement_id, site_code,
                    scraped_url_id, api_url_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                url_key, origin_url, data_source,
                announcement_id, site_code,
                scraped_url_id, api_url_id
            ))

            conn.commit()

            if cursor.rowcount > 0:
                return cursor.lastrowid
            else:
                return None  # 중복

        except Exception as e:
            conn.rollback()
            raise Exception(f"최종 레지스트리 등록 실패: {e}")
        finally:
            cursor.close()
            conn.close()

    def migrate_scraped_to_final(self, site_code: Optional[str] = None) -> int:
        """
        완료된 스크래핑 데이터를 최종 레지스트리로 이관

        Args:
            site_code: 특정 사이트만 (선택)

        Returns:
            이관 개수
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if site_code:
                cursor.execute("""
                    INSERT IGNORE INTO final_url_registry (
                        url_key, origin_url, data_source,
                        scraped_url_id, announcement_id, site_code
                    )
                    SELECT
                        s.url_key, s.origin_url, 'scraper',
                        s.id, s.announcement_id, s.site_code
                    FROM scraped_url_registry s
                    WHERE s.processing_status = 'completed'
                      AND s.announcement_id IS NOT NULL
                      AND s.site_code = %s
                """, (site_code,))
            else:
                cursor.execute("""
                    INSERT IGNORE INTO final_url_registry (
                        url_key, origin_url, data_source,
                        scraped_url_id, announcement_id, site_code
                    )
                    SELECT
                        s.url_key, s.origin_url, 'scraper',
                        s.id, s.announcement_id, s.site_code
                    FROM scraped_url_registry s
                    WHERE s.processing_status = 'completed'
                      AND s.announcement_id IS NOT NULL
                """)

            migrated_count = cursor.rowcount
            conn.commit()

            print(f"✅ 스크래핑 데이터 {migrated_count}개 이관 완료")
            return migrated_count

        except Exception as e:
            conn.rollback()
            raise Exception(f"스크래핑 데이터 이관 실패: {e}")
        finally:
            cursor.close()
            conn.close()

    # =====================================================
    # 통계 및 조회
    # =====================================================

    def get_stats(self) -> Dict:
        """전체 통계 조회"""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            stats = {}

            # 스크래핑 통계
            cursor.execute("""
                SELECT
                    processing_status,
                    COUNT(*) as count
                FROM scraped_url_registry
                GROUP BY processing_status
            """)
            stats['scraped'] = {row['processing_status']: row['count'] for row in cursor.fetchall()}

            # API 통계
            cursor.execute("""
                SELECT
                    dedup_status,
                    COUNT(*) as count
                FROM api_url_buffer
                GROUP BY dedup_status
            """)
            stats['api'] = {row['dedup_status']: row['count'] for row in cursor.fetchall()}

            # 최종 통계
            cursor.execute("""
                SELECT
                    data_source,
                    COUNT(*) as count
                FROM final_url_registry
                GROUP BY data_source
            """)
            stats['final'] = {row['data_source']: row['count'] for row in cursor.fetchall()}

            return stats

        finally:
            cursor.close()
            conn.close()


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

    # 관리자 초기화
    manager = UrlRegistryManager(db_config=db_config)

    # 1. 스크래핑 URL 등록
    result = manager.register_scraped_url(
        url="https://www.k-startup.go.kr/web/contents/bizpbanc-deadline.do?pbancSn=172173",
        site_code="kStartUp",
        processing_status="pending"
    )
    print(f"스크래핑 등록: {result}")

    # 2. API 데이터 수신
    api_data = [
        {
            'url': "https://www.bizinfo.go.kr/web/lay1/program/S1T294C295/business/retrieveBusinessDetail.do?bltSeq=1234567",
            'raw_data': {'title': '지원사업', 'content': '...'}
        }
    ]
    manager.receive_api_urls(api_data, "bizInfo", "batch_20251019_120000")

    # 3. 중복 제거
    dedup_stats = manager.deduplicate_api_urls("batch_20251019_120000")
    print(f"중복 제거: {dedup_stats}")

    # 4. 전체 통계
    stats = manager.get_stats()
    print(f"전체 통계: {stats}")
