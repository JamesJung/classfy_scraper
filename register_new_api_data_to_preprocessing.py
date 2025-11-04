#!/usr/bin/env python3
"""
api_url_registry에서 2025-10-30 이후 데이터를 announcement_pre_processing에 등록

전제조건:
1. announcement_pre_processing에서 구 api_scrap 데이터 삭제 완료
2. /home/zium/moabojo/incremental/api/{site_code}/{folder_id}/content.md 파일 존재

기능:
1. api_url_registry에서 post_date >= '2025-10-30' 데이터 조회
2. 각 레코드의 folder_name에서 폴더 경로 추출
3. content.md 파일 읽기
4. announcement_pre_processing 테이블에 INSERT
5. api_url_registry의 preprocessing_id 업데이트
"""

import mysql.connector
from pathlib import Path
from datetime import datetime
import sys
import re
import json
from typing import Dict, List, Optional, Tuple
import hashlib

# 데이터베이스 연결 설정
DB_CONFIG = {
    'host': '192.168.0.95',
    'port': 3309,
    'user': 'root',
    'password': 'b3UvSDS232GbdZ42',
    'database': 'subvention'
}

# 기준 날짜
CUTOFF_DATE = '2025-10-30'

# 프로덕션 데이터 경로
BASE_DATA_PATH = Path("/home/zium/moabojo/incremental")


