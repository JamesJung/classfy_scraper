#!/usr/bin/env python3

def load_db_urls(file_path):
    """DB에서 가져온 URL 파일 읽기"""
    db_dict = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # 첫 번째 줄은 헤더이므로 건너뛰기
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    site_code = parts[0]
                    announcement_url = parts[1]
                    db_dict[site_code] = announcement_url

        print(f"✅ DB에서 {len(db_dict)}개 레코드 로드")
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
                    site_url_dict[site_code] = list_url

        print(f"✅ site_url.txt에서 {len(site_url_dict)}개 레코드 로드")
        return site_url_dict
    except Exception as e:
        print(f"❌ 파일 읽기 실패: {e}")
        return {}

def normalize_url(url):
    """URL 정규화 (비교를 위해)"""
    if not url:
        return ""
    # 끝의 슬래시 제거
    url = url.rstrip('/')
    # http와 https 통일
    url = url.replace('http://', 'https://')
    return url

def compare_urls(db_data, file_data):
    """URL 비교"""
    print("\n" + "="*120)
    print("URL 비교 결과")
    print("="*120)

    # 1. DB에만 있는 사이트
    db_only = set(db_data.keys()) - set(file_data.keys())
    print(f"\n📊 DB에만 있는 사이트 ({len(db_only)}개):")
    if len(db_only) > 0:
        for site_code in sorted(db_only):
            print(f"  - {site_code}: {db_data[site_code]}")
    else:
        print("  (없음)")

    # 2. 파일에만 있는 사이트
    file_only = set(file_data.keys()) - set(db_data.keys())
    print(f"\n📊 site_url.txt에만 있는 사이트 ({len(file_only)}개):")
    if len(file_only) > 0:
        for site_code in sorted(file_only):
            print(f"  - {site_code}: {file_data[site_code]}")
    else:
        print("  (없음)")

    # 3. 양쪽 모두 있는 사이트
    common_sites = set(db_data.keys()) & set(file_data.keys())
    different_urls = []
    same_urls = []

    for site_code in common_sites:
        db_url = normalize_url(db_data[site_code])
        file_url = normalize_url(file_data[site_code])

        if db_url != file_url:
            different_urls.append((site_code, db_data[site_code], file_data[site_code]))
        else:
            same_urls.append(site_code)

    print(f"\n📊 양쪽 모두 있는 사이트 중 URL이 다른 경우 ({len(different_urls)}개):")
    if len(different_urls) > 0:
        for site_code, db_url, file_url in sorted(different_urls):
            print(f"\n  사이트: {site_code}")
            print(f"    DB:   {db_url}")
            print(f"    File: {file_url}")
    else:
        print("  (없음)")

    print(f"\n✅ 양쪽 모두 있고 URL이 동일한 사이트: {len(same_urls)}개")

    # 요약
    print("\n" + "="*120)
    print("📊 요약")
    print("="*120)
    print(f"DB에만 있음:                 {len(db_only):>4}개")
    print(f"파일에만 있음:               {len(file_only):>4}개")
    print(f"URL 다름:                    {len(different_urls):>4}개")
    print(f"URL 동일:                    {len(same_urls):>4}개")
    print(f"총 공통 사이트:              {len(common_sites):>4}개")
    print("-"*120)
    print(f"총 DB 레코드:                {len(db_data):>4}개")
    print(f"총 파일 레코드:              {len(file_data):>4}개")
    print("="*120)

    # 상세 통계
    print("\n" + "="*120)
    print("📊 상세 통계")
    print("="*120)
    total_unique_sites = len(set(db_data.keys()) | set(file_data.keys()))
    print(f"총 고유 사이트 수:           {total_unique_sites:>4}개")
    print(f"DB 커버리지:                 {len(db_data)/total_unique_sites*100:>5.1f}%")
    print(f"파일 커버리지:               {len(file_data)/total_unique_sites*100:>5.1f}%")
    if len(common_sites) > 0:
        print(f"URL 일치율 (공통 사이트):    {len(same_urls)/len(common_sites)*100:>5.1f}%")
    print("="*120)

def main():
    # DB 데이터 로드
    db_data = load_db_urls('/tmp/db_urls.txt')

    # site_url.txt 파일 로드
    file_data = load_site_url_file('/Users/jin/classfy_scraper/site_url.txt')

    # URL 비교
    compare_urls(db_data, file_data)

if __name__ == '__main__':
    main()
