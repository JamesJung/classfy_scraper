#!/usr/bin/env python3
"""
평탄화 구조 처리 테스트
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_directory_structure():
    """prv7, prv8 디렉토리 구조 확인"""
    
    # prv7, prv8 디렉토리 확인
    for prv_dir in ["prv7", "prv8"]:
        prv_path = Path(prv_dir)
        
        print(f"\n{'='*50}")
        print(f"{prv_dir.upper()} 디렉토리 구조 확인")
        print(f"{'='*50}")
        
        if not prv_path.exists():
            print(f"❌ {prv_dir} 디렉토리가 존재하지 않습니다.")
            continue
        
        # 하위 디렉토리들 확인
        subdirs = [d for d in prv_path.iterdir() if d.is_dir()]
        print(f"📁 총 {len(subdirs)}개 하위 디렉토리 발견")
        
        # 처음 10개 디렉토리 샘플 출력
        print(f"📋 디렉토리 샘플 (처음 10개):")
        for i, subdir in enumerate(subdirs[:10], 1):
            dir_name = subdir.name
            
            # content.md 파일 존재 여부 확인
            content_md = subdir / "content.md"
            attachments_dir = subdir / "attachments"
            
            has_content = "✅" if content_md.exists() else "❌"
            has_attachments = "📎" if attachments_dir.exists() else "  "
            
            print(f"  {i:2d}. {dir_name[:60]}... {has_content} {has_attachments}")
        
        # 2depth 구조인지 확인 (첫 번째 디렉토리 내부 확인)
        if subdirs:
            first_subdir = subdirs[0]
            nested_dirs = [d for d in first_subdir.iterdir() if d.is_dir()]
            
            print(f"\n🔍 구조 분석:")
            if nested_dirs:
                # 2depth 구조인지 확인
                nested_has_content = any((d / "content.md").exists() for d in nested_dirs[:5])
                if nested_has_content:
                    print(f"   📂 2depth 구조 감지: {first_subdir.name} 하위에 {len(nested_dirs)}개 디렉토리")
                    print(f"      예시: {nested_dirs[0].name if nested_dirs else 'N/A'}")
                else:
                    print(f"   📁 평탄화된 구조: content.md가 최상위에 위치")
            else:
                print(f"   📄 직접 구조: content.md가 바로 있음")
        
        print(f"\n💡 사용법:")
        print(f"   # 2depth 구조 (기본): python announcement_prv_processor.py --data {prv_dir}")
        print(f"   # 평탄화 구조:       python announcement_prv_processor.py --data {prv_dir} --flat")

if __name__ == "__main__":
    test_directory_structure()