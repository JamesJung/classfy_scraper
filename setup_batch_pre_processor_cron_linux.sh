#!/bin/bash

# 배치 프리프로세서 크론탭 설정 스크립트 (Linux 버전)
# 자동으로 프로젝트 경로를 감지하고 설정합니다

# 프로젝트 디렉토리 자동 감지
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="run_batch_pre_processor.sh"
SCRIPT_PATH="$SCRIPT_DIR/$SCRIPT_NAME"
PYTHON_PATH=$(which python3)
LOG_DIR="$SCRIPT_DIR/logs"

echo "========================================="
echo "  배치 프리프로세서 크론탭 설정 (Linux)"
echo "========================================="
echo ""
echo "프로젝트 정보:"
echo "  - 프로젝트 경로: $SCRIPT_DIR"
echo "  - 실행 스크립트: $SCRIPT_PATH"
echo "  - Python 경로: $PYTHON_PATH"
echo "  - 로그 경로: $LOG_DIR"
echo ""

# 스크립트 존재 확인
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "❌ 오류: $SCRIPT_PATH 파일이 없습니다."
    echo ""
    echo "다음 명령으로 파일을 생성하세요:"
    echo "cat > $SCRIPT_PATH << 'EOF'"
    cat << 'SCRIPT_CONTENT'
#!/bin/bash

# 배치 프리프로세서 실행 스크립트
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

# 1. Eminwon 데이터 처리 (오늘 날짜)
echo "" >> "$LOG_FILE"
echo "1. Eminwon 데이터 처리 시작..." >> "$LOG_FILE"
$PYTHON_PATH batch_scraper_to_pre_processor.py --source eminwon >> "$LOG_FILE" 2>&1
EMINWON_RESULT=$?

# 2. Homepage 데이터 처리 (오늘 날짜)
echo "" >> "$LOG_FILE"
echo "2. Homepage 데이터 처리 시작..." >> "$LOG_FILE"
$PYTHON_PATH batch_scraper_to_pre_processor.py --source homepage >> "$LOG_FILE" 2>&1
HOMEPAGE_RESULT=$?

echo "========================================" >> "$LOG_FILE"
echo "배치 프리프로세서 실행 종료: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 30일 이상 된 로그 파일 삭제
find "$LOG_DIR" -name "batch_pre_processor_*.log" -mtime +30 -delete

exit 0
SCRIPT_CONTENT
    echo "EOF"
    echo "chmod +x $SCRIPT_PATH"
    exit 1
fi

# 실행 권한 확인
if [ ! -x "$SCRIPT_PATH" ]; then
    chmod +x "$SCRIPT_PATH"
    echo "✅ $SCRIPT_NAME 에 실행 권한을 부여했습니다."
fi

echo "이 스크립트는 다음 데이터를 처리합니다:"
echo "  1. Eminwon 데이터 (eminwon_data_new/YYYY-MM-DD)"
echo "  2. Homepage 데이터 (scraped_incremental_v2/YYYY-MM-DD)"
echo ""

# 현재 크론탭 백업
BACKUP_FILE="/tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt"
crontab -l > "$BACKUP_FILE" 2>/dev/null
echo "현재 크론탭을 백업했습니다: $BACKUP_FILE"
echo ""

# 기존 설정 확인
EXISTING_CRON=$(crontab -l 2>/dev/null | grep "$SCRIPT_PATH" | head -n1)
if [ ! -z "$EXISTING_CRON" ]; then
    echo "⚠️  기존 크론탭 설정이 있습니다:"
    echo "$EXISTING_CRON"
    echo ""
    read -p "기존 설정을 덮어쓰시겠습니까? (y/n): " overwrite
    if [ "$overwrite" != "y" ] && [ "$overwrite" != "Y" ]; then
        echo "설정을 취소합니다."
        exit 0
    fi
fi

# 스케줄 선택
echo "원하는 실행 스케줄을 선택하세요:"
echo ""
echo "=== 권장 설정 ==="
echo "1) 매일 새벽 3시 30분 실행 (스크래퍼 실행 후 처리)"
echo "2) 매일 오전 6시, 오후 2시, 밤 10시 실행 (하루 3번)"
echo ""
echo "=== 기타 설정 ==="
echo "3) 매일 특정 시간 실행 (직접 입력)"
echo "4) 매 4시간마다 실행"
echo "5) 평일(월-금) 오전 10시 실행"
echo "6) 사용자 정의 크론 표현식"
echo "7) 취소"
echo ""

