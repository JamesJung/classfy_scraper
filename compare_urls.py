#!/usr/bin/env python3
import mysql.connector
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

def connect_db():
    """MySQL 데이터베이스 연결"""
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', '192.168.0.95'),
            port=int(os.getenv('DB_PORT', '3309')),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME', 'subvention')
        )
        print(f"✅ MySQL 연결 성공: {os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}")
        return conn
    except Exception as e:
        print(f"❌ MySQL 연결 실패: {e}")
        return None

def fetch_site_master_data(conn):
    """SITE_MASTER 테이블에서 데이터 가져오기"""
    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT SITE_CODE, ANNOUNCEMENT_URL FROM SITE_MASTER WHERE ANNOUNCEMENT_URL IS NOT NULL AND ANNOUNCEMENT_URL != ''"
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()

        # dict로 변환 {site_code: announcement_url}
        site_master_dict = {}
        for row in results:
            site_code = row['SITE_CODE']
            announcement_url = row['ANNOUNCEMENT_URL']
            site_master_dict[site_code] = announcement_url

        print(f"✅ SITE_MASTER에서 {len(site_master_dict)}개 레코드 가져옴")
        return site_master_dict
    except Exception as e:
        print(f"❌ 데이터 조회 실패: {e}")
        return {}

def load_site_url_file(file_path):
    """site_url.txt 파일 읽기"""
    site_url_dict = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    site_code = parts[0]
                    list_url = parts[1]
                    site_url_dict[site_code] = list_url

        print(f"✅ site_url.txt에서 {len(site_url_dict)}개 레코드 로드")
        return site_url_dict
    except Exception as e:
        print(f"❌ 파일 읽기 실패: {e}")
        return {}

def compare_urls(db_data, file_data):
    """URL 비교"""
    print("\n" + "="*100)
    print("URL 비교 결과")
    print("="*100)

    # 1. DB에만 있는 사이트
    db_only = set(db_data.keys()) - set(file_data.keys())
    print(f"\n📊 DB에만 있는 사이트 ({len(db_only)}개):")
    for site_code in sorted(db_only):
        print(f"  - {site_code}: {db_data[site_code]}")

    # 2. 파일에만 있는 사이트
    file_only = set(file_data.keys()) - set(db_data.keys())
    print(f"\n📊 site_url.txt에만 있는 사이트 ({len(file_only)}개):")
    for site_code in sorted(file_only):
        print(f"  - {site_code}: {file_data[site_code]}")

    # 3. 양쪽 모두 있는 사이트 중 URL이 다른 경우
    common_sites = set(db_data.keys()) & set(file_data.keys())
    different_urls = []
    same_urls = []

    for site_code in common_sites:
        db_url = db_data[site_code]
        file_url = file_data[site_code]

        if db_url != file_url:
            different_urls.append((site_code, db_url, file_url))
        else:
            same_urls.append(site_code)

    print(f"\n📊 양쪽 모두 있는 사이트 중 URL이 다른 경우 ({len(different_urls)}개):")
    for site_code, db_url, file_url in sorted(different_urls):
        print(f"\n  사이트: {site_code}")
        print(f"    DB:   {db_url}")
        print(f"    File: {file_url}")

    print(f"\n✅ 양쪽 모두 있고 URL이 동일한 사이트: {len(same_urls)}개")

    # 요약
    print("\n" + "="*100)
    print("📊 요약")
    print("="*100)
    print(f"DB에만 있음:        {len(db_only)}개")
    print(f"파일에만 있음:      {len(file_only)}개")
    print(f"URL 다름:           {len(different_urls)}개")
    print(f"URL 동일:           {len(same_urls)}개")
    print(f"총 DB 레코드:       {len(db_data)}개")
    print(f"총 파일 레코드:     {len(file_data)}개")
    print("="*100)

def main():
    # MySQL 연결
    conn = connect_db()
    if not conn:
        return

    # SITE_MASTER 데이터 가져오기
    db_data = fetch_site_master_data(conn)
    conn.close()

    # site_url.txt 파일 읽기
    file_path = '/Users/jin/classfy_scraper/site_url.txt'
    file_data = load_site_url_file(file_path)

    # URL 비교
    compare_urls(db_data, file_data)

if __name__ == '__main__':
    main()
