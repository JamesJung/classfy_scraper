# api_url_processing_log와 api_url_registry 매핑 분석

## 📋 현재 매핑 방식

### 1. 테이블 구조

#### api_url_registry (원본 데이터)
```sql
CREATE TABLE api_url_registry (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,              -- PK (자동 증가)
    site_code VARCHAR(50) NOT NULL,
    announcement_url VARCHAR(1000),
    scrap_url VARCHAR(1000),
    url_key VARCHAR(500),
    url_key_hash CHAR(32) GENERATED AS (md5(url_key)), -- 자동 생성
    preprocessing_id INT,                               -- announcement_pre_processing FK
    ...
    UNIQUE KEY unique_site_announcement (site_code, announcement_id)
);
```

#### api_url_processing_log (처리 로그)
```sql
CREATE TABLE api_url_processing_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,               -- PK (자동 증가)
    api_url_registry_id BIGINT NOT NULL,                -- api_url_registry FK ⭐
    processing_status ENUM(...),
    existing_preprocessing_id INT,
    ...
    CONSTRAINT fk_processing_log_registry
        FOREIGN KEY (api_url_registry_id)
        REFERENCES api_url_registry(id)
        ON DELETE CASCADE
);
```

### 2. 매핑 관계

```
api_url_registry (1) ←─── (N) api_url_processing_log
    ↓
    id ────────────────→ api_url_registry_id
```

**매핑 키:** `api_url_registry_id` → `api_url_registry.id` (FK)

---

## 🔍 현재 매핑 프로세스

### Step 1: announcement_pre_processing 저장
```python
# Lines 1863-2044: UPSERT 로직
if not existing:
    INSERT INTO announcement_pre_processing ...
    record_id = result.lastrowid  # preprocessing_id
else:
    UPDATE announcement_pre_processing ...
    record_id = existing_id
```

### Step 2: api_url_registry 업데이트 및 ID 획득
```python
# Lines 2176-2179: api_url_registry 업데이트
api_registry_updated, api_url_registry_id = self._update_api_url_registry(
    session, origin_url, record_id, db_site_code, scraping_url,
    url_key_hash=url_key_hash
)
```

**_update_api_url_registry 함수 로직 (Lines 1332-1503):**
```python
def _update_api_url_registry(...) -> tuple[bool, int]:
    # 1. url_key_hash로 매칭 (우선순위 0)
    if url_key_hash:
        UPDATE api_url_registry
        SET preprocessing_id = :preprocessing_id
        WHERE url_key_hash = :url_key_hash
        LIMIT 1

        if rows_affected > 0:
            # 업데이트된 레코드의 ID 조회
            SELECT id FROM api_url_registry
            WHERE url_key_hash = :url_key_hash
            LIMIT 1

            return True, registry_id  # ⭐ api_url_registry.id 반환

    # 2. 사이트별 URL 매칭 (폴백)
    if site_code == "kStartUp":
        WHERE scrap_url = :scraping_url
    else:  # bizInfo, smes24
        WHERE announcement_url = :origin_url

    return True, registry_id  # ⭐ api_url_registry.id 반환
```

### Step 3: api_url_processing_log에 로그 기록
```python
# Lines 2190-2206: 로그 기록
self._log_api_url_processing(
    session=session,
    ...
    preprocessing_id=record_id,
    api_url_registry_id=api_url_registry_id,  # ⭐ api_url_registry.id 전달
    ...
)
```

**_log_api_url_processing 함수 (Lines 1569-1667):**
```python
def _log_api_url_processing(
    self,
    session,
    ...
    api_url_registry_id: int = None,  # ⭐
    ...
):
    INSERT INTO api_url_processing_log (
        ...
        api_url_registry_id,  # ⭐ FK
        ...
    ) VALUES (
        ...
        :api_url_registry_id,  # ⭐
        ...
    )
```

---

