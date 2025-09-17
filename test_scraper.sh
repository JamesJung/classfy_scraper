#!/bin/bash

# Node.js 스크래핑 시스템 테스트 스크립트
# 다양한 사이트와 설정으로 스크래핑 테스트

echo "=== Node.js 스크래핑 시스템 테스트 ===="
echo ""

# 의존성 설치 확인
echo "1. 의존성 설치 확인 중..."
if [ ! -d "node_modules" ]; then
    echo "의존성을 설치합니다..."
    npm install
else
    echo "의존성이 이미 설치되어 있습니다."
fi
echo ""

# 테스트 1: 기본 도움말 확인
echo "2. 도움말 테스트..."
node scraper.js --help
echo ""

# 테스트 2: 파라미터 검증 테스트
echo "3. 파라미터 검증 테스트..."
echo "필수 파라미터 누락 시 오류 확인:"
node scraper.js --year 2025 2>/dev/null || echo "✅ 필수 파라미터 검증 작동"
echo ""

# 테스트 3: 일반적인 상공회의소 사이트 (실제 사용 예제)
echo "4. 실제 사이트 테스트 예제들:"
echo ""

# 안산상공회의소 테스트 (주석 처리 - 실제 사용시 주석 해제)
echo "4-1. 안산상공회의소 테스트 (DEMO):"
echo "명령어: node scraper.js --site acci --url 'https://www.acci.or.kr/board/list' --year 2025"
echo "실제 실행을 원하시면 아래 주석을 해제하세요:"
echo "# node scraper.js --site acci --url 'https://www.acci.or.kr/board/list' --year 2025"
echo ""

# CBT 테스트 (주석 처리)
echo "4-2. 중소기업기술혁신협회 테스트 (DEMO):"
echo "명령어: node scraper.js --site cbt --url 'https://www.cbt.or.kr/board/notice' --year 2025"
echo "# node scraper.js --site cbt --url 'https://www.cbt.or.kr/board/notice' --year 2025"
echo ""

# 커스터마이징된 선택자 테스트 (주석 처리)
echo "4-3. 커스터마이징된 선택자 테스트 (DEMO):"
echo "명령어: node scraper.js --site custom --url 'https://example.com/board' --year 2025 --list-selector '.board-list tr' --title-selector '.title a' --date-selector '.date'"
echo "# node scraper.js --site custom --url 'https://example.com/board' --year 2025 --list-selector '.board-list tr' --title-selector '.title a' --date-selector '.date'"
echo ""

# 테스트 4: 예제 스크립트 실행
echo "5. 예제 스크립트 테스트:"
echo "node example_usage.js 실행 중..."
node example_usage.js
echo ""

# 테스트 5: 출력 디렉토리 구조 확인
echo "6. 출력 디렉토리 구조 확인:"
echo "스크래핑 완료 후 다음과 같은 구조가 생성됩니다:"
echo ""
echo "scraped_data/"
echo "├── 001_게시물제목1/"
echo "│   ├── content.md"
echo "│   └── attachments/"
echo "│       ├── 첨부파일1.pdf"
echo "│       └── 첨부파일2.hwp"
echo "├── 002_게시물제목2/"
echo "│   └── content.md"
echo "└── 003_게시물제목3/"
echo "    ├── content.md"
echo "    └── attachments/"
echo "        └── 첨부파일.xlsx"
echo ""

# 테스트 6: 유용한 팁 제공
echo "7. 사용 팁:"
echo ""
echo "✅ 디버깅 모드 실행:"
echo "   - scraper.js에서 headless: false로 설정하면 브라우저가 보입니다"
echo ""
echo "✅ 선택자 찾기:"
echo "   - 브라우저 개발자 도구에서 F12 → Elements → 우클릭 → Copy selector"
echo ""
echo "✅ 네트워크 모니터링:"
echo "   - F12 → Network 탭에서 AJAX 요청 확인 가능"
echo ""
echo "✅ 메모리 사용량 확인:"
echo "   - htop 또는 Activity Monitor로 메모리 사용량 모니터링"
echo ""

# 테스트 7: 일반적인 문제해결
echo "8. 문제해결 가이드:"
echo ""
echo "❌ 'Cannot find module' 오류:"
echo "   → npm install 실행"
echo ""
echo "❌ '선택자를 찾을 수 없음' 오류:"
echo "   → 브라우저에서 해당 사이트 구조 확인 후 선택자 수정"
echo ""
echo "❌ '페이지 로딩 실패' 오류:"
echo "   → 사이트 접근 가능 여부 및 robots.txt 확인"
echo ""
echo "❌ '첨부파일 다운로드 실패' 오류:"
echo "   → 로그인이 필요한 사이트인지 확인"
echo ""

echo "=== 테스트 완료 ==="
echo ""
echo "실제 스크래핑을 실행하려면:"
echo "1. 위의 주석 처리된 명령어들을 주석 해제하거나"
echo "2. 직접 node scraper.js --site [사이트] --url [URL] --year [연도] 실행"
echo ""
echo "추가 도움이 필요하시면 README_nodejs_scraper.md를 참조하세요."