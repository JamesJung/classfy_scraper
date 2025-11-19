# 스크래퍼 사이트 헬스체크

스크래퍼 대상 사이트의 상태를 모니터링하고 문제가 있는 사이트를 자동으로 감지하는 헬스체크 시스템입니다.

## 📋 기능

### 1. 헬스체크 항목

#### HTTP 상태 코드
- ✅ **정상**: 200, 201
- ⚠️ **리다이렉트**: 301, 302, 303, 307, 308
- ❌ **클라이언트 오류**: 400, 401, 403, 404, 405, 406, 407, 408, 409, 410
- ❌ **서버 오류**: 500, 501, 502, 503, 504, 505

#### 응답 시간
- ✅ **정상**: < 10초
- ⚠️ **느림**: 10-20초
- ❌ **매우 느림**: > 20초
- ❌ **타임아웃**: > 30초

#### 네트워크 오류
- ❌ **DNS_ERROR**: 도메인을 찾을 수 없음 (ENOTFOUND)
- ❌ **CONNECTION_REFUSED**: 연결 거부됨 (ECONNREFUSED)
- ❌ **TIMEOUT**: 연결 타임아웃 (ETIMEDOUT)
- ❌ **SSL_ERROR**: SSL/TLS 인증서 오류
- ⚠️ **HTTP_PARSE_ERROR**: HTTP 파싱 에러 (브라우저 전용 사이트)

#### HTTP 클라이언트
- **undici**: Node.js 공식 HTTP 클라이언트 사용
- axios 대비 더 관대한 HTTP 파싱
- 브라우저 호환성 향상
- **SSL 검증 비활성화**: Agent를 통한 SSL 인증서 검증 비활성화 (브라우저와 동일한 동작)
- **자동 리다이렉트**: 리다이렉트를 자동으로 따라가므로 정상으로 처리

### 2. 데이터베이스 테이블 구조

#### health_check_log 테이블
문제가 있는 사이트의 상세 로그를 기록합니다.

```sql
CREATE TABLE health_check_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    check_date DATE NOT NULL,
    site_code VARCHAR(100) NOT NULL,
    site_url VARCHAR(1000) NOT NULL,
    status_code INT,
    error_type VARCHAR(100),
    error_message TEXT,
    response_time INT COMMENT '응답시간(ms)',
    redirect_url VARCHAR(1000) COMMENT '리다이렉트된 URL',
    redirect_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_check (check_date, site_code),
    INDEX idx_check_date (check_date),
    INDEX idx_site_code (site_code),
    INDEX idx_status_code (status_code)
)
```

#### health_check_summary 테이블
일별 헬스체크 요약 정보를 저장합니다.

```sql
CREATE TABLE health_check_summary (
    id INT AUTO_INCREMENT PRIMARY KEY,
    check_date DATE NOT NULL,
    total_count INT NOT NULL DEFAULT 0 COMMENT '총 체크 사이트 수',
    success_count INT NOT NULL DEFAULT 0 COMMENT '성공 건수',
    failure_count INT NOT NULL DEFAULT 0 COMMENT '실패 건수',
    avg_response_time INT COMMENT '평균 응답시간(ms)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_date (check_date),
    INDEX idx_check_date (check_date)
)
```

## 🚀 사용법

### 1. 테스트 실행 (처음 10개 사이트만)

```bash
node node/health/health_check_test.js
```

### 2. 전체 사이트 헬스체크 (undici)

```bash
node node/health/health_check.js
```

### 3. Playwright 브라우저 헬스체크

HTTP 파싱 에러가 발생하는 사이트들을 실제 브라우저로 재검증:

```bash
# HTTP_PARSE_ERROR 사이트만 체크 (기본)
node node/health/health_check_playwright.js

# 또는 명시적으로
node node/health/health_check_playwright.js --parse-errors-only

# 전체 사이트를 브라우저로 체크 (느림, 권장하지 않음)
node node/health/health_check_playwright.js --all
```

**사용 시나리오:**
1. 먼저 `health_check.js`로 전체 사이트 체크
2. HTTP_PARSE_ERROR가 발견되면 `health_check_playwright.js`로 재검증
3. 브라우저에서 실제로 정상 작동하는지 확인

### 4. 크론잡 설정 (매일 자동 실행)

```bash
# crontab -e
# 매일 오전 3시에 실행
0 3 * * * cd /Users/jin/classfy_scraper && node node/health/health_check.js >> logs/health_check.log 2>&1
```

## 📊 결과 확인

### 1. 오늘의 요약 정보

```sql
SELECT
    check_date,
    total_count,
    success_count,
    failure_count,
    ROUND(success_count * 100.0 / total_count, 2) as success_rate,
    avg_response_time
FROM health_check_summary
WHERE check_date = CURDATE();
```

### 2. 주간 트렌드

```sql
SELECT
    check_date,
    total_count,
    success_count,
    failure_count,
    avg_response_time,
    ROUND(success_count * 100.0 / total_count, 2) as success_rate
FROM health_check_summary
WHERE check_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
ORDER BY check_date DESC;
```

### 3. 최근 헬스체크 실패 상세

```sql
SELECT
    check_date,
    COUNT(*) as error_count,
    GROUP_CONCAT(DISTINCT error_type) as error_types
FROM health_check_log
WHERE check_date >= DATE_SUB(CURDATE(), INTERVAL 1 DAY)
GROUP BY check_date
ORDER BY check_date DESC;
```

### 4. 오류 타입별 통계

```sql
SELECT
    error_type,
    COUNT(*) as count,
    COUNT(DISTINCT site_code) as affected_sites
FROM health_check_log
WHERE check_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
GROUP BY error_type
ORDER BY count DESC;
```

