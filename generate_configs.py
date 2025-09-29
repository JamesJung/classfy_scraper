#!/usr/bin/env python3
"""
모든 스크래퍼 파일을 분석하여 config JSON 파일 생성
"""

import os
import re
import json
from pathlib import Path

def extract_scraper_info(filepath):
    """스크래퍼 파일에서 필요한 정보 추출"""
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 사이트 코드 추출
    site_code = Path(filepath).stem.replace('_scraper', '')
    
    info = {
        'siteCode': site_code,
        'siteName': '',
        'baseUrl': '',
        'listUrl': '',
        'dateFormat': 'YYYY.MM.DD',  # 기본값
        'selectors': {},
        'pagination': {},
        'onclickPatterns': [],
        'announcementIdPattern': {
            'urlParams': ['seq', 'id', 'no', 'idx'],
            'description': 'URL에서 공고 ID를 추출하는 파라미터 목록'
        },
        'dailyPages': 3
    }
    
    # yargs 옵션에서 selector 정보 추출
    yargs_match = re.search(r'setupCLI\(\)[^}]*?\.option.*?default:\s*[\'"`]([^\'"`]+)[\'"`]', content, re.DOTALL)
    
    # URL 추출
    url_match = re.search(r"\.option\(['\"]url['\"].*?default:\s*['\"`]([^'\"`]+)['\"`]", content, re.DOTALL)
    if url_match:
        info['listUrl'] = url_match.group(1).split('?')[0] + '?'
        # baseUrl 추출
        from urllib.parse import urlparse
        parsed = urlparse(info['listUrl'])
        info['baseUrl'] = f"{parsed.scheme}://{parsed.netloc}"
    
    # 사이트명 추출 (URL에서)
    if info['baseUrl']:
        domain = info['baseUrl'].replace('https://', '').replace('http://', '')
        if 'anseong' in domain:
            info['siteName'] = '안성시'
        elif 'cs' in domain or 'changwon' in domain:
            info['siteName'] = '창원시'
        elif 'cwg' in domain:
            info['siteName'] = '청원구'
        else:
            info['siteName'] = site_code.upper()
    
    # Selector 추출
    list_selector_match = re.search(r"\.option\(['\"]list-selector['\"].*?default:\s*['\"`]([^'\"`]+)['\"`]", content, re.DOTALL)
    title_selector_match = re.search(r"\.option\(['\"]title-selector['\"].*?default:\s*['\"`]([^'\"`]+)['\"`]", content, re.DOTALL)
    date_selector_match = re.search(r"\.option\(['\"]date-selector['\"].*?default:\s*['\"`]([^'\"`]+)['\"`]", content, re.DOTALL)
    
    if list_selector_match:
        list_sel = list_selector_match.group(1).strip()
        # 테이블 셀렉터 분리
        if 'tbody tr' in list_sel:
            table_sel = list_sel.replace(' tbody tr', '').strip()
            info['selectors']['list'] = table_sel
            info['selectors']['row'] = list_sel
        else:
            info['selectors']['list'] = list_sel
            info['selectors']['row'] = list_sel
    
    if title_selector_match:
        info['selectors']['link'] = title_selector_match.group(1).strip()
        info['selectors']['title'] = title_selector_match.group(1).strip()
    
    if date_selector_match:
        info['selectors']['date'] = date_selector_match.group(1).strip()
    
    # buildListUrl에서 pagination 정보 추출
    build_list_url_match = re.search(r'buildListUrl\([^)]*\)\s*{([^}]+)}', content, re.DOTALL)
    if build_list_url_match:
        func_body = build_list_url_match.group(1)
        
        # page 파라미터 패턴 찾기
        if 'pageIndex=' in func_body:
            info['pagination'] = {
                'type': 'query',
                'param': '&pageIndex',
                'maxPages': 10
            }
        elif 'page=' in func_body:
            param_match = re.search(r'([&?])page=', func_body)
            if param_match:
                info['pagination'] = {
                    'type': 'query', 
                    'param': f'{param_match.group(1)}page',
                    'maxPages': 10
                }
        elif 'currentPageNo=' in func_body:
            info['pagination'] = {
                'type': 'query',
                'param': '&currentPageNo',
                'maxPages': 10
            }
        elif 'pageNo=' in func_body:
            info['pagination'] = {
                'type': 'query',
                'param': '&pageNo',
                'maxPages': 10
            }
    
    # buildDetailUrl에서 onclick 패턴 추출
    build_detail_url_match = re.search(r'buildDetailUrl\([^)]*\)\s*{([^}]+(?:{[^}]+}[^}]+)*)}', content, re.DOTALL)
    if build_detail_url_match:
        func_body = build_detail_url_match.group(1)
        
        # boardView 패턴
        if 'boardView' in func_body:
            board_match = re.search(r'boardView.*?match.*?(\/.+?\/[gimsu]*)', func_body)
            if board_match:
                pattern = board_match.group(1).strip('/')
                # URL 템플릿 찾기
                url_template_match = re.search(r'(https?://[^\'"`]+(?:\$\{[^}]+\}|[^\'"`]+)+)', func_body)
                if url_template_match:
                    template = url_template_match.group(1)
                    # ${idx} 형태를 {2} 형태로 변환
                    template = re.sub(r'\$\{idx\}', '{2}', template)
                    template = re.sub(r'\$\{page\}', '{1}', template)
                    
                    info['onclickPatterns'].append({
                        'pattern': pattern.replace('\\', '\\\\'),
                        'urlTemplate': template,
                        'description': 'boardView 패턴'
                    })
        
        # fn_view 패턴
        if 'fn_view' in func_body or 'fnView' in func_body:
            info['onclickPatterns'].append({
                'pattern': 'fn_?[vV]iew\\s*\\(\\s*[\'\"](\\d+)[\'"]\\s*\\)',
                'urlTemplate': info['baseUrl'] + '/view.do?seq={1}',
                'description': 'fn_view 패턴'
            })
        
        # goView 패턴
        if 'goView' in func_body:
            info['onclickPatterns'].append({
                'pattern': 'goView\\s*\\(\\s*[\'\"](\\d+)[\'"]\\s*\\)',
                'urlTemplate': info['baseUrl'] + '/view.do?seq={1}',
                'description': 'goView 패턴'
            })
        
        # view 패턴
        if re.search(r"view\s*\(\\s\*\['\"\]", func_body):
            info['onclickPatterns'].append({
                'pattern': 'view\\s*\\(\\s*[\'\"](\\d+)[\'"]\\s*\\)',
                'urlTemplate': info['baseUrl'] + '/board/view.do?seq={1}',
                'description': 'view 패턴'
            })
        
        # announcementId 추출 파라미터 확인
        if 'notAncmtMgtNo' in func_body:
            if 'notAncmtMgtNo' not in info['announcementIdPattern']['urlParams']:
                info['announcementIdPattern']['urlParams'].insert(0, 'notAncmtMgtNo')
        if 'mgtNo' in func_body:
            if 'mgtNo' not in info['announcementIdPattern']['urlParams']:
                info['announcementIdPattern']['urlParams'].insert(0, 'mgtNo')
        if 'boardSeq' in func_body:
            if 'boardSeq' not in info['announcementIdPattern']['urlParams']:
                info['announcementIdPattern']['urlParams'].append('boardSeq')
    
    return info

