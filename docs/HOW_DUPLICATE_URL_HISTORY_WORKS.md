# 중복 URL 입력 시 히스토리 저장 방식

**작성일**: 2025-11-22
**목적**: 중복 URL이 들어왔을 때 어떻게 히스토리가 남는지 상세 설명

---

## 📊 전체 흐름도

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. 새 공고 수집                                                  │
│    - origin_url: https://www.test.kr/notice?id=123              │
│    - url_key 추출: www.test.kr|id=123                           │
│    - url_key_hash: MD5(url_key) = abc123...                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. UPSERT 실행 (ON DUPLICATE KEY UPDATE)                        │
│    INSERT INTO announcement_pre_processing (...)                │
│    VALUES (...)                                                  │
│    ON DUPLICATE KEY UPDATE                                       │
│        folder_name = VALUES(folder_name), ...                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    ┌─────────┴─────────┐
                    │                   │
           ┌────────▼────────┐ ┌───────▼────────┐
           │ affected_rows=1 │ │ affected_rows=2│
           │ (새 레코드 삽입) │ │ (기존 레코드   │
           │                 │ │  업데이트)     │
           └────────┬────────┘ └───────┬────────┘
                    │                   │
                    │                   │
           ┌────────▼─────────────────┬▼────────┐
           │                          │         │
    ┌──────▼──────┐        ┌─────────▼────┐ ┌──▼────────┐
    │ new_inserted│        │ replaced     │ │kept_exist │
    │             │        │ (우선순위 높음│ │(우선순위  │
    │             │        │  → 교체)     │ │ 낮음)     │
    └──────┬──────┘        └─────────┬────┘ └──┬────────┘
           │                         │         │
           └─────────────┬───────────┴─────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. announcement_duplicate_log 기록 (히스토리 저장!)             │
│    - preprocessing_id: 저장된 레코드 ID                          │
│    - duplicate_type: new_inserted / replaced / kept_existing   │
│    - url_key_hash: abc123...                                    │
│    - duplicate_detail: JSON 상세 정보                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✅ 히스토리가 남는 방법: announcement_duplicate_log 테이블

