# 수정 완료 도메인 요약

## 실행 일시
2025-11-11

## 1. 초기 문제
- **문제 유형**: extraction_method='query_params'인데 key_params=[]
- **문제 수량**: 52개 도메인
- **상태**: URL 데이터가 없어 패턴 분석 불가

## 2. 수정 완료 도메인 (18개)

### 2.1 gw.riia.or.kr (gwba) - UUID 패턴
```
URL: https://gw.riia.or.kr/board/businessAnnouncement/view/4c4c3ed3-9d13-11f0-a0c6-7f87f843f3e6

설정:
  site_code: gwba
  domain: gw.riia.or.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /board/businessAnnouncement/view/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})

URL 키 생성:
  gw.riia.or.kr|4c4c3ed3-9d13-11f0-a0c6-7f87f843f3e6
```

### 2.2 ijnto.or.kr - 단순 숫자 ID
```
URL: https://ijnto.or.kr/plaza/notice/read/507

설정:
  site_code: ijnto
  domain: ijnto.or.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /plaza/notice/read/(\d+)

URL 키 생성:
  ijnto.or.kr|507
```

### 2.3 jcia.or.kr - 경로 중간의 숫자 ID
```
URL: https://jcia.or.kr/cf/Board/9246/detailView.do

설정:
  site_code: jcia
  domain: jcia.or.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /cf/Board/(\d+)/

URL 키 생성:
  jcia.or.kr|9246
```

### 2.4 www.ttg.co.kr - 게시판 ID
```
URL: https://www.ttg.co.kr/board/ttg020301/445
     https://www.ttg.co.kr/board/ttg020301/441

설정:
  site_code: ttg
  domain: www.ttg.co.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /board/ttg020301/(\d+)

URL 키 생성:
  www.ttg.co.kr|445
  www.ttg.co.kr|441
```

### 2.5 www.kofpi.or.kr (kofpi1) - 쿼리 파라미터 + 경로 구분
```
URL: https://www.kofpi.or.kr/notice/notice_01view.do?bb_seq=12198

설정:
  site_code: kofpi1
  domain: www.kofpi.or.kr
  extraction_method: query_params
  key_params: ["bb_seq"]
  path_pattern: /notice/notice_01view\.do

URL 키 생성:
  www.kofpi.or.kr|12198
```

### 2.6 www.kofpi.or.kr (kofpi2) - 쿼리 파라미터 + 경로 구분
```
URL: https://www.kofpi.or.kr/notice/notice_02view.do?bb_seq=12201

설정:
  site_code: kofpi2
  domain: www.kofpi.or.kr
  extraction_method: query_params
  key_params: ["bb_seq"]
  path_pattern: /notice/notice_02view\.do

URL 키 생성:
  www.kofpi.or.kr|12201

참고:
  - bokji.net과 유사한 하이브리드 설정
  - path_pattern으로 site_code 구분 (notice_01view vs notice_02view)
  - key_params로 실제 ID 추출 (bb_seq)
```

### 2.7 www.jares.go.kr - 경로 기반 숫자 ID
```
URL: https://www.jares.go.kr/main/board/19/1/read/95711
     https://www.jares.go.kr/main/board/19/1/read/95682

설정:
  site_code: jares
  domain: www.jares.go.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /main/board/19/1/read/(\d+)

URL 키 생성:
  www.jares.go.kr|95711
  www.jares.go.kr|95682
```

### 2.8 www.htdream.kr - 쿼리 파라미터
```
URL: https://www.htdream.kr/main/pubAmt/addPubAmtView2.do?pbanId=8741&pbanOpenYn=Y

설정:
  site_code: htdream
  domain: www.htdream.kr
  extraction_method: query_params
  key_params: ["pbanId"]
  path_pattern: NULL

URL 키 생성:
  www.htdream.kr|8741
```

