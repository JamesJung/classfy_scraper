# 스크래퍼 시스템 전체 정리

## 🎯 구축된 3가지 시스템

---

## 1️⃣ 실패 공고 추적 및 재시도 시스템

### 개요
스크래핑 중 실패한 개별 공고를 DB에 기록하고 재시도하는 시스템

### 핵심 파일
- `create_failed_announcements_table.sql` - 실패 공고 저장 테이블
- `node/scraper/failure_logger.js` - 실패 로깅 모듈
- `patch_scrapers.js` - 156개 스크래퍼 자동 패치
- `patch_17_scrapers.js` - 17개 특수 케이스 수동 패치
- `retry_failed_announcements.py` - 실패 공고 재시도
- `test_failure_logger.js` - 테스트 스크립트

### DB 테이블
```sql
scraper_failed_announcements
- id, batch_date, site_code
- announcement_title, announcement_url, detail_url
- error_type, error_message
- retry_count, status (pending/success/permanent_failure)
```

### 사용법
```bash
# 1. 테이블 생성
mysql -u root -p classfy < create_failed_announcements_table.sql

# 2. 스크래퍼 실행 (자동으로 실패 기록)
node node/scraper/andong_scraper.js --site andong --year 2024

# 3. 실패 공고 재시도
python3 retry_failed_announcements.py --site andong --date 2025-01-15
```

### 상태
✅ **완료** - 156개 스크래퍼 모두 패치 완료, 구문 오류 없음

### 문서
📄 [SCRAPER_FAILURE_RETRY_README.md](./SCRAPER_FAILURE_RETRY_README.md)

---

## 2️⃣ 건수 검증 시스템

### 개요
예상 건수와 실제 스크래핑 건수를 비교하여 부분 실패 감지

### 핵심 파일
- `create_count_validation_table.sql` - 건수 검증 테이블
- `node/scraper/count_validator.js` - 건수 검증 모듈
- `run_scraper_with_validation.js` - 검증 포함 스크래핑
- `test_count_validation.js` - 테스트 스크립트

### DB 테이블
```sql
scraper_count_validation
- id, batch_date, site_code
- expected_count, actual_count, failed_count
- status (counting/scraping/completed/mismatch)
- count_started_at, scrape_completed_at
```

### andong_scraper 추가 메소드
```javascript
// 예상 건수 카운트 (다운로드 없음)
await scraper.countExpectedAnnouncements()
// → { totalCount, pageCount }

// 실제 스크래핑 (성공 건수 반환)
await scraper.scrape()
// → { successCount, startCounter, endCounter }
```

### 사용법
```bash
# 1. 테이블 생성
mysql -u root -p classfy < create_count_validation_table.sql

# 2. 검증 포함 스크래핑 (카운트 → 스크래핑 → 검증)
node run_scraper_with_validation.js --site andong --year 2024

# 3. 카운트 생략하고 바로 스크래핑
node run_scraper_with_validation.js --site andong --skip-count
```

### 검증 로직
```javascript
// 1. 예상 건수 카운트
const { totalCount } = await scraper.countExpectedAnnouncements();
await CountValidator.completeCounting(siteCode, totalCount, pageCount);

// 2. 실제 스크래핑
const { successCount } = await scraper.scrape();

// 3. 검증
const validation = await CountValidator.completeScraping(siteCode, successCount);
if (validation.mismatch) {
    console.log(`⚠️ 예상 ${validation.expectedCount}개 중 ${validation.actualCount}개만 성공`);
}
```

### 상태
✅ **완료** - andong_scraper에 통합 완료

---

## 3️⃣ URL 추출 및 중복 체크 시스템 ⭐ NEW

### 개요
실제 스크래핑 전에 상세 URL만 추출하여 DB에 저장하고 중복 체크

### 핵심 파일
- `create_detail_urls_table.sql` - URL 저장 테이블
- `node/scraper/url_manager.js` - URL 관리 모듈
- `extract_urls.js` - URL 추출 실행 스크립트
- `test_url_normalization.js` - URL 정규화 테스트

### DB 테이블
```sql
scraper_detail_urls
- id, batch_date, site_code
- title, list_url, detail_url
- normalized_url (page 파라미터 제거)
- url_hash (SHA256)
- scraped (0: 미완료, 1: 완료)
- UNIQUE KEY (site_code, url_hash, batch_date)
```

