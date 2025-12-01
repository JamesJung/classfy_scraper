#!/usr/bin/env python3
"""
누락된 모든 데이터를 일괄 처리하는 스크립트

/home/zium/moabojo/incremental/ 디렉토리를 스캔하여
DB에 등록되지 않은 모든 데이터를 announcement_pre_processor.py로 처리합니다.

announcement_pre_processor.py는 이미 처리된 folder_name은 자동으로 스킵하므로
이 스크립트를 반복 실행해도 안전합니다.
"""

import os
import sys
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set
import argparse

# DB 연결 설정
try:
    import mysql.connector
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# 기본 설정
BASE_DIR = Path('/home/zium/moabojo/incremental')
PROCESSOR_SCRIPT = 'announcement_pre_processor.py'

# 디렉토리 매핑 (실제 FTP 서버 구조 기준)
# /home/zium/moabojo/incremental/
#   ├── eminwon/{date}/{site_code}/{folder}/
#   ├── homepage/{date}/{site_code}/{folder}/
#   ├── api/{bizInfo|kStartUp|smes24}/{folder}/
#   └── btp/{YYYYMMDD}/{site_code}/{folder}/
SOURCE_DIRS = {
    'eminwon': BASE_DIR / 'eminwon',
    'homepage': BASE_DIR / 'homepage',
    'api': BASE_DIR / 'api',
    'scraper': BASE_DIR / 'btp',
}

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('process_missing.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def get_db_connection():
    """DB 연결 생성"""
    if not DB_AVAILABLE:
        logger.warning("mysql-connector-python이 설치되지 않았습니다. pip install mysql-connector-python")
        return None

    try:
        conn = mysql.connector.connect(
            host=os.environ.get('DB_HOST', '192.168.0.95'),
            user=os.environ.get('DB_USER', 'root'),
            password=os.environ.get('DB_PASSWORD', 'b3UvSDS232GbdZ42'),
            port=int(os.environ.get('DB_PORT', '3309')),
            database=os.environ.get('DB_NAME', 'subvention')
        )
        return conn
    except Exception as e:
        logger.error(f"DB 연결 실패: {e}")
        return None


def get_processed_folders(conn) -> Set[str]:
    """DB에 이미 등록된 folder_name 목록 조회"""
    if conn is None:
        return set()

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT folder_name FROM announcement_pre_processing")
        return set(row[0] for row in cursor.fetchall())
    except Exception as e:
        logger.error(f"DB 조회 실패: {e}")
        return set()


def scan_directories() -> Dict[str, List[Dict]]:
    """
    모든 소스 디렉토리를 스캔하여 처리할 폴더 목록 반환

    Returns:
        {
            'eminwon': [{'path': Path, 'site_code': str, 'folder_name': str, 'date': str}, ...],
            'homepage': [...],
            'api': [...]
        }
    """
    result = {
        'eminwon': [],
        'homepage': [],
        'api': [],
        'scraper': []
    }

    # Eminwon 디렉토리 스캔
    eminwon_dir = SOURCE_DIRS.get('eminwon')
    if eminwon_dir and eminwon_dir.exists():
        logger.info(f"Eminwon 디렉토리 스캔: {eminwon_dir}")
        for date_dir in sorted(eminwon_dir.iterdir()):
            if date_dir.is_dir() and not date_dir.name.startswith('.'):
                for site_dir in date_dir.iterdir():
                    if site_dir.is_dir() and not site_dir.name.startswith('.'):
                        for folder in site_dir.iterdir():
                            if folder.is_dir() and (folder / 'content.md').exists():
                                result['eminwon'].append({
                                    'path': folder,
                                    'site_code': site_dir.name,
                                    'folder_name': folder.name,
                                    'date': date_dir.name,
                                    'parent_dir': date_dir  # date 디렉토리를 전달 (site_code는 내부에서 추가됨)
                                })

    # Homepage 디렉토리 스캔
    homepage_dir = SOURCE_DIRS.get('homepage')
    if homepage_dir and homepage_dir.exists():
        logger.info(f"Homepage 디렉토리 스캔: {homepage_dir}")
        for date_dir in sorted(homepage_dir.iterdir()):
            if date_dir.is_dir() and not date_dir.name.startswith('.'):
                for site_dir in date_dir.iterdir():
                    if site_dir.is_dir() and not site_dir.name.startswith('.'):
                        for folder in site_dir.iterdir():
                            if folder.is_dir() and (folder / 'content.md').exists():
                                result['homepage'].append({
                                    'path': folder,
                                    'site_code': site_dir.name,
                                    'folder_name': folder.name,
                                    'date': date_dir.name,
                                    'parent_dir': date_dir  # date 디렉토리를 전달
                                })

    # API 디렉토리 스캔 (bizInfo, kStartUp, smes24)
    api_dir = SOURCE_DIRS.get('api')
    if api_dir and api_dir.exists():
        logger.info(f"API 디렉토리 스캔: {api_dir}")
        for api_type_dir in api_dir.iterdir():
            if api_type_dir.is_dir() and api_type_dir.name in ['bizInfo', 'kStartUp', 'smes24']:
                for folder in api_type_dir.iterdir():
                    if folder.is_dir() and (folder / 'content.md').exists():
                        result['api'].append({
                            'path': folder,
                            'site_code': api_type_dir.name,
                            'folder_name': folder.name,
                            'date': '',  # API는 날짜별 구분 없음
                            'parent_dir': api_dir  # api 디렉토리를 전달 (site_code는 내부에서 추가됨)
                        })

    # Scraper(BTP) 디렉토리 스캔
    scraper_dir = SOURCE_DIRS.get('scraper')
    if scraper_dir and scraper_dir.exists():
        logger.info(f"Scraper 디렉토리 스캔: {scraper_dir}")
        for date_dir in sorted(scraper_dir.iterdir()):
            if date_dir.is_dir() and not date_dir.name.startswith('.'):
                for site_dir in date_dir.iterdir():
                    if site_dir.is_dir() and not site_dir.name.startswith('.'):
                        for folder in site_dir.iterdir():
                            if folder.is_dir() and (folder / 'content.md').exists():
                                result['scraper'].append({
                                    'path': folder,
                                    'site_code': site_dir.name,
                                    'folder_name': folder.name,
                                    'date': date_dir.name,
                                    'parent_dir': date_dir  # date 디렉토리를 전달
                                })

    return result


def get_site_type(source: str) -> str:
    """소스 타입을 site_type으로 변환"""
    mapping = {
        'eminwon': 'Eminwon',
        'homepage': 'Homepage',
        'api': 'API',
        'scraper': 'Scraper'
    }
    return mapping.get(source, 'Scraper')


def run_processor(site_dir: Path, site_code: str, site_type: str, dry_run: bool = False) -> bool:
    """
    announcement_pre_processor.py 실행

    Args:
        site_dir: site_code 레벨의 디렉토리 (예: /home/zium/.../2025-12-01/서울)
        site_code: 사이트 코드
        site_type: Eminwon, Homepage, API, Scraper (로깅용)
        dry_run: 실제 실행 없이 로그만 출력
    """
    # announcement_pre_processor.py는 --site-type을 받지 않음
    # 경로에서 자동으로 site_type 결정 (determine_site_type 함수 사용)
    cmd = [
        'python3', PROCESSOR_SCRIPT,
        '-d', str(site_dir),
        '--site-code', site_code
    ]

    logger.info(f"실행: {' '.join(cmd)} (site_type: {site_type})")

    if dry_run:
        return True

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10분 타임아웃
        )

        if result.returncode == 0:
            logger.info(f"성공: {site_code} ({site_type})")
            return True
        else:
            logger.error(f"실패: {site_code} - {result.stderr[:500]}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"타임아웃: {site_code}")
        return False
    except Exception as e:
        logger.error(f"오류: {site_code} - {e}")
        return False


def process_missing_data(sources: List[str] = None, dry_run: bool = False,
                         check_db: bool = True, specific_date: str = None):
    """
    누락된 데이터 일괄 처리

    Args:
        sources: 처리할 소스 목록 ['eminwon', 'homepage', 'api', 'scraper']
        dry_run: 실제 실행 없이 로그만 출력
        check_db: DB 조회하여 이미 처리된 것은 스킵
        specific_date: 특정 날짜만 처리 (YYYY-MM-DD)
    """
    if sources is None:
        sources = ['eminwon', 'homepage', 'api', 'scraper']

    logger.info("=" * 80)
    logger.info("누락 데이터 일괄 처리 시작")
    logger.info(f"처리 대상 소스: {sources}")
    logger.info(f"Dry-run 모드: {dry_run}")
    logger.info("=" * 80)

    # 디렉토리 스캔
    all_folders = scan_directories()

    # DB에서 이미 처리된 목록 조회
    processed_folders = set()
    if check_db:
        conn = get_db_connection()
        if conn:
            processed_folders = get_processed_folders(conn)
            conn.close()
            logger.info(f"DB에 이미 등록된 folder_name: {len(processed_folders)}개")

    # 처리할 site_code별로 그룹핑
    # announcement_pre_processor.py는 site_code 단위로 실행됨
    to_process = {}  # {(site_dir, site_code, site_type): [folders]}

    stats = {
        'total_scanned': 0,
        'already_processed': 0,
        'to_process': 0,
        'success': 0,
        'failed': 0
    }

    for source in sources:
        if source not in all_folders:
            continue

        site_type = get_site_type(source)

        for item in all_folders[source]:
            stats['total_scanned'] += 1

            # 특정 날짜 필터
            if specific_date and item['date'] != specific_date:
                continue

            # DB에서 이미 처리된 것은 스킵 (announcement_pre_processor.py 내부에서도 체크하지만 효율을 위해)
            if check_db and item['folder_name'] in processed_folders:
                stats['already_processed'] += 1
                continue

            stats['to_process'] += 1

            # site_code 단위로 그룹핑
            key = (str(item['parent_dir']), item['site_code'], site_type)
            if key not in to_process:
                to_process[key] = []
            to_process[key].append(item)

    logger.info(f"\n스캔 결과:")
    logger.info(f"  - 총 스캔: {stats['total_scanned']}개 폴더")
    logger.info(f"  - 이미 처리됨: {stats['already_processed']}개")
    logger.info(f"  - 처리 필요: {stats['to_process']}개")
    logger.info(f"  - 처리할 site_code 수: {len(to_process)}개")

    if not to_process:
        logger.info("처리할 데이터가 없습니다.")
        return stats

    # site_code 단위로 처리
    logger.info(f"\n{'='*80}")
    logger.info("처리 시작")
    logger.info(f"{'='*80}\n")

    for idx, ((site_dir, site_code, site_type), folders) in enumerate(to_process.items(), 1):
        logger.info(f"[{idx}/{len(to_process)}] {site_code} ({site_type}) - {len(folders)}개 폴더")

        success = run_processor(
            Path(site_dir),
            site_code,
            site_type,
            dry_run=dry_run
        )

        if success:
            stats['success'] += 1
        else:
            stats['failed'] += 1

    # 최종 통계
    logger.info(f"\n{'='*80}")
    logger.info("처리 완료 - 최종 통계")
    logger.info(f"{'='*80}")
    logger.info(f"총 스캔: {stats['total_scanned']}개")
    logger.info(f"이미 처리됨: {stats['already_processed']}개")
    logger.info(f"처리 시도: {len(to_process)}개 site_code")
    logger.info(f"  - 성공: {stats['success']}개")
    logger.info(f"  - 실패: {stats['failed']}개")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='누락된 모든 데이터를 일괄 처리',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 모든 소스의 누락 데이터 처리
  python3 process_all_missing_data.py

  # Eminwon만 처리
  python3 process_all_missing_data.py --source eminwon

  # API만 처리
  python3 process_all_missing_data.py --source api

  # 특정 날짜만 처리
  python3 process_all_missing_data.py --date 2025-12-01

  # Dry-run (실제 실행 없이 확인만)
  python3 process_all_missing_data.py --dry-run

  # DB 체크 없이 모두 처리 시도
  python3 process_all_missing_data.py --no-db-check
        """
    )

    parser.add_argument(
        '--source',
        type=str,
        choices=['eminwon', 'homepage', 'api', 'scraper', 'all'],
        default='all',
        help='처리할 데이터 소스 (기본값: all)'
    )

    parser.add_argument(
        '--date',
        type=str,
        help='특정 날짜만 처리 (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='실제 실행 없이 처리할 목록만 출력'
    )

    parser.add_argument(
        '--no-db-check',
        action='store_true',
        help='DB 조회 없이 모두 처리 시도 (announcement_pre_processor.py 내부에서 중복 체크)'
    )

    args = parser.parse_args()

    # 소스 결정
    if args.source == 'all':
        sources = ['eminwon', 'homepage', 'api', 'scraper']
    else:
        sources = [args.source]

    # 처리 실행
    stats = process_missing_data(
        sources=sources,
        dry_run=args.dry_run,
        check_db=not args.no_db_check,
        specific_date=args.date
    )

    # 종료 코드
    sys.exit(0 if stats['failed'] == 0 else 1)


if __name__ == '__main__':
    main()
