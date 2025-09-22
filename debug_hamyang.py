#!/usr/bin/env python3

import os
import sys
import mysql.connector
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 1. 함양군 폴더 확인
print("="*80)
print("함양 데이터 디버깅")
print("="*80)

# 오늘 날짜
today = datetime.now().strftime('%Y-%m-%d')
eminwon_path = Path(f'eminwon_data_new/{today}/함양군')

print(f"\n1. 폴더 확인: {eminwon_path}")
if eminwon_path.exists():
    folders = [d for d in eminwon_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
    print(f"   - 공고 폴더 수: {len(folders)}개")
    
    # 최신 5개 폴더명 출력
    print(f"   - 최신 폴더 5개:")
    for folder in sorted(folders)[-5:]:
        # content.md 파일에서 날짜 추출
        content_file = folder / 'content.md'
        date_str = "날짜 없음"
        if content_file.exists():
            with open(content_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if '**작성일**:' in content:
                    lines = content.split('\n')
                    for line in lines:
                        if '**작성일**:' in line:
                            date_str = line.split('**작성일**:')[1].strip()
                            break
        print(f"      - {folder.name[:50]}... [{date_str}]")
else:
    print(f"   ❌ 폴더가 존재하지 않습니다!")
    sys.exit(1)

# 2. .processed 마커 파일 확인
marker_file = eminwon_path / '.processed'
print(f"\n2. 처리 마커 파일 확인: {marker_file}")
if marker_file.exists():
    mtime = datetime.fromtimestamp(marker_file.stat().st_mtime)
    print(f"   - 마커 파일 존재 (수정시간: {mtime})")
    
    # 마커 파일 삭제
    marker_file.unlink()
    print(f"   - 마커 파일 삭제 완료")
else:
    print(f"   - 마커 파일 없음")

# 3. DB 확인
print(f"\n3. DB 데이터 확인")
conn = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    port=int(os.getenv('DB_PORT', '3306')),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)

cursor = conn.cursor()

# site_code가 '함양' 또는 '함양군'인 데이터 확인
for site_code in ['함양', '함양군']:
    cursor.execute("""
        SELECT COUNT(*) as count,
               MAX(created_at) as last_created
        FROM announcement_pre_processing
        WHERE site_code = %s
    """, (site_code,))
    
    result = cursor.fetchone()
    if result and result[0] > 0:
        print(f"   - site_code='{site_code}': {result[0]}개 (최종처리: {result[1]})")

# 오늘 처리된 함양 데이터
cursor.execute("""
    SELECT folder_name, created_at
    FROM announcement_pre_processing
    WHERE (site_code = '함양' OR site_code = '함양군')
    AND DATE(created_at) = CURDATE()
    ORDER BY created_at DESC
    LIMIT 5
""")

results = cursor.fetchall()
if results:
    print(f"\n   오늘 처리된 함양 데이터 (최근 5개):")
    for row in results:
        print(f"      - {row[0][:50]}... ({row[1]})")
else:
    print(f"\n   ⚠️  오늘 처리된 함양 데이터가 없습니다!")

cursor.close()
conn.close()

# 4. 수동 처리 테스트 명령
print(f"\n4. 수동 처리 테스트 명령:")
print("   단일 지역 처리:")
print(f"   python announcement_pre_processor.py -d eminwon_data_new/{today} --site-code 함양 --force")
print("")
print("   배치 처리 (함양만):")
print(f"   rm eminwon_data_new/{today}/함양군/.processed")
print(f"   python eminwon_batch_processor.py --date {today}")
print("")
print("   강제 배치 처리:")
print(f"   python eminwon_batch_processor.py --date {today} --force")

print("\n" + "="*80)