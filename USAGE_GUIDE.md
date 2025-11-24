# andong_scraper.js 사용 가이드

## 📋 개요

`andong_scraper.js`는 2가지 모드로 실행할 수 있습니다:

1. **URL 추출 모드** (`--count`) - 상세 URL만 추출하여 DB에 저장 (빠름, 다운로드 없음)
2. **전체 스크래핑 모드** (기본) - 첨부파일 다운로드 + content.md 생성

---

## 🚀 사용법

### 모드 1: URL만 추출 (권장 - 첫 단계)

실제 다운로드 없이 상세 URL만 빠르게 추출하여 DB에 저장합니다.

```bash
# 기본 사용 - 2025년 공고 URL 추출
node node/scraper/andong_scraper.js --site andong --year 2025 --count

# 특정 날짜 이후 공고 URL 추출
node node/scraper/andong_scraper.js --site andong --date 20240101 --count

# 배치 날짜 지정
node node/scraper/andong_scraper.js --site andong --year 2024 --count --batch-date 2025-01-15
```

**장점:**
- ⚡ 빠른 실행 (다운로드 없음)
- 📊 URL 목록 확인 가능
- 🔍 중복 URL 자동 제거
- ✅ 이후 실제 스크래핑 시 중복 체크 가능

**출력 예시:**
```
=== 상세 URL 추출 및 저장 시작 ===
사이트 코드: andong

페이지 1 확인 중...
  ✓ 2025년도 제1차 안동시 정책자문위원회 개최 안내...
  ✓ 안동시 2025년 상반기 지역개발채권 매입대상 확인...
  ...

=== URL 추출 완료 ===
총 URL 수: 150개
DB 저장 성공: 150개
확인한 페이지 수: 15개

DB 통계:
  전체: 150개
  스크래핑 완료: 0개
  스크래핑 대기: 150개
```

### 모드 2: 전체 스크래핑 (기본)

첨부파일 다운로드 + content.md 생성까지 전부 수행합니다.

```bash
# 기본 사용 - 2025년 공고 스크래핑
node node/scraper/andong_scraper.js --site andong --year 2025

# 특정 날짜 이후 공고 스크래핑
node node/scraper/andong_scraper.js --site andong --date 20240101

# 기존 폴더 덮어쓰기
node node/scraper/andong_scraper.js --site andong --year 2024 --force
```

**출력 예시:**
```
=== 스크래핑 시작 ===
대상 연도: 2025
사이트 코드: andong

--- 페이지 1 처리 중 ---
처리 중: 2025년도 제1차 안동시 정책자문위원회 개최 안내
  상세 페이지 URL: https://...
  📥 첨부파일 3개 다운로드 중...
  ✅ 파일 저장 성공: 001_2025년도_제1차_안동시_정책자문위원회...

스크래핑 성공: 150개 공고 처리
```

---

## 📊 주요 옵션

| 옵션 | 짧은 형식 | 설명 | 기본값 |
|------|----------|------|--------|
| `--count` | `-c` | URL만 추출 모드 | `false` |
| `--site` | `-s` | 사이트 코드 | `andong` |
| `--year` | `-y` | 대상 연도 | `2025` |
| `--date` | `-d` | 대상 날짜 (YYYYMMDD) | `null` |
| `--batch-date` | `-b` | 배치 날짜 (YYYY-MM-DD) | 오늘 |
| `--output` | `-o` | 출력 디렉토리 | `scraped_data` |
| `--force` | `-f` | 기존 폴더 덮어쓰기 | `false` |
| `--url` | `-u` | 기본 URL | andong URL |
| `--list-selector` | - | 리스트 선택자 | `table.bod_list tbody tr` |
| `--title-selector` | - | 제목 선택자 | `td:nth-child(3) a` |
| `--date-selector` | - | 날짜 선택자 | `td:nth-child(5)` |

---

## 🔄 권장 워크플로우

### 1단계: URL 추출

```bash
# 빠르게 URL만 추출
node node/scraper/andong_scraper.js --site andong --year 2024 --count
```

### 2단계: DB 확인

```sql
-- 추출된 URL 확인
SELECT COUNT(*) as total, site_code
FROM scraper_detail_urls
WHERE batch_date = CURDATE()
  AND site_code = 'andong';

-- 샘플 확인
SELECT title, detail_url, normalized_url
FROM scraper_detail_urls
WHERE site_code = 'andong'
  AND batch_date = CURDATE()
LIMIT 10;
```

### 3단계: 실제 스크래핑

```bash
# 전체 스크래핑 실행
node node/scraper/andong_scraper.js --site andong --year 2024
```

### 4단계: 검증

```sql
-- 스크래핑 완료 현황
SELECT
    site_code,
    COUNT(*) as total,
    SUM(scraped) as completed,
    SUM(1-scraped) as pending
FROM scraper_detail_urls
WHERE batch_date = CURDATE()
GROUP BY site_code;

-- 실패한 공고 확인
SELECT * FROM scraper_failed_announcements
WHERE site_code = 'andong'
  AND batch_date = CURDATE()
  AND status = 'pending';
```

