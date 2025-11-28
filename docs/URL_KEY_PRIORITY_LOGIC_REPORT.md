# URL Key 중복 판단 및 우선순위 로직 보고서

**작성일**: 2025-11-24
**분석 대상**: `announcement_pre_processor.py`의 url_key 기반 중복 처리 로직

---

## 📋 Executive Summary

### 핵심 메커니즘
- **중복 판단 기준**: `url_key_hash` (MD5 해시) UNIQUE INDEX 사용
- **우선순위 시스템**: site_type 기반 3단계 우선순위 (Eminwon/Homepage/Scraper > api_scrap > Unknown)
- **처리 방식**: MySQL `ON DUPLICATE KEY UPDATE` + 조건부 업데이트

---

## 🔑 URL Key 중복 판단 메커니즘

### 1. 테이블 구조

#### announcement_pre_processing 테이블
```sql
CREATE TABLE announcement_pre_processing (
    id INT PRIMARY KEY AUTO_INCREMENT,
    url_key VARCHAR(500),           -- 정규화된 URL 키 (검색용)
    url_key_hash CHAR(32) UNIQUE,   -- ✅ MD5 해시 (중복 판단 기준)
    site_type VARCHAR(50),
    site_code VARCHAR(50),
    ...
    UNIQUE KEY url_key_hash (url_key_hash)  -- ✅ UNIQUE INDEX
);
```

**핵심 포인트**:
- `url_key_hash`에 **UNIQUE INDEX**가 설정되어 중복 판단
- `url_key`는 검색용 (MUL INDEX)
- `url_key_hash`가 NULL이면 중복 체크 생략 (domain_key_config에 없는 도메인)

### 2. URL Key 생성 과정

```python
# src/utils/domainKeyExtractor.py
def extract_url_key(url: str) -> str:
    """
    URL에서 고유 키를 추출 (도메인별 설정 기반)

    예시:
    - www.seoul.go.kr?bbs_cd=123&seq=456
      → "www.seoul.go.kr|bbs_cd=123|seq=456"

    - www.busan.go.kr?sno=74842
      → "www.busan.go.kr|sno=74842"
    """
    # domain_key_config 테이블에서 도메인별 파라미터 설정 로드
    # 설정된 파라미터만 추출하여 정규화
    # 파라미터 순서는 알파벳 순으로 정렬 (순서 무관하게 동일 키 생성)
```

```python
# url_key → url_key_hash 변환
import hashlib

url_key = "www.seoul.go.kr|bbs_cd=123|seq=456"
url_key_hash = hashlib.md5(url_key.encode('utf-8')).hexdigest()
# → "a1b2c3d4e5f6..."
```

---

## ⚖️ 우선순위 시스템

### 1. 우선순위 정의 (`_get_priority()` 메서드)

```python
def _get_priority(self, site_type: str) -> int:
    """
    site_type의 우선순위를 반환합니다.
    높을수록 우선순위 높음.

    Returns:
        우선순위 값 (0-3)
    """
    priority_map = {
        'Eminwon': 3,      # ✅ 최고 우선순위 (민원24 크롤링)
        'Homepage': 3,     # ✅ 최고 우선순위 (지자체 홈페이지)
        'Scraper': 3,      # ✅ 최고 우선순위 (일반 스크래퍼)
        'api_scrap': 1,    # ⚠️ 낮은 우선순위 (K-Startup 등 API)
        'Unknown': 0,      # ❌ 최저 우선순위
    }
    return priority_map.get(site_type, 0)
```

**우선순위 로직**:
1. **Eminwon/Homepage/Scraper (3)**: 지자체 직접 수집 데이터
2. **api_scrap (1)**: 외부 API 데이터 (K-Startup 등)
3. **Unknown (0)**: 알 수 없는 소스

**의미**:
- 지자체에서 직접 수집한 데이터가 API 데이터보다 우선
- 같은 공고가 여러 소스에서 수집되면 **우선순위 높은 것으로 덮어씀**

---

## 🔄 중복 처리 흐름

### 1. 전체 처리 흐름

