# Step 9: 모니터링 쿼리 설정 완료

**작성일**: 2025-11-22
**목적**: URL 중복 제거 시스템의 지속적인 정상 동작 모니터링
**상태**: ✅ 완료

---

## 📋 작업 요약

URL 중복 제거 시스템(UNIQUE 제약, url_key 기반 중복 방지)이 정상적으로 작동하는지 지속적으로 모니터링할 수 있는 도구를 생성했습니다.

### 생성된 파일

| 파일명 | 유형 | 목적 |
|--------|------|------|
| `monitoring_url_dedup.sql` | MySQL 쿼리 | 9개 섹션의 상세 모니터링 쿼리 |
| `monitoring_url_dedup.py` | Python 스크립트 | 자동 모니터링 및 이상 징후 알림 |
| `setup_monitoring_cron.sh` | Bash 스크립트 | 크론 작업 자동 설정 |

---

## 🔍 모니터링 항목

### 1. 일일 중복 타입 분포 (최근 24시간)

**목적**: 중복 처리 로직이 정상 작동하는지 확인

**정상 기대값**:
- `new_inserted`: 신규 데이터 (사이트마다 다름)
- `replaced`: 우선순위 높은 수집으로 교체
- `same_type_duplicate`: 같은 우선순위 중복 (많으면 비정상)
- `kept_existing`: 우선순위 낮아서 유지
- `unknown`: **0건이어야 정상** (있으면 로직 오류)

**쿼리**:
```sql
SELECT
    duplicate_type AS 중복타입,
    COUNT(*) AS 건수,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS 비율_퍼센트
FROM announcement_duplicate_log
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY duplicate_type
ORDER BY 건수 DESC;
```

---

### 2. UNIQUE 제약 동작 검증

**목적**: `uq_url_key_hash` UNIQUE 제약이 정상 작동하는지 확인

**정상 기대값**: 모든 검사 항목이 0건

#### 2-1. url_key_hash 중복 검사

**쿼리**:
```sql
SELECT COUNT(*) AS 중복건수
FROM (
    SELECT url_key_hash
    FROM announcement_pre_processing
    WHERE url_key_hash IS NOT NULL
    GROUP BY url_key_hash
    HAVING COUNT(*) > 1
) dup;
```

**이상 징후**: 중복건수 > 0 → UNIQUE 제약 위반!

---

#### 2-2. GENERATED COLUMN 정상 동작 확인

**쿼리**:
```sql
SELECT COUNT(*) AS 비정상건수
FROM announcement_pre_processing
WHERE url_key IS NOT NULL AND url_key_hash IS NULL;
```

**이상 징후**: 비정상건수 > 0 → GENERATED COLUMN 오류!

---

#### 2-3. 중복 처리 비율

**쿼리**:
```sql
SELECT
    SUM(CASE WHEN duplicate_type IN ('replaced', 'same_type_duplicate') THEN 1 ELSE 0 END) AS 중복처리건수,
    COUNT(*) AS 전체건수,
    ROUND(SUM(...) * 100.0 / COUNT(*), 2) AS 중복처리비율_퍼센트
FROM announcement_duplicate_log
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR);
```

**판단 기준**:
- > 50%: 중복 수집 많음 (수집 소스 점검 필요)
- 20-50%: 정상 범위
- < 20%: 신규 데이터 많음 (정상)

---

### 3. 주간 처리 상태 트렌드 (최근 7일)

**목적**: 수집 효율성 및 제외 비율 추이 확인

**쿼리**:
```sql
SELECT
    DATE(created_at) AS 날짜,
    COUNT(*) AS 전체건수,
    SUM(CASE WHEN processing_status = '성공' THEN 1 ELSE 0 END) AS 성공,
    SUM(CASE WHEN processing_status = '제외' THEN 1 ELSE 0 END) AS 제외,
    ROUND(SUM(...) * 100.0 / COUNT(*), 2) AS 성공률_퍼센트,
    ROUND(SUM(...) * 100.0 / COUNT(*), 2) AS 제외율_퍼센트
FROM announcement_pre_processing
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY DATE(created_at)
ORDER BY 날짜 DESC;
```

**트렌드 분석**:
- 성공률 지속 하락 → 제외 키워드 재검토 필요
- 제외율 > 80% 지속 → 수집 효율성 문제

