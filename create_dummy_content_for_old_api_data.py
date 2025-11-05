#!/usr/bin/env python3
"""
API scrap 구 데이터(2025-10-30 이전) 처리 방지 스크립트

프로덕션 환경 구조:
- api/bizInfo/{folder_id}/
- api/kStartUp/{folder_id}/
- api/smes24/{folder_id}/

기능:
1. api_url_registry에서 2025-10-30 이전 데이터 조회
2. 각 폴더에 content.md 존재 여부 확인
3. content.md가 없으면 DO_NOT_PROCESS 플래그가 있는 더미 파일 생성
4. announcement_pre_processor.py가 이 플래그를 감지하여 건너뜀
"""

import mysql.connector
from pathlib import Path
from datetime import datetime
import sys
import re
from typing import Dict, List, Tuple

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

# 더미 content.md 템플릿
DUMMY_CONTENT_TEMPLATE = """# ARCHIVED - OLD DATA

이 공고는 오래된 데이터로 처리하지 않습니다.
This announcement is archived and will not be processed.

- Archive Date: {archive_date}
- Reason: Data before {cutoff_date}
- Site Code: {site_code}
- Folder ID: {folder_id}
- Post Date: {post_date}
- Original Folder: {folder_name}

DO_NOT_PROCESS
"""


