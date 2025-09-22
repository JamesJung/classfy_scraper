#!/usr/bin/env python3

import os
import re
from pathlib import Path
import shutil

def normalize_site_code(site_code: str) -> str:
    """site_code 정규화 - 시/군/구 제거"""
    normalized = re.sub(r'(시|군|구)$', '', site_code)
    return normalized

def rename_folders():
    """2025-09-22 폴더들을 정규화된 이름으로 변경"""
    base_path = Path('eminwon_data_new/2025-09-22')
    
    if not base_path.exists():
        print(f"❌ {base_path} 폴더가 존재하지 않습니다.")
        return
    
    # 모든 하위 폴더 가져오기
    folders = [d for d in base_path.iterdir() if d.is_dir()]
    
    renamed_count = 0
    skipped_count = 0
    
    print(f"총 {len(folders)}개 폴더 발견")
    print("="*60)
    
    for folder in sorted(folders):
        folder_name = folder.name
        
        # 이미 정규화된 이름이면 스킵
        if not (folder_name.endswith('시') or folder_name.endswith('군') or folder_name.endswith('구')):
            print(f"⏭️  {folder_name:20} (이미 정규화됨)")
            skipped_count += 1
            continue
        
        # 정규화된 이름 생성
        normalized_name = normalize_site_code(folder_name)
        new_path = base_path / normalized_name
        
        # 이미 존재하는 경우 처리
        if new_path.exists():
            print(f"⚠️  {folder_name:20} -> {normalized_name:15} (이미 존재, 병합)")
            
            # 기존 폴더의 내용을 새 폴더로 이동
            for item in folder.iterdir():
                if item.name.startswith('.'):
                    continue  # 숨김 파일 스킵
                    
                target = new_path / item.name
                if not target.exists():
                    shutil.move(str(item), str(target))
                    print(f"    이동: {item.name}")
            
            # 빈 폴더 삭제
            try:
                folder.rmdir()
                print(f"    원본 폴더 삭제 완료")
            except OSError:
                print(f"    ⚠️ 원본 폴더에 파일이 남아있음")
        else:
            # 단순 이름 변경
            folder.rename(new_path)
            print(f"✅ {folder_name:20} -> {normalized_name}")
            renamed_count += 1
    
    print("="*60)
    print(f"완료: {renamed_count}개 변경, {skipped_count}개 스킵")
    
    # 결과 확인
    print("\n현재 폴더 목록:")
    folders_after = sorted([d.name for d in base_path.iterdir() if d.is_dir()])
    for folder in folders_after[:10]:
        print(f"  - {folder}")
    if len(folders_after) > 10:
        print(f"  ... 외 {len(folders_after)-10}개")

if __name__ == "__main__":
    print("2025-09-22 폴더명 정규화 시작")
    print("="*60)
    rename_folders()