## 📊 데이터 흐름도

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. API 스크래핑 (bizInfo, kStartUp, smes24)                     │
│    - api_url_registry에 INSERT                                  │
│    - id: 자동 증가 (예: 1876)                                   │
│    - preprocessing_id: NULL (아직 처리 안됨)                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. announcement_pre_processor 실행                              │
│    - announcement_pre_processing에 UPSERT                       │
│    - record_id: 183184 (예시)                                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. api_url_registry 업데이트                                    │
│    UPDATE api_url_registry                                      │
│    SET preprocessing_id = 183184                                │
│    WHERE url_key_hash = 'abc123...'                             │
│                                                                 │
│    SELECT id FROM api_url_registry                              │
│    WHERE url_key_hash = 'abc123...'                             │
│    → registry_id = 1876 ⭐                                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. api_url_processing_log에 로그 기록                           │
│    INSERT INTO api_url_processing_log (                         │
│        api_url_registry_id = 1876,  ← api_url_registry.id ⭐   │
│        processing_status = 'new_inserted',                      │
│        existing_preprocessing_id = NULL,                        │
│        ...                                                      │
│    )                                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 질문 분석: "api_url_registry의 id를 같게 하는 건 안되는지?"

### 현재 방식
```
api_url_registry.id = 1876 (AUTO_INCREMENT)
api_url_processing_log.id = 86 (AUTO_INCREMENT)
api_url_processing_log.api_url_registry_id = 1876 (FK)
```

### 제안: api_url_processing_log.id = api_url_registry.id?

#### ❌ 불가능한 이유

##### 1. AUTO_INCREMENT 충돌
```sql
-- api_url_registry
id BIGINT PRIMARY KEY AUTO_INCREMENT  -- MySQL이 자동 관리

-- api_url_processing_log
id BIGINT PRIMARY KEY AUTO_INCREMENT  -- MySQL이 자동 관리
```

**문제:** 두 테이블의 AUTO_INCREMENT는 독립적으로 관리됩니다.

##### 2. 1:N 관계 위반
```
api_url_registry (1) ←─── (N) api_url_processing_log
```

**예시:**
```
api_url_registry.id = 1876 (하나의 URL)
    ↓
api_url_processing_log:
    - id=86,  api_url_registry_id=1876, status='new_inserted'     (1차 시도)
    - id=120, api_url_registry_id=1876, status='duplicate_skipped' (2차 시도)
    - id=245, api_url_registry_id=1876, status='duplicate_updated' (3차 시도)
```

**같은 URL에 대한 여러 처리 시도를 모두 기록**해야 하므로 1:N 관계가 필수입니다.

##### 3. 로그 테이블의 목적
```python
# 같은 URL을 다시 처리하는 경우
# 1차 처리: api_url_registry_id=1876 → processing_log.id=86
# 2차 처리: api_url_registry_id=1876 → processing_log.id=120 (새 로그)
```

로그 테이블은 **모든 시도를 기록**해야 하므로 독립적인 PK가 필요합니다.

---

## ✅ 현재 방식의 장점

### 1. 완전한 이력 추적
```sql
-- URL 1876에 대한 모든 처리 이력 조회
SELECT * FROM api_url_processing_log
WHERE api_url_registry_id = 1876
ORDER BY created_at ASC;

-- 결과:
-- 2025-10-28 10:00 | new_inserted
-- 2025-10-29 15:30 | duplicate_skipped (우선순위 낮음)
-- 2025-10-30 20:15 | duplicate_updated (우선순위 높음)
```

### 2. 데이터 무결성
```sql
CONSTRAINT fk_processing_log_registry
    FOREIGN KEY (api_url_registry_id)
    REFERENCES api_url_registry(id)
    ON DELETE CASCADE
```

- api_url_registry 삭제 시 관련 로그 자동 삭제 (CASCADE)
- 데이터 정합성 보장

### 3. 유연한 쿼리
```sql
-- 원본 데이터 + 처리 이력 JOIN
SELECT
    aur.id,
    aur.title,
    aur.announcement_url,
    apl.processing_status,
    apl.created_at
FROM api_url_registry aur
LEFT JOIN api_url_processing_log apl ON aur.id = apl.api_url_registry_id
WHERE aur.site_code = 'bizInfo'
ORDER BY apl.created_at DESC;
```