class DummyContentCreator:
    def __init__(self, base_path: str, dry_run: bool = True):
        """
        Args:
            base_path: 프로덕션 데이터 베이스 경로 (예: /data 또는 /mnt/storage)
            dry_run: True면 미리보기만, False면 실제 파일 생성
        """
        self.base_path = Path(base_path)
        self.dry_run = dry_run
        self.stats = {
            'total': 0,
            'content_md_exists': 0,
            'dummy_created': 0,
            'folder_not_found': 0,
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

    def get_old_api_data(self) -> List[Dict]:
        """
        api_url_registry에서 2025-10-30 이전 데이터 조회

        Returns:
            레코드 목록 [{'site_code': ..., 'folder_name': ..., 'post_date': ...}, ...]
        """
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)

            query = f"""
                SELECT
                    site_code,
                    folder_name,
                    post_date,
                    announcement_url,
                    title
                FROM api_url_registry
                WHERE post_date < '{CUTOFF_DATE}'
                ORDER BY site_code, folder_name
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

    def get_folder_path(self, site_code: str, folder_id: str) -> Path:
        """
        프로덕션 환경 폴더 경로 생성

        Args:
            site_code: bizInfo, kStartUp, smes24
            folder_id: 폴더 ID (예: 175424, PBLN_000000000090863)

        Returns:
            전체 경로 (예: /data/api/kStartUp/175424)
        """
        return self.base_path / "api" / site_code / folder_id

    def create_dummy_content(self, folder_path: Path, site_code: str,
                            folder_id: str, folder_name: str, post_date: str) -> bool:
        """
        더미 content.md 파일 생성

        Args:
            folder_path: 폴더 경로
            site_code: 사이트 코드
            folder_id: 폴더 ID
            folder_name: 원본 folder_name
            post_date: 게시 날짜

        Returns:
            생성 성공 여부
        """
        content_md_path = folder_path / "content.md"

        # 더미 내용 생성
        dummy_content = DUMMY_CONTENT_TEMPLATE.format(
            archive_date=datetime.now().strftime('%Y-%m-%d'),
            cutoff_date=CUTOFF_DATE,
            site_code=site_code,
            folder_id=folder_id,
            post_date=post_date,
            folder_name=folder_name
        )

        if self.dry_run:
            print(f"  [DRY RUN] 생성할 파일: {content_md_path}")
            return True
        else:
            try:
                # 폴더가 없으면 생성
                folder_path.mkdir(parents=True, exist_ok=True)

                # 더미 파일 작성
                content_md_path.write_text(dummy_content, encoding='utf-8')
                print(f"  ✅ 생성: {content_md_path}")
                return True
            except Exception as e:
                print(f"  ❌ 생성 실패: {content_md_path} - {e}")
                self.errors_list.append({
                    'path': str(content_md_path),
                    'error': str(e)
                })
                return False

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
                    'content_md_exists': 0,
                    'dummy_created': 0,
                    'folder_not_found': 0,
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

            # 프로덕션 경로 생성
            folder_path = self.get_folder_path(site_code, folder_id)
            content_md_path = folder_path / "content.md"

            # 진행 상황 출력 (100건마다)
            if i % 100 == 0:
                print(f"\n진행: {i}/{len(records)} ({i/len(records)*100:.1f}%)")

            # content.md 존재 여부 확인
            if content_md_path.exists():
                if i <= 10:  # 처음 10건만 상세 출력
                    print(f"⏭️  [{i}/{len(records)}] 건너뜀 (이미 존재): {folder_path.relative_to(self.base_path)}")
                self.stats['content_md_exists'] += 1
                site_stats[site_code]['content_md_exists'] += 1
                continue

            # 폴더 존재 여부 확인
            if not folder_path.exists():
                if i <= 10:
                    print(f"📁 [{i}/{len(records)}] 폴더 없음 (생성 예정): {folder_path.relative_to(self.base_path)}")
                # 폴더가 없어도 생성할 예정이므로 계속 진행

            # 더미 content.md 생성
            if i <= 10:
                print(f"📝 [{i}/{len(records)}] 더미 생성: {folder_path.relative_to(self.base_path)}")

            if self.create_dummy_content(folder_path, site_code, folder_id, folder_name, str(post_date)):
                self.stats['dummy_created'] += 1
                site_stats[site_code]['dummy_created'] += 1
            else:
                self.stats['errors'] += 1
                site_stats[site_code]['errors'] += 1

        # 사이트별 통계 출력
        print("\n" + "=" * 80)
        print("사이트별 통계")
        print("=" * 80)
        for site_code, stats in site_stats.items():
            print(f"\n[{site_code}]")
            print(f"  총 레코드: {stats['total']}건")
            print(f"  content.md 이미 존재: {stats['content_md_exists']}건")
            print(f"  더미 생성: {stats['dummy_created']}건")
            print(f"  에러: {stats['errors']}건")

    def print_summary(self):
        """
        최종 통계 출력
        """
        print("\n" + "=" * 80)
        print("최종 통계")
        print("=" * 80)
        print(f"총 레코드: {self.stats['total']}건")
        print(f"content.md 이미 존재: {self.stats['content_md_exists']}건")
        print(f"더미 생성: {self.stats['dummy_created']}건")
        print(f"폴더 없음: {self.stats['folder_not_found']}건")
        print(f"에러: {self.stats['errors']}건")

        if self.errors_list:
            print(f"\n에러 목록 (최대 10건):")
            for error in self.errors_list[:10]:
                print(f"  - {error}")

        print("\n" + "=" * 80)
        if self.dry_run:
            print("DRY RUN 모드 완료")
            print("실제 파일을 생성하려면 다음 명령을 실행하세요:")
            print("  python create_dummy_content_for_old_api_data.py --execute /data")
        else:
            print("실행 완료")
            print(f"총 {self.stats['dummy_created']}개의 더미 content.md 파일이 생성되었습니다.")
        print("=" * 80)


def main():
    """
    메인 실행 함수
    """
    if len(sys.argv) < 2:
        print("사용법:")
        print("  DRY RUN (미리보기):")
        print("    python create_dummy_content_for_old_api_data.py /data")
        print("")
        print("  실제 실행:")
        print("    python create_dummy_content_for_old_api_data.py --execute /data")
        sys.exit(1)

    # 인자 파싱
    dry_run = True
    base_path = None

    if sys.argv[1] == '--execute':
        dry_run = False
        if len(sys.argv) < 3:
            print("❌ 오류: --execute 옵션 사용 시 데이터 경로를 지정해야 합니다.")
            print("예: python create_dummy_content_for_old_api_data.py --execute /data")
            sys.exit(1)
        base_path = sys.argv[2]
    else:
        base_path = sys.argv[1]

    # 경로 확인
    base_path = Path(base_path).resolve()
    if not base_path.exists():
        print(f"❌ 오류: 경로가 존재하지 않습니다: {base_path}")
        sys.exit(1)

    print("=" * 80)
    print("API Scrap 구 데이터 처리 방지 스크립트")
    print("=" * 80)
    print(f"데이터 경로: {base_path}")
    print(f"기준 날짜: {CUTOFF_DATE} (이전 데이터 처리)")
    print(f"모드: {'DRY RUN (미리보기)' if dry_run else 'EXECUTE (실제 생성)'}")
    print("=" * 80)

    # 확인
    if not dry_run:
        print("\n⚠️  WARNING: 실제 파일을 생성합니다!")
        confirm = input("계속하시겠습니까? (yes/no): ")
        if confirm.lower() != 'yes':
            print("취소되었습니다.")
            sys.exit(0)

    # 처리 시작
    creator = DummyContentCreator(base_path, dry_run)

    # 데이터 조회
    records = creator.get_old_api_data()

    if not records:
        print("처리할 레코드가 없습니다.")
        sys.exit(0)

    # 레코드 처리
    creator.process_records(records)

    # 통계 출력
    creator.print_summary()


if __name__ == '__main__':
    main()
