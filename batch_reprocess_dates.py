#!/usr/bin/env python3
"""
미처리 날짜의 데이터를 일괄 재처리하는 스크립트

이 스크립트는:
1. find_unprocessed_dates.py의 결과 파일(unprocessed_dates.json)을 읽음
2. 또는 지정된 날짜 범위를 재처리
3. batch_scraper_to_pre_processor.py를 호출하여 미처리 데이터를 DB에 등록

사용법:
  # JSON 파일 기반 자동 재처리
  python3 batch_reprocess_dates.py --auto

  # 특정 날짜 재처리
  python3 batch_reprocess_dates.py --date 2025-11-11

  # 날짜 범위 재처리
  python3 batch_reprocess_dates.py --start 2025-11-11 --end 2025-11-13

  # 특정 소스만 재처리
  python3 batch_reprocess_dates.py --auto --source btp

옵션:
  --auto          : unprocessed_dates.json 파일 기반 자동 재처리
  --date DATE     : 특정 날짜 재처리 (YYYY-MM-DD)
  --start DATE    : 시작 날짜 (YYYY-MM-DD)
  --end DATE      : 종료 날짜 (YYYY-MM-DD)
  --source        : 재처리할 소스 (all|btp|eminwon|homepage)
  --force         : 이미 처리된 항목도 다시 처리
  --dry-run       : 실제 실행 없이 계획만 출력
"""

import os
import sys
import argparse
import subprocess
import json
from pathlib import Path
from datetime import datetime, timedelta
import time


class BatchReprocessor:
    def __init__(self, source='all', force=False, dry_run=False):
        self.source = source
        self.force = force
        self.dry_run = dry_run
        self.script_dir = Path(__file__).parent
        self.batch_processor = self.script_dir / 'batch_scraper_to_pre_processor.py'

        # 통계
        self.stats = {
            'total_dates': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }

    def load_unprocessed_dates(self, json_file='unprocessed_dates.json'):
        """find_unprocessed_dates.py 결과 파일 로드"""
        json_path = self.script_dir / json_file

        if not json_path.exists():
            print(f"❌ 파일을 찾을 수 없습니다: {json_path}")
            print(f"\n먼저 다음 명령어를 실행하세요:")
            print(f"  python3 find_unprocessed_dates.py")
            return None

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return data

    def process_date(self, source_name, date_str):
        """특정 날짜의 데이터를 재처리"""
        print(f"\n{'='*80}")
        print(f"처리 시작: {source_name} / {date_str}")
        print(f"{'='*80}")

        # 날짜 형식 변환 (YYYYMMDD -> YYYY-MM-DD)
        if '-' not in date_str and len(date_str) == 8:
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        else:
            formatted_date = date_str

        # 소스 이름 매핑 (btp -> scraper)
        # batch_scraper_to_pre_processor.py는 'scraper'를 사용
        mapped_source = 'scraper' if source_name == 'btp' else source_name

        # batch_scraper_to_pre_processor.py 명령어 구성
        cmd = [
            'python3',
            str(self.batch_processor),
            '--source', mapped_source,
            '--date', formatted_date
        ]

        if self.force:
            cmd.append('--force')

        print(f"실행 명령어: {' '.join(cmd)}")

        if self.dry_run:
            print(f"[DRY-RUN] 실제 실행 건너뜀")
            return True

        # 실행
        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1시간 타임아웃
            )

            elapsed_time = time.time() - start_time

            if result.returncode == 0:
                print(f"✅ 성공 ({elapsed_time:.1f}초)")
                return True
            else:
                print(f"❌ 실패 (Exit Code: {result.returncode}, {elapsed_time:.1f}초)")
                if result.stderr:
                    print(f"\nStderr:\n{result.stderr[:500]}")
                if result.stdout:
                    print(f"\nStdout:\n{result.stdout[:500]}")

                self.stats['errors'].append({
                    'source': source_name,
                    'date': date_str,
                    'exit_code': result.returncode,
                    'stderr': result.stderr[:200] if result.stderr else '',
                    'stdout': result.stdout[:200] if result.stdout else ''
                })
                return False

        except subprocess.TimeoutExpired:
            print(f"❌ 타임아웃 (1시간 초과)")
            self.stats['errors'].append({
                'source': source_name,
                'date': date_str,
                'error': 'Timeout (1시간 초과)'
            })
            return False

        except Exception as e:
            print(f"❌ 예외 발생: {e}")
            self.stats['errors'].append({
                'source': source_name,
                'date': date_str,
                'error': str(e)
            })
            return False

    def reprocess_auto(self):
        """JSON 파일 기반 자동 재처리"""
        print(f"{'='*80}")
        print(f"자동 재처리 모드")
        print(f"{'='*80}")

        data = self.load_unprocessed_dates()
        if not data:
            return

        print(f"\n검사 날짜: {data.get('scan_date', 'Unknown')}")
        print(f"검사 기간: 최근 {data.get('days_scanned', 'Unknown')}일")

        results = data.get('results', {})
        sources = [self.source] if self.source != 'all' else ['btp', 'eminwon', 'homepage']

        total_dates = 0
        for source_name in sources:
            unprocessed = results.get(source_name, [])
            total_dates += len(unprocessed)

        self.stats['total_dates'] = total_dates

        if total_dates == 0:
            print(f"\n✅ 재처리할 날짜가 없습니다!")
            return

        print(f"\n재처리 대상: {total_dates}개 날짜")

        if self.dry_run:
            print(f"\n[DRY-RUN 모드] 실제 실행 없이 계획만 출력합니다.\n")

        # 소스별 처리
        for source_name in sources:
            unprocessed = results.get(source_name, [])

            if not unprocessed:
                continue

            print(f"\n{'='*80}")
            print(f"【{source_name.upper()}】 {len(unprocessed)}개 날짜 재처리")
            print(f"{'='*80}")

            for item in unprocessed:
                date_str = item['date']
                diff = item['diff']

                print(f"\n[{source_name}] {date_str} - 미등록 {diff}개 공고")

                success = self.process_date(source_name, date_str)

                if success:
                    self.stats['success'] += 1
                else:
                    self.stats['failed'] += 1

                # 각 처리 사이에 짧은 딜레이
                if not self.dry_run:
                    time.sleep(2)

    def reprocess_date(self, date_str):
        """특정 날짜 재처리"""
        print(f"{'='*80}")
        print(f"날짜 재처리: {date_str}")
        print(f"{'='*80}")

        sources = [self.source] if self.source != 'all' else ['btp', 'eminwon', 'homepage']

        self.stats['total_dates'] = len(sources)

        for source_name in sources:
            success = self.process_date(source_name, date_str)

            if success:
                self.stats['success'] += 1
            else:
                self.stats['failed'] += 1

            if not self.dry_run:
                time.sleep(2)

    def reprocess_date_range(self, start_date, end_date):
        """날짜 범위 재처리"""
        print(f"{'='*80}")
        print(f"날짜 범위 재처리: {start_date} ~ {end_date}")
        print(f"{'='*80}")

        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        if start > end:
            print(f"❌ 시작 날짜가 종료 날짜보다 늦습니다!")
            return

        sources = [self.source] if self.source != 'all' else ['btp', 'eminwon', 'homepage']

        # 날짜 목록 생성
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)

        self.stats['total_dates'] = len(dates) * len(sources)

        print(f"\n재처리 대상: {len(dates)}개 날짜 × {len(sources)}개 소스 = {self.stats['total_dates']}개")

        if self.dry_run:
            print(f"\n[DRY-RUN 모드] 실제 실행 없이 계획만 출력합니다.\n")

        for date_str in dates:
            for source_name in sources:
                success = self.process_date(source_name, date_str)

                if success:
                    self.stats['success'] += 1
                else:
                    self.stats['failed'] += 1

                if not self.dry_run:
                    time.sleep(2)

    def print_summary(self):
        """최종 요약 출력"""
        print(f"\n{'='*80}")
        print(f"【재처리 완료】")
        print(f"{'='*80}")

        print(f"\n  총 대상   : {self.stats['total_dates']}개")
        print(f"  성공      : {self.stats['success']}개")
        print(f"  실패      : {self.stats['failed']}개")
        print(f"  건너뜀    : {self.stats['skipped']}개")

        if self.stats['errors']:
            print(f"\n  ❌ 실패 상세:")
            for err in self.stats['errors'][:10]:
                source = err.get('source', 'Unknown')
                date = err.get('date', 'Unknown')
                error = err.get('error', err.get('stderr', 'Unknown error'))
                print(f"    - [{source}] {date}: {error[:100]}")

            if len(self.stats['errors']) > 10:
                print(f"    ... 외 {len(self.stats['errors']) - 10}개")

        if self.stats['success'] == self.stats['total_dates']:
            print(f"\n  ✅ 모든 데이터 재처리 성공!")
        elif self.stats['failed'] > 0:
            print(f"\n  ⚠️  일부 데이터 재처리 실패")
            print(f"\n  💡 재시도:")
            print(f"     python3 batch_reprocess_dates.py --auto --force")