def main():
    """메인 함수"""
    
    scraper_dir = Path('/Users/jin/classfy_scraper/node/scraper')
    config_dir = Path('/Users/jin/classfy_scraper/node/configs')
    
    # configs 디렉토리 생성
    config_dir.mkdir(exist_ok=True)
    
    # 제외할 스크래퍼
    exclude = ['eminwon_scraper.js', 'announcement_scraper.js', 'unified_detail_scraper.js', 'eminwon_detail_scraper.js']
    
    # 모든 스크래퍼 파일 처리
    scraper_files = sorted(scraper_dir.glob('*_scraper.js'))
    
    results = []
    errors = []
    
    for scraper_file in scraper_files:
        if scraper_file.name in exclude:
            continue
        
        try:
            print(f"처리 중: {scraper_file.name}")
            
            info = extract_scraper_info(scraper_file)
            
            # 유효한 정보가 있는 경우만 저장
            if info['listUrl'] and info['selectors'].get('row'):
                # JSON 파일 저장
                config_file = config_dir / f"{info['siteCode']}.json"
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(info, f, ensure_ascii=False, indent=4)
                
                results.append(info['siteCode'])
                print(f"  ✓ {info['siteCode']}.json 생성 완료")
            else:
                errors.append(f"{info['siteCode']}: 필수 정보 부족")
                print(f"  ✗ {info['siteCode']}: 필수 정보 부족")
                
        except Exception as e:
            errors.append(f"{scraper_file.name}: {str(e)}")
            print(f"  ✗ 오류: {str(e)}")
    
    print(f"\n===== 처리 완료 =====")
    print(f"성공: {len(results)}개")
    print(f"실패: {len(errors)}개")
    
    if errors:
        print("\n실패 목록:")
        for error in errors:
            print(f"  - {error}")
    
    print(f"\n생성된 config 파일들: {config_dir}")

if __name__ == '__main__':
    main()