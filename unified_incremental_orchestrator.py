#!/usr/bin/env python3

"""
통합 증분 수집 오케스트레이터
안양시, 원주시 등 일반 스크래퍼를 통합 관리하는 시스템
"""

import os
import json
import subprocess
import mysql.connector
from pathlib import Path
from datetime import datetime
import logging
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import unicodedata

class UnifiedIncrementalOrchestrator:
    def __init__(self, test_mode=False, specific_sites=None, verbose=False):
        self.test_mode = test_mode
        self.specific_sites = specific_sites
        self.verbose = verbose
        
        # 환경 변수 로드
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        
        # DB 설정
        self.db_config = {
            'host': os.environ.get('DB_HOST'),
            'user': os.environ.get('DB_USER'),
            'password': os.environ.get('DB_PASSWORD'),
            'database': os.environ.get('DB_NAME'),
            'port': int(os.environ.get('DB_PORT', 3306)),
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci'
        }
        
        # 설정 파일 로드
        config_path = Path('node/scraper/scrapers_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            self.configs = json.load(f)
        
        # 출력 디렉토리
        today = datetime.now().strftime('%Y-%m-%d')
        self.output_base = Path('unified_data') / today
        
        # Node.js 스크립트 경로
        self.list_collector_path = 'node/scraper/unified_list_collector.js'
        self.detail_scraper_path = 'node/scraper/unified_detail_scraper.js'
        
        # 통계
        self.stats = {
            'total_checked': 0,
            'new_found': 0,
            'downloaded': 0,
            'errors': 0,
            'duplicates': 0
        }
        
        # 로깅 설정
        self.setup_logging()
    
    def setup_logging(self):
        """로깅 설정"""
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        log_level = logging.DEBUG if self.verbose else logging.INFO
        
        # 로그 디렉토리 생성
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        # 로그 파일명
        log_file = log_dir / f'unified_orchestrator_{datetime.now().strftime("%Y%m%d")}.log'
        
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_file, encoding='utf-8')
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def check_node_dependencies(self):
        """Node.js 및 스크립트 확인"""
        try:
            # Node.js 버전 확인
            result = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise Exception('Node.js not found')
            self.logger.info(f'Node.js version: {result.stdout.strip()}')
            
            # 스크립트 파일 확인
            if not Path(self.list_collector_path).exists():
                raise Exception(f'List collector not found: {self.list_collector_path}')
            if not Path(self.detail_scraper_path).exists():
                raise Exception(f'Detail scraper not found: {self.detail_scraper_path}')
            
            return True
        except Exception as e:
            self.logger.error(f'Dependency check failed: {e}')
            return False
    
    def collect_list(self, site_code, pages=3):
        """Node.js 리스트 수집기 호출"""
        self.logger.info(f'[{site_code}] 리스트 수집 시작 ({pages} 페이지)')
        
        cmd = [
            'node',
            self.list_collector_path,
            '--site', site_code,
            '--pages', str(pages)
        ]
        
        if self.verbose:
            cmd.append('--verbose')
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            # stderr에서 디버그 출력 표시 (verbose 모드)
            if self.verbose and result.stderr:
                for line in result.stderr.split('\n'):
                    if line.strip():
                        self.logger.debug(f'[{site_code}] {line}')
            
            if result.returncode != 0:
                self.logger.error(f'[{site_code}] 리스트 수집 실패')
                return []
            
            # stdout에서 JSON 파싱
            data = json.loads(result.stdout)
            if data['status'] == 'success':
                self.logger.info(f'[{site_code}] {data["count"]}개 공고 수집 완료')
                return data['data']
            else:
                self.logger.error(f'[{site_code}] 수집 오류: {data.get("error")}')
                return []
                
        except subprocess.TimeoutExpired:
            self.logger.error(f'[{site_code}] 리스트 수집 타임아웃')
            return []
        except json.JSONDecodeError as e:
            self.logger.error(f'[{site_code}] JSON 파싱 오류: {e}')
            return []
        except Exception as e:
            self.logger.error(f'[{site_code}] 수집 중 오류: {e}')
            return []
    
    def check_url_exists_in_db(self, site_code, url):
        """DB에서 URL 중복 체크"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            # NFC 정규화
            normalized_url = unicodedata.normalize('NFC', url)
            
            cursor.execute(
                """
                SELECT id FROM unified_url_registry 
                WHERE site_code = %s AND announcement_url = %s
                """,
                (site_code, normalized_url)
            )
            
            result = cursor.fetchone()
            return result is not None
            
        finally:
            cursor.close()
            conn.close()
    
    def filter_new_announcements(self, site_code, announcements):
        """새 공고만 필터링"""
        new_items = []
        duplicate_count = 0
        
        for ann in announcements:
            url = ann.get('url', '')
            if not url:
                continue
            
            if not self.check_url_exists_in_db(site_code, url):
                new_items.append(ann)
                self.stats['new_found'] += 1
                if self.verbose:
                    self.logger.info(f'  ✅ NEW: [{ann["id"]}] {ann["title"][:50]}...')
            else:
                duplicate_count += 1
                self.stats['duplicates'] += 1
                if self.verbose:
                    self.logger.debug(f'  ⏭️  DUPLICATE: [{ann["id"]}] {ann["title"][:50]}...')
        
        self.logger.info(f'[{site_code}] 필터링 결과: 신규 {len(new_items)}개, 중복 {duplicate_count}개')
        return new_items
    
    def download_detail(self, site_code, announcement, index):
        """상세 페이지 다운로드"""
        # 폴더명 생성
        safe_title = ''.join(c for c in announcement['title'] if c.isalnum() or c in ' -_')[:100]
        folder_name = f"{str(index).zfill(3)}_{announcement['id']}_{safe_title}"
        output_dir = self.output_base / site_code
        
        cmd = [
            'node',
            self.detail_scraper_path,
            '--site', site_code,
            '--url', announcement.get('url', ''),
            '--output-dir', str(output_dir),
            '--folder-name', folder_name,
            '--title', announcement.get('title', ''),
            '--date', announcement.get('date', '')
        ]
        
        # 추가 속성 전달
        if announcement.get('onclick'):
            cmd.extend(['--onclick', announcement['onclick']])
        if announcement.get('dataAction'):
            cmd.extend(['--data-action', announcement['dataAction']])
        
        if self.verbose:
            cmd.append('--verbose')
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # stderr 디버그 출력
            if self.verbose and result.stderr:
                for line in result.stderr.split('\n'):
                    if line.strip():
                        self.logger.debug(f'[{site_code}] {line}')
            
            if result.returncode == 0:
                # 성공 응답 파싱
                try:
                    response = json.loads(result.stdout)
                    if response['status'] == 'success':
                        self.logger.info(f'  ✅ DOWNLOADED: [{announcement["id"]}] {announcement["title"][:50]}...')
                        self.stats['downloaded'] += 1
                        
                        # DB에 저장
                        self.save_to_database(site_code, announcement, folder_name, response.get('actualTitle'))
                        return True
                except:
                    pass
            
            self.logger.error(f'  ❌ FAILED: [{announcement["id"]}] {announcement["title"][:50]}...')
            self.stats['errors'] += 1
            return False
            
        except subprocess.TimeoutExpired:
            self.logger.error(f'  ⏱️  TIMEOUT: [{announcement["id"]}] {announcement["title"][:50]}...')
            self.stats['errors'] += 1
            return False
        except Exception as e:
            self.logger.error(f'  ❌ ERROR: [{announcement["id"]}] {e}')
            self.stats['errors'] += 1
            return False
    
    def save_to_database(self, site_code, announcement, folder_name, actual_title=None):
        """DB에 저장"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            # 콘텐츠 해시 생성
            content_hash = hashlib.sha256(
                f"{site_code}_{announcement['id']}_{announcement['title']}".encode()
            ).hexdigest()
            
            # 제목 결정 (실제 제목 우선)
            title = actual_title or announcement.get('title', '')
            
            # NFC 정규화
            title = unicodedata.normalize('NFC', title)
            url = unicodedata.normalize('NFC', announcement.get('url', ''))
            folder_name = unicodedata.normalize('NFC', folder_name)
            
            # 날짜 처리
            post_date = announcement.get('date', '')
            if post_date:
                # 다양한 날짜 형식 처리
                import re
                date_match = re.search(r'(\d{4})[-.\s](\d{1,2})[-.\s](\d{1,2})', post_date)
                if date_match:
                    year, month, day = date_match.groups()
                    post_date = f'{year}-{month.zfill(2)}-{day.zfill(2)}'
                else:
                    post_date = None
            else:
                post_date = None
            
            cursor.execute(
                """
                INSERT INTO unified_url_registry 
                (site_code, announcement_id, announcement_url, title, post_date, folder_name, content_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                last_checked_date = CURRENT_TIMESTAMP,
                title = VALUES(title),
                folder_name = VALUES(folder_name)
                """,
                (site_code, announcement['id'], url, title, post_date, folder_name, content_hash)
            )
            
            conn.commit()
            
        except Exception as e:
            self.logger.error(f'DB 저장 오류: {e}')
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    
    def process_site(self, site_code, pages=3):
        """단일 사이트 처리"""
        site_name = self.configs[site_code]['name']
        
        self.logger.info(f'\n{"="*60}')
        self.logger.info(f'처리 중: {site_code} ({site_name})')
        self.logger.info(f'{"="*60}')
        
        site_stats = {
            'checked': 0,
            'new': 0,
            'downloaded': 0
        }
        
        try:
            # 1. 리스트 수집
            announcements = self.collect_list(site_code, pages)
            if not announcements:
                self.logger.warning(f'[{site_code}] 수집된 공고 없음')
                return site_stats
            
            site_stats['checked'] = len(announcements)
            self.stats['total_checked'] += len(announcements)
            
            # 2. 새 공고 필터링
            new_announcements = self.filter_new_announcements(site_code, announcements)
            site_stats['new'] = len(new_announcements)
            
            if not new_announcements:
                self.logger.info(f'[{site_code}] 새 공고 없음')
                return site_stats
            
            # 3. 상세 다운로드
            self.logger.info(f'[{site_code}] {len(new_announcements)}개 공고 다운로드 시작...')
            
            for idx, ann in enumerate(new_announcements, 1):
                # 테스트 모드에서는 2개만 처리
                if self.test_mode and site_stats['downloaded'] >= 2:
                    self.logger.info(f'[{site_code}] 테스트 모드: 2개 제한')
                    break
                
                if self.download_detail(site_code, ann, idx):
                    site_stats['downloaded'] += 1
            
            self.logger.info(f'[{site_code}] 처리 완료: 확인 {site_stats["checked"]}개, 신규 {site_stats["new"]}개, 다운로드 {site_stats["downloaded"]}개')
            
        except Exception as e:
            self.logger.error(f'[{site_code}] 처리 중 오류: {e}')
        
        return site_stats
    
    def run(self, sites=None, pages=3):
        """메인 실행"""
        self.logger.info('='*80)
        self.logger.info('통합 증분 수집 시작')
        self.logger.info('='*80)
        
        # 의존성 확인
        if not self.check_node_dependencies():
            self.logger.error('의존성 확인 실패. 종료합니다.')
            return False
        
        # 처리할 사이트 결정
        if sites:
            sites_to_process = [s for s in sites if s in self.configs]
        elif self.specific_sites:
            sites_to_process = [s for s in self.specific_sites if s in self.configs]
        else:
            sites_to_process = list(self.configs.keys())
        
        self.logger.info(f'처리할 사이트: {", ".join(sites_to_process)}')
        
        # 사이트별 처리
        start_time = datetime.now()
        
        for site in sites_to_process:
            self.process_site(site, pages)
        
        # 처리 시간 계산
        elapsed_time = (datetime.now() - start_time).total_seconds()
        
        # 최종 통계
        self.logger.info('\n' + '='*80)
        self.logger.info('수집 통계')
        self.logger.info('='*80)
        self.logger.info(f'처리 시간: {elapsed_time:.1f}초')
        self.logger.info(f'확인한 공고: {self.stats["total_checked"]:,}개')
        self.logger.info(f'신규 공고: {self.stats["new_found"]:,}개')
        self.logger.info(f'다운로드 성공: {self.stats["downloaded"]:,}개')
        self.logger.info(f'중복 공고: {self.stats["duplicates"]:,}개')
        self.logger.info(f'오류: {self.stats["errors"]:,}개')
        self.logger.info('='*80)
        
        # 통계 파일 저장
        stats_file = self.output_base / 'collection_stats.json'
        stats_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'sites_processed': sites_to_process,
                'stats': self.stats,
                'elapsed_seconds': elapsed_time
            }, f, ensure_ascii=False, indent=2)
        
        return True

def main():
    parser = argparse.ArgumentParser(description='통합 증분 수집 오케스트레이터')
    parser.add_argument('--sites', nargs='+', help='처리할 사이트 (예: anyang wonju)')
    parser.add_argument('--pages', type=int, default=3, help='수집할 페이지 수 (기본: 3)')
    parser.add_argument('--test', action='store_true', help='테스트 모드 (사이트당 2개만 처리)')
    parser.add_argument('--verbose', '-v', action='store_true', help='상세 로그 출력')
    
    args = parser.parse_args()
    
    orchestrator = UnifiedIncrementalOrchestrator(
        test_mode=args.test,
        specific_sites=args.sites,
        verbose=args.verbose
    )
    
    success = orchestrator.run(sites=args.sites, pages=args.pages)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()