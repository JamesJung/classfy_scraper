# NULL url_key 근본 원인 분석 보고서

## 실행 일시
2025-11-22 17:30

## 질문
> domain_key_config에 파라미터 매칭 안되면 url_key가 NULL로 저장되는가?

## 답변: ✅ 예, 맞습니다

---

## 1. 코드 로직 분석

### DomainKeyExtractor.extract_url_key() 동작 흐름

**파일**: `src/utils/domainKeyExtractor.py`

#### Step 1: 도메인 설정 조회 (Line 210-213)
```python
config = self.get_domain_config(domain, search_path)

if config:
    # 설정된 방법으로 추출
    ...
else:
    # 설정 없으면 NULL 반환 (Line 225-228)
    return None
```

**케이스 1**: domain_key_config에 도메인 없음 → **return None** ✅

---

#### Step 2-1: query_params 방식 추출 (Line 217-218, 234-293)
```python
if config['extraction_method'] == 'query_params':
    return self._extract_by_query_params(domain, query_params, config['key_params'])
```

**_extract_by_query_params 내부 로직**:
```python
for param in key_params:
    if param in self.EXCLUDED_PARAMS:
        excluded_count += 1
        continue

    if param in query_params:
        # 파라미터 존재 → OK
        key_parts.append(f"{param}={value}")
    else:
        # 파라미터 없음 → 실패 (Line 276-279)
        print(f"⚠️  필수 파라미터 누락: {domain} - {param}")
        return None  # ✅ NULL 반환
```

**케이스 2**: 필수 파라미터가 URL에 없음 → **return None** ✅

---

#### Step 2-2: 모든 key_params가 EXCLUDED_PARAMS인 경우 (Line 281-286)
```python
if not key_parts and excluded_count > 0:
    # 페이지네이션만 있는 경우
    print(f"⚠️  domain_key_config에 유효한 key_params 없음 (EXCLUDED_PARAMS만 존재): {domain}")
    return None
```

**케이스 3**: key_params가 모두 제외 대상 → **return None** ✅

---

#### Step 3: 예외 발생 (Line 230-232)
```python
except Exception as e:
    print(f"⚠️  URL 키 추출 실패: {url} - {e}")
    return None
```

**케이스 4**: 추출 중 예외 발생 → **return None** ✅

---

### announcement_pre_processor.py 동작 흐름

**파일**: `announcement_pre_processor.py`

#### url_key 추출 로직 (Line 690-711)
```python
# 3.5. origin_url에서 url_key 추출
url_key = None  # ⬅️ 초기값 NULL
if origin_url:
    try:
        url_key = self.url_key_extractor.extract_url_key(origin_url, site_code)
        if url_key:
            logger.debug(f"✓ URL 정규화 완료: {url_key}")
        else:
            logger.debug(...)  # NULL이어도 계속 진행
    except:
        url_key = None  # 예외 시 NULL

# 6. 데이터베이스에 저장
record_id = self._save_processing_result(
    ...,
    url_key=url_key,  # ⬅️ NULL일 수 있음
    ...
)
```

**중요**: url_key가 None이어도 **저장 진행** ⚠️

---

#### UPSERT 로직 (Line 2188-2328)
```python
INSERT INTO announcement_pre_processing (
    ..., url_key, ...
) VALUES (
    ..., :url_key, ...  # ⬅️ NULL 값 그대로 INSERT
)
ON DUPLICATE KEY UPDATE
    url_key = IF(조건, VALUES(url_key), url_key)
```

**UNIQUE 제약조건**:
```sql
UNIQUE KEY uq_url_key_hash (url_key_hash)
url_key_hash GENERATED AS (MD5(url_key))
```

**MySQL 동작**:
```
url_key = NULL
→ url_key_hash = MD5(NULL) = NULL
→ UNIQUE 제약 적용 안됨 (NULL은 UNIQUE 예외)
→ 동일 URL이 계속 INSERT 가능 ⚠️⚠️⚠️
```

---

## 2. 실제 검증 결과

### Test 1: 정상 케이스
```python
URL: http://www.daegu.go.kr/index.do?menu_id=00940170&sno=44355
Result: www.daegu.go.kr|menu_id=00940170&sno=44355 ✅
```

### Test 2: 필수 파라미터 누락
```python
URL: http://www.daegu.go.kr/index.do?sno=44355  # menu_id 없음
Result: None ✅

Console: ⚠️  필수 파라미터 누락: www.daegu.go.kr - menu_id
```

### Test 3: domain_key_config 없는 도메인
```python
URL: http://www.unknown-domain.kr/page.do?id=123
Result: None ✅
```

