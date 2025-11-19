#!/usr/bin/env python3
from datetime import datetime

def load_db_urls(file_path):
    """DB에서 가져온 URL 파일 읽기"""
    db_dict = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    site_code = parts[0]
                    announcement_url = parts[1]
                    if announcement_url and announcement_url != 'NULL' and announcement_url.strip() != '':
                        db_dict[site_code] = announcement_url
        return db_dict
    except Exception as e:
        print(f"❌ DB 파일 읽기 실패: {e}")
        return {}

def load_site_url_file(file_path):
    """site_url.txt 파일 읽기"""
    site_url_dict = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    site_code = parts[0]
                    list_url = parts[1]
                    if list_url and list_url.strip() != '':
                        site_url_dict[site_code] = list_url
        return site_url_dict
    except Exception as e:
        print(f"❌ 파일 읽기 실패: {e}")
        return {}

def normalize_url(url):
    """URL 정규화 (비교를 위해)"""
    if not url:
        return ""
    url = url.rstrip('/')
    url = url.replace('http://', 'https://')
    if '#' in url:
        url = url.split('#')[0]
    return url

def generate_report(db_data, file_data, output_file):
    """상세 비교 리포트 생성"""

    with open(output_file, 'w', encoding='utf-8') as f:
        # 헤더
        f.write("="*150 + "\n")
        f.write("MySQL SITE_MASTER vs site_url.txt URL 비교 결과\n")
        f.write(f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*150 + "\n\n")

        # 통계
        db_only = set(db_data.keys()) - set(file_data.keys())
        file_only = set(file_data.keys()) - set(db_data.keys())
        common_sites = set(db_data.keys()) & set(file_data.keys())

        different_urls = []
        same_urls = []

        for site_code in common_sites:
            db_url = normalize_url(db_data[site_code])
            file_url = normalize_url(file_data[site_code])
            if db_url != file_url:
                different_urls.append(site_code)
            else:
                same_urls.append(site_code)

        total_unique_sites = len(set(db_data.keys()) | set(file_data.keys()))

        f.write("[전체 통계]\n")
        f.write(f"- 총 고유 사이트 수: {total_unique_sites}개\n")
        f.write(f"- DB 레코드: {len(db_data)}개 ({len(db_data)/total_unique_sites*100:.1f}% 커버리지)\n")
        f.write(f"- 파일 레코드: {len(file_data)}개 ({len(file_data)/total_unique_sites*100:.1f}% 커버리지)\n")
        f.write(f"- 공통 사이트: {len(common_sites)}개\n")
        f.write(f"  * URL 동일: {len(same_urls)}개 ({len(same_urls)/len(common_sites)*100:.1f}%)\n")
        f.write(f"  * URL 다름: {len(different_urls)}개 ({len(different_urls)/len(common_sites)*100:.1f}%)\n")
        f.write(f"- DB에만 있음: {len(db_only)}개\n")
        f.write(f"- 파일에만 있음: {len(file_only)}개\n\n")

        f.write("="*150 + "\n")
        f.write("[상세 비교 결과]\n")
        f.write("형식: 테이블URL | 파일URL | SITE_CODE | 결과\n")
        f.write("="*150 + "\n\n")

        # 1. URL이 동일한 경우
        f.write(f"■ URL 동일 ({len(same_urls)}개)\n")
        f.write("-"*150 + "\n")
        for site_code in sorted(same_urls):
            db_url = db_data[site_code]
            file_url = file_data[site_code]
            f.write(f"{db_url} | {file_url} | {site_code} | 일치\n")
        f.write("\n")

        # 2. URL이 다른 경우
        f.write(f"■ URL 다름 ({len(different_urls)}개)\n")
        f.write("-"*150 + "\n")
        for site_code in sorted(different_urls):
            db_url = db_data[site_code]
            file_url = file_data[site_code]
            f.write(f"{db_url} | {file_url} | {site_code} | 불일치\n")
        f.write("\n")

        # 3. DB에만 있는 경우
        f.write(f"■ DB에만 있음 ({len(db_only)}개)\n")
        f.write("-"*150 + "\n")
        for site_code in sorted(db_only):
            db_url = db_data[site_code]
            f.write(f"{db_url} | (없음) | {site_code} | DB에만존재\n")
        f.write("\n")

        # 4. 파일에만 있는 경우
        f.write(f"■ 파일에만 있음 ({len(file_only)}개)\n")
        f.write("-"*150 + "\n")
        for site_code in sorted(file_only):
            file_url = file_data[site_code]
            f.write(f"(없음) | {file_url} | {site_code} | 파일에만존재\n")
        f.write("\n")

        f.write("="*150 + "\n")
        f.write("리포트 종료\n")
        f.write("="*150 + "\n")

    print(f"✅ 리포트가 {output_file}에 저장되었습니다.")

def main():
    # DB 데이터 로드
    print("DB 데이터 로드 중...")
    db_data = load_db_urls('/tmp/db_urls_all.txt')
    print(f"✅ DB에서 {len(db_data)}개 레코드 로드")

    # site_url.txt 파일 로드
    print("site_url.txt 파일 로드 중...")
    file_data = load_site_url_file('/Users/jin/classfy_scraper/site_url.txt')
    print(f"✅ site_url.txt에서 {len(file_data)}개 레코드 로드")

    # 리포트 생성
    print("\n리포트 생성 중...")
    output_file = '/Users/jin/classfy_scraper/url_comparison_report.txt'
    generate_report(db_data, file_data, output_file)

if __name__ == '__main__':
    main()
