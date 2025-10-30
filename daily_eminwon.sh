#!/bin/bash

# =============================================================================
# Eminwon 일일 수집 스크립트 (CRON 최적화 버전 v2.0)
# 단계별 로깅 및 문제 진단 기능 추가
# =============================================================================

# ============= 0. 즉시 로깅 시작 (임시 로그파일) =============
TEMP_LOG="/tmp/eminwon_startup_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "${TEMP_LOG}") 2>&1

echo "=========================================="
echo "스크립트 시작: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# ============= 1. CRON 환경 대응: PATH 및 환경 변수 명시적 설정 =============
echo "[STEP 1/10] 환경 변수 설정..."

export PATH="/usr/local/bin:/usr/bin:/bin"
export HOME="/home/zium"
export USER="zium"
export SHELL="/bin/bash"

echo "  ✓ PATH: ${PATH}"
echo "  ✓ HOME: ${HOME}"
echo "  ✓ USER: ${USER}"

# ============= 2. 기본 디렉토리 설정 =============
echo "[STEP 2/10] 디렉토리 설정..."

# 현재 사용자와 현재 작업 디렉토리 확인
CURRENT_USER=$(whoami)
CURRENT_PWD=$(pwd)

echo "  디버깅: CURRENT_USER=${CURRENT_USER}"
echo "  디버깅: CURRENT_PWD=${CURRENT_PWD}"

# 배포 서버 환경인지 확인 (zium 계정)
if [ "$CURRENT_USER" = "zium" ] && [ -d "/home/zium/classfy_scraper" ]; then
    # 배포 서버 환경 (최우선)
    ROOT_DIR="/home/zium/classfy_scraper"
    echo "  ✓ 환경: 배포 서버 (zium)"
# 현재 디렉토리가 classfy_scraper인지 확인
elif [[ "$CURRENT_PWD" == *"classfy_scraper"* ]]; then
    # 현재 디렉토리 사용 (이미 올바른 위치)
    ROOT_DIR="$CURRENT_PWD"
    echo "  ✓ 환경: 현재 디렉토리 사용"
# WSL 환경 확인
elif [ -d "/mnt/d/workspace/sources/classfy_scraper" ]; then
    ROOT_DIR="/mnt/d/workspace/sources/classfy_scraper"
    echo "  ✓ 환경: WSL (로컬)"
# Mac 환경 확인
elif [ -d "/Users/jin/classfy_scraper" ]; then
    ROOT_DIR="/Users/jin/classfy_scraper"
    echo "  ✓ 환경: Mac (로컬)"
else
    # 현재 디렉토리를 기본값으로
    ROOT_DIR="$CURRENT_PWD"
    echo "  ⚠ 환경: 알 수 없음, 현재 디렉토리 사용"
fi

# 변수에서 캐리지 리턴 및 후행 슬래시 제거
ROOT_DIR=$(echo "$ROOT_DIR" | tr -d '\r' | sed 's:/*$::')

LOG_DIR="${ROOT_DIR}/logs"
DATE=$(date +%Y%m%d)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/eminwon_daily_${TIMESTAMP}.log"

echo "  ✓ ROOT_DIR: ${ROOT_DIR}"
echo "  ✓ LOG_DIR: ${LOG_DIR}"
echo "  ✓ LOG_FILE: ${LOG_FILE}"

# ============= 3. 로그 디렉토리 생성 및 검증 =============
echo "[STEP 3/10] 로그 디렉토리 생성..."

if mkdir -p "${LOG_DIR}"; then
    echo "  ✓ 로그 디렉토리 생성/확인 성공: ${LOG_DIR}"

    # 쓰기 권한 테스트
    if touch "${LOG_DIR}/test_write_$$" 2>/dev/null; then
        rm -f "${LOG_DIR}/test_write_$$"
        echo "  ✓ 로그 디렉토리 쓰기 권한 확인"
    else
        echo "  ✗ ERROR: 로그 디렉토리 쓰기 권한 없음: ${LOG_DIR}"
        echo "  디버깅 정보:"
        ls -ld "${LOG_DIR}" 2>&1 || echo "    디렉토리 정보 조회 실패"
        echo "  임시 로그: ${TEMP_LOG}"
        exit 1
    fi
