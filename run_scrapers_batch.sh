#!/bin/bash

# 스크립트 실행 경로
SCRIPT_DIR="/home/zium/classfy_scraper"
LOG_DIR="$SCRIPT_DIR/logs"
PYTHON_PATH="/usr/bin/python3"  # Python 경로 확인 필요

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 현재 시간
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/scraper_batch_$TIMESTAMP.log"

# 스크립트 실행 디렉토리로 이동
cd "$SCRIPT_DIR"

echo "========================================" >> "$LOG_FILE"
echo "스크래퍼 배치 실행 시작: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# Python 스크립트 실행
$PYTHON_PATH run_incremental_scrapers_v2.py >> "$LOG_FILE" 2>&1

# 실행 결과 확인
if [ $? -eq 0 ]; then
    echo "스크래퍼 실행 성공: $(date)" >> "$LOG_FILE"
else
    echo "스크래퍼 실행 실패: $(date)" >> "$LOG_FILE"
    echo "오류 코드: $?" >> "$LOG_FILE"
fi

echo "========================================" >> "$LOG_FILE"
echo "스크래퍼 배치 종료: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 30일 이상 된 로그 파일 삭제
find "$LOG_DIR" -name "scraper_batch_*.log" -mtime +30 -delete