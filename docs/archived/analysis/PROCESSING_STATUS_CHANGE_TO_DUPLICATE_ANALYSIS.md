# processing_status에 'error' 대신 '중복' 사용 제안 검토

## 📋 제안 내용

**현재**: announcement_duplicate_log.duplicate_type='error' (213건)
**제안**: processing_status='중복'으로 변경

---

## 🔍 현황 분석

### 1. 두 가지 다른 'error'가 있음

#### A. announcement_pre_processing.processing_status = "error"
```sql
SELECT processing_status, COUNT(*)
FROM announcement_pre_processing
WHERE processing_status = 'error';

Result: 1건 (실제 오류)
```

**실제 오류 케이스**:
- site_code: prv_guro
- folder: 020_2025년 10월 지방세 독촉고지서...
- error_message: "처리할 내용이 없음"

#### B. announcement_duplicate_log.duplicate_type = "error"
```sql
SELECT duplicate_type, COUNT(*)
FROM announcement_duplicate_log
WHERE duplicate_type = 'error';

Result: 213건 (로그 기록 오류)
```

**실제 데이터 상태**:
```sql
SELECT adl.duplicate_type, app.processing_status, COUNT(*)
FROM announcement_duplicate_log adl
JOIN announcement_pre_processing app ON adl.preprocessing_id = app.id
WHERE adl.duplicate_type = 'error'
GROUP BY app.processing_status;

+----------------+-------------------+-------+
| duplicate_type | processing_status | count |
+----------------+-------------------+-------+
| error          | archived          | 178   |
| error          | 성공              | 32    |
| error          | 제외              | 3     |
+----------------+-------------------+-------+
```

**핵심**: duplicate_type='error'인데 **실제로는 정상 처리됨** (archived, 성공, 제외)

---

## ⚠️ 문제점: 용어 혼동

### 사용자 제안의 의도 파악

제안: **"processing_status에 'error' 대신 '중복' 사용"**

이것이 의미하는 바:
1. `announcement_pre_processing.processing_status = "중복"`?
2. `announcement_duplicate_log.duplicate_type = "중복"`?
3. 아니면 둘 다?

### 혼동 가능성 분석

#### 시나리오 1: announcement_pre_processing.processing_status = "중복"
```python
# 현재 값들
"성공"      - 정상 처리
"제외"      - 제외 키워드 매칭
"error"     - 실제 오류
"archived"  - 아카이브됨

# 제안 추가
"중복"      - 중복 감지됨?
```

**문제점**:
- ❌ "중복"은 **오류가 아님** (정상 처리)
- ❌ 현재 processing_status는 **최종 처리 상태**를 나타냄
  - "성공" = 정상 처리됨
  - "제외" = 제외됨
  - "error" = 실패함
  - "중복" = ??? (성공인가? 실패인가?)
- ❌ 중복 감지 시 처리 결과는 3가지:
  1. 새 데이터로 교체 (replaced) → "성공"
  2. 기존 데이터 유지 (kept_existing) → "성공"
  3. 동일 타입 재수집 (same_type_duplicate) → "성공"
- ❌ 모두 **"성공"**인데 별도로 "중복"으로 표시하면 혼란

#### 시나리오 2: announcement_duplicate_log.duplicate_type 값 변경
```python
# 현재 매핑
duplicate_type_map = {
    'new_inserted': 'new_inserted',
    'duplicate_updated': 'replaced',
    'duplicate_preserved': 'kept_existing',
    'failed': 'error'  # ← 이것을 '중복'으로?
}
```

**문제점**:
- ❌ 'failed'는 **실제 오류**를 의미
- ❌ '중복'으로 변경하면 의미 왜곡
- ❌ 실제 오류와 중복을 구분할 수 없음

---

## 🎯 실제 문제는 무엇인가?

### 근본 원인 분석

```sql
-- duplicate_type='error'인데 실제로는 정상 처리됨
SELECT adl.*, app.processing_status, app.folder_name
FROM announcement_duplicate_log adl
JOIN announcement_pre_processing app ON adl.preprocessing_id = app.id
WHERE adl.duplicate_type = 'error'
LIMIT 5;
```

**발견**:
- announcement_duplicate_log에만 'error' 기록
- announcement_pre_processing에는 'archived', '성공', '제외'
- **실제로는 오류가 아님!**

### 왜 이런 일이 발생했나?

이전 분석에서 발견한 원인:
1. **DomainKeyExtractor 초기화 실패** → domain_has_config 항상 False
2. **잘못된 논리 검증** → processing_status='failed' 설정
3. **'failed' → 'error' 매핑** → duplicate_type='error' 기록

**하지만**:
- 실제 INSERT/UPDATE는 정상 작동
- announcement_pre_processing에는 정상 저장됨 ('성공', 'archived', '제외')
- **로그만 잘못 기록됨**

---

## ✅ 올바른 해결 방안

### 방안 1: duplicate_type='error'를 정확한 값으로 수정 (권장)

**목표**: 로그를 정확하게 기록

