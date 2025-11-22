#!/usr/bin/env python3
"""
announcement_pre_processing 테이블의 성공 처리된 레코드를 
EXCLUSION_KEYWORDS 테이블과 매칭하여 재처리하는 프로그램
"""

import os
import pymysql
from dotenv import load_dotenv
from datetime import datetime
import re

# .env 파일 로드
load_dotenv()

# 데이터베이스 연결 설정
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")


def get_db_connection():
    """데이터베이스 연결 생성"""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def load_exclusion_keywords(conn):
    """EXCLUSION_KEYWORDS 테이블에서 제외 키워드 목록 로드"""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT KEYWORD as keyword, DESCRIPTION as description
            FROM EXCLUSION_KEYWORDS
            WHERE IS_ACTIVE = 1
            ORDER BY KEYWORD
        """)
        keywords = cursor.fetchall()

    print(f"\n📋 활성화된 제외 키워드: {len(keywords)}개")

    # 키워드 샘플 출력
    if keywords:
        sample = [kw['keyword'] for kw in keywords[:10]]
        print(f"  샘플: {', '.join(sample)}", end='')
        if len(keywords) > 10:
            print(f" 외 {len(keywords) - 10}개", end='')
        print()

    return keywords


def load_successful_records(conn):
    """processing_status가 '성공'인 레코드 로드"""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, title, folder_name, processing_status, exclusion_keyword, exclusion_reason
            FROM announcement_pre_processing
            WHERE processing_status = '성공'
        """)
        records = cursor.fetchall()

    print(f"\n📊 처리 대상 레코드: {len(records)}개 (processing_status = '성공')")
    return records


def check_keyword_match(title, folder_name, keywords):
    """제목 또는 폴더명에 제외 키워드가 포함되어 있는지 확인

    원래 announcement_pre_processor.py의 로직과 동일하게 folder_name을 기준으로 체크하고,
    추가로 title도 체크합니다.
    """
    matched_keywords = []

    # folder_name 체크 (원래 로직)
    if folder_name:
        folder_name_lower = folder_name.lower()
        for keyword_info in keywords:
            keyword = keyword_info['keyword'].lower()
            if keyword in folder_name_lower:
                matched_keywords.append(keyword_info['keyword'])

    # title 체크 (보조)
    if title and not matched_keywords:
        title_lower = title.lower()
        for keyword_info in keywords:
            keyword = keyword_info['keyword'].lower()
            if keyword in title_lower:
                matched_keywords.append(keyword_info['keyword'])

    if matched_keywords:
        reason = f"제외 키워드가 입력되어 있습니다: {', '.join(matched_keywords)}"
        return ', '.join(matched_keywords), reason

    return None, None


def update_record_with_exclusion(conn, record_id, keyword, reason):
    """레코드를 제외 처리로 업데이트"""
    with conn.cursor() as cursor:
        cursor.execute("""
            UPDATE announcement_pre_processing
            SET processing_status = '제외',
                exclusion_keyword = %s,
                exclusion_reason = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (keyword, reason, record_id))
    conn.commit()


def main():
    """메인 실행 함수"""
    print("=" * 80)
    print("공고 제외 키워드 재처리 프로그램")
    print(f"실행 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    conn = get_db_connection()
    
    try:
        # EXCLUSION_KEYWORDS 테이블 로드
        keywords = load_exclusion_keywords(conn)
        
        if not keywords:
            print("\n⚠️ 활성화된 제외 키워드가 없습니다.")
            return
        
        # 성공 처리된 레코드 로드
        records = load_successful_records(conn)
        
        if not records:
            print("\n⚠️ 처리할 레코드가 없습니다.")
            return
        
        # 통계 변수
        updated_count = 0
        skipped_count = 0
        keyword_stats = {}
        
        print("\n처리 시작...")
        print("-" * 80)
        
        # 각 레코드에 대해 키워드 매칭 수행
        for idx, record in enumerate(records, 1):
            title = record['title']
            folder_name = record['folder_name']

            # 진행률 표시 (100개마다)
            if idx % 100 == 0:
                print(f"  진행: {idx}/{len(records)} ({idx*100/len(records):.1f}%)")

            # 키워드 매칭 (folder_name과 title 둘 다 체크)
            matched_keyword, exclusion_reason = check_keyword_match(title, folder_name, keywords)

            if matched_keyword:
                # 제외 처리로 업데이트
                update_record_with_exclusion(
                    conn,
                    record['id'],
                    matched_keyword,
                    exclusion_reason
                )
                updated_count += 1

                # 통계 수집
                for kw in matched_keyword.split(', '):
                    if kw not in keyword_stats:
                        keyword_stats[kw] = 0
                    keyword_stats[kw] += 1

                # 처음 10개는 상세 로그 출력
                if updated_count <= 10:
                    print(f"  [{updated_count}] ID: {record['id']}")
                    print(f"      폴더명: {folder_name[:50] if folder_name else 'N/A'}...")
                    print(f"      제목: {title[:50] if title else 'N/A'}...")
                    print(f"      매칭 키워드: '{matched_keyword}'")
                    print(f"      제외 사유: {exclusion_reason}")
            else:
                skipped_count += 1
        
        # 최종 통계 출력
        print("\n" + "=" * 80)
        print("처리 결과")
        print("=" * 80)
        print(f"✅ 총 처리: {len(records)}개")
        print(f"🔄 제외 처리로 변경: {updated_count}개 ({updated_count*100/len(records):.1f}%)")
        print(f"⭕ 변경 없음: {skipped_count}개 ({skipped_count*100/len(records):.1f}%)")
        
        if keyword_stats:
            print("\n📈 키워드별 매칭 통계 (상위 10개):")
            sorted_stats = sorted(keyword_stats.items(), key=lambda x: x[1], reverse=True)
            for keyword, count in sorted_stats[:10]:
                print(f"  - '{keyword}': {count}건")
            
            if len(sorted_stats) > 10:
                remaining_count = sum(count for _, count in sorted_stats[10:])
                print(f"  - 기타 {len(sorted_stats) - 10}개 키워드: {remaining_count}건")
        
        # 업데이트 후 현재 상태 조회
        print("\n📊 현재 전체 처리 상태:")
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT processing_status, COUNT(*) as count
                FROM announcement_pre_processing
                GROUP BY processing_status
                ORDER BY count DESC
            """)
            status_stats = cursor.fetchall()
            
            total = sum(stat['count'] for stat in status_stats)
            for stat in status_stats:
                percentage = stat['count'] * 100 / total if total > 0 else 0
                print(f"  - {stat['processing_status']}: {stat['count']:,}개 ({percentage:.1f}%)")
    
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        conn.close()
    
    print("\n" + "=" * 80)
    print(f"실행 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


if __name__ == "__main__":
    main()