```
공고 데이터 수집
  ↓
URL에서 url_key 추출 (domain_key_config 기반)
  ↓
url_key → url_key_hash (MD5) 생성
  ↓
announcement_pre_processing 테이블에 INSERT
  ↓
[url_key_hash UNIQUE 제약 확인]
  ↓
┌─────────────────────────────────────┐
│ 중복 없음 (url_key_hash 없음)       │
│ → 신규 INSERT                       │
│ → duplicate_type: 'new_inserted'    │
└─────────────────────────────────────┘
  ↓
┌─────────────────────────────────────┐
│ 중복 있음 (url_key_hash 존재)       │
│ → ON DUPLICATE KEY UPDATE 실행      │
│ → 우선순위 비교                      │
└─────────────────────────────────────┘
  ↓
┌──────────────────────────────────────┐
│ 우선순위 비교 결과                    │
├──────────────────────────────────────┤
│ 1. 신규 우선순위 > 기존 우선순위      │
│    → 모든 필드 업데이트               │
│    → duplicate_type: 'replaced'      │
├──────────────────────────────────────┤
│ 2. 신규 우선순위 < 기존 우선순위      │
│    → 기존 데이터 유지 (업데이트 안함) │
│    → duplicate_type: 'kept_existing' │
├──────────────────────────────────────┤
│ 3. 신규 우선순위 = 기존 우선순위      │
│    → 최신 데이터로 업데이트           │
│    → duplicate_type: 'same_type_...' │
└──────────────────────────────────────┘
  ↓
announcement_duplicate_log에 로그 기록
```

---

### 2. ON DUPLICATE KEY UPDATE 로직

#### Case 1: force=True (우선순위 기반 조건부 업데이트)

```sql
INSERT INTO announcement_pre_processing (...)
VALUES (...)
ON DUPLICATE KEY UPDATE
    -- 각 필드마다 우선순위 체크
    content_md = IF(
        -- 조건: 새 데이터가 지자체 OR 기존 데이터가 지자체가 아님
        VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
        site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
        -- TRUE: 새 값으로 업데이트
        VALUES(content_md),
        -- FALSE: 기존 값 유지
        content_md
    ),
    -- 다른 필드도 동일한 패턴 반복
    ...
```

**의미**:
- 새 데이터가 **Eminwon/Homepage/Scraper**면 → 무조건 업데이트
- 기존 데이터가 **api_scrap**이고 새 데이터가 **Eminwon**이면 → 업데이트
- 기존 데이터가 **Eminwon**이고 새 데이터가 **api_scrap**이면 → 유지 (업데이트 안함)

#### Case 2: force=False (무조건 업데이트)

```sql
INSERT INTO announcement_pre_processing (...)
VALUES (...)
ON DUPLICATE KEY UPDATE
    folder_name = VALUES(folder_name),
    site_type = VALUES(site_type),
    content_md = VALUES(content_md),
    -- 모든 필드를 새 값으로 업데이트
    ...
```

---

### 3. 중복 타입 (duplicate_type)

| duplicate_type | 설명 | 발생 조건 |
|----------------|------|-----------|
| `unconfigured_domain` | domain_key_config에 설정 없음 | url_key = NULL (domain 미등록) |
| `new_inserted` | 신규 삽입 | url_key_hash 중복 없음 |
| `replaced` | 기존 데이터 교체 | 새 우선순위 > 기존 우선순위 |
| `kept_existing` | 기존 데이터 유지 | 새 우선순위 < 기존 우선순위 |
| `same_type_duplicate` | 동일 타입 재수집 | 새 우선순위 = 기존 우선순위 |
| `error` | 처리 중 오류 | 예외 발생 |

---

## 📊 우선순위 비교 예시

### 예시 1: 지자체 데이터가 API 데이터 덮어쓰기

```
기존 데이터:
  - url_key_hash: "a1b2c3..."
  - site_type: "api_scrap" (우선순위 1)
  - title: "2025년 창업지원사업"

새 데이터:
  - url_key_hash: "a1b2c3..." (동일!)
  - site_type: "Homepage" (우선순위 3)
  - title: "2025년 서울시 창업지원사업 모집"

처리 결과:
  ✅ replaced (우선순위 3 > 1)
  - site_type: "api_scrap" → "Homepage"
  - title: "2025년 창업지원사업" → "2025년 서울시 창업지원사업 모집"
  - 모든 필드가 새 데이터로 교체됨
```

### 예시 2: API 데이터가 지자체 데이터를 덮어쓸 수 없음

```
기존 데이터:
  - url_key_hash: "xyz123..."
  - site_type: "Eminwon" (우선순위 3)
  - title: "부산시 소상공인 지원사업"

새 데이터:
  - url_key_hash: "xyz123..." (동일!)
  - site_type: "api_scrap" (우선순위 1)
  - title: "소상공인 지원사업"

처리 결과:
  ⚠️ kept_existing (우선순위 1 < 3)
  - 기존 데이터 유지 (업데이트 안함)
  - API 데이터는 무시됨
```

