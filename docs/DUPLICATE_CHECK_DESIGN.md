# announcement_duplicate_log 테이블 상세 설계 및 구현 가이드

## 📋 목차

1. [핵심 원칙](#핵심-원칙)
2. [테이블 설계](#테이블-설계)
3. [중복 체크 로직](#중복-체크-로직)
4. [로그 기록 시나리오](#로그-기록-시나리오)
5. [코드 구현](#코드-구현)
6. [활용 방안](#활용-방안)
7. [테스트 시나리오](#테스트-시나리오)

---

## 🎯 핵심 원칙

### 로그 기록 원칙

**기록 대상**: `url_key_hash` 기반 중복 체크 시 발생하는 모든 시도

**기록 시점**: `announcement_pre_processing` 테이블 저장 직후

**기록 범위**:
- ✅ **도메인 미설정**: domain_key_config에 설정이 없어서 url_key가 생성되지 않은 경우
- ✅ **신규 삽입**: url_key_hash 중복이 없어서 새로 저장된 경우
- ✅ **중복 발견 - 교체**: 우선순위가 높아서 기존 데이터를 교체한 경우 (UPSERT UPDATE)
- ✅ **중복 발견 - 유지**: 우선순위가 낮아서 기존 데이터를 유지한 경우
- ✅ **중복 발견 - 동일**: 우선순위가 같아서 최신 데이터로 업데이트한 경우 (UPSERT UPDATE)
- ✅ **오류**: 예상치 못한 처리 오류 발생 시

---

## 📊 테이블 설계

### 기존 스키마 (create_announcement_duplicate_log.sql)

```sql
CREATE TABLE IF NOT EXISTS announcement_duplicate_log (
    -- 기본 정보
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    -- 메인 테이블 참조
    preprocessing_id INT NOT NULL COMMENT '최종 저장된 announcement_pre_processing.id',
    existing_preprocessing_id INT COMMENT '기존 레코드 ID (중복 발생시)',

    -- 중복 발생 정보
    duplicate_type VARCHAR(50) NOT NULL COMMENT '중복 유형',
    /*
        - 'unconfigured_domain': domain_key_config에 설정 없음 (url_key 생성 실패)
        - 'new_inserted': 신규 삽입 (중복 아님)
        - 'replaced': 기존 데이터 교체됨 (새 데이터 우선순위 높음, UPSERT UPDATE)
        - 'kept_existing': 기존 데이터 유지됨 (새 데이터 우선순위 낮음)
        - 'same_type_duplicate': 같은 타입 중복 (우선순위 동일, UPSERT UPDATE)
        - 'error': 처리 중 오류 발생
        - 'unknown': 예상치 못한 상태
    */

    -- ⭐ 핵심: URL 식별자 (중복 체크 기준)
    url_key_hash CHAR(32) COMMENT 'URL 키 해시 (MD5)',

    -- 타입 정보
    new_site_type VARCHAR(50) NOT NULL,
    new_site_code VARCHAR(50) NOT NULL,
    existing_site_type VARCHAR(50),
    existing_site_code VARCHAR(50),

    -- 우선순위 정보
    new_priority TINYINT,
    existing_priority TINYINT,

    -- 중복 상세 정보
    duplicate_detail JSON,
    new_folder_name VARCHAR(255),
    error_message TEXT,

    -- 타임스탬프
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- ⭐ 핵심 인덱스: url_key_hash로 검색
    INDEX idx_url_key_hash (url_key_hash),
    INDEX idx_preprocessing_id (preprocessing_id),
    INDEX idx_existing_id (existing_preprocessing_id),
    INDEX idx_duplicate_type (duplicate_type),
    INDEX idx_created_at (created_at),
    INDEX idx_new_site_code (new_site_code),

    -- 외래키
    CONSTRAINT fk_preprocessing_id
        FOREIGN KEY (preprocessing_id)
        REFERENCES announcement_pre_processing(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 설계 포인트

#### 1. url_key_hash가 핵심

```
중복 체크 흐름:
1. origin_url 추출
2. url_key 생성 (URL 정규화)
3. url_key_hash 계산 (MD5)
4. announcement_pre_processing에서 url_key_hash로 기존 레코드 조회
5. 조회 결과에 따라 duplicate_type 결정
6. announcement_duplicate_log 기록
```

#### 2. 중복 유형 (duplicate_type)

| duplicate_type | 발생 조건 | 설명 |
|---------------|----------|------|
| `unconfigured_domain` | domain_key_config에 설정 없음 | url_key 생성 실패 (Fallback 비활성화) |
| `new_inserted` | url_key_hash가 DB에 없음 | 완전히 새로운 공고 (UPSERT INSERT) |
| `replaced` | url_key_hash 중복 + 새 우선순위 > 기존 우선순위 | 지자체가 API 교체 (UPSERT UPDATE) |
| `kept_existing` | url_key_hash 중복 + 새 우선순위 < 기존 우선순위 | API가 지자체 유지 (UPSERT에서 조건 미충족) |
| `same_type_duplicate` | url_key_hash 중복 + 새 우선순위 = 기존 우선순위 | 같은 타입 재수집 (UPSERT UPDATE) |
| `error` | 예상치 못한 처리 오류 | UPSERT affected_rows 이상값 등 |
| `unknown` | 매핑되지 않은 상태 | 예상치 못한 상태 (버그 가능성) |

#### 3. 우선순위 체계

```python
def get_priority(site_type: str) -> int:
    """
    우선순위 매핑 (높을수록 우선)
    """
    priority_map = {
        'Eminwon': 3,    # 지자체 민원
        'Homepage': 3,   # 지자체 홈페이지
        'Scraper': 3,    # 지자체 스크레이퍼
        'api_scrap': 1,  # API 수집
        'Unknown': 0,    # 알 수 없음
    }
    return priority_map.get(site_type, 0)
```

**우선순위 규칙**:
- 지자체 데이터 (Eminwon/Homepage/Scraper) = 3
- API 데이터 (api_scrap) = 1
- **지자체 > API**: 지자체 데이터가 API 데이터를 덮어씀
- **API < 지자체**: API 데이터가 지자체 데이터를 유지함

---

## 🔍 중복 체크 로직

### 전체 흐름도

```
┌─────────────────────────────────────────────────────────────┐
│ 1. content.md 읽기 → origin_url 추출                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. URL 정규화: origin_url → url_key                         │
│    - domain_key_config 조회                                  │
│    - 설정 없으면 url_key = NULL (Fallback 비활성화)         │
│    - 쿼리 파라미터 정렬 등                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
                    url_key가 없음?
                    ↙ YES        ↘ NO
         ┌─────────────────┐    ┌───────────────────────────┐
         │ duplicate_type  │    │ 3. UPSERT 실행             │
         │ = 'unconfigured_│    │    INSERT ... ON DUPLICATE│
         │ domain'         │    │    KEY UPDATE ... WHERE   │
         │                 │    │    우선순위 조건          │
         └─────────────────┘    └───────────────────────────┘
                  ↓                          ↓
                  ↓                   affected_rows?
                  ↓              ↙ 1           ↓ 2          ↘ 기타
                  ↓    ┌──────────────┐ ┌────────────┐ ┌──────────┐
                  ↓    │new_inserted  │ │duplicate_  │ │error     │
                  ↓    │(INSERT됨)    │ │updated     │ │(예외값)  │
                  ↓    └──────────────┘ │(UPDATE됨)  │ └──────────┘
                  ↓                     └────────────┘
                  ↓                          ↓
                  ↓                     우선순위 비교
                  ↓                  ↙ >      ↓ =      ↘ <
                  ↓         ┌──────────┐ ┌───────────┐ ┌──────────────┐
                  ↓         │replaced  │ │same_type_ │ │kept_existing │
                  ↓         │          │ │duplicate  │ │(조건 미충족) │
                  ↓         └──────────┘ └───────────┘ └──────────────┘
                  ↓                          ↓
                  └──────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. url_key_hash 조회 (GENERATED COLUMN)                     │
│    - DB에서 자동 생성된 url_key_hash 조회                    │
└─────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. announcement_duplicate_log 기록 ⭐                        │
│    - preprocessing_id: 저장된 레코드 ID                     │
│    - existing_preprocessing_id: 기존 레코드 ID (중복 시)    │
│    - url_key_hash: DB 생성 해시 (GENERATED COLUMN)          │
│    - duplicate_type: 중복 유형                               │
│    - new/existing_site_type/code: 타입 정보                 │
│    - new/existing_priority: 우선순위                        │
│    - duplicate_detail: 상세 정보 (JSON, domain 포함)        │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 로그 기록 시나리오

### 시나리오 1: 신규 삽입 (new_inserted)

**상황**: bizInfo에서 새로운 공고 수집

**데이터**:
```python
origin_url = "https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId=PBLN_000000000100001"
url_key = "bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId=PBLN_000000000100001"
url_key_hash = MD5(url_key) = "abc123def456..."
site_type = "api_scrap"
site_code = "bizInfo"
```

**중복 체크**:
```sql
SELECT id, site_type, site_code
FROM announcement_pre_processing
WHERE url_key_hash = 'abc123def456...'
-- 결과: 없음 (신규)
```

**announcement_duplicate_log 기록**:
```sql
INSERT INTO announcement_duplicate_log (
    preprocessing_id,
    existing_preprocessing_id,
    duplicate_type,
    url_key_hash,
    new_site_type,
    new_site_code,
    existing_site_type,
    existing_site_code,
    new_priority,
    existing_priority,
    new_folder_name,
    duplicate_detail,
    error_message
) VALUES (
    1001,                    -- 방금 저장된 ID
    NULL,                    -- 기존 레코드 없음
    'new_inserted',
    'abc123def456...',
    'api_scrap',
    'bizInfo',
    NULL,
    NULL,
    1,                       -- api_scrap 우선순위
    NULL,
    '2025-11-01_PBLN_000000000100001',
    NULL,
    NULL
);
```

---

### 시나리오 2: 교체 (replaced)

**상황**: 같은 공고를 seoul 지자체 홈페이지에서 다시 수집

**데이터**:
```python
origin_url = "https://www.seoul.go.kr/support/announce/view.do?id=12345"  # 같은 공고
url_key = "bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId=PBLN_000000000100001"  # 정규화 후 동일
url_key_hash = MD5(url_key) = "abc123def456..."  # 동일
site_type = "Homepage"
site_code = "seoul"
```

**중복 체크**:
```sql
SELECT id, site_type, site_code
FROM announcement_pre_processing
WHERE url_key_hash = 'abc123def456...'
-- 결과: id=1001, site_type='api_scrap', site_code='bizInfo' (기존 레코드)
```

**우선순위 비교**:
```python
new_priority = get_priority('Homepage') = 3
existing_priority = get_priority('api_scrap') = 1
# 3 > 1 → 교체
```

**announcement_pre_processing 업데이트**:
```sql
UPDATE announcement_pre_processing
SET
    site_type = 'Homepage',
    site_code = 'prv_seoul',  -- prv_ 접두사 추가
    content_md = '새 내용',
    ...
WHERE id = 1001;
```

**announcement_duplicate_log 기록**:
```sql
INSERT INTO announcement_duplicate_log (
    preprocessing_id,
    existing_preprocessing_id,
    duplicate_type,
    url_key_hash,
    new_site_type,
    new_site_code,
    existing_site_type,
    existing_site_code,
    new_priority,
    existing_priority,
    new_folder_name,
    duplicate_detail,
    error_message
) VALUES (
    1001,                    -- 동일 ID (업데이트됨)
    1001,                    -- 기존 레코드 ID
    'replaced',
    'abc123def456...',
    'Homepage',
    'seoul',
    'api_scrap',
    'bizInfo',
    3,
    1,
    'seoul_20251101_12345',
    JSON_OBJECT(
        'decision', '기존 데이터 교체',
        'reason', '우선순위 높음: Homepage(3) > api_scrap(1)',
        'existing_folder', '2025-11-01_PBLN_000000000100001',
        'priority_comparison', '3 > 1'
    ),
    NULL
);
```

---

### 시나리오 3: 유지 (kept_existing)

**상황**: seoul 지자체 데이터가 이미 있는데, bizInfo에서 다시 수집

**데이터**:
```python
origin_url = "https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId=PBLN_000000000100001"
url_key = "bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId=PBLN_000000000100001"
url_key_hash = "abc123def456..."
site_type = "api_scrap"
site_code = "bizInfo"
```

**중복 체크**:
```sql
SELECT id, site_type, site_code
FROM announcement_pre_processing
WHERE url_key_hash = 'abc123def456...'
-- 결과: id=1001, site_type='Homepage', site_code='prv_seoul' (기존 레코드)
```

**우선순위 비교**:
```python
new_priority = get_priority('api_scrap') = 1
existing_priority = get_priority('Homepage') = 3
# 1 < 3 → 유지 (업데이트 안함)
```

**announcement_pre_processing**: 변경 없음

**announcement_duplicate_log 기록**:
```sql
INSERT INTO announcement_duplicate_log (
    preprocessing_id,
    existing_preprocessing_id,
    duplicate_type,
    url_key_hash,
    new_site_type,
    new_site_code,
    existing_site_type,
    existing_site_code,
    new_priority,
    existing_priority,
    new_folder_name,
    duplicate_detail,
    error_message
) VALUES (
    1001,                    -- 기존 ID (변경 없음)
    1001,                    -- 기존 레코드 ID
    'kept_existing',
    'abc123def456...',
    'api_scrap',
    'bizInfo',
    'Homepage',
    'prv_seoul',
    1,
    3,
    '2025-11-01_PBLN_000000000100001',
    JSON_OBJECT(
        'decision', '기존 데이터 유지',
        'reason', '우선순위 낮음: api_scrap(1) < Homepage(3)',
        'existing_folder', 'seoul_20251101_12345',
        'priority_comparison', '1 < 3'
    ),
    NULL
);
```

---

### 시나리오 4: 동일 타입 중복 (same_type_duplicate)

**상황**: bizInfo에서 같은 공고를 다시 수집 (재수집)

**데이터**:
```python
url_key_hash = "abc123def456..."  # 동일
site_type = "api_scrap"
site_code = "bizInfo"
```

**중복 체크**:
```sql
SELECT id, site_type, site_code
FROM announcement_pre_processing
WHERE url_key_hash = 'abc123def456...'
-- 결과: id=1001, site_type='api_scrap', site_code='bizInfo' (동일 타입)
```

**우선순위 비교**:
```python
new_priority = get_priority('api_scrap') = 1
existing_priority = get_priority('api_scrap') = 1
# 1 = 1 → 최신 데이터로 업데이트
```

**announcement_pre_processing 업데이트**: 최신 내용으로 갱신

**announcement_duplicate_log 기록**:
```sql
INSERT INTO announcement_duplicate_log (
    preprocessing_id,
    existing_preprocessing_id,
    duplicate_type,
    url_key_hash,
    new_site_type,
    new_site_code,
    existing_site_type,
    existing_site_code,
    new_priority,
    existing_priority,
    new_folder_name,
    duplicate_detail,
    error_message
) VALUES (
    1001,
    1001,
    'same_type_duplicate',
    'abc123def456...',
    'api_scrap',
    'bizInfo',
    'api_scrap',
    'bizInfo',
    1,
    1,
    '2025-11-02_PBLN_000000000100001',
    JSON_OBJECT(
        'decision', '최신 데이터로 업데이트',
        'reason', '우선순위 동일: api_scrap(1) = api_scrap(1)',
        'existing_folder', '2025-11-01_PBLN_000000000100001',
        'priority_comparison', '1 = 1',
        'update_type', 'refresh'
    ),
    NULL
);
```

---

### 시나리오 5: 오류 (error)

**상황**: URL 정규화 실패

**데이터**:
```python
origin_url = "invalid-url"
url_key = None  # 정규화 실패
url_key_hash = None
site_type = "api_scrap"
site_code = "bizInfo"
```

**announcement_duplicate_log 기록**:
```sql
INSERT INTO announcement_duplicate_log (
    preprocessing_id,
    existing_preprocessing_id,
    duplicate_type,
    url_key_hash,
    new_site_type,
    new_site_code,
    existing_site_type,
    existing_site_code,
    new_priority,
    existing_priority,
    new_folder_name,
    duplicate_detail,
    error_message
) VALUES (
    1002,
    NULL,
    'error',
    NULL,
    'api_scrap',
    'bizInfo',
    NULL,
    NULL,
    1,
    NULL,
    '2025-11-01_INVALID',
    NULL,
    'URL 정규화 실패: origin_url이 유효하지 않음'
);
```

---

## 💻 코드 구현

### 1️⃣ _save_processing_result() 함수 수정

**파일**: `announcement_pre_processor.py`

**핵심 변경사항**:
1. url_key_hash 기반 중복 체크
2. 우선순위 비교
3. announcement_duplicate_log 기록

```python
def _save_processing_result(
    self,
    folder_name: str,
    site_code: str,
    content_md: str,
    combined_content: str,
    attachment_filenames: List[str] = None,
    status: str = "성공",
    exclusion_keywords: List[str] = None,
    exclusion_reason: str = None,
    error_message: str = None,
    force: bool = False,
    title: str = None,
    origin_url: str = None,
    url_key: str = None,
    scraping_url: str = None,
    announcement_date: str = None,
    attachment_files_info: List[Dict[str, Any]] = None,
) -> Optional[int]:
    """처리 결과를 데이터베이스에 저장합니다."""
    try:
        from sqlalchemy import text
        import hashlib

        with self.db_manager.SessionLocal() as session:
            # ================================================
            # 1단계: url_key_hash 기반 중복 체크
            # ================================================
            url_key_hash = None
            existing_record = None

            if url_key:
                # url_key_hash 계산
                url_key_hash = hashlib.md5(url_key.encode('utf-8')).hexdigest()
                logger.debug(f"url_key_hash 생성: {url_key_hash[:16]}...")

                # 기존 레코드 조회
                try:
                    existing_record_result = session.execute(
                        text("""
                            SELECT id, site_type, site_code, folder_name, url_key
                            FROM announcement_pre_processing
                            WHERE url_key_hash = :url_key_hash
                            LIMIT 1
                        """),
                        {"url_key_hash": url_key_hash}
                    ).fetchone()

                    if existing_record_result:
                        existing_record = {
                            'id': existing_record_result.id,
                            'site_type': existing_record_result.site_type,
                            'site_code': existing_record_result.site_code,
                            'folder_name': existing_record_result.folder_name,
                            'url_key': existing_record_result.url_key
                        }
                        logger.info(
                            f"⚠️  중복 발견: url_key_hash={url_key_hash[:16]}... "
                            f"기존 레코드 ID={existing_record['id']}, "
                            f"site_type={existing_record['site_type']}, "
                            f"folder_name={existing_record['folder_name']}"
                        )
                except Exception as e:
                    logger.warning(f"기존 레코드 조회 실패 (무시하고 계속): {e}")

            # ================================================
            # 2단계: 우선순위 비교 및 처리 결정
            # ================================================
            duplicate_type = None
            should_update = False

            if not url_key:
                # URL 정규화 실패
                duplicate_type = 'error'
                should_update = True  # 에러라도 일단 저장
                logger.warning("URL 정규화 실패 - 중복 체크 불가")

            elif existing_record:
                # 중복 발견 - 우선순위 비교
                new_priority = self.get_priority(self.site_type)
                existing_priority = self.get_priority(existing_record['site_type'])

                logger.info(
                    f"우선순위 비교: 새={self.site_type}({new_priority}) vs "
                    f"기존={existing_record['site_type']}({existing_priority})"
                )

                if new_priority > existing_priority:
                    # 새 데이터 우선순위가 높음 → 교체
                    duplicate_type = 'replaced'
                    should_update = True
                    logger.info(f"✅ 기존 데이터 교체: {new_priority} > {existing_priority}")

                elif new_priority < existing_priority:
                    # 기존 데이터 우선순위가 높음 → 유지
                    duplicate_type = 'kept_existing'
                    should_update = False
                    logger.info(f"⏭️  기존 데이터 유지: {new_priority} < {existing_priority}")

                else:
                    # 우선순위 동일 → 최신 데이터로 업데이트
                    duplicate_type = 'same_type_duplicate'
                    should_update = True
                    logger.info(f"🔄 동일 우선순위 업데이트: {new_priority} = {existing_priority}")

            else:
                # 신규 삽입
                duplicate_type = 'new_inserted'
                should_update = True
                logger.info("✨ 신규 공고 삽입")

            # ================================================
            # 3단계: announcement_pre_processing 저장
            # ================================================
            record_id = None

            if should_update:
                if existing_record and duplicate_type in ['replaced', 'same_type_duplicate']:
                    # 기존 레코드 업데이트
                    # ... (UPDATE 쿼리 실행)
                    record_id = existing_record['id']
                    logger.info(f"기존 레코드 업데이트 완료: ID={record_id}")
                else:
                    # 신규 INSERT
                    # ... (INSERT 쿼리 실행)
                    result = session.execute(insert_sql, params)
                    record_id = result.lastrowid
                    logger.info(f"신규 레코드 저장 완료: ID={record_id}")

                session.commit()
            else:
                # 기존 데이터 유지 (kept_existing)
                record_id = existing_record['id']
                logger.info(f"기존 데이터 유지: ID={record_id}")

            # ================================================
            # 4단계: announcement_duplicate_log 기록 ⭐
            # ================================================
            self._log_announcement_duplicate(
                session=session,
                preprocessing_id=record_id,
                url_key_hash=url_key_hash,
                duplicate_type=duplicate_type,
                site_code=site_code,
                folder_name=folder_name,
                existing_record=existing_record,
                error_message=error_message if duplicate_type == 'error' else None
            )

            return record_id

    except Exception as e:
        logger.error(f"처리 결과 저장 실패: {e}")
        return None
```

---

### 2️⃣ _log_announcement_duplicate() 함수 (신규)

**파일**: `announcement_pre_processor.py`

```python
def _log_announcement_duplicate(
    self,
    session,
    preprocessing_id: int,
    url_key_hash: str,
    duplicate_type: str,
    site_code: str,
    folder_name: str,
    domain: str = None,
    domain_configured: bool = False,
    existing_record: dict = None,
    error_message: str = None
) -> bool:
    """
    announcement_duplicate_log 테이블에 중복 처리 로그를 기록합니다.

    Args:
        session: SQLAlchemy 세션
        preprocessing_id: 저장/업데이트된 레코드 ID
        url_key_hash: URL 키 해시 (MD5) - domain_key_config 없으면 NULL
        duplicate_type: 중복 유형
            - 'unconfigured_domain': domain_key_config에 설정 없음
            - 'new_inserted': 신규 삽입 (domain_key_config 있고 중복 없음)
            - 'replaced': 기존 데이터 교체 (우선순위 높음)
            - 'kept_existing': 기존 데이터 유지 (우선순위 낮음)
            - 'same_type_duplicate': 동일 타입 재수집 (우선순위 동일)
            - 'error': 처리 중 오류
        site_code: 사이트 코드
        folder_name: 폴더명
        domain: 도메인명
        domain_configured: domain_key_config에 설정 여부
        existing_record: 기존 레코드 정보 (중복 시)
        error_message: 에러 메시지 (오류 시)

    Returns:
        로그 기록 성공 여부
    """
    try:
        from sqlalchemy import text
        import json

        # 우선순위 계산
        new_priority = self.get_priority(self.site_type)
        existing_priority = None
        existing_preprocessing_id = None
        existing_site_type = None
        existing_site_code = None
        duplicate_detail = None

        # 기존 레코드 정보 추출
        if existing_record:
            existing_preprocessing_id = existing_record['id']
            existing_site_type = existing_record['site_type']
            existing_site_code = existing_record['site_code']
            existing_priority = self.get_priority(existing_site_type)

            # 상세 정보 JSON 생성
            if duplicate_type == 'replaced':
                decision = '기존 데이터 교체'
                reason = f'우선순위 높음: {self.site_type}({new_priority}) > {existing_site_type}({existing_priority})'
            elif duplicate_type == 'kept_existing':
                decision = '기존 데이터 유지'
                reason = f'우선순위 낮음: {self.site_type}({new_priority}) < {existing_site_type}({existing_priority})'
            elif duplicate_type == 'same_type_duplicate':
                decision = '최신 데이터로 업데이트'
                reason = f'우선순위 동일: {self.site_type}({new_priority}) = {existing_site_type}({existing_priority})'
            else:
                decision = '알 수 없음'
                reason = f'duplicate_type={duplicate_type}'

            duplicate_detail = {
                'decision': decision,
                'reason': reason,
                'existing_folder': existing_record.get('folder_name'),
                'existing_url_key': existing_record.get('url_key'),
                'priority_comparison': f'{new_priority} vs {existing_priority}',
                'domain': domain,
                'domain_configured': domain_configured,
                'timestamp': datetime.now().isoformat()
            }

        elif duplicate_type == 'unconfigured_domain':
            # domain_key_config에 없는 경우
            duplicate_detail = {
                'decision': '신규 등록 (domain_key_config 없음)',
                'reason': 'domain_key_config 테이블에 설정이 없어서 중복 체크 생략',
                'domain': domain,
                'domain_configured': False,
                'timestamp': datetime.now().isoformat()
            }

        elif duplicate_type == 'new_inserted':
            # domain_key_config에 있지만 url_key_hash 중복 없음
            duplicate_detail = {
                'decision': '신규 등록',
                'reason': 'url_key_hash 중복 없음',
                'domain': domain,
                'domain_configured': domain_configured,
                'timestamp': datetime.now().isoformat()
            }

        # announcement_duplicate_log INSERT
        sql = text("""
            INSERT INTO announcement_duplicate_log (
                preprocessing_id,
                existing_preprocessing_id,
                duplicate_type,
                url_key_hash,
                new_site_type,
                new_site_code,
                existing_site_type,
                existing_site_code,
                new_priority,
                existing_priority,
                new_folder_name,
                duplicate_detail,
                error_message
            ) VALUES (
                :preprocessing_id,
                :existing_preprocessing_id,
                :duplicate_type,
                :url_key_hash,
                :new_site_type,
                :new_site_code,
                :existing_site_type,
                :existing_site_code,
                :new_priority,
                :existing_priority,
                :new_folder_name,
                :duplicate_detail,
                :error_message
            )
        """)

        # JSON 직렬화
        duplicate_detail_json = None
        if duplicate_detail:
            duplicate_detail_json = json.dumps(duplicate_detail, ensure_ascii=False)

        # 파라미터 바인딩
        params = {
            'preprocessing_id': preprocessing_id,
            'existing_preprocessing_id': existing_preprocessing_id,
            'duplicate_type': duplicate_type,
            'url_key_hash': url_key_hash,
            'new_site_type': self.site_type,
            'new_site_code': site_code,
            'existing_site_type': existing_site_type,
            'existing_site_code': existing_site_code,
            'new_priority': new_priority,
            'existing_priority': existing_priority,
            'new_folder_name': folder_name,
            'duplicate_detail': duplicate_detail_json,
            'error_message': error_message
        }

        # 실행
        session.execute(sql, params)
        session.commit()

        logger.debug(
            f"중복 로그 기록 완료: {duplicate_type} - "
            f"preprocessing_id={preprocessing_id}, "
            f"url_key_hash={url_key_hash[:16] if url_key_hash else 'None'}..."
        )

        return True

    except Exception as e:
        logger.error(f"중복 로그 기록 실패: {e}")
        # 로그 기록 실패해도 메인 처리는 계속 진행
        return False
```

---

### 3️⃣ get_priority() 함수

**파일**: `announcement_pre_processor.py`

```python
def get_priority(self, site_type: str) -> int:
    """
    site_type별 우선순위를 반환합니다.

    우선순위 규칙:
    - 지자체 데이터 (Eminwon/Homepage/Scraper) = 3 (높음)
    - API 데이터 (api_scrap) = 1 (낮음)
    - Unknown = 0 (최하)

    Args:
        site_type: 사이트 타입

    Returns:
        우선순위 (0-3)
    """
    priority_map = {
        'Eminwon': 3,
        'Homepage': 3,
        'Scraper': 3,
        'api_scrap': 1,
        'Unknown': 0,
    }
    return priority_map.get(site_type, 0)
```

---

## 📊 활용 방안

### 1️⃣ URL별 처리 이력 조회

**목적**: 특정 URL이 어떻게 처리되었는지 전체 이력 확인

**쿼리**:
```sql
-- URL 키로 검색
SELECT
    adl.created_at,
    adl.duplicate_type,
    adl.new_site_type,
    adl.new_site_code,
    adl.new_folder_name,
    adl.existing_site_type,
    adl.existing_site_code,
    adl.new_priority,
    adl.existing_priority,
    JSON_EXTRACT(adl.duplicate_detail, '$.decision') as decision,
    JSON_EXTRACT(adl.duplicate_detail, '$.reason') as reason,
    app.title,
    app.origin_url
FROM announcement_duplicate_log adl
LEFT JOIN announcement_pre_processing app ON adl.preprocessing_id = app.id
WHERE adl.url_key_hash = MD5('정규화된_URL_키')
ORDER BY adl.created_at ASC;
```

**결과 예시**:
```
created_at          | duplicate_type     | new_site_type | new_site_code | existing_site_type | decision
--------------------|-------------------|---------------|---------------|--------------------|-----------
2025-11-01 10:00:00 | new_inserted      | api_scrap     | bizInfo       | NULL               | NULL
2025-11-01 15:30:00 | replaced          | Homepage      | seoul         | api_scrap          | 기존 데이터 교체
2025-11-02 09:15:00 | kept_existing     | api_scrap     | bizInfo       | Homepage           | 기존 데이터 유지
2025-11-03 14:20:00 | same_type_duplicate| Homepage     | seoul         | Homepage           | 최신 데이터로 업데이트
```

**활용**:
- ✅ 한 URL의 전체 처리 흐름 파악
- ✅ 어느 사이트에서 먼저 수집했는지 확인
- ✅ 데이터 교체 이력 추적

---

### 2️⃣ 일별 중복 발생 통계

**목적**: 매일 얼마나 많은 중복이 발생하는지 추적

**쿼리**:
```sql
SELECT
    DATE(created_at) as date,
    duplicate_type,
    COUNT(*) as count,
    COUNT(DISTINCT url_key_hash) as unique_urls,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY DATE(created_at)), 2) as percentage
FROM announcement_duplicate_log
WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
GROUP BY DATE(created_at), duplicate_type
ORDER BY date DESC, count DESC;
```

**결과 예시**:
```
date       | duplicate_type      | count | unique_urls | percentage
-----------|--------------------| ------|-------------|------------
2025-11-01 | new_inserted       | 1200  | 1200        | 75.00%
2025-11-01 | kept_existing      | 280   | 250         | 17.50%
2025-11-01 | replaced           | 80    | 75          | 5.00%
2025-11-01 | same_type_duplicate| 40    | 35          | 2.50%
```

**활용**:
- ✅ 중복 발생률 추이 모니터링
- ✅ 신규 공고 비율 확인
- ✅ 이상 패턴 감지 (갑자기 중복률 급증 등)

---

### 3️⃣ 사이트별 중복 발생률

**목적**: 어떤 사이트에서 중복이 많이 발생하는지 파악

**쿼리**:
```sql
SELECT
    new_site_code,
    new_site_type,
    COUNT(*) as total_attempts,
    SUM(CASE WHEN duplicate_type = 'new_inserted' THEN 1 ELSE 0 END) as new_count,
    SUM(CASE WHEN duplicate_type IN ('replaced', 'kept_existing', 'same_type_duplicate') THEN 1 ELSE 0 END) as duplicate_count,
    ROUND(SUM(CASE WHEN duplicate_type IN ('replaced', 'kept_existing', 'same_type_duplicate') THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as duplicate_rate,
    COUNT(DISTINCT url_key_hash) as unique_urls
FROM announcement_duplicate_log
WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
  AND url_key_hash IS NOT NULL
GROUP BY new_site_code, new_site_type
ORDER BY duplicate_rate DESC
LIMIT 20;
```

**결과 예시**:
```
new_site_code | new_site_type | total_attempts | new_count | duplicate_count | duplicate_rate | unique_urls
--------------|---------------|----------------|-----------|-----------------|----------------|-------------
bizInfo       | api_scrap     | 5000           | 4000      | 1000            | 20.00%         | 4500
seoul         | Homepage      | 3500           | 3000      | 500             | 14.29%         | 3200
busan         | Homepage      | 2800           | 2500      | 300             | 10.71%         | 2650
```

**활용**:
- ✅ 중복 발생이 많은 사이트 식별
- ✅ 스크레이핑 주기 조정 근거
- ✅ 사이트별 데이터 품질 비교

---

### 4️⃣ 우선순위 적용 검증

**목적**: 지자체 > API 우선순위가 제대로 적용되는지 확인

**쿼리**:
```sql
-- 우선순위 비교 결과
SELECT
    duplicate_type,
    new_site_type,
    existing_site_type,
    new_priority,
    existing_priority,
    COUNT(*) as count
FROM announcement_duplicate_log
WHERE duplicate_type IN ('replaced', 'kept_existing')
  AND created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
GROUP BY duplicate_type, new_site_type, existing_site_type, new_priority, existing_priority
ORDER BY count DESC;
```

**결과 예시**:
```
duplicate_type | new_site_type | existing_site_type | new_priority | existing_priority | count
---------------|---------------|--------------------|--------------|--------------------|-------
kept_existing  | api_scrap     | Homepage          | 1            | 3                  | 280
kept_existing  | api_scrap     | Eminwon           | 1            | 3                  | 150
replaced       | Homepage      | api_scrap         | 3            | 1                  | 80
replaced       | Eminwon       | api_scrap         | 3            | 1                  | 45
```

**검증**:
- ✅ `kept_existing`에서 new_priority < existing_priority 확인
- ✅ `replaced`에서 new_priority > existing_priority 확인
- ✅ 우선순위 로직 정상 동작 검증

**이상 케이스 탐지**:
```sql
-- 우선순위 역전 케이스 (버그 가능성)
SELECT *
FROM announcement_duplicate_log
WHERE
    (duplicate_type = 'kept_existing' AND new_priority > existing_priority)
    OR
    (duplicate_type = 'replaced' AND new_priority < existing_priority)
ORDER BY created_at DESC;
```

---

### 5️⃣ 자주 중복되는 URL Top 20

**목적**: 어떤 URL이 여러 소스에서 중복 수집되는지 파악

**쿼리**:
```sql
SELECT
    adl.url_key_hash,
    COUNT(*) as occurrence_count,
    COUNT(DISTINCT adl.new_site_code) as site_count,
    GROUP_CONCAT(DISTINCT adl.new_site_type ORDER BY adl.new_site_type) as site_types,
    GROUP_CONCAT(DISTINCT adl.new_site_code ORDER BY adl.new_site_code) as site_codes,
    MAX(app.title) as title,
    MAX(app.origin_url) as origin_url,
    MIN(adl.created_at) as first_seen,
    MAX(adl.created_at) as last_seen
FROM announcement_duplicate_log adl
LEFT JOIN announcement_pre_processing app ON adl.preprocessing_id = app.id
WHERE adl.created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
  AND adl.url_key_hash IS NOT NULL
GROUP BY adl.url_key_hash
HAVING occurrence_count >= 3
ORDER BY occurrence_count DESC, site_count DESC
LIMIT 20;
```

**결과 예시**:
```
url_key_hash    | occurrence_count | site_count | site_types                  | site_codes          | title
----------------|------------------|------------|-----------------------------|--------------------|--------
abc123def456... | 8                | 4          | Homepage,Eminwon,api_scrap  | seoul,busan,bizInfo| 창업지원
xyz789ghi012... | 6                | 3          | Homepage,api_scrap          | seoul,bizInfo,smes24| 중소기업
```

**활용**:
- ✅ 여러 소스에서 수집되는 인기 공고 식별
- ✅ 스크레이핑 최적화 (중복 제거)
- ✅ 데이터 소스별 커버리지 분석

---

### 6️⃣ 에러 분석

**목적**: URL 정규화 실패 등 에러 패턴 파악

**쿼리**:
```sql
SELECT
    error_message,
    new_site_code,
    new_site_type,
    COUNT(*) as error_count,
    MAX(created_at) as last_occurrence
FROM announcement_duplicate_log
WHERE duplicate_type = 'error'
  AND created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
GROUP BY error_message, new_site_code, new_site_type
ORDER BY error_count DESC
LIMIT 20;
```

**결과 예시**:
```
error_message              | new_site_code | new_site_type | error_count | last_occurrence
---------------------------|---------------|---------------|-------------|------------------
URL 정규화 실패            | bizInfo       | api_scrap     | 25          | 2025-11-01 15:30
domain_key_config 없음     | unknown_site  | Scraper       | 18          | 2025-11-01 14:20
origin_url이 유효하지 않음  | seoul         | Homepage      | 12          | 2025-11-01 13:15
```

**활용**:
- ✅ 에러 발생 패턴 분석
- ✅ 우선순위 있는 버그 수정
- ✅ URL 정규화 로직 개선

---

## 🧪 테스트 시나리오

### 테스트 1: 신규 삽입

**입력**:
```python
folder_name = "bizInfo_20251101_001"
site_code = "bizInfo"
site_type = "api_scrap"
origin_url = "https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId=NEW001"
url_key = "bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId=NEW001"
url_key_hash = MD5(url_key) = "aaa111bbb222..."
```

**예상 결과**:
```sql
-- announcement_pre_processing
INSERT 성공, id=2001

-- announcement_duplicate_log
INSERT INTO announcement_duplicate_log VALUES (
    preprocessing_id = 2001,
    existing_preprocessing_id = NULL,
    duplicate_type = 'new_inserted',
    url_key_hash = 'aaa111bbb222...',
    new_site_type = 'api_scrap',
    new_site_code = 'bizInfo',
    existing_site_type = NULL,
    existing_site_code = NULL,
    new_priority = 1,
    existing_priority = NULL,
    ...
)
```

**검증 쿼리**:
```sql
SELECT * FROM announcement_duplicate_log WHERE preprocessing_id = 2001;
-- duplicate_type = 'new_inserted' 확인
```

---

### 테스트 2: 지자체가 API 교체

**전제 조건**:
```sql
-- 기존 데이터 (bizInfo)
INSERT INTO announcement_pre_processing (id, site_type, site_code, url_key_hash, ...)
VALUES (2001, 'api_scrap', 'bizInfo', 'aaa111bbb222...', ...);
```

**입력**:
```python
folder_name = "seoul_20251101_100"
site_code = "seoul"
site_type = "Homepage"
origin_url = "https://www.seoul.go.kr/support/announce/view.do?id=12345"
url_key = "bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId=NEW001"  # 동일
url_key_hash = "aaa111bbb222..."  # 동일
```

**예상 결과**:
```sql
-- announcement_pre_processing
UPDATE id=2001 SET site_type='Homepage', site_code='prv_seoul', ...

-- announcement_duplicate_log
INSERT INTO announcement_duplicate_log VALUES (
    preprocessing_id = 2001,
    existing_preprocessing_id = 2001,
    duplicate_type = 'replaced',
    url_key_hash = 'aaa111bbb222...',
    new_site_type = 'Homepage',
    new_site_code = 'seoul',
    existing_site_type = 'api_scrap',
    existing_site_code = 'bizInfo',
    new_priority = 3,
    existing_priority = 1,
    duplicate_detail = '{"decision": "기존 데이터 교체", "reason": "우선순위 높음: Homepage(3) > api_scrap(1)", ...}',
    ...
)
```

**검증 쿼리**:
```sql
-- 로그 확인
SELECT * FROM announcement_duplicate_log WHERE preprocessing_id = 2001 ORDER BY created_at DESC LIMIT 2;
-- 첫 번째: new_inserted (최초 삽입)
-- 두 번째: replaced (교체)

-- 데이터 확인
SELECT site_type, site_code FROM announcement_pre_processing WHERE id = 2001;
-- site_type = 'Homepage', site_code = 'prv_seoul' 확인
```

---

### 테스트 3: API가 지자체 유지

**전제 조건**:
```sql
-- 기존 데이터 (seoul)
UPDATE announcement_pre_processing SET site_type='Homepage', site_code='prv_seoul' WHERE id=2001;
```

**입력**:
```python
folder_name = "bizInfo_20251102_001"
site_code = "bizInfo"
site_type = "api_scrap"
url_key_hash = "aaa111bbb222..."  # 동일
```

**예상 결과**:
```sql
-- announcement_pre_processing
변경 없음 (기존 데이터 유지)

-- announcement_duplicate_log
INSERT INTO announcement_duplicate_log VALUES (
    preprocessing_id = 2001,  -- 동일 ID
    existing_preprocessing_id = 2001,
    duplicate_type = 'kept_existing',
    url_key_hash = 'aaa111bbb222...',
    new_site_type = 'api_scrap',
    new_site_code = 'bizInfo',
    existing_site_type = 'Homepage',
    existing_site_code = 'prv_seoul',
    new_priority = 1,
    existing_priority = 3,
    duplicate_detail = '{"decision": "기존 데이터 유지", "reason": "우선순위 낮음: api_scrap(1) < Homepage(3)", ...}',
    ...
)
```

**검증 쿼리**:
```sql
-- 로그 확인
SELECT duplicate_type, new_priority, existing_priority
FROM announcement_duplicate_log
WHERE preprocessing_id = 2001
ORDER BY created_at DESC
LIMIT 1;
-- duplicate_type = 'kept_existing', new_priority=1, existing_priority=3 확인

-- 데이터 변경 없음 확인
SELECT site_type FROM announcement_pre_processing WHERE id = 2001;
-- site_type = 'Homepage' (변경 없음)
```

---

### 테스트 4: 동일 타입 재수집

**전제 조건**:
```sql
UPDATE announcement_pre_processing SET site_type='api_scrap', site_code='bizInfo' WHERE id=2001;
```

**입력**:
```python
folder_name = "bizInfo_20251103_001"
site_code = "bizInfo"
site_type = "api_scrap"
url_key_hash = "aaa111bbb222..."  # 동일
```

**예상 결과**:
```sql
-- announcement_pre_processing
UPDATE id=2001 SET content_md='최신 내용', updated_at=NOW(), ...

-- announcement_duplicate_log
INSERT INTO announcement_duplicate_log VALUES (
    preprocessing_id = 2001,
    existing_preprocessing_id = 2001,
    duplicate_type = 'same_type_duplicate',
    url_key_hash = 'aaa111bbb222...',
    new_site_type = 'api_scrap',
    new_site_code = 'bizInfo',
    existing_site_type = 'api_scrap',
    existing_site_code = 'bizInfo',
    new_priority = 1,
    existing_priority = 1,
    duplicate_detail = '{"decision": "최신 데이터로 업데이트", "reason": "우선순위 동일: api_scrap(1) = api_scrap(1)", ...}',
    ...
)
```

**검증 쿼리**:
```sql
SELECT duplicate_type, new_priority, existing_priority
FROM announcement_duplicate_log
WHERE preprocessing_id = 2001
ORDER BY created_at DESC
LIMIT 1;
-- duplicate_type = 'same_type_duplicate', new_priority=1, existing_priority=1 확인
```

---

## 📚 종합 활용 대시보드

### Grafana 패널 구성

**패널 1: 일일 처리 현황**
```sql
SELECT
    DATE(created_at) as time,
    duplicate_type,
    COUNT(*) as value
FROM announcement_duplicate_log
WHERE $__timeFilter(created_at)
GROUP BY time, duplicate_type
ORDER BY time;
```

**패널 2: 우선순위 적용 현황**
```sql
SELECT
    CONCAT(new_site_type, ' → ', COALESCE(existing_site_type, 'NEW')) as transition,
    COUNT(*) as count
FROM announcement_duplicate_log
WHERE DATE(created_at) = CURDATE()
GROUP BY transition
ORDER BY count DESC;
```

**패널 3: 중복률 추이**
```sql
SELECT
    DATE(created_at) as time,
    ROUND(SUM(CASE WHEN duplicate_type != 'new_inserted' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as duplicate_rate
FROM announcement_duplicate_log
WHERE $__timeFilter(created_at)
GROUP BY time
ORDER BY time;
```

---

## ✅ 구현 체크리스트

### 코드 구현
- [ ] `_save_processing_result()` 함수 수정
  - [ ] url_key_hash 계산
  - [ ] url_key_hash 기반 중복 체크
  - [ ] 우선순위 비교 로직
  - [ ] announcement_duplicate_log 호출
- [ ] `_log_announcement_duplicate()` 함수 작성
  - [ ] duplicate_type 결정 로직
  - [ ] duplicate_detail JSON 생성
  - [ ] INSERT 쿼리 실행
- [ ] `get_priority()` 함수 확인

### 데이터베이스
- [ ] announcement_duplicate_log 테이블 생성
- [ ] 인덱스 확인 (url_key_hash)
- [ ] 외래키 확인 (preprocessing_id)

### 테스트
- [ ] 신규 삽입 테스트
- [ ] 교체 (replaced) 테스트
- [ ] 유지 (kept_existing) 테스트
- [ ] 동일 타입 중복 테스트
- [ ] 에러 케이스 테스트

### 분석 쿼리
- [ ] URL별 이력 조회
- [ ] 일별 통계
- [ ] 사이트별 통계
- [ ] 우선순위 검증
- [ ] 에러 분석

### 문서화
- [ ] 코드 주석
- [ ] README 업데이트
- [ ] 쿼리 샘플 문서

---

**작성일**: 2025-11-01
**최종 업데이트**: 2025-11-03
**버전**: 1.1 (실제 구현 반영)
**핵심**: url_key_hash 기반 중복 체크 및 로그 기록 (UPSERT 방식, domain_key_config 연동)
**상태**: 구현 완료 및 운영 중

## 🔄 변경 이력

### v1.1 (2025-11-03)
- UPSERT 방식 반영 (INSERT ... ON DUPLICATE KEY UPDATE)
- `unconfigured_domain` duplicate_type 추가
- `domain`, `domain_configured` 파라미터 추가
- url_key_hash GENERATED COLUMN 방식 반영
- Fallback 비활성화 정책 반영
- 실제 코드 구현 내용 기준으로 문서 전면 수정

### v1.0 (2025-11-01)
- 초기 설계 문서 작성
