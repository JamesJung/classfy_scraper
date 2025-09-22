#!/usr/bin/env python3

import mysql.connector
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 데이터베이스 연결
conn = mysql.connector.connect(
    host=os.getenv('DB_HOST', '211.37.179.142'),
    port=int(os.getenv('DB_PORT', '3306')),
    user=os.getenv('DB_USER', 'scraper'),
    password=os.getenv('DB_PASSWORD', 'bilink2018#'),
    database=os.getenv('DB_NAME', 'opendata')
)

cursor = conn.cursor()

print("=== 테이블 확인 ===")
# 1. announcement_prv_processing 테이블 (eminwon용)
cursor.execute("""
    SELECT site_code, COUNT(*) as count, 
           MAX(created_at) as last_created,
           MAX(announcement_date) as last_announcement
    FROM announcement_prv_processing
    WHERE site_code LIKE '%함양%'
    GROUP BY site_code
""")
print("\nannouncement_prv_processing 테이블:")
for row in cursor.fetchall():
    print(f"  site_code: {row[0]}, count: {row[1]}, last_created: {row[2]}, last_announcement: {row[3]}")

# 2. announcement_processing 테이블 (일반)
cursor.execute("""
    SELECT site_code, COUNT(*) as count,
           MAX(created_at) as last_created,
           MAX(announcement_date) as last_announcement  
    FROM announcement_processing
    WHERE site_code LIKE '%함양%'
    GROUP BY site_code
""")
print("\nannouncement_processing 테이블:")
for row in cursor.fetchall():
    print(f"  site_code: {row[0]}, count: {row[1]}, last_created: {row[2]}, last_announcement: {row[3]}")

# 3. 오늘 처리된 데이터 확인
cursor.execute("""
    SELECT site_code, COUNT(*) as count
    FROM announcement_prv_processing
    WHERE DATE(created_at) = CURDATE()
    AND site_code LIKE '%함양%'
    GROUP BY site_code
""")
print("\n오늘 처리된 함양 데이터:")
for row in cursor.fetchall():
    print(f"  site_code: {row[0]}, count: {row[1]}")

# 4. 최근 5개 데이터 확인
cursor.execute("""
    SELECT folder_name, announcement_date, created_at
    FROM announcement_prv_processing
    WHERE site_code LIKE '%함양%'
    ORDER BY created_at DESC
    LIMIT 5
""")
print("\n함양군 최근 5개 데이터:")
for row in cursor.fetchall():
    print(f"  folder: {row[0][:50]}, announcement_date: {row[1]}, created_at: {row[2]}")

cursor.close()
conn.close()