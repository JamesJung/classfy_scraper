#!/usr/bin/env python3
"""
NFD를 NFC로 변환 - 배치 업데이트 방식
"""

import mysql.connector
import unicodedata
import os
from dotenv import load_dotenv

load_dotenv()

def convert_nfd_to_nfc_batch():
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
        print("NFD → NFC 변환 시작...")
        
        # 먼저 증평 데이터만 테스트
        print("\n1. 증평 데이터 변환 중...")
        
        # NFD 형태의 증평을 찾아서 NFC로 변환
        nfd_jeungpyeong = unicodedata.normalize("NFD", "증평")
        nfc_jeungpyeong = "증평"
        
        cursor.execute("""
            UPDATE eminwon_url_registry 
            SET region = %s
            WHERE region = %s
        """, (nfc_jeungpyeong, nfd_jeungpyeong))
        
        jeungpyeong_updated = cursor.rowcount
        print(f"  증평: {jeungpyeong_updated}개 레코드 변환")
        
        # 다른 주요 지역들도 변환
        regions_to_convert = [
            "부산북", "안산", "연수", "연천", "의왕", "장수", "청양",
            "청주", "수원", "가평", "남양주", "기장"
        ]
        
        print("\n2. 다른 지역 데이터 변환 중...")
        total_updated = jeungpyeong_updated
        
        for region_name in regions_to_convert:
            nfd_region = unicodedata.normalize("NFD", region_name)
            nfc_region = region_name
            
            cursor.execute("""
                UPDATE eminwon_url_registry 
                SET region = %s
                WHERE region = %s
            """, (nfc_region, nfd_region))
            
            if cursor.rowcount > 0:
                print(f"  {region_name}: {cursor.rowcount}개 레코드 변환")
                total_updated += cursor.rowcount
        
        # folder_name과 title도 변환 (증평 데이터만 우선)
        print("\n3. folder_name과 title 변환 중 (증평)...")
        
        cursor.execute("""
            SELECT id, folder_name, title 
            FROM eminwon_url_registry 
            WHERE region = '증평'
        """)
        
        records = cursor.fetchall()
        for record_id, folder_name, title in records:
            nfc_folder = unicodedata.normalize("NFC", folder_name) if folder_name else folder_name
            nfc_title = unicodedata.normalize("NFC", title) if title else title
            
            if folder_name != nfc_folder or title != nfc_title:
                cursor.execute("""
                    UPDATE eminwon_url_registry 
                    SET folder_name = %s, title = %s
                    WHERE id = %s
                """, (nfc_folder, nfc_title, record_id))
        
        conn.commit()
        
        print(f"\n✅ 총 {total_updated}개 region 레코드를 NFC로 변환했습니다.")
        
        # 변환 결과 확인
        print("\n변환 결과 확인:")
        cursor.execute("SELECT COUNT(*) FROM eminwon_url_registry WHERE region = '증평'")
        count = cursor.fetchone()[0]
        print(f"  증평 (NFC): {count}개")
        
        # NFD로 한번 더 체크
        cursor.execute("SELECT COUNT(*) FROM eminwon_url_registry WHERE region = %s", 
                      (unicodedata.normalize("NFD", "증평"),))
        nfd_count = cursor.fetchone()[0]
        print(f"  증평 (NFD 남은 것): {nfd_count}개")
        
    except Exception as e:
        print(f"오류 발생: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    convert_nfd_to_nfc_batch()