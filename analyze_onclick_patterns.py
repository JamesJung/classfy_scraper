#!/usr/bin/env python3
"""
모든 scraper 파일에서 buildDetailUrl 함수를 분석하여 onclick 패턴 추출
"""

import os
import re
from pathlib import Path
import json

def extract_buildDetailUrl_functions(scraper_dir="node/scraper"):
    """모든 scraper 파일에서 buildDetailUrl 함수 추출"""
    scraper_path = Path(scraper_dir)
    results = {}
    
    for scraper_file in scraper_path.glob("*_scraper.js"):
        site_code = scraper_file.stem.replace('_scraper', '')
        
        if site_code == 'announcement':  # 템플릿 파일 제외
            continue
            
        try:
            with open(scraper_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # buildDetailUrl 함수를 중괄호 균형으로 찾기
            build_detail_content = None
            
            # buildDetailUrl 시작 위치 찾기
            patterns = [
                'async buildDetailUrl',
                'buildDetailUrl',
                'buildDetailUrl:',
            ]
            
            start_pos = -1
            for pattern in patterns:
                pos = content.find(pattern)
                if pos != -1:
                    start_pos = pos
                    break
            
            if start_pos != -1:
                # 중괄호 균형 맞춰서 함수 끝 찾기
                brace_count = 0
                in_func = False
                end_pos = start_pos
                
                for i in range(start_pos, len(content)):
                    if content[i] == '{':
                        brace_count += 1
                        in_func = True
                    elif content[i] == '}':
                        brace_count -= 1
                        if in_func and brace_count == 0:
                            end_pos = i + 1
                            break
                
                if end_pos > start_pos:
                    build_detail_content = content[start_pos:end_pos]
            
            if build_detail_content:
                results[site_code] = {
                    'file': str(scraper_file),
                    'content': build_detail_content,
                    'patterns': extract_onclick_patterns(build_detail_content, site_code)
                }
                
        except Exception as e:
            print(f"Error processing {scraper_file}: {e}")
    
    return results

def extract_onclick_patterns(content, site_code):
    """buildDetailUrl 내용에서 onclick 패턴 추출"""
    patterns = []
    
    # 다양한 onclick 패턴 찾기
    onclick_patterns = [
        # announcement.onclick.match(/패턴/)
        r'announcement\.onclick\.match\(/([^/]+)/',
        # const xxxMatch = announcement.onclick.match(/패턴/)
        r'(?:const|let|var)\s+\w+Match\s*=\s*announcement\.onclick\.match\(/([^/]+)/',
        # if (announcement.onclick.includes('함수명'))
        r'announcement\.onclick\.includes\([\'"]([^\'"]+)[\'"]',
        # onclick.match(/패턴/)
        r'onclick\.match\(/([^/]+)/',
    ]
    
    for pattern in onclick_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches:
            # URL 템플릿 찾기 (match 이후 500자 내에서)
            match_pos = content.find(match)
            if match_pos == -1:
                continue
                
            nearby_content = content[match_pos:match_pos+1000]
            
            # URL 템플릿 패턴들
            url_patterns = [
                # const detailUrl = `URL템플릿`;
                r'(?:const|let|var)\s+detailUrl\s*=\s*[`\'"]([^`\'"]+)[`\'"]',
                # return `URL템플릿`;
                r'return\s+[`\'"]([^`\'"]+)[`\'"]',
                # detailUrl = `URL템플릿`;
                r'detailUrl\s*=\s*[`\'"]([^`\'"]+)[`\'"]',
            ]
            
            url_template = None
            for url_pattern in url_patterns:
                url_matches = re.findall(url_pattern, nearby_content)
                if url_matches:
                    url_template = url_matches[0]
                    break
            
            if url_template:
                # ${변수} 패턴을 {번호} 패턴으로 변환
                # boardView는 보통 두 번째 파라미터가 ID
                if 'boardView' in match:
                    url_template = re.sub(r'\$\{idx\}|\$\{[^}]*\}', '{2}', url_template)
                else:
                    # 순서대로 번호 매기기
                    var_count = 1
                    def replace_var(m):
                        nonlocal var_count
                        result = f'{{{var_count}}}'
                        var_count += 1
                        return result
                    url_template = re.sub(r'\$\{[^}]+\}', replace_var, url_template)
                
                patterns.append({
                    'pattern': match,
                    'urlTemplate': url_template,
                    'description': describe_pattern(match)
                })
    
    return patterns

def describe_pattern(pattern):
    """패턴 설명 생성"""
    if 'boardView' in pattern:
        return "boardView(page, idx) 패턴"
    elif 'opDetail' in pattern:
        return "opDetail(mgtno) 패턴"
    elif 'goView' in pattern:
        return "goView 패턴"
    elif 'fn_' in pattern:
        return f"fn_ 함수 패턴"
    elif 'javascript' in pattern.lower():
        return "JavaScript 함수 호출 패턴"
    else:
        # 함수명 추출
        func_match = re.match(r'(\w+)', pattern)
        if func_match:
            return f"{func_match.group(1)} 함수 패턴"
        return "커스텀 onclick 패턴"

def main():
    print("="*60)
    print("buildDetailUrl 함수 분석")
    print("="*60)
    
    results = extract_buildDetailUrl_functions()
    
    # 통계
    total = len(results)
    with_patterns = sum(1 for r in results.values() if r['patterns'])
    
    print(f"\n총 {total}개 scraper 파일 분석")
    print(f"onclick 패턴 발견: {with_patterns}개")
    
    # onclick 패턴이 있는 사이트만 출력
    onclick_sites = {}
    for site_code, data in results.items():
        if data['patterns']:
            print(f"\n[{site_code}]")
            onclick_sites[site_code] = {
                'onclickPatterns': data['patterns']
            }
            for pattern in data['patterns']:
                print(f"  - 패턴: {pattern['pattern'][:50]}...")
                print(f"    템플릿: {pattern['urlTemplate'][:80]}...")
    
    # JSON 파일로 저장
    output_file = "onclick_patterns.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(onclick_sites, f, ensure_ascii=False, indent=4)
    
    print(f"\n결과 저장: {output_file}")
    
    # buildDetailUrl이 있지만 패턴이 없는 사이트 확인
    no_pattern_sites = [site for site, data in results.items() if not data['patterns']]
    if no_pattern_sites:
        print(f"\nbuildDetailUrl은 있지만 onclick 패턴이 없는 사이트: {len(no_pattern_sites)}개")
        print(f"  {', '.join(no_pattern_sites[:10])}")
        if len(no_pattern_sites) > 10:
            print(f"  ... 외 {len(no_pattern_sites)-10}개")

if __name__ == "__main__":
    main()