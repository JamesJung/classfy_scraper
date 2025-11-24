# Regenerate 스크립트 중복 체크 로직 추가 완료

**작성일**: 2025-11-22
**목적**: url_key 재생성 시 UNIQUE 제약 위반 에러 재발 방지

---

## 🔴 문제 상황

### 예전 에러 (url_key_regeneration.log)
```
pymysql.err.IntegrityError: (1062, "Duplicate entry '6f16e19e336a0aa4dc32cb5b35d369f3' for key 'uk_url_key_hash'")
```

**원인:**
- 모든 regenerate 스크립트가 단순 `UPDATE` 쿼리 사용
- UPDATE로 url_key를 변경하면 url_key_hash도 자동 변경 (GENERATED COLUMN)
- 변경된 url_key_hash가 다른 레코드와 충돌 시 UNIQUE 제약 위반

**예시:**
```
레코드 A: id=100, url_key='www.test.kr|id=1', url_key_hash='abc123'
레코드 B: id=200, url_key='www.test.kr|id=2', url_key_hash='def456'

# regenerate 스크립트 실행
UPDATE ... SET url_key='www.test.kr|id=1' WHERE id=200

# url_key_hash가 'abc123'으로 변경됨 → 레코드 A와 충돌!
❌ IntegrityError: Duplicate entry 'abc123' for key 'uq_url_key_hash'
```

---

## ✅ 해결 방법: 사전 중복 체크 추가

### 기존 코드 (문제)
```python
# 단순 UPDATE만 실행
UPDATE table_name
SET url_key = new_url_key
WHERE id = record_id
```
- 중복 발생 시 **IntegrityError 발생**
- 스크립트 중단

### 수정 코드 (해결)
```python
# 1. 중복 체크: 변경할 url_key_hash가 이미 다른 레코드에 존재하는지 확인
SELECT id FROM table_name
WHERE url_key_hash = MD5(new_url_key) AND id != record_id
LIMIT 1

if duplicate_record:
    # 중복 발견, 스킵
    print("⚠️  중복 url_key_hash 발견, 스킵")
    failed_count += 1
    continue

# 2. 중복 없으면 안전하게 UPDATE
UPDATE table_name
SET url_key = new_url_key
WHERE id = record_id
```
- 중복 발생 시 **미리 감지하여 스킵**
- 스크립트 계속 진행
- 안전한 레코드만 업데이트

---

## 📝 수정 완료된 스크립트

| # | 파일명 | 대상 테이블 | 수정 위치 |
|---|--------|------------|----------|
| 1 | `regenerate_url_keys.py` | announcement_pre_processing<br>api_url_registry | 라인 212-240<br>라인 296-323 |
| 2 | `regenerate_all_url_keys.py` | api_url_registry | 라인 88-107 |
| 3 | `regenerate_mixed_url_keys.py` | announcement_pre_processing | 라인 80-107 |
| 4 | `regenerate_aict_url_keys.py` | api_url_registry | 라인 147-169 |
| 5 | `regenerate_affected_url_keys.py` | api_url_processing_log | 라인 197-233 |

---

## 🔍 수정 상세 내용

### 1. regenerate_url_keys.py

**대상 테이블**: `announcement_pre_processing`, `api_url_registry`

**수정 내용**:
- 2개 함수에 각각 중복 체크 로직 추가
  - `regenerate_announcement_pre_processing()` (라인 212-240)
  - `regenerate_api_url_registry()` (라인 296-323)

**수정 코드**:
```python
# 1. 중복 체크
check_sql = f"""
    SELECT id FROM {table_name}
    WHERE url_key_hash = MD5(%s) AND id != %s
    LIMIT 1
"""
self.cursor.execute(check_sql, (new_url_key, row_id))
duplicate_record = self.cursor.fetchone()

if duplicate_record:
    # 중복 발견, 스킵
    print(f"  ⚠️  중복 url_key_hash 발견, 스킵 (id={row_id}, 충돌 id={duplicate_record[0]})")
    self.stats[table_name]['failed'] += 1
    continue

# 2. 안전하게 UPDATE
update_sql = f"UPDATE {table_name} SET url_key = %s WHERE id = %s"
self.cursor.execute(update_sql, (new_url_key, row_id))
```

