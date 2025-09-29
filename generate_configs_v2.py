#!/usr/bin/env python3
"""
모든 스크래퍼 파일을 분석하여 config JSON 파일 생성 (개선된 버전)
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
    
    # URL 추출 - default: 뒤의 전체 URL을 가져옴 (토큰 포함)
    url_match = re.search(r"\.option\(['\"]url['\"][^}]*?default:\s*['\"`]([^'\"`]+)['\"`]", content, re.DOTALL)
    if url_match:
        full_url = url_match.group(1)
        info['listUrl'] = full_url
        # baseUrl 추출
        from urllib.parse import urlparse
        parsed = urlparse(full_url)
        info['baseUrl'] = f"{parsed.scheme}://{parsed.netloc}"
    
    # 사이트명 매핑 (주요 사이트만)
    site_name_map = {
        'anseong': '안성시',
        'anyang': '안양시',
        'cs': '창원시', 
        'changwon': '창원시',
        'cwg': '청원구',
        'cheongju': '청주시',
        'cheongyang': '청양군',
        'chilgok': '칠곡군',
        'chungbuk': '충청북도',
        'chungju': '충주시',
        'chungnam': '충청남도',
        'daegu': '대구광역시',
        'daejeon': '대전광역시',
        'busan': '부산광역시',
        'seoul': '서울특별시',
        'incheon': '인천광역시',
        'gwangju': '광주광역시',
        'ulsan': '울산광역시',
        'sejong': '세종특별자치시',
        'jeju': '제주특별자치도',
        'gangnam': '강남구',
        'gangbuk': '강북구',
        'jongno': '종로구',
        'mapo': '마포구',
        'nowon': '노원구',
        'songpa': '송파구',
        'yongsan': '용산구',
        'gimpo': '김포시',
        'guri': '구리시',
        'siheung': '시흥시',
        'pocheon': '포천시',
        'pyeongtaek': '평택시',
        'osan': '오산시',
        'paju': '파주시',
        'icheon': '이천시',
        'ui4u': '의정부시',
        'gccity': '과천시',
        'gjcity': '광주시',
        'nyj': '남양주시',
        'gm': '구미시',
        'yanggu': '양구군',
        'gg': '강진군',
        'gbgs': '고창군',
        'gwanak': '관악구',
        'seosan': '서산시',
        'pohang': '포항시',
        'gijang': '기장군',
        'sdm': '서대문구',
        'seogu': '서구',
        'geumjeong': '금정구',
        'goryeong': '고령군',
        'gc': '거창군',
        'namgu': '남구',
    }
    
    info['siteName'] = site_name_map.get(site_code, site_code.upper())
    
    # Selector 추출 - yargs의 setupCLI 함수에서
    # list-selector 옵션 찾기
    list_selector_match = re.search(
        r"\.option\(['\"]list-selector['\"][^}]*?default:\s*['\"`]([^'\"`]+)['\"`]", 
        content, re.DOTALL
    )
    
    # title-selector 옵션 찾기  
    title_selector_match = re.search(
        r"\.option\(['\"]title-selector['\"][^}]*?default:\s*['\"`]([^'\"`]+)['\"`]",
        content, re.DOTALL
    )
    
    # date-selector 옵션 찾기
    date_selector_match = re.search(
        r"\.option\(['\"]date-selector['\"][^}]*?default:\s*['\"`]([^'\"`]+)['\"`]",
        content, re.DOTALL
    )
    
    if list_selector_match:
        list_sel = list_selector_match.group(1).strip()
        # 테이블과 row 분리
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
    build_list_url_match = re.search(r'buildListUrl\s*\([^)]*\)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', content, re.DOTALL)
    if build_list_url_match:
        func_body = build_list_url_match.group(1)
        
        # URL 파라미터 찾기
        if 'searchParams.set' in func_body:
            # searchParams.set('page', pageNum) 패턴
            param_match = re.search(r"searchParams\.set\(['\"]([^'\"]+)['\"]", func_body)
            if param_match:
                param_name = param_match.group(1)
                info['pagination'] = {
                    'type': 'query',
                    'param': f'&{param_name}',
                    'maxPages': 10
                }
        elif '?page=' in func_body or '&page=' in func_body:
            info['pagination'] = {
                'type': 'query',
                'param': '&page',
                'maxPages': 10
            }
        elif 'pageIndex=' in func_body:
            info['pagination'] = {
                'type': 'query',
                'param': '&pageIndex',
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
        
        # JavaScript 페이지네이션 체크
        if 'goPage' in func_body:
            info['pagination'] = {
                'type': 'javascript',
                'function': 'goPage',
                'maxPages': 10
            }
    
    # buildDetailUrl에서 onclick 패턴과 announcementIdPattern 추출
    build_detail_url_match = re.search(r'buildDetailUrl\s*\([^)]*\)\s*\{(.*?)\n\s*\}', content, re.DOTALL)
    if build_detail_url_match:
        func_body = build_detail_url_match.group(1)
        
        # boardView 패턴 처리
        board_view_match = re.search(r'boardViewMatch.*?match\((.*?)\)', func_body, re.DOTALL)
        if board_view_match:
            # boardView(page, idx) 형태 처리
            pattern_text = board_view_match.group(1)
            if 'boardView' in func_body:
                # URL 템플릿 찾기
                url_template_match = re.search(r'detailUrl\s*=\s*[`\'"]([^`\'"]+)[`\'"]', func_body)
                if url_template_match:
                    template = url_template_match.group(1)
                    # ${변수} 형태를 {숫자} 형태로 변환
                    template = re.sub(r'\$\{idx\}', '{2}', template)
                    template = re.sub(r'\$\{page\}', '{1}', template)
                    
                    # notAncmtMgtNo가 템플릿에 있으면 announcementIdPattern에 추가
                    if 'notAncmtMgtNo=' in template:
                        if 'notAncmtMgtNo' not in info['announcementIdPattern']['urlParams']:
                            info['announcementIdPattern']['urlParams'].insert(0, 'notAncmtMgtNo')
                    
                    info['onclickPatterns'].append({
                        'pattern': r'boardView\s*\(\s*[\'"]([^\'\"]+)[\'\"]\s*,\s*[\'"]([^\'\"]+)[\'\"]\s*\)',
                        'urlTemplate': template,
                        'description': 'boardView(page, idx) 패턴'
                    })
        
        # fn_view 패턴 체크
        if 'fn_view' in func_body or 'fnView' in func_body:
            # URL 템플릿 찾기
            view_url_match = re.search(r'[`\'"]([^`\'"]*(?:view|detail)[^`\'"]+)[`\'"]', func_body)
            if view_url_match:
                template = view_url_match.group(1)
                template = re.sub(r'\$\{[^}]+\}', '{1}', template)
                
                info['onclickPatterns'].append({
                    'pattern': r'fn_?[vV]iew\s*\(\s*[\'"]?(\d+)[\'"]?\s*\)',
                    'urlTemplate': template if template.startswith('http') else info['baseUrl'] + template,
                    'description': 'fn_view 패턴'
                })
        
        # goView 패턴 체크
        if 'goView(' in func_body:
            info['onclickPatterns'].append({
                'pattern': r'goView\s*\(\s*[\'"]?(\d+)[\'"]?\s*\)',
                'urlTemplate': info['baseUrl'] + '/view.do?seq={1}',
                'description': 'goView 패턴'
            })
        
        # view() 패턴 체크
        if re.search(r'view\s*\(', func_body):
            info['onclickPatterns'].append({
                'pattern': r'view\s*\(\s*[\'"]?(\d+)[\'"]?\s*\)',
                'urlTemplate': info['baseUrl'] + '/board/view.do?seq={1}',
                'description': 'view 패턴'
            })
        
        # 특수 파라미터 체크 및 announcementIdPattern 업데이트
        special_params = ['notAncmtMgtNo', 'mgtNo', 'boardSeq', 'bbsSeq', 'articleNo', 'nttId']
        for param in special_params:
            if param in func_body:
                if param not in info['announcementIdPattern']['urlParams']:
                    info['announcementIdPattern']['urlParams'].append(param)
    
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
    
    # anseong 파일 확인
    anseong_config = config_dir / 'anseong.json'
    if anseong_config.exists():
        with open(anseong_config, 'r', encoding='utf-8') as f:
            anseong_data = json.load(f)
        print("\n=== anseong.json 내용 ===")
        print(json.dumps(anseong_data, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()