---

### 4. 사이트별 수집 효율성 (최근 7일)

**목적**: 비효율적인 사이트 식별

**쿼리**:
```sql
SELECT
    site_code AS 사이트코드,
    COUNT(*) AS 전체건수,
    SUM(CASE WHEN processing_status = '성공' THEN 1 ELSE 0 END) AS 성공,
    ROUND(SUM(...) * 100.0 / COUNT(*), 2) AS 성공률_퍼센트,
    CASE
        WHEN SUM(...) >= 50 THEN '🟢 우수'
        WHEN SUM(...) >= 20 THEN '🟡 보통'
        WHEN SUM(...) >= 5 THEN '🟠 낮음'
        ELSE '🔴 매우 낮음 (점검 필요)'
    END AS 효율성등급
FROM announcement_pre_processing
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY site_code
HAVING COUNT(*) >= 10
ORDER BY 성공률_퍼센트 DESC
LIMIT 30;
```

**조치 기준**:
- 🔴 매우 낮음 (< 5%): 수집 중단 검토
- 🟠 낮음 (5-20%): 제외 키워드 조정 필요

---

### 5. NULL url_key 모니터링

**목적**: url_key가 NULL인 레코드 추적 (domain_key_config 설정 문제 감지)

**쿼리**:
```sql
SELECT
    site_code AS 사이트코드,
    COUNT(*) AS NULL건수,
    MIN(created_at) AS 최초발생시각,
    MAX(created_at) AS 최근발생시각,
    CASE
        WHEN MAX(created_at) >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            THEN '🔴 최근 발생 (domain_key_config 점검 필요)'
        WHEN MAX(created_at) >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            THEN '🟡 1주일 내 발생'
        ELSE '🟢 과거 데이터 (정상)'
    END AS 상태
FROM announcement_pre_processing
WHERE url_key IS NULL
GROUP BY site_code
ORDER BY MAX(created_at) DESC, NULL건수 DESC;
```

**조치 기준**:
- 🔴 최근 발생: domain_key_config 설정 확인 필수
- 🟡 1주일 내: 모니터링 강화

---

### 6. unknown duplicate_type 추적

**목적**: unknown이 새로 발생하는지 모니터링 (발생하면 로직 오류)

#### 6-1. 최근 7일 unknown 발생

**쿼리**:
```sql
SELECT COUNT(*) AS 건수
FROM announcement_duplicate_log
WHERE duplicate_type = 'unknown'
AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY);
```

**판단**:
- 건수 = 0: ✅ 정상
- 건수 > 0: ❌ announcement_pre_processor.py 로직 점검 필요

---

#### 6-2. 전체 unknown 통계

**쿼리**:
```sql
SELECT
    COUNT(*) AS 총_unknown건수,
    MIN(created_at) AS 최초발생,
    MAX(created_at) AS 최근발생
FROM announcement_duplicate_log
WHERE duplicate_type = 'unknown';
```

**판단**:
- MAX(created_at) < 2025-11-04: ✅ UNIQUE 제약 추가 전 히스토리 (정상)
- MAX(created_at) >= 2025-11-04: ❌ 최근 발생 (로직 점검 필요)

---

### 7. domain_key_config 활성화 상태 점검

**목적**: 모든 도메인이 정상적으로 설정되어 있는지 확인

**쿼리**:
```sql
SELECT
    domain AS 도메인,
    extraction_method AS 추출방식,
    key_params AS 키파라미터,
    path_pattern AS 경로패턴,
    is_active AS 활성화
FROM domain_key_config
ORDER BY is_active DESC, domain;
```

**확인 사항**:
- is_active = 0인 도메인이 의도적 비활성화인지 확인

---

### 8. 백업 테이블 용량 모니터링

**목적**: 불필요한 백업 테이블 디스크 공간 확인

**쿼리**:
```sql
SELECT
    TABLE_NAME AS 테이블명,
    ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024 / 1024, 2) AS 용량_GB,
    TABLE_ROWS AS 예상행수,
    CREATE_TIME AS 생성일
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'subvention'
AND TABLE_NAME LIKE '%backup%'
ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC;
```