### 5. 가장 문제가 많은 사이트

```sql
SELECT
    site_code,
    site_url,
    COUNT(*) as error_count,
    GROUP_CONCAT(DISTINCT error_type) as error_types,
    MAX(check_date) as last_error
FROM health_check_log
WHERE check_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
GROUP BY site_code, site_url
ORDER BY error_count DESC
LIMIT 10;
```

### 6. 특정 사이트의 헬스체크 히스토리

```sql
SELECT
    check_date,
    status_code,
    error_type,
    error_message,
    response_time,
    redirect_url
FROM health_check_log
WHERE site_code = 'andong'
ORDER BY check_date DESC
LIMIT 20;
```

### 7. 대시보드용 통합 쿼리

```sql
SELECT
    s.check_date,
    s.total_count,
    s.success_count,
    s.failure_count,
    s.avg_response_time,
    ROUND(s.success_count * 100.0 / s.total_count, 2) as success_rate,
    COUNT(DISTINCT l.error_type) as error_type_count
FROM health_check_summary s
LEFT JOIN health_check_log l ON s.check_date = l.check_date
WHERE s.check_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
GROUP BY s.check_date, s.total_count, s.success_count, s.failure_count, s.avg_response_time
ORDER BY s.check_date DESC;
```

## ⚙️ 설정

`health_check.js` 파일의 `CONFIG` 객체에서 설정을 변경할 수 있습니다:

```javascript
const CONFIG = {
    timeout: 30000,        // 타임아웃 30초 (정부 사이트는 느린 경우가 많음)
    userAgent: '...',      // User-Agent 헤더
    concurrency: 5,        // 동시 실행 수
};
```

**참고**:
- 타임아웃을 30초로 설정하여 느린 정부 사이트도 처리 가능
- 20초 이상 응답하는 사이트는 SLOW_RESPONSE로 표시
- undici는 자동으로 리다이렉트를 따라가므로 별도 설정 불필요

## 📈 예상 실행 시간

- **테스트 모드** (10개): 약 30초-1분
- **전체 실행** (605개): 약 40-60분
  - 동시 실행 수: 5개
  - 사이트당 평균 3-5초
  - 타임아웃: 30초
  - 배치 간 1초 대기

## 🔍 에러 타입 설명

| 에러 타입 | 설명 | 원인 |
|----------|------|------|
| `DNS_ERROR` | DNS 조회 실패 | 도메인이 존재하지 않거나 DNS 서버 문제 |
| `CONNECTION_REFUSED` | 연결 거부 | 서버가 응답하지 않거나 방화벽 차단 |
| `TIMEOUT` | 타임아웃 | 서버 응답이 너무 느림 (30초 초과) |
| `SSL_ERROR` | SSL 오류 | 인증서 만료/유효하지 않음 |
| `HTTP_PARSE_ERROR` | HTTP 파싱 에러 | HTTP 헤더/응답 라인이 표준 미준수 (브라우저 전용) |
| `CLIENT_ERROR` | 클라이언트 오류 | 404, 403 등 클라이언트 측 오류 |
| `SERVER_ERROR` | 서버 오류 | 500, 502, 503 등 서버 측 오류 |
| `REDIRECT` | 리다이렉트 | URL이 다른 주소로 리다이렉트됨 |
| `SLOW_RESPONSE` | 느린 응답 | 응답 시간이 20초 이상 |
| `TOO_MANY_REDIRECTS` | 과도한 리다이렉트 | 5회 이상 리다이렉트 |
| `NETWORK_ERROR` | 네트워크 오류 | 기타 네트워크 관련 오류 |

## 📝 로그 예시

### 정상 사이트
```
✅ andong: 정상 (1053ms)
✅ anseong: 정상 (1667ms)
```

### 문제 있는 사이트
```
❌ example1: CLIENT_ERROR - 클라이언트 오류: 404
❌ example2: TIMEOUT - 타임아웃 (10000ms)
❌ example3: REDIRECT - 리다이렉트 감지: 301
⚠️  haman: HTTP_PARSE_ERROR - 브라우저 전용 사이트 (HTTP 헤더 파싱 에러)
```

## 🛠️ 트러블슈팅

### 1. MySQL 연결 오류
```bash
# .env 파일 확인
cat .env | grep DB_

# MySQL 연결 테스트
mysql -h 192.168.0.95 -u root -p -P3309 subvention
```

### 2. 타임아웃이 너무 많이 발생
- `CONFIG.timeout` 값을 늘림 (현재: 30000ms, 더 필요하면 60000ms까지)
- `CONFIG.concurrency` 값을 줄임 (예: 3)

### 3. 메모리 부족
- `CONFIG.concurrency` 값을 줄임
- 배치 크기를 작게 조정

## 📚 의존성

```json
{
  "mysql2": "^3.15.3",
  "undici": "^7.16.0",
  "playwright": "^1.56.1",
  "dotenv": "^17.2.2"
}
```

**참고**:
- **undici**: Node.js 공식 HTTP 클라이언트로, axios보다 더 관대한 HTTP 파싱 제공
- **playwright**: HTTP 파싱 에러가 발생하는 사이트를 실제 브라우저로 검증
  - 설치 후 `npx playwright install chromium` 실행 필요

## 🔗 관련 파일

- `health_check.js` - 전체 사이트 헬스체크 (undici)
- `health_check_test.js` - 테스트용 (10개 사이트만, undici)
- `health_check_playwright.js` - Playwright 브라우저 헬스체크
- `.env` - 데이터베이스 연결 정보

## 📞 문의

문제가 발생하면 로그를 확인하거나 데이터베이스의 `health_check_log` 테이블을 조회하세요.
