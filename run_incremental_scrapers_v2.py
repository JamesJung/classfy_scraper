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

def get_latest_date_from_scraped_files(site_code, output_dir):
    """스크래핑된 파일에서 최신 날짜를 가져옵니다."""
    from pathlib import Path
    import re
    
    output_path = Path(output_dir)
    if not output_path.exists():
        return None
    
    # 001_로 시작하는 첫 번째 폴더 찾기
    first_dir = None
    for item_dir in sorted(output_path.iterdir()):
        if item_dir.is_dir() and item_dir.name.startswith('001_'):
            first_dir = item_dir
            break
    
    if not first_dir:
        # 001_로 시작하는 폴더가 없으면 첫 번째 디렉토리 사용
        dirs = [d for d in output_path.iterdir() if d.is_dir()]
        if dirs:
            first_dir = sorted(dirs)[0]
        else:
            return None
    
    # content.md 파일 읽기
    content_md_path = first_dir / "content.md"
    if not content_md_path.exists():
        print(f"  ⚠️ content.md 파일 없음: {first_dir.name}")
        return None
    
    try:
        with open(content_md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 날짜 추출 패턴
        date_patterns = [
            r'\*\*작성일\*\*[:\s]*(.+?)(?:\n|$)',
            r'작성일[:\s]*(.+?)(?:\n|$)',
            r'\*\*등록일\*\*[:\s]*(.+?)(?:\n|$)',
            r'등록일[:\s]*(.+?)(?:\n|$)',
            r'\*\*공고일\*\*[:\s]*(.+?)(?:\n|$)',
            r'공고일[:\s]*(.+?)(?:\n|$)'
        ]
        
        announcement_date = None
        for pattern in date_patterns:
            date_match = re.search(pattern, content, re.IGNORECASE)
            if date_match:
                announcement_date = date_match.group(1).strip()
                break
        
        if announcement_date:
            print(f"  📄 파일에서 추출한 최신 날짜: {announcement_date} (from {first_dir.name})")
            return announcement_date
        else:
            print(f"  ⚠️ 날짜 정보를 찾을 수 없음: {first_dir.name}")
            return None
            
    except Exception as e:
        print(f"  ❌ 파일 읽기 오류: {e}")
        return None

def update_latest_announcement_date(site_code, output_dir=None):
    """스크래핑 완료 후 해당 사이트의 최신 공고 날짜를 업데이트합니다."""
    
    # 스크래핑된 파일에서 최신 날짜 가져오기
    latest_date_str = None
    if output_dir:
        latest_date_str = get_latest_date_from_scraped_files(site_code, output_dir)
    
    if not latest_date_str:
        print(f"  ⚠️ 날짜 정보를 찾을 수 없어 DB 업데이트 스킵")
        return False
    
    # 날짜 형식 변환 (YYYY-MM-DD 형식으로)
    from datetime import datetime
    import re
    
    try:
        # 다양한 날짜 형식 처리
        date_obj = None
        
        # YYYY-MM-DD 형식
        if re.match(r'^\d{4}-\d{2}-\d{2}$', latest_date_str):
            date_obj = datetime.strptime(latest_date_str, '%Y-%m-%d')
        # YYYY.MM.DD 형식
        elif re.match(r'^\d{4}\.\d{2}\.\d{2}$', latest_date_str):
            date_obj = datetime.strptime(latest_date_str, '%Y.%m.%d')
        # YYYYMMDD 형식
        elif re.match(r'^\d{8}$', latest_date_str):
            date_obj = datetime.strptime(latest_date_str, '%Y%m%d')
        # YYYY년 MM월 DD일 형식
        elif re.match(r'^\d{4}년\s*\d{1,2}월\s*\d{1,2}일$', latest_date_str):
            date_obj = datetime.strptime(re.sub(r'[년월일\s]', '-', latest_date_str).rstrip('-'), '%Y-%m-%d')
        else:
            print(f"  ⚠️ 알 수 없는 날짜 형식: {latest_date_str}")
            return False
        
        # YYYY-MM-DD 형식으로 변환
        formatted_date = date_obj.strftime('%Y-%m-%d')
        
        # DB 업데이트
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE homepage_site_announcement_date
                    SET latest_announcement_date = %s,
                        updated_at = NOW()
                    WHERE site_code = %s
                """, (formatted_date, site_code))
                
                conn.commit()
                print(f"  📅 DB 업데이트 성공: {site_code} → {formatted_date}")
                return True
        finally:
            conn.close()
                
    except Exception as e:
        print(f"  ❌ DB 업데이트 오류: {site_code} - {e}")
        return False
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
    from_date_str = from_date.strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    # 스크래퍼가 내부적으로 site_code를 추가하므로, 여기서는 날짜 디렉토리까지만 생성
    base_dir_for_date = BASE_OUTPUT_DIR / today_str
    base_dir_for_date.mkdir(parents=True, exist_ok=True)
    
    # 실제 output_dir는 스크래퍼가 생성할 것이므로 여기서는 base_dir만 전달
    expected_output_dir = base_dir_for_date / site_code  # 예상 출력 디렉토리 (로깅용)
    
    try:
        # 스크래퍼에 전달할 arguments (named arguments 형식)
        cmd = [
            "node",
            str(scraper_path),
            "--output", str(base_dir_for_date),     # 날짜 디렉토리까지만 전달
            "--date", from_date_str,          # 시작 날짜
            "--site", site_code,              # 사이트 코드
            "--force"                         # 기존 폴더 덮어쓰기
        ]
        
        print(f"\n[{site_code}] 스크래퍼 실행")
        print(f"  스크래퍼 파일: {scraper_path}")
        print(f"  시작일: {from_date_str}")
        print(f"  종료일: {today_str}")
        print(f"  기본 출력 디렉토리: {base_dir_for_date}")
        print(f"  예상 최종 디렉토리: {expected_output_dir}")
        print(f"  작업 디렉토리: {NODE_DIR}")
        print(f"  명령: {' '.join(cmd)}")
        print(f"  Arguments: --output {base_dir_for_date} --date {from_date_str} --site {site_code} --force")
        
        # 환경변수 설정 (필요시)
        env = os.environ.copy()
        env['NODE_ENV'] = 'production'
        
        result = subprocess.run(
            cmd,
            cwd=str(NODE_DIR),
            capture_output=True,
            text=True,
            timeout=300,
            env=env
        )
        
        # stdout, stderr 출력 (디버깅용)
        if result.stdout:
            print(f"  [STDOUT]: {result.stdout[:500]}")
        if result.stderr:
            print(f"  [STDERR]: {result.stderr[:500]}")
        
        if result.returncode == 0:
            # stdout이 없어도 성공으로 처리할 수 있도록 체크
            scraped_count = 0
            if "scraped" in result.stdout.lower():
                # stdout에서 스크래핑 개수 추출 시도
                import re
                match = re.search(r'(\d+)\s*(?:items?|announcements?|공고)', result.stdout)
                if match:
                    scraped_count = int(match.group(1))
            
            return {
                'site_code': site_code,
                'status': 'success',
                'output_dir': str(expected_output_dir),
                'scraped_count': scraped_count,
                'stdout': result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
            }
        else:
            return {
                'site_code': site_code,
                'status': 'failed',
                'returncode': result.returncode,
                'error': result.stderr if result.stderr else result.stdout,
                'stdout': result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
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
            # 스크래핑 성공 시 DB 업데이트
            update_latest_announcement_date(site_code, result['output_dir'])
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