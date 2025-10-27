#!/bin/bash

# 기본 디렉토리 설정
ROOT_DIR="/home/zium/classfy_scraper"
LOG_DIR="/home/zium/classfy_scraper/logs"
DATE=$(date +%Y%m%d)
LOG_FILE="${LOG_DIR}/eminwon_daily_${DATE}.log"

echo "DEBUG: cd ROOT_DIR" >> "$LOG_FILE" # <--- 디버그 포인트 1

cd $ROOT_DIR || exit 1

# logs 디렉토리가 없으면 생성
mkdir -p $LOG_DIR
echo "DEBUG: Log directory created." >> "$LOG_FILE" # <--- 디버그 포인트 1

# NVM 로드 (Node.js 사용을 위해)
# export NVM_DIR="$HOME/.nvm"
# [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

export PATH="/home/zium/.nvm/versions/node/v18.16.0/bin:$PATH"

# 환경 설정
#    export PATH="/home/zium/.nvm/versions/node/v18.16.0/bin:$PATH:/usr/local/bin:/usr/bin:/bin"
# export NODE_PATH="/home/zium/.nvm/versions/node/v18.16.0/bin/node"
cd $ROOT_DIR


# .env 파일 로드
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "DEBUG: .env file loaded." >> "$LOG_FILE" # <--- 디버그 포인트 2
fi

echo "=== Eminwon 일일 수집 시작: $(date) ===" >> "$LOG_FILE"



# 시작 시간 기록
START_TIME=$(date +%s)
echo "Node version: $(node --version)" >> "$LOG_FILE"
echo "Python version: $(python3 --version)" >> "$LOG_FILE"

echo "DEBUG: Node & Python version" >> "$LOG_FILE" # <--- 디버그 포인트 2

# 1. 증분 수집
echo "[1/2] 증분 수집 시작..." >> "$LOG_FILE"
/usr/bin/python3 eminwon_incremental_orchestrator.py >> "$LOG_FILE" 2>&1

echo "DEBUG: RUN!!!" >> "$LOG_FILE" # <--- 디버그 포인트 2

if [ $? -eq 0 ]; then
    echo "[1/2] ✅ 증분 수집 완료" >> "$LOG_FILE"
else
    echo "[1/2] ❌ 증분 수집 실패" >> "$LOG_FILE"
fi


# 종료 시간 및 총 실행 시간 계산
END_TIME=$(date +%s)
ELAPSED_TIME=$((END_TIME - START_TIME))
ELAPSED_MIN=$((ELAPSED_TIME / 60))
ELAPSED_SEC=$((ELAPSED_TIME % 60))

echo "=== 완료: $(date) ===" >> "$LOG_FILE"
echo "총 실행 시간: ${ELAPSED_MIN}분 ${ELAPSED_SEC}초" >> "$LOG_FILE"