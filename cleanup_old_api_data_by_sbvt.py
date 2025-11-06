#!/usr/bin/env python3
"""
incremental/api 디렉토리에서 2025-10-31 이전 데이터 중
announcement_pre_processing 테이블에 sbvt_id가 없는 데이터만 삭제하는 스크립트

조건:
1. incremental/api/{bizInfo,smes24,kStartUp} 디렉토리 탐색
2. 2025-10-31 이전 데이터 확인
3. announcement_pre_processing 테이블에서 sbvt_id 컬럼이 NULL 또는 레코드 자체가 없는 경우 삭제
"""

import json
import sys
import shutil
from pathlib import Path
from typing import List, Tuple, Dict, Set
import argparse

# DB 연결을 위한 import
sys.path.append(str(Path(__file__).parent))
from src.config.config import config_manager

try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    print("⚠️  pymysql이 설치되지 않았습니다. pip install pymysql을 실행하세요.")
    sys.exit(1)

CUTOFF_DATE = "2025-10-31"
API_SOURCES = {
    "bizInfo": "bizInfo",
    "smes24": "smes24",
    "kStartUp": "kStartUp"
}


def get_db_connection():
    """DB 연결 생성"""
    try:
        config = config_manager.get_section('database')

        conn = pymysql.connect(
            host=config['host'],
            user=config['user'],
            password=config['password'],
            database=config['name'],
            port=config['port'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        sys.exit(1)


def check_sbvt_id_status(conn, site_code: str, folder_names: List[str]) -> Dict[str, str]:
    """
    announcement_pre_processing 테이블에서 sbvt_id 상태 확인

    Returns:
        {
            'folder_name': 'has_sbvt_id' | 'no_sbvt_id' | 'not_exists'
        }
    """
    if not folder_names:
        return {}

    status_map = {}

    try:
        cursor = conn.cursor()

        # 1. sbvt_id 컬럼이 존재하는지 확인
        cursor.execute("SHOW COLUMNS FROM announcement_pre_processing LIKE 'sbvt_id'")
        has_sbvt_id_column = cursor.fetchone() is not None

        if not has_sbvt_id_column:
            print("⚠️  announcement_pre_processing 테이블에 sbvt_id 컬럼이 없습니다.")
            print("    레코드 자체가 없는 데이터를 삭제 대상으로 판단합니다.")

        # 2. 레코드 존재 여부 및 sbvt_id 확인
        placeholders = ', '.join(['%s'] * len(folder_names))

        if has_sbvt_id_column:
            # sbvt_id 컬럼이 있는 경우
            query = f"""
                SELECT folder_name, sbvt_id
                FROM announcement_pre_processing
                WHERE folder_name IN ({placeholders})
            """
        else:
            # sbvt_id 컬럼이 없는 경우 (레코드 존재 여부만 확인)
            query = f"""
                SELECT folder_name, NULL as sbvt_id
                FROM announcement_pre_processing
                WHERE folder_name IN ({placeholders})
            """

        cursor.execute(query, folder_names)
        rows = cursor.fetchall()

        # 조회된 레코드 처리
        existing_folders = set()
        for row in rows:
            folder_name = row['folder_name']
            existing_folders.add(folder_name)

            if has_sbvt_id_column:
                if row['sbvt_id'] is None or row['sbvt_id'] == '':
                    status_map[folder_name] = 'no_sbvt_id'
                else:
                    status_map[folder_name] = 'has_sbvt_id'
            else:
                # sbvt_id 컬럼이 없으면 레코드가 있으면 보존
                status_map[folder_name] = 'has_sbvt_id'

        # 조회되지 않은 폴더는 레코드 없음
        for folder_name in folder_names:
            if folder_name not in existing_folders:
                status_map[folder_name] = 'not_exists'

        cursor.close()

    except Exception as e:
        print(f"  ⚠️  DB 조회 실패: {e}")

    return status_map


def extract_date_from_json(json_path: Path) -> str | None:
    """JSON 파일에서 날짜 추출"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        date_fields = [
            'listDate',
            'writtenDate',
            'announcementDate',
            'announcementStartDate',
            'pblancDt',
            'writDt',
            'pbanc_rcpt_bgng_dt'
        ]

        for field in date_fields:
            if field in data and data[field]:
                date_str = str(data[field])
                date_str = date_str.replace('.', '-').split()[0].split('T')[0]

                if len(date_str) == 8 and date_str.isdigit():
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

                return date_str

        return None
    except Exception as e:
        return None


def scan_api_directory(
    base_path: Path,
    cutoff_date: str,
    conn,
    dry_run: bool = True
) -> Dict[str, List[Tuple[Path, str, str]]]:
    """
    API 디렉토리를 스캔하여 삭제 대상 폴더 목록 반환

    Returns:
        {
            'bizInfo': [(폴더경로, 날짜, sbvt_id상태), ...],
            ...
        }
    """
    results = {source: [] for source in API_SOURCES.keys()}

    for source, site_code in API_SOURCES.items():
        source_path = base_path / source

        if not source_path.exists():
            print(f"\n⚠️  {source} 디렉토리가 존재하지 않습니다: {source_path}")
            continue

        print(f"\n{'='*80}")
        print(f"📂 {source} 스캔 중...")
        print(f"{'='*80}")

        folders = [d for d in source_path.iterdir() if d.is_dir()]
        print(f"   총 {len(folders)}개 폴더 발견")

        # 1단계: 날짜 기준으로 필터링
        old_folders = []

        for folder in folders:
            json_files = list(folder.glob("*.json"))
            if not json_files:
                continue

            announcement_date = extract_date_from_json(json_files[0])
            if not announcement_date:
                continue

            if announcement_date < cutoff_date:
                # folder_name 형식: {site_code}/{announcement_id}
                folder_name = f"{site_code}/{folder.name}"
                old_folders.append((folder, announcement_date, folder_name))

        if not old_folders:
            print(f"   ✅ {cutoff_date} 이전 데이터 없음")
            continue

        print(f"   📅 {cutoff_date} 이전 데이터: {len(old_folders)}개")

        # 2단계: DB sbvt_id 체크 (배치로 처리)
        folder_names = [fn for _, _, fn in old_folders]
        sbvt_status = check_sbvt_id_status(conn, site_code, folder_names)

        # 통계
        has_sbvt_count = sum(1 for s in sbvt_status.values() if s == 'has_sbvt_id')
        no_sbvt_count = sum(1 for s in sbvt_status.values() if s == 'no_sbvt_id')
        not_exists_count = sum(1 for s in sbvt_status.values() if s == 'not_exists')

        print(f"   💾 DB 상태:")
        print(f"      - sbvt_id 있음: {has_sbvt_count}개 (보존)")
        print(f"      - sbvt_id 없음: {no_sbvt_count}개 (삭제 대상)")
        print(f"      - 레코드 없음: {not_exists_count}개 (삭제 대상)")

        # 3단계: sbvt_id가 없거나 레코드가 없는 데이터만 선별
        for folder, date_str, folder_name in old_folders:
            status = sbvt_status.get(folder_name, 'not_exists')

            if status in ['no_sbvt_id', 'not_exists']:
                results[source].append((folder, date_str, status))
                status_emoji = "🗑️  [삭제 대상]" if not dry_run else "📋 [확인됨]"
                status_text = "sbvt_id 없음" if status == 'no_sbvt_id' else "레코드 없음"
                print(f"  {status_emoji} {folder.name} - {date_str} ({status_text})")
            elif dry_run:
                print(f"  ✅ [보존] {folder.name} - {date_str} (sbvt_id 있음)")

    return results


def delete_folders(folders: List[Tuple[Path, str, str]], backup_dir: Path | None = None) -> Tuple[int, int]:
    """폴더 삭제 (옵션: 백업)"""
    success = 0
    failed = 0

    for folder, date_str, status in folders:
        try:
            if backup_dir:
                source_name = folder.parent.name
                backup_source_dir = backup_dir / source_name
                backup_source_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_source_dir / folder.name
                shutil.copytree(folder, backup_path)
                print(f"  💾 백업 완료: {folder.name} -> {backup_path}")

            shutil.rmtree(folder)
            success += 1
            status_text = "sbvt_id 없음" if status == 'no_sbvt_id' else "레코드 없음"
            print(f"  ✅ 삭제 완료: {folder.name} ({date_str}, {status_text})")

        except Exception as e:
            failed += 1
            print(f"  ❌ 삭제 실패: {folder.name} - {e}")

    return success, failed


def main():
    parser = argparse.ArgumentParser(
        description=f'incremental/api에서 {CUTOFF_DATE} 이전 데이터 중 sbvt_id가 없는 데이터만 삭제',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # Dry-run (실제 삭제 안함)
  python cleanup_old_api_data_by_sbvt.py --dry-run

  # 실제 삭제
  python cleanup_old_api_data_by_sbvt.py

  # 백업 후 삭제
  python cleanup_old_api_data_by_sbvt.py --backup backup_api_20251106
        """
    )

    parser.add_argument('--dry-run', action='store_true', help='실제 삭제하지 않고 삭제 대상만 확인')
    parser.add_argument('--backup', type=str, help='삭제 전 백업 디렉토리 경로')
    parser.add_argument('--cutoff-date', type=str, default=CUTOFF_DATE, help=f'기준 날짜 (기본값: {CUTOFF_DATE})')
    parser.add_argument('--base-path', type=str, default='incremental/api', help='API 디렉토리 경로')

    args = parser.parse_args()

    base_path = Path(args.base_path)
    backup_dir = Path(args.backup) if args.backup else None
    cutoff_date = args.cutoff_date

    if not base_path.exists():
        print(f"❌ 오류: {base_path} 디렉토리가 존재하지 않습니다.")
        return 1

    # DB 연결
    print("\n🔌 DB 연결 중...")
    conn = get_db_connection()
    print("✅ DB 연결 성공")

    print("\n" + "="*80)
    print("🧹 incremental/api 오래된 데이터 정리 (sbvt_id 없는 데이터만)")
    print("="*80)
    print(f"📅 기준 날짜: {cutoff_date} (이전 데이터 중 sbvt_id 없는 것만 삭제)")
    print(f"📂 대상 디렉토리: {base_path.absolute()}")
    print(f"🔍 모드: {'DRY-RUN (실제 삭제 안함)' if args.dry_run else '실제 삭제 모드'}")
    if backup_dir:
        print(f"💾 백업 디렉토리: {backup_dir.absolute()}")
    print("="*80)

    # 스캔
    results = scan_api_directory(base_path, cutoff_date, conn, args.dry_run)

    # 통계
    total_to_delete = sum(len(folders) for folders in results.values())

    print("\n" + "="*80)
    print("📊 스캔 결과 요약 (sbvt_id 없는 데이터만)")
    print("="*80)

    for source in API_SOURCES.keys():
        count = len(results[source])
        print(f"  {source:12} : {count:4}개 폴더")

    print(f"  {'총 삭제 대상':12} : {total_to_delete:4}개 폴더")
    print("="*80)

    conn.close()

    if total_to_delete == 0:
        print("\n✅ 삭제할 데이터가 없습니다.")
        return 0

    if args.dry_run:
        print("\n✅ Dry-run 완료. 실제 삭제하려면 --dry-run 옵션 없이 실행하세요.")
        return 0

    # 확인
    print("\n⚠️  위 폴더들이 삭제됩니다! (sbvt_id가 없는 데이터만)")
    if backup_dir:
        print(f"💾 삭제 전 {backup_dir}에 백업됩니다.")

    response = input("\n계속하시겠습니까? (yes/no): ").strip().lower()

    if response not in ['yes', 'y']:
        print("\n❌ 취소되었습니다.")
        return 0

    # 백업 디렉토리 생성
    if backup_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n💾 백업 디렉토리 생성: {backup_dir.absolute()}")

    # 삭제 실행
    print("\n" + "="*80)
    print("🗑️  삭제 시작...")
    print("="*80)

    total_success = 0
    total_failed = 0

    for source in API_SOURCES.keys():
        if not results[source]:
            continue

        print(f"\n📂 {source} 처리 중...")
        success, failed = delete_folders(results[source], backup_dir)
        total_success += success
        total_failed += failed

    # 최종 결과
    print("\n" + "="*80)
    print("📊 최종 결과")
    print("="*80)
    print(f"  ✅ 성공: {total_success}개")
    print(f"  ❌ 실패: {total_failed}개")
    if backup_dir and total_success > 0:
        print(f"  💾 백업 위치: {backup_dir.absolute()}")
    print("="*80)

    print("\n✅ 정리 완료!")

    return 0 if total_failed == 0 else 1


if __name__ == '__main__':
    exit(main())