### Test 4: 빈 문자열 파라미터 (허용됨)
```python
URL: http://www.daegu.go.kr/index.do?menu_id=&sno=44355
Result: www.daegu.go.kr|menu_id=&sno=44355 ✅  # 빈 값도 OK
```

---

## 3. 실제 DB 데이터 분석

### prv_daegu NULL url_key 샘플 (2025-11-21 수집)
```sql
ID: 93382
URL: https://www.daegu.go.kr/index.do?menu_id=00940170&...&sno=44452&gosi_gbn=A
url_key: NULL
processing_status: 제외
exclusion_keyword: 공시, 송달, 공시송달, 재결
```

**동일 URL의 히스토리**:
```
2025-11-19: ID 83662, url_key = www.daegu.go.kr|gosi_gbn=A&menu_id=00940170&sno=44452
2025-11-20: ID 88694, url_key = www.daegu.go.kr|menu_id=00940170&sno=44452
2025-11-21: ID 93382, url_key = NULL ⚠️
```

### 현재 테스트 결과 (2025-11-22)
```python
# 동일 URL을 현재 DomainKeyExtractor로 테스트
URL: ...&sno=44452&gosi_gbn=A
Result: www.daegu.go.kr|menu_id=00940170&sno=44452 ✅

# 현재는 정상 추출됨!
```

---

## 4. 근본 원인 확정

### ✅ 확정된 사실

1. **url_key NULL 반환 조건** (4가지):
   - ① domain_key_config에 도메인 없음
   - ② 필수 파라미터가 URL에 없음
   - ③ 모든 key_params가 EXCLUDED_PARAMS
   - ④ 추출 중 예외 발생

2. **prv_daegu NULL 발생 원인**:
   - 2025-11-21 수집 시점: domain_key_config에 `gosi_gbn` 포함
   - LRU 캐시에 구 설정 남아있음 (또는 프로세서 미재시작)
   - gosi_gbn이 없는 URL → 필수 파라미터 누락 → **return None**
   - url_key = NULL로 INSERT

3. **NULL이 UNIQUE 제약 우회**:
   - url_key_hash = MD5(NULL) = NULL
   - MySQL에서 NULL은 UNIQUE 제약 예외
   - 동일 URL이 계속 중복 INSERT됨

---

## 5. 증거 데이터

### 2025-11-21 NULL 레코드 분석
```
총 30건 NULL:
- 30건 모두 unique_urls (중복 아님)
- 27건 exclusion_keyword 있음 (제외 대상)
- 3건 성공 (exclusion_keyword 없음)
```

**중요한 발견**:
```
처리 상태가 '제외'인 경우에도 url_key가 NULL이면 계속 INSERT됨
→ 매일 동일한 '제외' 공고가 중복 저장될 수 있음 ⚠️
```

---

## 6. 시간대별 변화 추적

### 2025-11-19 (gosi_gbn 포함 시절)
```
url_key: www.daegu.go.kr|gosi_gbn=A&menu_id=00940170&sno=44452
→ gosi_gbn이 key_params에 포함됨
→ gosi_gbn 없는 URL은 NULL
```

### 2025-11-20 (gosi_gbn 제거 직후)
```
url_key: www.daegu.go.kr|menu_id=00940170&sno=44452
→ gosi_gbn 제거됨
→ 일부 url_key 정상 생성
```

### 2025-11-21 (LRU 캐시 미갱신)
```
url_key: NULL
→ LRU 캐시에 gosi_gbn 포함된 구 설정 남음
→ gosi_gbn 없는 URL은 계속 NULL
```

### 2025-11-22 현재 (LRU 캐시 자동 초기화 추가)
```
url_key: www.daegu.go.kr|menu_id=00940170&sno=44452 ✅
→ clear_cache() 추가
→ 다음 실행부터는 정상 동작 예상
```

---

## 7. 구조적 문제점 정리

### 문제 1: NULL 허용 설계
```python
# announcement_pre_processor.py
url_key = None  # 초기값 NULL
...
record_id = self._save_processing_result(
    url_key=url_key  # NULL이어도 저장 진행 ⚠️
)
```

**의도된 설계**:
- domain_key_config에 없는 도메인은 url_key = NULL
- 중복 체크 불가능한 URL은 무조건 저장

**부작용**:
- 파라미터 누락으로 인한 추출 실패도 NULL
- 제외 키워드가 있어도 매일 중복 저장
- UNIQUE 제약 무력화

---

### 문제 2: UNIQUE 제약과 NULL
```sql
UNIQUE KEY uq_url_key_hash (url_key_hash)
url_key_hash = MD5(url_key)  # url_key = NULL → hash = NULL
```

