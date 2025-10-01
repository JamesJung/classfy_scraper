#!/bin/bash

# ========================================
# Eminwon Batch Processor 일일 실행 스크립트
# 매일 새벽 6시 20분 실행용
# ========================================

# 기본 디렉토리 설정
ROOT_DIR="/home/zium/classfy_scraper"
LOG_DIR="/home/zium/classfy_scraper/logs"
DATE=$(date +%Y%m%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/eminwon_batch_${DATE}.log"

# 환경 설정
export PATH="/usr/local/bin:/usr/bin:/bin"
cd $ROOT_DIR

# logs 디렉토리가 없으면 생성
mkdir -p $LOG_DIR

# .env 파일 로드
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "========================================" >> "$LOG_FILE"
echo "Eminwon Batch Processor 시작: $(date)" >> "$LOG_FILE"
echo "처리 대상: ${YESTERDAY}" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 시작 시간 기록
START_TIME=$(date +%s)

# Python 및 환경 확인
echo "Python version: $(python3 --version)" >> "$LOG_FILE"
echo "Working directory: $(pwd)" >> "$LOG_FILE"

# 어제 날짜 데이터 처리 (보통 새벽에 전날 데이터를 처리)
echo "[시작] 배치 처리 시작..." >> "$LOG_FILE"
/usr/bin/python3 eminwon_batch_scraper_to_pre_processor.py --date ${YESTERDAY} --workers 5 >> "$LOG_FILE" 2>&1

# 종료 코드 확인
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[완료] ✅ 배치 처리 성공" >> "$LOG_FILE"
    
    # 처리 결과 요약 출력
    if [ -f "${LOG_DIR}/eminwon_batch_results_${YESTERDAY}.json" ]; then
        echo "" >> "$LOG_FILE"
        echo "처리 결과 요약:" >> "$LOG_FILE"
        python3 -c "
import json
with open('${LOG_DIR}/eminwon_batch_results_${YESTERDAY}.json') as f:
    data = json.load(f)
    stats = data.get('stats', {})
    print(f\"  - 전체 지역: {stats.get('total_regions', 0)}개\")
    print(f\"  - 성공: {stats.get('success', 0)}개\")
    print(f\"  - 실패: {stats.get('failed', 0)}개\")
    print(f\"  - 스킵: {stats.get('skipped', 0)}개\")
    print(f\"  - 전체 공고: {stats.get('total_announcements', 0)}개\")
" >> "$LOG_FILE" 2>&1
    fi
else
    echo "[실패] ❌ 배치 처리 실패 (Exit code: $EXIT_CODE)" >> "$LOG_FILE"
    
    # 에러 알림 (선택사항: 이메일, Slack 등)
    # echo "Eminwon batch processing failed on $(date)" | mail -s "Batch Processing Failed" admin@example.com
fi

# 종료 시간 및 총 실행 시간 계산
END_TIME=$(date +%s)
ELAPSED_TIME=$((END_TIME - START_TIME))
ELAPSED_MIN=$((ELAPSED_TIME / 60))
ELAPSED_SEC=$((ELAPSED_TIME % 60))

echo "========================================" >> "$LOG_FILE"
echo "Eminwon Batch Processor 종료: $(date)" >> "$LOG_FILE"
echo "총 실행 시간: ${ELAPSED_MIN}분 ${ELAPSED_SEC}초" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# 로그 파일 크기 관리 (30일 이상 된 로그 삭제)
find $LOG_DIR -name "eminwon_batch_*.log" -mtime +30 -delete
find $LOG_DIR -name "eminwon_batch_results_*.json" -mtime +30 -delete

exit $EXIT_CODE