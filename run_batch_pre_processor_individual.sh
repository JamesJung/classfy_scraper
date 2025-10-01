#!/bin/bash

# 개별 소스별 배치 프리프로세서 실행 스크립트
# Eminwon 또는 Homepage 데이터를 선택적으로 처리

SCRIPT_DIR="/Users/jin/classfy_scraper"
LOG_DIR="$SCRIPT_DIR/logs"
PYTHON_PATH="/usr/bin/python3"

# 파라미터 확인
if [ $# -eq 0 ]; then
    echo "사용법: $0 [eminwon|homepage|both]"
    echo ""
    echo "옵션:"
    echo "  eminwon  - Eminwon 데이터만 처리"
    echo "  homepage - Homepage 데이터만 처리"
    echo "  both     - 모든 데이터 처리"
    exit 1
fi

SOURCE=$1

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 현재 시간
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# 스크립트 실행 디렉토리로 이동
cd "$SCRIPT_DIR"

case $SOURCE in
    eminwon)
        LOG_FILE="$LOG_DIR/eminwon_pre_processor_$TIMESTAMP.log"
        echo "Eminwon 데이터 처리 시작: $(date)" | tee "$LOG_FILE"
        $PYTHON_PATH batch_scraper_to_pre_processor.py --source eminwon >> "$LOG_FILE" 2>&1
        RESULT=$?
        if [ $RESULT -eq 0 ]; then
            echo "Eminwon 처리 성공: $(date)" | tee -a "$LOG_FILE"
        else
            echo "Eminwon 처리 실패 (오류 코드: $RESULT): $(date)" | tee -a "$LOG_FILE"
        fi
        ;;
        
    homepage)
        LOG_FILE="$LOG_DIR/homepage_pre_processor_$TIMESTAMP.log"
        echo "Homepage 데이터 처리 시작: $(date)" | tee "$LOG_FILE"
        $PYTHON_PATH batch_scraper_to_pre_processor.py --source homepage >> "$LOG_FILE" 2>&1
        RESULT=$?
        if [ $RESULT -eq 0 ]; then
            echo "Homepage 처리 성공: $(date)" | tee -a "$LOG_FILE"
        else
            echo "Homepage 처리 실패 (오류 코드: $RESULT): $(date)" | tee -a "$LOG_FILE"
        fi
        ;;
        
    both)
        LOG_FILE="$LOG_DIR/both_pre_processor_$TIMESTAMP.log"
        echo "전체 데이터 처리 시작: $(date)" | tee "$LOG_FILE"
        
        # Eminwon 처리
        echo "" | tee -a "$LOG_FILE"
        echo "1. Eminwon 데이터 처리..." | tee -a "$LOG_FILE"
        $PYTHON_PATH batch_scraper_to_pre_processor.py --source eminwon >> "$LOG_FILE" 2>&1
        EMINWON_RESULT=$?
        
        # Homepage 처리
        echo "" | tee -a "$LOG_FILE"
        echo "2. Homepage 데이터 처리..." | tee -a "$LOG_FILE"
        $PYTHON_PATH batch_scraper_to_pre_processor.py --source homepage >> "$LOG_FILE" 2>&1
        HOMEPAGE_RESULT=$?
        
        # 결과 확인
        if [ $EMINWON_RESULT -eq 0 ] && [ $HOMEPAGE_RESULT -eq 0 ]; then
            echo "모든 처리 성공: $(date)" | tee -a "$LOG_FILE"
            RESULT=0
        else
            echo "일부 처리 실패 (Eminwon: $EMINWON_RESULT, Homepage: $HOMEPAGE_RESULT): $(date)" | tee -a "$LOG_FILE"
            RESULT=1
        fi
        ;;
        
    *)
        echo "잘못된 옵션: $SOURCE"
        echo "사용 가능한 옵션: eminwon, homepage, both"
        exit 1
        ;;
esac

# 30일 이상 된 로그 파일 삭제
find "$LOG_DIR" -name "*_pre_processor_*.log" -mtime +30 -delete

exit $RESULT