### 2.9 www.gntp.or.kr (gntp_sm) - 경로 기반 숫자 ID
```
URL: https://www.gntp.or.kr/biz/smartFactCont/20109

설정:
  site_code: gntp_sm
  domain: www.gntp.or.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /biz/smartFactCont/(\d+)

URL 키 생성:
  www.gntp.or.kr|20109

참고:
  - www.gntp.or.kr에는 2개의 site_code가 존재
  - gntp: /biz/applyInfo/(\d+) 패턴 사용
  - gntp_sm: /biz/smartFactCont/(\d+) 패턴 사용
```

### 2.10 www.gjcci.or.kr - 경로 중간의 wr_no 값
```
URL: http://www.gjcci.or.kr/user/board/view/board_cd/3010/wr_no/1541

설정:
  site_code: gjcci
  domain: www.gjcci.or.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /user/board/view/board_cd/[^/]+/wr_no/(\d+)

URL 키 생성:
  www.gjcci.or.kr|1541

참고:
  - board_cd는 가변적이므로 [^/]+ 사용
  - wr_no 뒤의 숫자를 ID로 추출
```

### 2.11 www.ggeea.or.kr - 경로 끝의 숫자 ID
```
URL: https://www.ggeea.or.kr/notice/180
     https://www.ggeea.or.kr/notice/181

설정:
  site_code: ggeea
  domain: www.ggeea.or.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /notice/(\d+)

URL 키 생성:
  www.ggeea.or.kr|180
  www.ggeea.or.kr|181
```

### 2.12 www.geea.or.kr - 경로 끝의 숫자 ID
```
URL: http://www.geea.or.kr/bbs/notice/213896

설정:
  site_code: geea
  domain: www.geea.or.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /bbs/notice/(\d+)

URL 키 생성:
  www.geea.or.kr|213896
```

### 2.13 www.gdtp.or.kr - 경로 끝의 숫자 ID
```
URL: https://www.gdtp.or.kr/post/3061

설정:
  site_code: gdtp
  domain: www.gdtp.or.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /post/(\d+)

URL 키 생성:
  www.gdtp.or.kr|3061
```

### 2.14 www.koat.or.kr (fact) - 경로 중간의 숫자 ID
```
URL: https://www.koat.or.kr/board/business/15810/view.do

설정:
  site_code: fact
  domain: www.koat.or.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /board/business/(\d+)/view\.do

URL 키 생성:
  www.koat.or.kr|15810
```

### 2.15 www.dtmsa.or.kr - 경로 끝의 숫자 ID
```
URL: https://www.dtmsa.or.kr/announcement/840

설정:
  site_code: dtmsa
  domain: www.dtmsa.or.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /announcement/(\d+)

URL 키 생성:
  www.dtmsa.or.kr|840
```

### 2.16 www.busan.go.kr (busan) - 경로 끝의 숫자 ID
```
URL: https://www.busan.go.kr/nongup/agricommunity11/1705630

설정:
  site_code: busan
  domain: www.busan.go.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /nongup/agricommunity11/(\d+)

URL 키 생성:
  www.busan.go.kr|1705630

참고:
  - www.busan.go.kr에는 2개의 site_code가 존재
  - prv_busan: query_params (sno) 사용
  - busan: path_pattern 사용 (새로 설정)
```

### 2.17 dgdp.or.kr (dgdc) - 경로 끝의 숫자 ID
```
URL: https://dgdp.or.kr/notice/public/3461

설정:
  site_code: dgdc
  domain: dgdp.or.kr
  extraction_method: path_pattern
  key_params: []
  path_pattern: /notice/public/(\d+)

URL 키 생성:
  dgdp.or.kr|3461
```

### 2.18 www.kita.net (kita_notice) - 쿼리 파라미터 + 경로 구분 (신규 추가)
```
URL: https://www.kita.net/board/notice/noticeDetail.do?postIndex=1864009

설정:
  site_code: kita_notice
  domain: www.kita.net
  extraction_method: query_params
  key_params: ["postIndex"]
  path_pattern: /board/notice/noticeDetail\.do

URL 키 생성:
  www.kita.net|1864009

참고:
  - www.kita.net에는 2개의 site_code가 존재
  - kita: bizAltkey 파라미터 사용, /asocBiz/asocBiz/asocBizOngoingDetail\.do 경로
  - kita_notice: postIndex 파라미터 사용, /board/notice/noticeDetail\.do 경로 (신규 추가)
  - 두 site_code 모두 query_params 사용, path_pattern으로 구분
```