### 테이블 구조
```sql
CREATE TABLE announcement_duplicate_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    preprocessing_id BIGINT,                  -- 저장/업데이트된 레코드 ID
    existing_preprocessing_id BIGINT,         -- 기존 레코드 ID (중복 시)
    duplicate_type VARCHAR(50),               -- 중복 유형
    url_key_hash CHAR(32),                    -- url_key의 MD5 해시
    new_site_type VARCHAR(50),                -- 새 데이터의 site_type
    new_site_code VARCHAR(50),                -- 새 데이터의 site_code
    existing_site_type VARCHAR(50),           -- 기존 데이터의 site_type
    existing_site_code VARCHAR(50),           -- 기존 데이터의 site_code
    new_priority INT,                         -- 새 데이터 우선순위
    existing_priority INT,                    -- 기존 데이터 우선순위
    new_folder_name VARCHAR(500),             -- 새 폴더명
    existing_folder_name VARCHAR(500),        -- 기존 폴더명
    duplicate_detail JSON,                    -- 상세 정보 (변경 내역 등)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🔍 시나리오별 상세 설명

### 시나리오 1: 완전히 새로운 URL (첫 수집)

**입력:**
```
origin_url: https://www.test.kr/notice?id=123
title: "2025년 지원사업 공고"
site_type: Eminwon
```

**처리 과정:**
1. url_key 추출: `www.test.kr|id=123`
2. url_key_hash 계산: `MD5(www.test.kr|id=123)` = `abc123...`
3. UPSERT 실행:
   ```sql
   INSERT INTO announcement_pre_processing (url_key, ...)
   VALUES ('www.test.kr|id=123', ...)
   ON DUPLICATE KEY UPDATE ...
   ```
4. **affected_rows = 1** (새 레코드 삽입)

**히스토리 기록 (announcement_duplicate_log):**
```json
{
  "id": 1001,
  "preprocessing_id": 50001,              // 새로 삽입된 레코드 ID
  "existing_preprocessing_id": NULL,      // 기존 레코드 없음
  "duplicate_type": "new_inserted",       // 신규 삽입
  "url_key_hash": "abc123...",
  "new_site_type": "Eminwon",
  "new_site_code": "prv_seoul",
  "existing_site_type": NULL,
  "existing_site_code": NULL,
  "new_priority": 3,
  "existing_priority": NULL,
  "new_folder_name": "20251122_001_2025년지원사업공고",
  "existing_folder_name": NULL,
  "duplicate_detail": {
    "decision": "신규 등록",
    "reason": "url_key_hash 중복 없음",
    "domain": "www.test.kr",
    "domain_configured": true,
    "timestamp": "2025-11-22T10:30:00"
  },
  "created_at": "2025-11-22 10:30:00"
}
```

**결과:**
- ✅ announcement_pre_processing에 새 레코드 INSERT
- ✅ announcement_duplicate_log에 히스토리 기록 (duplicate_type='new_inserted')

---

### 시나리오 2: 동일 URL 재수집 (우선순위 높음 → 교체)

**입력:**
```
origin_url: https://www.test.kr/notice?id=123  (같은 URL!)
title: "2025년 지원사업 공고 [수정]"
site_type: Homepage  (우선순위 3)
```

**기존 데이터:**
```
id: 50001
url_key: www.test.kr|id=123
url_key_hash: abc123...
title: "2025년 지원사업 공고"
site_type: api_scrap  (우선순위 1)
```

**처리 과정:**
1. url_key 추출: `www.test.kr|id=123` (동일!)
2. url_key_hash: `abc123...` (동일!)
3. **UPSERT 전 중복 체크:**
   ```sql
   SELECT id, site_type, title, ...
   FROM announcement_pre_processing
   WHERE url_key_hash = 'abc123...'
   ```
   → 기존 레코드 발견! (id=50001, site_type=api_scrap)

4. UPSERT 실행:
   ```sql
   INSERT INTO announcement_pre_processing (url_key, ...)
   VALUES ('www.test.kr|id=123', ...)
   ON DUPLICATE KEY UPDATE
       title = VALUES(title),      -- "2025년 지원사업 공고 [수정]"으로 업데이트
       site_type = VALUES(site_type),  -- "Homepage"로 업데이트
       ...
   ```
5. **affected_rows = 2** (기존 레코드 UPDATE)

6. **우선순위 비교:**
   - 새 데이터: Homepage (priority=3)
   - 기존 데이터: api_scrap (priority=1)
   - **3 > 1 → 교체 (replaced)**

**히스토리 기록 (announcement_duplicate_log):**
```json
{
  "id": 1002,
  "preprocessing_id": 50001,              // 업데이트된 레코드 ID (기존과 동일)
  "existing_preprocessing_id": 50001,     // 기존 레코드 ID
  "duplicate_type": "replaced",           // 기존 데이터 교체
  "url_key_hash": "abc123...",
  "new_site_type": "Homepage",
  "new_site_code": "prv_seoul",
  "existing_site_type": "api_scrap",
  "existing_site_code": "bizInfo",
  "new_priority": 3,
  "existing_priority": 1,
  "new_folder_name": "20251122_002_2025년지원사업공고수정",
  "existing_folder_name": "20251122_001_2025년지원사업공고",
  "duplicate_detail": {
    "decision": "기존 데이터 교체",
    "reason": "우선순위 높음: Homepage(3) > api_scrap(1)",
    "existing_folder": "20251122_001_2025년지원사업공고",
    "existing_url_key": "www.test.kr|id=123",
    "priority_comparison": "3 vs 1",
    "changed_fields": {
      "title": {
        "before": "2025년 지원사업 공고",
        "after": "2025년 지원사업 공고 [수정]",
        "changed": true
      },
      "folder_name": {
        "before": "20251122_001_2025년지원사업공고",
        "after": "20251122_002_2025년지원사업공고수정",
        "changed": true
      }
    },
    "domain": "www.test.kr",
    "domain_configured": true,
    "timestamp": "2025-11-22T11:00:00"
  },
  "created_at": "2025-11-22 11:00:00"
}
```

**결과:**
- ✅ announcement_pre_processing의 기존 레코드 UPDATE (id=50001)
- ✅ announcement_duplicate_log에 히스토리 기록 (duplicate_type='replaced')
- ✅ 변경된 필드 상세 정보 JSON으로 저장

---

### 시나리오 3: 동일 URL 재수집 (우선순위 낮음 → 유지)

**입력:**
```
origin_url: https://www.test.kr/notice?id=123  (같은 URL!)
title: "2025년 지원사업 공고 [오래된 버전]"
site_type: api_scrap  (우선순위 1)
```

**기존 데이터:**
```
id: 50001
url_key: www.test.kr|id=123
title: "2025년 지원사업 공고 [최신]"
site_type: Eminwon  (우선순위 3)
```

**처리 과정:**
1. url_key_hash 중복 발견
2. UPSERT 실행 → affected_rows = 2
3. **우선순위 비교:**
   - 새 데이터: api_scrap (priority=1)
   - 기존 데이터: Eminwon (priority=3)
   - **1 < 3 → 기존 유지 (kept_existing)**

**히스토리 기록:**
```json
{
  "id": 1003,
  "preprocessing_id": 50001,              // 레코드 ID (변경 없음)
  "existing_preprocessing_id": 50001,
  "duplicate_type": "kept_existing",      // 기존 데이터 유지
  "url_key_hash": "abc123...",
  "new_site_type": "api_scrap",
  "new_site_code": "bizInfo",
  "existing_site_type": "Eminwon",
  "existing_site_code": "prv_seoul",
  "new_priority": 1,
  "existing_priority": 3,
  "new_folder_name": "20251122_003_오래된버전",
  "existing_folder_name": "20251122_002_2025년지원사업공고수정",
  "duplicate_detail": {
    "decision": "기존 데이터 유지",
    "reason": "우선순위 낮음: api_scrap(1) < Eminwon(3)",
    "existing_folder": "20251122_002_2025년지원사업공고수정",
    "existing_url_key": "www.test.kr|id=123",
    "priority_comparison": "1 vs 3",
    "changed_fields": null,  // 변경 없음
    "domain": "www.test.kr",
    "domain_configured": true,
    "timestamp": "2025-11-22T12:00:00"
  }
}
```

**결과:**
- ⚠️ announcement_pre_processing의 데이터는 변경 없음 (기존 유지)
- ✅ announcement_duplicate_log에 히스토리 기록 (duplicate_type='kept_existing')

---

## 📋 duplicate_type 종류

| duplicate_type | 의미 | affected_rows | 우선순위 비교 | 데이터 변경 |
|----------------|------|---------------|---------------|-------------|
| **new_inserted** | 신규 삽입 | 1 | - | ✅ INSERT |
| **replaced** | 기존 교체 | 2 | 새 > 기존 | ✅ UPDATE |
| **kept_existing** | 기존 유지 | 2 | 새 < 기존 | ❌ 유지 |
| **same_type_duplicate** | 동일 타입 재수집 | 2 | 새 = 기존 | ✅ UPDATE (최신 우선) |
| **unconfigured_domain** | 설정 없는 도메인 | 1 | - | ✅ INSERT (url_key=NULL) |
| **error** | 처리 오류 | - | - | ❌ 실패 |

---

## 🔍 히스토리 조회 쿼리

### 1. 특정 URL의 전체 히스토리 조회
```sql
SELECT
    adl.id,
    adl.duplicate_type,
    adl.new_site_type,
    adl.existing_site_type,
    adl.new_priority,
    adl.existing_priority,
    adl.new_folder_name,
    adl.existing_folder_name,
    adl.duplicate_detail,
    adl.created_at
