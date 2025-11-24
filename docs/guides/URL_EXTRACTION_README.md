# 스크래퍼 URL 추출 및 검증 시스템

## 📋 개요

스크래핑 전에 상세 URL만 먼저 추출하여 DB에 저장하고, 실제 스크래핑 시 중복 체크를 수행하는 시스템입니다.

### 주요 기능

1. **URL만 추출** - 첨부파일 다운로드나 content.md 생성 없이 URL만 추출
2. **URL 정규화** - page 관련 파라미터 제거하여 중복 방지
3. **중복 체크** - 정규화된 URL의 해시값으로 중복 확인
4. **진행 상황 추적** - 스크래핑 완료 여부 기록

---

## 🗂️ 구성 요소

### 1. DB 테이블

```sql
CREATE TABLE scraper_detail_urls (
    id INT PRIMARY KEY AUTO_INCREMENT,
    batch_date DATE NOT NULL,
    site_code VARCHAR(50) NOT NULL,
    title VARCHAR(500) NULL,
    list_url TEXT NULL,
    detail_url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    url_hash VARCHAR(64) NOT NULL,
    list_date VARCHAR(50) NULL,
    scraped TINYINT(1) DEFAULT 0,
    scraped_at TIMESTAMP NULL,
    UNIQUE KEY uk_site_url_hash (site_code, url_hash, batch_date)
);
```

**생성 방법:**
```bash
mysql -h localhost -P 3306 -u [사용자] -p [데이터베이스] < create_detail_urls_table.sql
```

### 2. 핵심 모듈

#### `url_manager.js`
URL 정규화, 저장, 중복 체크를 담당하는 핵심 모듈

**주요 메소드:**
- `normalizeUrl(url)` - URL 정규화 (page 파라미터 제거)
- `hashUrl(url)` - URL의 SHA256 해시 생성
- `saveDetailUrl(data)` - URL DB 저장
- `isDuplicate(site_code, detail_url, batch_date)` - 중복 체크
- `markAsScraped(site_code, detail_url, batch_date)` - 스크래핑 완료 표시
- `getUnscrapedUrls(site_code, batch_date, limit)` - 미스크래핑 URL 조회
- `getStats(site_code, batch_date)` - 통계 조회

#### `andong_scraper.js` (확장됨)
새로운 메소드 추가:
- `extractAndSaveUrls(batchDate)` - URL만 추출하여 DB에 저장

---

## 🚀 사용 방법

### Step 1: URL 정규화 테스트

page 파라미터가 올바르게 제거되는지 확인:

```bash
node test_url_normalization.js
```

**예상 결과:**
```
✅ 모든 테스트 통과
✅ page 파라미터가 다른 URL들의 해시가 동일
✅ 고유 식별자가 다른 URL들의 해시가 다름
```

### Step 2: URL 추출 및 저장

특정 사이트의 상세 URL을 추출하여 DB에 저장:

```bash
# andong 사이트의 2024년 공고 URL 추출
node extract_urls.js --site andong --year 2024

# 특정 날짜 이후 공고만 추출
node extract_urls.js --site andong --date 20240101

# 배치 날짜 지정
node extract_urls.js --site andong --year 2024 --batch-date 2025-01-15
```

**CLI 옵션:**
- `--site, -s` : 사이트 코드 (필수)
- `--url, -u` : 기본 URL (필수)
- `--year, -y` : 대상 연도 (기본: 현재 연도)
- `--date, -d` : 대상 날짜 YYYYMMDD (선택)
- `--batch-date, -b` : 배치 날짜 YYYY-MM-DD (기본: 오늘)
- `--list-selector` : 리스트 선택자
- `--title-selector` : 제목 선택자
- `--date-selector` : 날짜 선택자

### Step 3: DB 확인

추출된 URL 확인:

```sql
-- 추출된 URL 확인
SELECT
    site_code,
    title,
    detail_url,
    normalized_url,
    scraped,
    created_at
FROM scraper_detail_urls
WHERE site_code = 'andong'
  AND batch_date = '2025-01-15'
ORDER BY created_at DESC
LIMIT 10;

-- 통계 확인
SELECT
    site_code,
    batch_date,
    COUNT(*) as total,
    SUM(CASE WHEN scraped = 1 THEN 1 ELSE 0 END) as scraped,
    SUM(CASE WHEN scraped = 0 THEN 1 ELSE 0 END) as unscraped
FROM scraper_detail_urls
GROUP BY site_code, batch_date
ORDER BY batch_date DESC;

-- 중복 확인 (같은 url_hash가 여러 개 있는지)
SELECT
    url_hash,
    COUNT(*) as count,
    GROUP_CONCAT(title SEPARATOR ' | ') as titles
FROM scraper_detail_urls
WHERE site_code = 'andong'
  AND batch_date = '2025-01-15'
GROUP BY url_hash
HAVING count > 1;
```

### Step 4: 실제 스크래핑 (향후)

실제 스크래핑 시 중복 체크 활용:

```javascript
const UrlManager = require('./node/scraper/url_manager');

// 스크래핑 전 중복 체크
const isDuplicate = await UrlManager.isDuplicate('andong', detailUrl, batchDate);
if (isDuplicate) {
    console.log('이미 추출된 URL, 스킵');
    return;
}

// 스크래핑 후 완료 표시
await UrlManager.markAsScraped('andong', detailUrl, batchDate);
```

---

## 🔍 URL 정규화 로직

### 제거되는 파라미터

- **페이지 관련:** page, pageNum, pageNo, pageIndex, pageNumber, startPage, currentPage, p, pg, pn
- **오프셋 관련:** offset, start, from
- **크기 관련:** pageSize, pagesize, size, limit
- **상태 관련:** isManager, isCharge

### 예시

```javascript
// 원본 URL 1
https://www.gg.go.kr/bbs/boardView.do?bIdx=201528470&bsIdx=469&bcIdx=0&menuId=1547&isManager=false&isCharge=false&page=10

// 원본 URL 2
https://www.gg.go.kr/bbs/boardView.do?bIdx=201528470&bsIdx=469&bcIdx=0&menuId=1547&isManager=false&isCharge=false&page=99

// 정규화 결과 (동일)
https://www.gg.go.kr/bbs/boardView.do?bIdx=201528470&bsIdx=469&bcIdx=0&menuId=1547

// 해시 (동일)
d39d7e0e1521e495...
```

---

## 📊 워크플로우

```
┌─────────────────────────┐
│  1. URL 추출            │
│  extract_urls.js        │
│  - 리스트 페이지 순회    │
│  - 상세 URL 생성        │
│  - URL 정규화           │
│  - DB 저장              │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  scraper_detail_urls    │
│  - detail_url           │
│  - normalized_url       │
│  - url_hash (SHA256)    │
│  - scraped = 0          │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  2. 실제 스크래핑        │
│  (향후 구현)             │
│  - 중복 체크             │
│  - 첨부파일 다운로드     │
│  - content.md 생성      │
│  - scraped = 1 업데이트 │
└─────────────────────────┘
```

---

## 🧪 테스트

### URL 정규화 테스트

```bash
node test_url_normalization.js
```

**테스트 항목:**
- ✅ page 파라미터 제거
- ✅ pageNum, pageIndex 등 다양한 변형 제거
- ✅ 중복 URL 해시 동일 확인
- ✅ 다른 URL 해시 다름 확인

### 실제 URL 추출 테스트 (소량)

```bash
# 최신 1페이지만 추출 (빠른 테스트)
node extract_urls.js --site andong --date 20250101
```

---

## 📈 통계 및 모니터링

### 추출 현황 조회