**조치 기준**:
- > 1.0 GB: 압축/삭제 검토
- > 0.5 GB: 모니터링

---

### 9. 일일 요약 리포트

**목적**: 한눈에 보는 시스템 상태

**주요 지표**:
- 전체 레코드 수
- url_key 생성률
- 최근 24시간 수집 건수
- 최근 24시간 성공률
- 최근 24시간 제외율
- unknown 발생 여부
- url_key_hash 중복 여부

---

## 🐍 Python 모니터링 스크립트

### 사용법

#### 1. 전체 리포트 (상세)

```bash
python3 monitoring_url_dedup.py
```

**출력 내용**:
- 중요 검사 항목
- 일일 요약
- 이상 징후
- 중복 타입 분포
- TOP 5 비효율적 사이트
- TOP 5 효율적 사이트

---

#### 2. 빠른 요약 (핵심만)

```bash
python3 monitoring_url_dedup.py --quick
```

**출력 내용**:
- 중요 검사 항목 (url_key_hash 중복, unknown 발생 등)
- 일일 요약 (전체 레코드, 최근 24시간 통계)
- 이상 징후 목록

**예시 출력**:
```
================================================================================
URL 중복 제거 모니터링 요약 리포트 - 2025-11-22 13:02:49
================================================================================

🔍 중요 검사 항목:
  - url_key_hash 중복: 0건 ✅
  - url_key 있지만 hash NULL: 0건 ✅
  - 최근 7일 unknown 발생: 0건 ✅
  - 최근 24시간 NULL url_key: 194건 ⚠️

📊 일일 요약:
  - 전체 레코드: 42,827건
  - url_key 생성률: 95.61%
  - 최근 24시간 수집: 3,018건
    • 성공: 304건 (10.07%)
    • 제외: 2,713건 (89.89%)
    • archived: 0건
    • error: 1건

🚨 이상 징후:
  [WARNING] ⚠️  최근 24시간 NULL url_key 발생: 총 194건 (prv_icbp(99건), prv_seoul(41건), prv_haenam(9건)...)
```

---

#### 3. 이상 징후만 (크론 알림용)

```bash
python3 monitoring_url_dedup.py --alert
```

**동작**:
- 이상 징후 있으면: 알림 출력 + exit code 1
- 정상이면: "정상" 메시지 + exit code 0

**크론에서 사용 시 장점**:
- 정상일 때는 로그가 짧음 (디스크 절약)
- 이상 시에만 상세 내역 기록
- exit code로 알림 시스템 연동 가능

---

### 이상 징후 감지 기준

| 검사 항목 | 정상 | 경고 (WARNING) | 심각 (CRITICAL) |
|-----------|------|----------------|-----------------|
| url_key_hash 중복 | 0건 | - | > 0건 (UNIQUE 제약 위반) |
| url_key 있지만 hash NULL | 0건 | - | > 0건 (GENERATED COLUMN 오류) |
| 최근 7일 unknown 발생 | 0건 | - | > 0건 (로직 오류) |
| 최근 24시간 NULL url_key | 0건 | > 0건 (domain_key_config 점검) | - |
| 제외율 | < 60% | 60-80% | > 80% (매우 비효율) |
| 성공률 | > 15% | 5-15% | < 5% (매우 낮음) |

---

## ⏰ 크론 작업 설정

### 자동 설정 스크립트

```bash
bash setup_monitoring_cron.sh
```

**실행 결과**:
1. 크론 설정 내용 미리보기
2. 사용자 확인 (y/n)
3. 기존 크론 백업
4. 새 크론 작업 추가
5. 로그 디렉토리 생성

---

### 추가되는 크론 작업

#### 1. 매일 오전 9시 - 전체 리포트

```cron
0 9 * * * cd /mnt/d/workspace/sources/classfy_scraper && python3 monitoring_url_dedup.py >> logs/url_dedup_monitor_daily.log 2>&1
```

**출력**: 전체 상세 리포트

---

#### 2. 매일 오전 9시 10분 - 이상 징후 알림

```cron
10 9 * * * cd /mnt/d/workspace/sources/classfy_scraper && python3 monitoring_url_dedup.py --alert >> logs/url_dedup_alerts.log 2>&1
```

**출력**: 이상 징후 있을 때만 기록

---

