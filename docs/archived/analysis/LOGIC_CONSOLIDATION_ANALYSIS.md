# 중복 체크 로직 통합 분석

## 현재 상태

### 1930라인: 기존 예외 로직 (구현 시점: 과거)
```python
if site_code == 'smes24' and origin_url and 'bizinfo.go.kr' in origin_url.lower():
    # bizInfo의 scraping_url == smes24의 origin_url 체크
    existing_bizinfo = session.execute(
        "SELECT ... WHERE scraping_url = :origin_url AND site_code = 'bizInfo'"
    )
    if existing_bizinfo:
        return existing_bizinfo.id  # 스킵
```

**커버하는 케이스**:
- smes24가 들어올 때
- origin_url에 'bizinfo.go.kr' 포함
- bizInfo의 scraping_url과 일치하는 경우

**예시**:
- smes24: origin_url = "https://www.bizinfo.go.kr/...PBLN_00"
- bizInfo: scraping_url = "https://www.bizinfo.go.kr/...PBLN_00"
→ 스킵

---

### 1964라인: 신규 일반 로직 (구현 시점: 지금)
```python
if site_code in ['bizInfo', 'smes24', 'kStartUp'] and scraping_url:
    # scraping_url이 동일한 모든 케이스 체크
    existing_by_scraping = session.execute(
        "SELECT ... WHERE scraping_url = :scraping_url AND site_code != :current_site_code"
    )
    if existing_by_scraping:
        # 우선순위 비교 후 스킵
```

**커버하는 케이스**:
1. bizInfo vs smes24 (양방향)
2. bizInfo vs kStartUp (양방향)
3. smes24 vs kStartUp (양방향)
4. **1930라인 케이스도 포함** ✅

**예시**:
- 케이스 A: smes24 scraping_url = bizInfo scraping_url → 스킵
- 케이스 B: bizInfo scraping_url = smes24 scraping_url → bizInfo 우선
- 케이스 C: kStartUp scraping_url = bizInfo scraping_url → bizInfo 우선

---

## 문제점

### 1. 로직 중복
- **1930라인 로직은 1964라인에 포함됨**
- 같은 체크를 두 번 수행 (비효율)

### 2. 일관성 부족
- 1930: origin_url 기반 체크
- 1964: scraping_url 기반 체크
- 의도는 같지만 구현이 다름

### 3. 유지보수 어려움
- 두 로직의 관계가 명확하지 않음
- 향후 수정 시 두 곳 모두 수정 필요

---

## 해결 방안

### 옵션 1: 기존 로직(1930) 제거 ✅ 권장
```python
# 1930라인 삭제 또는 주석 처리
# if site_code == 'smes24' and origin_url and 'bizinfo.go.kr' in origin_url.lower():
#     ... (구 로직)

# 1964라인만 유지 (모든 케이스 커버)
if site_code in ['bizInfo', 'smes24', 'kStartUp'] and scraping_url:
    ... (신규 로직)
```

**장점**:
- 중복 제거
- 단일 진실 공급원 (Single Source of Truth)
- 유지보수 용이

**단점**:
- 없음 (1964 로직이 완전히 포함함)

---

### 옵션 2: 기존 로직(1930) 유지 (현재 상태)
```python
# 1930라인 유지
if site_code == 'smes24' and origin_url and 'bizinfo.go.kr' in origin_url.lower():
    ... (구 로직 - 빠른 체크)

# 1964라인 유지
if site_code in ['bizInfo', 'smes24', 'kStartUp'] and scraping_url:
    ... (신규 로직 - 포괄적 체크)
```

**장점**:
- 1930라인이 먼저 실행되어 일부 케이스는 빠르게 처리
- 기존 동작 완전 보존

**단점**:
- 로직 중복
- 혼란 가능성
- 유지보수 복잡

---

### 옵션 3: 기존 로직(1930)을 주석으로 보존
```python
# ================================================
# ⚠️ DEPRECATED: 아래 로직은 1964라인에 통합됨
# ================================================
# if site_code == 'smes24' and origin_url and 'bizinfo.go.kr' in origin_url.lower():
#     try:
#         existing_bizinfo = session.execute(...)
#         ...
#     except Exception as e:
#         logger.error(...)

# ================================================
# 🆕 API 사이트: scraping_url 기반 중복 체크 (통합 버전)
# ================================================
if site_code in ['bizInfo', 'smes24', 'kStartUp'] and scraping_url:
    ... (신규 로직)
```

