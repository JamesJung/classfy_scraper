# Node.js 공고 스크래핑 시스템 (Playwright 기반)

기존 Python 기반 enhanced_scraper의 핵심 기능을 Node.js + Playwright로 구현한 고성능 웹 스크래핑 시스템입니다.

## 🎯 주요 기능

### ✅ 구현된 요구사항
1. **날짜 기반 필터링**: 파라미터로 받은 연도까지 스크래핑 진행
2. **2단계 날짜 확인**: 리스트 → 상세 페이지 순서로 날짜 검증
3. **다양한 페이지 접근 방식**: URL, JavaScript 방식 모두 지원
4. **본문 추출**: 헤더/사이드바 제외하고 content.md 파일 생성
5. **첨부파일 다운로드**: 링크/POST/JavaScript 방식 모두 구현
6. **페이징 처리**: 자동 페이지 이동으로 전체 데이터 수집
7. **폴더 구조**: `001_게시물이름/content.md, attachments/` 구조
8. **중복 방지**: 동일한 제목의 게시물 자동 스킵

## 📦 설치

### 1. 의존성 설치
```bash
npm install
```

### 2. 필요 패키지 확인
- `playwright`: 브라우저 자동화 (Chromium, Firefox, Safari 지원)
- `cheerio`: HTML 파싱
- `axios`: HTTP 요청
- `fs-extra`: 파일 시스템 유틸
- `moment`: 날짜 처리
- `yargs`: CLI 인터페이스

### 3. 브라우저 설치
```bash
# Playwright 브라우저 설치 (필수)
npx playwright install
```

## 🚀 사용법

### 기본 사용법
```bash
node scraper.js --site [사이트코드] --url [기본URL] --year [대상연도]
```

### 주요 옵션
```bash
# 필수 옵션
--site, -s        사이트 코드 (예: acci, cbt)
--url, -u         기본 URL (예: https://example.com/board)

# 선택 옵션  
--year, -y        대상 연도 (기본값: 현재 연도)
--output, -o      출력 디렉토리 (기본값: scraped_data)

# 선택자 커스터마이징
--list-selector   리스트 행 선택자 (기본값: 'table tr')
--title-selector  제목 링크 선택자 (기본값: 'td:nth-child(2) a')  
--date-selector   날짜 셀 선택자 (기본값: 'td:last-child')
```

## 📋 사용 예제

### 1. 기본 스크래핑
```bash
# 2025년까지 acci 사이트 스크래핑
node scraper.js \
  --site acci \
  --url "https://acci.or.kr/board/list" \
  --year 2025
```

### 2. 출력 디렉토리 지정
```bash
# custom_output 폴더에 저장
node scraper.js \
  --site cbt \
  --url "https://cbt.or.kr/notice" \
  --year 2025 \
  --output "custom_output"
```

### 3. 선택자 커스터마이징 
```bash
# 특별한 HTML 구조에 맞게 선택자 조정
node scraper.js \
  --site custom \
  --url "https://example.com/board" \
  --year 2025 \
  --list-selector ".board-list tr" \
  --title-selector ".title a" \
  --date-selector ".date"
```

### 4. 실제 사이트 예제들

#### ACCI (안산상공회의소)
```bash
node scraper.js \
  --site acci \
  --url "https://www.acci.or.kr/board/list?boardId=notice" \
  --year 2025 \
  --list-selector "tbody tr" \
  --title-selector ".title a" \
  --date-selector ".date"
```

#### CBT (중소기업기술혁신협회)  
```bash
node scraper.js \
  --site cbt \
  --url "https://www.cbt.or.kr/board/notice" \
  --year 2025 \
  --list-selector ".board-list tr" \
  --title-selector "td:nth-child(2) a" \
  --date-selector "td:nth-child(4)"
```

## 📁 출력 구조

```
scraped_data/
├── 001_2025년 창업지원사업 공고/
│   ├── content.md
│   └── attachments/
│       ├── 지원사업_신청서.hwp
│       └── 사업계획서_양식.pdf
├── 002_기술개발지원 안내/
│   ├── content.md
│   └── attachments/
│       └── 기술개발_가이드.pdf
└── 003_수출지원사업 모집공고/
    └── content.md
```

### content.md 예제
```markdown
# 2025년 창업지원사업 공고

**작성일:** 2025-01-15

## 본문

2025년도 창업지원사업을 다음과 같이 공고합니다.

### 1. 지원대상
- 예비창업자 및 창업 3년 이내 기업
- 기술기반 창업기업 우대

### 2. 지원내용  
- 사업화 자금: 최대 5,000만원
- 멘토링 및 컨설팅 지원
- 마케팅 지원

## 첨부파일

1. 지원사업_신청서.hwp
2. 사업계획서_양식.pdf
```

## ⚡ 핵심 알고리즘

### 날짜 기반 필터링 로직
```javascript
// 1단계: 리스트에서 날짜 확인
const listDate = this.extractDate(announcement.dateText);
if (listDate && listDate.year() < this.targetYear) {
    return true; // 스크래핑 중단
}

// 2단계: 상세 페이지에서 재확인  
const detailDate = this.extractDate(detailContent.dateText);
if (detailDate && detailDate.year() < this.targetYear) {
    return true; // 스크래핑 중단
}
```