## 3. 통합 수정 SQL

```sql
-- 18개 도메인 일괄 수정 (17개 수정 + 1개 신규 추가)

-- 1. gw.riia.or.kr (UUID 패턴)
UPDATE domain_key_config
SET 
    path_pattern = '/board/businessAnnouncement/view/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'gwba' AND domain = 'gw.riia.or.kr';

-- 2. ijnto.or.kr
UPDATE domain_key_config
SET 
    path_pattern = '/plaza/notice/read/(\\d+)',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'ijnto' AND domain = 'ijnto.or.kr';

-- 3. jcia.or.kr
UPDATE domain_key_config
SET 
    path_pattern = '/cf/Board/(\\d+)/',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'jcia' AND domain = 'jcia.or.kr';

-- 4. www.ttg.co.kr
UPDATE domain_key_config
SET 
    path_pattern = '/board/ttg020301/(\\d+)',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'ttg' AND domain = 'www.ttg.co.kr';

-- 5. www.kofpi.or.kr (kofpi1) - 쿼리 파라미터 + 경로 구분
UPDATE domain_key_config
SET
    path_pattern = '/notice/notice_01view\\.do',
    key_params = '["bb_seq"]',
    extraction_method = 'query_params'
WHERE site_code = 'kofpi1' AND domain = 'www.kofpi.or.kr';

-- 6. www.kofpi.or.kr (kofpi2) - 쿼리 파라미터 + 경로 구분
UPDATE domain_key_config
SET
    path_pattern = '/notice/notice_02view\\.do',
    key_params = '["bb_seq"]',
    extraction_method = 'query_params'
WHERE site_code = 'kofpi2' AND domain = 'www.kofpi.or.kr';

-- 7. www.jares.go.kr - 경로 기반 ID 추출
UPDATE domain_key_config
SET
    path_pattern = '/main/board/19/1/read/(\\d+)',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'jares' AND domain = 'www.jares.go.kr';

-- 8. www.htdream.kr - 쿼리 파라미터 기반 ID 추출
UPDATE domain_key_config
SET
    key_params = '["pbanId"]',
    extraction_method = 'query_params'
WHERE site_code = 'htdream' AND domain = 'www.htdream.kr';

-- 9. www.gntp.or.kr (gntp_sm) - smartFactCont 경로
UPDATE domain_key_config
SET
    path_pattern = '/biz/smartFactCont/(\\d+)',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'gntp_sm' AND domain = 'www.gntp.or.kr';

-- 10. www.gjcci.or.kr - wr_no 파라미터 추출
UPDATE domain_key_config
SET
    path_pattern = '/user/board/view/board_cd/[^/]+/wr_no/(\\d+)',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'gjcci' AND domain = 'www.gjcci.or.kr';

-- 11. www.ggeea.or.kr - notice ID 추출
UPDATE domain_key_config
SET
    path_pattern = '/notice/(\\d+)',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'ggeea' AND domain = 'www.ggeea.or.kr';

-- 12. www.geea.or.kr - bbs/notice 경로
UPDATE domain_key_config
SET
    path_pattern = '/bbs/notice/(\\d+)',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'geea' AND domain = 'www.geea.or.kr';

-- 13. www.gdtp.or.kr - post 경로
UPDATE domain_key_config
SET
    path_pattern = '/post/(\\d+)',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'gdtp' AND domain = 'www.gdtp.or.kr';

-- 14. www.koat.or.kr (fact) - board/business 경로
UPDATE domain_key_config
SET
    path_pattern = '/board/business/(\\d+)/view\\.do',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'fact' AND domain = 'www.koat.or.kr';

-- 15. www.dtmsa.or.kr - announcement 경로
UPDATE domain_key_config
SET
    path_pattern = '/announcement/(\\d+)',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'dtmsa' AND domain = 'www.dtmsa.or.kr';

-- 16. www.busan.go.kr (busan) - nongup/agricommunity11 경로
UPDATE domain_key_config
SET
    path_pattern = '/nongup/agricommunity11/(\\d+)',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'busan' AND domain = 'www.busan.go.kr';

-- 17. dgdp.or.kr (dgdc) - notice/public 경로
UPDATE domain_key_config
SET
    path_pattern = '/notice/public/(\\d+)',
    key_params = '[]',
    extraction_method = 'path_pattern'
WHERE site_code = 'dgdc' AND domain = 'dgdp.or.kr';

-- 18. www.kita.net (kita_notice) - 신규 추가
INSERT INTO domain_key_config (site_code, domain, extraction_method, key_params, path_pattern)
VALUES ('kita_notice', 'www.kita.net', 'query_params', '["postIndex"]', '/board/notice/noticeDetail\\.do')
ON DUPLICATE KEY UPDATE
    extraction_method = 'query_params',
    key_params = '["postIndex"]',
    path_pattern = '/board/notice/noticeDetail\\.do';

-- kita에 path_pattern 추가 (site_code 구분용)
UPDATE domain_key_config
SET path_pattern = '/asocBiz/asocBiz/asocBizOngoingDetail\\.do'
WHERE site_code = 'kita' AND domain = 'www.kita.net';

-- 검증
SELECT id, site_code, domain, extraction_method, key_params, path_pattern
FROM domain_key_config
WHERE site_code IN ('gwba', 'ijnto', 'jcia', 'ttg', 'kofpi1', 'kofpi2', 'jares', 'htdream', 'gntp_sm', 'gjcci', 'ggeea', 'geea', 'gdtp', 'fact', 'dtmsa', 'busan', 'dgdc', 'kita_notice')
ORDER BY site_code;
```

