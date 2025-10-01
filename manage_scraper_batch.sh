#!/bin/bash

# 스크래퍼 배치 관리 스크립트

SCRIPT_DIR="/Users/jin/classfy_scraper"
BATCH_SCRIPT="$SCRIPT_DIR/run_scrapers_batch.sh"
LOG_DIR="$SCRIPT_DIR/logs"

echo "========================================="
echo "  공고 스크래퍼 배치 관리 도구"
echo "========================================="
echo ""
echo "1) 크론탭 설정/변경"
echo "2) 수동으로 스크래퍼 실행"
echo "3) 현재 크론탭 확인"
echo "4) 크론탭 삭제"
echo "5) 최근 로그 확인"
echo "6) 로그 디렉토리 열기"
echo "7) 종료"
echo ""

read -p "선택 (1-7): " choice

case $choice in
    1)
        echo "크론탭을 설정합니다..."
        bash "$SCRIPT_DIR/setup_cron.sh"
        ;;
    2)
        echo "스크래퍼를 수동으로 실행합니다..."
        bash "$BATCH_SCRIPT"
        echo "실행이 완료되었습니다. 로그를 확인하세요."
        ;;
    3)
        echo "현재 설정된 크론탭:"
        crontab -l | grep "$BATCH_SCRIPT" || echo "설정된 크론탭이 없습니다."
        ;;
    4)
        echo "스크래퍼 관련 크론탭을 삭제합니다..."
        crontab -l | grep -v "$BATCH_SCRIPT" | crontab -
        echo "삭제되었습니다."
        ;;
    5)
        echo "최근 로그 파일:"
        if [ -d "$LOG_DIR" ]; then
            LATEST_LOG=$(ls -t "$LOG_DIR"/scraper_batch_*.log 2>/dev/null | head -1)
            if [ -n "$LATEST_LOG" ]; then
                echo "파일: $LATEST_LOG"
                echo "----------------------------------------"
                tail -n 50 "$LATEST_LOG"
            else
                echo "로그 파일이 없습니다."
            fi
        else
            echo "로그 디렉토리가 없습니다."
        fi
        ;;
    6)
        echo "로그 디렉토리를 엽니다..."
        mkdir -p "$LOG_DIR"
        open "$LOG_DIR" 2>/dev/null || echo "로그 디렉토리: $LOG_DIR"
        ;;
    7)
        echo "종료합니다."
        exit 0
        ;;
    *)
        echo "잘못된 선택입니다."
        exit 1
        ;;
esac