# aict.snu.ac.kr URL 패턴 분석 보고서

## 📋 요약

aict.snu.ac.kr 도메인에서 **2가지 서로 다른 URL 패턴**이 발견되었으며, 현재 시스템 설정은 하나의 패턴만 처리하도록 되어 있어 **일부 URL이 잘못된 url_key를 생성**하고 있습니다.

---

## 🔍 발견된 문제

### 문제 요약
- **현재 설정**: `domain_key_config`에 `["p", "reqIdx"]`만 등록
- **실제 패턴**: 2가지 URL 형태 존재
  1. `p` + `reqIdx` 조합 (19개)
  2. `p` + `idx` 조합 (1개)

### 영향 받는 레코드

#### ID 60122 (정상)
```
URL: https://aict.snu.ac.kr/?p=76&page=1&viewMode=view&reqIdx=202504101707579748
현재 url_key: www.k-startup.go.kr|pbancSn=172839 ❌ (잘못된 도메인)
올바른 url_key: aict.snu.ac.kr|p=76&reqIdx=202504101707579748
```

#### ID 60370 (문제)
```
URL: https://aict.snu.ac.kr/?p=265_view&idx=200&page=1
현재 url_key: www.k-startup.go.kr|pbancSn=172557 ❌ (잘못된 도메인)
올바른 url_key: aict.snu.ac.kr|p=265_view&idx=200
```

---

## 📊 데이터 분석 결과

### 1. URL 패턴 분포

| 패턴 | 파라미터 조합 | 개수 | 비율 |
|------|-------------|------|------|
| 패턴 A | `p=76` + `reqIdx=<timestamp>` | 19개 | 95% |
| 패턴 B | `p=265_view` + `idx=<number>` | 1개 | 5% |

### 2. 도메인 혼동 문제

현재 시스템에서 **aict.snu.ac.kr URL이 www.k-startup.go.kr로 잘못 인식**되는 문제가 있습니다:

```
📊 잘못된 url_key 분포:
- www.k-startup.go.kr|pbancSn=... (6개) ← aict.snu.ac.kr URL인데 k-startup으로 인식
- aict.snu.ac.kr|p=76&reqIdx=... (14개) ← 정상
```

### 3. domain_key_config 현재 설정

```
ID: 359
Site Code: (비어있음)
Domain: aict.snu.ac.kr
key_params: ["p", "reqIdx"]
```

**문제점**:
- `idx` 파라미터가 설정에 누락되어 있음
- `p=265_view&idx=200` 형태의 URL을 처리하지 못함

---

## 🎯 URL 패턴 상세 분석

### 패턴 A: `p` + `reqIdx` (대부분)

**특징**:
- `p` 값: 고정 (76)
- `reqIdx`: 타임스탬프 형식의 고유 ID (YYYYMMDDHHMMSSnnnn)
- 추가 파라미터: `page`, `viewMode` (url_key에는 미포함)

**예시**:
```
https://aict.snu.ac.kr/?p=76&page=1&viewMode=view&reqIdx=202504101707579748
→ url_key: aict.snu.ac.kr|p=76&reqIdx=202504101707579748
```

### 패턴 B: `p` + `idx` (소수)

**특징**:
- `p` 값: 페이지 식별자 + "_view" (예: 265_view)
- `idx`: 숫자 ID
- 추가 파라미터: `page` (url_key에는 미포함)

**예시**:
```
https://aict.snu.ac.kr/?p=265_view&idx=200&page=1
→ url_key: aict.snu.ac.kr|p=265_view&idx=200
```

---

## 🔧 대응 방안

### 방안 1: 복수 key_params 설정 (권장 ✅)

**방법**: `domain_key_config`에 두 가지 패턴을 모두 등록

```sql
-- 기존 레코드 업데이트
UPDATE domain_key_config
SET key_params = '["p", "reqIdx", "idx"]'
WHERE domain = 'aict.snu.ac.kr';
```

**장점**:
- 가장 간단하고 직관적
- 두 패턴 모두 자동 처리
- 추가 로직 불필요

**단점**:
- `reqIdx`와 `idx`가 동시에 없는 경우 처리 필요
- 현재 시스템이 OR 조건을 지원하는지 확인 필요

**처리 로직**:
```python
# domainKeyExtractor.py에서
if 'reqIdx' in params:
    url_key = f"{domain}|p={p_value}&reqIdx={reqIdx_value}"
elif 'idx' in params:
    url_key = f"{domain}|p={p_value}&idx={idx_value}"
```

---

### 방안 2: 조건부 key_params 적용

**방법**: URL에 따라 다른 key_params 사용

```sql
-- 패턴 A용 설정
INSERT INTO domain_key_config (site_code, domain, key_params)
VALUES ('kStartUp', 'aict.snu.ac.kr', '["p", "reqIdx"]');

-- 패턴 B용 설정 (또는 별도 처리)
-- URL에 idx가 있으면 ["p", "idx"] 사용
```

**장점**:
- 명확한 분리
- 각 패턴별 독립 관리

**단점**:
- 구현 복잡도 증가
- 동적 판단 로직 필요

---

