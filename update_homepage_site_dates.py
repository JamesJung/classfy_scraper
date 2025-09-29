#!/usr/bin/env python3
import os
import sys
import pymysql
from dotenv import load_dotenv
from datetime import datetime, date

load_dotenv()

DB_HOST = os.getenv('DB_HOST')
DB_PORT = int(os.getenv('DB_PORT', 3306))
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def create_table():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS homepage_site_announcement_date (
                    site_code VARCHAR(50) PRIMARY KEY,
                    latest_announcement_date DATE NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_date (latest_announcement_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
            print("✓ homepage_site_announcement_date 테이블 생성/확인 완료")
    finally:
        conn.close()

def get_latest_dates():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    site_code,
                    MAX(
                        CASE 
                            WHEN announcement_date REGEXP '^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$' 
                            THEN STR_TO_DATE(announcement_date, '%Y-%m-%d')
                            WHEN announcement_date LIKE '** %'
                            THEN STR_TO_DATE(SUBSTRING(announcement_date, 4), '%Y-%m-%d')
                            ELSE NULL
                        END
                    ) as latest_date
                FROM announcement_pre_processing
                WHERE site_type = 'Homepage'
                    AND announcement_date IS NOT NULL
                    AND announcement_date != ''
                GROUP BY site_code
                HAVING latest_date IS NOT NULL
                ORDER BY site_code
            """)
            results = cursor.fetchall()
            print(f"\n✓ site_type='Homepage'인 레코드에서 {len(results)}개 site_code 발견")
            return results
    finally:
        conn.close()

def update_homepage_dates(latest_dates):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE homepage_site_announcement_date")
            
            inserted = 0
            skipped = 0
            for row in latest_dates:
                try:
                    latest_date = row['latest_date']
                    if latest_date and (isinstance(latest_date, (datetime, date))):
                        if isinstance(latest_date, datetime):
                            date_val = latest_date.date()
                        else:
                            date_val = latest_date
                        cursor.execute("""
                            INSERT INTO homepage_site_announcement_date 
                            (site_code, latest_announcement_date)
                            VALUES (%s, %s)
                        """, (row['site_code'], date_val))
                        inserted += 1
                    else:
                        print(f"  ⚠ {row['site_code']}: 잘못된 날짜 형식 - {latest_date} (타입: {type(latest_date).__name__})")
                        skipped += 1
                except Exception as e:
                    print(f"  ⚠ {row['site_code']}: 오류 - {e}")
                    skipped += 1
            
            conn.commit()
            print(f"✓ {inserted}개 저장 완료, {skipped}개 스킵")
            
            print("\n=== 저장된 데이터 샘플 (최근 10개) ===")
            cursor.execute("""
                SELECT site_code, latest_announcement_date 
                FROM homepage_site_announcement_date 
                ORDER BY latest_announcement_date DESC 
                LIMIT 10
            """)
            for row in cursor.fetchall():
                print(f"  {row['site_code']}: {row['latest_announcement_date']}")
    finally:
        conn.close()

def main():
    print("=" * 60)
    print("홈페이지 고시/공고 최신 날짜 업데이트")
    print("=" * 60)
    
    create_table()
    latest_dates = get_latest_dates()
    
    if not latest_dates:
        print("\n⚠ site_type='Homepage'인 데이터가 없습니다.")
        sys.exit(0)
    
    update_homepage_dates(latest_dates)
    
    print("\n" + "=" * 60)
    print("완료!")
    print("=" * 60)

if __name__ == "__main__":
    main()