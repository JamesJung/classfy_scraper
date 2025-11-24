# url_key_hash 구현 완료 요약

**작성일**: 2025-10-30
**상태**: ✅ 구현 완료 (DB 스키마 변경 진행 중)

---

## ✅ 완료된 작업

### **1. DB 스키마 변경** (진행 중)

**파일**: `add_url_key_columns.py`

**작업 내용**:
```sql
-- url_key 컬럼 추가
ALTER TABLE api_url_registry
ADD COLUMN url_key VARCHAR(500) COMMENT '정규화된 URL (domain|path|params)';

-- url_key_hash Generated Column 추가 (자동 생성)
ALTER TABLE api_url_registry
ADD COLUMN url_key_hash CHAR(32) AS (MD5(url_key)) STORED COMMENT '자동 생성 해시';

-- 인덱스 추가
ALTER TABLE api_url_registry
ADD INDEX idx_url_key (url_key),
ADD INDEX idx_url_key_hash (url_key_hash);
```

**장점**:
- ✅ url_key_hash가 Generated Column → url_key 변경 시 자동 업데이트
- ✅ 데이터 정합성 자동 보장
- ✅ 애플리케이션 코드 단순화 (hash 계산 불필요)

---

### **2. Python extract_url_key.py 스크립트 생성** ✅

**파일**: `/mnt/d/workspace/sources/classfy_scraper/extract_url_key.py`

**기능**:
- DomainKeyExtractor를 재사용하여 URL 정규화
- grantProjectNoticeBatcher에서 호출 가능
- stdout으로 url_key 출력

**사용법**:
```bash
python3 extract_url_key.py "https://www.bizinfo.go.kr/notice?page=1&id=123" "bizInfo"
# 출력: www.bizinfo.go.kr|/notice|id=123&page=1
```

---

### **3. JavaScript urlKeyExtractor.js 유틸 생성** ✅

**파일**: `/mnt/d/workspace/sources/grantProjectNoticeBatcher/src/utils/urlKeyExtractor.js`

**기능**:
- Python 스크립트를 spawn으로 호출
- url_key 생성 결과 반환
- 실패 시 null 반환 (에러 핸들링)

**사용법**:
```javascript
import { extractUrlKey } from './utils/urlKeyExtractor.js';

const urlKey = await extractUrlKey(
  'https://www.bizinfo.go.kr/notice?page=1&id=123',
  'bizInfo'
);
// Returns: "www.bizinfo.go.kr|/notice|id=123&page=1"
```

---

### **4. grantProjectNoticeBatcher registry.js 수정** ✅

**파일**: `/mnt/d/workspace/sources/grantProjectNoticeBatcher/src/db/registry.js`

**백업**: `registry.js.backup_20251030_HHMMSS`

**변경 사항**:

1. ✅ `extractUrlKey` import 추가
2. ✅ `insertRegistry()` 함수에 url_key 생성 로직 추가
3. ✅ INSERT 쿼리에 url_key 컬럼 추가
4. ✅ ON DUPLICATE KEY UPDATE에 url_key 추가

**핵심 코드**:
```javascript
// url_key 생성
let urlKey = null;
const targetUrl = siteCode === 'kStartUp' ? scrapUrl : announcementUrl;

if (targetUrl) {
  urlKey = await extractUrlKey(targetUrl, siteCode);
}

// INSERT with url_key
INSERT INTO api_url_registry
  (site_code, site_name, scrap_url, announcement_url, announcement_id,
   title, post_date, status, folder_name, url_key, ...)  // 🆕 url_key 추가
VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ...)

ON DUPLICATE KEY UPDATE
  title = VALUES(title),
  ...
  url_key = VALUES(url_key),  // 🆕 url_key 추가
```

---

## 📊 예상 효과

### **Before (현재)**