```python
# announcement_pre_processor.py:2141-2152

# ❌ 현재 코드
if not domain_has_config:
    processing_status = 'failed'  # → duplicate_type='error'

# ✅ 수정 코드 (Option A: API 데이터 예외)
if not domain_has_config:
    if self.site_type == 'api_scrap':
        # API 데이터는 외부 도메인 정상
        processing_status = 'new_inserted'  # → duplicate_type='new_inserted'
    else:
        # 지자체 데이터는 오류
        processing_status = 'failed'  # → duplicate_type='error'
```

**결과**:
- API 데이터 → duplicate_type='new_inserted' (정확)
- 실제 오류 → duplicate_type='error' (정확)

### 방안 2: 기존 잘못된 로그 수정

```sql
-- duplicate_type='error'이지만 실제로는 정상 처리된 것들
UPDATE announcement_duplicate_log
SET duplicate_type = 'new_inserted'
WHERE duplicate_type = 'error'
  AND preprocessing_id IN (
    SELECT id FROM announcement_pre_processing
    WHERE processing_status IN ('성공', 'archived', '제외')
  );
```

**결과**:
- 213건 중 대부분이 'new_inserted'로 변경됨
- 실제 오류만 'error'로 남음

### 방안 3: DomainKeyExtractor 초기화 수정 (필수)

```python
# announcement_pre_processor.py:67
engine = self.db_manager.SessionLocal().bind
db_config = {
    'host': engine.url.host,
    'user': engine.url.username,
    'password': engine.url.password,
    'database': engine.url.database,
    'port': engine.url.port,
    'charset': 'utf8mb4'
}
self.url_key_extractor = DomainKeyExtractor(db_config=db_config)
```

---

## ❌ '중복'이라는 용어를 사용하면 안 되는 이유

### 이유 1: 의미 불명확

**질문**: "중복"이 무엇을 의미하는가?
- 중복이 **감지**됨? (상태)
- 중복 **처리**됨? (동작)
- 중복으로 **실패**함? (결과)

**현재 시스템**:
- 중복 감지는 **정상 동작**
- 중복 처리 결과는 여러 가지:
  - 'new_inserted': 중복 아님
  - 'replaced': 중복 감지 + 교체
  - 'kept_existing': 중복 감지 + 유지
  - 'same_type_duplicate': 중복 감지 + 동일 타입
  - 'error': 오류

### 이유 2: 로직 혼란

```python
# 만약 processing_status='중복'을 추가한다면?

if processing_status == '성공':
    # 정상 처리
elif processing_status == '제외':
    # 제외됨
elif processing_status == 'error':
    # 오류 발생
elif processing_status == '중복':  # ← 이게 무엇?
    # ???
```

**문제**:
- 중복은 오류인가? 성공인가?
- 중복 처리 결과를 어떻게 표시하나?
- 교체/유지를 구분하나?

### 이유 3: 중복 정보는 이미 존재

**announcement_duplicate_log 테이블**이 바로 중복 정보를 기록하는 곳!

```sql
SELECT
    duplicate_type,
    new_site_type,
    existing_site_type,
    new_priority,
    existing_priority
FROM announcement_duplicate_log
WHERE preprocessing_id = ?;
```

**현재 시스템 설계**:
- `announcement_pre_processing.processing_status` = **최종 처리 상태**
- `announcement_duplicate_log.duplicate_type` = **중복 상세 정보**

→ 역할 분담이 명확함

---

## 🎓 올바른 용어 체계

### announcement_pre_processing.processing_status (사용자용)

**의미**: 해당 공고가 어떻게 처리되었는가?

| 값 | 의미 | 사용자 이해 |
|----|------|-----------|
| "성공" | 정상 처리됨 | ✅ 사용 가능 |
| "제외" | 제외됨 | ✅ 사용 불가 (제외 키워드) |
| "error" | 처리 실패 | ❌ 오류 발생 |
| "archived" | 보관됨 | 📦 아카이브 |

**"중복" 추가 시**:
- ❓ 사용 가능한가? 불가능한가?
- ❓ 어떤 데이터가 최종 사용되는가?
- ❓ 교체/유지를 어떻게 구분하나?

### announcement_duplicate_log.duplicate_type (시스템용)

**의미**: 중복 처리 상세 정보

| 값 | 의미 | 최종 processing_status |
|----|------|----------------------|
| new_inserted | 신규 삽입 | "성공" |
| replaced | 교체됨 | "성공" |
| kept_existing | 유지됨 | "성공" |
| same_type_duplicate | 동일 타입 | "성공" |
| unconfigured_domain | 설정 없음 | "성공" |
| error | 오류 | "error" (실제 오류만) |

→ 중복 정보는 여기에 상세하게 기록됨

---

## 📊 제안: 사용자 인터페이스 개선

만약 사용자가 "중복 여부"를 쉽게 알고 싶다면:

### 방안 A: VIEW 생성

```sql
CREATE VIEW announcement_processing_with_duplicate AS
SELECT
    app.*,
    CASE
        WHEN adl.duplicate_type IN ('replaced', 'kept_existing', 'same_type_duplicate') THEN '중복처리'
        WHEN adl.duplicate_type = 'new_inserted' THEN '신규'
        WHEN adl.duplicate_type = 'error' THEN '오류'
        ELSE app.processing_status
    END AS duplicate_status
FROM announcement_pre_processing app
LEFT JOIN announcement_duplicate_log adl ON app.id = adl.preprocessing_id;
```

