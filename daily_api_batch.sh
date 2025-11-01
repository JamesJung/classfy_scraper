#!/bin/bash

################################################################################
# API 디렉토리 일일 배치 실행 스크립트
# bizInfo, smes24, kStartUp 세 개 사이트 순차 처리
# 성능 및 메모리 최적화 버전
################################################################################

# 색상 설정
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 스크립트 디렉토리 설정 및 작업 디렉토리 이동
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR" || {
    echo -e "${RED}[ERROR]${NC} 작업 디렉토리 이동 실패: $SCRIPT_DIR"
    exit 1
}

LOG_DIR="$SCRIPT_DIR/logs/api_batch"
API_DIR="/home/zium/moabojo/incremental/api"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 실행 타임스탬프
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TODAY=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/api_batch_${TIMESTAMP}.log"

# Python 경로
PYTHON_CMD="python3"

# 처리할 사이트 목록
SITES=("bizInfo" "smes24" "kStartUp")

# 통계 변수
TOTAL_SUCCESS=0
TOTAL_FAILED=0
TOTAL_TIME=0

################################################################################
# 함수 정의
################################################################################

# 로그 함수
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

# 메모리 사용량 체크 함수
check_memory() {
    if command -v free &> /dev/null; then
        MEMORY_INFO=$(free -h | grep Mem | awk '{print "사용중: "$3" / 전체: "$2" (사용률: "int($3/$2*100)"%)"}'  )
        log_info "메모리 상태: $MEMORY_INFO"
    fi
}

# 디렉토리 체크 함수
check_directory() {
    local site_code=$1
    local site_dir="$API_DIR/$site_code"

    if [ ! -d "$site_dir" ]; then
        log_warning "$site_code 디렉토리가 존재하지 않습니다: $site_dir"
        return 1
    fi

    # 디렉토리 내 파일 개수 체크
    local file_count=$(find "$site_dir" -type f 2>/dev/null | wc -l)
    log_info "$site_code 디렉토리 파일 수: $file_count"

    return 0
}

# 프로세스 처리 함수
process_site() {
    local site_code=$1
    local site_start_time=$(date +%s)

    log_info "========================================="
    log_info "$site_code 처리 시작"
    log_info "========================================="

    # 디렉토리 존재 확인
    if ! check_directory "$site_code"; then
        log_error "$site_code 디렉토리 확인 실패 - 건너뜀"
        return 2
    fi

    # 처리 전 메모리 상태 확인
    check_memory

    # Python 스크립트 실행
    log_info "명령: $PYTHON_CMD $SCRIPT_DIR/announcement_pre_processor.py -d $API_DIR --site-code $site_code"
    log_info "작업 디렉토리: $(pwd)"

    $PYTHON_CMD "$SCRIPT_DIR/announcement_pre_processor.py" -d "$API_DIR" --site-code "$site_code" 2>&1 | tee -a "$LOG_FILE"
    local exit_code=${PIPESTATUS[0]}

    # 처리 후 메모리 상태 확인
    check_memory

    # 처리 시간 계산
    local site_end_time=$(date +%s)
    local elapsed=$((site_end_time - site_start_time))
    local minutes=$((elapsed / 60))
    local seconds=$((elapsed % 60))

    # 결과 처리
    if [ $exit_code -eq 0 ]; then
        log_success "$site_code 처리 완료 (소요시간: ${minutes}분 ${seconds}초)"
        TOTAL_SUCCESS=$((TOTAL_SUCCESS + 1))
    else
        log_error "$site_code 처리 실패 (오류코드: $exit_code, 소요시간: ${minutes}분 ${seconds}초)"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
    fi

    TOTAL_TIME=$((TOTAL_TIME + elapsed))

    # 메모리 정리를 위한 대기 (선택적, 필요시 주석 해제)
    # log_info "메모리 정리 대기 (5초)..."
    # sleep 5

    return $exit_code
}

################################################################################
# 메인 실행
################################################################################

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}API 디렉토리 일일 배치${NC}"
echo -e "${BLUE}================================${NC}"
log_info "실행시간: $(date '+%Y-%m-%d %H:%M:%S')"
log_info "로그파일: $LOG_FILE"
log_info ""

# Python 버전 확인
python_version=$($PYTHON_CMD --version 2>/dev/null)
if [ -z "$python_version" ]; then
    log_error "Python3이 설치되지 않았습니다"
    exit 1
