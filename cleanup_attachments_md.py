#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
attachments 폴더 내 .md 파일 삭제 스크립트

지정된 폴더 하위의 모든 attachments 폴더에서 .md 파일만 삭제합니다.
content.md 파일은 절대 삭제하지 않습니다.
"""

import os
import sys
import glob
import argparse
from pathlib import Path

def cleanup_attachments_md(base_folder: str, dry_run: bool = False) -> dict:
    """
    지정된 폴더 하위의 모든 attachments 폴더에서 .md 파일 삭제
    
    Args:
        base_folder: 기준 폴더 경로
        dry_run: True면 실제 삭제하지 않고 삭제될 파일만 출력
        
    Returns:
        dict: 삭제 결과 통계
    """
    if not os.path.exists(base_folder):
        print(f"❌ 폴더가 존재하지 않습니다: {base_folder}")
        return {"error": "folder_not_found"}
    
    stats = {
        "total_attachments_folders": 0,
        "md_files_found": 0,
        "md_files_deleted": 0,
        "errors": 0,
        "files_list": []
    }
    
    # attachments 폴더들 찾기
    attachments_pattern = os.path.join(base_folder, "**", "attachments")
    attachments_folders = glob.glob(attachments_pattern, recursive=True)
    
    stats["total_attachments_folders"] = len(attachments_folders)
    
    print(f"📁 기준 폴더: {base_folder}")
    print(f"🔍 찾은 attachments 폴더: {len(attachments_folders)}개")
    
    if dry_run:
        print("🔬 DRY RUN 모드: 실제 삭제는 하지 않습니다.")
    
    print("-" * 60)
    
    for attachments_folder in attachments_folders:
        try:
            # attachments 폴더 내 .md 파일 찾기
            md_pattern = os.path.join(attachments_folder, "*.md")
            md_files = glob.glob(md_pattern)
            
            if not md_files:
                continue
                
            print(f"\n📂 {attachments_folder}")
            
            for md_file in md_files:
                filename = os.path.basename(md_file)
                
                # content.md 파일은 절대 삭제하지 않음
                if filename.lower() == "content.md":
                    print(f"  ⏭️  건너뜀: {filename} (content.md는 삭제하지 않음)")
                    continue
                
                stats["md_files_found"] += 1
                stats["files_list"].append(md_file)
                
                if dry_run:
                    print(f"  🔍 삭제 예정: {filename}")
                else:
                    try:
                        os.remove(md_file)
                        stats["md_files_deleted"] += 1
                        print(f"  ✅ 삭제 완료: {filename}")
                    except Exception as e:
                        stats["errors"] += 1
                        print(f"  ❌ 삭제 실패: {filename} - {e}")
                        
        except Exception as e:
            stats["errors"] += 1
            print(f"❌ 폴더 처리 중 오류 {attachments_folder}: {e}")
    
    return stats

def main():
    parser = argparse.ArgumentParser(
        description="attachments 폴더 내 .md 파일 삭제 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python cleanup_attachments_md.py /Users/jin/classfy_scraper/data.enhanced/cceiDaeGu
  python cleanup_attachments_md.py /path/to/folder --dry-run
        """
    )
    
    parser.add_argument(
        "folder",
        help="처리할 기준 폴더 경로"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 삭제하지 않고 삭제될 파일만 출력"
    )
    
    args = parser.parse_args()
    
    # 폴더 경로 정규화
    folder_path = os.path.abspath(os.path.expanduser(args.folder))
    
    print("🧹 attachments 폴더 .md 파일 정리 도구")
    print("=" * 60)
    
    # 삭제 실행
    stats = cleanup_attachments_md(folder_path, dry_run=args.dry_run)
    
    if "error" in stats:
        sys.exit(1)
    
    # 결과 출력
    print("\n" + "=" * 60)
    print("📊 처리 결과")
    print(f"  • attachments 폴더: {stats['total_attachments_folders']}개")
    print(f"  • 발견된 .md 파일: {stats['md_files_found']}개")
    
    if args.dry_run:
        print(f"  • 삭제 예정 파일: {stats['md_files_found']}개")
        print("\n💡 실제 삭제하려면 --dry-run 옵션을 제거하고 다시 실행하세요.")
    else:
        print(f"  • 삭제된 파일: {stats['md_files_deleted']}개")
        print(f"  • 삭제 실패: {stats['errors']}개")
        
        if stats['md_files_deleted'] > 0:
            print("✅ 정리 완료!")
        elif stats['md_files_found'] == 0:
            print("✅ 삭제할 .md 파일이 없습니다.")

if __name__ == "__main__":
    main()