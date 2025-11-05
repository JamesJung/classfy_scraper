# api_url_registry.announcement_url ↔ announcement_pre_processing.origin_url 관계 분석

## 📋 분석 목적

`api_url_registry` 테이블의 `announcement_url` 컬럼과 `announcement_pre_processing` 테이블의 `origin_url` 컬럼이 같거나 유사한 부분이 있는지 확인

**분석 일시**: 2025-10-30

---

## 🔍 코드 분석 결과

### 1. **api_url_registry 업데이트 로직** (announcement_pre_processor.py:1332-1464)

#### **핵심 메서드**: `_update_api_url_registry()`

```python
def _update_api_url_registry(
    self, session, origin_url: str, preprocessing_id: int, site_code: str, scraping_url: str = None
) -> bool:
    """
    api_url_registry 테이블의 preprocessing_id를 업데이트합니다.

    Args:
        origin_url: 원본 URL (announcement_pre_processing.origin_url)
        preprocessing_id: announcement_pre_processing 테이블의 ID
        site_code: 사이트 코드 (kStartUp, bizInfo, smes24)
        scraping_url: 스크래핑 URL
    """
```

---

## 📊 테이블 관계 매핑

### **관계도**:

```
api_url_registry (API 수집 원본 데이터)
    ↓ preprocessing_id (FK-like)
announcement_pre_processing (전처리된 공고 데이터)
```

### **연결 컬럼**:

| api_url_registry | announcement_pre_processing | 관계 |
|------------------|----------------------------|------|
| `preprocessing_id` | `id` | **외래 키 관계** (실제 FK 제약 없음) |
| `announcement_url` | `origin_url` | **데이터 유사성** (매칭 조건) |
| `scrap_url` (kStartUp 전용) | `scraping_url` | **데이터 유사성** (매칭 조건) |

---

## 🔗 URL 매칭 로직

### **케이스 1: kStartUp** (line 1360-1394)

```python
if site_code == "kStartUp":
    # scrap_url 컬럼 사용 (announcement_url은 신뢰할 수 없음)
    UPDATE api_url_registry
    SET preprocessing_id = :preprocessing_id
    WHERE scrap_url = :scraping_url
    LIMIT 1
```

**매칭 조건**:
- `api_url_registry.scrap_url` = `announcement_pre_processing.scraping_url`
- announcement_url은 **사용 안 함** (신뢰할 수 없음)

### **케이스 2: bizInfo, smes24** (line 1396-1459)

**1차 시도**: scraping_url로 매칭
```python
UPDATE api_url_registry
SET preprocessing_id = :preprocessing_id
WHERE announcement_url = :scraping_url
LIMIT 1
```

**2차 시도**: origin_url로 매칭 (1차 실패 시)
```python
UPDATE api_url_registry
SET preprocessing_id = :preprocessing_id
WHERE announcement_url = :origin_url
LIMIT 1
```

**매칭 우선순위**:
1. `api_url_registry.announcement_url` = `announcement_pre_processing.scraping_url`
2. `api_url_registry.announcement_url` = `announcement_pre_processing.origin_url`

---

## ✅ **결론: URL 유사성 확인**

### **1. announcement_url ↔ origin_url 관계**

**✅ 예, 같은 경우가 있습니다!**

**매칭 시나리오** (bizInfo, smes24):
```
api_url_registry.announcement_url = announcement_pre_processing.origin_url
→ preprocessing_id 업데이트 (2차 시도에서 매칭)
```

**예시**:
```
api_url_registry:
  - announcement_url: "https://www.bizinfo.go.kr/web/lay1/program/S1T294C295/notice/view.do?NOTICE_NO=123456"
  - preprocessing_id: NULL → 업데이트 대상

announcement_pre_processing:
  - id: 12345
  - origin_url: "https://www.bizinfo.go.kr/web/lay1/program/S1T294C295/notice/view.do?NOTICE_NO=123456"

매칭 결과:
  → api_url_registry.preprocessing_id = 12345 (업데이트됨)
```

### **2. announcement_url ↔ scraping_url 관계**

**✅ 예, 우선적으로 매칭됩니다!**

**매칭 시나리오** (bizInfo, smes24):
```
api_url_registry.announcement_url = announcement_pre_processing.scraping_url
→ preprocessing_id 업데이트 (1차 시도에서 매칭, 우선순위 높음)
```

