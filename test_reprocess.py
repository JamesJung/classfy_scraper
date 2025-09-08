#!/usr/bin/env python3

import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.models.announcementDatabase import AnnouncementDatabaseManager

def test_database_connection():
    """데이터베이스 연결 테스트"""
    try:
        db_manager = AnnouncementDatabaseManager()
        
        if db_manager.test_connection():
            print("✅ 데이터베이스 연결 성공")
            
            # 간단한 쿼리 테스트
            with db_manager.SessionLocal() as session:
                from sqlalchemy import text
                result = session.execute(text("SELECT id, folder_name FROM announcement_processing WHERE id = 461"))
                record = result.fetchone()
                
                if record:
                    print(f"✅ 레코드 조회 성공: ID {record[0]}, 폴더명: {record[1]}")
                    return True
                else:
                    print("❌ 레코드 조회 실패: ID 461이 존재하지 않음")
                    return False
        else:
            print("❌ 데이터베이스 연결 실패")
            return False
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return False

if __name__ == "__main__":
    test_database_connection()