---

### 2. regenerate_all_url_keys.py

**대상 테이블**: `api_url_registry`

**수정 내용**:
- url_key 변경 전 중복 체크 추가 (라인 88-107)

**수정 코드**:
```python
# 1. 중복 체크
cursor.execute('''
    SELECT id FROM api_url_registry
    WHERE url_key_hash = MD5(%s) AND id != %s
    LIMIT 1
''', (new_url_key, record_id))
duplicate_record = cursor.fetchone()

if duplicate_record:
    # 중복 발견, 스킵
    fail_count += 1
else:
    # 2. 안전하게 UPDATE
    cursor.execute('''
        UPDATE api_url_registry
        SET url_key = %s
        WHERE id = %s
    ''', (new_url_key, record_id))
    updated_count += 1
```

---

### 3. regenerate_mixed_url_keys.py

**대상 테이블**: `announcement_pre_processing`

**수정 내용**:
- SQLAlchemy 기반 중복 체크 추가 (라인 80-107)

**수정 코드**:
```python
# 1. 중복 체크
duplicate_check = conn.execute(
    text("""
        SELECT id FROM announcement_pre_processing
        WHERE url_key_hash = MD5(:new_url_key) AND id != :id
        LIMIT 1
    """),
    {"new_url_key": new_url_key, "id": record.id}
)
duplicate_record = duplicate_check.fetchone()

if duplicate_record:
    # 중복 발견, 스킵
    print(f"  ⚠️  중복 url_key_hash 발견, 스킵 (ID {record.id}, 충돌 ID {duplicate_record[0]})")
    failed_count += 1
    continue

# 2. 안전하게 UPDATE
conn.execute(
    text("UPDATE announcement_pre_processing SET url_key = :new_url_key WHERE id = :id"),
    {"new_url_key": new_url_key, "id": record.id}
)
```

---

### 4. regenerate_aict_url_keys.py

**대상 테이블**: `api_url_registry`

**수정 내용**:
- 배치 업데이트 전 각 레코드별 중복 체크 (라인 147-169)

**수정 코드**:
```python
for update in updates:
    # 1. 중복 체크
    duplicate_check = session.execute(text("""
        SELECT id FROM api_url_registry
        WHERE url_key_hash = MD5(:new_url_key) AND id != :record_id
        LIMIT 1
    """), {
        'new_url_key': update['new_url_key'],
        'record_id': update['id']
    })
    duplicate_record = duplicate_check.fetchone()

    if duplicate_record:
        # 중복 발견, 스킵
        print(f"  ⚠️  중복 url_key_hash 발견, 스킵 (ID {update['id']}, 충돌 ID {duplicate_record[0]})")
        error_count += 1
        continue

    # 2. 안전하게 UPDATE
    session.execute(update_query, {
        'record_id': update['id'],
        'new_url_key': update['new_url_key']
    })
    success_count += 1
```

---

### 5. regenerate_affected_url_keys.py

**대상 테이블**: `api_url_processing_log`

**수정 내용**:
- url_key_hash 직접 계산 방식에서도 중복 체크 추가 (라인 197-233)

**수정 코드**:
```python
# 해시 계산
new_url_key_hash = hashlib.md5(new_url_key.encode('utf-8')).hexdigest()

# 1. 중복 체크
duplicate_check = session.execute(text("""
    SELECT id FROM api_url_processing_log
    WHERE url_key_hash = :url_key_hash AND id != :id
    LIMIT 1
"""), {
    'url_key_hash': new_url_key_hash,
    'id': record_id
})
duplicate_record = duplicate_check.fetchone()

if duplicate_record:
    # 중복 발견, 스킵
    print(f"⚠️  중복 url_key_hash 발견, 스킵 (ID {record_id}, 충돌 ID {duplicate_record[0]})")
    skip_count += 1
    continue

# 2. 안전하게 UPDATE
result = session.execute(text("""
    UPDATE api_url_processing_log
    SET url_key = :url_key, url_key_hash = :url_key_hash
    WHERE id = :id
"""), {
    'id': record_id,
    'url_key': new_url_key,
    'url_key_hash': new_url_key_hash
})
```

