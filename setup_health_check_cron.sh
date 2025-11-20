#!/bin/bash
#
# Health Check Cron Job 설정 스크립트
#
# 사용법:
#   ./setup_health_check_cron.sh
#
# 기능:
#   - 매일 자정(00:00)에 health check 실행
#   - 로그를 logs/health_check.log에 저장
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEALTH_CHECK_SCRIPT="$SCRIPT_DIR/health_check.js"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/health_check.log"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# Node.js 경로 확인
NODE_PATH=$(which node)
if [ -z "$NODE_PATH" ]; then
    echo "❌ Node.js를 찾을 수 없습니다. Node.js를 설치해주세요."
    exit 1
fi

echo "========================================="
echo "  Health Check Cron Job 설정"
echo "========================================="
echo "Node.js 경로: $NODE_PATH"
echo "스크립트 경로: $HEALTH_CHECK_SCRIPT"
echo "로그 파일: $LOG_FILE"
echo ""

# 기존 crontab 백업
echo "기존 crontab 백업 중..."
crontab -l > "$SCRIPT_DIR/crontab_backup_$(date +%Y%m%d_%H%M%S).txt" 2>/dev/null || true

# crontab 항목 생성
CRON_JOB="0 0 * * * $NODE_PATH $HEALTH_CHECK_SCRIPT >> $LOG_FILE 2>&1"

# 기존 crontab에 health_check.js가 있는지 확인
if crontab -l 2>/dev/null | grep -q "health_check.js"; then
    echo "⚠️  기존 health_check cron job이 이미 존재합니다."
    echo ""
    echo "현재 등록된 cron job:"
    crontab -l | grep "health_check.js"
    echo ""
    read -p "기존 항목을 제거하고 새로 등록하시겠습니까? (y/N): " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # 기존 항목 제거
        (crontab -l 2>/dev/null | grep -v "health_check.js") | crontab -
        echo "✓ 기존 항목 제거 완료"
    else
        echo "설정을 취소했습니다."
        exit 0
    fi
fi

# 새 cron job 추가
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "✓ Cron job 등록 완료!"
echo ""
echo "등록된 cron job:"
crontab -l | grep "health_check.js"
echo ""
echo "========================================="
echo "  설정 완료"
echo "========================================="
echo "실행 스케줄: 매일 자정 (00:00)"
echo "로그 파일: $LOG_FILE"
echo ""
echo "수동 실행: node $HEALTH_CHECK_SCRIPT"
echo "cron 확인: crontab -l"
echo "cron 제거: crontab -l | grep -v 'health_check.js' | crontab -"
echo ""
