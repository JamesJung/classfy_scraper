#!/bin/bash

# 크론탭 설정 스크립트
SCRIPT_PATH="/Users/jin/classfy_scraper/run_scrapers_batch.sh"

echo "크론탭 설정을 시작합니다..."

# 현재 크론탭 백업
crontab -l > /tmp/current_cron_backup.txt 2>/dev/null

# 새로운 크론탭 설정
echo "다음 중 원하는 스케줄을 선택하세요:"
echo "1) 매일 새벽 2시 실행"
echo "2) 매일 오전 6시와 오후 6시 실행 (하루 2번)"
echo "3) 매 4시간마다 실행"
echo "4) 매 시간 실행"
echo "5) 평일(월-금) 오전 9시 실행"
echo "6) 사용자 정의"

read -p "선택 (1-6): " choice

case $choice in
    1)
        CRON_SCHEDULE="0 2 * * *"
        DESCRIPTION="매일 새벽 2시"
        ;;
    2)
        CRON_SCHEDULE="0 6,18 * * *"
        DESCRIPTION="매일 오전 6시와 오후 6시"
        ;;
    3)
        CRON_SCHEDULE="0 */4 * * *"
        DESCRIPTION="매 4시간마다"
        ;;
    4)
        CRON_SCHEDULE="0 * * * *"
        DESCRIPTION="매 시간"
        ;;
    5)
        CRON_SCHEDULE="0 9 * * 1-5"
        DESCRIPTION="평일 오전 9시"
        ;;
    6)
        echo "크론 표현식을 직접 입력하세요 (예: 0 2 * * *):"
        read CRON_SCHEDULE
        DESCRIPTION="사용자 정의"
        ;;
    *)
        echo "잘못된 선택입니다."
        exit 1
        ;;
esac

# 크론탭에 추가할 라인
CRON_LINE="$CRON_SCHEDULE $SCRIPT_PATH # 공고 스크래퍼 자동 실행 - $DESCRIPTION"

# 기존 크론탭에서 동일한 스크립트 실행 라인 제거
crontab -l 2>/dev/null | grep -v "$SCRIPT_PATH" > /tmp/new_cron.txt

# 새로운 크론 작업 추가
echo "$CRON_LINE" >> /tmp/new_cron.txt

# 크론탭 업데이트
crontab /tmp/new_cron.txt

echo ""
echo "크론탭이 설정되었습니다!"
echo "설정된 스케줄: $DESCRIPTION"
echo "크론 표현식: $CRON_SCHEDULE"
echo ""
echo "현재 크론탭 내용:"
crontab -l | grep "$SCRIPT_PATH"
echo ""
echo "크론탭 전체 내용을 확인하려면: crontab -l"
echo "크론탭을 편집하려면: crontab -e"
echo "크론탭을 삭제하려면: crontab -r"