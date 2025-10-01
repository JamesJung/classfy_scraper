#!/usr/bin/env python3
"""
eminwon_data의 attachments 폴더에서 .md 파일들을 삭제하는 스크립트
content.md는 삭제하지 않음 (attachments 폴더 내의 .md 파일만 삭제)
"""

import os
import glob
from pathlib import Path

def clean_md_files_in_attachments():
    base_dir = Path("/Users/jin/classfy_scraper/eminwon_data")
    
    if not base_dir.exists():
        print(f"❌ 디렉토리가 존재하지 않습니다: {base_dir}")
        return
    
    # attachments 폴더 내의 모든 .md 파일 찾기
    md_files = glob.glob(str(base_dir / "**" / "attachments" / "*.md"), recursive=True)
    
    total_files = len(md_files)
    deleted_count = 0
    error_count = 0
    
    print(f"🔍 발견된 .md 파일: {total_files}개")
    
    if total_files == 0:
        print("✅ 삭제할 .md 파일이 없습니다.")
        return
    
    # 사용자 확인
    print(f"\n⚠️  {total_files}개의 .md 파일을 attachments 폴더에서 삭제합니다.")
    response = input("계속하시겠습니까? (y/N): ")
    
    if response.lower() != 'y':
        print("❌ 작업이 취소되었습니다.")
        return
    
    print("\n🗑️  파일 삭제 시작...")
    
    for file_path in md_files:
        try:
            # 안전 체크: attachments 폴더 내의 파일인지 확인
            if "/attachments/" in file_path:
                os.remove(file_path)
                deleted_count += 1
                
                # 진행 상황 표시 (100개마다)
                if deleted_count % 100 == 0:
                    print(f"  진행중... {deleted_count}/{total_files} 삭제됨")
            else:
                print(f"  ⚠️  스킵 (attachments 폴더가 아님): {file_path}")
                
        except Exception as e:
            error_count += 1
            print(f"  ❌ 삭제 실패: {file_path}")
            print(f"     오류: {str(e)}")
    
    # 결과 출력
    print("\n" + "="*50)
    print("📊 작업 완료")
    print(f"  ✅ 삭제 성공: {deleted_count}개")
    print(f"  ❌ 삭제 실패: {error_count}개")
    print(f"  📁 총 파일: {total_files}개")
    print("="*50)

if __name__ == "__main__":
    clean_md_files_in_attachments()