```javascript
const UrlManager = require('./node/scraper/url_manager');

const stats = await UrlManager.getStats('andong', '2025-01-15');
console.log(`전체: ${stats.total}개`);
console.log(`완료: ${stats.scraped}개`);
console.log(`대기: ${stats.unscraped}개`);
```

### 미스크래핑 URL 조회

```javascript
const unscraped = await UrlManager.getUnscrapedUrls('andong', '2025-01-15', 100);
console.log(`미스크래핑 URL ${unscraped.length}개:`);
unscraped.forEach(item => {
    console.log(`  - ${item.title}`);
    console.log(`    ${item.detail_url}`);
});
```

---

## 🔧 다른 사이트 코드로 확장

### 1. 사이트별 설정 준비

```bash
# 경기도 URL 추출
node extract_urls.js \
  --site gg \
  --url "https://www.gg.go.kr/bbs/boardList.do?bsIdx=469&menuId=1547" \
  --list-selector "table tbody tr" \
  --title-selector "td.subject a" \
  --date-selector "td.date" \
  --year 2024

# 거제시 URL 추출
node extract_urls.js \
  --site geoje \
  --url "https://www.gjcity.go.kr/portal/saeol/gosi/list.do?mId=0202010000" \
  --list-selector "table.bod_list tbody tr" \
  --title-selector "td:nth-child(2) a" \
  --date-selector "td:nth-child(5)" \
  --year 2024
```

### 2. 배치 스크립트 작성

여러 사이트를 순차적으로 처리하는 스크립트:

```bash
#!/bin/bash
# extract_all_sites.sh

SITES=("andong" "gg" "geoje")
YEAR=2024
BATCH_DATE=$(date +%Y-%m-%d)

for SITE in "${SITES[@]}"; do
    echo "=== $SITE 사이트 URL 추출 시작 ==="
    node extract_urls.js --site $SITE --year $YEAR --batch-date $BATCH_DATE
    echo ""
done

echo "=== 전체 통계 ==="
mysql -h localhost -P 3306 -u root -p -e "
    SELECT
        site_code,
        COUNT(*) as total,
        SUM(CASE WHEN scraped = 1 THEN 1 ELSE 0 END) as scraped,
        SUM(CASE WHEN scraped = 0 THEN 1 ELSE 0 END) as unscraped
    FROM classfy.scraper_detail_urls
    WHERE batch_date = '$BATCH_DATE'
    GROUP BY site_code;
"
```

---

## 🐛 트러블슈팅

### 문제 1: URL 정규화 후에도 중복 발생

**원인:** URL 파라미터 순서가 다름

**해결:** UrlManager의 `normalizeUrl()` 메소드가 URLSearchParams를 사용하여 자동으로 정렬합니다.

### 문제 2: UNIQUE 제약조건 위반

**원인:** 같은 URL을 재추출

**해결:** `ON DUPLICATE KEY UPDATE`를 사용하여 기존 레코드를 업데이트합니다.

### 문제 3: page 외 다른 파라미터도 제거 필요

**해결:** `url_manager.js`의 `pageParams` 배열에 추가:

```javascript
const pageParams = [
    'page', 'pageNum', // 기존
    'yourParam' // 추가
];
```

---

## 📝 TODO

- [ ] 실제 스크래핑 시 중복 체크 통합
- [ ] 미스크래핑 URL 재시도 로직
- [ ] URL 추출 실패 로그 수집
- [ ] 사이트별 URL 패턴 자동 감지
- [ ] 대량 사이트 병렬 처리

---

## 📚 관련 문서

- [SCRAPER_FAILURE_RETRY_README.md](./SCRAPER_FAILURE_RETRY_README.md) - 실패 공고 재시도 시스템
- [create_detail_urls_table.sql](./create_detail_urls_table.sql) - DB 테이블 생성
- [test_url_normalization.js](./test_url_normalization.js) - URL 정규화 테스트

---

## ⚙️ 환경 설정

`.env` 파일에 DB 설정 필요:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=subvention
```
