#!/usr/bin/env python3
"""
날짜 추출 디버깅 스크립트
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from announcement_prv_processor import AnnouncementPrvProcessor

def test_date_extraction():
    processor = AnnouncementPrvProcessor(date_filter="20250705")
    
    # 실제 content.md 파일 읽기
    content_path = Path("test_final_date/final_festival/content.md")
    if content_path.exists():
        with open(content_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print("=== Content.md 내용 ===")
        print(content[:200])
        print("\n" + "="*50)
        
        # 날짜 추출 테스트
        extracted_date = processor._extract_date_from_content(content)
        print(f"추출된 날짜: {extracted_date}")
        
        # 필터링 테스트
        should_process = processor._should_process_by_date(content)
        print(f"처리 여부: {should_process}")
        
        # 필터 날짜 확인
        print(f"필터 날짜: {processor.filter_date}")
        
    else:
        print("테스트 파일이 없습니다")

if __name__ == "__main__":
    test_date_extraction()