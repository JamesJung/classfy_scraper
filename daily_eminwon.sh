#!/bin/bash

# =============================================================================
# Eminwon 일일 수집 스크립트 (CRON 최적화 버전)
# =============================================================================

# ============= 1. CRON 환경 대응: PATH 및 환경 변수 명시적 설정 =============
export PATH="/home/zium/.nvm/versions/node/v18.16.0/bin:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/zium"
export USER="zium"
export SHELL="/bin/bash"

# ============= 2. 기본 디렉토리 설정 (변수 인용 추가) =============
ROOT_DIR="/home/zium/classfy_scraper"
LOG_DIR="/home/zium/classfy_scraper/logs"
DATE=$(date +%Y%m%d)
LOG_FILE="${LOG_DIR}/eminwon_daily_${DATE}.log"

# ============= 3. 로그 디렉토리 생성 (mkdir -p는 이미 존재해도 에러 없음) =============
mkdir -p "${LOG_DIR}"

# ============= 4. 작업 디렉토리 이동 (인용 추가) =============
cd "${ROOT_DIR}" || {
    echo "ERROR: Cannot change directory to ${ROOT_DIR}" >> "${LOG_FILE}" 2>&1
    exit 1
}

# ============= 5. .env 파일 로드 (개선된 버전) =============
if [ -f "${ROOT_DIR}/.env" ]; then
    # set -a: 이후 변수를 자동으로 export
    # source: .env 파일을 현재 셸에서 실행
    # set +a: 자동 export 해제
    set -a
    source "${ROOT_DIR}/.env"
    set +a
    echo "DEBUG: .env file loaded successfully" >> "${LOG_FILE}"
else
    echo "WARNING: .env file not found at ${ROOT_DIR}/.env" >> "${LOG_FILE}"
fi

# ============= 6. 수집 시작 로그 =============
echo "===================================================================================" >> "${LOG_FILE}"
echo "=== Eminwon 일일 수집 시작: $(date '+%Y-%m-%d %H:%M:%S') ===" >> "${LOG_FILE}"
echo "===================================================================================" >> "${LOG_FILE}"

# 시작 시간 기록
START_TIME=$(date +%s)

# ============= 7. 환경 정보 로깅 (디버깅용) =============
echo "Working Directory: $(pwd)" >> "${LOG_FILE}"
echo "User: $(whoami)" >> "${LOG_FILE}"
echo "PATH: ${PATH}" >> "${LOG_FILE}"
echo "Node version: $(node --version 2>&1)" >> "${LOG_FILE}"
echo "Python version: $(python3 --version 2>&1)" >> "${LOG_FILE}"
echo "" >> "${LOG_FILE}"

# ============= 8. 증분 수집 실행 =============
echo "[1/2] 증분 수집 시작..." >> "${LOG_FILE}"

# Python 스크립트 실행 (절대 경로 사용)
/usr/bin/python3 "${ROOT_DIR}/eminwon_incremental_orchestrator.py" >> "${LOG_FILE}" 2>&1
EXIT_CODE=$?

if [ ${EXIT_CODE} -eq 0 ]; then
    echo "[1/2] ✅ 증분 수집 완료" >> "${LOG_FILE}"
else
    echo "[1/2] ❌ 증분 수집 실패 (Exit Code: ${EXIT_CODE})" >> "${LOG_FILE}"
fi

echo "" >> "${LOG_FILE}"

# ============= 9. 종료 시간 및 총 실행 시간 계산 =============
END_TIME=$(date +%s)
ELAPSED_TIME=$((END_TIME - START_TIME))
ELAPSED_MIN=$((ELAPSED_TIME / 60))
ELAPSED_SEC=$((ELAPSED_TIME % 60))

# ============= 10. 완료 로그 =============
echo "===================================================================================" >> "${LOG_FILE}"
echo "=== 완료: $(date '+%Y-%m-%d %H:%M:%S') ===" >> "${LOG_FILE}"
echo "총 실행 시간: ${ELAPSED_MIN}분 ${ELAPSED_SEC}초" >> "${LOG_FILE}"
echo "Exit Code: ${EXIT_CODE}" >> "${LOG_FILE}"
echo "===================================================================================" >> "${LOG_FILE}"

# ============= 11. Exit Code 반환 =============
exit ${EXIT_CODE}