```
[grantProjectNoticeBatcher]
  INSERT api_url_registry (
    announcement_url = "...?id=123&page=1",
    url_key = NULL,
    url_key_hash = NULL
  )

[announcement_pre_processor.py]
  origin_url = "...?page=1&id=123"  # 파라미터 순서 다름
  url_key_hash = "abc123..."

  WHERE url_key_hash = "abc123..."  # ← NULL이라 실패 ❌
  WHERE announcement_url = origin_url  # ← 파라미터 순서 달라 실패 ❌

  결과: preprocessing_id 업데이트 실패 (현재 0개)
```

---

### **After (개선 후)**

```
[grantProjectNoticeBatcher]
  urlKey = extractUrlKey("...?id=123&page=1")
         → "www.bizinfo.go.kr|/notice|id=123&page=1"

  INSERT api_url_registry (
    announcement_url = "...?id=123&page=1",
    url_key = "www.bizinfo.go.kr|/notice|id=123&page=1",
    url_key_hash = "abc123..."  # Generated Column이 자동 생성 ✅
  )

[announcement_pre_processor.py]
  origin_url = "...?page=1&id=123"  # 파라미터 순서 다름
  url_key = extractUrlKey(origin_url)
          → "www.bizinfo.go.kr|/notice|id=123&page=1"  # 정규화되어 동일! ✅
  url_key_hash = MD5(url_key)
               → "abc123..."  # 동일한 해시! ✅

  WHERE url_key_hash = "abc123..."  # ← 매칭 성공! ✅
  SET preprocessing_id = 12345

  결과: preprocessing_id 업데이트 성공 ✅
```

**개선 효과**:
- 매칭률: 60-70% → **90-95%** (+20-30%p)
- preprocessing_id 업데이트: 0개 → **거의 전부 성공**

---

## 🧪 테스트 계획

### **1. Python 스크립트 테스트**

```bash
cd /mnt/d/workspace/sources/classfy_scraper

# bizInfo 테스트
python3 extract_url_key.py "https://www.bizinfo.go.kr/notice?page=1&id=123" "bizInfo"
# 예상: www.bizinfo.go.kr|/notice|id=123&page=1

# kStartUp 테스트
python3 extract_url_key.py "https://www.k-startup.go.kr/web/contents/bizNotice_view.do?pbancSn=999" "kStartUp"
# 예상: www.k-startup.go.kr|/web/contents/bizNotice_view.do|pbancSn=999
```

---

### **2. DB 스키마 확인**

```sql
-- 컬럼 확인
SELECT COLUMN_NAME, COLUMN_TYPE, GENERATION_EXPRESSION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'api_url_registry'
AND COLUMN_NAME IN ('url_key', 'url_key_hash');

-- 예상 결과:
-- url_key       | VARCHAR(500) | NULL
-- url_key_hash  | CHAR(32)     | MD5(url_key)  ← Generated
```

---

### **3. grantProjectNoticeBatcher 실행 테스트**

```bash
cd /mnt/d/workspace/sources/grantProjectNoticeBatcher

# 테스트 실행 (실제 환경에서)
npm start  # 또는 docker-compose up

# 로그 확인
tail -f logs/application.log | grep "URL key extracted"
```

---

### **4. DB 데이터 확인**

```sql
-- 새로 INSERT된 데이터 확인
SELECT
    id,
    site_code,
    announcement_id,
    LEFT(announcement_url, 50) as url,
    LEFT(url_key, 50) as url_key,
    url_key_hash,
    create_at
FROM api_url_registry
ORDER BY create_at DESC
LIMIT 10;

-- url_key와 url_key_hash가 자동으로 채워져 있는지 확인
-- url_key_hash = MD5(url_key) 인지 검증
SELECT COUNT(*) as incorrect_count
FROM api_url_registry
WHERE url_key IS NOT NULL
AND url_key_hash IS NOT NULL
AND url_key_hash != MD5(url_key);
-- 예상: 0 (일치해야 함)
```

---

### **5. announcement_pre_processor.py 매칭 테스트**

```bash
cd /mnt/d/workspace/sources/classfy_scraper

# 공고 처리 실행
python announcement_pre_processor.py -d data --site-code kStartUp

# 로그에서 url_key_hash 매칭 확인
tail -f logs/announcement_pre_processor.log | grep "url_key_hash"
# 예상: "✅ api_url_registry 업데이트 성공 (kStartUp, url_key_hash)"
```

