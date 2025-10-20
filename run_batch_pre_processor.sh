#!/bin/bash

# 배치 프리프로세서 실행 스크립트
# Eminwon과 Homepage 데이터를 모두 처리

SCRIPT_DIR="/home/zium/classfy_scraper"
LOG_DIR="$SCRIPT_DIR/logs"
PYTHON_PATH="/usr/bin/python3"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 현재 시간
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/batch_pre_processor_$TIMESTAMP.log"

# 스크립트 실행 디렉토리로 이동
cd "$SCRIPT_DIR"

echo "========================================" >> "$LOG_FILE"
echo "배치 프리프로세서 실행 시작: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 1. Eminwon 데이터 처리
echo "" >> "$LOG_FILE"
echo "1. Eminwon 데이터 처리 시작..." >> "$LOG_FILE"
$PYTHON_PATH batch_scraper_to_pre_processor.py --source eminwon >> "$LOG_FILE" 2>&1
EMINWON_RESULT=$?

if [ $EMINWON_RESULT -eq 0 ]; then
    echo "Eminwon 처리 성공" >> "$LOG_FILE"
else
    echo "Eminwon 처리 실패 (오류 코드: $EMINWON_RESULT)" >> "$LOG_FILE"
fi

# 2. Homepage 데이터 처리
echo "" >> "$LOG_FILE"
echo "2. Homepage 데이터 처리 시작..." >> "$LOG_FILE"
$PYTHON_PATH batch_scraper_to_pre_processor.py --source homepage >> "$LOG_FILE" 2>&1
HOMEPAGE_RESULT=$?

if [ $HOMEPAGE_RESULT -eq 0 ]; then
    echo "Homepage 처리 성공" >> "$LOG_FILE"
else
    echo "Homepage 처리 실패 (오류 코드: $HOMEPAGE_RESULT)" >> "$LOG_FILE"
fi

# 전체 결과 확인
if [ $EMINWON_RESULT -eq 0 ] && [ $HOMEPAGE_RESULT -eq 0 ]; then
    echo "" >> "$LOG_FILE"
    echo "모든 처리 성공: $(date)" >> "$LOG_FILE"
    EXIT_CODE=0
else
    echo "" >> "$LOG_FILE"
    echo "일부 처리 실패: $(date)" >> "$LOG_FILE"
    EXIT_CODE=1
fi

echo "========================================" >> "$LOG_FILE"
echo "배치 프리프로세서 실행 종료: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 30일 이상 된 로그 파일 삭제
find "$LOG_DIR" -name "batch_pre_processor_*.log" -mtime +30 -delete

exit $EXIT_CODE