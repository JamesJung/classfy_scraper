#!/usr/bin/env python3

import os
import json
import csv
from pathlib import Path

# eminwon.json 파일 읽기
with open('node/scraper/eminwon.json', 'r', encoding='utf-8') as f:
    eminwon_data = json.load(f)

# 지역명 매핑 (eminwon.json의 키 -> eminwon_data 폴더명)
region_mapping = {
    "서울강서구": "서울강서",
    "금천구": "금천",
    "도봉구": "도봉",
    "동작구": "동작",
    "서초구": "서초",
    "강동구": "강동",
    "부산강서구": "부산강서",
    "부산서구": "부산서",
    "부산남구": "부산남",
    "부산진구": "부산진",
    "부산중구": "부산중",
    "부산동구": "부산동",
    "부산북구": "부산북",
    "해운대구": "해운대",
    "사상구": "사상",
    "사하구": "사하",
    "수영구": "수영",
    "동래구": "동래",
    "대구북구": "대구북",
    "대구동구": "대구동",
    "대구남구": "대구남",
    "대구중구": "대구중",
    "달성군": "달성",
    "달서구": "달서",
    "수성구": "수성",
    "대구서구": "대구서",
    "인천중구": "인천중",
    "연수구": "연수",
    "인천광역시": "인천광역시",
    "광주광역시": "광주광역시",
    "광주북구": "광주북",
    "광주동구": "광주동",
    "광주남구": "광주남",
    "대전광역시": "대전광역시",
    "대전서구": "대전서",
    "대전동구": "대전동",
    "대전중구": "대전중",
    "유성구": "유성",
    "대덕구": "대덕",
    "울산광역시": "울산광역시",
    "울산남구": "울산남",
    "울산동구": "울산동",
    "울산북구": "울산북",
    "울산중구": "울산중",
    "경기도": "경기도",
    "충청북도": "충청북도",
    "충청남도": "충청남도",
    "전라남도": "전라남도",
    "제주특별자치도": "제주특별자치도",
    "강원특별자치도": "강원특별자치도",
    "전북특별자치도": "전북특별자치도",
    "강원고성군": "강원고성",
    "속초시": "속초",
    "양양군": "양양",
    "정선군": "정선",
    "춘천시": "춘천",
    "평창군": "평창",
    "화천군": "화천",
    "가평군": "가평",
    "고양시": "고양",
    "과천시": "과천",
    "구리시": "구리",
    "군포시": "군포",
    "부천시": "부천",
    "성남시": "성남",
    "수원시": "수원",
    "안산시": "안산",
    "안양시": "안양",
    "양주시": "양주",
    "연천군": "연천",
    "용인시": "용인",
    "의왕시": "의왕",
    "포천시": "포천",
    "하남시": "하남",
    "화성시": "화성",
    "경상남도고성군": "경상남도고성",
    "남해군": "남해",
    "봉화군": "봉화",
    "밀양시": "밀양",
    "사천시": "사천",
    "진주시": "진주",
    "함안군": "함안",
    "함양군": "함양",
    "합천군": "합천",
    "상주시": "상주",
    "예천군": "예천",
    "고흥군": "고흥",
    "담양군": "담양",
    "보성군": "보성",
    "영광군": "영광",
    "화순군": "화순",
    "고창군": "고창",
    "군산시": "군산",
    "무주군": "무주",
    "순창군": "순창",
    "완주군": "완주",
    "익산시": "익산",
    "임실군": "임실",
    "장수군": "장수",
    "전주시": "전주",
    "정읍시": "정읍",
    "진안군": "진안",
    "공주시": "공주",
    "논산시": "논산",
    "당진시": "당진",
    "보령시": "보령",
    "부여군": "부여",
    "서산시": "서산",
    "서천군": "서천",
    "아산시": "아산",
    "예산군": "예산",
    "천안시": "천안",
    "청양군": "청양",
    "태안군": "태안",
    "괴산군": "괴산",
    "단양군": "단양",
    "증평군": "증평",
    "진천군": "진천",
    "청주시": "청주",
    "남양주": "남양주",
    "기장군": "기장"
}

# 결과 저장용 리스트
results = []
total_count = 0
found_count = 0
not_found_regions = []

# eminwon_data 디렉토리에서 실제 존재하는 폴더 목록 가져오기
eminwon_data_path = Path('eminwon_data')
actual_folders = set()
if eminwon_data_path.exists():
    for folder in eminwon_data_path.iterdir():
        if folder.is_dir():
            actual_folders.add(folder.name)

