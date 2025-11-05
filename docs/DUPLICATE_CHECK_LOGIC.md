# 중복 공고 체크 로직 분석 보고서

## 📋 실행 요약

**목적**: `announcement_pre_processor.py` 실행 시 url_key/url_key_hash 기반 중복 체크 로직이 의도대로 동작하는지 검증

**분석 일시**: 2025-10-30

**분석 대상**:
- `announcement_pre_processor.py` (line 1622-1994)
- 중복 체크 핵심 로직 (`_save_to_database_simple` 메서드)

---

## 🔍 중복 체크 로직 분석

### 1. 핵심 메커니즘

#### 1.1 UNIQUE 제약 조건
```sql
UNIQUE KEY uk_url_key_hash (url_key_hash)
```

**announcement_pre_processing 테이블**에 `url_key_hash` 컬럼에 UNIQUE 제약 조건이 설정되어 있습니다.

- **url_key**: 정규화된 URL (VARCHAR 500)
- **url_key_hash**: url_key의 MD5 해시 (CHAR 32)

#### 1.2 UPSERT 쿼리
```python
INSERT INTO announcement_pre_processing (...)
VALUES (...)
ON DUPLICATE KEY UPDATE
    site_type = IF(조건, VALUES(site_type), site_type),
    ...
```

**동작 방식**:
1. **INSERT 시도**: url_key_hash가 중복되지 않으면 새 레코드 삽입
   - `affected_rows = 1` 반환

2. **DUPLICATE KEY 감지**: url_key_hash가 이미 존재하면
   - `affected_rows = 2` 반환
   - ON DUPLICATE KEY UPDATE 절 실행
   - 우선순위에 따라 업데이트 또는 기존 데이터 유지

---

### 2. 중복 체크 세부 로직

#### 2.1 url_key 생성 (announcement_pre_processor.py:565-591)

```python
# 3.5. origin_url에서 url_key 추출 (URL 정규화)
url_key = None
if origin_url:
    try:
        # 1순위: domain_key_config에서 도메인 설정 조회
        url_key = self.url_key_extractor.extract_url_key(origin_url, site_code)
        if url_key:
            logger.debug(f"✓ URL 정규화 완료 (domain_key_config 사용)")
        else:
            # 2순위: 폴백 정규화 (쿼리 파라미터 정렬)
            logger.warning(f"⚠️  도메인 설정 없음, 폴백 정규화 수행")
            url_key = self._fallback_normalize_url(origin_url)
    except Exception as e:
        # 예외 발생 시에도 폴백 시도
        url_key = self._fallback_normalize_url(origin_url)
```

**url_key 생성 우선순위**:
1. **domain_key_config 사용** (DomainKeyExtractor)
   - domain_key_config 테이블에 도메인별 설정 조회
   - key_params에 정의된 파라미터만 추출
   - 알파벳 순 정렬하여 일관된 키 생성

2. **폴백 정규화** (_fallback_normalize_url)
   - domain_key_config 없는 경우
   - 쿼리 파라미터를 알파벳 순 정렬
   - page, pageIndex 등 페이지네이션 파라미터 제외

#### 2.2 중복 체크 분기 (announcement_pre_processor.py:1853-1970)

**케이스 1: domain_key_config 없는 경우** (line 1854-1879)
```python
if not domain_has_config:
    logger.info(f"domain_key_config 없음, 중복 체크 제외")

    if affected_rows == 1:
        processing_status = 'new_inserted'
    elif affected_rows == 2:
        processing_status = 'duplicate_skipped'
        duplicate_reason = {
            "reason": "domain_key_config 없음, 중복 감지했으나 제외됨",
            "domain": domain,
            "fallback_used": True
        }
```

**특징**:
- 중복 감지는 하지만 **우선순위 비교 안 함**
- `duplicate_skipped` 상태로 로그만 기록
- 데이터는 업데이트되지 않음 (기존 데이터 유지)

**케이스 2: domain_key_config 있는 경우** (line 1881-1946)
```python
elif affected_rows == 1:
    # 새로 INSERT됨
    processing_status = 'new_inserted'

elif affected_rows == 2:
    # UPDATE됨 (중복 감지)
    # UPSERT 전에 조회한 기존 레코드로 우선순위 비교
    if existing_record_before_upsert:
        existing_site_type = existing_record_before_upsert.site_type
        current_priority = self._get_priority(self.site_type)
        existing_priority = self._get_priority(existing_site_type)

        if current_priority > existing_priority:
            processing_status = 'duplicate_updated'  # 업데이트됨
        elif current_priority == existing_priority:
            processing_status = 'duplicate_updated'  # 최신 데이터 우선
        else:
            processing_status = 'duplicate_preserved'  # 기존 유지
```

