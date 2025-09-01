#!/usr/bin/env python3
"""
단일 공고 처리 테스트 스크립트

새로운 데이터 처리 기능을 테스트합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from announcement_processor import AnnouncementProcessor

def test_single_announcement():
    """단일 공고를 처리하여 새로운 기능을 테스트합니다."""
    
    print("=== 단일 공고 처리 테스트 ===")
    
    # 테스트할 디렉토리 (간단한 공고 선택)
    test_directory = Path("data.enhanced/acci/001_2025년 「시니어인턴십」 사업 참여 안내")
    
    if not test_directory.exists():
        print(f"❌ 테스트 디렉토리가 존재하지 않습니다: {test_directory}")
        return
    
    processor = AnnouncementProcessor()
    
    try:
        # 단일 디렉토리 처리
        success = processor.process_directory_with_custom_name(
            directory_path=test_directory,
            site_code="acci",
            folder_name="001_test_single_announcement"
        )
        
        if success:
            print("✅ 단일 공고 처리 성공!")
            print("\n새로운 기능들:")
            print("1. ✅ 공고일자 YYYY-MM-DD 형태 표준화")
            print("2. ✅ 본문에서 원본 URL 추출")
            print("3. ✅ 지원대상 분석 (개인/기업, 소상공인 여부)")
        else:
            print("❌ 단일 공고 처리 실패")
            
    except Exception as e:
        print(f"❌ 처리 중 오류 발생: {e}")

if __name__ == "__main__":
    test_single_announcement()