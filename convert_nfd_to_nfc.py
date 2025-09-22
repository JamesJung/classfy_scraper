#!/usr/bin/env python3
"""
기존 NFD 형태로 저장된 데이터를 NFC(일반 한글)로 변환
"""

import mysql.connector
import unicodedata
import os
from dotenv import load_dotenv

load_dotenv()

def convert_nfd_to_nfc():
    # Database configuration
    db_config = {
        'host': os.environ.get('DB_HOST'),
        'user': os.environ.get('DB_USER'),
        'password': os.environ.get('DB_PASSWORD'),
        'database': os.environ.get('DB_NAME'),
        'port': int(os.environ.get('DB_PORT')),
        'charset': 'utf8mb4',
        'collation': 'utf8mb4_unicode_ci'
    }
    
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    
    try:
        # 먼저 현재 상태 확인
        print("현재 데이터베이스 상태 확인...")
        cursor.execute("SELECT COUNT(*) FROM eminwon_url_registry")
        total_count = cursor.fetchone()[0]
        print(f"전체 레코드 수: {total_count}")
        
        # NFD 형태 데이터 확인
        cursor.execute("""
            SELECT DISTINCT region 
            FROM eminwon_url_registry 
            WHERE LENGTH(region) != CHAR_LENGTH(region)
            LIMIT 10
        """)
        nfd_regions = cursor.fetchall()
        
        if nfd_regions:
            print(f"\nNFD 형태로 저장된 지역 예시: {nfd_regions[:5]}")
        
        # 모든 레코드를 가져와서 NFC로 변환
        print("\n데이터 변환 시작...")
        cursor.execute("""
            SELECT id, region, folder_name, title 
            FROM eminwon_url_registry
        """)
        
        all_records = cursor.fetchall()
        update_count = 0
        
        for record_id, region, folder_name, title in all_records:
            # NFC로 정규화
            nfc_region = unicodedata.normalize("NFC", region) if region else region
            nfc_folder_name = unicodedata.normalize("NFC", folder_name) if folder_name else folder_name
            nfc_title = unicodedata.normalize("NFC", title) if title else title
            
            # 변경이 필요한 경우에만 업데이트
            if region != nfc_region or folder_name != nfc_folder_name or title != nfc_title:
                cursor.execute("""
                    UPDATE eminwon_url_registry 
                    SET region = %s, folder_name = %s, title = %s
                    WHERE id = %s
                """, (nfc_region, nfc_folder_name, nfc_title, record_id))
                update_count += 1
                
                if update_count % 100 == 0:
                    print(f"  {update_count}개 레코드 변환 완료...")
        
        conn.commit()
        print(f"\n✅ 총 {update_count}개 레코드를 NFC로 변환했습니다.")
        
        # 변환 후 확인
        print("\n변환 후 확인...")
        
        # 증평 데이터 확인
        cursor.execute("SELECT COUNT(*) FROM eminwon_url_registry WHERE region = '증평'")
        jeungpyeong_count = cursor.fetchone()[0]
        print(f"증평 레코드 수: {jeungpyeong_count}")
        
        # 샘플 데이터 확인
        cursor.execute("""
            SELECT region, COUNT(*) as cnt 
            FROM eminwon_url_registry 
            WHERE region LIKE '증%'
            GROUP BY region
        """)
        sample_regions = cursor.fetchall()
        if sample_regions:
            print("\n'증'으로 시작하는 지역:")
            for region, cnt in sample_regions:
                print(f"  {region}: {cnt}개")
        
    except Exception as e:
        print(f"오류 발생: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    convert_nfd_to_nfc()