---

### **6. 매칭률 확인**

```sql
-- preprocessing_id 매핑률 확인
SELECT
    site_code,
    COUNT(*) as total,
    SUM(CASE WHEN preprocessing_id IS NOT NULL THEN 1 ELSE 0 END) as mapped,
    ROUND(SUM(CASE WHEN preprocessing_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) as mapping_rate
FROM api_url_registry
WHERE site_code IN ('kStartUp', 'bizInfo', 'smes24')
GROUP BY site_code;

-- 예상: mapping_rate가 90% 이상으로 향상
```

---

## 📋 체크리스트

### **완료**

- [x] DB 스키마 변경 스크립트 작성
- [x] Python extract_url_key.py 생성
- [x] JavaScript urlKeyExtractor.js 생성
- [x] grantProjectNoticeBatcher registry.js 수정
- [x] registry.js 백업 생성

### **진행 중**

- [ ] DB 스키마 변경 실행 완료 (ALTER TABLE 실행 중)

### **대기 중** (DB 스키마 완료 후)

- [ ] Python 스크립트 단독 테스트
- [ ] Node.js urlKeyExtractor 테스트
- [ ] grantProjectNoticeBatcher 실행 테스트
- [ ] 새 데이터 INSERT 후 DB 확인
- [ ] announcement_pre_processor.py 실행 테스트
- [ ] 매칭률 통계 확인

---

## 🎯 다음 단계

1. **DB 스키마 변경 완료 확인**
   - add_url_key_columns.py 실행 완료 대기
   - 컬럼 및 인덱스 생성 확인

2. **Python 스크립트 테스트**
   - extract_url_key.py 실행 테스트
   - 다양한 URL 패턴으로 검증

3. **grantProjectNoticeBatcher 테스트**
   - 실제 환경에서 INSERT 테스트
   - url_key, url_key_hash 자동 생성 확인

4. **announcement_pre_processor.py 테스트**
   - url_key_hash 매칭 동작 확인
   - preprocessing_id 업데이트 성공 확인

5. **매칭률 모니터링**
   - 개선 전후 비교
   - 90% 이상 매칭률 달성 확인

---

## 📚 작성된 파일 목록

### **스크립트**

1. `/mnt/d/workspace/sources/classfy_scraper/add_url_key_columns.py` - DB 스키마 변경
2. `/mnt/d/workspace/sources/classfy_scraper/extract_url_key.py` - URL 정규화 스크립트

### **유틸리티**

3. `/mnt/d/workspace/sources/grantProjectNoticeBatcher/src/utils/urlKeyExtractor.js` - Node.js 유틸

### **수정된 파일**

4. `/mnt/d/workspace/sources/grantProjectNoticeBatcher/src/db/registry.js` - INSERT 로직 수정
5. `/mnt/d/workspace/sources/grantProjectNoticeBatcher/src/db/registry.js.backup_*` - 백업

### **문서**

6. `GRANT_PROJECT_BATCHER_URL_KEY_IMPLEMENTATION.md` - 상세 구현 가이드
7. `URL_KEY_HASH_ARCHITECTURE_REVIEW.md` - 아키텍처 분석
8. `IMPLEMENTATION_COMPLETE_SUMMARY.md` - 이 문서

---

## ✅ 결론

### **완료된 작업**:

1. ✅ DB 스키마 설계 (url_key + Generated Column url_key_hash)
2. ✅ Python 스크립트 생성 (DomainKeyExtractor 재사용)
3. ✅ Node.js 유틸 생성 (Python 호출)
4. ✅ grantProjectNoticeBatcher 수정 (INSERT 시 url_key 생성)

### **진행 중**:

- 🔄 DB 스키마 변경 실행 (ALTER TABLE 진행 중)

### **다음 단계**:

- 📝 테스트 및 검증
- 📊 매칭률 모니터링

---

**구현 완료!**
DB 스키마 변경이 완료되면 즉시 테스트 가능합니다.
