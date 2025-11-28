# 식별자 누락 도메인 수정 보고서

## 실행 일시
2025-11-11

## 1. 문제 현황

### 초기 상태
- **총 이슈**: 292개 (Critical: 124개, Warning: 168개)
- **식별자 누락**: 122개 도메인
  - path_pattern과 key_params가 모두 없어서 URL 고유성 보장 불가
  - 데이터 중복 및 손실 위험

## 2. 분석 방법

### 자동 분석 스크립트 작성
**파일**: `analyze_missing_identifiers.py`

**기능**:
1. 식별자가 누락된 도메인 목록 조회
2. 각 도메인의 실제 URL 샘플 분석
3. URL 패턴 자동 추출
   - 경로 기반 패턴 (path_pattern)
   - 쿼리 파라미터 기반 패턴 (key_params)
4. 수정 SQL 자동 생성

**분석 결과**:
```
총 121개 도메인:
  - path_pattern 추천: 2개
  - key_params 추천: 2개
  - unknown (수동 검토): 5개
  - no_urls (등록된 URL 없음): 112개
```

## 3. 수정 내용

### 3.1 자동 분석으로 수정된 도메인 (4개)

#### hamkke.org
```sql
-- URL 패턴: https://hamkke.org/archives/business/48623
UPDATE domain_key_config
SET path_pattern = '/archives/business/{id}',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE id = 801;
```

#### www.technopark.kr
```sql
-- URL 패턴: https://www.technopark.kr/businessboard/224325
UPDATE domain_key_config
SET path_pattern = '/businessboard/{id}',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE id = 924;
```

#### www.icsinbo.or.kr
```sql
-- URL 패턴: https://www.icsinbo.or.kr/home/board/brdDetail.do?menu_cd=000096&num=1390
UPDATE domain_key_config
SET key_params = '["num"]',
    path_pattern = NULL,
    extraction_method = 'query_params'
WHERE id = 699;
```

#### yeosucci.korcham.net
```sql
-- URL 패턴: https://yeosucci.korcham.net/front/board/boardContentsView.do?contId=112696&boardId=10748&menuId=3075
UPDATE domain_key_config
SET key_params = '["contId"]',
    path_pattern = NULL,
    extraction_method = 'query_params'
WHERE id = 679;
```

### 3.2 수동 분석으로 수정된 도메인 (5개)

#### pohangcci.korcham.net
```sql
-- URL: https://pohangcci.korcham.net/front/board/boardContentsView.do?contId=122225&boardId=10275&menuId=1440
-- ID 파라미터: contId
UPDATE domain_key_config
SET key_params = '["contId"]',
    path_pattern = NULL,
    extraction_method = 'query_params'
WHERE site_code = 'pohangcci';
```

#### sokchocci.korcham.net
```sql
-- URL: https://sokchocci.korcham.net/front/board/boardContentsView.do?contId=122099&boardId=10635&menuId=2750
-- ID 파라미터: contId
UPDATE domain_key_config
SET key_params = '["contId"]',
    path_pattern = NULL,
    extraction_method = 'query_params'
WHERE site_code = 'sokchocci';
```

#### www.baroinfo.com
```sql
-- URL: https://www.baroinfo.com/front/M000000742/applybusiness/view.do?articleId=AC00006633
-- ID 파라미터: articleId
UPDATE domain_key_config
SET key_params = '["articleId"]',
    path_pattern = NULL,
    extraction_method = 'query_params'
WHERE site_code = 'baroinfo';
```

#### www.gsfez.go.kr
```sql
-- URL: https://www.gsfez.go.kr/gsfez/news/bulletin?articleSeq=1984
-- ID 파라미터: articleSeq
UPDATE domain_key_config
SET key_params = '["articleSeq"]',
    path_pattern = NULL,
    extraction_method = 'query_params'
WHERE site_code = 'gsfez';
```

#### www.motie.go.kr
```sql
-- URL: https://www.motie.go.kr/ftz/yulchon/notification/notice/bbs/bbsView.do?bbs_seq_n=155&bbs_cd_n=117&currentPage=1&search_key_n=&cate_n=&dept_v=&search_val_v=
-- ID 파라미터: bbs_seq_n
UPDATE domain_key_config
SET key_params = '["bbs_seq_n"]',
    path_pattern = NULL,
    extraction_method = 'query_params'
WHERE site_code = 'motie';
```

## 4. 검증 결과