### URL 정규화 로직
**제거되는 파라미터:**
- page, pageNum, pageNo, pageIndex, startPage, currentPage, p, pg
- offset, start, from
- pageSize, size, limit
- isManager, isCharge

**예시:**
```
원본 1: https://www.gg.go.kr/.../boardView.do?bIdx=123&page=10
원본 2: https://www.gg.go.kr/.../boardView.do?bIdx=123&page=99
정규화: https://www.gg.go.kr/.../boardView.do?bIdx=123
→ 같은 url_hash 생성 → 중복으로 판단
```

### andong_scraper 추가 메소드
```javascript
// URL만 추출하여 DB 저장
await scraper.extractAndSaveUrls(batchDate)
// → { totalCount, savedCount, pageCount }
```

### 사용법
```bash
# 1. 테이블 생성
mysql -u root -p classfy < create_detail_urls_table.sql

# 2. URL 정규화 테스트
node test_url_normalization.js
# → ✅ 모든 테스트 통과 확인

# 3. URL 추출
node extract_urls.js --site andong --year 2024

# 4. 다른 사이트 코드로도 실행
node extract_urls.js --site gg --year 2024
node extract_urls.js --site geoje --date 20240101

# 5. 통계 확인
SELECT site_code, COUNT(*) as total,
       SUM(scraped) as completed,
       SUM(1-scraped) as pending
FROM scraper_detail_urls
WHERE batch_date = '2025-01-15'
GROUP BY site_code;
```

### UrlManager API
```javascript
const UrlManager = require('./node/scraper/url_manager');

// URL 정규화
const normalized = UrlManager.normalizeUrl(url);

// URL 저장
await UrlManager.saveDetailUrl({
    site_code: 'andong',
    title: '공고 제목',
    detail_url: detailUrl,
    batch_date: '2025-01-15'
});

// 중복 체크
const isDup = await UrlManager.isDuplicate('andong', detailUrl);

// 스크래핑 완료 표시
await UrlManager.markAsScraped('andong', detailUrl);

// 미스크래핑 URL 조회
const unscraped = await UrlManager.getUnscrapedUrls('andong', '2025-01-15', 100);

// 통계
const stats = await UrlManager.getStats('andong', '2025-01-15');
// → { total, scraped, unscraped }
```

### 상태
✅ **완료** - 테스트 통과, andong_scraper에 통합 완료

### 문서
📄 [URL_EXTRACTION_README.md](./URL_EXTRACTION_README.md)

---

## 🔄 워크플로우 통합

### 전체 스크래핑 프로세스

```
┌────────────────────────────────────────────┐
│ 1단계: URL 추출                             │
│ extract_urls.js                            │
│ - 리스트 페이지 순회                        │
│ - 상세 URL 생성 및 정규화                   │
│ - scraper_detail_urls에 저장               │
└──────────────┬─────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────┐
│ 2단계: 건수 카운트 (선택)                   │
│ countExpectedAnnouncements()               │
│ - 예상 건수 확인                            │
│ - scraper_count_validation에 기록          │
└──────────────┬─────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────┐
│ 3단계: 실제 스크래핑                        │
│ scrape()                                   │
│ - URL 중복 체크 (UrlManager)               │
│ - 첨부파일 다운로드                         │
│ - content.md 생성                          │
│ - 실패 시 scraper_failed_announcements 기록│
│ - 성공 시 markAsScraped() 호출             │
└──────────────┬─────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────┐
│ 4단계: 검증 및 재시도                       │
│ - 건수 검증 (expected vs actual)           │
│ - 실패 공고 재시도 (retry_failed_...)      │
│ - 미스크래핑 URL 재처리                     │
└────────────────────────────────────────────┘
```

---

## 📊 DB 테이블 관계

```
scraper_detail_urls (URL 목록)
├─ site_code, batch_date
├─ detail_url, normalized_url, url_hash
└─ scraped (0/1)
    │
    ├─→ scraper_count_validation (건수 검증)
    │   ├─ expected_count (URL 추출 건수)
    │   ├─ actual_count (스크래핑 성공 건수)
    │   └─ failed_count
    │
    └─→ scraper_failed_announcements (실패 공고)
        ├─ detail_url (scraper_detail_urls와 연결)
        ├─ error_type, error_message
        └─ retry_count, status
```

