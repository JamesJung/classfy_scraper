#!/bin/bash

# 배치 프리프로세서 크론탭 설정 스크립트
SCRIPT_PATH="/Users/jin/classfy_scraper/run_batch_pre_processor.sh"

echo "========================================="
echo "  배치 프리프로세서 크론탭 설정"
echo "========================================="
echo ""
echo "이 스크립트는 다음 데이터를 처리합니다:"
echo "  1. Eminwon 데이터 (eminwon_data_new/YYYY-MM-DD)"
echo "  2. Homepage 데이터 (scraped_incremental_v2/YYYY-MM-DD)"
echo ""

# 현재 크론탭 백업
crontab -l > /tmp/current_cron_backup_pre_processor.txt 2>/dev/null

# 스케줄 선택
echo "원하는 실행 스케줄을 선택하세요:"
echo "1) 매일 새벽 3시 실행 (스크래퍼 실행 후)"
echo "2) 매일 오전 7시와 오후 7시 실행 (하루 2번)"
echo "3) 매 6시간마다 실행"
echo "4) 평일(월-금) 오전 10시 실행"
echo "5) 사용자 정의"
echo "6) 취소"

read -p "선택 (1-6): " choice

case $choice in
    1)
        CRON_SCHEDULE="0 3 * * *"
        DESCRIPTION="매일 새벽 3시"
        ;;
    2)
        CRON_SCHEDULE="0 7,19 * * *"
        DESCRIPTION="매일 오전 7시와 오후 7시"
        ;;
    3)
        CRON_SCHEDULE="0 */6 * * *"
        DESCRIPTION="매 6시간마다"
        ;;
    4)
        CRON_SCHEDULE="0 10 * * 1-5"
        DESCRIPTION="평일 오전 10시"
        ;;
    5)
        echo "크론 표현식을 직접 입력하세요 (예: 0 3 * * *):"
        read CRON_SCHEDULE
        DESCRIPTION="사용자 정의"
        ;;
    6)
        echo "설정을 취소합니다."
        exit 0
        ;;
    *)
        echo "잘못된 선택입니다."
        exit 1
        ;;
esac

# 크론탭에 추가할 라인
CRON_LINE="$CRON_SCHEDULE $SCRIPT_PATH # 배치 프리프로세서 자동 실행 - $DESCRIPTION"

# 기존 크론탭에서 동일한 스크립트 실행 라인 제거
crontab -l 2>/dev/null | grep -v "$SCRIPT_PATH" > /tmp/new_cron_pre_processor.txt

# 새로운 크론 작업 추가
echo "$CRON_LINE" >> /tmp/new_cron_pre_processor.txt

# 크론탭 업데이트
crontab /tmp/new_cron_pre_processor.txt

echo ""
echo "✅ 크론탭이 설정되었습니다!"
echo ""
echo "설정 정보:"
echo "  - 스케줄: $DESCRIPTION"
echo "  - 크론 표현식: $CRON_SCHEDULE"
echo "  - 실행 스크립트: $SCRIPT_PATH"
echo ""
echo "현재 설정된 배치 프리프로세서 크론탭:"
crontab -l | grep "$SCRIPT_PATH"
echo ""
echo "유용한 명령어:"
echo "  크론탭 전체 확인: crontab -l"
echo "  크론탭 편집: crontab -e"
echo "  크론탭 삭제: crontab -r"
echo "  로그 확인: tail -f /Users/jin/classfy_scraper/logs/batch_pre_processor_*.log"