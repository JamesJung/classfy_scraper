#!/usr/bin/env python3

import mysql.connector
import os
from dotenv import load_dotenv
from datetime import datetime

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

print(f"\n{'='*80}")
print(f"오늘({datetime.now().strftime('%Y-%m-%d')}) 처리된 데이터 확인")
print(f"{'='*80}\n")

# 1. 전체 요약
cursor.execute("""
    SELECT 
        COUNT(DISTINCT site_code) as total_regions,
        COUNT(*) as total_announcements,
        MIN(created_at) as start_time,
        MAX(created_at) as end_time
    FROM announcement_pre_processing
    WHERE DATE(created_at) = CURDATE()
""")
result = cursor.fetchone()
if result and result[1] > 0:
    print(f"📊 전체 요약:")
    print(f"  - 처리 지역: {result[0]}개")
    print(f"  - 전체 공고: {result[1]:,}개")
    print(f"  - 시작 시간: {result[2]}")
    print(f"  - 종료 시간: {result[3]}")
    if result[2] and result[3]:
        duration = (result[3] - result[2]).total_seconds() / 60
        print(f"  - 소요 시간: {duration:.1f}분")
else:
    print("오늘 처리된 데이터가 없습니다.")

# 2. 지역별 통계 (상위 10개)
print(f"\n📈 지역별 공고 수 (상위 10개):")
cursor.execute("""
    SELECT 
        site_code,
        COUNT(*) as count
    FROM announcement_pre_processing
    WHERE DATE(created_at) = CURDATE()
    GROUP BY site_code
    ORDER BY count DESC
    LIMIT 10
""")
for row in cursor.fetchall():
    print(f"  {row[0]:15} : {row[1]:4}개")

# 3. 지원사업 통계 (컬럼이 있는 경우만)
print(f"\n💰 처리 상태별 통계:")

# 4. 처리 상태
print(f"\n🔍 처리 상태:")
cursor.execute("""
    SELECT 
        processing_status,
        COUNT(*) as count
    FROM announcement_pre_processing
    WHERE DATE(created_at) = CURDATE()
    GROUP BY processing_status
""")
for row in cursor.fetchall():
    status = row[0] if row[0] else 'NULL'
    print(f"  - {status}: {row[1]:,}개")

# 5. 최근 처리 항목
print(f"\n📝 최근 처리 항목 (5개):")
cursor.execute("""
    SELECT 
        site_code,
        SUBSTRING(folder_name, 1, 50) as folder,
        created_at
    FROM announcement_pre_processing
    WHERE DATE(created_at) = CURDATE()
    ORDER BY created_at DESC
    LIMIT 5
""")
for row in cursor.fetchall():
    print(f"  [{row[0]}] {row[1]}... - {row[2]}")

print(f"\n{'='*80}\n")

cursor.close()
conn.close()