---

## 🚀 권장 실행 순서

### 신규 사이트 스크래핑

```bash
# 1. URL 추출 (빠름, 다운로드 없음)
node extract_urls.js --site andong --year 2024

# 2. 추출된 URL 확인
SELECT COUNT(*) FROM scraper_detail_urls
WHERE site_code = 'andong' AND batch_date = CURDATE();

# 3. 건수 검증 포함 스크래핑
node run_scraper_with_validation.js --site andong --year 2024

# 4. 실패 공고 재시도
python3 retry_failed_announcements.py --site andong

# 5. 최종 검증
SELECT
    (SELECT COUNT(*) FROM scraper_detail_urls WHERE site_code='andong' AND scraped=1) as scraped,
    (SELECT COUNT(*) FROM scraper_detail_urls WHERE site_code='andong' AND scraped=0) as unscraped,
    (SELECT COUNT(*) FROM scraper_failed_announcements WHERE site_code='andong' AND status='pending') as failed;
```

### 기존 스크래핑 (URL 추출 생략)

```bash
# 바로 스크래핑 (기존 방식과 동일)
node node/scraper/andong_scraper.js --site andong --year 2024

# 실패 공고 재시도
python3 retry_failed_announcements.py --site andong
```

---

## 📋 체크리스트

### 시스템 1: 실패 공고 추적
- [x] DB 테이블 생성
- [x] failure_logger.js 구현
- [x] 156개 스크래퍼 패치
- [x] 재시도 로직 구현
- [x] 테스트 완료

### 시스템 2: 건수 검증
- [x] DB 테이블 생성
- [x] count_validator.js 구현
- [x] andong_scraper 통합
- [x] 검증 스크립트 작성
- [x] 테스트 완료

### 시스템 3: URL 추출 및 중복 체크
- [x] DB 테이블 생성
- [x] url_manager.js 구현
- [x] URL 정규화 로직
- [x] andong_scraper 통합
- [x] 추출 스크립트 작성
- [x] 테스트 완료 (8/8 통과)

---

## 🛠️ 유지보수

### 새로운 page 관련 파라미터 추가
`node/scraper/url_manager.js` 수정:
```javascript
const pageParams = [
    'page', 'pageNum', // 기존
    'newPageParam' // 추가
];
```

### 새로운 사이트 코드 추가
```bash
# URL 추출
node extract_urls.js \
  --site new_site \
  --url "https://..." \
  --list-selector "..." \
  --title-selector "..." \
  --date-selector "..." \
  --year 2024
```

### 실패율 모니터링
```sql
-- 일별 실패율
SELECT
    batch_date,
    site_code,
    COUNT(*) as total,
    SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as failed,
    ROUND(SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as fail_rate
FROM scraper_failed_announcements
WHERE batch_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
GROUP BY batch_date, site_code
ORDER BY fail_rate DESC;
```

---

## 📚 관련 문서

1. [SCRAPER_FAILURE_RETRY_README.md](./SCRAPER_FAILURE_RETRY_README.md) - 실패 공고 재시도 시스템
2. [URL_EXTRACTION_README.md](./URL_EXTRACTION_README.md) - URL 추출 및 중복 체크 시스템
3. [test_failure_logger.js](./test_failure_logger.js) - 실패 로거 테스트
4. [test_count_validation.js](./test_count_validation.js) - 건수 검증 테스트
5. [test_url_normalization.js](./test_url_normalization.js) - URL 정규화 테스트

---

## 🎉 완성된 기능

✅ **개별 공고 실패 추적** - 어떤 공고가 실패했는지 정확히 파악
✅ **자동 재시도** - 실패한 공고 자동 재처리
✅ **건수 검증** - 예상 vs 실제 건수 비교로 부분 실패 감지
✅ **URL 중복 제거** - page 파라미터 무시, 같은 공고 중복 방지
✅ **진행 상황 추적** - 어디까지 스크래핑했는지 실시간 확인
✅ **다중 사이트 지원** - 모든 site_code에 적용 가능

---

**구축 완료!** 🎊