### 예시 3: 동일한 소스의 재수집 (최신 데이터로 업데이트)

```
기존 데이터:
  - url_key_hash: "def456..."
  - site_type: "Homepage" (우선순위 3)
  - combined_content: "..." (2024-11-20 수집)

새 데이터:
  - url_key_hash: "def456..." (동일!)
  - site_type: "Homepage" (우선순위 3)
  - combined_content: "...(수정됨)" (2024-11-24 재수집)

처리 결과:
  ✅ same_type_duplicate (우선순위 3 = 3)
  - 최신 데이터로 업데이트
  - updated_at 갱신됨
```

---

## 📝 announcement_duplicate_log 로깅

모든 중복 처리는 `announcement_duplicate_log` 테이블에 기록됩니다.

### 로그 스키마

```sql
CREATE TABLE announcement_duplicate_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    preprocessing_id INT,              -- 처리된 레코드 ID
    existing_preprocessing_id INT,     -- 기존 레코드 ID (중복 시)
    duplicate_type VARCHAR(50),        -- 중복 타입
    url_key_hash CHAR(32),            -- URL 키 해시
    new_site_type VARCHAR(50),        -- 새 데이터 타입
    new_site_code VARCHAR(50),        -- 새 사이트 코드
    existing_site_type VARCHAR(50),   -- 기존 데이터 타입
    existing_site_code VARCHAR(50),   -- 기존 사이트 코드
    new_priority INT,                 -- 새 우선순위
    existing_priority INT,            -- 기존 우선순위
    new_folder_name VARCHAR(500),     -- 새 폴더명
    existing_folder_name VARCHAR(500),-- 기존 폴더명
    duplicate_detail JSON,            -- 상세 정보
    error_message TEXT,               -- 오류 메시지
    created_at TIMESTAMP              -- 로그 생성 시각
);
```

### 로그 예시 (duplicate_detail JSON)

```json
{
  "decision": "기존 데이터 교체",
  "reason": "우선순위 높음: Homepage(3) > api_scrap(1)",
  "existing_folder": "175613_2025년_서울바이오허브",
  "existing_url_key": "www.k-startup.go.kr|bizpbanc=123",
  "priority_comparison": "3 vs 1",
  "changed_fields": {
    "title": {
      "before": "2025년 서울바이오허브 글로벌진출 성장가속 프로그램",
      "after": "2025년 서울바이오허브 글로벌 진출 성장 가속 프로그램」 전문 수행기관 모집",
      "changed": true
    },
    "combined_content": {
      "before": "...(이전 내용 100자)...",
      "after": "...(새 내용 100자)...",
      "changed": true
    }
  },
  "domain": "www.k-startup.go.kr",
  "domain_configured": true,
  "timestamp": "2025-11-24T10:00:22.123456"
}
```

---

## 🎯 특수 케이스

### 1. domain_key_config에 없는 도메인

```python
# url_key = None으로 설정
# url_key_hash = None (NULL)
# UNIQUE 제약 무시 (NULL은 중복으로 간주 안함)
# → duplicate_type: 'unconfigured_domain'
```

**예시**:
- 새로운 지자체 사이트 발견 시
- domain_key_config 미등록 상태
- 중복 체크 없이 모두 INSERT됨

### 2. url_key는 있지만 url_key_hash가 NULL

```python
# domain_key_config에 is_active=False로 설정된 경우
# 또는 url_key 생성 실패 시
# → 중복 체크 생략
```

### 3. 동일 url_key_hash의 동시 INSERT (Race Condition)

```sql
-- MySQL의 ON DUPLICATE KEY UPDATE는 원자적(atomic)
-- 두 프로세스가 동시에 INSERT해도:
-- 1. 첫 번째: INSERT 성공
-- 2. 두 번째: DUPLICATE KEY 감지 → UPDATE 실행
```

---

## 📈 통계 쿼리 예시

### 1. 우선순위별 중복 처리 현황

```sql
SELECT
    duplicate_type,
    new_site_type,
    existing_site_type,
    COUNT(*) as count
FROM announcement_duplicate_log
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY duplicate_type, new_site_type, existing_site_type
ORDER BY count DESC;
```

### 2. 교체된 데이터 분석 (replaced)

```sql
SELECT
    new_site_type,
    existing_site_type,
    new_priority,
    existing_priority,
    COUNT(*) as replaced_count
FROM announcement_duplicate_log
WHERE duplicate_type = 'replaced'
  AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY new_site_type, existing_site_type, new_priority, existing_priority
ORDER BY replaced_count DESC;
```