**우선순위 정책** (_get_priority 메서드):
- Eminwon: 3
- Homepage: 2
- Scraper: 1
- API (kStartUp, bizInfo, smes24): 0

**케이스 3: url_key 없는 경우** (line 1823-1834)
```python
if not url_key:
    self._log_api_url_processing(
        processing_status='no_url_key',
        error_message="URL 정규화 실패 (url_key 없음)"
    )
```

---

### 3. 처리 상태 (processing_status)

| 상태 | 의미 | 발생 조건 |
|------|------|----------|
| `new_inserted` | 새로 삽입됨 | affected_rows=1 (중복 아님) |
| `duplicate_updated` | 중복이지만 업데이트됨 | affected_rows=2 + 우선순위 높음/동일 |
| `duplicate_preserved` | 중복이라 기존 유지 | affected_rows=2 + 우선순위 낮음 |
| `duplicate_skipped` | 중복 감지했으나 제외됨 | affected_rows=2 + domain_key_config 없음 |
| `no_url_key` | URL 정규화 실패 | url_key가 None |
| `failed` | 처리 실패 | 예상치 못한 affected_rows |

---

### 4. api_url_processing_log 기록

모든 처리 결과는 `api_url_processing_log` 테이블에 기록됩니다:

```python
self._log_api_url_processing(
    session=session,
    site_code=db_site_code,
    url_key=url_key,
    url_key_hash=url_key_hash,
    processing_status=processing_status,
    preprocessing_id=record_id,
    existing_preprocessing_id=existing_preprocessing_id,
    existing_site_type=existing_site_type,
    existing_site_code=existing_site_code,
    duplicate_reason=duplicate_reason,
    title=title,
    folder_name=folder_name
)
```

**기록 내용**:
- url_key, url_key_hash
- processing_status
- duplicate_reason (JSON)
- 기존 레코드 정보 (existing_preprocessing_id, existing_site_type 등)

---

## ✅ 의도대로 동작하는지 검증

### 1. 중복 체크 동작 여부

**예상 동작**:
1. ✅ url_key_hash UNIQUE 제약으로 중복 감지
2. ✅ affected_rows=2 시 UPSERT 실행
3. ✅ domain_key_config 유무에 따라 분기 처리

**검증 방법**:
```sql
-- 1. 중복 처리 로그 조회
SELECT processing_status, COUNT(*) as cnt
FROM api_url_processing_log
GROUP BY processing_status;

-- 예상 결과:
-- new_inserted: 신규 삽입 건수
-- duplicate_updated: 중복이지만 업데이트된 건수
-- duplicate_skipped: 폴백으로 중복 제외된 건수
-- duplicate_preserved: 우선순위 낮아 유지된 건수
-- no_url_key: URL 정규화 실패 건수
```

```sql
-- 2. url_key_hash 중복 확인
SELECT url_key_hash, COUNT(*) as cnt
FROM announcement_pre_processing
WHERE url_key_hash IS NOT NULL
GROUP BY url_key_hash
HAVING COUNT(*) > 1;

-- 예상 결과: 0건 (UNIQUE 제약으로 중복 불가)
```

### 2. domain_key_config 유무에 따른 분기

**domain_key_config 있는 경우**:
- ✅ 중복 체크 활성화
- ✅ 우선순위 비교 수행
- ✅ duplicate_updated / duplicate_preserved 상태

**domain_key_config 없는 경우**:
- ✅ 중복 감지는 하지만 우선순위 비교 안 함
- ✅ duplicate_skipped 상태
- ✅ duplicate_reason에 `"fallback_used": true` 표시

**검증 방법**:
```sql
-- 폴백 사용 로그 조회
SELECT *
FROM api_url_processing_log
WHERE processing_status = 'duplicate_skipped'
AND duplicate_reason LIKE '%fallback_used%'
LIMIT 10;
```

### 3. 우선순위 정책

**우선순위**: Eminwon (3) > Homepage (2) > Scraper (1) > API (0)

**예상 동작**:
- API 공고 후 Eminwon 공고 수집 → **업데이트** (duplicate_updated)
- Eminwon 공고 후 API 공고 수집 → **기존 유지** (duplicate_preserved)

**검증 방법**:
```sql
-- 우선순위에 따른 처리 로그
SELECT
    processing_status,
    existing_site_type,
    site_code,
    duplicate_reason,
    COUNT(*) as cnt
FROM api_url_processing_log
WHERE processing_status IN ('duplicate_updated', 'duplicate_preserved')
GROUP BY processing_status, existing_site_type, site_code;
```

---

## ⚠️ 고려사항 및 잠재적 이슈

### 1. domain_key_config 없는 도메인의 실제 중복

**현상**:
- domain_key_config 없는 도메인에서 동일 공고가 여러 번 수집되어도
- url_key_hash UNIQUE 제약으로 INSERT 실패
- affected_rows=2 (UPDATE 실행)
- `duplicate_skipped` 상태로 처리
- **로그만 기록, 데이터는 업데이트 안 됨**