#### 3. 매시간 정각 - 빠른 요약 체크

```cron
0 */1 * * * cd /mnt/d/workspace/sources/classfy_scraper && python3 monitoring_url_dedup.py --quick >> logs/url_dedup_hourly.log 2>&1
```

**출력**: 핵심 지표만

---

#### 4. 매주 월요일 오전 9시 30분 - MySQL 상세 쿼리

```cron
30 9 * * 1 cd /mnt/d/workspace/sources/classfy_scraper && mysql -h 192.168.0.95 -P 3309 -u root -pb3UvSDS232GbdZ42 subvention < monitoring_url_dedup.sql >> logs/url_dedup_weekly.log 2>&1
```

**출력**: 9개 섹션 전체 쿼리 결과

---

### 로그 파일 위치

| 로그 파일 | 생성 주기 | 내용 |
|----------|----------|------|
| `logs/url_dedup_monitor_daily.log` | 매일 오전 9시 | 전체 상세 리포트 |
| `logs/url_dedup_alerts.log` | 매일 오전 9시 10분 | 이상 징후 (있을 때만) |
| `logs/url_dedup_hourly.log` | 매시간 | 빠른 요약 |
| `logs/url_dedup_weekly.log` | 매주 월요일 | MySQL 상세 쿼리 결과 |

---

## ✅ 실행 결과 (2025-11-22 테스트)

### 현재 시스템 상태

```
🔍 중요 검사 항목:
  - url_key_hash 중복: 0건 ✅
  - url_key 있지만 hash NULL: 0건 ✅
  - 최근 7일 unknown 발생: 0건 ✅
  - 최근 24시간 NULL url_key: 194건 ⚠️

📊 일일 요약:
  - 전체 레코드: 42,827건
  - url_key 생성률: 95.61%
  - 최근 24시간 수집: 3,018건
    • 성공: 304건 (10.07%)
    • 제외: 2,713건 (89.89%)
```

### 해석

**정상 항목** ✅:
- url_key_hash 중복 없음 → UNIQUE 제약 정상 작동
- GENERATED COLUMN 정상 동작
- unknown duplicate_type 신규 발생 없음 → 로직 정상

**주의 필요** ⚠️:
- NULL url_key 194건 발생 (prv_icbp, prv_seoul, prv_haenam)
  - **원인**: domain_key_config 설정과 실제 URL 형식 불일치
  - **조치**:
    - prv_icbp: URL 수집 오류 (사용자 명시, 현상 유지)
    - prv_seoul: 일부 URL이 다른 형식 (추가 조사 필요)
    - prv_haenam: URL 수집 오류 (사용자 명시, 현상 유지)

- 제외율 89.89% (매우 높음)
  - **원인**: 제외 키워드가 너무 광범위
  - **조치**: Step 8 권장사항 참고하여 제외 키워드 재검토

---

## 📊 모니터링 대시보드 (권장)

### 매일 확인할 핵심 지표

```bash
python3 monitoring_url_dedup.py --quick
```

**체크리스트**:
- [ ] url_key_hash 중복 = 0건
- [ ] unknown 발생 = 0건
- [ ] GENERATED COLUMN 정상
- [ ] 성공률 > 10%
- [ ] 제외율 < 85%

---

### 매주 확인할 상세 지표

```bash
python3 monitoring_url_dedup.py
```

**체크리스트**:
- [ ] 주간 트렌드 (성공률 하락 여부)
- [ ] 비효율적 사이트 (제외율 > 95%)
- [ ] NULL url_key 신규 발생 사이트
- [ ] 백업 테이블 용량 (> 1GB)

---

### 매주 월요일 확인할 MySQL 상세 쿼리

```bash
mysql -h 192.168.0.95 -P 3309 -u root -pb3UvSDS232GbdZ42 subvention < monitoring_url_dedup.sql
```

**체크리스트**:
- [ ] domain_key_config 활성화 상태
- [ ] 사이트별 효율성 등급
- [ ] 백업 테이블 정리 필요 여부

---

## 🔔 이상 징후 발생 시 조치 방법

### 1. url_key_hash 중복 발견

**증상**:
```
❌ UNIQUE 제약 위반! url_key_hash 중복 5건 발견
```

