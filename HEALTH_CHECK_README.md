# Health Check 자동화 가이드

## 개요

스크래퍼 사이트들의 상태를 자동으로 체크하고 `health_check_log` 테이블에 결과를 저장하는 시스템입니다.

## 파일 구성

- `health_check.js` - Health Check 실행 스크립트
- `setup_health_check_cron.sh` - Crontab 자동 설정 스크립트
- `HEALTH_CHECK_README.md` - 이 파일

## 기능

### Health Check 수행 항목

1. **사이트 목록 조회**: `scraper_site_url` 테이블에서 사이트 목록 로드
2. **HTTP 요청**: 각 사이트 URL에 GET 요청
3. **결과 수집**:
   - HTTP 상태 코드 (200, 404, 500 등)
   - 응답 시간 (ms)
   - 리다이렉트 URL 및 횟수
   - 에러 타입 및 메시지 (DNS 오류, SSL 오류, 타임아웃 등)
4. **DB 저장**: `health_check_log` 테이블에 UPSERT
   - `(check_date, site_code)` 조합으로 중복 방지
   - 같은 날 같은 사이트는 최신 결과로 업데이트

## 설치 및 설정

### 1. 수동 실행 테스트

먼저 스크립트가 정상 작동하는지 테스트:

```bash
cd /Users/jin/classfy_scraper
node health_check.js
```

예상 출력:
```
========================================
  스크래퍼 사이트 Health Check 시작
  실행 시각: 2025-01-19T12:00:00.000Z
========================================

✓ 데이터베이스 연결 성공

총 50개 사이트 체크 시작...

[1/50] seoul_gangnam ... ✓ OK (245ms)
[2/50] busan_haeundae ... ⇢ Redirect 301 (1회)
[3/50] daegu_suseong ... ✗ TIMEOUT: Request timeout
...

========================================
  Health Check 완료
========================================
총 사이트: 50개
정상: 45개
오류: 5개
========================================
```

### 2. Crontab 자동 설정

매일 자정에 자동 실행되도록 crontab 등록:

```bash
cd /Users/jin/classfy_scraper
./setup_health_check_cron.sh
```

등록 후 확인:
```bash
crontab -l | grep health_check
```

출력 예시:
```
0 0 * * * /usr/local/bin/node /Users/jin/classfy_scraper/health_check.js >> /Users/jin/classfy_scraper/logs/health_check.log 2>&1
```

### 3. 실행 스케줄 변경 (옵션)

다른 시간에 실행하려면 crontab을 직접 수정:

```bash
crontab -e
```

예시:
- `0 0 * * *` - 매일 자정 (기본값)
- `0 6 * * *` - 매일 오전 6시
- `0 */6 * * *` - 6시간마다
- `0 12 * * 1` - 매주 월요일 정오

Cron 표현식 형식: `분 시 일 월 요일`

## 로그 확인

### 실행 로그 보기

```bash
# 최근 로그 확인
tail -f /Users/jin/classfy_scraper/logs/health_check.log

# 오늘 실행된 로그만 보기
grep "$(date +%Y-%m-%d)" /Users/jin/classfy_scraper/logs/health_check.log

# 에러만 필터링
grep "✗" /Users/jin/classfy_scraper/logs/health_check.log
```

### DB에서 결과 조회

```sql
-- 오늘 Health Check 결과
SELECT *
FROM health_check_log
WHERE check_date = CURDATE()
ORDER BY site_code;

-- 오류 발생 사이트
SELECT site_code, status_code, error_type, error_message
FROM health_check_log
WHERE check_date = CURDATE()
  AND (status_code IS NULL OR status_code >= 400)
ORDER BY site_code;

-- 응답 시간이 느린 사이트 (5초 이상)
SELECT site_code, response_time, site_url
FROM health_check_log
WHERE check_date = CURDATE()
  AND response_time > 5000
ORDER BY response_time DESC;
```

## Announcement Viewer에서 확인

Health Check 결과는 Announcement Viewer의 HEALTH체크 메뉴에서 확인 가능:

1. 브라우저에서 http://localhost:3003 접속
2. 상단 메뉴에서 "HEALTH체크" 클릭
3. 날짜, 사이트 코드, 상태 코드로 필터링 가능

## 문제 해결

### Crontab이 실행되지 않는 경우

1. **cron 서비스 확인** (Linux):
   ```bash
   sudo systemctl status cron
   sudo systemctl start cron
   ```

2. **macOS에서 권한 문제**:
   - 시스템 환경설정 > 보안 및 개인정보 보호 > 전체 디스크 접근
   - Terminal 또는 cron에 권한 부여

3. **로그 확인**:
   ```bash
   # macOS
   log show --predicate 'process == "cron"' --last 1h

   # Linux
   grep CRON /var/log/syslog
   ```

### 스크립트 실행 오류

1. **Node.js 경로 확인**:
   ```bash
   which node
   # crontab의 NODE_PATH와 일치하는지 확인
   ```

2. **데이터베이스 연결 실패**:
   - DB_CONFIG의 호스트, 포트, 인증정보 확인
   - 네트워크 연결 확인

3. **타임아웃 조정**:
   `health_check.js`의 `REQUEST_TIMEOUT` 값 조정 (기본 10초)

## Crontab 제거

Health Check 자동 실행을 중지하려면:

```bash
# 현재 crontab 백업
crontab -l > ~/crontab_backup.txt

# health_check 항목만 제거
crontab -l | grep -v 'health_check.js' | crontab -

# 확인
crontab -l
```

## 수동 실행 옵션

필요시 수동으로 즉시 실행:

```bash
# 일반 실행
node /Users/jin/classfy_scraper/health_check.js

# 로그 파일에 저장하며 실행
node /Users/jin/classfy_scraper/health_check.js >> /Users/jin/classfy_scraper/logs/health_check_manual.log 2>&1

# 백그라운드 실행
nohup node /Users/jin/classfy_scraper/health_check.js &
```

## 추가 개선 사항 (옵션)

### Slack/Email 알림 추가

오류가 발생한 사이트가 있을 때 알림을 받으려면:

1. `health_check.js`에 알림 로직 추가
2. 환경변수로 Slack Webhook URL 또는 Email 설정 추가
3. 오류 사이트 수가 임계값을 초과하면 알림 발송

### 성능 모니터링

응답 시간 추이를 모니터링하려면:

```sql
-- 최근 7일간 평균 응답 시간 추이
SELECT
  check_date,
  AVG(response_time) as avg_response_time,
  COUNT(*) as total_checks,
  SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) as success_count
FROM health_check_log
WHERE check_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
GROUP BY check_date
ORDER BY check_date DESC;
```

## 문의

문제가 발생하거나 개선 사항이 있으면 이슈를 등록하거나 담당자에게 문의하세요.