FROM announcement_duplicate_log adl
WHERE adl.url_key_hash = MD5('www.test.kr|id=123')
ORDER BY adl.created_at DESC;
```

**결과 예시:**
```
id  | duplicate_type  | new_site_type | existing_site_type | created_at
----|-----------------|---------------|--------------------|------------
1003| kept_existing   | api_scrap     | Eminwon            | 2025-11-22 12:00
1002| replaced        | Homepage      | api_scrap          | 2025-11-22 11:00
1001| new_inserted    | Eminwon       | NULL               | 2025-11-22 10:30
```

→ **히스토리가 모두 기록됨!**

---

### 2. 오늘 교체된 레코드 조회
```sql
SELECT
    adl.preprocessing_id,
    app.title,
    adl.new_site_type,
    adl.existing_site_type,
    JSON_EXTRACT(adl.duplicate_detail, '$.reason') as reason,
    adl.created_at
FROM announcement_duplicate_log adl
JOIN announcement_pre_processing app ON adl.preprocessing_id = app.id
WHERE DATE(adl.created_at) = CURDATE()
    AND adl.duplicate_type = 'replaced'
ORDER BY adl.created_at DESC;
```

---

### 3. 변경 내역 상세 조회
```sql
SELECT
    adl.preprocessing_id,
    adl.duplicate_type,
    JSON_PRETTY(adl.duplicate_detail) as detail