---

## 📊 수정 효과

### Before (수정 전)
```
중복 url_key_hash 발견 시:
❌ IntegrityError 발생
❌ 스크립트 중단
❌ 나머지 레코드 처리 불가
```

### After (수정 후)
```
중복 url_key_hash 발견 시:
⚠️  중복 감지 및 스킵
✅ 스크립트 계속 진행
✅ 안전한 레코드만 업데이트
✅ 처리 통계에 실패 건수 기록
```

---

## 🧪 테스트 시나리오

### 시나리오 1: 정상 케이스
```
레코드 A: id=100, url_key='www.test.kr|id=1', url_key_hash='abc123'
레코드 B: id=200, url_key='www.test.kr|id=2', url_key_hash='def456'

# B의 url_key를 변경 (충돌 없음)
new_url_key = 'www.test.kr|id=3' → url_key_hash='ghi789'

1. 중복 체크: SELECT ... WHERE url_key_hash='ghi789' AND id != 200
   → 결과 없음 (중복 아님)
2. UPDATE 실행: id=200의 url_key를 'www.test.kr|id=3'으로 변경
3. ✅ 성공
```

### 시나리오 2: 중복 발견 케이스
```
레코드 A: id=100, url_key='www.test.kr|id=1', url_key_hash='abc123'
레코드 B: id=200, url_key='www.test.kr|id=2', url_key_hash='def456'

# B의 url_key를 A와 같은 값으로 변경 시도
new_url_key = 'www.test.kr|id=1' → url_key_hash='abc123'

1. 중복 체크: SELECT ... WHERE url_key_hash='abc123' AND id != 200
   → id=100 발견 (중복!)
2. ⚠️  중복 감지, 스킵
3. 다음 레코드 계속 처리
```

---

## 🔄 announcement_pre_processor.py는?

**수정 불필요!** 이미 `ON DUPLICATE KEY UPDATE` 사용 중

```python
# announcement_pre_processor.py (라인 2183-2323)
INSERT INTO announcement_pre_processing (...)
VALUES (...)
ON DUPLICATE KEY UPDATE
    folder_name = VALUES(folder_name),
    ...
```

**동작:**
- url_key 중복 시 → 자동으로 UPDATE 수행 (에러 없음)
- url_key 없으면 → INSERT 수행
- **IntegrityError 절대 발생하지 않음**

---

## ✅ 재발 방지 완료

| 구분 | Before | After |
|------|--------|-------|
| **regenerate 스크립트** | 단순 UPDATE<br>❌ 에러 발생 가능 | 사전 중복 체크<br>✅ 안전하게 스킵 |
| **announcement_pre_processor** | ON DUPLICATE KEY UPDATE<br>✅ 이미 안전 | (변경 없음) |

---

## 📋 체크리스트

- [x] regenerate_url_keys.py 수정
- [x] regenerate_all_url_keys.py 수정
- [x] regenerate_mixed_url_keys.py 수정
- [x] regenerate_aict_url_keys.py 수정
- [x] regenerate_affected_url_keys.py 수정
- [x] announcement_pre_processor.py 확인 (수정 불필요)
- [x] 수정 내용 문서화

---

## 🎯 다음 실행 시

모든 regenerate 스크립트를 실행할 때 이제 안전합니다:

```bash
# 예시
python3 regenerate_url_keys.py

# 중복 발견 시 출력 예시:
# ⚠️  중복 url_key_hash 발견, 스킵 (id=123, 충돌 id=456): url_key=www.test.kr|id=1
# ✅ 처리 완료: 변경 100개, 스킵 5개
```

---

**작성자**: Claude Code
**완료일**: 2025-11-22