## 4. 진행 현황

**52개 문제 도메인 중**:
- ✅ 수정 완료: 18개
- ⏳ 남은 도메인: 34개

**참고**: kita_notice는 52개 문제 도메인에 포함되지 않았던 신규 추가 항목입니다.

**남은 도메인 목록**:
- 모두 URL 데이터가 없는 비활성 도메인
- 실제 URL이 제공될 때 패턴 분석 후 수정 필요

## 5. 일반적인 URL 패턴 유형

### 5.1 경로 끝의 숫자 ID
```
패턴: /path/to/{id}
예시: /plaza/notice/read/507
정규식: /plaza/notice/read/(\d+)
```

### 5.2 경로 중간의 숫자 ID
```
패턴: /path/{id}/action
예시: /cf/Board/9246/detailView.do
정규식: /cf/Board/(\d+)/
```

### 5.3 UUID 패턴
```
패턴: /path/{uuid}
예시: /board/.../4c4c3ed3-9d13-11f0-a0c6-7f87f843f3e6
정규식: /board/.../([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})
```

### 5.4 쿼리 파라미터 (기존 많이 사용)
```
패턴: ?id={id}
예시: ?BOARDIDX=31255
설정: extraction_method='query_params', key_params='["BOARDIDX"]'
```

### 5.5 쿼리 파라미터 + 경로 구분 (하이브리드)
```
패턴: 같은 도메인, 다른 경로, 같은 쿼리 파라미터
예시: /notice/notice_01view.do?bb_seq=123
     /notice/notice_02view.do?bb_seq=456
설정:
  - extraction_method='query_params'
  - key_params로 실제 ID 추출
  - path_pattern으로 site_code 구분
참고: bokji.net, kofpi 사례
```

## 6. 다음 단계

1. **남은 34개 도메인**
   - URL 수집 시 패턴 분석
   - 위 유형 중 하나에 해당할 가능성 높음

2. **자동화 개선**
   - 경로 기반 패턴 자동 감지
   - analyze_missing_identifiers.py 업데이트

3. **검증 강화**
   - validate_domain_key_config.py에 extraction_method 일관성 검사 추가