read -p "선택 (1-7): " choice

case $choice in
    1)
        CRON_SCHEDULE="30 3 * * *"
        DESCRIPTION="매일 새벽 3시 30분"
        ;;
    2)
        CRON_SCHEDULE="0 6,14,22 * * *"
        DESCRIPTION="매일 오전 6시, 오후 2시, 밤 10시"
        ;;
    3)
        read -p "실행할 시간을 입력하세요 (0-23): " hour
        if [[ "$hour" =~ ^[0-9]+$ ]] && [ "$hour" -ge 0 ] && [ "$hour" -le 23 ]; then
            CRON_SCHEDULE="0 $hour * * *"
            DESCRIPTION="매일 $hour시"
        else
            echo "잘못된 시간입니다."
            exit 1
        fi
        ;;
    4)
        CRON_SCHEDULE="0 */4 * * *"
        DESCRIPTION="매 4시간마다"
        ;;
    5)
        CRON_SCHEDULE="0 10 * * 1-5"
        DESCRIPTION="평일 오전 10시"
        ;;
    6)
        echo "크론 표현식을 직접 입력하세요."
        echo "형식: 분 시 일 월 요일"
        echo "예시: 0 3 * * * (매일 새벽 3시)"
        read -p "크론 표현식: " CRON_SCHEDULE
        DESCRIPTION="사용자 정의"
        ;;
    7)
        echo "설정을 취소합니다."
        exit 0
        ;;
    *)
        echo "잘못된 선택입니다."
        exit 1
        ;;
esac

# 크론탭에 추가할 라인 (환경변수 포함)
CRON_COMMENT="# 배치 프리프로세서 자동 실행 - $DESCRIPTION"
CRON_LINE="$CRON_SCHEDULE cd $SCRIPT_DIR && $SCRIPT_PATH >> $LOG_DIR/cron_execution.log 2>&1"

# 기존 크론탭에서 동일한 스크립트 실행 라인 제거
crontab -l 2>/dev/null | grep -v "$SCRIPT_PATH" > /tmp/new_cron_pre_processor.txt

# 새로운 크론 작업 추가
echo "$CRON_COMMENT" >> /tmp/new_cron_pre_processor.txt
echo "$CRON_LINE" >> /tmp/new_cron_pre_processor.txt

# 크론탭 업데이트
crontab /tmp/new_cron_pre_processor.txt

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 크론탭이 성공적으로 설정되었습니다!"
    echo ""
    echo "📋 설정 정보:"
    echo "  - 스케줄: $DESCRIPTION"
    echo "  - 크론 표현식: $CRON_SCHEDULE"
    echo "  - 실행 스크립트: $SCRIPT_PATH"
    echo "  - 로그 디렉토리: $LOG_DIR"
    echo ""
    echo "📌 현재 설정된 배치 프리프로세서 크론탭:"
    crontab -l | grep -A1 "배치 프리프로세서"
    echo ""
    echo "🛠️  유용한 명령어:"
    echo "  크론탭 전체 확인: crontab -l"
    echo "  크론탭 편집: crontab -e"
    echo "  크론탭 삭제: crontab -r"
    echo "  크론 서비스 상태: systemctl status crond (또는 cron)"
    echo "  실시간 로그 확인: tail -f $LOG_DIR/batch_pre_processor_*.log"
    echo "  크론 실행 로그: tail -f $LOG_DIR/cron_execution.log"
    echo ""
    echo "📝 다음 실행 예정 시간 확인:"
    echo "  크론탭 테스트: crontab -l | cronitor predict"
    echo "  또는 온라인 도구 사용: https://crontab.guru/#$CRON_SCHEDULE"
else
    echo ""
    echo "❌ 크론탭 설정에 실패했습니다."
    echo "수동으로 설정하려면 다음 명령을 사용하세요:"
    echo "crontab -e"
    echo ""
    echo "그리고 다음 라인을 추가하세요:"
    echo "$CRON_COMMENT"
    echo "$CRON_LINE"
fi

# 임시 파일 정리
rm -f /tmp/new_cron_pre_processor.txt