def main():
    parser = argparse.ArgumentParser(
        description='미처리 데이터 일괄 재처리',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # JSON 파일 기반 자동 재처리
  python3 batch_reprocess_dates.py --auto

  # 특정 날짜 재처리
  python3 batch_reprocess_dates.py --date 2025-11-11

  # 날짜 범위 재처리
  python3 batch_reprocess_dates.py --start 2025-11-11 --end 2025-11-13

  # Dry-run (실행 계획만 출력)
  python3 batch_reprocess_dates.py --auto --dry-run

  # 강제 재처리 (이미 처리된 항목도 재처리)
  python3 batch_reprocess_dates.py --date 2025-11-11 --force
        """
    )

    parser.add_argument(
        '--auto',
        action='store_true',
        help='unprocessed_dates.json 파일 기반 자동 재처리'
    )

    parser.add_argument(
        '--date',
        type=str,
        help='재처리할 날짜 (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--start',
        type=str,
        help='시작 날짜 (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--end',
        type=str,
        help='종료 날짜 (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--source',
        choices=['all', 'btp', 'eminwon', 'homepage'],
        default='all',
        help='재처리할 소스 (기본: all)'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='이미 처리된 항목도 다시 처리'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='실제 실행 없이 계획만 출력'
    )

    args = parser.parse_args()

    # 옵션 검증
    if not (args.auto or args.date or (args.start and args.end)):
        parser.error("--auto, --date, 또는 --start/--end 중 하나를 지정해야 합니다.")

    if (args.start and not args.end) or (args.end and not args.start):
        parser.error("--start와 --end는 함께 사용해야 합니다.")

    # 재처리 실행
    reprocessor = BatchReprocessor(
        source=args.source,
        force=args.force,
        dry_run=args.dry_run
    )

    if args.auto:
        reprocessor.reprocess_auto()
    elif args.date:
        reprocessor.reprocess_date(args.date)
    elif args.start and args.end:
        reprocessor.reprocess_date_range(args.start, args.end)

    reprocessor.print_summary()


if __name__ == '__main__':
    main()