**영향**:
- 실제 중복 공고가 있어도 데이터가 갱신되지 않음
- 공고 내용이 변경되어도 반영 안 될 수 있음

**예시**:
```
1차 수집: www.example.com/notice?id=123 → url_key_hash=abc123 → INSERT
2차 수집: www.example.com/notice?id=123 (내용 변경됨)
  → url_key_hash=abc123 (동일)
  → affected_rows=2
  → domain_key_config 없음
  → duplicate_skipped
  → 기존 데이터 유지 (변경 내용 반영 안 됨)
```

**개선 방안**:
1. domain_key_config 없는 도메인도 우선순위 비교 수행
2. 또는 최신 데이터로 항상 업데이트 (updated_at 기준)
3. 또는 중복 체크 완전 제외 (url_key_hash UNIQUE 제거)

### 2. url_key_hash UNIQUE 제약과 폴백의 충돌

**문제**:
- `url_key_hash UNIQUE` 제약은 DB 레벨에서 항상 강제
- 하지만 코드 레벨에서는 domain_key_config 없으면 중복 체크 제외
- **모순**: DB는 중복 허용 안 하지만, 코드는 중복 체크 안 함

**결과**:
- affected_rows=2 반환되지만 우선순위 비교 안 함
- 로그에만 기록, 실제 데이터는 조건부 업데이트

**개선 방안**:
1. domain_key_config 없는 도메인은 url_key_hash를 NULL로 설정
2. 또는 url_key_hash 대신 url_key에만 INDEX 설정 (UNIQUE 제거)
3. 또는 domain_key_config 없는 도메인도 정상 중복 체크 수행

### 3. UPSERT 전 기존 레코드 조회

**현재 로직** (line 1637-1647):
```python
if force and url_key:
    existing_record_before_upsert = session.execute(
        text("SELECT id, site_type, site_code FROM announcement_pre_processing WHERE url_key = :url_key"),
        {"url_key": url_key}
    ).fetchone()
```

**문제**:
- `force=True`일 때만 기존 레코드 조회
- `force=False`이면 조회 안 함 → 우선순위 비교 불가
- 하지만 UPSERT는 force 관계없이 항상 실행

**영향**:
- force=False 시 existing_site_type 정보 없음
- line 1942-1945: "UPSERT 전 기존 레코드 조회 실패" 처리
- duplicate_updated로 간주 (우선순위 비교 없이)

**개선 방안**:
```python
# force 관계없이 항상 조회
if url_key:
    existing_record_before_upsert = session.execute(...)
```

### 4. folder_name 중복 체크와 url_key 중복 체크의 이중화

**현재**:
1. **folder_name 중복 체크** (line 446-448)
   - force=False 시 folder_name 중복되면 건너뜀
   - UNIQUE KEY on folder_name

2. **url_key_hash 중복 체크** (line 1853-1970)
   - UPSERT 시 url_key_hash 중복되면 우선순위 비교
   - UNIQUE KEY on url_key_hash

**문제**:
- 같은 공고를 다른 폴더명으로 두 번 수집하면?
  - folder_name 다름 → 첫 번째 체크 통과
  - url_key_hash 같음 → UPSERT 실행
  - 중복 처리됨 (정상)

- 하지만 folder_name UNIQUE도 있어서 같은 폴더 두 번 처리 불가

**개선 방안**:
- folder_name은 처리 이력 관리용
- url_key_hash는 실제 중복 감지용
- **현재 설계는 정상적으로 보임**

### 5. api_url_registry 업데이트 타이밍

**현재** (line 1973-1984):
```python
# API 사이트인 경우 api_url_registry 테이블 업데이트 (commit 전에 실행)
if origin_url:
    api_registry_updated = self._update_api_url_registry(
        session, origin_url, record_id, db_site_code, scraping_url
    )
```

**문제**:
- api_url_registry 업데이트는 중복 여부와 무관하게 실행
- 중복으로 기존 데이터 유지되어도 api_url_registry는 업데이트

**영향**:
- 일관성 문제는 없으나, 불필요한 업데이트 발생 가능

**개선 방안**:
```python
# duplicate_updated일 때만 api_url_registry 업데이트
if processing_status == 'duplicate_updated' and origin_url:
    api_registry_updated = self._update_api_url_registry(...)
```

### 6. 페이지네이션 파라미터 제외

**폴백 정규화** (_fallback_normalize_url, line 1207-1250):
```python
# 페이지네이션/검색 파라미터 제외
exclude_params = {
    'page', 'pageIndex', 'pageNo', 'pageSize', 'pageNum',
    'currentPage', 'searchCnd', 'searchWrd', 'srchWrd'
}
```

