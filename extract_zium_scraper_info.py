#!/usr/bin/env python3
import os
import re
import glob

def extract_scraper_info(file_path, scraper_type):
    """
    스크래퍼 파일에서 site_code, list_url 등을 추출

    Args:
        file_path: 스크래퍼 파일의 절대 경로
        scraper_type: 'advanced' 또는 'enhanced'

    Returns:
        dict: {site_code, list_url, scraper_path, scraper_name}
    """
    # 파일명에서 site_code 추출
    filename = os.path.basename(file_path)

    if scraper_type == 'advanced':
        # advanced_XXX.py -> XXX
        site_code = filename.replace('advanced_', '').replace('.py', '')
    else:  # enhanced
        # enhanced_XXX_scraper.py -> XXX
        site_code = filename.replace('enhanced_', '').replace('_scraper.py', '')

    # base_scraper는 제외
    if site_code == 'base' or site_code == '':
        return None

    # 파일 내용에서 list_url 추출
    list_url = None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

            # list_url 패턴 찾기 (여러 패턴 시도)
            patterns = [
                r'list_url\s*=\s*["\']([^"\']+)["\']',
                r'LIST_URL\s*=\s*["\']([^"\']+)["\']',
                r'url\s*=\s*["\']([^"\']+)["\']',
                r'base_url\s*=\s*["\']([^"\']+)["\']',
            ]

            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    list_url = match.group(1)
                    break
    except Exception as e:
        print(f"Error reading {file_path}: {e}")

    # scraper_path (절대 경로)
    scraper_path = file_path

    # scraper_name (enhanced/XXX 또는 advanced/XXX)
    scraper_name = f"{scraper_type}/{site_code}"

    return {
        'site_code': site_code,
        'list_url': list_url or '',
        'scraper_path': scraper_path,
        'scraper_name': scraper_name
    }

def main():
    base_path = '/Users/jin/zium_scraper/scraper'

    results = []

    # advanced 디렉토리의 모든 .py 파일 처리
    advanced_files = glob.glob(os.path.join(base_path, 'advanced', 'advanced_*.py'))
    for file_path in advanced_files:
        info = extract_scraper_info(file_path, 'advanced')
        if info:
            results.append(info)

    # enhanced 디렉토리의 모든 _scraper.py 파일 처리
    enhanced_files = glob.glob(os.path.join(base_path, 'enhanced', 'enhanced_*_scraper.py'))
    for file_path in enhanced_files:
        info = extract_scraper_info(file_path, 'enhanced')
        if info:
            results.append(info)

    # 결과를 site_url.txt에 추가할 형식으로 출력
    print(f"총 {len(results)}개의 스크래퍼 정보를 추출했습니다.\n")

    # site_url.txt 형식으로 출력
    output_lines = []
    for info in results:
        line = f"{info['site_code']}\t{info['list_url']}\t{info['scraper_path']}\t{info['scraper_name']}"
        output_lines.append(line)
        print(line)

    # site_url.txt에 저장
    output_file = '/Users/jin/classfy_scraper/site_url.txt'
    try:
        # 기존 파일 읽기 (있다면)
        existing_lines = []
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_lines = f.read().splitlines()

        # 새로운 내용 추가
        with open(output_file, 'a', encoding='utf-8') as f:
            for line in output_lines:
                # 중복 체크 (site_code 기준)
                site_code = line.split('\t')[0]
                if not any(existing_line.startswith(site_code + '\t') for existing_line in existing_lines):
                    f.write(line + '\n')

        print(f"\n결과가 {output_file}에 추가되었습니다.")
    except Exception as e:
        print(f"파일 저장 중 오류 발생: {e}")

if __name__ == '__main__':
    main()