**원인**:
- UNIQUE 제약이 손상됨
- 직접 SQL UPDATE로 중복 생성됨

**조치**:
```sql
-- 1. 중복 레코드 조회
SELECT url_key_hash, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
FROM announcement_pre_processing
WHERE url_key_hash IS NOT NULL
GROUP BY url_key_hash
HAVING cnt > 1;

-- 2. 수동으로 중복 제거 (최신 레코드만 유지)
-- (개별 케이스 검토 필요)
```

---

### 2. unknown duplicate_type 신규 발생

**증상**:
```
❌ unknown duplicate_type 최근 발생! 10건 (로직 점검 필요)
```

**원인**:
- announcement_pre_processor.py의 duplicate_type_map 로직 오류
- affected_rows가 예상치 못한 값 (0, 3 등)

**조치**:
1. announcement_pre_processor.py 라인 2555-2593 로직 점검
2. affected_rows 값 로그 확인
3. duplicate_type_map에 새로운 케이스 추가 필요 여부 검토

---

### 3. NULL url_key 최근 발생

**증상**:
```
⚠️  최근 24시간 NULL url_key 발생: 총 50건 (prv_xxx(50건))
```

**원인**:
- domain_key_config 설정과 실제 URL 형식 불일치
- 새로운 URL 패턴 발견

**조치**:
```bash
# 1. NULL url_key URL 조회
mysql -h ... -e "
SELECT origin_url
FROM announcement_pre_processing
WHERE site_code = 'prv_xxx'
AND url_key IS NULL
ORDER BY created_at DESC
LIMIT 10;
"

# 2. domain_key_config 확인
mysql -h ... -e "
SELECT *
FROM domain_key_config
WHERE domain = 'www.xxx.go.kr';
"

# 3. 필요 시 domain_key_config 수정 후 재생성
python3 regenerate_null_url_keys.py
```

---

### 4. 제외율 > 80%

**증상**:
```
⚠️  제외율 매우 높음: 89.00% (효율성 점검 필요)
```

**원인**:
- 제외 키워드가 너무 광범위
- 특정 사이트에서 대량의 무관한 공고 수집

**조치**:
- Step 8 권장사항 참고
- 제외 키워드 재검토
- 비효율적 사이트 수집 중단 검토

---

## 📝 다음 단계 권장사항

### 우선순위 1: 이상 징후 대응

- [ ] NULL url_key 발생 사이트 조사 (prv_icbp, prv_seoul, prv_haenam)
  - prv_icbp, prv_haenam: 사용자 명시로 현상 유지
  - prv_seoul: 추가 URL 패턴 분석 필요

### 우선순위 2: 효율성 개선

- [ ] Step 8 권장사항 실행
  - 제외 키워드 재검토
  - 비효율적 사이트 수집 중단 (yangcheon, icbp 등)
  - 고효율 사이트 수집 빈도 증가 (smes24, kStartUp 등)

### 우선순위 3: 백업 정리

- [ ] Step 7 실행
  - announcement_pre_processing_backup_20251121 (1.7GB) 압축 및 아카이브

---

## ✅ Step 9 완료 체크리스트

- [x] monitoring_url_dedup.sql 생성 (9개 섹션)
- [x] monitoring_url_dedup.py 생성 (3가지 모드)
- [x] setup_monitoring_cron.sh 생성
- [x] Python 스크립트 테스트 실행
- [x] 현재 시스템 상태 확인
- [x] 이상 징후 분석
- [x] 조치 방법 문서화
- [x] 크론 작업 설정 방법 제공

---

## 📚 참고 문서

- `URL_KEY_HASH_UNIQUE_INDEX_RECOMMENDATIONS.md`: 전체 9단계 계획
- `REGENERATE_SCRIPTS_DUPLICATE_CHECK_FIX.md`: 재생성 스크립트 중복 체크 로직
- `STEP2_NULL_URL_KEY_REGENERATION_REPORT.md`: NULL url_key 재생성 보고서
- `STEP3_DAEGU_FORMAT_UNIFICATION_REPORT.md`: prv_daegu 형식 통일 보고서
- `STEP8_COLLECTION_EFFICIENCY_REPORT.md`: 수집 효율성 분석

---

**작성자**: Claude Code
**완료일**: 2025-11-22 13:00 KST
