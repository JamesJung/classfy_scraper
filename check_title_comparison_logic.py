#!/usr/bin/env python3
"""
각 스크래퍼 파일에서 제목 비교 로직이 있는지 체크하는 스크립트
"""

import os
import re
from pathlib import Path
from datetime import datetime

# 스크래퍼 디렉토리
SCRAPER_DIR = Path("/Users/jin/classfy_scraper/node/scraper")

def check_title_comparison(file_path, site_code):
    """파일에서 제목 비교 로직을 찾기"""
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 제목 비교와 관련된 패턴들
        patterns = {
            'exact_title_match': [
                r'announcement\.title\s*===?\s*',  # announcement.title === something
                r'title\s*===?\s*',                # title === something
                r'\.title.*?===',                  # .title ... ===
            ],
            'includes_title': [
                r'\.includes\([\'"`].*?title',     # .includes("...title")
                r'title.*?\.includes\(',           # title.includes(
            ],
            'indexOf_title': [
                r'\.indexOf\([\'"`].*?title',      # .indexOf("...title")
                r'title.*?\.indexOf\(',            # title.indexOf(
            ],
            'startsWith_endsWith': [
                r'\.startsWith\([\'"`]',           # .startsWith("...")
                r'\.endsWith\([\'"`]',             # .endsWith("...")
            ],
            'regex_title': [
                r'title.*?\.match\(',              # title.match(
                r'title.*?\.test\(',               # title.test(
                r'new RegExp.*?title',             # new RegExp(...title...)
            ],
            'lastProcessedTitle': [
                r'lastProcessedTitle',             # lastProcessedTitle 변수
                r'previousTitle',                  # previousTitle 변수
                r'latestTitle',                    # latestTitle 변수
            ],
            'break_on_condition': [
                r'if\s*\(.*?title.*?\).*?break',   # if (..title..) break
                r'if\s*\(.*?title.*?\).*?return',  # if (..title..) return
            ]
        }
        
        findings = {}
        
        for pattern_type, pattern_list in patterns.items():
            for pattern in pattern_list:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    if pattern_type not in findings:
                        findings[pattern_type] = []
                    findings[pattern_type].extend(matches[:3])  # 최대 3개 예시만
        
        # 추가로 제목으로 중복 체크하는 로직 찾기
        duplicate_patterns = [
            r'processedTitles',
            r'seenTitles',
            r'existingTitles',
            r'duplicateCheck',
            r'Set\(\).*?title',  # Set에 title 추가
            r'Map\(\).*?title',  # Map에 title 추가
        ]
        
        for pattern in duplicate_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                if 'duplicate_check' not in findings:
                    findings['duplicate_check'] = []
                findings['duplicate_check'].append(pattern)
        
        # 날짜 비교 패턴도 체크
        date_comparison_patterns = [
            r'targetDate.*?[<>=]',
            r'fromDate.*?[<>=]',
            r'startDate.*?[<>=]',
            r'announcement\.date.*?[<>=]',
        ]
        
        for pattern in date_comparison_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                if 'date_comparison' not in findings:
                    findings['date_comparison'] = []
                findings['date_comparison'].append(pattern)
        
        return findings
        
    except Exception as e:
        return {'error': str(e)}