### 상세 페이지 URL 구성
```javascript
async buildDetailUrl(announcement) {
    const link = announcement.link;
    
    // 완전한 URL
    if (link.startsWith('http')) return link;
    
    // 상대 URL  
    if (link.startsWith('/')) {
        return new URL(link, this.baseUrl).toString();
    }
    
    // JavaScript 방식
    if (link.includes('javascript:')) {
        const match = link.match(/location\.href\=[\'"](.*?)[\'"]|goView\([\'"](.*?)[\'"]\)/);
        if (match) return new URL(match[1] || match[2], this.baseUrl).toString();
    }
    
    return null;
}
```

### 첨부파일 다운로드 방식

#### 1. 링크 방식 (일반적)
```javascript
async downloadViaLink(url, attachDir, fileName) {
    const response = await axios({
        method: 'GET', 
        url: url,
        responseType: 'stream'
    });
    
    response.data.pipe(fs.createWriteStream(filePath));
}
```

#### 2. POST 방식 (폼 제출)
```javascript
async downloadViaForm(attachment, attachDir, fileName) {
    await this.page.evaluate((onclick) => {
        eval(onclick); // JavaScript 코드 실행
    }, attachment.onclick);
}
```

#### 3. JavaScript 방식
- `onclick` 이벤트 분석하여 URL 추출
- `window.open()`, `location.href` 등 다양한 패턴 지원

## 🔧 고급 설정

### 선택자 패턴 가이드
```javascript
// 일반적인 테이블 구조
listSelector: 'tbody tr'
titleSelector: 'td:nth-child(2) a'  // 2번째 열의 링크
dateSelector: 'td:last-child'       // 마지막 열

// div 기반 구조  
listSelector: '.board-item'
titleSelector: '.title a'
dateSelector: '.date'

// 복잡한 구조
listSelector: 'article.post'
titleSelector: 'h3.post-title a' 
dateSelector: '.meta .date'
```

### 날짜 형식 지원
- `YYYY-MM-DD` (2025-01-15)
- `YYYY.MM.DD` (2025.01.15)  
- `YYYY/MM/DD` (2025/01/15)
- `MM-DD-YYYY` (01-15-2025)
- 자연어 형식도 moment.js로 파싱 시도

### 브라우저 설정 커스터마이징
```javascript
// config.js에서 설정 변경
browser: {
    headless: "new",  // false로 변경시 브라우저 UI 표시
    devMode: false,   // true로 변경시 디버그 모드
    launchOptions: {
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage'  // 메모리 사용량 최적화
        ],
        timeout: 60000
    }
}
```

## 🐛 디버깅 가이드

### 1. 선택자 확인
브라우저 개발자 도구에서 CSS 선택자 테스트:
```javascript
// 콘솔에서 실행
document.querySelectorAll('table tr');     // 리스트 확인
document.querySelector('td:nth-child(2) a'); // 제목 링크 확인
```

### 2. 네트워크 요청 모니터링  
```javascript
// 페이지 이벤트 리스닝 추가
page.on('response', response => {
    console.log(`${response.status()} ${response.url()}`);
});
```

### 3. 스크린샷 촬영
```javascript
// 디버깅용 스크린샷
await page.screenshot({ path: 'debug.png', fullPage: true });
```

### 4. Playwright 디버그 모드
```bash
# 브라우저 UI를 보면서 디버깅
PWDEBUG=1 node scraper.js --site test --url "https://example.com"

# 단계별 실행
node scraper.js --site test --url "https://example.com" --debug
```

## ⚠️ 주의사항

### 1. robots.txt 준수
사이트의 robots.txt를 확인하고 스크래핑 정책을 준수하세요.

### 2. 요청 간격 조절
```javascript
await this.delay(1000); // 1초 대기 (서버 부하 방지)
```

### 3. 메모리 관리
대용량 스크래핑시 메모리 사용량 모니터링 필요.

### 4. 오류 처리
네트워크 오류, 페이지 로딩 실패 등에 대한 재시도 로직 구현 권장.

## 🔄 확장 가능성

### 1. 데이터베이스 연동
```javascript
// MySQL, PostgreSQL 등 데이터베이스 저장 기능 추가 가능
```

### 2. 병렬 처리
```javascript  
// Playwright의 멀티 브라우저 지원
// 다중 컨텍스트로 병렬 스크래핑 가능
```

### 3. 프록시 지원
```javascript
// Playwright 컨텍스트에서 프록시 설정
const context = await browser.newContext({
    proxy: { server: 'http://proxy-server:port' }
});
```

### 4. 스케줄링
```javascript
// cron을 통한 자동 스크래핑 스케줄링
```

## 📊 성능 비교

| 항목 | Python/Puppeteer | Node.js/Playwright |
|------|------------------|-------------------|
| 메모리 사용량 | 높음 | 중간 |
| 처리 속도 | 중간 | 높음 |  
| JavaScript 지원 | 완전 지원 | 완전 지원 |
| 브라우저 지원 | Chrome만 | Chrome/Firefox/Safari |
| 설치 복잡도 | 높음 | 낮음 |
| 안정성 | 중간 | 높음 |

## 📞 지원

문제 발생시 다음 정보와 함께 문의:
- 대상 사이트 URL
- 사용한 명령어
- 오류 메시지
- 브라우저 스크린샷

---

**개발**: Claude Code 기반 시스템  
**기반**: 기존 Python enhanced_scraper 분석  
**버전**: 1.0.0  
**상태**: 운영 준비 완료 ✅