### 4. 중복 처리 통계
```sql
-- URL별 처리 시도 횟수
SELECT
    api_url_registry_id,
    COUNT(*) as attempt_count,
    GROUP_CONCAT(processing_status ORDER BY created_at) as status_history
FROM api_url_processing_log
GROUP BY api_url_registry_id
HAVING attempt_count > 1;

-- 결과:
-- registry_id | attempt_count | status_history
-- 1876        | 3            | new_inserted,duplicate_skipped,duplicate_updated
```

---

## 🔧 대안 검토

### 대안 1: 복합 PK 사용 (❌ 비추천)
```sql
-- api_url_processing_log
PRIMARY KEY (api_url_registry_id, attempt_number)
```

**문제:**
- attempt_number 관리 복잡
- AUTO_INCREMENT 사용 불가
- JOIN 성능 저하

### 대안 2: UNIQUE 제약조건 (❌ 불가능)
```sql
UNIQUE KEY uk_one_log_per_url (api_url_registry_id)
```

**문제:** 같은 URL에 대한 여러 시도를 기록할 수 없음

### 대안 3: 현재 방식 유지 (✅ 권장)
```sql
-- api_url_processing_log
id BIGINT PRIMARY KEY AUTO_INCREMENT
api_url_registry_id BIGINT NOT NULL FK
```

**장점:**
- 완전한 이력 추적
- 데이터 무결성 보장
- 표준 설계 패턴
- 성능 최적화 가능

---

## 📈 성능 최적화

### 현재 인덱스
```sql
-- api_url_processing_log
KEY idx_api_url_registry_id (api_url_registry_id)
```

### 권장 복합 인덱스
```sql
-- URL별 최신 로그 조회용
CREATE INDEX idx_registry_created
ON api_url_processing_log(api_url_registry_id, created_at DESC);

-- 상태별 통계용
CREATE INDEX idx_registry_status
ON api_url_processing_log(api_url_registry_id, processing_status);
```

---

## 🎯 결론

### ✅ 현재 방식 (권장)
```
api_url_registry.id (독립적 AUTO_INCREMENT)
    ↓ FK
api_url_processing_log.api_url_registry_id
api_url_processing_log.id (독립적 AUTO_INCREMENT)
```

**이유:**
1. ✅ 1:N 관계 정확히 표현
2. ✅ 모든 처리 시도 기록 가능
3. ✅ 데이터 무결성 보장 (FK, CASCADE)
4. ✅ 표준 설계 패턴
5. ✅ 유연한 쿼리 및 통계

### ❌ 제안된 방식 (불가능)
```
api_url_processing_log.id = api_url_registry.id
```

**문제:**
1. ❌ AUTO_INCREMENT 충돌
2. ❌ 1:N 관계 표현 불가
3. ❌ 여러 시도 기록 불가
4. ❌ 로그 테이블 목적 상실

---

## 📋 사용 예시

### URL별 전체 처리 이력 조회
```sql
SELECT
    apl.id as log_id,
    apl.api_url_registry_id,
    apl.processing_status,
    apl.created_at,
    aur.title,
    aur.announcement_url,
    aur.preprocessing_id
FROM api_url_processing_log apl
JOIN api_url_registry aur ON apl.api_url_registry_id = aur.id
WHERE apl.api_url_registry_id = 1876
ORDER BY apl.created_at ASC;
```

### 중복 처리된 URL 목록
```sql
SELECT
    aur.id,
    aur.title,
    COUNT(apl.id) as attempt_count,
    MAX(apl.created_at) as last_attempt,
    GROUP_CONCAT(apl.processing_status ORDER BY apl.created_at) as status_history
FROM api_url_registry aur
JOIN api_url_processing_log apl ON aur.id = apl.api_url_registry_id
GROUP BY aur.id
HAVING attempt_count > 1
ORDER BY attempt_count DESC;
```

### 최신 처리 상태 조회 (윈도우 함수)
```sql
SELECT *
FROM (
    SELECT
        apl.*,
        ROW_NUMBER() OVER (
            PARTITION BY apl.api_url_registry_id
            ORDER BY apl.created_at DESC
        ) as rn
    FROM api_url_processing_log apl
) latest
WHERE rn = 1;
```

---

**작성일:** 2025-10-31
**결론:** 현재 방식 유지 권장 ✅
**이유:** 1:N 관계, 완전한 이력 추적, 데이터 무결성