def main():
    print("=" * 80)
    print("스크래퍼 제목 비교 로직 체크")
    print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # 모든 스크래퍼 파일 찾기
    scraper_files = sorted(SCRAPER_DIR.glob("*_scraper.js"))
    
    print(f"\n총 {len(scraper_files)}개 스크래퍼 파일 발견\n")
    
    results = {
        'with_title_logic': [],
        'without_title_logic': [],
        'with_date_logic': [],
        'errors': []
    }
    
    for scraper_file in scraper_files:
        site_code = scraper_file.stem.replace('_scraper', '')
        findings = check_title_comparison(scraper_file, site_code)
        
        if 'error' in findings:
            results['errors'].append({
                'site_code': site_code,
                'error': findings['error']
            })
        elif findings:
            # 날짜 비교 로직이 있는지 체크
            if 'date_comparison' in findings:
                results['with_date_logic'].append(site_code)
            
            # 제목 관련 로직이 있는지 체크 (date_comparison 제외)
            title_related_findings = {k: v for k, v in findings.items() if k != 'date_comparison'}
            if title_related_findings:
                results['with_title_logic'].append({
                    'site_code': site_code,
                    'logic_types': list(title_related_findings.keys()),
                    'examples': title_related_findings
                })
            else:
                results['without_title_logic'].append(site_code)
        else:
            results['without_title_logic'].append(site_code)
    
    # 결과 출력
    print(f"\n📊 분석 결과:")
    print(f"  - 제목 비교 로직 있음: {len(results['with_title_logic'])}개")
    print(f"  - 제목 비교 로직 없음: {len(results['without_title_logic'])}개")
    print(f"  - 날짜 비교 로직 있음: {len(results['with_date_logic'])}개")
    print(f"  - 오류 발생: {len(results['errors'])}개")
    
    # 상세 결과를 파일로 저장
    output_file = Path("/Users/jin/classfy_scraper/scraper_title_logic_report.md")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# 스크래퍼 제목 비교 로직 분석 보고서\n\n")
        f.write(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## 요약\n")
        f.write(f"- 총 스크래퍼 수: {len(scraper_files)}개\n")
        f.write(f"- 제목 비교 로직 있음: {len(results['with_title_logic'])}개\n")
        f.write(f"- 제목 비교 로직 없음: {len(results['without_title_logic'])}개\n")
        f.write(f"- 날짜 비교 로직 있음: {len(results['with_date_logic'])}개\n\n")
        
        f.write("## 제목 비교 로직이 있는 스크래퍼\n\n")
        if results['with_title_logic']:
            for item in results['with_title_logic']:
                f.write(f"### {item['site_code']}\n")
                f.write(f"- 로직 유형: {', '.join(item['logic_types'])}\n")
                f.write("- 예시:\n")
                for logic_type, examples in item['examples'].items():
                    f.write(f"  - {logic_type}: {examples[:2]}\n")
                f.write("\n")
        else:
            f.write("없음\n\n")
        
        f.write("## 제목 비교 로직이 없는 스크래퍼\n\n")
        if results['without_title_logic']:
            # 10개씩 줄바꿈하여 출력
            for i in range(0, len(results['without_title_logic']), 10):
                batch = results['without_title_logic'][i:i+10]
                f.write(f"- {', '.join(batch)}\n")
        else:
            f.write("없음\n\n")
        
        f.write("\n## 날짜 비교 로직이 있는 스크래퍼\n\n")
        if results['with_date_logic']:
            for i in range(0, len(results['with_date_logic']), 10):
                batch = results['with_date_logic'][i:i+10]
                f.write(f"- {', '.join(batch)}\n")
        else:
            f.write("없음\n\n")
        
        if results['errors']:
            f.write("\n## 오류 발생 스크래퍼\n\n")
            for item in results['errors']:
                f.write(f"- {item['site_code']}: {item['error']}\n")
    
    print(f"\n✅ 분석 완료!")
    print(f"📄 상세 보고서 저장: {output_file}")
    
    # 제목 비교 로직이 없는 스크래퍼 목록만 따로 저장
    no_title_logic_file = Path("/Users/jin/classfy_scraper/scrapers_without_title_logic.txt")
    with open(no_title_logic_file, 'w', encoding='utf-8') as f:
        f.write("# 제목 비교 로직이 없는 스크래퍼 목록\n\n")
        f.write(f"총 {len(results['without_title_logic'])}개\n\n")
        for site_code in results['without_title_logic']:
            f.write(f"{site_code}\n")
    
    print(f"📄 제목 비교 없는 스크래퍼 목록: {no_title_logic_file}")


if __name__ == "__main__":
    main()