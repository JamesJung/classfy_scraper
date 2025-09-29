#!/usr/bin/env python3
"""
announcement_id_patterns.json과 onclick_patterns.json을 병합
"""

import json
from pathlib import Path

def merge_patterns():
    # 파일 읽기
    announcement_patterns = {}
    onclick_patterns = {}
    
    if Path("announcement_id_patterns.json").exists():
        with open("announcement_id_patterns.json", 'r', encoding='utf-8') as f:
            announcement_patterns = json.load(f)
    
    if Path("onclick_patterns.json").exists():
        with open("onclick_patterns.json", 'r', encoding='utf-8') as f:
            onclick_patterns = json.load(f)
    
    # 병합
    merged = {}
    all_sites = set(announcement_patterns.keys()) | set(onclick_patterns.keys())
    
    for site_code in sorted(all_sites):
        site_data = {}
        
        # onclick 패턴 추가 (있으면)
        if site_code in onclick_patterns:
            # 중복 제거
            unique_patterns = []
            seen = set()
            for pattern in onclick_patterns[site_code].get('onclickPatterns', []):
                pattern_key = (pattern['pattern'], pattern['urlTemplate'])
                if pattern_key not in seen:
                    seen.add(pattern_key)
                    unique_patterns.append(pattern)
            
            if unique_patterns:
                site_data['onclickPatterns'] = unique_patterns
        
        # announcement ID 패턴 추가 (있으면)
        if site_code in announcement_patterns:
            if 'announcementIdPattern' in announcement_patterns[site_code]:
                site_data['announcementIdPattern'] = announcement_patterns[site_code]['announcementIdPattern']
        
        # onclick 패턴에서 urlParams 추출
        if 'onclickPatterns' in site_data and 'announcementIdPattern' not in site_data:
            url_params = set()
            for pattern in site_data['onclickPatterns']:
                template = pattern.get('urlTemplate', '')
                # URL 파라미터 추출 (예: notAncmtMgtNo={2})
                import re
                param_matches = re.findall(r'[?&](\w+)=\{', template)
                url_params.update(param_matches)
            
            if url_params:
                site_data['announcementIdPattern'] = {
                    'urlParams': list(url_params),
                    'description': 'URL에서 공고 ID를 추출하는 파라미터 목록'
                }
        
        if site_data:
            merged[site_code] = site_data
    
    # 저장
    output_file = "announcement_id_patterns_final.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=4)
    
    # 통계 출력
    print("="*60)
    print("패턴 병합 완료")
    print("="*60)
    
    onclick_count = sum(1 for v in merged.values() if 'onclickPatterns' in v)
    param_count = sum(1 for v in merged.values() if 'announcementIdPattern' in v)
    both_count = sum(1 for v in merged.values() if 'onclickPatterns' in v and 'announcementIdPattern' in v)
    
    print(f"전체 사이트: {len(merged)}개")
    print(f"onclick 패턴 보유: {onclick_count}개")
    print(f"URL 파라미터 패턴 보유: {param_count}개")
    print(f"둘 다 보유: {both_count}개")
    print(f"\n결과 파일: {output_file}")

if __name__ == "__main__":
    merge_patterns()