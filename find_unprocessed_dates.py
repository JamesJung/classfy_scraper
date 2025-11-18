#!/usr/bin/env python3
"""
incremental 디렉토리에서 미처리된 날짜 폴더를 찾는 스크립트

이 스크립트는:
1. /home/zium/moabojo/incremental/btp/, eminwon/, homepage/ 디렉토리를 스캔
2. 각 날짜 폴더의 공고 개수를 계산
3. DB의 announcement_pre_processing 테이블과 비교
4. 미등록된 데이터가 있는 날짜 폴더를 리포트

사용법:
  python3 find_unprocessed_dates.py [--days N] [--source all|btp|eminwon|homepage]

옵션:
  --days N    : 최근 N일 이내의 폴더만 검사 (기본: 30일)
  --source    : 검사할 소스 (기본: all)
  --report    : 상세 리포트 출력
"""

import os
import sys
import argparse
import mysql.connector
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import json
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


class UnprocessedDataFinder:
    def __init__(self, days=30, source='all', report=False):
        self.days = days
        self.source = source
        self.report = report

        # DB 연결
        self.conn = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT')),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME')
        )
        self.cursor = self.conn.cursor(dictionary=True)

        # 소스별 기본 경로
        self.base_paths = {
            'btp': Path('/home/zium/moabojo/incremental/btp'),
            'eminwon': Path('/home/zium/moabojo/incremental/eminwon'),
            'homepage': Path('/home/zium/moabojo/incremental/homepage')
        }

        # 결과 저장
        self.results = {
            'btp': [],
            'eminwon': [],
            'homepage': []
        }

    def get_date_folders(self, source_name):
        """특정 소스의 날짜 폴더 목록 반환"""
        base_path = self.base_paths[source_name]

        if not base_path.exists():
            print(f"⚠️  경로가 존재하지 않음: {base_path}")
            return []

        date_folders = []
        cutoff_date = datetime.now() - timedelta(days=self.days)

        for item in base_path.iterdir():
            if not item.is_dir():
                continue

            # 날짜 폴더 형식 파싱 (YYYY-MM-DD 또는 YYYYMMDD)
            folder_name = item.name
            try:
                if '-' in folder_name:
                    # YYYY-MM-DD 형식
                    folder_date = datetime.strptime(folder_name, '%Y-%m-%d')
                elif len(folder_name) == 8 and folder_name.isdigit():
                    # YYYYMMDD 형식
                    folder_date = datetime.strptime(folder_name, '%Y%m%d')
                else:
                    continue

                # 최근 N일 이내인지 확인
                if folder_date >= cutoff_date:
                    date_folders.append({
                        'path': item,
                        'date_str': folder_name,
                        'date': folder_date
                    })
            except ValueError:
                continue

        return sorted(date_folders, key=lambda x: x['date'], reverse=True)

    def count_folder_announcements(self, date_folder_path):
        """날짜 폴더 내의 공고 개수 계산"""
        total = 0
        site_counts = {}

        if not date_folder_path.exists():
            return total, site_counts

        for site_folder in date_folder_path.iterdir():
            if not site_folder.is_dir() or site_folder.name.startswith('.'):
                continue

            # 사이트 폴더 내의 공고 폴더 개수 (숫자로 시작하는 폴더)
            announcement_folders = [
                d for d in site_folder.iterdir()
                if d.is_dir() and not d.name.startswith('.')
            ]

            count = len(announcement_folders)
            if count > 0:
                site_counts[site_folder.name] = count
                total += count

        return total, site_counts

    def count_db_announcements(self, date_str, site_code=None):
        """
        DB에 등록된 공고 개수 계산

        content_md IS NOT NULL 조건을 사용하여 실제로 처리 완료된 공고만 카운트합니다.
        created_at 날짜 기준은 재처리 시 부정확할 수 있으므로,
        추가로 folder_name 패턴도 확인합니다.

        Args:
            date_str: 날짜 문자열 (YYYY-MM-DD 또는 YYYYMMDD)
            site_code: 사이트 코드 (None이면 모든 사이트)

        Returns:
            DB에 등록된 공고 개수
        """
        # 날짜 형식 변환 (YYYYMMDD -> YYYY-MM-DD)
        if '-' in date_str:
            db_date = date_str
            folder_date = date_str.replace('-', '')  # YYYYMMDD for folder pattern
        else:
            db_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            folder_date = date_str

        if site_code:
            # content_md가 있는 공고만 카운트 (실제 처리 완료)
            # created_at 날짜 기준 OR folder_name 패턴 기준 (재처리 대응)
            query = """
                SELECT COUNT(*) as count
                FROM announcement_pre_processing
                WHERE content_md IS NOT NULL
                    AND site_code = %s
                    AND (
                        DATE(created_at) = %s
                        OR folder_name LIKE CONCAT(%s, '_%')
                    )
            """
            self.cursor.execute(query, (site_code, db_date, folder_date))
        else:
            query = """
                SELECT COUNT(*) as count
                FROM announcement_pre_processing
                WHERE content_md IS NOT NULL
                    AND (
                        DATE(created_at) = %s
                        OR folder_name LIKE CONCAT(%s, '_%')
                    )
            """
            self.cursor.execute(query, (db_date, folder_date))

        result = self.cursor.fetchone()
        return result['count'] if result else 0

    def check_source(self, source_name):
        """특정 소스의 미처리 데이터 확인"""
        print(f"\n{'='*80}")
        print(f"【{source_name.upper()}】 미처리 데이터 검사")
        print(f"{'='*80}")

        date_folders = self.get_date_folders(source_name)

        if not date_folders:
            print(f"  검사할 날짜 폴더가 없습니다.")
            return

        print(f"  최근 {self.days}일 이내 날짜 폴더: {len(date_folders)}개\n")

        unprocessed = []

        for folder_info in date_folders:
            folder_path = folder_info['path']
            date_str = folder_info['date_str']

            # 폴더 내 공고 개수 계산
            folder_count, site_counts = self.count_folder_announcements(folder_path)

            # DB 내 공고 개수 계산
            db_count = self.count_db_announcements(date_str)

            # 차이 계산
            diff = folder_count - db_count

            if diff > 0 or self.report:
                status = "❌ 미등록" if diff > 0 else "✅ 완료"
                print(f"  {date_str}: {status}")
                print(f"    폴더: {folder_count:4d}개 | DB: {db_count:4d}개 | 차이: {diff:4d}개")

                if diff > 0:
                    unprocessed.append({
                        'date': date_str,
                        'folder_count': folder_count,
                        'db_count': db_count,
                        'diff': diff,
                        'site_counts': site_counts
                    })

                    if self.report and site_counts:
                        print(f"    사이트별 상세:")
                        for site, count in sorted(site_counts.items(), key=lambda x: -x[1])[:10]:
                            site_db_count = self.count_db_announcements(date_str, site)
                            site_diff = count - site_db_count
                            if site_diff > 0:
                                print(f"      - {site:<20}: 폴더 {count:3d}개 | DB {site_db_count:3d}개 | 차이 {site_diff:3d}개")

        self.results[source_name] = unprocessed

        if unprocessed:
            print(f"\n  ⚠️  미처리 날짜: {len(unprocessed)}개")
            print(f"  📊 미등록 공고: {sum(d['diff'] for d in unprocessed):,}개")
        else:
            print(f"\n  ✅ 모든 데이터가 처리되었습니다.")

    def generate_report(self):
        """최종 리포트 생성"""
        print(f"\n{'='*80}")
        print("【최종 요약】")
        print(f"{'='*80}\n")

        total_unprocessed_dates = 0
        total_unprocessed_announcements = 0

        for source_name, unprocessed in self.results.items():
            if unprocessed:
                count = len(unprocessed)
                announcements = sum(d['diff'] for d in unprocessed)
                total_unprocessed_dates += count
                total_unprocessed_announcements += announcements

                print(f"  {source_name.upper():<10}: {count}개 날짜, {announcements:,}개 공고 미등록")

        print(f"\n  {'='*76}")
        print(f"  총계        : {total_unprocessed_dates}개 날짜, {total_unprocessed_announcements:,}개 공고 미등록")
        print(f"  {'='*76}")

        if total_unprocessed_announcements > 0:
            print(f"\n  ⚠️  DB에 등록되지 않은 공고가 {total_unprocessed_announcements:,}개 있습니다!")
            print(f"\n  💡 재처리 명령어:")
            print(f"     python3 batch_reprocess_dates.py --auto")
        else:
            print(f"\n  ✅ 모든 데이터가 DB에 등록되었습니다!")

    def export_json(self, output_file='unprocessed_dates.json'):
        """결과를 JSON 파일로 저장"""
        output = {
            'scan_date': datetime.now().isoformat(),
            'days_scanned': self.days,
            'results': self.results
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False, default=str)

        print(f"\n  📄 결과 저장: {output_file}")

    def run(self):
        """메인 실행"""
        print(f"{'='*80}")
        print(f"미처리 데이터 검사 시작")
        print(f"{'='*80}")
        print(f"  검사 기간: 최근 {self.days}일")
        print(f"  검사 대상: {self.source}")

        sources = ['btp', 'eminwon', 'homepage'] if self.source == 'all' else [self.source]

        for source_name in sources:
            self.check_source(source_name)

        self.generate_report()
        self.export_json()

        self.cursor.close()
        self.conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='incremental 디렉토리의 미처리 데이터 검사',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='검사할 기간 (일 단위, 기본: 30일)'
    )

    parser.add_argument(
        '--source',
        choices=['all', 'btp', 'eminwon', 'homepage'],
        default='all',
        help='검사할 소스 (기본: all)'
    )

    parser.add_argument(
        '--report',
        action='store_true',
        help='상세 리포트 출력'
    )

    args = parser.parse_args()

    finder = UnprocessedDataFinder(
        days=args.days,
        source=args.source,
        report=args.report
    )

    finder.run()


if __name__ == '__main__':
    main()
