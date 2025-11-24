#!/bin/bash

################################################################################
# 크론탭 빠른 설치 스크립트
#
# 사용법: ./install_crontab.sh
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON_TEMP_FILE="/tmp/scraper_crontab_temp.txt"

echo "================================================================================"
echo "  스크래퍼 배치 작업 크론탭 설치"
echo "================================================================================"
echo ""

# 현재 크론탭 백업
if crontab -l > /dev/null 2>&1; then
    echo "✓ 기존 크론탭을 백업합니다..."
    crontab -l > "${SCRIPT_DIR}/crontab_backup_$(date +%Y%m%d_%H%M%S).txt"
    echo "  백업 위치: ${SCRIPT_DIR}/crontab_backup_$(date +%Y%m%d_%H%M%S).txt"
    echo ""
else
    echo "✓ 기존 크론탭이 없습니다."
    echo ""
fi

# 설치할 크론 설정 선택
echo "설치할 크론탭 설정을 선택하세요:"
echo ""
echo "1) 매일 오전 1시 - 당일 공고 URL 추출 (추천)"
echo "2) 매일 오전 9시, 오후 6시 - 당일 공고 URL 추출 (하루 2회)"
echo "3) 6시간마다 - 당일 공고 URL 추출 (실시간 모니터링)"
echo "4) 매주 월요일 오전 3시 - 현재 연도 전체 공고 URL 추출"
echo "5) 직접 크론탭 편집기 열기"
echo "6) 취소"
echo ""
read -p "선택 (1-6): " choice

case $choice in
    1)
        echo "매일 오전 1시 크론탭을 설치합니다..."
        CRON_LINE="0 1 * * * cd ${SCRIPT_DIR} && ./batch_count_all_scrapers.sh \$(date +\\%Y\\%m\\%d) >> logs/cron_daily.log 2>&1"
        ;;
    2)
        echo "매일 오전 9시, 오후 6시 크론탭을 설치합니다..."
        CRON_LINE="0 9,18 * * * cd ${SCRIPT_DIR} && ./batch_count_all_scrapers.sh \$(date +\\%Y\\%m\\%d) >> logs/cron_twice_daily.log 2>&1"
        ;;
    3)
        echo "6시간마다 크론탭을 설치합니다..."
        CRON_LINE="0 */6 * * * cd ${SCRIPT_DIR} && ./batch_count_all_scrapers.sh \$(date +\\%Y\\%m\\%d) >> logs/cron_6hours.log 2>&1"
        ;;
    4)
        echo "매주 월요일 오전 3시 크론탭을 설치합니다..."
        CRON_LINE="0 3 * * 1 cd ${SCRIPT_DIR} && ./batch_count_all_scrapers.sh >> logs/cron_weekly.log 2>&1"
        ;;
    5)
        echo "크론탭 편집기를 엽니다..."
        echo ""
        echo "다음 예시를 참고하세요:"
        echo "  ${SCRIPT_DIR}/crontab_examples.txt"
        echo ""
        crontab -e
        exit 0
        ;;
    6)
        echo "취소되었습니다."
        exit 0
        ;;
    *)
        echo "잘못된 선택입니다."
        exit 1
        ;;
esac

# 기존 크론탭 가져오기
if crontab -l > /dev/null 2>&1; then
    crontab -l > "${CRON_TEMP_FILE}"
else
    touch "${CRON_TEMP_FILE}"
fi

# 중복 체크 및 추가
if grep -qF "${SCRIPT_DIR}/batch_count_all_scrapers.sh" "${CRON_TEMP_FILE}"; then
    echo ""
    echo "⚠️  이미 유사한 크론탭이 설치되어 있습니다:"
    grep "${SCRIPT_DIR}/batch_count_all_scrapers.sh" "${CRON_TEMP_FILE}"
    echo ""
    read -p "덮어쓰시겠습니까? (y/N): " overwrite

    if [[ "$overwrite" =~ ^[Yy]$ ]]; then
        # 기존 라인 제거
        sed -i.bak "/${SCRIPT_DIR//\//\\/}\/batch_count_all_scrapers.sh/d" "${CRON_TEMP_FILE}"
        echo "${CRON_LINE}" >> "${CRON_TEMP_FILE}"
        echo "✓ 크론탭을 덮어썼습니다."
    else
        echo "취소되었습니다."
        rm "${CRON_TEMP_FILE}"
        exit 0
    fi
else
    # 새로운 라인 추가
    echo "${CRON_LINE}" >> "${CRON_TEMP_FILE}"
    echo "✓ 크론탭을 추가했습니다."
fi

# 크론탭 설치
crontab "${CRON_TEMP_FILE}"
rm "${CRON_TEMP_FILE}"

echo ""
echo "================================================================================"
echo "  크론탭 설치 완료"
echo "================================================================================"
echo ""
echo "설치된 크론탭:"
crontab -l | grep "${SCRIPT_DIR}/batch_count_all_scrapers.sh"
echo ""
echo "전체 크론탭 확인: crontab -l"
echo "크론탭 편집: crontab -e"
echo "크론탭 삭제: crontab -r"
echo ""
echo "수동 실행 테스트:"
echo "  cd ${SCRIPT_DIR}"
echo "  ./batch_count_all_scrapers.sh"
echo ""
echo "================================================================================"
