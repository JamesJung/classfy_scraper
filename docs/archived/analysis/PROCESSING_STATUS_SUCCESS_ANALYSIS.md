# Processing Status 'success' vs '성공' 분석 보고서

## 분석 일시
2025-11-05

## 문제점
announcement_pre_processing 테이블에 processing_status가 'success'로 등록되어 있으나, 정상적으로는 '성공'이어야 함

## 원인 분석

### 1. 정상적인 처리 흐름
**announcement_pre_processor.py**에서는 다음과 같이 한글 상태값을 사용:

```python
# Line 697: 정상 처리 완료 시
status="성공"

# Line 674: 제외 처리 시
status="제외"

# Line 551, 578, 656, 716: 에러 시
status="error"
```

### 2. 중복 체크 관련 상태값
URL 중복 체크 시에는 다음의 **영문 상태값**을 사용:
- `new_inserted`: 새로운 레코드 삽입
- `duplicate_updated`: 중복 레코드 업데이트됨
- `duplicate_preserved`: 중복으로 기존 레코드 유지
- `no_url_key`: URL 키 없음
- `failed`: 실패

이 값들은 **processing_status**가 아닌 중복 로그용 내부 상태값으로, announcement_pre_processing 테이블의 최종 processing_status에는 반영되지 않아야 함.

### 3. 'success' 값이 사용된 곳

#### (1) reprocess_with_exclusion_keywords.py (Line 73, 77)
```python
WHERE processing_status = 'success'
```
**문제**: 잘못된 상태값 사용. '성공'을 사용해야 함.

#### (2) check_homepage_site_announcement_date.py (Line 239)
```python
WHERE sel.status = 'success'
```
**주의**: 이것은 **scraper_execution_log** 테이블의 status 필드로, announcement_pre_processing과는 다른 테이블임.

### 4. 테이블별 상태값 정리

| 테이블 | 필드명 | 올바른 값 |
|--------|--------|-----------|
| announcement_pre_processing | processing_status | '성공', '제외', 'error' |
| scraper_execution_log | status | 'success', 'failed', 'skipped' 등 |
| api_url_processing_log | processing_status | 'new_inserted', 'duplicate_updated' 등 |
| announcement_duplicate_log | duplicate_type | 'new_inserted', 'duplicate_updated' 등 |

## 'success' 값이 DB에 들어간 경로 추정

### 가능성 1: 과거 코드
과거에 announcement_pre_processor.py에서 영문 'success'를 사용했다가 한글 '성공'으로 변경되었을 가능성

### 가능성 2: 직접 SQL 삽입
관리자가 직접 SQL로 데이터를 삽입하면서 'success'를 사용했을 가능성

### 가능성 3: 다른 스크립트
분석하지 못한 다른 Python 스크립트에서 'success'를 사용했을 가능성

## 수정 필요 사항

### 1. 코드 수정
**reprocess_with_exclusion_keywords.py** 수정:
```python
# Before
WHERE processing_status = 'success'

# After
WHERE processing_status = '성공'
```

### 2. 데이터베이스 일괄 수정
기존 'success' 값을 '성공'으로 일괄 변경:
```sql
UPDATE announcement_pre_processing
SET processing_status = '성공'
WHERE processing_status = 'success';
```

### 3. 검증
수정 후 다음 쿼리로 검증:
```sql
-- 1. 모든 processing_status 값 확인
SELECT processing_status, COUNT(*) as count
FROM announcement_pre_processing
GROUP BY processing_status
ORDER BY count DESC;

-- 2. 'success' 값이 남아있는지 확인
SELECT COUNT(*)
FROM announcement_pre_processing
WHERE processing_status = 'success';
```

## 재발 방지

### 1. 상수 정의 추가 권장
```python
# constants.py
class ProcessingStatus:
    SUCCESS = "성공"
    EXCLUDED = "제외"
    ERROR = "error"
```

### 2. 코드 리뷰 체크리스트
- processing_status 필드에는 한글 값 사용
- status 필드(다른 테이블)와 혼동 주의
- 중복 체크 내부 상태값과 최종 processing_status 구분

## 결론
- **announcement_pre_processing.processing_status**는 한글 값('성공', '제외', 'error')을 사용
- 현재 DB에 'success'로 등록된 데이터는 '성공'으로 일괄 수정 필요
- reprocess_with_exclusion_keywords.py 코드 수정 필요
