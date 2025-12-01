#!/usr/bin/env python3
"""
누락된 폴더를 announcement_pre_processing 테이블에 일괄 등록하는 스크립트

※ 이 스크립트는 FTP 서버(192.168.0.95)에서 직접 실행해야 합니다.

분석 결과 기반:
- API (bizInfo, kStartUp, smes24): 우선순위 정책/중복으로 제외된 것은 스킵
- Eminwon/Homepage: prv_ 접두사 적용
- BTP: 그대로 등록

사용법:
  python3 batch_register_missing_folders.py --dry-run       # 미리보기
  python3 batch_register_missing_folders.py --execute       # 실제 등록
  python3 batch_register_missing_folders.py --source api    # API만 처리
  python3 batch_register_missing_folders.py --source eminwon --execute
"""

import mysql.connector
import json
import re
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple

# 데이터베이스 설정
DB_CONFIG = {
    'host': '192.168.0.95',
    'port': 3309,
    'user': 'root',
    'password': 'b3UvSDS232GbdZ42',
    'database': 'subvention'
}

# 기본 경로 (서버 로컬 경로)
BASE_PATH = '/home/zium/moabojo/incremental'


class MissingFolderRegistrar:
    def __init__(self, dry_run: bool = True, sources: List[str] = None, target_date: str = None):
        self.dry_run = dry_run
        self.sources = sources or ['api', 'eminwon', 'homepage', 'btp']
        self.target_date = target_date or datetime.now().strftime('%Y-%m-%d')
        self.conn = None
        self.stats = {
            'total_missing': 0,
            'design_excluded': 0,
            'registered': 0,
            'errors': 0,
            'content_not_found': 0
        }
        self.errors_list = []

    def connect_db(self):
        """DB 연결"""
        print("DB 연결 중...")
        self.conn = mysql.connector.connect(**DB_CONFIG)
        print("DB 연결 완료")

    def close_connections(self):
        """연결 종료"""
        if self.conn:
            self.conn.close()

    def read_content_md(self, full_path: str) -> Optional[str]:
        """로컬 파일시스템에서 content.md 읽기"""
        content_path = os.path.join(full_path, 'content.md')
        try:
            with open(content_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return None
        except Exception as e:
            return None

    def scan_local_folders(self, source: str) -> List[Dict]:
        """로컬 파일시스템에서 폴더 스캔"""
        folders = []

        if source == 'api':
            # API: /home/zium/moabojo/incremental/api/{site_code}/{folder_name}
            for api_name in ['bizInfo', 'kStartUp', 'smes24']:
                api_path = os.path.join(BASE_PATH, 'api', api_name)
                if os.path.isdir(api_path):
                    for folder_name in os.listdir(api_path):
                        full_path = os.path.join(api_path, folder_name)
                        if os.path.isdir(full_path):
                            folders.append({
                                'site_code': api_name,
                                'folder_name': folder_name,
                                'full_path': full_path,
                                'site_type': 'api_scrap'
                            })

        elif source == 'eminwon':
            # Eminwon: /home/zium/moabojo/incremental/eminwon/{YYYY-MM-DD}/{site_code}/{folder_name}
            date_path = os.path.join(BASE_PATH, 'eminwon', self.target_date)
            if os.path.isdir(date_path):
                for site_code in os.listdir(date_path):
                    site_path = os.path.join(date_path, site_code)
                    if os.path.isdir(site_path):
                        for folder_name in os.listdir(site_path):
                            full_path = os.path.join(site_path, folder_name)
                            if os.path.isdir(full_path):
                                folders.append({
                                    'site_code': site_code,
                                    'folder_name': folder_name,
                                    'full_path': full_path,
                                    'site_type': 'Eminwon'
                                })

        elif source == 'homepage':
            # Homepage: /home/zium/moabojo/incremental/homepage/{YYYY-MM-DD}/{site_code}/{folder_name}
            date_path = os.path.join(BASE_PATH, 'homepage', self.target_date)
            if os.path.isdir(date_path):
                for site_code in os.listdir(date_path):
                    site_path = os.path.join(date_path, site_code)
                    if os.path.isdir(site_path):
                        for folder_name in os.listdir(site_path):
                            full_path = os.path.join(site_path, folder_name)
                            if os.path.isdir(full_path):
                                folders.append({
                                    'site_code': site_code,
                                    'folder_name': folder_name,
                                    'full_path': full_path,
                                    'site_type': 'Homepage'
                                })

        elif source == 'btp':
            # BTP: /home/zium/moabojo/incremental/btp/{YYYYMMDD}/{site_code}/{folder_name}
            btp_date = self.target_date.replace('-', '')
            date_path = os.path.join(BASE_PATH, 'btp', btp_date)
            if os.path.isdir(date_path):
                for site_code in os.listdir(date_path):
                    site_path = os.path.join(date_path, site_code)
                    if os.path.isdir(site_path):
                        for folder_name in os.listdir(site_path):
                            full_path = os.path.join(site_path, folder_name)
                            if os.path.isdir(full_path):
                                folders.append({
                                    'site_code': site_code,
                                    'folder_name': folder_name,
                                    'full_path': full_path,
                                    'site_type': 'Scraper'
                                })

        return folders

    def get_db_folder_names(self, site_type: str, site_code: str = None) -> Set[str]:
        """DB에서 folder_name 목록 조회"""
        cursor = self.conn.cursor()

        if site_type == 'api_scrap':
            # API: site_code로 조회
            cursor.execute(
                "SELECT folder_name FROM announcement_pre_processing WHERE site_code = %s",
                (site_code,)
            )
        elif site_type in ['Homepage', 'Eminwon']:
            # Homepage/Eminwon: prv_ 접두사 적용된 site_code로 조회
            db_site_code = f"prv_{site_code}"
            cursor.execute(
                "SELECT folder_name FROM announcement_pre_processing WHERE site_code = %s",
                (db_site_code,)
            )
        else:
            # Scraper: site_code로 조회
            cursor.execute(
                "SELECT folder_name FROM announcement_pre_processing WHERE site_code = %s",
                (site_code,)
            )

        result = set(row[0] for row in cursor.fetchall())
        cursor.close()
        return result

    def is_design_excluded(self, folder_name: str, site_code: str) -> Tuple[bool, str]:
        """
        API 데이터가 설계상 제외되었는지 확인 (duplicate_log 기반)

        Returns:
            (제외 여부, 제외 사유)
        """
        cursor = self.conn.cursor(dictionary=True)

        # 가장 최근 로그 조회
        cursor.execute("""
            SELECT duplicate_type, existing_site_code
            FROM announcement_duplicate_log
            WHERE new_folder_name = %s AND new_site_code = %s
            ORDER BY id DESC
            LIMIT 1
        """, (folder_name, site_code))

        row = cursor.fetchone()
        cursor.close()

        if not row:
            return False, "미처리"

        dup_type = row['duplicate_type']

        # 설계상 정상 제외 케이스
        if dup_type == 'kept_existing':
            return True, f"우선순위 제외 (기존: {row['existing_site_code']})"
        elif dup_type == 'same_type_duplicate':
            return True, f"중복 제외 (기존: {row['existing_site_code']})"
        elif dup_type == 'replaced':
            return True, "다른 데이터로 대체됨"

        return False, dup_type


    def extract_info_from_content(self, content: str) -> Dict:
        """content.md에서 정보 추출"""
        info = {
            'title': None,
            'origin_url': None,
            'scraping_url': None,
            'announcement_date': None,
            'url_key': None
        }

        # 제목 추출
        for line in content.split('\n'):
            if line.startswith('# '):
                info['title'] = line[2:].strip()
                break
            elif line.startswith('## '):
                info['title'] = line[3:].strip()
                break

        # URL 추출
        patterns = {
            'origin_url': [r'원본\s*URL:\s*(.+)', r'origin_url:\s*(.+)', r'URL:\s*(.+)'],
            'scraping_url': [r'스크래핑\s*URL:\s*(.+)', r'scraping_url:\s*(.+)'],
            'announcement_date': [r'공고일자:\s*(.+)', r'게시일:\s*(.+)', r'등록일:\s*(.+)'],
            'url_key': [r'url_key:\s*(.+)']
        }

        for key, pats in patterns.items():
            for pat in pats:
                match = re.search(pat, content, re.IGNORECASE)
                if match:
                    info[key] = match.group(1).strip()
                    break

        return info

    def register_folder(self, folder: Dict, content: str) -> bool:
        """폴더를 DB에 등록"""
        if self.dry_run:
            return True

        try:
            cursor = self.conn.cursor()

            info = self.extract_info_from_content(content)

            # site_code 변환 (Homepage/Eminwon은 prv_ 접두사)
            db_site_code = folder['site_code']
            if folder['site_type'] in ['Homepage', 'Eminwon']:
                db_site_code = f"prv_{folder['site_code']}"

            sql = """
                INSERT INTO announcement_pre_processing (
                    folder_name, folder_path, site_type, site_code, content_md, combined_content,
                    attachment_filenames, attachment_files_list, exclusion_keyword, exclusion_reason,
                    title, origin_url, url_key, scraping_url, announcement_date,
                    processing_status, error_message, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, NOW(), NOW()
                )
                ON DUPLICATE KEY UPDATE
                    content_md = VALUES(content_md),
                    title = VALUES(title),
                    updated_at = NOW()
            """

            params = (
                folder['folder_name'],
                folder['full_path'],
                folder['site_type'],
                db_site_code,
                content,
                '',  # combined_content
                None,  # attachment_filenames
                None,  # attachment_files_list
                None,  # exclusion_keyword
                None,  # exclusion_reason
                info['title'],
                info['origin_url'],
                info['url_key'],
                info['scraping_url'],
                info['announcement_date'],
                'success',
                None
            )

            cursor.execute(sql, params)
            self.conn.commit()
            cursor.close()
            return True

        except Exception as e:
            self.errors_list.append({
                'folder': folder['folder_name'],
                'error': str(e)
            })
            return False

    def process_source(self, source: str):
        """소스별 처리"""
        print(f"\n{'='*60}")
        print(f"  {source.upper()} 처리")
        print(f"{'='*60}")

        # 로컬 폴더 스캔
        print(f"로컬 폴더 스캔 중...")
        ftp_folders = self.scan_local_folders(source)
        print(f"폴더 수: {len(ftp_folders)}")

        if not ftp_folders:
            print("처리할 폴더 없음")
            return

        # site_code별 그룹화
        by_site = {}
        for f in ftp_folders:
            sc = f['site_code']
            if sc not in by_site:
                by_site[sc] = []
            by_site[sc].append(f)

        print(f"site_code 수: {len(by_site)}")

        # 각 site_code별 처리
        for site_code, folders in by_site.items():
            site_type = folders[0]['site_type']

            # DB 폴더 목록
            db_folders = self.get_db_folder_names(site_type, site_code)

            # 누락 폴더 찾기
            missing = [f for f in folders if f['folder_name'] not in db_folders]

            if not missing:
                continue

            print(f"\n[{site_code}] 누락: {len(missing)}건")

            for folder in missing:
                self.stats['total_missing'] += 1

                # API의 경우 설계상 제외 여부 확인
                if source == 'api':
                    excluded, reason = self.is_design_excluded(folder['folder_name'], site_code)
                    if excluded:
                        self.stats['design_excluded'] += 1
                        print(f"  ⏭️  {folder['folder_name'][:40]}... - {reason}")
                        continue

                # content.md 읽기
                content = self.read_content_md(folder['full_path'])
                if not content:
                    self.stats['content_not_found'] += 1
                    print(f"  ⚠️  {folder['folder_name'][:40]}... - content.md 없음")
                    continue

                # 등록
                if self.register_folder(folder, content):
                    self.stats['registered'] += 1
                    print(f"  ✅ {folder['folder_name'][:40]}...")
                else:
                    self.stats['errors'] += 1
                    print(f"  ❌ {folder['folder_name'][:40]}... - 등록 실패")

    def run(self):
        """메인 실행"""
        print("="*60)
        print("  누락 폴더 일괄 등록 스크립트")
        print("="*60)
        print(f"모드: {'DRY RUN (미리보기)' if self.dry_run else 'EXECUTE (실제 등록)'}")
        print(f"대상 소스: {', '.join(self.sources)}")
        print(f"대상 날짜: {self.target_date}")
        print(f"기본 경로: {BASE_PATH}")
        print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)

        try:
            self.connect_db()

            for source in self.sources:
                self.process_source(source)

        finally:
            self.close_connections()

        # 요약
        print("\n" + "="*60)
        print("  처리 결과 요약")
        print("="*60)
        print(f"전체 누락: {self.stats['total_missing']}건")
        print(f"- 설계상 제외 (API 우선순위/중복): {self.stats['design_excluded']}건")
        print(f"- content.md 없음: {self.stats['content_not_found']}건")
        print(f"- 등록 완료: {self.stats['registered']}건")
        print(f"- 오류: {self.stats['errors']}건")

        if self.errors_list:
            print(f"\n오류 목록 (최대 10건):")
            for err in self.errors_list[:10]:
                print(f"  - {err['folder']}: {err['error']}")

        print("\n" + "="*60)
        if self.dry_run:
            print("DRY RUN 완료. 실제 등록하려면 --execute 옵션 사용")
        else:
            print(f"실행 완료. {self.stats['registered']}건 등록됨")
        print("="*60)


def main():
    parser = argparse.ArgumentParser(description='누락된 폴더 일괄 등록 (서버에서 직접 실행)')
    parser.add_argument('--execute', action='store_true', help='실제 등록 (기본: dry-run)')
    parser.add_argument('--dry-run', action='store_true', help='미리보기 모드 (기본)')
    parser.add_argument('--source', choices=['api', 'eminwon', 'homepage', 'btp', 'all'],
                        default='all', help='처리할 소스 (기본: all)')
    parser.add_argument('--date', type=str, default=None,
                        help='대상 날짜 (YYYY-MM-DD 형식, 기본: 오늘)')

    args = parser.parse_args()

    dry_run = not args.execute

    if args.source == 'all':
        sources = ['api', 'eminwon', 'homepage', 'btp']
    else:
        sources = [args.source]

    # 실행 확인
    if not dry_run:
        print("\n⚠️  WARNING: 실제로 DB에 데이터를 등록합니다!")
        confirm = input("계속하시겠습니까? (yes/no): ")
        if confirm.lower() != 'yes':
            print("취소되었습니다.")
            sys.exit(0)

    registrar = MissingFolderRegistrar(dry_run=dry_run, sources=sources, target_date=args.date)
    registrar.run()


if __name__ == '__main__':
    main()
