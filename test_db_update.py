#!/usr/bin/env python3
"""
DB 업데이트 로직 테스트 스크립트
스크래핑 후 DB가 업데이트되지 않는 문제를 디버깅하기 위한 도구
"""

import os
import sys
from pathlib import Path
import pymysql
from dotenv import load_dotenv
from datetime import datetime
import re

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")


def get_latest_date_from_scraped_files(site_code, output_dir):
    """스크래핑된 파일에서 최신 날짜를 가져옵니다."""
    output_path = Path(output_dir)
    if not output_path.exists():
        print(f"❌ 디렉토리가 존재하지 않음: {output_dir}")
        return None

    print(f"📂 디렉토리 확인: {output_path}")

    # 001_로 시작하는 첫 번째 폴더 찾기
    first_dir = None
    for item_dir in sorted(output_path.iterdir()):
        if item_dir.is_dir() and item_dir.name.startswith("001_"):
            first_dir = item_dir
            print(f"✅ 001_ 폴더 발견: {first_dir.name}")
            break

    if not first_dir:
        # 001_로 시작하는 폴더가 없으면 첫 번째 디렉토리 사용
        dirs = [d for d in output_path.iterdir() if d.is_dir()]
        if dirs:
            first_dir = sorted(dirs)[0]
            print(f"⚠️ 001_ 폴더가 없어서 첫 번째 폴더 사용: {first_dir.name}")
        else:
            print(f"❌ 하위 디렉토리가 없음")
            return None

    # content.md 파일 읽기
    content_md_path = first_dir / "content.md"
    if not content_md_path.exists():
        print(f"❌ content.md 파일 없음: {content_md_path}")
        return None

    print(f"📄 content.md 파일 읽기: {content_md_path}")

    try:
        with open(content_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 날짜 추출 패턴
        date_patterns = [
            r"\*\*작성일\*\*[:\s]*(.+?)(?:\n|$)",
            r"작성일[:\s]*(.+?)(?:\n|$)",
            r"\*\*등록일\*\*[:\s]*(.+?)(?:\n|$)",
            r"등록일[:\s]*(.+?)(?:\n|$)",
            r"\*\*공고일\*\*[:\s]*(.+?)(?:\n|$)",
            r"공고일[:\s]*(.+?)(?:\n|$)",
        ]

        announcement_date = None
        for pattern in date_patterns:
            date_match = re.search(pattern, content, re.IGNORECASE)
            if date_match:
                announcement_date = date_match.group(1).strip()
                print(f"✅ 날짜 추출 성공: {announcement_date} (패턴: {pattern})")
                break

        if not announcement_date:
            print(f"❌ 날짜 정보를 찾을 수 없음")
            print("content.md 내용 미리보기:")
            print(content[:500])

        return announcement_date

    except Exception as e:
        print(f"❌ 파일 읽기 오류: {e}")
        return None


def test_db_connection():
    """DB 연결 테스트"""
    print("\n" + "=" * 50)
    print("DB 연결 테스트")
    print("=" * 50)
    
    print(f"DB_HOST: {DB_HOST}:{DB_PORT}")
    print(f"DB_NAME: {DB_NAME}")
    print(f"DB_USER: {DB_USER}")
    
    # 네트워크 연결 테스트
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((DB_HOST, DB_PORT))
        sock.close()
        if result == 0:
            print(f"✅ 포트 {DB_PORT}가 열려있음")
        else:
            print(f"❌ 포트 {DB_PORT}에 연결할 수 없음 (에러 코드: {result})")
            return False
    except Exception as e:
        print(f"❌ 네트워크 에러: {e}")
        return False
    
    # DB 연결 테스트
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as cnt FROM homepage_site_announcement_date")
            result = cursor.fetchone()
            print(f"✅ DB 연결 성공: {result['cnt']}개 사이트 정보 확인")
            
            # andong 사이트 정보 확인
            cursor.execute("""
                SELECT site_code, latest_announcement_date 
                FROM homepage_site_announcement_date 
                WHERE site_code = 'andong'
            """)
            andong = cursor.fetchone()
            if andong:
                print(f"📅 현재 andong 날짜: {andong['latest_announcement_date']}")
            else:
                print("⚠️ andong 레코드가 없음")
                
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        return False


def update_db_manually(site_code, new_date):
    """수동으로 DB 업데이트"""
    print(f"\n업데이트 시도: {site_code} → {new_date}")
    
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE homepage_site_announcement_date
                SET latest_announcement_date = %s
                WHERE site_code = %s
            """, (new_date, site_code))
            
            affected = cursor.rowcount
            print(f"✅ {affected}개 행 업데이트됨")
            
            conn.commit()
            print("✅ 커밋 성공")
            
            # 확인
            cursor.execute("""
                SELECT latest_announcement_date 
                FROM homepage_site_announcement_date 
                WHERE site_code = %s
            """, (site_code,))
            result = cursor.fetchone()
            print(f"📅 업데이트 후 값: {result['latest_announcement_date']}")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 업데이트 실패: {e}")
        return False


def main():
    print("🔧 DB 업데이트 테스트 도구")
    print("=" * 60)
    
    # 1. andong 스크래핑 결과 확인
    site_code = "andong"
    output_dir = "scraped_incremental_v2/2025-09-29/andong"
    
    print(f"\n1️⃣ {site_code} 스크래핑 결과 확인")
    print("-" * 50)
    
    latest_date = get_latest_date_from_scraped_files(site_code, output_dir)
    
    if latest_date:
        print(f"\n📌 추출된 날짜: {latest_date}")
        
        # 날짜 형식 변환
        try:
            # YYYY-MM-DD 형식
            if re.match(r"^\d{4}-\d{2}-\d{2}$", latest_date):
                formatted_date = latest_date
            # YYYY.MM.DD 형식
            elif re.match(r"^\d{4}\.\d{2}\.\d{2}$", latest_date):
                formatted_date = latest_date.replace(".", "-")
            # YYYY년 MM월 DD일 형식
            elif re.match(r"^\d{4}년\s*\d{1,2}월\s*\d{1,2}일$", latest_date):
                formatted_date = re.sub(r"[년월일\s]", "-", latest_date).rstrip("-")
            else:
                print(f"⚠️ 알 수 없는 날짜 형식: {latest_date}")
                formatted_date = None
                
            if formatted_date:
                print(f"📅 변환된 날짜: {formatted_date}")
                
                # 2. DB 연결 테스트
                if test_db_connection():
                    
                    # 3. DB 업데이트
                    print("\n2️⃣ DB 업데이트 시도")
                    print("-" * 50)
                    
                    if update_db_manually(site_code, formatted_date):
                        print("\n✅ DB 업데이트 성공!")
                    else:
                        print("\n❌ DB 업데이트 실패")
                else:
                    print("\n❌ DB에 연결할 수 없어 업데이트를 수행할 수 없습니다.")
                    print("   .env 파일의 DB 설정을 확인해주세요.")
                    
        except Exception as e:
            print(f"❌ 날짜 형식 변환 오류: {e}")
    else:
        print("\n❌ 스크래핑된 파일에서 날짜를 추출할 수 없습니다.")
        
    print("\n" + "=" * 60)
    print("테스트 완료")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 커맨드라인 인자로 직접 업데이트
        if len(sys.argv) == 3:
            site = sys.argv[1]
            date = sys.argv[2]
            print(f"직접 업데이트: {site} → {date}")
            if test_db_connection():
                update_db_manually(site, date)
        else:
            print("사용법: python test_db_update.py [site_code] [date]")
            print("예시: python test_db_update.py andong 2025-09-29")
    else:
        main()