### 3. 유지된 데이터 분석 (kept_existing)

```sql
SELECT
    existing_site_type,
    new_site_type,
    COUNT(*) as kept_count
FROM announcement_duplicate_log
WHERE duplicate_type = 'kept_existing'
  AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY existing_site_type, new_site_type
ORDER BY kept_count DESC;
```

---

## ⚙️ 설정 및 관리

### domain_key_config 테이블

```sql
CREATE TABLE domain_key_config (
    id INT PRIMARY KEY AUTO_INCREMENT,
    domain VARCHAR(255) UNIQUE,        -- 도메인명
    key_params JSON,                   -- URL 파라미터 설정
    is_active BOOLEAN DEFAULT TRUE,    -- 활성화 여부
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**예시 설정**:
```json
{
  "domain": "www.seoul.go.kr",
  "key_params": ["bbs_cd", "seq"],
  "is_active": true
}
```

**의미**:
- `www.seoul.go.kr?bbs_cd=123&seq=456&extra=999`
- → url_key: `www.seoul.go.kr|bbs_cd=123|seq=456`
- → `extra` 파라미터는 무시됨

---

## 🔍 모니터링 포인트

### 1. 우선순위 역전 감지

```sql
-- api_scrap이 지자체 데이터를 덮어쓴 케이스 (비정상)
SELECT *
FROM announcement_duplicate_log
WHERE duplicate_type = 'replaced'
  AND new_priority < existing_priority
ORDER BY created_at DESC
LIMIT 100;
```

### 2. 과도한 중복 발생

```sql
-- 같은 url_key_hash에 대한 과도한 중복 처리
SELECT
    url_key_hash,
    COUNT(*) as duplicate_count
FROM announcement_duplicate_log
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 DAY)
GROUP BY url_key_hash
HAVING duplicate_count > 10
ORDER BY duplicate_count DESC;
```

### 3. unconfigured_domain 모니터링

```sql
-- domain_key_config 미등록 도메인 추출
SELECT
    JSON_EXTRACT(duplicate_detail, '$.domain') as domain,
    COUNT(*) as count
FROM announcement_duplicate_log
WHERE duplicate_type = 'unconfigured_domain'
  AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY domain
ORDER BY count DESC;
```

---

## ✅ 장단점 분석

### 장점

1. **명확한 우선순위**: 지자체 데이터가 API 데이터보다 우선
2. **자동 중복 제거**: UNIQUE INDEX로 DB 레벨에서 중복 방지
3. **완전한 로깅**: 모든 중복 처리 이력 추적 가능
4. **유연한 설정**: domain_key_config로 도메인별 맞춤 설정
5. **Race Condition 안전**: MySQL의 원자적 연산 보장

### 단점 및 개선 가능 영역

1. **force=True 로직 복잡도**
   - SQL이 길고 복잡함 (각 필드마다 IF 조건)
   - 유지보수 어려움
   - **개선안**: 애플리케이션 레벨에서 우선순위 판단 후 INSERT/UPDATE 분리

2. **NULL url_key_hash 처리**
   - domain_key_config 미등록 시 모두 INSERT됨
   - 실제로는 중복일 수 있음
   - **개선안**: origin_url 기반 fallback 중복 체크

3. **우선순위 단계 부족**
   - 3단계만 존재 (3, 1, 0)
   - Eminwon과 Homepage의 우선순위가 동일
   - **개선안**: 더 세분화된 우선순위 체계

4. **동일 우선순위 처리**
   - 무조건 최신 데이터로 업데이트
   - 이전 데이터가 더 정확할 수 있음
   - **개선안**: 필드별 merge 전략 (비어있는 필드만 채우기 등)

---

## 📌 요약

### 핵심 원리
```
url_key_hash (UNIQUE) + site_type 우선순위 + ON DUPLICATE KEY UPDATE
= 자동 중복 제거 + 품질 높은 데이터 우선 보존
```

### 처리 순서
1. URL → url_key 추출 (domain_key_config 기반)
2. url_key → url_key_hash (MD5)
3. INSERT with ON DUPLICATE KEY UPDATE
4. 우선순위 비교 → 조건부 업데이트
5. announcement_duplicate_log에 로그 기록

### 우선순위
```
Eminwon/Homepage/Scraper (3) > api_scrap (1) > Unknown (0)
```

---

**작성자**: Claude Code
**작성일**: 2025-11-24
**관련 파일**: `announcement_pre_processor.py` (Line 1586-1900, 2180-2350)
