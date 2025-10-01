#!/usr/bin/env python3
"""
기존 프로세스가 종료되기를 기다린 후 DB 업데이트를 실행하는 스크립트
"""

import time
import subprocess
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def check_process_running(process_name="announcement_pre_processor"):
    """특정 프로세스가 실행 중인지 확인"""
    try:
        result = subprocess.run(
            ['pgrep', '-f', process_name],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except:
        return False

def wait_for_db_available():
    """DB 연결이 가능해질 때까지 대기"""
    print("⏳ 기존 프로세스 종료 대기 중...")
    
    while check_process_running():
        print(".", end="", flush=True)
        time.sleep(10)
    
    print("\n✅ 기존 프로세스가 종료되었습니다.")
    print("DB 업데이트를 시작합니다...")
    
    # test_db_update.py 실행
    subprocess.run([sys.executable, "test_db_update.py"])
    
    # 또는 run_incremental_scrapers_v2.py 실행
    # subprocess.run([sys.executable, "run_incremental_scrapers_v2.py"])

if __name__ == "__main__":
    print("🔄 DB 업데이트 대기 스크립트")
    print("=" * 50)
    
    if check_process_running():
        print("⚠️ announcement_pre_processor.py가 실행 중입니다.")
        print("종료될 때까지 기다립니다...")
        wait_for_db_available()
    else:
        print("✅ 실행 중인 프로세스가 없습니다.")
        print("DB 업데이트를 즉시 실행합니다...")
        subprocess.run([sys.executable, "test_db_update.py"])