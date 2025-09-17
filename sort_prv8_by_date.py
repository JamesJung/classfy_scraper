#!/usr/bin/env python3
"""
prv8 폴더들을 작성일 기준으로 정렬하는 스크립트
"""

import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def extract_date_from_content(content_md: str) -> Optional[datetime]:
    """content.md에서 작성일을 추출합니다."""
    if not content_md:
        return None
    
    # 다양한 날짜 패턴 정의
    date_patterns = [
        # YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD 형식
        r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',
        # YYYY년 M월 D일 형식
        r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',
        # MM/DD/YYYY, MM-DD-YYYY 형식
        r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})',
        # 등록일, 작성일, 공고일 등의 키워드와 함께 나오는 패턴
        r'(?:등록일|작성일|공고일|게시일|공지일|발표일)[\s:]*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',
        r'(?:등록일|작성일|공고일|게시일|공지일|발표일)[\s:]*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',
        # 마크다운 형식: **작성일**: 2025.07.29
        r'\*\*(?:등록일|작성일|공고일|게시일|공지일|발표일)\*\*[\s:]*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',
    ]
    
    try:
        for pattern in date_patterns:
            matches = re.findall(pattern, content_md)
            
            for match in matches:
                try:
                    if len(match) == 3:
                        # 패턴에 따라 년, 월, 일 순서 결정
                        if pattern.startswith(r'(\d{1,2})'):  # MM/DD/YYYY 형식
                            month, day, year = map(int, match)
                        else:  # YYYY/MM/DD 형식
                            year, month, day = map(int, match)
                        
                        # 날짜 유효성 검사
                        if 1 <= month <= 12 and 1 <= day <= 31 and 2020 <= year <= 2030:
                            extracted_date = datetime(year, month, day)
                            return extracted_date
                            
                except (ValueError, TypeError):
                    continue
        
        return None
        
    except Exception as e:
        print(f"날짜 추출 중 오류: {e}")
        return None

def get_folders_with_dates(prv_path: Path) -> List[Tuple[str, Optional[datetime], str]]:
    """prv8 폴더들과 그들의 날짜를 가져옵니다."""
    folders_with_dates = []
    
    if not prv_path.exists():
        print(f"❌ {prv_path} 디렉토리가 존재하지 않습니다.")
        return []
    
    # 하위 디렉토리들 확인
    subdirs = [d for d in prv_path.iterdir() if d.is_dir()]
    total_dirs = len(subdirs)
    
    print(f"📁 총 {total_dirs}개 폴더 처리 시작...")
    
    for i, folder_path in enumerate(subdirs, 1):
        folder_name = folder_path.name
        content_md_path = folder_path / "content.md"
        
        # 진행률 표시
        if i % 1000 == 0 or i == total_dirs:
            print(f"  진행: {i}/{total_dirs} ({i/total_dirs*100:.1f}%)")
        
        extracted_date = None
        date_str = "날짜 없음"
        
        if content_md_path.exists():
            try:
                with open(content_md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                extracted_date = extract_date_from_content(content)
                if extracted_date:
                    date_str = extracted_date.strftime('%Y-%m-%d')
                
            except Exception as e:
                date_str = f"읽기 실패: {e}"
        else:
            date_str = "content.md 없음"
        
        folders_with_dates.append((folder_name, extracted_date, date_str))
    
    return folders_with_dates

def sort_and_display_results(folders_with_dates: List[Tuple[str, Optional[datetime], str]]):
    """결과를 정렬하고 표시합니다."""
    print(f"\n📊 정렬 결과 분석...")
    
    # 날짜가 있는 것과 없는 것 분리
    with_date = [(name, date, date_str) for name, date, date_str in folders_with_dates if date is not None]
    without_date = [(name, date, date_str) for name, date, date_str in folders_with_dates if date is None]
    
    # 날짜가 있는 것들을 날짜 순으로 정렬
    with_date.sort(key=lambda x: x[1])
    
    print(f"✅ 날짜 추출 성공: {len(with_date)}개 폴더")
    print(f"❌ 날짜 추출 실패: {len(without_date)}개 폴더")
    
    # 날짜별 분포 확인
    if with_date:
        earliest = with_date[0][1]
        latest = with_date[-1][1]
        print(f"📅 날짜 범위: {earliest.strftime('%Y-%m-%d')} ~ {latest.strftime('%Y-%m-%d')}")
    
    # 결과를 파일에 저장
    output_file = "prv8_folders_sorted_by_date.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("PRV8 폴더 날짜별 정렬 결과\n")
        f.write("=" * 80 + "\n")
        f.write(f"총 폴더 수: {len(folders_with_dates)}개\n")
        f.write(f"날짜 추출 성공: {len(with_date)}개\n")
        f.write(f"날짜 추출 실패: {len(without_date)}개\n")
        
        if with_date:
            f.write(f"날짜 범위: {earliest.strftime('%Y-%m-%d')} ~ {latest.strftime('%Y-%m-%d')}\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("날짜순 정렬 결과 (오래된 순)\n")
        f.write("=" * 80 + "\n")
        
        for i, (folder_name, date, date_str) in enumerate(with_date, 1):
            f.write(f"{i:5d}. [{date_str}] {folder_name}\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("날짜 추출 실패 목록\n")
        f.write("=" * 80 + "\n")
        
        for i, (folder_name, date, date_str) in enumerate(without_date, 1):
            f.write(f"{i:5d}. [{date_str}] {folder_name}\n")
    
    print(f"\n💾 결과가 {output_file} 파일에 저장되었습니다.")
    
    # 화면에 일부 결과 표시
    print(f"\n📋 날짜순 정렬 결과 (처음 20개):")
    print("-" * 80)
    for i, (folder_name, date, date_str) in enumerate(with_date[:20], 1):
        # 폴더명이 길면 줄임
        display_name = folder_name[:60] + "..." if len(folder_name) > 60 else folder_name
        print(f"{i:3d}. [{date_str}] {display_name}")
    
    if len(with_date) > 20:
        print(f"... (총 {len(with_date)}개 중 20개만 표시)")
    
    # 날짜별 분포 요약
    if with_date:
        print(f"\n📈 날짜별 분포 요약:")
        date_counts = {}
        for _, date, _ in with_date:
            year_month = date.strftime('%Y-%m')
            date_counts[year_month] = date_counts.get(year_month, 0) + 1
        
        # 상위 10개 월별 분포
        sorted_months = sorted(date_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        for month, count in sorted_months:
            print(f"  {month}: {count}개")

def main():
    """메인 함수"""
    print("=" * 60)
    print("PRV8 폴더 날짜별 정렬 스크립트")
    print("=" * 60)
    
    prv8_path = Path("prv8")
    
    # 폴더들과 날짜 정보 수집
    folders_with_dates = get_folders_with_dates(prv8_path)
    
    if not folders_with_dates:
        print("처리할 폴더가 없습니다.")
        return
    
    # 결과 정렬 및 표시
    sort_and_display_results(folders_with_dates)
    
    print(f"\n✅ 처리 완료!")

if __name__ == "__main__":
    main()