---

## 🌐 다른 사이트로 확장

### 경기도 (gg)

```bash
node node/scraper/andong_scraper.js \
  --site gg \
  --url "https://www.gg.go.kr/bbs/boardList.do?bsIdx=469&menuId=1547" \
  --list-selector "table tbody tr" \
  --title-selector "td.subject a" \
  --date-selector "td.date" \
  --year 2024 \
  --count
```

### 거제시 (geoje)

```bash
node node/scraper/andong_scraper.js \
  --site geoje \
  --url "https://www.gjcity.go.kr/portal/saeol/gosi/list.do?mId=0202010000" \
  --list-selector "table.bod_list tbody tr" \
  --title-selector "td:nth-child(2) a" \
  --date-selector "td:nth-child(5)" \
  --date 20240101 \
  --count
```

---

## 💡 팁

### 1. 소량 테스트

최신 공고만 빠르게 테스트:

```bash
# 2025-01-01 이후 공고만 (소량)
node node/scraper/andong_scraper.js --site andong --date 20250101 --count
```

### 2. 배치 날짜 활용

같은 날 여러 번 실행해도 중복 저장되지 않습니다:

```bash
# 첫 실행
node node/scraper/andong_scraper.js --site andong --year 2024 --count

# 재실행 (중복 제거됨)
node node/scraper/andong_scraper.js --site andong --year 2024 --count
```

### 3. URL 정규화 확인

```javascript
const UrlManager = require('./node/scraper/url_manager');

// URL 정규화 테스트
const url1 = 'https://example.com/view?id=123&page=10';
const url2 = 'https://example.com/view?id=123&page=99';

console.log(UrlManager.normalizeUrl(url1));
// → https://example.com/view?id=123

console.log(UrlManager.normalizeUrl(url2));
// → https://example.com/view?id=123

console.log(UrlManager.hashUrl(UrlManager.normalizeUrl(url1)) ===
            UrlManager.hashUrl(UrlManager.normalizeUrl(url2)));
// → true (같은 공고로 인식)
```

---

## ❓ 자주 묻는 질문

### Q1: --count 모드와 일반 모드의 차이는?

| 구분 | --count 모드 | 일반 모드 |
|------|-------------|----------|
| 실행 속도 | ⚡ 매우 빠름 | 🐢 느림 |
| 디스크 사용 | 0 MB | GB 단위 |
| URL 추출 | ✅ | ✅ |
| 상세 페이지 접근 | ✅ (URL만) | ✅ |
| 첨부파일 다운로드 | ❌ | ✅ |
| content.md 생성 | ❌ | ✅ |
| DB 저장 | scraper_detail_urls | 모든 테이블 |

### Q2: --count 모드로 추출한 URL을 어떻게 활용하나요?

1. **중복 체크**: 실제 스크래핑 시 이미 추출된 URL인지 확인
2. **통계**: 예상 건수 파악
3. **선별 스크래핑**: 특정 URL만 골라서 스크래핑 가능
4. **에러 분석**: URL 생성 로직 검증

### Q3: 두 모드를 같이 써야 하나요?

**권장 사항:**
- 신규 사이트: --count → 확인 → 전체 스크래핑
- 기존 사이트: 전체 스크래핑만 실행

### Q4: 중복 URL은 어떻게 처리되나요?

```sql
-- UNIQUE KEY로 자동 중복 제거
UNIQUE KEY uk_site_url_hash (site_code, url_hash, batch_date)
```

같은 `site_code`, `url_hash`, `batch_date`는 1개만 저장됩니다.

---

## 🔧 트러블슈팅

### 문제: "UrlManager is not defined"

**원인:** --count 모드에서 UrlManager 로드 실패

**해결:**
```bash
# url_manager.js 존재 확인
ls node/scraper/url_manager.js

# Syntax 체크
node -c node/scraper/url_manager.js
```

### 문제: URL이 DB에 저장되지 않음

**원인:** DB 테이블 미생성

**해결:**
```bash
mysql -u root -p classfy < create_detail_urls_table.sql
```

### 문제: 같은 URL이 계속 추출됨

**원인:** page 파라미터가 정규화되지 않는 새로운 형태

**해결:** `node/scraper/url_manager.js` 수정:
```javascript
const pageParams = [
    'page', 'pageNum', // 기존
    'yourNewPageParam' // 추가
];
```

---

## 📚 관련 문서

- [SCRAPER_SYSTEMS_SUMMARY.md](./SCRAPER_SYSTEMS_SUMMARY.md) - 전체 시스템 정리
- [URL_EXTRACTION_README.md](./URL_EXTRACTION_README.md) - URL 추출 상세 가이드
- [SCRAPER_FAILURE_RETRY_README.md](./SCRAPER_FAILURE_RETRY_README.md) - 실패 재시도 가이드