FROM announcement_duplicate_log adl
WHERE adl.preprocessing_id = 50001
ORDER BY adl.created_at DESC
LIMIT 1;
```

**출력:**
```json
{
  "decision": "기존 데이터 교체",
  "reason": "우선순위 높음: Homepage(3) > api_scrap(1)",
  "existing_folder": "20251122_001_2025년지원사업공고",
  "existing_url_key": "www.test.kr|id=123",
  "priority_comparison": "3 vs 1",
  "changed_fields": {
    "title": {
      "before": "2025년 지원사업 공고",
      "after": "2025년 지원사업 공고 [수정]",
      "changed": true
    }
  },
  "timestamp": "2025-11-22T11:00:00"
}
```

---

## ✅ 결론: 히스토리는 무조건 남습니다!

### 히스토리가 남는 경우

| 상황 | announcement_pre_processing | announcement_duplicate_log |
|------|----------------------------|----------------------------|
| 새 URL 첫 수집 | ✅ INSERT | ✅ 히스토리 기록 (new_inserted) |
| 중복 URL (우선순위 높음) | ✅ UPDATE (교체) | ✅ 히스토리 기록 (replaced) |
| 중복 URL (우선순위 낮음) | ❌ 변경 없음 | ✅ 히스토리 기록 (kept_existing) |
| 중복 URL (우선순위 동일) | ✅ UPDATE (최신) | ✅ 히스토리 기록 (same_type_duplicate) |

**모든 경우에 announcement_duplicate_log에 히스토리가 기록됩니다!**

---

## 🎯 핵심 포인트

1. **ON DUPLICATE KEY UPDATE** 사용으로 에러 없이 UPSERT
2. **affected_rows 값**으로 신규/중복 판단
   - affected_rows = 1 → 신규 INSERT
   - affected_rows = 2 → 중복 UPDATE
3. **UPSERT 전 중복 체크**로 기존 레코드 정보 조회
4. **우선순위 비교**로 교체/유지 결정
5. **announcement_duplicate_log**에 모든 처리 결과 기록
   - preprocessing_id: 최종 레코드 ID
   - duplicate_type: 처리 유형
   - duplicate_detail: JSON 상세 정보 (변경 내역, 우선순위 등)
6. **변경된 필드 추적**: before/after 값을 JSON으로 저장

---

**작성자**: Claude Code
**작성일**: 2025-11-22