### 방안 B: 컬럼 추가 (비권장)

```sql
ALTER TABLE announcement_pre_processing
ADD COLUMN is_duplicate BOOLEAN DEFAULT FALSE;
```

**하지만**:
- ❌ 중복 정보 중복 저장
- ❌ announcement_duplicate_log와 불일치 가능성
- ❌ 불필요한 복잡성 증가

---

## 🎯 최종 권장 사항

### ✅ 해야 할 것

#### 1. DomainKeyExtractor 초기화 수정 (필수)
```python
self.url_key_extractor = DomainKeyExtractor(db_config=db_config)
```

#### 2. 논리 검증 개선 (필수)
```python
if not domain_has_config:
    if self.site_type == 'api_scrap':
        processing_status = 'new_inserted'
    else:
        processing_status = 'failed'
```

#### 3. 기존 잘못된 로그 수정 (권장)
```sql
UPDATE announcement_duplicate_log
SET duplicate_type = 'new_inserted'
WHERE duplicate_type = 'error'
  AND preprocessing_id IN (
    SELECT id FROM announcement_pre_processing
    WHERE processing_status != 'error'
  );
```

### ❌ 하지 말아야 할 것

#### 1. processing_status='중복' 추가 (비권장)
**이유**:
- 의미 불명확 (성공? 실패?)
- 기존 체계 파괴
- 중복 정보는 이미 announcement_duplicate_log에 존재

#### 2. duplicate_type='error' → '중복' 변경 (비권장)
**이유**:
- 실제 오류와 중복을 구분할 수 없음
- 'error'는 실제 오류를 의미해야 함

---

## 🔍 사용자가 고려해야 할 사항

### 질문 1: '중복'을 왜 표시하고 싶은가?

**목적별 해결책**:

#### 목적 A: 중복 건수 파악
```sql
-- announcement_duplicate_log 활용
SELECT
    duplicate_type,
    COUNT(*) as count
FROM announcement_duplicate_log
WHERE duplicate_type IN ('replaced', 'kept_existing', 'same_type_duplicate')
GROUP BY duplicate_type;
```

#### 목적 B: 사용자에게 중복 표시
```sql
-- VIEW 생성
CREATE VIEW announcement_status_view AS
SELECT
    app.*,
    CASE
        WHEN adl.duplicate_type IS NULL THEN app.processing_status
        WHEN adl.duplicate_type = 'new_inserted' THEN '신규'
        WHEN adl.duplicate_type IN ('replaced', 'kept_existing', 'same_type_duplicate') THEN '중복(정상처리)'
        ELSE app.processing_status
    END AS display_status
FROM announcement_pre_processing app
LEFT JOIN announcement_duplicate_log adl ON app.id = adl.preprocessing_id;
```

#### 목적 C: 중복 상세 정보
```sql
-- announcement_duplicate_log의 duplicate_detail 활용
SELECT
    app.folder_name,
    app.processing_status,
    adl.duplicate_type,
    adl.duplicate_detail
FROM announcement_pre_processing app
JOIN announcement_duplicate_log adl ON app.id = adl.preprocessing_id
WHERE adl.duplicate_type != 'new_inserted';
```

### 질문 2: 현재 'error' 로그가 문제인가?

**현재 상황**:
- duplicate_type='error' 213건
- 실제로는 정상 처리됨 (archived, 성공, 제외)
- **로그 기록 오류**

**해결책**:
1. 코드 수정 (DomainKeyExtractor + 논리 검증)
2. 기존 로그 수정 (SQL UPDATE)
3. 신규 데이터는 정확하게 기록됨

→ **'중복'이 아니라 'new_inserted'가 맞음**

---

## 📋 결론

### 사용자 제안: "processing_status에 'error' 대신 '중복'"

**판단**: ❌ **권장하지 않음**

**이유**:
1. **의미 불명확**: '중복'이 성공인지 실패인지 불분명
2. **로직 혼란**: 중복 처리 결과는 여러 가지 (교체/유지/동일)
3. **중복 정보 존재**: announcement_duplicate_log에 이미 상세 정보 있음
4. **실제 문제 오진**: 문제는 'error'가 아니라 **잘못된 'error' 기록**

### 올바른 해결책

1. **DomainKeyExtractor 초기화** (근본 원인)
2. **논리 검증 개선** (API 데이터 예외 처리)
3. **기존 로그 수정** (잘못 기록된 'error' → 'new_inserted')
4. **사용자 인터페이스** (필요 시 VIEW 생성)

### 추가 고려사항

**만약 정말 '중복' 표시가 필요하다면**:
- announcement_pre_processing.processing_status는 건드리지 말 것
- 대신 VIEW를 생성하여 표시 용도로 사용
- announcement_duplicate_log를 활용

---

**작성일**: 2025-11-05
**작성자**: AI Assistant