### 수정 전
```
총 292개 이슈:
  - 🔴 Critical: 124개
  - 🟡 Warning: 168개
```

### 수정 후
```
총 283개 이슈:
  - 🔴 Critical: 115개 (9개 감소 ✅)
  - 🟡 Warning: 168개
```

### 수정된 도메인 검증
```sql
SELECT id, site_code, domain, extraction_method, key_params, path_pattern
FROM domain_key_config
WHERE site_code IN ('hamkke', 'icsinbo', 'ttp', 'yeosucci', 'pohangcci', 'sokchocci', 'baroinfo', 'gsfez', 'motie');
```

**결과**:
| site_code | domain | extraction_method | key_params | path_pattern |
|-----------|--------|-------------------|------------|--------------|
| hamkke | hamkke.org | path_pattern | [] | /archives/business/{id} |
| ttp | www.technopark.kr | path_pattern | [] | /businessboard/{id} |
| icsinbo | www.icsinbo.or.kr | query_params | ["num"] | NULL |
| yeosucci | yeosucci.korcham.net | query_params | ["contId"] | NULL |
| pohangcci | pohangcci.korcham.net | query_params | ["contId"] | NULL |
| sokchocci | sokchocci.korcham.net | query_params | ["contId"] | NULL |
| baroinfo | www.baroinfo.com | query_params | ["articleId"] | NULL |
| gsfez | www.gsfez.go.kr | query_params | ["articleSeq"] | NULL |
| motie | www.motie.go.kr | query_params | ["bbs_seq_n"] | NULL |

## 5. 미수정 도메인 (112개)

### 현황
등록된 URL이 없는 도메인 112개는 수정하지 않음

**이유**:
- announcement_pre_processing 테이블에 해당 site_code의 URL이 없음
- 실제 URL 패턴을 확인할 수 없어 설정 불가
- 향후 데이터가 등록되면 분석 후 수정 필요

**대표적인 미수정 도메인**:
- acci.korcham.net
- agro.seoul.go.kr
- andongcci.korcham.net
- ansancci.korcham.net
- ... (총 112개)

## 6. 생성된 파일

### 6.1 분석 스크립트
```
analyze_missing_identifiers.py
- 식별자 누락 도메인 자동 분석
- URL 패턴 추출 및 추천
- 수정 SQL 자동 생성
```

### 6.2 SQL 파일
```
/tmp/fix_missing_identifiers.sql
- 자동 분석으로 생성된 수정 SQL (4개 도메인)

/tmp/fix_unknown_patterns.sql
- 수동 분석으로 작성된 수정 SQL (5개 도메인)

/tmp/fix_all_missing_identifiers.sql
- 전체 수정 SQL (9개 도메인)
```

### 6.3 분석 결과
```
/tmp/missing_identifiers_analysis.json
- 전체 121개 도메인 분석 결과
- URL 패턴, 추천 설정 등 상세 정보
```

## 7. 향후 작업

### 7.1 즉시 조치 필요
- ✅ **완료**: URL이 있는 9개 도메인 수정
- ⏳ **보류**: URL이 없는 112개 도메인
  - 데이터 수집 후 재분석 필요

### 7.2 지속적 모니터링
1. **새 도메인 추가 시**
   - `analyze_missing_identifiers.py` 실행
   - URL 패턴 자동 분석 및 수정

2. **검증 스크립트 정기 실행**
   - `validate_domain_key_config.py` 매주 실행
   - Critical 이슈 발견 시 즉시 대응

3. **남은 Critical 이슈**
   - 식별자 누락: 115개 (대부분 URL 없는 도메인)
   - extraction_method 불일치: 3개 (shinan, motie, gntp)
     - ⚠️ motie는 이미 수정했으나 다른 도메인 설정과 충돌 가능성

## 8. 결론

### 성과
- ✅ 9개 도메인 설정 수정 완료
- ✅ Critical 이슈 9개 해결 (124개 → 115개)
- ✅ 자동 분석 스크립트 개발로 향후 작업 효율화
- ✅ URL 고유성 보장 체계 강화

### 제한사항
- 112개 도메인은 URL 데이터가 없어 수정 불가
- 실제 데이터가 수집되면 재분석 및 수정 필요

### 추천사항
1. URL 없는 도메인의 스크래핑 활성화 여부 확인
2. 비활성 도메인은 domain_key_config에서 제거 고려
3. 새 도메인 추가 시 자동 분석 스크립트 활용