**장점**:
- 히스토리 보존
- 의도 명확
- 단일 로직 유지

**단점**:
- 주석이 길어짐

---

## 검증

### 1930라인이 1964라인에 포함되는지 확인

#### 테스트 케이스: ID 12490(bizInfo) vs 12639(smes24)

**1930라인 체크 (구 로직)**:
```
조건: site_code == 'smes24' AND 'bizinfo.go.kr' in origin_url
smes24(12639): origin_url = "https://www.bizinfo.go.kr/...PBLN_00" ✅
→ bizInfo의 scraping_url 검색
→ 12490 발견 → 스킵
```

**1964라인 체크 (신규 로직)**:
```
조건: site_code in ['bizInfo', 'smes24', 'kStartUp'] AND scraping_url exists
smes24(12639): scraping_url = "https://www.bizinfo.go.kr/...PBLN_00" ✅
→ 동일 scraping_url 검색
→ 12490(bizInfo) 발견 → 우선순위 비교 → 스킵
```

**결론**: ✅ 신규 로직이 기존 케이스를 완전히 커버

---

## 권장 조치

### 즉시 조치
1. **1930라인 로직 주석 처리** (DEPRECATED 마킹)
2. 1964라인 로직만 활성화
3. 1주일 모니터링

### 검증 기간 후
- 문제 없으면 1930라인 완전 삭제

### 롤백 시나리오
- 문제 발생 시 1930라인 주석 해제

---

## 코드 변경 예시

### Before (현재)
```python
# Line 1926-1957
if site_code == 'smes24' and origin_url and 'bizinfo.go.kr' in origin_url.lower():
    # ... 기존 로직

# Line 1959-2065
if site_code in ['bizInfo', 'smes24', 'kStartUp'] and scraping_url:
    # ... 신규 로직
```

### After (권장)
```python
# Line 1926-1957
# ================================================
# ⚠️ DEPRECATED (2025-11-07): 아래 로직은 1964라인의 통합 로직으로 대체됨
# 1964라인이 모든 API 간 scraping_url 중복을 포괄적으로 처리
# ================================================
# if site_code == 'smes24' and origin_url and 'bizinfo.go.kr' in origin_url.lower():
#     try:
#         existing_bizinfo = session.execute(
#             text("""
#                 SELECT id, site_type, site_code, folder_name, url_key, created_at
#                 FROM announcement_pre_processing
#                 WHERE scraping_url = :origin_url
#                 AND site_code = 'bizInfo'
#                 LIMIT 1
#             """),
#             {"origin_url": origin_url}
#         ).fetchone()
#
#         if existing_bizinfo:
#             logger.info(
#                 f"🚫 중복 스킵 (예외 로직): smes24 origin_url이 bizInfo scraping_url과 일치\n"
#                 f"   smes24 folder: {folder_name}\n"
#                 f"   origin_url: {origin_url[:100]}...\n"
#                 f"   기존 bizInfo: ID={existing_bizinfo.id}, folder={existing_bizinfo.folder_name}\n"
#                 f"   기존 url_key: {existing_bizinfo.url_key}\n"
#                 f"   → bizInfo 우선 (지자체 원본 데이터 유지)"
#             )
#
#             return existing_bizinfo.id  # 기존 ID 반환하고 종료
#
#     except Exception as e:
#         logger.error(f"예외 케이스 중복 체크 실패 (계속 진행): {e}")
#         # 에러 발생 시 기존 로직으로 폴백

# Line 1959-2065 (신규 통합 로직)
if site_code in ['bizInfo', 'smes24', 'kStartUp'] and scraping_url:
    # ... 신규 로직 (모든 케이스 포함)
```

---

## 성능 영향

### 기존 로직 제거 시
- **쿼리 수**: 2회 → 1회 (50% 감소)
- **처리 시간**: 미미한 개선 (ms 단위)
- **메모리**: 변화 없음

### 결론
- 성능 저하 없음
- 오히려 쿼리 감소로 미세 개선
