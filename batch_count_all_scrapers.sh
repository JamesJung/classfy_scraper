#!/bin/bash

################################################################################
# 모든 스크래퍼 URL 추출 배치 스크립트
#
# 설명: 모든 스크래퍼를 --count 옵션으로 실행하여 URL만 추출
# 사용법: ./batch_count_all_scrapers.sh [날짜]
#         날짜 형식: YYYYMMDD (예: 20241124)
#         날짜 미지정시 현재 연도의 모든 공고 추출
################################################################################

# 현재 스크립트 위치
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRAPER_DIR="${SCRIPT_DIR}/node/scraper"
LOG_DIR="${SCRIPT_DIR}/logs/batch_count"

# 로그 디렉토리 생성
mkdir -p "${LOG_DIR}"

# 현재 날짜/시간
BATCH_DATE=$(date +"%Y-%m-%d")
CURRENT_YEAR=$(date +"%Y")
LOG_FILE="${LOG_DIR}/batch_count_${BATCH_DATE}_$(date +"%H%M%S").log"

# 파라미터 확인
TARGET_DATE="$1"

# 제외할 파일 목록
EXCLUDE_FILES=(
    "announcement_scraper.js"
    "config.js"
    "failure_logger.js"
    "count_validator.js"
    "url_manager.js"
    "unified_detail_scraper.js"
    "unified_list_collector.js"
)

# 배열에 포함되어 있는지 체크하는 함수
function is_excluded() {
    local file="$1"
    for excluded in "${EXCLUDE_FILES[@]}"; do
        if [[ "$file" == "$excluded" ]]; then
            return 0
        fi
    done
    return 1
}

# 로그 함수
function log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

# 시작 로그
log "================================================================================"
log "  모든 스크래퍼 URL 추출 배치 작업 시작"
log "================================================================================"
log "배치 날짜: ${BATCH_DATE}"

if [[ -n "$TARGET_DATE" ]]; then
    log "대상 날짜: ${TARGET_DATE}"
    DATE_OPTION="--date ${TARGET_DATE}"
else
    log "대상 연도: ${CURRENT_YEAR}"
    DATE_OPTION="--year ${CURRENT_YEAR}"
fi

log "로그 파일: ${LOG_FILE}"
log ""

# 통계 변수
TOTAL_COUNT=0
SUCCESS_COUNT=0
FAILED_COUNT=0
SKIPPED_COUNT=0

# 실패한 스크래퍼 목록
FAILED_SCRAPERS=()

# 모든 스크래퍼 파일 처리
cd "${SCRAPER_DIR}"

for scraper_file in *_scraper.js; do
    # 제외 파일 체크
    if is_excluded "$scraper_file"; then
        log "⊘ ${scraper_file} - 제외됨"
        ((SKIPPED_COUNT++))
        continue
    fi

    # 사이트 코드 추출 (파일명에서 _scraper.js 제거)
    SITE_CODE="${scraper_file%_scraper.js}"

    TOTAL_COUNT=$((TOTAL_COUNT + 1))

    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "처리 중 [$TOTAL_COUNT]: ${SITE_CODE}"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 스크래퍼 실행
    START_TIME=$(date +%s)

    if node "${scraper_file}" --site "${SITE_CODE}" ${DATE_OPTION} --count --batch-date "${BATCH_DATE}" >> "${LOG_FILE}" 2>&1; then
        END_TIME=$(date +%s)
        ELAPSED=$((END_TIME - START_TIME))
        log "✓ ${SITE_CODE} 완료 (${ELAPSED}초)"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        END_TIME=$(date +%s)
        ELAPSED=$((END_TIME - START_TIME))
        log "✗ ${SITE_CODE} 실패 (${ELAPSED}초)"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_SCRAPERS+=("${SITE_CODE}")
    fi

    log ""

    # 다음 스크래퍼 실행 전 대기 (서버 부하 방지)
    sleep 2
done

# 최종 통계
log "================================================================================"
log "  배치 작업 완료"
log "================================================================================"
log "전체 스크래퍼: ${TOTAL_COUNT}개"
log "성공: ${SUCCESS_COUNT}개"
log "실패: ${FAILED_COUNT}개"
log "제외: ${SKIPPED_COUNT}개"
log ""

if [[ ${FAILED_COUNT} -gt 0 ]]; then
    log "실패한 스크래퍼 목록:"
    for failed in "${FAILED_SCRAPERS[@]}"; do
        log "  - ${failed}"
    done
    log ""
fi

# DB 통계 조회
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "DB 통계 (batch_date: ${BATCH_DATE})"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# .env 파일에서 DB 정보 읽기
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    source <(grep -E '^(DB_HOST|DB_PORT|DB_USER|DB_PASSWORD|DB_NAME)=' "${SCRIPT_DIR}/.env" | sed 's/^/export /')

    MYSQL_CMD="mysql -h ${DB_HOST} -P ${DB_PORT} -u ${DB_USER} -p${DB_PASSWORD} ${DB_NAME}"

    # 사이트별 통계
    $MYSQL_CMD -e "
        SELECT
            site_code AS '사이트',
            COUNT(*) AS '전체',
            SUM(scraped) AS '완료',
            SUM(1-scraped) AS '대기'
        FROM scraper_detail_urls
        WHERE batch_date = '${BATCH_DATE}'
        GROUP BY site_code
        ORDER BY site_code;
    " 2>/dev/null | tee -a "${LOG_FILE}"

    log ""

    # 전체 통계
    $MYSQL_CMD -e "
        SELECT
            COUNT(*) AS '총 URL 수',
            SUM(scraped) AS '완료',
            SUM(1-scraped) AS '대기',
            ROUND(SUM(scraped) * 100.0 / COUNT(*), 2) AS '완료율(%)'
        FROM scraper_detail_urls
        WHERE batch_date = '${BATCH_DATE}';
    " 2>/dev/null | tee -a "${LOG_FILE}"
else
    log "⚠️ .env 파일을 찾을 수 없어 DB 통계를 조회할 수 없습니다."
fi

log ""
log "================================================================================"
log "로그 파일: ${LOG_FILE}"
log "================================================================================"

# 종료 코드
if [[ ${FAILED_COUNT} -gt 0 ]]; then
    exit 1
else
    exit 0
fi
