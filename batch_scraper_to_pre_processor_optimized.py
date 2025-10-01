#!/usr/bin/env python3

"""
최적화된 배치 처리 오케스트레이터
- 타임아웃 문제 해결
- 메모리 효율성 개선
- 실패한 지역만 재처리 옵션
"""

import os
import sys
import argparse
import subprocess
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
import time
import json
import signal
import psutil

class OptimizedBatchProcessor:
    def __init__(self, data_source: str = 'eminwon', date_str: Optional[str] = None,
                 max_workers: int = 2, force: bool = False, attach_force: bool = False,
                 retry_failed: bool = False, timeout: int = 1200):
        """
        Args:
            data_source: 'eminwon' 또는 'homepage'
            date_str: 처리할 날짜 (YYYY-MM-DD 형식)
            max_workers: 병렬 처리 워커 수 (기본값 2로 감소)
            force: 이미 처리된 항목도 다시 처리
            attach_force: 첨부파일 강제 재처리
            retry_failed: 실패한 항목만 재처리
            timeout: 프로세스 타임아웃 (초)
        """
        self.data_source = data_source
        
        if date_str:
            self.target_date = date_str
        else:
            self.target_date = datetime.now().strftime('%Y-%m-%d')
        
        # 데이터 소스에 따른 디렉토리 설정
        if self.data_source == 'eminwon':
            self.base_dir = Path('eminwon_data_new') / self.target_date
        elif self.data_source == 'homepage':
            self.base_dir = Path('scraped_incremental_v2') / self.target_date
        else:
            raise ValueError(f"Invalid data source: {data_source}")
        
        self.max_workers = max_workers
        self.force = force
        self.attach_force = attach_force
        self.retry_failed = retry_failed
        self.timeout = timeout
        
        self.setup_logging()
        
        # 통계
        self.stats = {
            'total_regions': 0,
            'processed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'timeout': 0,
            'errors': [],
            'total_announcements': 0,
            'region_details': [],
            'failed_regions': []
        }
        
        # 실패 기록 파일
        self.failed_regions_file = Path('logs') / f'{self.data_source}_failed_regions_{self.target_date}.json'
    
    def setup_logging(self):
        """로깅 설정"""
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = log_dir / f'{self.data_source}_batch_optimized_{timestamp}.log'
        
        # 포맷터 설정 - 더 간결한 로그
        formatter = logging.Formatter(
            '%(asctime)s - [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # 파일 핸들러
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # 로거 설정
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def get_region_folders(self) -> List[Path]:
        """처리할 지역 폴더 목록 반환"""
        if not self.base_dir.exists():
            self.logger.error(f"디렉토리가 존재하지 않습니다: {self.base_dir}")
            return []
        
        # 실패한 지역만 재처리하는 경우
        if self.retry_failed and self.failed_regions_file.exists():
            with open(self.failed_regions_file, 'r', encoding='utf-8') as f:
                failed_data = json.load(f)
                failed_regions = failed_data.get('failed_regions', [])
                
            if failed_regions:
                self.logger.info(f"실패한 {len(failed_regions)}개 지역만 재처리합니다.")
                region_folders = []
                for region_name in failed_regions:
                    region_path = self.base_dir / region_name
                    if region_path.exists():
                        region_folders.append(region_path)
                return sorted(region_folders)
        
        # 모든 지역 처리
        region_folders = [
            d for d in self.base_dir.iterdir()
            if d.is_dir() and not d.name.startswith('.')
        ]
        
        return sorted(region_folders)
    
    def normalize_site_code(self, site_code: str) -> str:
        """site_code 정규화"""
        normalized = re.sub(r'(시|군|구)$', '', site_code)
        return normalized
    
    def check_memory(self) -> bool:
        """메모리 사용량 체크"""
        memory = psutil.virtual_memory()
        if memory.percent > 85:
            self.logger.warning(f"메모리 사용량 높음: {memory.percent}%")
            return False
        return True
    
    def process_region_with_timeout(self, region_path: Path) -> Dict[str, Any]:
        """타임아웃 처리가 개선된 지역 처리"""
        region_name = region_path.name
        start_time = time.time()
        
        normalized_site_code = self.normalize_site_code(region_name)
        
        result = {
            'region': region_name,
            'normalized_code': normalized_site_code,
            'path': str(region_path),
            'success': False,
            'error': None,
            'processing_time': 0,
            'folders_processed': 0,
            'announcement_count': 0
        }
        
        try:
            # 메모리 체크
            if not self.check_memory():
                self.logger.warning(f"[{region_name}] 메모리 부족으로 대기")
                time.sleep(5)
            
            # 공고 폴더 수 확인
            announcement_folders = [
                d for d in region_path.iterdir()
                if d.is_dir() and not d.name.startswith('.')
            ]
            result['folders_processed'] = len(announcement_folders)
            result['announcement_count'] = len(announcement_folders)
            
            if len(announcement_folders) == 0:
                self.logger.info(f"[{region_name}] 공고가 없어 건너뜀")
                result['skipped'] = True
                self.stats['skipped'] += 1
                return result
            
            self.logger.info(f"[{region_name}] 처리 시작 ({len(announcement_folders)}개 공고)")
            
            # 명령어 구성
            cmd = [
                sys.executable,
                'announcement_pre_processor.py',
                '-d', str(self.base_dir),
                '--site-code', normalized_site_code
            ]
            
            if self.force:
                cmd.append('--force')
            if self.attach_force:
                cmd.append('--attach-force')
            
            # 프로세스 실행 (타임아웃 적용)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid if sys.platform != 'win32' else None
            )
            
            try:
                stdout, stderr = process.communicate(timeout=self.timeout)
                
                if process.returncode == 0:
                    result['success'] = True
                    self.stats['success'] += 1
                    self.logger.info(f"[{region_name}] ✅ 성공")
                    
                    # 처리 완료 마커 생성
                    if not self.retry_failed:
                        marker_file = region_path / '.processed'
                        marker_file.touch()
                else:
                    result['error'] = stderr or stdout
                    self.stats['failed'] += 1
                    self.stats['failed_regions'].append(region_name)
                    self.logger.error(f"[{region_name}] ❌ 실패")
                    
            except subprocess.TimeoutExpired:
                # 프로세스 강제 종료
                if sys.platform != 'win32':
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    process.terminate()
                    
                time.sleep(2)
                if process.poll() is None:
                    process.kill()
                
                result['error'] = f'Timeout ({self.timeout}초 초과)'
                self.stats['timeout'] += 1
                self.stats['failed'] += 1
                self.stats['failed_regions'].append(region_name)
                self.logger.error(f"[{region_name}] ⏱️ 타임아웃")
            
        except Exception as e:
            result['error'] = str(e)
            self.stats['failed'] += 1
            self.stats['failed_regions'].append(region_name)
            self.logger.error(f"[{region_name}] ❌ 오류: {e}")
        
        finally:
            result['processing_time'] = time.time() - start_time
            self.stats['processed'] += 1
            self.stats['total_announcements'] += result['announcement_count']
            
            if result['success'] or result.get('skipped'):
                status = '✅' if result.get('success') else '⏭️'
            else:
                status = '❌'
            
            progress = (self.stats['processed'] / self.stats['total_regions']) * 100
            self.logger.info(
                f"[{progress:5.1f}%] {status} {region_name:20} "
                f"({result['announcement_count']:3}개, {result['processing_time']:.1f}초)"
            )
        
        return result
    
    def save_failed_regions(self):
        """실패한 지역 목록 저장"""
        if self.stats['failed_regions']:
            with open(self.failed_regions_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'date': self.target_date,
                    'source': self.data_source,
                    'failed_regions': self.stats['failed_regions'],
                    'timestamp': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"실패한 지역 목록 저장: {self.failed_regions_file}")
    
    def run(self):
        """메인 실행"""
        self.logger.info('='*60)
        self.logger.info(f'{self.data_source.upper()} 배치 처리 (최적화 버전)')
        self.logger.info(f'날짜: {self.target_date}')
        self.logger.info(f'데이터: {self.base_dir}')
        self.logger.info(f'워커: {self.max_workers}개, 타임아웃: {self.timeout}초')
        
        if self.retry_failed:
            self.logger.info('실패한 항목만 재처리 모드')
        if self.force:
            self.logger.info('강제 재처리 모드')
        if self.attach_force:
            self.logger.info('첨부파일 강제 재처리 모드')
        
        self.logger.info('='*60)
        
        # 처리할 지역 폴더 목록
        region_folders = self.get_region_folders()
        
        if not region_folders:
            self.logger.warning("처리할 지역 폴더가 없습니다")
            return False
        
        self.stats['total_regions'] = len(region_folders)
        self.logger.info(f"처리할 지역: {len(region_folders)}개")
        
        # 병렬 처리
        start_time = time.time()
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.process_region_with_timeout, region): region
                for region in region_folders
            }
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result['success']:
                        self.stats['region_details'].append({
                            'region': result['region'],
                            'code': result.get('normalized_code', ''),
                            'count': result['announcement_count'],
                            'time': result['processing_time']
                        })
                        
                except Exception as e:
                    self.logger.error(f"처리 중 오류: {e}")
        
        # 처리 시간
        total_time = time.time() - start_time
        
        # 최종 통계
        self.logger.info('')
        self.logger.info('='*60)
        self.logger.info('처리 완료 - 최종 통계')
        self.logger.info('='*60)
        self.logger.info(f"전체 지역: {self.stats['total_regions']}개")
        self.logger.info(f"  - 성공: {self.stats['success']}개")
        self.logger.info(f"  - 실패: {self.stats['failed']}개")
        self.logger.info(f"  - 타임아웃: {self.stats['timeout']}개")
        self.logger.info(f"  - 스킵: {self.stats['skipped']}개")
        self.logger.info(f"전체 공고: {self.stats['total_announcements']:,}개")
        self.logger.info(f"처리 시간: {total_time:.1f}초 ({total_time/60:.1f}분)")
        
        # 실패한 지역 표시
        if self.stats['failed_regions']:
            self.logger.info('')
            self.logger.info(f"실패한 지역 ({len(self.stats['failed_regions'])}개):")
            for region in self.stats['failed_regions'][:20]:
                self.logger.info(f"  - {region}")
            
            self.save_failed_regions()
            self.logger.info('')
            self.logger.info("재처리 명령어:")
            self.logger.info(f"python {sys.argv[0]} --source {self.data_source} --date {self.target_date} --retry-failed")
        
        # 결과 저장
        self.save_results(results)
        
        return self.stats['failed'] == 0

    def save_results(self, results: List[Dict]):
        """처리 결과 저장"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        result_file = Path('logs') / f'{self.data_source}_batch_results_{timestamp}.json'
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                'source': self.data_source,
                'date': self.target_date,
                'stats': self.stats,
                'results': results,
                'timestamp': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"결과 파일: {result_file}")

def main():
    parser = argparse.ArgumentParser(
        description='최적화된 배치 처리 오케스트레이터'
    )
    
    parser.add_argument(
        '--source',
        type=str,
        choices=['eminwon', 'homepage'],
        required=True,
        help='데이터 소스'
    )
    
    parser.add_argument(
        '--date',
        type=str,
        help='처리할 날짜 (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=2,
        help='병렬 처리 워커 수 (기본값: 2)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=1200,
        help='프로세스 타임아웃 (초, 기본값: 1200초=20분)'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='이미 처리된 항목도 다시 처리'
    )
    
    parser.add_argument(
        '--attach-force',
        action='store_true',
        help='첨부파일 강제 재처리'
    )
    
    parser.add_argument(
        '--retry-failed',
        action='store_true',
        help='이전 실행에서 실패한 항목만 재처리'
    )
    
    args = parser.parse_args()
    
    processor = OptimizedBatchProcessor(
        data_source=args.source,
        date_str=args.date,
        max_workers=args.workers,
        timeout=args.timeout,
        force=args.force,
        attach_force=args.attach_force,
        retry_failed=args.retry_failed
    )
    
    success = processor.run()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()