print("=" * 80)
print(f"eminwon.json에 등록된 지역 수: {len(eminwon_data)}")
print(f"eminwon_data 폴더에 있는 지역 수: {len(actual_folders)}")
print("=" * 80)

# 각 지역별로 content.md 파일 개수 카운트
for region_key, domain in eminwon_data.items():
    # 폴더명 찾기 (매핑 또는 원본 키 사용)
    folder_name = region_mapping.get(region_key, region_key)
    
    # eminwon_data 디렉토리 경로
    region_path = eminwon_data_path / folder_name
    
    if region_path.exists():
        # 해당 지역 폴더 내의 모든 하위 폴더에서 content.md 파일 찾기
        content_md_count = 0
        for subdir in region_path.iterdir():
            if subdir.is_dir():
                content_md_file = subdir / 'content.md'
                if content_md_file.exists():
                    content_md_count += 1
        
        results.append({
            'region_key': region_key,
            'folder_name': folder_name,
            'domain': domain,
            'content_md_count': content_md_count,
            'status': 'found'
        })
        found_count += 1
        total_count += content_md_count
        print(f"✓ {region_key:15} -> {folder_name:15} : {content_md_count:4}개")
    else:
        # 폴더가 없는 경우
        results.append({
            'region_key': region_key,
            'folder_name': folder_name,
            'domain': domain,
            'content_md_count': 0,
            'status': 'not_found'
        })
        not_found_regions.append(region_key)
        print(f"✗ {region_key:15} -> {folder_name:15} : 폴더 없음")

print("=" * 80)
print(f"총 지역 수: {len(eminwon_data)}")
print(f"찾은 지역 수: {found_count}")
print(f"못 찾은 지역 수: {len(not_found_regions)}")
print(f"총 content.md 파일 수: {total_count}")
print("=" * 80)

# CSV 파일로 저장
csv_filename = 'eminwon_count_result.csv'
with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
    fieldnames = ['지역명(json)', '폴더명', '도메인', 'content.md 개수', '상태']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    
    writer.writeheader()
    for result in results:
        writer.writerow({
            '지역명(json)': result['region_key'],
            '폴더명': result['folder_name'],
            '도메인': result['domain'],
            'content.md 개수': result['content_md_count'],
            '상태': result['status']
        })

print(f"\n결과가 {csv_filename} 파일로 저장되었습니다.")

# TXT 파일로도 저장
txt_filename = 'eminwon_count_result.txt'
with open(txt_filename, 'w', encoding='utf-8') as txtfile:
    txtfile.write("=" * 80 + "\n")
    txtfile.write("eminwon 지역별 content.md 파일 개수 집계\n")
    txtfile.write("=" * 80 + "\n\n")
    
    txtfile.write(f"총 지역 수: {len(eminwon_data)}\n")
    txtfile.write(f"찾은 지역 수: {found_count}\n")
    txtfile.write(f"못 찾은 지역 수: {len(not_found_regions)}\n")
    txtfile.write(f"총 content.md 파일 수: {total_count}\n\n")
    
    txtfile.write("-" * 80 + "\n")
    txtfile.write("지역별 상세 내역:\n")
    txtfile.write("-" * 80 + "\n\n")
    
    for result in sorted(results, key=lambda x: x['content_md_count'], reverse=True):
        status = "✓" if result['status'] == 'found' else "✗"
        txtfile.write(f"{status} {result['region_key']:20} -> {result['folder_name']:20} : {result['content_md_count']:5}개\n")
    
    if not_found_regions:
        txtfile.write("\n" + "-" * 80 + "\n")
        txtfile.write("폴더를 찾을 수 없는 지역:\n")
        txtfile.write("-" * 80 + "\n")
        for region in not_found_regions:
            txtfile.write(f"  - {region}\n")

print(f"결과가 {txt_filename} 파일로도 저장되었습니다.")

# eminwon_data에는 있지만 json에는 없는 폴더 찾기
print("\n" + "=" * 80)
print("eminwon_data에는 있지만 json에 없는 폴더:")
print("-" * 80)

mapped_folders = set()
for region_key in eminwon_data.keys():
    folder_name = region_mapping.get(region_key, region_key)
    mapped_folders.add(folder_name)

unmapped_folders = actual_folders - mapped_folders
if unmapped_folders:
    for folder in sorted(unmapped_folders):
        # 해당 폴더의 content.md 개수 확인
        folder_path = eminwon_data_path / folder
        content_md_count = 0
        for subdir in folder_path.iterdir():
            if subdir.is_dir():
                content_md_file = subdir / 'content.md'
                if content_md_file.exists():
                    content_md_count += 1
        print(f"  - {folder:20} : {content_md_count:4}개")
else:
    print("  없음")