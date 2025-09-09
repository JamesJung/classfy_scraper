#!/usr/bin/env python3
"""
날짜 필터링 기능 테스트
"""

import sys
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from announcement_prv_processor import AnnouncementPrvProcessor

def test_date_extraction():
    """날짜 추출 기능 테스트"""
    processor = AnnouncementPrvProcessor()
    
    # 테스트용 content.md 샘플들
    test_contents = [
        """
        ## 공고 제목
        등록일: 2025-07-05
        내용: 테스트 공고입니다.
        """,
        """
        공고일 2025년 7월 8일
        
        이 공고는 테스트용입니다.
        """,
        """
        작성일: 2025/07/12
        
        공고 내용
        """,
        """
        게시일 07/15/2025
        
        내용
        """,
        """
        공지일: 2025.08.01
        
        테스트 내용
        """,
        """
        일반적인 공고 내용으로 날짜가 없습니다.
        """,
        """
        2025년 6월 30일에 작성된 공고
        
        지원 내용: 창업 지원
        지원 대상: 스타트업
        """
    ]
    
    print("=" * 50)
    print("날짜 추출 테스트")
    print("=" * 50)
    
    for i, content in enumerate(test_contents, 1):
        print(f"\n[테스트 {i}]")
        print(f"내용: {content.strip()[:50]}...")
        
        extracted_date = processor._extract_date_from_content(content)
        if extracted_date:
            print(f"추출된 날짜: {extracted_date.strftime('%Y-%m-%d')}")
        else:
            print("날짜를 찾을 수 없음")

def test_date_filtering():
    """날짜 필터링 테스트"""
    print("\n" + "=" * 50)
    print("날짜 필터링 테스트")
    print("=" * 50)
    
    # 2025-07-10 이전만 처리하는 필터
    processor = AnnouncementPrvProcessor(date_filter="20250710")
    
    test_cases = [
        ("2025-07-05 공고", "등록일: 2025-07-05\n내용: 테스트"),  # 통과해야 함
        ("2025-07-10 공고", "작성일: 2025-07-10\n내용: 테스트"),  # 통과해야 함 (같은 날짜)
        ("2025-07-15 공고", "공고일: 2025-07-15\n내용: 테스트"),  # 건너뛰어야 함
        ("2025-08-01 공고", "게시일: 2025-08-01\n내용: 테스트"),  # 건너뛰어야 함
        ("날짜 없는 공고", "일반적인 공고 내용"),  # 건너뛰어야 함
    ]
    
    for name, content in test_cases:
        print(f"\n[테스트] {name}")
        should_process = processor._should_process_by_date(content)
        result = "처리함" if should_process else "건너뜀"
        print(f"결과: {result}")

def test_date_parsing():
    """날짜 파싱 테스트"""
    print("\n" + "=" * 50) 
    print("날짜 파싱 테스트")
    print("=" * 50)
    
    processor = AnnouncementPrvProcessor()
    
    test_dates = [
        "20250710",  # 올바른 형식
        "20250131",  # 올바른 형식
        "2025071",   # 잘못된 형식 (7자리)
        "202507100", # 잘못된 형식 (9자리)
        "20250732",  # 잘못된 날짜 (32일)
        "20251301",  # 잘못된 월 (13월)
        "abcd0710",  # 문자 포함
    ]
    
    for date_str in test_dates:
        print(f"\n[테스트] {date_str}")
        parsed_date = processor._parse_date_filter(date_str)
        if parsed_date:
            print(f"파싱 성공: {parsed_date.strftime('%Y-%m-%d')}")
        else:
            print("파싱 실패")

if __name__ == "__main__":
    test_date_parsing()
    test_date_extraction()
    test_date_filtering()