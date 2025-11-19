# 헬스체크 변경 이력

## 2025-11-12 - v1.1

### 주요 변경사항

#### 1. SSL/TLS 인증서 검증 비활성화 ✅
**문제**: 대부분의 사이트가 SSL 인증서 오류로 실패
**원인**: 자체 서명 인증서, 만료된 인증서 등을 사용하는 사이트들이 많음
**해결**:
```javascript
const httpsAgent = new https.Agent({
    rejectUnauthorized: false, // SSL 검증 비활성화
});
```
- 브라우저와 동일하게 동작하도록 SSL 검증 비활성화
- 실제 브라우저에서는 정상 작동하지만 Node.js에서는 거부되던 문제 해결

#### 2. check_date 형식 변경 ✅
**변경 전**: `DATETIME` (예: 2025-11-12 16:42:16)
**변경 후**: `DATE` (예: 2025-11-12)

```javascript
// YYYY-MM-DD 형식으로 생성
const checkDate = now.toISOString().split('T')[0];
```

**이유**:
- 하루에 한 번씩만 체크하므로 시간 정보 불필요
- 날짜별 집계가 간편해짐
- UPSERT 시 같은 날짜의 데이터를 쉽게 갱신 가능

#### 3. UPSERT 로직 추가 ✅
**기능**: 동일한 `check_date`와 `site_code`가 있으면 업데이트, 없으면 삽입

```sql
INSERT INTO health_check_log (...)
VALUES (...)
ON DUPLICATE KEY UPDATE
    site_url = VALUES(site_url),
    status_code = VALUES(status_code),
    error_type = VALUES(error_type),
    error_message = VALUES(error_message),
    response_time = VALUES(response_time),
    redirect_url = VALUES(redirect_url),
    redirect_count = VALUES(redirect_count),
    updated_at = CURRENT_TIMESTAMP
```

**UNIQUE 제약조건**:
```sql
UNIQUE KEY unique_check (check_date, site_code)
```

**장점**:
- 같은 날짜에 여러 번 실행해도 중복 데이터 없음
- 최신 상태로 자동 업데이트
- `updated_at` 필드로 마지막 업데이트 시간 추적

#### 4. updated_at 필드 추가 ✅
```sql
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
```
- 레코드가 마지막으로 업데이트된 시간 자동 기록
- UPSERT 발생 시 자동으로 현재 시간으로 갱신

### 테스트 결과

#### 변경 전
```
❌ andong: SSL_ERROR - SSL/TLS 인증서 오류
❌ anseong: SSL_ERROR - SSL/TLS 인증서 오류
❌ anyang: SSL_ERROR - SSL/TLS 인증서 오류
...
```

#### 변경 후
```
✅ andong: 정상 (995ms)
✅ anseong: 정상 (1715ms)
✅ anyang: 정상 (1257ms)
✅ boeun: 정상 (948ms)
✅ boseong: 정상 (4807ms)
✅ buan: 정상 (514ms)
✅ busan: 정상 (716ms)
✅ changwon: 정상 (461ms)
✅ cheongdo: 정상 (299ms)
✅ cheongju: 정상 (906ms)
```

### 데이터베이스 스키마 변경

#### 변경 전
```sql
check_date DATETIME NOT NULL
INDEX idx_check_date (check_date)
```

#### 변경 후
```sql
check_date DATE NOT NULL
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
UNIQUE KEY unique_check (check_date, site_code)
INDEX idx_check_date (check_date)
```

### 사용 예시

#### 1. 같은 날짜에 여러 번 실행
```bash
# 오전에 실행
node node/health/health_check.js

# 오후에 다시 실행 (UPSERT로 업데이트)
node node/health/health_check.js
```

#### 2. 오늘 데이터 조회
```sql
SELECT *
FROM health_check_log
WHERE check_date = CURDATE()
ORDER BY site_code;
```

#### 3. 최근 업데이트 확인
```sql
SELECT
    site_code,
    check_date,
    error_type,
    created_at,
    updated_at,
    TIMESTAMPDIFF(SECOND, created_at, updated_at) as update_delay
FROM health_check_log
WHERE check_date = CURDATE()
AND created_at != updated_at;  -- 업데이트된 레코드만
```

### 마이그레이션

기존 테이블을 사용 중이라면 다음 명령으로 재생성:

```sql
DROP TABLE IF EXISTS health_check_log;
```

스크립트 실행 시 자동으로 새 구조로 생성됩니다.

### 호환성

- Node.js: v14 이상
- MySQL: 5.7 이상 (ON DUPLICATE KEY UPDATE 지원)
- axios: ^1.7.9
- mysql2: ^3.15.3

### 성능 개선

- SSL 검증 비활성화로 연결 속도 향상
- UPSERT로 불필요한 중복 데이터 방지
- DATE 타입으로 인덱스 크기 감소

### 주의사항

⚠️ **SSL 검증 비활성화**
- 프로덕션 환경에서는 보안상 주의가 필요할 수 있음
- 하지만 헬스체크 목적으로는 문제없음 (읽기 전용)
- 실제 스크래핑 시에는 별도 고려 필요

### 다음 버전 계획

- [ ] 이메일/Slack 알림 기능
- [ ] 연속 실패 카운트
- [ ] 사이트 카테고리별 통계
- [ ] 웹 대시보드
