#!/usr/bin/env python3
"""
실패한 공고 재시도 스크립트

기능:
1. scraper_failed_announcements 테이블에서 status='pending' 조회
2. unified_detail_scraper.js로 각 공고 재시도
3. 성공 시 status='success' 업데이트
4. 실패 시 retry_count++, 3회 초과 시 status='permanent_failure'

사용법:
    python3 retry_failed_announcements.py                  # 오늘 실패 공고 재시도
    python3 retry_failed_announcements.py --site andong    # 특정 사이트만
    python3 retry_failed_announcements.py --date 2025-01-19  # 특정 날짜
    python3 retry_failed_announcements.py --limit 10       # 최대 10개만
"""

import os
import sys
import subprocess
import time
import pymysql
from dotenv import load_dotenv
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import logging

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

NODE_DIR = Path(__file__).parent / "node"
SCRAPER_SCRIPT = NODE_DIR / "scraper" / "unified_detail_scraper.js"
OUTPUT_BASE_DIR = Path(__file__).parent / "retry_failed_output"


def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_failed_announcements(site_code=None, batch_date=None, limit=None):
    """실패한 공고 목록 조회"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 기본: 오늘 날짜
            if not batch_date:
                batch_date = datetime.now().date()

            query = """
                SELECT id, batch_date, site_code, announcement_title,
                       announcement_url, detail_url, error_type,
                       error_message, retry_count
                FROM scraper_failed_announcements
                WHERE batch_date = %s
                  AND status = 'pending'
                  AND retry_count < 3
            """
            params = [batch_date]

            if site_code:
                query += " AND site_code = %s"
                params.append(site_code)

            query += " ORDER BY created_at ASC"

            if limit:
                query += " LIMIT %s"
                params.append(limit)

            cursor.execute(query, params)
            return cursor.fetchall()
    finally:
        conn.close()


def update_retry_status(announcement_id, status, retry_count=None, error_message=None):
    """재시도 상태 업데이트"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if status == 'success':
                cursor.execute(
                    """
                    UPDATE scraper_failed_announcements
                    SET status = %s, last_retry_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (status, announcement_id)
                )
            elif status == 'permanent_failure':
                cursor.execute(
                    """
                    UPDATE scraper_failed_announcements
                    SET status = %s, retry_count = %s,
                        error_message = %s,
                        last_retry_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (status, retry_count, error_message, announcement_id)
                )
            else:
                # pending 유지, retry_count 증가
                cursor.execute(
                    """
                    UPDATE scraper_failed_announcements
                    SET retry_count = %s, error_message = %s,
                        last_retry_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (retry_count, error_message, announcement_id)
                )
            conn.commit()
    finally:
        conn.close()


def retry_single_announcement(announcement):
    """단일 공고 재시도"""
    site_code = announcement['site_code']
    url = announcement['detail_url'] or announcement['announcement_url']
    title = announcement['announcement_title'] or 'Unknown'

    if not url:
        print(f"  ✗ URL 없음: {site_code} - {title}")
        return False

    # 출력 디렉토리
    today_str = datetime.now().strftime('%Y-%m-%d')
    output_dir = OUTPUT_BASE_DIR / today_str / site_code
    output_dir.mkdir(parents=True, exist_ok=True)

    # 폴더 이름 생성 (타임스탬프 기반)
    folder_name = f"{int(time.time())}_{title[:30]}"

    # unified_detail_scraper.js 실행
    cmd = [
        "node",
        str(SCRAPER_SCRIPT),
        "--site", site_code,
        "--url", url,
        "--outputDir", str(output_dir),
        "--folderName", folder_name,
        "--title", title
    ]

    try:
        print(f"  [재시도] {site_code} - {title[:50]}...")
        result = subprocess.run(
            cmd,
            cwd=str(NODE_DIR),
            capture_output=True,
            text=True,
            timeout=120  # 2분 타임아웃
        )

        if result.returncode == 0:
            print(f"  ✓ 성공: {site_code}")
            return True
        else:
            error_msg = result.stderr[:200] if result.stderr else result.stdout[:200]
            print(f"  ✗ 실패: {site_code} - {error_msg}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  ⏰ 타임아웃: {site_code}")
        return False
    except Exception as e:
        print(f"  ✗ 에러: {site_code} - {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(description='실패한 공고 재시도')
    parser.add_argument('--site', type=str, help='특정 사이트 코드만 재시도')
    parser.add_argument('--date', type=str, help='특정 날짜 (YYYY-MM-DD)')
    parser.add_argument('--limit', type=int, help='최대 재시도 개수')
    parser.add_argument('--verbose', '-v', action='store_true', help='상세 로그')
    args = parser.parse_args()

    # 로깅 설정
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("  실패한 공고 재시도 시작")
    print("=" * 80)
    print(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.site:
        print(f"대상 사이트: {args.site}")
    if args.date:
        print(f"대상 날짜: {args.date}")
    if args.limit:
        print(f"최대 개수: {args.limit}개")
    print("=" * 80)
    print()

    # 재시도 대상 조회
    batch_date = args.date if args.date else None
    failed_announcements = get_failed_announcements(
        site_code=args.site,
        batch_date=batch_date,
        limit=args.limit
    )

    if not failed_announcements:
        print("재시도할 실패 공고가 없습니다.")
        return

    print(f"총 {len(failed_announcements)}개 재시도 대상\n")

    stats = {"success": 0, "failed": 0, "permanent_failure": 0}

    for idx, announcement in enumerate(failed_announcements, 1):
        announcement_id = announcement['id']
        current_retry_count = announcement['retry_count']
        new_retry_count = current_retry_count + 1

        print(f"[{idx}/{len(failed_announcements)}] (재시도 {new_retry_count}/3)")

        # 재시도 실행
        success = retry_single_announcement(announcement)

        # 상태 업데이트
        if success:
            update_retry_status(announcement_id, 'success')
            stats['success'] += 1
        elif new_retry_count >= 3:
            # 3회 실패 시 영구 실패 처리
            update_retry_status(
                announcement_id,
                'permanent_failure',
                retry_count=new_retry_count,
                error_message=f"재시도 3회 초과"
            )
            stats['permanent_failure'] += 1
            print(f"  ⚠ 영구 실패 처리: {announcement['site_code']}")
        else:
            # 재시도 카운트 증가
            update_retry_status(
                announcement_id,
                'pending',
                retry_count=new_retry_count,
                error_message=f"재시도 {new_retry_count}회 실패"
            )
            stats['failed'] += 1

        # 다음 재시도 전 잠시 대기
        time.sleep(2)

    # 요약
    print("\n" + "=" * 80)
    print("  재시도 완료")
    print("=" * 80)
    print(f"성공: {stats['success']}개")
    print(f"실패 (재시도 예정): {stats['failed']}개")
    print(f"영구 실패: {stats['permanent_failure']}개")
    print("=" * 80)


if __name__ == "__main__":
    main()
