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

def create_table(conn):
    """scraper_site_url 테이블 생성"""
    try:
        cursor = conn.cursor()

        # 기존 테이블 삭제 (옵션)
        drop_table_query = "DROP TABLE IF EXISTS scraper_site_url"
        cursor.execute(drop_table_query)
        print("✅ 기존 테이블 삭제 완료 (존재했다면)")

        # 테이블 생성
        create_table_query = """
        CREATE TABLE scraper_site_url (
            id INT AUTO_INCREMENT PRIMARY KEY,
            site_code VARCHAR(100) NOT NULL,
            site_url VARCHAR(1000),
            scraper_path VARCHAR(500),
            scraper_name VARCHAR(200),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_site_code (site_code),
            INDEX idx_scraper_name (scraper_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        COMMENT='스크래퍼 사이트 URL 정보'
        """

        cursor.execute(create_table_query)
        print("✅ scraper_site_url 테이블 생성 완료")

        cursor.close()
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ 테이블 생성 실패: {e}")
        return False

def parse_site_url_file(file_path):
    """site_url.txt 파일 파싱"""
    records = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                line = line.strip()

                # 헤더나 구분선 건너뛰기
                if i <= 2 or not line or line.startswith('-'):
                    continue

                site_code = None
                site_url = None
                scraper_path = None
                scraper_name = None

                # 먼저 탭으로 구분 시도 (zium_scraper 데이터)
                if '\t' in line:
                    parts = line.split('\t')
                    if len(parts) >= 4:
                        site_code = parts[0].strip()
                        site_url = parts[1].strip()
                        scraper_path = parts[2].strip()
                        scraper_name = parts[3].strip()
                # 파이프(|)로 구분 (기본 스크래퍼 데이터)
                elif '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 4:
                        site_code = parts[0].strip()
                        site_url = parts[1].strip()
                        scraper_path = parts[2].strip()
                        scraper_name = parts[3].strip()

                # 유효한 데이터만 추가
                if site_code and site_url:
                    records.append({
                        'site_code': site_code,
                        'site_url': site_url,
                        'scraper_path': scraper_path if scraper_path else '',
                        'scraper_name': scraper_name if scraper_name else ''
                    })

        print(f"✅ {len(records)}개 레코드 파싱 완료")
        return records
    except Exception as e:
        print(f"❌ 파일 파싱 실패: {e}")
        return []

def insert_data(conn, records):
    """데이터 삽입"""
    try:
        cursor = conn.cursor()

        insert_query = """
        INSERT INTO scraper_site_url (site_code, site_url, scraper_path, scraper_name)
        VALUES (%s, %s, %s, %s)
        """

        # 배치 삽입
        inserted_count = 0
        failed_count = 0

        for record in records:
            try:
                cursor.execute(insert_query, (
                    record['site_code'],
                    record['site_url'],
                    record['scraper_path'],
                    record['scraper_name']
                ))
                inserted_count += 1
            except Exception as e:
                failed_count += 1
                print(f"⚠️  삽입 실패 ({record['site_code']}): {e}")

        conn.commit()
        cursor.close()

        print(f"✅ 데이터 삽입 완료: {inserted_count}개 성공, {failed_count}개 실패")
        return inserted_count
    except Exception as e:
        print(f"❌ 데이터 삽입 실패: {e}")
        return 0

def verify_data(conn):
    """데이터 검증"""
    try:
        cursor = conn.cursor(dictionary=True)

        # 총 레코드 수
        cursor.execute("SELECT COUNT(*) as total FROM scraper_site_url")
        result = cursor.fetchone()
        total_count = result['total']

        print(f"\n✅ 총 {total_count}개 레코드가 테이블에 저장되었습니다.")

        # 샘플 데이터 조회
        cursor.execute("SELECT * FROM scraper_site_url LIMIT 5")
        sample_data = cursor.fetchall()

        print("\n📊 샘플 데이터 (처음 5개):")
        for row in sample_data:
            print(f"  - {row['site_code']}: {row['site_url'][:80]}...")

        cursor.close()
        return True
    except Exception as e:
        print(f"❌ 데이터 검증 실패: {e}")
        return False

def main():
    print("="*80)
    print("site_url.txt 데이터를 MySQL로 가져오기")
    print("="*80 + "\n")

    # 1. DB 연결
    conn = connect_db()
    if not conn:
        return

    # 2. 테이블 생성
    if not create_table(conn):
        conn.close()
        return

    # 3. 파일 파싱
    file_path = '/Users/jin/classfy_scraper/site_url.txt'
    records = parse_site_url_file(file_path)

    if not records:
        print("❌ 파싱된 레코드가 없습니다.")
        conn.close()
        return

    # 4. 데이터 삽입
    inserted_count = insert_data(conn, records)

    if inserted_count > 0:
        # 5. 데이터 검증
        verify_data(conn)

    # 6. 연결 종료
    conn.close()
    print("\n✅ 모든 작업이 완료되었습니다.")

if __name__ == '__main__':
    main()