else
    echo "  ✗ ERROR: 로그 디렉토리 생성 실패: ${LOG_DIR}"
    echo "  임시 로그: ${TEMP_LOG}"
    exit 1
fi

# ============= 4. 작업 디렉토리 이동 및 검증 =============
echo "[STEP 4/10] 작업 디렉토리 이동..."

if [ ! -d "${ROOT_DIR}" ]; then
    echo "  ✗ ERROR: 작업 디렉토리가 존재하지 않음: ${ROOT_DIR}"
    echo "  임시 로그: ${TEMP_LOG}"
    exit 1
fi

if cd "${ROOT_DIR}"; then
    echo "  ✓ 작업 디렉토리 이동 성공: $(pwd)"
else
    echo "  ✗ ERROR: 작업 디렉토리 이동 실패: ${ROOT_DIR}"
    echo "  임시 로그: ${TEMP_LOG}"
    exit 1
fi

# ============= 5. 정식 로그 파일로 리다이렉션 =============
echo "[STEP 5/10] 정식 로그 파일로 전환..."

# 임시 로그 내용을 정식 로그로 복사
if cat "${TEMP_LOG}" >> "${LOG_FILE}" 2>/dev/null; then
    echo "  ✓ 로그 파일 생성 성공: ${LOG_FILE}"
    # 이제부터 정식 로그 파일로 출력
    exec >> "${LOG_FILE}" 2>&1
    echo "  ✓ 로그 리다이렉션 완료"
    rm -f "${TEMP_LOG}"
else
    echo "  ⚠ WARNING: 정식 로그 파일 생성 실패, 임시 로그 계속 사용: ${TEMP_LOG}"
    LOG_FILE="${TEMP_LOG}"
fi

# ============= 6. .env 파일 로드 및 검증 =============
echo "[STEP 6/10] .env 파일 로드..."

if [ -f "${ROOT_DIR}/.env" ]; then
    echo "  ✓ .env 파일 발견: ${ROOT_DIR}/.env"

    # 파일 권한 확인
    if [ -r "${ROOT_DIR}/.env" ]; then
        echo "  ✓ .env 파일 읽기 권한 확인"

        # 환경 변수 로드
        set -a
        source "${ROOT_DIR}/.env"
        set +a
        echo "  ✓ .env 파일 로드 성공"

        # 주요 환경 변수 확인 (값은 마스킹)
        echo "  환경 변수 확인:"
        [ -n "${DB_HOST}" ] && echo "    ✓ DB_HOST: ${DB_HOST}" || echo "    ✗ DB_HOST: 미설정"
        [ -n "${DB_NAME}" ] && echo "    ✓ DB_NAME: ${DB_NAME}" || echo "    ✗ DB_NAME: 미설정"
        [ -n "${DB_USER}" ] && echo "    ✓ DB_USER: ${DB_USER}" || echo "    ✗ DB_USER: 미설정"
        [ -n "${DB_PASSWORD}" ] && echo "    ✓ DB_PASSWORD: [설정됨]" || echo "    ✗ DB_PASSWORD: 미설정"
    else
        echo "  ✗ ERROR: .env 파일 읽기 권한 없음"
        ls -l "${ROOT_DIR}/.env"
    fi
else
    echo "  ⚠ WARNING: .env 파일이 존재하지 않음: ${ROOT_DIR}/.env"
    echo "  디렉토리 내용:"
    ls -la "${ROOT_DIR}" | grep -E "^-.*\.env" || echo "    .env 파일 없음"
fi

# ============= 7. 필수 실행 파일 검증 =============
echo "[STEP 7/10] 필수 실행 파일 검증..."

# Node.js 확인
if command -v node >/dev/null 2>&1; then
    NODE_VERSION=$(node --version 2>&1)
    echo "  ✓ Node.js: ${NODE_VERSION}"
else
    echo "  ✗ ERROR: Node.js를 찾을 수 없음"
    echo "    PATH: ${PATH}"
fi

# Python 확인
if command -v python3 >/dev/null 2>&1; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    echo "  ✓ Python3: ${PYTHON_VERSION}"
else
    echo "  ✗ ERROR: Python3을 찾을 수 없음"