fi
log_info "Python 버전: $python_version"

# announcement_pre_processor.py 존재 확인
if [ ! -f "$SCRIPT_DIR/announcement_pre_processor.py" ]; then
    log_error "announcement_pre_processor.py 파일을 찾을 수 없습니다"
    exit 1
fi

# api_dir 디렉토리 확인
if [ ! -d "$API_DIR" ]; then
    log_warning "api_dir 디렉토리가 존재하지 않습니다: $API_DIR"
    log_info "디렉토리 생성 중..."
    mkdir -p "$API_DIR"/{bizInfo,smes24,kStartUp}
    log_success "api_dir 디렉토리 생성 완료"
fi

# 초기 시스템 리소스 체크
log_info ""
log_info "초기 시스템 리소스 상태:"
check_memory

# 배치 시작 시간
BATCH_START_TIME=$(date +%s)

log_info ""
log_info "========================================="
log_info "배치 처리 시작 (총 ${#SITES[@]}개 사이트)"
log_info "========================================="
log_info ""

# 각 사이트 순차 처리
for site in "${SITES[@]}"; do
    process_site "$site"

    # 각 처리 간 구분선
    echo "" | tee -a "$LOG_FILE"
done

# 배치 종료 시간 계산
BATCH_END_TIME=$(date +%s)
BATCH_ELAPSED=$((BATCH_END_TIME - BATCH_START_TIME))
BATCH_MINUTES=$((BATCH_ELAPSED / 60))
BATCH_SECONDS=$((BATCH_ELAPSED % 60))

################################################################################
# 최종 결과 리포트
################################################################################

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}배치 처리 완료${NC}"
echo -e "${BLUE}================================${NC}"

log_info ""
log_info "========================================="
log_info "최종 처리 결과"
log_info "========================================="
log_info "총 처리 사이트: ${#SITES[@]}개"
log_success "성공: $TOTAL_SUCCESS개"
if [ $TOTAL_FAILED -gt 0 ]; then
    log_error "실패: $TOTAL_FAILED개"
else
    log_info "실패: $TOTAL_FAILED개"
fi
log_info "총 실행시간: ${BATCH_MINUTES}분 ${BATCH_SECONDS}초"
log_info ""

# 최종 메모리 상태
log_info "최종 시스템 리소스 상태:"
check_memory

# 디스크 사용량 확인
if [ -d "$API_DIR" ]; then
    log_info ""
    log_info "디스크 사용량:"
    du -sh "$API_DIR" 2>/dev/null | awk '{print "api_dir: " $1}' | tee -a "$LOG_FILE"
fi

# 로그 파일 정리 (30일 이상 된 로그 삭제)
log_info ""
log_info "로그 정리..."
find "$LOG_DIR" -name "api_batch_*.log" -mtime +30 -delete 2>/dev/null
OLD_LOGS=$(find "$LOG_DIR" -name "api_batch_*.log" -mtime +7 | wc -l)
if [ $OLD_LOGS -gt 0 ]; then
    log_info "7일 이상 된 로그 ${OLD_LOGS}개 발견 (30일 후 자동 삭제)"
fi

# 최종 상태 메시지
log_info ""
if [ $TOTAL_FAILED -eq 0 ]; then
    log_success "일일 배치 완료: $(date '+%Y-%m-%d %H:%M:%S')"
    EXIT_CODE=0
else
    log_warning "일일 배치 완료 (일부 실패): $(date '+%Y-%m-%d %H:%M:%S')"
    log_warning "로그 파일을 확인하세요: $LOG_FILE"
    EXIT_CODE=1
fi

# 슬랙 알림 (환경변수가 설정된 경우)
if [ ! -z "$SLACK_WEBHOOK_URL" ]; then
    STATUS_TEXT=$([[ $EXIT_CODE -eq 0 ]] && echo "성공" || echo "일부 실패")
    curl -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"API 디렉토리 배치 완료 \\n처리시간: ${BATCH_MINUTES}분 ${BATCH_SECONDS}초\\n성공: $TOTAL_SUCCESS / 실패: $TOTAL_FAILED\\n상태: $STATUS_TEXT\"}" \
        "$SLACK_WEBHOOK_URL" 2>/dev/null
fi

exit $EXIT_CODE
