#!/usr/bin/env python3
"""
PRV7 폴더 구조 평탄화 스크립트

현재 구조: prv7/지역1/지역2/공고폴더
목표 구조: prv7/지역1_지역2_공고폴더

실행 방법:
python flatten_prv7.py
"""

import os
import shutil
from pathlib import Path


def sanitize_folder_name(name):
    """폴더명에서 불안전한 문자 제거"""
    # 파일시스템에서 문제가 될 수 있는 문자들 제거/대체
    unsafe_chars = ['<', '>', ':', '"', '|', '?', '*', '/', '\\']
    for char in unsafe_chars:
        name = name.replace(char, '_')
    
    # 연속된 공백을 하나로 줄이고 앞뒤 공백 제거
    name = ' '.join(name.split())
    
    # 너무 긴 이름 제한 (255자 제한)
    if len(name) > 200:
        name = name[:200] + "..."
    
    return name


def flatten_prv7():
    """PRV7 폴더 구조를 평탄화"""
    base_path = Path("prv7")
    
    if not base_path.exists():
        print("prv7 폴더를 찾을 수 없습니다.")
        return
    
    # 백업 폴더 생성
    backup_path = Path("prv7_backup")
    if not backup_path.exists():
        print("원본 백업을 생성합니다...")
        shutil.copytree(base_path, backup_path)
        print(f"백업 완료: {backup_path}")
    
    print("PRV7 폴더 평탄화를 시작합니다...")
    
    moved_count = 0
    error_count = 0
    duplicate_count = 0
    
    # 3단계 깊이의 모든 공고 폴더 찾기
    for region1_path in base_path.iterdir():
        if not region1_path.is_dir():
            continue
            
        region1_name = sanitize_folder_name(region1_path.name)
        
        for region2_path in region1_path.iterdir():
            if not region2_path.is_dir():
                continue
                
            region2_name = sanitize_folder_name(region2_path.name)
            
            for announcement_path in region2_path.iterdir():
                if not announcement_path.is_dir():
                    continue
                    
                announcement_name = sanitize_folder_name(announcement_path.name)
                
                # 새 폴더명 생성: 지역1_지역2_공고폴더
                new_folder_name = f"{region1_name}_{region2_name}_{announcement_name}"
                new_path = base_path / new_folder_name
                
                try:
                    # 중복 폴더명 처리
                    counter = 1
                    original_new_path = new_path
                    while new_path.exists():
                        new_path = base_path / f"{original_new_path.name}_{counter}"
                        counter += 1
                        if counter > 1:
                            duplicate_count += 1
                    
                    # 폴더 이동
                    shutil.move(str(announcement_path), str(new_path))
                    moved_count += 1
                    
                    if moved_count % 100 == 0:
                        print(f"진행상황: {moved_count}개 폴더 이동 완료")
                        
                except Exception as e:
                    print(f"오류 발생 - {announcement_path}: {e}")
                    error_count += 1
    
    print(f"\n평탄화 완료!")
    print(f"이동된 폴더: {moved_count}개")
    print(f"중복 처리: {duplicate_count}개")
    print(f"오류 발생: {error_count}개")
    
    # 빈 폴더들 정리
    print("\n빈 폴더들을 정리합니다...")
    cleanup_empty_folders(base_path)
    
    print(f"\n완료! prv7 폴더가 평탄화되었습니다.")
    print(f"원본 백업은 {backup_path}에 보관되었습니다.")


def cleanup_empty_folders(base_path):
    """빈 폴더들 삭제"""
    deleted_count = 0
    
    # 2단계까지의 모든 폴더를 역순으로 확인 (하위부터)
    for region1_path in base_path.iterdir():
        if not region1_path.is_dir():
            continue
            
        # region2 폴더들 먼저 삭제
        for region2_path in region1_path.iterdir():
            if region2_path.is_dir():
                try:
                    # 폴더가 비어있으면 삭제
                    if not any(region2_path.iterdir()):
                        region2_path.rmdir()
                        deleted_count += 1
                        print(f"빈 폴더 삭제: {region2_path}")
                except:
                    pass
        
        # region1 폴더 삭제
        try:
            if not any(region1_path.iterdir()):
                region1_path.rmdir()
                deleted_count += 1
                print(f"빈 폴더 삭제: {region1_path}")
        except:
            pass
    
    print(f"삭제된 빈 폴더: {deleted_count}개")


if __name__ == "__main__":
    print("=" * 50)
    print("PRV7 폴더 평탄화 도구")
    print("=" * 50)
    
    flatten_prv7()