class ApiDataRegistrar:
    def __init__(self, dry_run: bool = True):
        """
        Args:
            dry_run: True면 미리보기만, False면 실제 등록
        """
        self.dry_run = dry_run
        self.stats = {
            'total': 0,
            'content_md_found': 0,
            'content_md_not_found': 0,
            'registered': 0,
            'skipped': 0,
            'errors': 0
        }
        self.errors_list = []

    def extract_folder_info(self, folder_name: str) -> Tuple[str, str]:
        """
        folder_name에서 site_code와 folder_id 추출

        Args:
            folder_name: "output/data/kStartUp/175424" 형식

        Returns:
            (site_code, folder_id) 튜플
        """
        # output/data/{site_code}/{folder_id} 패턴
        match = re.search(r'output/data/([^/]+)/(.+)$', folder_name)
        if match:
            return match.group(1), match.group(2)

        # 예외 처리: 다른 패턴이 있을 수 있음
        parts = folder_name.split('/')
        if len(parts) >= 2:
            return parts[-2], parts[-1]

        return None, None

    def get_content_md_path(self, site_code: str, folder_id: str) -> Path:
        """
        content.md 파일 경로 생성

        Args:
            site_code: bizInfo, kStartUp, smes24
            folder_id: 폴더 ID

        Returns:
            전체 경로
        """
        return BASE_DATA_PATH / "api" / site_code / folder_id / "content.md"

    def extract_title_from_content(self, content: str) -> Optional[str]:
        """content.md에서 제목 추출"""
        lines = content.split('\n')
        for line in lines:
            if line.startswith('# '):
                return line[2:].strip()
            if line.startswith('## '):
                return line[3:].strip()
        return None

    def extract_url_from_content(self, content: str, marker: str) -> Optional[str]:
        """content.md에서 URL 추출"""
        pattern = rf'{marker}:\s*(.+)'
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()
        return None

    def extract_date_from_content(self, content: str) -> Optional[str]:
        """content.md에서 날짜 추출"""
        # 공고일자, 게시일, 등록일 등 다양한 형식
        patterns = [
            r'공고일자:\s*(.+)',
            r'게시일:\s*(.+)',
            r'등록일:\s*(.+)',
            r'날짜:\s*(.+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1).strip()
        return None

    def convert_date_to_yyyymmdd(self, date_str: str) -> Optional[str]:
        """다양한 날짜 형식을 YYYYMMDD로 변환"""
        if not date_str:
            return None

        # 이미 YYYYMMDD 형식
        if len(date_str) == 8 and date_str.isdigit():
            return date_str

        # YYYY.MM.DD, YYYY-MM-DD 등
        date_str = date_str.replace('.', '-').replace('/', '-')
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str.split()[0], '%Y-%m-%d')
            return dt.strftime('%Y%m%d')
        except:
            return None

    def get_new_api_data(self) -> List[Dict]:
        """
        api_url_registry에서 2025-10-30 이후 데이터 조회

        Returns:
            레코드 목록
        """
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)

            query = f"""
                SELECT
                    id,
                    site_code,
                    site_name,
                    announcement_url,
                    announcement_id,
                    title,
                    post_date,
                    status,
                    folder_name,
                    scrap_url,
                    url_key,
                    url_key_hash
                FROM api_url_registry
                WHERE post_date >= '{CUTOFF_DATE}'
                ORDER BY site_code, post_date
            """

            cursor.execute(query)
            records = cursor.fetchall()

            cursor.close()
            conn.close()

            print(f"✅ 데이터베이스 조회 완료: {len(records)}건")
            return records

        except mysql.connector.Error as err:
            print(f"❌ 데이터베이스 오류: {err}")
            sys.exit(1)

    def register_to_preprocessing(self, record: Dict, content_md: str) -> Optional[int]:
        """
        announcement_pre_processing 테이블에 레코드 등록

        Args:
            record: api_url_registry 레코드
            content_md: content.md 내용

        Returns:
            생성된 레코드 ID 또는 None
        """
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()

            # content.md에서 정보 추출
            title = record['title'] or self.extract_title_from_content(content_md)
            origin_url = record['announcement_url']
            scraping_url = record['scrap_url']
            url_key = record['url_key']

            # 날짜 변환
            announcement_date = None
            if record['post_date']:
                announcement_date = record['post_date'].strftime('%Y%m%d')

            # folder_name 추출
            _, folder_id = self.extract_folder_info(record['folder_name'])

            # INSERT 쿼리
            sql = """
                INSERT INTO announcement_pre_processing (
                    folder_name, site_type, site_code, content_md, combined_content,
                    attachment_filenames, attachment_files_list, exclusion_keyword, exclusion_reason,
                    title, origin_url, url_key, scraping_url, announcement_date,
                    processing_status, error_message, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, NOW(), NOW()
                )
            """

            params = (
                folder_id,  # folder_name
                'api_scrap',  # site_type
                record['site_code'],  # site_code
                content_md,  # content_md
                '',  # combined_content (첨부파일 처리는 별도)
                None,  # attachment_filenames
                None,  # attachment_files_list
                None,  # exclusion_keyword
                None,  # exclusion_reason
                title,  # title
                origin_url,  # origin_url
                url_key,  # url_key
                scraping_url,  # scraping_url
                announcement_date,  # announcement_date
                'success',  # processing_status
                None,  # error_message
            )

            cursor.execute(sql, params)
            record_id = cursor.lastrowid

            # api_url_registry 업데이트
            update_sql = """
                UPDATE api_url_registry
                SET preprocessing_id = %s,
                    update_at = NOW()
                WHERE id = %s
            """
            cursor.execute(update_sql, (record_id, record['id']))

            conn.commit()
            cursor.close()
            conn.close()

            return record_id

        except mysql.connector.Error as err:
            print(f"  ❌ DB 오류: {err}")
            self.errors_list.append({
                'folder_name': record['folder_name'],
                'error': str(err)
            })
            return None

    def process_records(self, records: List[Dict]):
        """
        레코드 처리 메인 로직
        """
        print("\n" + "=" * 80)
        print(f"처리 시작: {len(records)}건")
        print("=" * 80)

        site_stats = {}

        for i, record in enumerate(records, 1):
            self.stats['total'] += 1

            site_code = record['site_code']
            folder_name = record['folder_name']
            post_date = record['post_date']

            # 사이트별 통계 초기화
            if site_code not in site_stats:
                site_stats[site_code] = {
                    'total': 0,
                    'content_md_found': 0,
                    'content_md_not_found': 0,
                    'registered': 0,
                    'errors': 0
                }

            site_stats[site_code]['total'] += 1

            # folder_name에서 site_code와 folder_id 추출
            _, folder_id = self.extract_folder_info(folder_name)

            if not folder_id:
                print(f"⚠️  [{i}/{len(records)}] folder_name 파싱 실패: {folder_name}")
                self.stats['errors'] += 1
                site_stats[site_code]['errors'] += 1
                self.errors_list.append({
                    'folder_name': folder_name,
                    'error': 'Cannot parse folder_name'
                })
                continue

            # content.md 경로 생성
            content_md_path = self.get_content_md_path(site_code, folder_id)

            # 진행 상황 출력 (10건마다)
            if i % 10 == 0 or i <= 10:
                print(f"\n[{i}/{len(records)}] 처리 중...")

            # content.md 존재 여부 확인
            if not content_md_path.exists():
                if i <= 10:
                    print(f"  ⏭️  건너뜀 (content.md 없음): {content_md_path.relative_to(BASE_DATA_PATH)}")
                self.stats['content_md_not_found'] += 1
                site_stats[site_code]['content_md_not_found'] += 1
                continue

            # content.md 읽기
            try:
                with open(content_md_path, 'r', encoding='utf-8') as f:
                    content_md = f.read()

                # DO_NOT_PROCESS 플래그 확인
                if "DO_NOT_PROCESS" in content_md:
                    if i <= 10:
                        print(f"  ⏭️  건너뜀 (ARCHIVED): {folder_id}")
                    self.stats['skipped'] += 1
                    continue

                self.stats['content_md_found'] += 1
                site_stats[site_code]['content_md_found'] += 1

                if i <= 10:
                    print(f"  📝 등록: {folder_id} - {record['title'][:50]}")

                # DRY RUN 모드가 아니면 실제 등록
                if not self.dry_run:
                    record_id = self.register_to_preprocessing(record, content_md)
                    if record_id:
                        self.stats['registered'] += 1
                        site_stats[site_code]['registered'] += 1
                        if i <= 10:
                            print(f"    ✅ 등록 완료 (ID: {record_id})")
                    else:
                        self.stats['errors'] += 1
                        site_stats[site_code]['errors'] += 1
                else:
                    self.stats['registered'] += 1
                    site_stats[site_code]['registered'] += 1

            except Exception as e:
                print(f"  ❌ 오류: {content_md_path} - {e}")
                self.stats['errors'] += 1
                site_stats[site_code]['errors'] += 1
                self.errors_list.append({
                    'path': str(content_md_path),
                    'error': str(e)
                })

        # 사이트별 통계 출력
        print("\n" + "=" * 80)
        print("사이트별 통계")
        print("=" * 80)
        for site_code, stats in site_stats.items():
            print(f"\n[{site_code}]")
            print(f"  총 레코드: {stats['total']}건")
            print(f"  content.md 발견: {stats['content_md_found']}건")
            print(f"  content.md 없음: {stats['content_md_not_found']}건")
            print(f"  등록 완료: {stats['registered']}건")
            print(f"  에러: {stats['errors']}건")

    def print_summary(self):
        """
        최종 통계 출력
        """
        print("\n" + "=" * 80)
        print("최종 통계")
        print("=" * 80)
        print(f"총 레코드: {self.stats['total']}건")
        print(f"content.md 발견: {self.stats['content_md_found']}건")
        print(f"content.md 없음: {self.stats['content_md_not_found']}건")
        print(f"건너뜀 (ARCHIVED): {self.stats['skipped']}건")
        print(f"등록 완료: {self.stats['registered']}건")
        print(f"에러: {self.stats['errors']}건")

        if self.errors_list:
            print(f"\n에러 목록 (최대 10건):")
            for error in self.errors_list[:10]:
                print(f"  - {error}")

        print("\n" + "=" * 80)
        if self.dry_run:
            print("DRY RUN 모드 완료")
            print("실제 등록을 하려면 다음 명령을 실행하세요:")
            print("  python register_new_api_data_to_preprocessing.py --execute")
        else:
            print("실행 완료")
            print(f"총 {self.stats['registered']}건이 announcement_pre_processing에 등록되었습니다.")
        print("=" * 80)


