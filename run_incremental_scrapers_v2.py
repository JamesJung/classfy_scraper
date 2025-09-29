#!/usr/bin/env python3
import os
import sys
import subprocess
import pymysql
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path

load_dotenv()

DB_HOST = os.getenv('DB_HOST')
DB_PORT = int(os.getenv('DB_PORT', 3306))
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')

NODE_DIR = Path(__file__).parent / "node"
SCRAPER_DIR = NODE_DIR / "scraper"
BASE_OUTPUT_DIR = Path(__file__).parent / "scraped_incremental_v2"

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def get_sites_to_scrape():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    site_code,
                    latest_announcement_date
                FROM homepage_site_announcement_date
                ORDER BY site_code
            """)
            return cursor.fetchall()
    finally:
        conn.close()

def check_scraper_exists(site_code):
    scraper_path = SCRAPER_DIR / f"{site_code}_scraper.js"
    return scraper_path.exists(), scraper_path

def run_scraper(site_code, from_date):
    exists, scraper_path = check_scraper_exists(site_code)
    
    if not exists:
        return {
            'site_code': site_code,
            'status': 'skipped',
            'reason': f'스크래퍼 파일 없음: {scraper_path}'
        }
    
    target_year = from_date.year
    today_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = BASE_OUTPUT_DIR / today_str / site_code
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        cmd = [
            "node",
            str(scraper_path)
        ]
        
        print(f"\n[{site_code}] 스크래퍼 실행: {target_year}년 데이터...")
        print(f"  출력 디렉토리: {output_dir}")
        print(f"  명령: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            cwd=str(NODE_DIR),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            return {
                'site_code': site_code,
                'status': 'success',
                'output_dir': str(output_dir),
                'stdout': result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
            }
        else:
            return {
                'site_code': site_code,
                'status': 'failed',
                'error': result.stderr[-500:] if len(result.stderr) > 500 else result.stderr
            }
    
    except subprocess.TimeoutExpired:
        return {
            'site_code': site_code,
            'status': 'timeout',
            'error': '5분 타임아웃 초과'
        }
    except Exception as e:
        return {
            'site_code': site_code,
            'status': 'error',
            'error': str(e)
        }

def main():
    print("=" * 80)
    print("홈페이지 고시/공고 점진적 스크래핑 v2")
    print("=" * 80)
    
    sites = get_sites_to_scrape()
    print(f"\n총 {len(sites)}개 사이트 대상")
    
    BASE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    results = {
        'success': [],
        'failed': [],
        'skipped': [],
        'timeout': [],
        'error': []
    }
    
    for idx, site in enumerate(sites, 1):
        site_code = site['site_code']
        from_date = site['latest_announcement_date']
        
        print(f"\n{'='*80}")
        print(f"[{idx}/{len(sites)}] {site_code}")
        print(f"{'='*80}")
        
        result = run_scraper(site_code, from_date)
        status = result['status']
        results[status].append(result)
        
        if status == 'success':
            print(f"  ✓ 성공: {result['output_dir']}")
        elif status == 'skipped':
            print(f"  ⊘ 스킵: {result['reason']}")
        elif status == 'failed':
            print(f"  ✗ 실패: {result['error'][:200]}")
        elif status == 'timeout':
            print(f"  ⏱ 타임아웃: {result['error']}")
        elif status == 'error':
            print(f"  ⚠ 오류: {result['error'][:200]}")
    
    print("\n" + "=" * 80)
    print("처리 결과 요약")
    print("=" * 80)
    print(f"성공: {len(results['success'])}개")
    print(f"실패: {len(results['failed'])}개")
    print(f"스킵: {len(results['skipped'])}개")
    print(f"타임아웃: {len(results['timeout'])}개")
    print(f"오류: {len(results['error'])}개")
    
    if results['skipped']:
        print(f"\n스킵된 사이트 ({len(results['skipped'])}개):")
        for r in results['skipped'][:10]:
            print(f"  - {r['site_code']}")
        if len(results['skipped']) > 10:
            print(f"  ... 외 {len(results['skipped']) - 10}개")
    
    print("\n" + "=" * 80)
    print("완료!")
    print("=" * 80)

if __name__ == "__main__":
    main()