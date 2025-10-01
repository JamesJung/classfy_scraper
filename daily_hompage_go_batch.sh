#!/bin/bash

################################################################################
# 통합 스크래퍼 일일 배치 실행 스크립트
# 314개 개별 사이트의 신규 공고 수집 및 처리
################################################################################

# 색상 설정
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 스크립트 위치 확인
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs/homepae_go_batch"
DATA_DIR="$PROJECT_ROOT/scraped_data"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 실행 날짜
TODAY=$(date +%Y%m%d)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/batch_${TIMESTAMP}.log"

# 실행 환경 확인
echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}통합 스크래퍼 일일 배치${NC}"
echo -e "${BLUE}================================${NC}"
echo "실행시간: $(date '+%Y-%m-%d %H:%M:%S')"
echo "로그파일: $LOG_FILE"
echo ""

# Node.js 버전 확인
echo -e "${YELLOW}환경 확인...${NC}"
node_version=$(node --version 2>/dev/null)
if [ -z "$node_version" ]; then
    echo -e "${RED}오류: Node.js가 설치되지 않았습니다${NC}"
    exit 1
fi
echo "Node.js 버전: $node_version"

# Python 버전 확인
python_version=$(python3 --version 2>/dev/null)
if [ -z "$python_version" ]; then
    echo -e "${RED}오류: Python3이 설치되지 않았습니다${NC}"
    exit 1
fi
echo "Python 버전: $python_version"

# npm 패키지 확인
echo -e "\n${YELLOW}의존성 확인...${NC}"
cd "$SCRIPT_DIR"
if [ ! -d "node_modules" ]; then
    echo "npm 패키지 설치 중..."
    npm install >> "$LOG_FILE" 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${RED}npm 설치 실패${NC}"
        exit 1
    fi
fi

# .env 파일 확인
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo -e "${RED}오류: .env 파일이 없습니다${NC}"
    echo "다음 형식으로 .env 파일을 생성하세요:"
    echo "DB_HOST=localhost"
    echo "DB_PORT=3306"
    echo "DB_USER=scraper"
    echo "DB_PASSWORD=your_password"
    echo "DB_NAME=opendata"
    exit 1
fi

# DB 테이블 확인 및 생성
echo -e "\n${YELLOW}데이터베이스 확인...${NC}"
mysql_check=$(mysql -h localhost -u scraper -p$DB_PASSWORD opendata -e "SHOW TABLES LIKE 'mkdigistry'" 2>/dev/null | grep homepage_gosi_url_registry)
if [ -z "$mysql_check" ]; then
    echo "DB 테이블 생성 중..."
    mysql -h localhost -u scraper -p$DB_PASSWORD opendata < "$PROJECT_ROOT/create_homepage_gosi_tables.sql" >> "$LOG_FILE" 2>&1
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}DB 테이블 생성 완료${NC}"
    else
        echo -e "${RED}DB 테이블 생성 실패${NC}"
        exit 1
    fi
fi

# 특정 사이트만 처리할 경우 (옵션)
SITES_OPTION=""
if [ ! -z "$1" ]; then
    SITES_OPTION="--sites $@"
    echo -e "\n${YELLOW}선택 사이트 처리: $@${NC}"
fi

# 메인 배치 실행
echo -e "\n${BLUE}================================${NC}"
echo -e "${BLUE}배치 처리 시작${NC}"
echo -e "${BLUE}================================${NC}"

START_TIME=$(date +%s)

# Python 오케스트레이터 실행
cd "$SCRIPT_DIR"
python3 homepage_gosi_batch_orchestrator.py $SITES_OPTION 2>&1 | tee -a "$LOG_FILE"
BATCH_STATUS=$?

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

# 실행 시간 계산
MINUTES=$((ELAPSED / 60))
SECONDS=$((ELAPSED % 60))

echo -e "\n${BLUE}================================${NC}"
echo -e "${BLUE}배치 처리 완료${NC}"
echo -e "${BLUE}================================${NC}"
echo "총 실행시간: ${MINUTES}분 ${SECONDS}초"

# 처리 결과 통계
echo -e "\n${YELLOW}처리 통계:${NC}"

# DB에서 오늘 처리한 통계 조회
mysql -h localhost -u scraper -p$DB_PASSWORD opendata -e "
SELECT 
    COUNT(DISTINCT site_code) as '처리 사이트',
    COUNT(*) as '전체 항목',
    SUM(status = 'completed') as '완료',
    SUM(status = 'failed') as '실패',
    SUM(status = 'pending') as '대기'
FROM homepage_gosi_url_registry 
WHERE DATE(first_seen_date) = CURDATE()
" 2>/dev/null

# 사이트별 통계
echo -e "\n${YELLOW}사이트별 신규 항목:${NC}"
mysql -h localhost -u scraper -p$DB_PASSWORD opendata -e "
SELECT 
    site_code as '사이트',
    COUNT(*) as '신규',
    SUM(status = 'completed') as '완료',
    SUM(status = 'failed') as '실패'
FROM homepage_gosi_url_registry 
WHERE DATE(first_seen_date) = CURDATE()
GROUP BY site_code
ORDER BY COUNT(*) DESC
LIMIT 10
" 2>/dev/null

# 오류 확인
if [ $BATCH_STATUS -ne 0 ]; then
    echo -e "\n${RED}배치 처리 중 오류가 발생했습니다${NC}"
    echo "로그 파일을 확인하세요: $LOG_FILE"
    
    # 최근 오류 표시
    echo -e "\n${YELLOW}최근 오류:${NC}"
    grep -E "ERROR|CRITICAL" "$LOG_FILE" | tail -5
else
    echo -e "\n${GREEN}배치 처리가 성공적으로 완료되었습니다${NC}"
fi

# 디스크 사용량 확인
echo -e "\n${YELLOW}디스크 사용량:${NC}"
du -sh "$DATA_DIR" 2>/dev/null | awk '{print "scraped_data: " $1}'

# 로그 파일 압축 (7일 이상 된 로그)
echo -e "\n${YELLOW}로그 정리...${NC}"
find "$LOG_DIR" -name "batch_*.log" -mtime +7 -exec gzip {} \; 2>/dev/null
find "$LOG_DIR" -name "*.log.gz" -mtime +30 -delete 2>/dev/null

echo -e "\n${GREEN}일일 배치 완료: $(date '+%Y-%m-%d %H:%M:%S')${NC}"

# 슬랙 알림 (설정된 경우)
if [ ! -z "$SLACK_WEBHOOK_URL" ]; then
    curl -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"통합 스크래퍼 배치 완료\\n처리시간: ${MINUTES}분 ${SECONDS}초\\n상태: $([[ $BATCH_STATUS -eq 0 ]] && echo '성공' || echo '실패')\"}" \
        "$SLACK_WEBHOOK_URL" 2>/dev/null
fi

exit $BATCH_STATUS