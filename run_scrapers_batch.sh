#!/bin/bash

# 스크립트 실행 경로
SCRIPT_DIR="/home/zium/classfy_scraper"
LOG_DIR="$SCRIPT_DIR/logs"
PYTHON_PATH="/usr/bin/python3"  # Python 경로 확인 필요

# ============================================
# NVM 환경 로드 (비대화형 셸 대응)
# ============================================
export NVM_DIR="$HOME/.nvm"

# nvm.sh 로드 (여러 경로 시도)
if [ -s "$NVM_DIR/nvm.sh" ]; then
    source "$NVM_DIR/nvm.sh"
elif [ -s "/home/zium/.nvm/nvm.sh" ]; then
    source "/home/zium/.nvm/nvm.sh"
fi

# Node.js 20 버전 활성화
if command -v nvm &> /dev/null; then
    nvm use 20 &> /dev/null || nvm use default &> /dev/null
fi

# Node.js 버전 확인 및 검증 (Playwright 요구사항: 18 이상)
NODE_VERSION=$(node --version 2>/dev/null)
if [ -z "$NODE_VERSION" ]; then
    echo "❌ 오류: Node.js를 찾을 수 없습니다"
    exit 1
fi

NODE_MAJOR=$(echo $NODE_VERSION | sed -E 's/v([0-9]+)\..*/\1/')
if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "❌ 오류: Node.js 버전이 너무 낮습니다: $NODE_VERSION"
    echo "   Playwright는 Node.js 18 이상이 필요합니다"
    echo "   현재 경로: $(which node)"
    exit 1
fi

echo "✅ Node.js 버전 확인: $NODE_VERSION (사용 가능)"
echo "   Node.js 경로: $(which node)"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 현재 시간
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/scraper_batch_$TIMESTAMP.log"

# 스크립트 실행 디렉토리로 이동
cd "$SCRIPT_DIR"

echo "========================================" >> "$LOG_FILE"
echo "스크래퍼 배치 실행 시작: $(date)" >> "$LOG_FILE"
echo "작업 디렉토리: $SCRIPT_DIR" >> "$LOG_FILE"
echo "Python 경로: $PYTHON_PATH" >> "$LOG_FILE"
echo "Python 버전: $($PYTHON_PATH --version 2>&1)" >> "$LOG_FILE"
echo "Node.js 경로: $(which node)" >> "$LOG_FILE"
echo "Node.js 버전: $(node --version)" >> "$LOG_FILE"
echo "사용자: $(whoami)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# Python 스크립트 실행 (실시간 로그 출력 및 파일 저장)
$PYTHON_PATH run_incremental_scrapers_v2.py 2>&1 | tee -a "$LOG_FILE"

# 실행 결과 확인 (PIPESTATUS 사용하여 정확한 종료 코드 캡처)
EXIT_CODE=${PIPESTATUS[0]}

echo "" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 스크래퍼 실행 성공: $(date)" >> "$LOG_FILE"
else
    echo "❌ 스크래퍼 실행 실패: $(date)" >> "$LOG_FILE"
    echo "오류 코드: $EXIT_CODE" >> "$LOG_FILE"
fi

echo "스크래퍼 배치 종료: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 30일 이상 된 로그 파일 삭제
find "$LOG_DIR" -name "scraper_batch_*.log" -mtime +30 -delete 2>/dev/null

exit $EXIT_CODE