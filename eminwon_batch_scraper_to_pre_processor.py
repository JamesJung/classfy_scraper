#!/usr/bin/env python3

"""
Eminwon 배치 처리 오케스트레이터

eminwon_data_new/YYYY-MM-DD 폴더 하위의 모든 지역 데이터를
announcement_pre_processor.py로 병렬 처리하는 프로그램
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

class EminwonBatchProcessor:
    def __init__(self, date_str: Optional[str] = None, max_workers: int = 5, force: bool = False, attach_force: bool = False):
        """
        Args:
            date_str: 처리할 날짜 (YYYY-MM-DD 형식). None이면 오늘 날짜
            max_workers: 병렬 처리 워커 수
            force: 이미 처리된 항목도 다시 처리
            attach_force: 첨부파일 강제 재처리
        """
        # 날짜 설정
        if date_str:
            self.target_date = date_str
        else:
            self.target_date = datetime.now().strftime('%Y-%m-%d')
        
        # 기본 디렉토리
        self.base_dir = Path('eminwon_data_new') / self.target_date
        
        # 병렬 처리 설정
        self.max_workers = max_workers
        
        # 처리 옵션
        self.force = force
        self.attach_force = attach_force
        
        # 로깅 설정
        self.setup_logging()
        
        # 통계
        self.stats = {
            'total_regions': 0,
            'processed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'errors': [],
            'total_announcements': 0,  # 전체 공고 수
            'region_details': []  # 지역별 상세 정보
        }
    
    def setup_logging(self):
        """로깅 설정"""
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f'eminwon_batch_{self.target_date}.log'
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_file, encoding='utf-8')
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def get_region_folders(self) -> List[Path]:
        """처리할 지역 폴더 목록 반환"""
        if not self.base_dir.exists():
            self.logger.error(f"디렉토리가 존재하지 않습니다: {self.base_dir}")
            return []
        
        # 하위 디렉토리만 추출 (지역 폴더)
        region_folders = [
            d for d in self.base_dir.iterdir() 
            if d.is_dir() and not d.name.startswith('.')
        ]
        
        return sorted(region_folders)
    
    def check_already_processed(self, region_path: Path) -> bool:
        """이미 처리되었는지 확인"""
        # announcement_prv_processing 테이블에서 확인하는 로직 추가 가능
        # 여기서는 간단히 처리 결과 파일 존재 여부로 확인
        
        if self.force:
            return False
        
        # 처리 완료 마커 파일 확인 (예시)
        marker_file = region_path / '.processed'
        if marker_file.exists():
            # 마커 파일의 날짜가 오늘이면 스킵
            mtime = datetime.fromtimestamp(marker_file.stat().st_mtime)
            if mtime.date() == datetime.now().date():
                return True
        
        return False
    
    def normalize_site_code(self, site_code: str) -> str:
        """site_code 정규화 - 시/군/구 제거"""
        # 끝에 있는 시/군/구 제거
        normalized = re.sub(r'(시|군|구)$', '', site_code)
        return normalized
    
    def process_region(self, region_path: Path) -> Dict[str, Any]:
        """단일 지역 처리"""
        region_name = region_path.name
        start_time = time.time()
        
        # site_code 정규화 (시/군/구 제거)
        normalized_site_code = self.normalize_site_code(region_name)
        
        result = {
            'region': region_name,
            'normalized_code': normalized_site_code,  # 정규화된 코드 추가
            'path': str(region_path),
            'success': False,
            'error': None,
            'processing_time': 0,
            'folders_processed': 0,
            'announcement_count': 0  # 공고 수 추가
        }
        
        try:
            # 이미 처리되었는지 확인
            if self.check_already_processed(region_path):
                self.logger.info(f"[{region_name}] 이미 처리됨 - 스킵")
                result['skipped'] = True
                self.stats['skipped'] += 1
                return result
            
            self.logger.info(f"[{region_name}] 처리 시작... (site_code: {normalized_site_code})")
            
            # 지역 폴더 내 공고 폴더 수 확인
            announcement_folders = [
                d for d in region_path.iterdir()
                if d.is_dir() and not d.name.startswith('.')
            ]
            result['folders_processed'] = len(announcement_folders)
            result['announcement_count'] = len(announcement_folders)
            self.stats['total_announcements'] += len(announcement_folders)
            
            # announcement_pre_processor.py 실행
            # 부모 디렉토리를 -d 파라미터로 전달
            cmd = [
                sys.executable,  # 현재 Python 인터프리터 사용
                'announcement_pre_processor.py',
                '-d', str(self.base_dir),  # 부모 디렉토리 (eminwon_data_new/2025-09-22)
                '--site-code', normalized_site_code  # 정규화된 site_code 사용 (예: 함양)
            ]
            
            # 옵션 추가
            if self.force:
                cmd.append('--force')
            if self.attach_force:
                cmd.append('--attach-force')
            
            # 프로세스 실행
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5분 타임아웃
            )
            
            if process.returncode == 0:
                result['success'] = True
                self.stats['success'] += 1
                self.logger.info(f"[{region_name}] ✅ 처리 완료 ({len(announcement_folders)}개 폴더)")
                
                # 처리 완료 마커 생성
                marker_file = region_path / '.processed'
                marker_file.touch()
            else:
                result['error'] = process.stderr or process.stdout
                self.stats['failed'] += 1
                self.stats['errors'].append({
                    'region': region_name,
                    'error': result['error'][:500]  # 에러 메시지 일부만 저장
                })
                self.logger.error(f"[{region_name}] ❌ 처리 실패: {result['error'][:200]}")
            
        except subprocess.TimeoutExpired:
            result['error'] = 'Timeout (5분 초과)'
            self.stats['failed'] += 1
            self.stats['errors'].append({
                'region': region_name,
                'error': 'Timeout'
            })
            self.logger.error(f"[{region_name}] ⏱️  타임아웃")
            
        except Exception as e:
            result['error'] = str(e)
            self.stats['failed'] += 1
            self.stats['errors'].append({
                'region': region_name,
                'error': str(e)
            })
            self.logger.error(f"[{region_name}] ❌ 오류: {e}")
        
        finally:
            result['processing_time'] = time.time() - start_time
            self.stats['processed'] += 1
        
        return result
    
    def run(self):
        """메인 실행"""
        self.logger.info('='*80)
        self.logger.info(f'Eminwon 배치 처리 시작 - {self.target_date}')
        self.logger.info('='*80)
        
        # 처리할 지역 폴더 목록
        region_folders = self.get_region_folders()
        
        if not region_folders:
            self.logger.warning(f"처리할 지역 폴더가 없습니다: {self.base_dir}")
            return False
        
        self.stats['total_regions'] = len(region_folders)
        self.logger.info(f"처리할 지역: {len(region_folders)}개")
        self.logger.info(f"병렬 워커 수: {self.max_workers}개")
        
        if self.force:
            self.logger.info("강제 재처리 모드 활성화")
        if self.attach_force:
            self.logger.info("첨부파일 강제 재처리 모드 활성화")
        
        # 병렬 처리
        start_time = time.time()
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 작업 제출
            futures = {
                executor.submit(self.process_region, region): region 
                for region in region_folders
            }
            
            # 진행 상황 모니터링
            self.logger.info(f"\n처리 진행 중...")
            for future in as_completed(futures):
                region = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    # 진행 상황 출력
                    progress = (self.stats['processed'] / self.stats['total_regions']) * 100
                    status = '✅' if result.get('success') else ('⏭️' if result.get('skipped') else '❌')
                    announcement_count = result.get('announcement_count', 0)
                    
                    # 지역별 상세 정보 저장
                    if announcement_count > 0 or result.get('success'):
                        self.stats['region_details'].append({
                            'region': result['region'],
                            'code': result.get('normalized_code', ''),
                            'count': announcement_count,
                            'status': 'success' if result.get('success') else 'skipped'
                        })
                    
                    self.logger.info(
                        f"[{progress:5.1f}%] {status} {result['region']:20} "
                        f"({announcement_count:3}개 공고, "
                        f"{result['processing_time']:.1f}초)"
                    )
                    
                except Exception as e:
                    self.logger.error(f"처리 중 오류 ({region.name}): {e}")
        
        # 처리 시간
        total_time = time.time() - start_time
        
        # 최종 통계
        self.logger.info('\n' + '='*80)
        self.logger.info('처리 완료 - 최종 통계')
        self.logger.info('='*80)
        self.logger.info(f"날짜: {self.target_date}")
        self.logger.info(f"전체 지역: {self.stats['total_regions']}개")
        self.logger.info(f"처리 완료: {self.stats['processed']}개")
        self.logger.info(f"  - 성공: {self.stats['success']}개")
        self.logger.info(f"  - 실패: {self.stats['failed']}개")
        self.logger.info(f"  - 스킵: {self.stats['skipped']}개")
        self.logger.info(f"전체 공고 수: {self.stats['total_announcements']:,}개")
        self.logger.info(f"처리 시간: {total_time:.1f}초 ({total_time/60:.1f}분)")
        self.logger.info(f"평균 처리 시간: {total_time/max(self.stats['processed'], 1):.1f}초/지역")
        
        # 지역별 공고 수 상위 10개 표시
        if self.stats['region_details']:
            self.logger.info('\n지역별 공고 수 (상위 10개):')
            sorted_regions = sorted(self.stats['region_details'], 
                                  key=lambda x: x['count'], reverse=True)
            for region_info in sorted_regions[:10]:
                self.logger.info(
                    f"  - {region_info['region']:15} ({region_info['code']:10}): "
                    f"{region_info['count']:4}개 공고"
                )
        
        # 에러가 있으면 출력
        if self.stats['errors']:
            self.logger.info('\n오류 상세:')
            for error in self.stats['errors'][:10]:  # 최대 10개만 표시
                self.logger.error(f"  - {error['region']}: {error['error'][:100]}")
        
        # 결과 저장
        self.save_results(results)
        
        self.logger.info('='*80)
        
        return self.stats['failed'] == 0
    
    def save_results(self, results: List[Dict]):
        """처리 결과 저장"""
        result_file = Path('logs') / f'eminwon_batch_results_{self.target_date}.json'
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                'date': self.target_date,
                'stats': self.stats,
                'results': results,
                'timestamp': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"결과 파일 저장: {result_file}")

def main():
    parser = argparse.ArgumentParser(
        description='Eminwon 배치 처리 오케스트레이터',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 오늘 날짜 데이터 처리
  python eminwon_batch_processor.py
  
  # 특정 날짜 데이터 처리
  python eminwon_batch_processor.py --date 2025-09-22
  
  # 워커 수 조정
  python eminwon_batch_processor.py --workers 10
  
  # 강제 재처리
  python eminwon_batch_processor.py --force --attach-force
        """
    )
    
    parser.add_argument(
        '--date',
        type=str,
        help='처리할 날짜 (YYYY-MM-DD 형식). 기본값: 오늘'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=5,
        help='병렬 처리 워커 수 (기본값: 5)'
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
        '--yesterday',
        action='store_true',
        help='어제 날짜 데이터 처리'
    )
    
    args = parser.parse_args()
    
    # 날짜 결정
    if args.yesterday:
        date_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        date_str = args.date
    
    # 프로세서 실행
    processor = EminwonBatchProcessor(
        date_str=date_str,
        max_workers=args.workers,
        force=args.force,
        attach_force=args.attach_force
    )
    
    success = processor.run()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()