### **3. scrap_url ↔ scraping_url 관계**

**✅ kStartUp 전용 매칭**

**매칭 시나리오** (kStartUp):
```
api_url_registry.scrap_url = announcement_pre_processing.scraping_url
→ preprocessing_id 업데이트
```

---

## 📈 매칭 우선순위 정리

### **bizInfo, smes24**:
1. **1순위**: `announcement_url` = `scraping_url`
2. **2순위**: `announcement_url` = `origin_url`

### **kStartUp**:
1. **유일 조건**: `scrap_url` = `scraping_url`
2. `announcement_url`은 **사용 안 함**

---

## 🎯 예상되는 매칭 결과

### **완전 일치 (exact match)**:

**bizInfo, smes24**:
- `api_url_registry.announcement_url` = `announcement_pre_processing.origin_url`
- 또는 `api_url_registry.announcement_url` = `announcement_pre_processing.scraping_url`

**kStartUp**:
- `api_url_registry.scrap_url` = `announcement_pre_processing.scraping_url`

### **부분 일치 가능성**:

**쿼리 파라미터 순서 다름**:
```
api_url_registry.announcement_url:
  https://example.com/notice?id=123&page=1

announcement_pre_processing.origin_url:
  https://example.com/notice?page=1&id=123

→ 완전 일치 실패, 매칭 안 됨 ❌
```

**해결 방안**: url_key_hash 활용 (정규화된 URL 해시)

---

## ⚠️ 주의사항

### **1. LIMIT 1 사용**

```python
WHERE announcement_url = :origin_url
LIMIT 1
```

**문제**:
- 동일한 URL이 여러 개 있을 경우 **첫 번째 레코드만 업데이트**
- 나머지는 preprocessing_id가 NULL로 남음

**영향**:
- api_url_registry에 중복 URL이 있으면 일부만 매핑됨

### **2. 매칭 실패 케이스**

**scraping_url과 origin_url 둘 다 매칭 안 됨**:
- api_url_registry.announcement_url과 일치하는 URL이 없음
- preprocessing_id가 NULL로 남음

**원인**:
- URL 정규화 차이 (쿼리 파라미터 순서, 프로토콜 등)
- API 수집 URL과 실제 공고 URL이 다름

### **3. kStartUp의 announcement_url 신뢰성 문제**

**코드 주석** (line 1357-1358):
```python
# ⚠️ 테이블 컬럼 구조:
# - api_url_registry.announcement_url: 공고 URL (bizInfo, smes24 사용)
# - api_url_registry.scrap_url: 스크래핑 URL (kStartUp 사용)
```

**문제**:
- kStartUp은 announcement_url을 **사용하지 않음** (신뢰할 수 없음)
- scrap_url만 사용

**영향**:
- kStartUp의 announcement_url과 origin_url 비교는 **의미 없음**

---

## 📊 검증 SQL 쿼리

### **1. 완전 일치 건수**

```sql
-- bizInfo, smes24: announcement_url = origin_url
SELECT COUNT(*) as exact_match_count
FROM api_url_registry ar
INNER JOIN announcement_pre_processing app
    ON ar.announcement_url = app.origin_url
WHERE ar.site_code IN ('bizInfo', 'smes24');

-- kStartUp: scrap_url = scraping_url
SELECT COUNT(*) as kstartup_match_count
FROM api_url_registry ar
INNER JOIN announcement_pre_processing app
    ON ar.scrap_url = app.scraping_url
WHERE ar.site_code = 'kStartUp';
```

### **2. preprocessing_id 매핑 현황**

```sql
SELECT
    site_code,
    COUNT(*) as total,
    SUM(CASE WHEN preprocessing_id IS NOT NULL THEN 1 ELSE 0 END) as mapped,
    SUM(CASE WHEN preprocessing_id IS NULL THEN 1 ELSE 0 END) as unmapped
FROM api_url_registry
WHERE site_code IN ('kStartUp', 'bizInfo', 'smes24')
GROUP BY site_code;
```

### **3. 매핑되었지만 URL 다른 경우**