def main():
    """
    메인 실행 함수
    """
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        dry_run = False
    else:
        dry_run = True

    print("=" * 80)
    print("API 신규 데이터 announcement_pre_processing 등록 스크립트")
    print("=" * 80)
    print(f"기준 날짜: {CUTOFF_DATE} 이후 데이터")
    print(f"데이터 경로: {BASE_DATA_PATH}/api/")
    print(f"모드: {'DRY RUN (미리보기)' if dry_run else 'EXECUTE (실제 등록)'}")
    print("=" * 80)

    # 확인
    if not dry_run:
        print("\n⚠️  WARNING: announcement_pre_processing 테이블에 실제로 데이터를 등록합니다!")
        print("⚠️  WARNING: 이전에 구 데이터를 삭제했는지 확인하세요!")
        confirm = input("계속하시겠습니까? (yes/no): ")
        if confirm.lower() != 'yes':
            print("취소되었습니다.")
            sys.exit(0)

    # 처리 시작
    registrar = ApiDataRegistrar(dry_run)

    # 데이터 조회
    records = registrar.get_new_api_data()

    if not records:
        print("처리할 레코드가 없습니다.")
        sys.exit(0)

    # 레코드 처리
    registrar.process_records(records)

    # 통계 출력
    registrar.print_summary()


if __name__ == '__main__':
    main()
