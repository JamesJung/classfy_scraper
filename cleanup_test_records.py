#!/usr/bin/env python3
"""
테스트 레코드 정리 스크립트
"""
import pymysql
from dotenv import load_dotenv
import os

# 환경변수 로드
load_dotenv()

def cleanup_test_records():
    """테스트 레코드 삭제"""
    
    try:
        # MySQL 연결
        connection = pymysql.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            charset='utf8mb4'
        )
        
        cursor = connection.cursor()
        
        # 테스트 폴더명 패턴
        test_folders = [
            "강원특별자치도_강릉시_1_2025 경포 썸머 페스티벌 안내",
            "강원특별자치도_강릉시_1_「2025년 강릉시 음식업소 외국어메뉴"
        ]
        
        # 레코드 삭제
        for folder_name in test_folders:
            # PRV 테이블에서 삭제
            cursor.execute(
                "DELETE FROM announcement_prv_processing WHERE folder_name = %s", 
                (folder_name,)
            )
            print(f"PRV 테이블에서 삭제: {folder_name} - {cursor.rowcount}개 레코드")
        
        connection.commit()
        print("테스트 레코드 정리 완료!")
        
    except Exception as e:
        print(f"오류 발생: {e}")
        
    finally:
        if connection:
            connection.close()

if __name__ == "__main__":
    cleanup_test_records()