#!/usr/bin/env python3
"""
scraped_data를 분석하여 announcement_id_pattern.json 생성
각 사이트의 공고 ID 패턴을 자동으로 추출
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse, parse_qs
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

class AnnouncementIdPatternGenerator:
    def __init__(self, scraped_dir: str = "scraped_data", scraper_dir: str = "node/scraper"):
        self.scraped_dir = Path(scraped_dir)
        self.scraper_dir = Path(scraper_dir)
        self.patterns = {}
        
    def get_site_codes(self) -> List[str]:
        """scraped_data 하위 폴더에서 사이트 코드 추출"""
        site_codes = []
        
        if not self.scraped_dir.exists():
            logging.error(f"디렉토리가 없습니다: {self.scraped_dir}")
            return site_codes
            
        for item in self.scraped_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                site_codes.append(item.name)
                
        return sorted(site_codes)
    
    def extract_urls_from_content(self, content_file: Path) -> Optional[str]:
        """content.md 파일에서 원본 URL 추출"""
        try:
            with open(content_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 다양한 URL 패턴 시도
            patterns = [
                r'\*\*원본 URL\*\*:\s*(.+)',  # **원본 URL**: 형식
                r'상세 URL\s*:\s*(.+)',        # 상세 URL : 형식
                r'URL\s*:\s*(.+)',             # URL : 형식
                r'https?://[^\s\n]+',          # 그냥 URL
            ]
            
            for pattern in patterns:
                url_match = re.search(pattern, content)
                if url_match:
                    url = url_match.group(1) if url_match.lastindex else url_match.group(0)
                    return url.strip()
                
        except Exception as e:
            logging.debug(f"파일 읽기 오류 {content_file}: {e}")
            
        return None
    
    def analyze_url_params(self, urls: List[str]) -> Set[str]:
        """URL 리스트에서 변화하는 파라미터 찾기"""
        if len(urls) < 2:
            return set()
            
        # 각 URL의 쿼리 파라미터 파싱
        all_params = []
        for url in urls:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            all_params.append(params)
        
        # 변화하는 파라미터 찾기
        changing_params = set()
        
        # 첫 번째 URL의 파라미터를 기준으로
        for param_name in all_params[0].keys():
            values = []
            for params in all_params:
                if param_name in params:
                    values.append(params[param_name][0] if params[param_name] else None)
            
            # 값이 다른 파라미터만 추출
            if len(set(values)) > 1:
                # 숫자로 변환 가능한 값들인지 확인 (보통 ID는 숫자)
                if all(v and v.isdigit() for v in values):
                    changing_params.add(param_name)
        
        return changing_params
    
    def extract_onclick_patterns_from_scraper(self, site_code: str) -> List[Dict]:
        """scraper 파일에서 onclick 패턴 추출"""
        onclick_patterns = []
        scraper_file = self.scraper_dir / f"{site_code}_scraper.js"
        
        if not scraper_file.exists():
            return onclick_patterns
            
        try:
            with open(scraper_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # buildDetailUrl 함수 찾기 (더 유연한 패턴)
            build_detail_match = re.search(
                r'async\s+buildDetailUrl[^{]*\{(.*?)^\s*\}',
                content,
                re.DOTALL | re.MULTILINE
            )
            
            if not build_detail_match:
                # 다른 패턴 시도
                build_detail_match = re.search(
                    r'buildDetailUrl[^{]*\{(.*?)^\s*\}',
                    content,
                    re.DOTALL | re.MULTILINE
                )
            
            if not build_detail_match:
                return onclick_patterns
                
            build_detail_content = build_detail_match.group(1)
            
            # onclick 패턴 찾기
            # 다양한 패턴 매칭
            patterns_to_find = [
                # announcement.onclick.match(/.../)
                (r'announcement\.onclick\.match\(/([^/]+)/[^)]*\)', 'match'),
                # const xxxMatch = announcement.onclick.match(/.../)
                (r'const\s+\w+Match\s*=\s*announcement\.onclick\.match\(/([^/]+)/[^)]*\)', 'const_match'),
                # boardViewMatch = announcement.onclick.match(/boardView.../)
                (r'(\w+Match)\s*=\s*announcement\.onclick\.match\(/([^/]+)/[^)]*\)', 'var_match'),
            ]
            
            onclick_matches = []
            for pattern, pattern_type in patterns_to_find:
                matches = re.finditer(pattern, build_detail_content)
                for match in matches:
                    if pattern_type == 'var_match':
                        # 두 번째 그룹이 실제 패턴
                        onclick_matches.append((match.group(2), match))
                    else:
                        onclick_matches.append((match.group(1), match))
            
            for pattern_str, match_obj in onclick_matches:
                # pattern_str은 이미 추출된 정규식 패턴
                
                # URL 템플릿 찾기 (다음 줄들에서)
                lines_after = build_detail_content[match_obj.end():match_obj.end()+500]
                
                # detailUrl 할당 찾기
                url_match = re.search(
                    r'(?:const|let|var)\s+detailUrl\s*=\s*[`\'"]([^`\'"]+)[`\'"]',
                    lines_after
                )
                
                if url_match:
                    url_template = url_match.group(1)
                    
                    # ${변수명} 패턴을 {번호} 패턴으로 변환
                    # 먼저 변수명 추출
                    var_matches = re.findall(r'\$\{(\w+)\}', url_template)
                    
                    # 패턴에서 캡처 그룹 순서 파악
                    if 'boardView' in pattern_str:
                        # boardView('1', '68812') 형식 - 두 번째가 ID
                        url_template = re.sub(r'\$\{idx\}|\$\{mgtno\}|\$\{[^}]+\}', '{2}', url_template)
                    elif pattern_str.count('([^') == 1:
                        # 단일 파라미터
                        url_template = re.sub(r'\$\{[^}]+\}', '{1}', url_template)
                    else:
                        # 다중 파라미터 - 순서대로 번호 매기기
                        for i, var in enumerate(var_matches, 1):
                            url_template = url_template.replace(f'${{{var}}}', f'{{{i}}}')
                    
                    onclick_patterns.append({
                        'pattern': pattern_str,
                        'urlTemplate': url_template,
                        'description': self.describe_pattern(pattern_str)
                    })
            
        except Exception as e:
            logging.debug(f"Scraper 파일 분석 오류 {site_code}: {e}")
            
        return onclick_patterns
    
    def describe_pattern(self, pattern: str) -> str:
        """패턴에 대한 설명 생성"""
        if 'boardView' in pattern:
            return "boardView(page, idx) 패턴"
        elif 'opDetail' in pattern:
            return "opDetail(mgtno) 패턴"
        elif 'javascript' in pattern.lower():
            return "JavaScript 함수 호출 패턴"
        else:
            # 함수명 추출 시도
            func_match = re.match(r'(\w+)', pattern)
            if func_match:
                return f"{func_match.group(1)} 함수 패턴"
            return "커스텀 onclick 패턴"
    
    def analyze_site(self, site_code: str) -> Dict:
        """단일 사이트 분석"""
        site_dir = self.scraped_dir / site_code
        
        if not site_dir.exists():
            return None
            
        logging.info(f"\n[{site_code}] 분석 시작")
        
        # 최신 10개 폴더 찾기
        folders = []
        for folder in site_dir.iterdir():
            if folder.is_dir() and re.match(r'^\d{3}_', folder.name):
                folders.append(folder)
        
        # 번호 기준 정렬 (001이 최신)
        folders.sort(key=lambda x: int(x.name[:3]))
        
        # URL 수집
        urls = []
        for folder in folders[:10]:
            content_file = folder / "content.md"
            if content_file.exists():
                url = self.extract_urls_from_content(content_file)
                if url:
                    urls.append(url)
        
        if not urls:
            logging.warning(f"[{site_code}] URL을 찾을 수 없음")
            return None
        
        logging.info(f"[{site_code}] {len(urls)}개 URL 수집")
        
        # URL 분석하여 변화하는 파라미터 찾기
        changing_params = self.analyze_url_params(urls)
        
        # onclick 패턴 추출
        onclick_patterns = self.extract_onclick_patterns_from_scraper(site_code)
        
        # 결과 구성
        result = {}
        
        # onclick 패턴이 있는 경우
        if onclick_patterns:
            result['onclickPatterns'] = onclick_patterns
            
            # urlTemplate에서 파라미터 추출
            url_params = set()
            for pattern in onclick_patterns:
                template = pattern.get('urlTemplate', '')
                # URL에서 파라미터 이름 추출
                param_matches = re.findall(r'[?&](\w+)=\{', template)
                url_params.update(param_matches)
            
            if url_params:
                result['announcementIdPattern'] = {
                    'urlParams': list(url_params),
                    'description': 'URL에서 공고 ID를 추출하는 파라미터 목록'
                }
        
        # URL 직접 링크인 경우 (onclick 패턴 없음)
        elif changing_params:
            result['announcementIdPattern'] = {
                'urlParams': list(changing_params),
                'description': 'URL에서 공고 ID를 추출하는 파라미터 목록'
            }
            logging.info(f"[{site_code}] 변화하는 파라미터: {changing_params}")
        
        if result:
            logging.info(f"[{site_code}] 패턴 추출 완료")
            return result
        else:
            logging.warning(f"[{site_code}] 패턴을 찾을 수 없음")
            return None
    
    def generate_patterns(self):
        """모든 사이트의 패턴 생성"""
        site_codes = self.get_site_codes()
        
        logging.info(f"총 {len(site_codes)}개 사이트 발견")
        
        for site_code in site_codes:
            pattern = self.analyze_site(site_code)
            if pattern:
                self.patterns[site_code] = pattern
        
        logging.info(f"\n총 {len(self.patterns)}개 사이트 패턴 생성")
        
        # JSON 파일로 저장
        output_file = Path("announcement_id_patterns.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.patterns, f, ensure_ascii=False, indent=4)
        
        logging.info(f"결과 저장: {output_file}")
        
        return self.patterns

def main():
    generator = AnnouncementIdPatternGenerator()
    patterns = generator.generate_patterns()
    
    # 통계 출력
    print(f"\n{'='*60}")
    print("패턴 생성 완료")
    print(f"{'='*60}")
    
    onclick_count = 0
    direct_link_count = 0
    
    for site_code, pattern in patterns.items():
        if 'onclickPatterns' in pattern:
            onclick_count += 1
        elif 'announcementIdPattern' in pattern:
            direct_link_count += 1
    
    print(f"onclick 패턴 사이트: {onclick_count}개")
    print(f"직접 링크 사이트: {direct_link_count}개")
    print(f"전체: {len(patterns)}개")

if __name__ == "__main__":
    main()