```sql
SELECT
    ar.id,
    ar.site_code,
    ar.announcement_url,
    app.origin_url,
    CASE
        WHEN ar.announcement_url = app.origin_url THEN 'exact'
        WHEN SUBSTRING_INDEX(ar.announcement_url, '?', 1) = SUBSTRING_INDEX(app.origin_url, '?', 1) THEN 'base_url_match'
        ELSE 'different'
    END as match_type
FROM api_url_registry ar
INNER JOIN announcement_pre_processing app
    ON ar.preprocessing_id = app.id
WHERE ar.site_code IN ('bizInfo', 'smes24')
LIMIT 100;
```

### **4. 매핑 안 된 레코드**

```sql
-- preprocessing_id가 NULL인 레코드
SELECT
    site_code,
    announcement_url,
    scrap_url
FROM api_url_registry
WHERE preprocessing_id IS NULL
AND site_code IN ('kStartUp', 'bizInfo', 'smes24')
LIMIT 10;
```

---

## 💡 개선 방안

### **1. url_key_hash 활용**

**현재 문제**:
- 쿼리 파라미터 순서가 다르면 매칭 실패

**개선안**:
```python
# 1차 시도: url_key_hash로 매칭
UPDATE api_url_registry ar
INNER JOIN announcement_pre_processing app
    ON ar.url_key_hash = app.url_key_hash
SET ar.preprocessing_id = app.id
WHERE ar.preprocessing_id IS NULL
AND ar.url_key_hash IS NOT NULL;

# 2차 시도: announcement_url = origin_url (정확한 일치)
UPDATE api_url_registry ar
INNER JOIN announcement_pre_processing app
    ON ar.announcement_url = app.origin_url
SET ar.preprocessing_id = app.id
WHERE ar.preprocessing_id IS NULL;
```

### **2. LIMIT 1 제거 또는 모든 중복 처리**

**현재**:
```python
WHERE announcement_url = :origin_url
LIMIT 1  # ← 첫 번째만 업데이트
```

**개선안 A**: 모든 중복 레코드 업데이트
```python
WHERE announcement_url = :origin_url
# LIMIT 제거
```

**개선안 B**: 최신 레코드만 업데이트
```python
WHERE announcement_url = :origin_url
ORDER BY id DESC
LIMIT 1
```

### **3. 매칭 실패 로그 기록**

```python
if not api_registry_updated:
    # 매칭 실패 이유 기록
    logger.warning(
        f"api_url_registry 매칭 실패: "
        f"site_code={site_code}, "
        f"announcement_url={origin_url[:50]}..., "
        f"scraping_url={scraping_url[:50] if scraping_url else 'None'}..."
    )

    # 별도 테이블에 매칭 실패 이력 기록 (선택적)
    self._log_failed_api_registry_match(
        session, origin_url, scraping_url, site_code, preprocessing_id
    )
```

---

## 📝 요약

### ✅ **같거나 유사한 부분이 있나?**

**예, 있습니다!**

1. **bizInfo, smes24**:
   - `api_url_registry.announcement_url` = `announcement_pre_processing.origin_url` (2차 매칭)
   - `api_url_registry.announcement_url` = `announcement_pre_processing.scraping_url` (1차 매칭)

2. **kStartUp**:
   - `api_url_registry.scrap_url` = `announcement_pre_processing.scraping_url`
   - announcement_url은 사용 안 함

### 🔗 **관계 유형**

**외래 키 관계** (실제 FK 제약 없음):
- `api_url_registry.preprocessing_id` → `announcement_pre_processing.id`

**데이터 유사성 (매칭 조건)**:
- `announcement_url` ↔ `origin_url` (bizInfo, smes24)
- `announcement_url` ↔ `scraping_url` (bizInfo, smes24, 우선)
- `scrap_url` ↔ `scraping_url` (kStartUp)

### ⚠️ **주의사항**

1. **완전 일치만 매칭** (쿼리 파라미터 순서 달라도 실패)
2. **LIMIT 1로 첫 번째만 업데이트** (중복 URL 일부만 매핑)
3. **kStartUp은 announcement_url 사용 안 함**

### 💡 **권장 검증**

```bash
# 테스트 스크립트 실행 (DB 접속 필요)
python3 check_url_similarity.py

# 또는 SQL 직접 실행
mysql -u user -p database < quick_url_check.sql
```

---

**작성일**: 2025-10-30
**분석 대상**: announcement_pre_processor.py (line 1332-1464)
**작성자**: Claude Code Assistant