fi

# 필수 스크립트 확인
ORCHESTRATOR_SCRIPT="${ROOT_DIR}/eminwon_incremental_orchestrator.py"
echo "  디버깅: ROOT_DIR=${ROOT_DIR}"
echo "  디버깅: 현재 디렉토리=$(pwd)"
echo "  디버깅: ORCHESTRATOR_SCRIPT=${ORCHESTRATOR_SCRIPT}"

if [ -f "${ORCHESTRATOR_SCRIPT}" ]; then
    echo "  ✓ Orchestrator 스크립트: ${ORCHESTRATOR_SCRIPT}"
    if [ -r "${ORCHESTRATOR_SCRIPT}" ]; then
        echo "  ✓ 스크립트 읽기 권한 확인"
    else
        echo "  ✗ ERROR: 스크립트 읽기 권한 없음"
        ls -l "${ORCHESTRATOR_SCRIPT}"
    fi
else
    echo "  ✗ ERROR: Orchestrator 스크립트를 찾을 수 없음: ${ORCHESTRATOR_SCRIPT}"
    echo "  디버깅: 현재 위치의 Python 파일 목록"
    ls -la *.py 2>/dev/null | head -10 || echo "    Python 파일 없음"
    echo ""
    echo "  ⚠ 주의: 이 스크립트는 배포 서버(/home/zium/classfy_scraper)에서만 실행되어야 합니다"
    echo "  현재 위치: $(pwd)"
    echo "  예상 위치: /home/zium/classfy_scraper"
    exit 1
fi

# ============= 8. 시스템 정보 로깅 =============
echo "[STEP 8/10] 시스템 정보 수집..."
echo "==================================================================================="
echo "=== 실행 환경 정보 ==="
echo "==================================================================================="
echo "실행 시간: $(date '+%Y-%m-%d %H:%M:%S')"
echo "작업 디렉토리: $(pwd)"
echo "실행 사용자: $(whoami)"
echo "사용자 UID/GID: $(id)"
echo "PATH: ${PATH}"
echo "HOME: ${HOME}"
echo "Disk Space:"
df -h "${ROOT_DIR}" 2>&1 | head -2
echo "==================================================================================="
echo ""

# 시작 시간 기록
START_TIME=$(date +%s)

# ============= 9. 증분 수집 실행 =============
echo "[STEP 9/10] Eminwon 증분 수집 실행..."
echo "==================================================================================="

# Python 스크립트 실행 (절대 경로 사용)
if python3 "${ORCHESTRATOR_SCRIPT}"; then
    EXIT_CODE=$?
    echo ""
    echo "  ✓ 증분 수집 완료 (Exit Code: ${EXIT_CODE})"
else
    EXIT_CODE=$?
    echo ""
    echo "  ✗ 증분 수집 실패 (Exit Code: ${EXIT_CODE})"
    echo "  스크립트: ${ORCHESTRATOR_SCRIPT}"
    echo "  Python: $(which python3)"
fi

# ============= 10. 완료 및 요약 =============
echo "[STEP 10/10] 작업 완료 및 요약..."
echo "==================================================================================="

# 종료 시간 및 총 실행 시간 계산
END_TIME=$(date +%s)
ELAPSED_TIME=$((END_TIME - START_TIME))
ELAPSED_MIN=$((ELAPSED_TIME / 60))
ELAPSED_SEC=$((ELAPSED_TIME % 60))

echo "=== 작업 완료 ==="
echo "==================================================================================="
echo "종료 시간: $(date '+%Y-%m-%d %H:%M:%S')"
echo "총 실행 시간: ${ELAPSED_MIN}분 ${ELAPSED_SEC}초"
echo "Exit Code: ${EXIT_CODE}"
echo "로그 파일: ${LOG_FILE}"
echo "==================================================================================="

# 로그 파일 크기 및 위치 출력
if [ -f "${LOG_FILE}" ]; then
    LOG_SIZE=$(du -h "${LOG_FILE}" | cut -f1)
    echo "로그 파일 크기: ${LOG_SIZE}"
    echo "로그 파일 경로: ${LOG_FILE}"
fi

exit ${EXIT_CODE}