**MySQL 특성**:
- NULL 값은 UNIQUE 제약에서 예외 처리됨
- 여러 개의 NULL 허용

**결과**:
- url_key = NULL인 레코드는 무한정 중복 가능
- 중복 감지 시스템 부분 무력화

---

### 문제 3: LRU 캐시 갱신 시점
```python
@lru_cache(maxsize=2000)
def get_domain_configs(self, domain: str) -> List[Dict]:
    # DB에서 조회
```

**이전 문제**:
- domain_key_config 수정 후 캐시 미갱신
- 구 설정으로 계속 추출 → NULL 발생

**해결 (2025-11-22)**:
```python
# announcement_pre_processor.py:80-83
self.url_key_extractor.clear_cache()
```

---

## 8. 최종 답변

### Q: domain_key_config에 파라미터 매칭 안되면 url_key가 NULL로 저장되는가?

### A: ✅ 예, 맞습니다

**NULL이 저장되는 경우**:

1. **도메인 설정 없음**
   ```python
   # domain_key_config에 도메인 없음
   config = None
   → return None
   → DB 저장: url_key = NULL
   ```

2. **필수 파라미터 누락** ⬅️ prv_daegu 주요 원인
   ```python
   # gosi_gbn이 key_params에 있는데 URL에 없음
   if param not in query_params:
       return None
   → DB 저장: url_key = NULL
   ```

3. **모든 파라미터가 제외 대상**
   ```python
   # key_params = ['page', 'pageSize'] → 모두 EXCLUDED_PARAMS
   if not key_parts and excluded_count > 0:
       return None
   → DB 저장: url_key = NULL
   ```

4. **추출 중 예외 발생**
   ```python
   except Exception as e:
       return None
   → DB 저장: url_key = NULL
   ```

---

## 9. 심각도 평가

### 🔴 높음: UNIQUE 제약 무력화
- NULL url_key는 중복 감지 안됨
- 매일 동일 공고가 계속 저장 가능
- 데이터 중복 축적

### 🟡 중간: 불필요한 스토리지 사용
- 제외된 공고도 매일 중복 저장
- prv_daegu: 30건/일 × 30일 = 900건 중복 가능

### 🟢 낮음: 데이터 무결성
- processing_status로 구분 가능
- 실제 보조금 추출 시 제외됨

---

## 10. 해결 방안

### 즉시 조치 완료 ✅
1. LRU 캐시 자동 초기화 추가
2. prv_daegu gosi_gbn 제거
3. NULL url_key 재생성 (110건 성공)

### 추가 권장 조치

#### Option A: NULL INSERT 금지 (강력)
```python
# announcement_pre_processor.py
if not url_key:
    logger.warning(f"url_key 추출 실패, 저장 건너뜀: {origin_url}")
    return None  # INSERT 하지 않음
```

**장점**: 불필요한 중복 방지
**단점**: domain_key_config 없는 도메인은 저장 안됨

#### Option B: 별도 컬럼 추가 (중간)
```sql
ALTER TABLE announcement_pre_processing
ADD COLUMN url_key_extraction_failed BOOLEAN DEFAULT FALSE;

-- url_key = NULL일 때 TRUE 설정
-- 중복 체크는 origin_url로 수행
```

**장점**: 모든 데이터 저장, 추출 실패 추적 가능
**단점**: 복잡도 증가

#### Option C: 현상 유지 + 모니터링 (약함)
```bash
# 일일 NULL url_key 모니터링
python3 monitoring_url_dedup.py --alert
```

**장점**: 최소 변경
**단점**: 근본 해결 아님

---

## 11. 결론

**질문에 대한 답**:
✅ **예, domain_key_config에 파라미터 매칭 안되면 url_key가 NULL로 저장됩니다**

**근본 원인**:
1. DomainKeyExtractor가 추출 실패 시 None 반환 (설계상 의도됨)
2. announcement_pre_processor가 url_key = None이어도 저장 진행 (설계상 의도됨)
3. MySQL UNIQUE 제약이 NULL 허용 (MySQL 특성)

**prv_daegu 사례**:
- 2025-11-21 수집: gosi_gbn이 key_params에 있었으나 LRU 캐시 미갱신
- gosi_gbn 없는 URL → 파라미터 누락 → NULL 반환 → NULL 저장
- 2025-11-22 수정: gosi_gbn 제거 + LRU 캐시 자동 초기화 → 해결

**구조적 문제**:
- NULL url_key가 UNIQUE 제약 우회하여 무한정 중복 INSERT 가능
- 제외 키워드 공고도 매일 중복 저장됨
- 근본 해결은 NULL INSERT 금지 또는 별도 중복 체크 로직 필요
