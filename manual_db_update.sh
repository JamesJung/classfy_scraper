#!/bin/bash
# 수동 DB 업데이트 스크립트
# DB 연결이 제한될 때 사용

echo "📅 스크래핑된 파일에서 날짜를 추출하여 수동 업데이트 준비"

SITE_CODE="andong"
SCRAPED_DIR="scraped_incremental_v2/2025-09-29/andong"

# 001_ 폴더에서 content.md 찾기
CONTENT_FILE=$(find "$SCRAPED_DIR" -name "content.md" -path "*/001_*" | head -1)

if [ -z "$CONTENT_FILE" ]; then
    echo "❌ content.md 파일을 찾을 수 없습니다"
    exit 1
fi

echo "📄 파일 발견: $CONTENT_FILE"

# 작성일 추출
DATE=$(grep -E "\*\*작성일\*\*|작성일:" "$CONTENT_FILE" | head -1 | sed -E 's/.*[[:space:]]([0-9]{4}-[0-9]{2}-[0-9]{2}).*/\1/')

if [ -z "$DATE" ]; then
    echo "❌ 날짜를 추출할 수 없습니다"
    exit 1
fi

echo "📅 추출된 날짜: $DATE"
echo ""
echo "DB 연결이 가능해지면 다음 명령을 실행하세요:"
echo ""
echo "UPDATE homepage_site_announcement_date SET latest_announcement_date = '$DATE' WHERE site_code = '$SITE_CODE';"
echo ""
echo "또는 Python 스크립트 실행:"
echo "python3 test_db_update.py $SITE_CODE $DATE"