**문제**:
- 모든 도메인에 동일한 제외 파라미터 적용
- 일부 사이트는 page 파라미터가 게시글 ID일 수 있음
- 잘못된 제외로 다른 공고가 중복으로 판정될 수 있음

**예시**:
```
www.example.com/notice?page=123  # page=게시글ID
www.example.com/notice?page=456  # page=게시글ID

→ 두 공고 모두 url_key = "www.example.com|/notice|" (page 제외됨)
→ 중복으로 판정됨 (실제로는 다른 공고)
```

**개선 방안**:
- domain_key_config에 exclude_params 설정 추가
- 또는 폴백 로직에서 더 정교한 파라미터 분석

---

## 📊 테스트 스크립트

작성된 테스트 스크립트: `test_duplicate_check_url_key.py`

### 테스트 케이스

1. **domain_key_config 존재 - 중복 체크 활성화**
   - k-startup.go.kr 등 API 사이트
   - 중복 처리 로그 확인
   - 우선순위 비교 동작 확인

2. **domain_key_config 없음 - 중복 체크 제외 (폴백)**
   - 폴백 로직 사용 확인
   - duplicate_skipped 상태 확인
   - duplicate_reason에 fallback_used 표시 확인

3. **url_key 없음 - no_url_key 상태**
   - url_key NULL 레코드 조회
   - no_url_key 처리 로그 확인

4. **전체 통계**
   - processing_status별 건수
   - 중복 처리 비율
   - url_key 존재 여부 통계

### 실행 방법

```bash
# MySQL 서버 시작 필요
python3 test_duplicate_check_url_key.py
```

**결과 파일**: `test_duplicate_check_results.json`

---

## 🎯 결론

### 의도대로 동작하는 부분

1. ✅ **url_key_hash UNIQUE 제약**으로 중복 감지 정상 동작
2. ✅ **UPSERT 로직**으로 affected_rows=2 시 중복 처리
3. ✅ **domain_key_config 유무**에 따른 분기 처리
4. ✅ **우선순위 정책** 적용 (Eminwon > Homepage > Scraper > API)
5. ✅ **api_url_processing_log** 모든 처리 기록

### 잠재적 문제점

1. ⚠️ **domain_key_config 없는 도메인의 실제 중복**
   - 중복 감지는 하지만 데이터 업데이트 안 됨
   - 공고 변경 사항 반영 안 될 수 있음

2. ⚠️ **force=False 시 우선순위 비교 불가**
   - existing_record 조회 안 함
   - duplicate_updated로 간주

3. ⚠️ **페이지네이션 파라미터 제외**
   - 일부 사이트에서 오탐 가능성

### 권장 사항

1. **domain_key_config 없는 도메인 처리 개선**
   ```python
   # 옵션 1: 최신 데이터로 항상 업데이트
   if not domain_has_config and affected_rows == 2:
       processing_status = 'duplicate_updated'

   # 옵션 2: url_key_hash를 NULL로 설정 (중복 체크 완전 제외)
   if not domain_has_config:
       url_key_hash = None
   ```

2. **force 관계없이 기존 레코드 조회**
   ```python
   # force=False여도 우선순위 비교를 위해 조회
   if url_key and affected_rows == 2:
       existing_record_before_upsert = session.execute(...)
   ```

3. **도메인별 exclude_params 설정**
   - domain_key_config에 exclude_params 컬럼 추가
   - 또는 폴백 로직에서 더 정교한 파라미터 분석

---

## 📝 추가 검증 필요 사항

DB 서버 접속 후 다음 쿼리로 실제 동작 확인:

```sql
-- 1. 처리 상태별 통계
SELECT processing_status, COUNT(*) as cnt
FROM api_url_processing_log
GROUP BY processing_status
ORDER BY cnt DESC;

-- 2. 중복 처리 상세 (샘플 10건)
SELECT
    url_key_hash,
    site_code,
    processing_status,
    existing_site_type,
    duplicate_reason,
    created_at
FROM api_url_processing_log
WHERE processing_status LIKE 'duplicate%'
ORDER BY created_at DESC
LIMIT 10;

-- 3. 폴백 사용 로그
SELECT COUNT(*) as cnt
FROM api_url_processing_log
WHERE duplicate_reason LIKE '%fallback_used%';

-- 4. url_key_hash 중복 확인 (0건이어야 정상)
SELECT url_key_hash, COUNT(*) as cnt
FROM announcement_pre_processing
WHERE url_key_hash IS NOT NULL
GROUP BY url_key_hash
HAVING COUNT(*) > 1;

-- 5. url_key 없는 레코드
SELECT COUNT(*) as cnt
FROM announcement_pre_processing
WHERE url_key IS NULL;
```

---

**작성일**: 2025-10-30
**작성자**: Claude Code Assistant
**분석 대상 파일**: announcement_pre_processor.py (line 1622-1994)