### 방안 3: 정규식 기반 패턴 매칭

**방법**: URL 패턴을 정규식으로 식별하여 처리

```python
import re

def extract_aict_url_key(url):
    if re.search(r'reqIdx=\d+', url):
        # 패턴 A
        return extract_params(url, ['p', 'reqIdx'])
    elif re.search(r'p=\d+_view.*idx=\d+', url):
        # 패턴 B
        return extract_params(url, ['p', 'idx'])
```

**장점**:
- 복잡한 패턴도 정확히 처리
- 확장성 높음

**단점**:
- 구현 복잡
- 성능 오버헤드

---

## 🚨 추가 발견 사항

### 도메인 혼동 문제

**현상**:
```
aict.snu.ac.kr URL이 www.k-startup.go.kr로 잘못 인식되는 케이스 발견
```

**원인 추정**:
1. 리다이렉트: aict.snu.ac.kr → k-startup.go.kr 리다이렉트 발생?
2. Origin URL 추적: 원본 URL이 k-startup이고 aict는 중간 경유지?
3. 스크래핑 로직 오류: 잘못된 도메인 추출

**확인 필요**:
```bash
# URL이 실제로 리다이렉트되는지 확인
curl -I "https://aict.snu.ac.kr/?p=76&page=1&viewMode=view&reqIdx=202504101707579748"

# api_url_registry의 scrap_url 또는 origin_url 확인
SELECT id, scrap_url, announcement_url
FROM api_url_registry
WHERE id IN (60122, 60370);
```

---

## 💡 권장 해결 방안

### 단계별 접근

#### 1단계: domain_key_config 수정 (즉시)

```sql
-- 현재 설정 백업
SELECT * FROM domain_key_config WHERE domain = 'aict.snu.ac.kr';

-- key_params 업데이트
UPDATE domain_key_config
SET key_params = '["p", "reqIdx", "idx"]'
WHERE domain = 'aict.snu.ac.kr';
```

#### 2단계: url_key 재생성 (필수)

```bash
# aict.snu.ac.kr의 모든 URL url_key 재생성
python3 regenerate_url_keys.py --domain aict.snu.ac.kr --force
```

#### 3단계: 도메인 혼동 문제 조사 (중요)

```python
# 스크립트 작성: investigate_aict_domain_confusion.py
# - scrap_url과 announcement_url 비교
# - 리다이렉트 체인 추적
# - origin_url 확인
```

#### 4단계: domainKeyExtractor.py 로직 보강 (선택)

```python
def extract_url_key(url, domain, key_params):
    params = parse_qs(urlparse(url).query)

    # aict.snu.ac.kr 특수 처리
    if domain == 'aict.snu.ac.kr':
        p_value = params.get('p', [''])[0]

        # 패턴 A: reqIdx 우선
        if 'reqIdx' in params:
            reqIdx = params['reqIdx'][0]
            return f"{domain}|p={p_value}&reqIdx={reqIdx}"

        # 패턴 B: idx 사용
        elif 'idx' in params:
            idx = params['idx'][0]
            return f"{domain}|p={p_value}&idx={idx}"

    # 기본 로직
    return default_extract_logic(url, domain, key_params)
```

---

## 📈 예상 효과

### Before (현재)
```
❌ ID 60122: www.k-startup.go.kr|pbancSn=172839 (잘못된 도메인)
❌ ID 60370: www.k-startup.go.kr|pbancSn=172557 (잘못된 도메인, 누락 파라미터)
```

### After (수정 후)
```
✅ ID 60122: aict.snu.ac.kr|p=76&reqIdx=202504101707579748
✅ ID 60370: aict.snu.ac.kr|p=265_view&idx=200
```

---

## 🔍 후속 조치

1. **도메인 혼동 원인 파악**
   - `scrap_url` vs `announcement_url` 비교
   - 리다이렉트 체인 추적
   - 크롤링 로직 검토

2. **다른 도메인에도 유사 문제 있는지 조사**
   ```sql
   SELECT domain, key_params, COUNT(*) as url_count
   FROM domain_key_config dkc
   JOIN api_url_registry aur ON aur.announcement_url LIKE CONCAT('%', dkc.domain, '%')
   GROUP BY domain, key_params
   HAVING url_count > 1;
   ```

3. **url_key 검증 강화**
   - url_key의 도메인 부분이 실제 URL 도메인과 일치하는지 검증
   - 불일치 시 경고 로그

---

## 📝 결론

aict.snu.ac.kr은 **2가지 URL 패턴을 사용**하며, 현재 시스템은 하나의 패턴만 처리합니다.

**즉시 조치 필요**:
1. `domain_key_config`에 `idx` 파라미터 추가
2. 기존 20개 레코드의 `url_key` 재생성
3. 도메인 혼동 원인 조사 (k-startup vs aict)

**권장 방안**: 방안 1 (복수 key_params 설정)
- 구현 간단
- 확장성 높음
- 유지보수 용이

---

**작성일**: 2025-10-30
**분석 대상**: api_url_registry (aict.snu.ac.kr, 20개 레코드)
**상태**: 조치 대기 중 ⏳
