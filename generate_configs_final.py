#!/usr/bin/env python3
"""
모든 스크래퍼 파일을 분석하여 config JSON 파일 생성 (최종 버전 - 주석 우선 처리)
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
    
    # 사이트명 매핑
    site_name_map = {
        'anseong': '안성시',
        'anyang': '안양시',
        'boeun': '보은군',
        'boseong': '보성군',
        'buan': '부안군',
        'busan': '부산광역시',
        'changwon': '창원시',
        'cheongdo': '청도군',
        'cheongju': '청주시',
        'cheongyang': '청양군',
        'chilgok': '칠곡군',
        'chungbuk': '충청북도',
        'chungju': '충주시',
        'chungnam': '충청남도',
        'cng': '청남도',
        'cs': '창원시',
        'cwg': '청원구',
        'daegu': '대구광역시',
        'daejeon': '대전광역시',
        'ddc': '동대문구',
        'djjunggu': '대전중구',
        'ep': '은평구',
        'eumseong': '음성군',
        'gangbuk': '강북구',
        'ganghwa': '강화군',
        'gangjin': '강진군',
        'gangnam': '강남구',
        'gb': '강북구',
        'gbgs': '고창군',
        'gbmg': '광명시',
        'gc': '거창군',
        'gccity': '과천시',
        'geochang': '거창군',
        'geoje': '거제시',
        'geumjeong': '금정구',
        'geumsan': '금산군',
        'gg': '강진군',
        'gimhae': '김해시',
        'gimje': '김제시',
        'gimpo': '김포시',
        'gjcity': '광주시',
        'gm': '구미시',
        'gn': '강릉시',
        'gochang': '고창군',
        'gokseong': '곡성군',
        'goryeong': '고령군',
        'goseong': '고성군',
        'gp': '김포시',
        'gumi': '구미시',
        'gunwi': '군위군',
        'guri': '구리시',
        'guro': '구로구',
        'gurye': '구례군',
        'gwanak': '관악구',
        'gwangjin': '광진구',
        'gwangju': '광주광역시',
        'gwangsan': '광산구',
        'gwangyang': '광양시',
        'gwd': '강원도',
        'gwgs': '고성군',
        'gyeongju': '경주시',
        'gyeongnam': '경상남도',
        'gyeryong': '계룡시',
        'gyeyang': '계양구',
        'hadong': '하동군',
        'haenam': '해남군',
        'haman': '함안군',
        'hampyeong': '함평군',
        'hc': '합천군',
        'hongcheon': '홍천군',
        'hongseong': '홍성군',
        'hsg': '화성시',
        'icbp': '인천부평구',
        'icdonggu': '인천동구',
        'icheon': '이천시',
        'incheon': '인천광역시',
        'inje': '인제군',
        'jangheung': '장흥군',
        'jangseong': '장성군',
        'jecheon': '제천시',
        'jeju': '제주특별자치도',
        'jeonbuk': '전라북도',
        'jeonnam': '전라남도',
        'jindo': '진도군',
        'jongno': '종로구',
        'jp': '증평군',
        'junggu': '중구',
        'jungnang': '중랑구',
        'mapo': '마포구',
        'michuhol': '미추홀구',
        'mokpo': '목포시',
        'muan': '무안군',
        'naju': '나주시',
        'namdong': '남동구',
        'namhae': '남해군',
        'namgu': '남구',
        'namwon': '남원시',
        'nowon': '노원구',
        'nyj': '남양주시',
        'oc': '옹진군',
        'ongjin': '옹진군',
        'osan': '오산시',
        'paju': '파주시',
        'pocheon': '포천시',
        'pohang': '포항시',
        'pyeongtaek': '평택시',
        'sacheon': '사천시',
        'samcheok': '삼척시',
        'sancheong': '산청군',
        'sb': '성북구',
        'sd': '성동구',
        'sdm': '서대문구',
        'sejong': '세종특별자치시',
        'seo': '서초구',
        'seogu': '서구',
        'seosan': '서산시',
        'seoul': '서울특별시',
        'shinan': '신안군',
        'siheung': '시흥시',
        'sj': '세종시',
        'songpa': '송파구',
        'suncheon': '순천시',
        'taebaek': '태백시',
        'tongyeong': '통영시',
        'ui4u': '의정부시',
        'uiryung': '의령군',
        'uljin': '울진군',
        'ulju': '울주군',
        'ulleung': '울릉군',
        'ulsan': '울산광역시',
        'usc': '울산중구',
        'wando': '완도군',
        'wonju': '원주시',
        'yangcheon': '양천구',
        'yanggu': '양구군',
        'yangsan': '양산시',
        'yc': '양천구',
        'yd': '영등포구',
        'yd21': '영도구',
        'ydp': '영등포구',
        'yeoju': '여주시',
        'yeongam': '영암군',
        'yeongdo': '영도구',
        'yeongju': '영주시',
        'yeonje': '연제구',
        'yeosu': '여수시',
        'yongsan': '용산구',
        'yp21': '양평군',
        'yyg': '영양군',
        'gijang': '기장군',
        'seogu': '서구',
    }
    
    info['siteName'] = site_name_map.get(site_code, site_code.upper())
    
    # Selector 추출 - 주석 다음 라인의 실제 default를 우선 찾기
    # list-selector 옵션 찾기 (주석 다음 라인 우선)
    list_selector_match = re.search(
        r"\.option\(['\"]list-selector['\"][^}]*?//[^\n]*\n\s*default:\s*['\"`]([^'\"`]+)['\"`]",
        content, re.DOTALL
    )
    if not list_selector_match:
        # 주석이 없으면 일반 default 찾기
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
        elif '&cpage=' in func_body:
            info['pagination'] = {
                'type': 'query',
                'param': '&cpage',
                'maxPages': 10
            }
        
        # JavaScript 페이지네이션 체크
        if 'goPage' in func_body or 'return this.baseUrl' in func_body:
            # JavaScript 방식이면서 URL 변경 없는 경우
            info['pagination'] = {
                'type': 'javascript',
                'function': 'goPage',
                'maxPages': 10
            }
    
    # buildDetailUrl에서 onclick 패턴과 announcementIdPattern 추출
    build_detail_url_match = re.search(r'buildDetailUrl\s*\([^)]*\)\s*\{(.*?)\n\s*\}', content, re.DOTALL)
    if build_detail_url_match:
        func_body = build_detail_url_match.group(1)
        
        # boardView 패턴 처리 - 안성시 타입
        if 'boardView' in func_body:
            # boardViewMatch 변수 정의 찾기
            boardview_var_match = re.search(r'boardViewMatch.*?match\(([^)]+)\)', func_body)
            if boardview_var_match:
                # URL 템플릿 찾기
                url_template_match = re.search(r'(?:const\s+)?detailUrl\s*=\s*[`\'"]([^`\'"]+)[`\'"]', func_body)
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
        special_params = ['notAncmtMgtNo', 'mgtNo', 'boardSeq', 'bbsSeq', 'articleNo', 'nttId', 'bbsNttSeq', 'articleId']
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
        print("\n=== anseong.json 확인 ===")
        print(f"셀렉터: {anseong_data['selectors'].get('list')}")
        print(f"onclick 패턴: {len(anseong_data['onclickPatterns'])}개")
        if anseong_data['onclickPatterns']:
            print(f"  - {anseong_data['onclickPatterns'][0]['description']}")

if __name__ == '__main__':
    main()