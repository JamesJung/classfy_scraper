# processing_status 종류 및 로직 분석

## 📋 중요: 두 가지 다른 processing_status

코드에 **이름은 같지만 용도가 다른** 두 가지 processing_status가 있습니다:

### 1️⃣ 함수 파라미터 `status` (DB 저장용)
- **변수명**: `status` (파라미터)
- **저장 위치**: `announcement_pre_processing.processing_status` 컬럼
- **용도**: 전체 처리 결과를 사용자에게 표시
- **언어**: 한글/영문 혼재

### 2️⃣ 로컬 변수 `processing_status` (내부 로직용)
- **변수명**: `processing_status` (로컬 변수)
- **저장 위치**: 메모리 (DB 저장 안 됨)
- **용도**: UPSERT 결과를 duplicate_type으로 매핑하기 위한 중간 변수
- **언어**: 영문

---

## 1️⃣ DB 저장용 `status` 파라미터

### 종류 (5가지)

| status 값 | 의미 | 설정 위치 | 사용 빈도 (실제 DB) |
|-----------|------|----------|-------------------|
| **"성공"** | 정상 처리 완료 | Line 697, 1860 (기본값) | 3,232건 (25.5%) |
| **"제외"** | 제외 키워드 매칭 | Line 674 | 5,885건 (46.5%) |
| **"error"** | 처리 중 오류 | Line 551, 578, 656, 716 | 1건 (0.01%) |
| **"success"** | 정상 처리 (영문) | ? (구 버전?) | 237건 (1.9%) |
| **"archived"** | 아카이브됨 | ? (외부 스크립트?) | 3,387건 (26.7%) |

### 설정 로직

#### Case 1: "성공" (Line 697)
```python
# 정상 처리 완료
result_id = self._save_processing_result(
    folder_name=folder_name,
    site_code=self.site_code,
    content_md=content_md,
    combined_content=combined_content,
    attachment_filenames=attachment_filenames,
    status="성공",  # ← 기본값
    title=title,
    origin_url=origin_url,
    url_key=url_key,
    scraping_url=scraping_url,
    announcement_date=announcement_date,
    attachment_files_info=attachment_files_info,
    force=force,
)
```

#### Case 2: "제외" (Line 674)
```python
# 제외 키워드 매칭
exclusion_keywords_found, exclusion_reason = self._check_exclusion_keywords(
    combined_content
)

if exclusion_keywords_found:
    logger.info(f"제외 키워드 발견: {exclusion_reason}")
    result_id = self._save_processing_result(
        folder_name=folder_name,
        site_code=self.site_code,
        content_md=content_md,
        combined_content=combined_content,
        attachment_filenames=attachment_filenames,
        status="제외",  # ← 제외
        exclusion_keywords=exclusion_keywords_found,
        exclusion_reason=exclusion_reason,
        # ...
    )
```

#### Case 3: "error" (Line 551, 578, 656, 716)
```python
# Line 551: content.md 파일 없음
if not os.path.exists(content_md_path):
    logger.error(f"content.md 파일을 찾을 수 없습니다: {content_md_path}")
    self._save_processing_result(
        folder_name=folder_name,
        site_code=self.site_code,
        content_md="",
        combined_content="",
        status="error",
        error_message="content.md 파일 없음",
    )
    return

# Line 578: PDF 변환 실패
except Exception as e:
    logger.error(f"PDF 처리 실패: {pdf_file}, {e}")
    self._save_processing_result(
        folder_name=folder_name,
        site_code=self.site_code,
        content_md=content_md,
        combined_content=combined_content,
        status="error",
        error_message=f"PDF 처리 실패: {str(e)}",
    )
    return

# Line 656: 전체 처리 실패
except Exception as e:
    logger.error(f"처리 중 오류 발생: {folder_path}, {e}")
    self._save_processing_result(
        folder_name=folder_name,
        site_code=self.site_code,
        content_md="",
        combined_content="",
        status="error",
        error_message=str(e),
    )

# Line 716: URL 키 추출 실패
except Exception as e:
    logger.error(f"URL 키 추출 실패: {origin_url}, {e}")
    self._save_processing_result(
        folder_name=folder_name,
        # ...
        status="error",
        error_message=f"URL 키 추출 실패: {str(e)}",
    )
```

#### "success"와 "archived"의 출처
- 코드에서 직접 설정하는 곳이 없음
- 추정:
  - `"success"`: 구 버전 코드에서 사용 (현재는 "성공" 사용)
  - `"archived"`: 외부 스크립트 또는 수동 업데이트

---

## 2️⃣ 내부 로직용 `processing_status` 변수

### 종류 (4가지)

| processing_status 값 | 의미 | 설정 조건 | duplicate_type 매핑 |
|---------------------|------|----------|-------------------|
| **'new_inserted'** | 신규 삽입 | affected_rows == 1 | 'new_inserted' |
| **'duplicate_updated'** | 중복 업데이트 | affected_rows == 2 | 'replaced' 또는 'same_type_duplicate' |
| **'duplicate_preserved'** | 중복 유지 | affected_rows == 2 + 우선순위 낮음 | 'kept_existing' |
| **'failed'** | 처리 실패 | 논리 오류 또는 예상치 못한 경우 | 'error' |

### 설정 로직

#### Case 1: 'new_inserted' (Line 2157)
```python
# UPSERT 실행 후
elif affected_rows == 1:
    # 새로 INSERT됨
    processing_status = 'new_inserted'  # ← 중복 체크 결과 (duplicate_type용)
    logger.debug(f"새 레코드 삽입: ID={record_id}, url_key_hash={url_key_hash[:16]}...")
```

**조건**:
- `affected_rows == 1` (신규 INSERT 성공)
- url_key가 있고 domain_key_config도 있음

#### Case 2: 'duplicate_updated' (Line 2177, 2190, 2216)
```python
# 우선순위가 더 높음 (Line 2177)
if current_priority > existing_priority:
    processing_status = 'duplicate_updated'
    duplicate_reason = {
        "reason": f"{self.site_type} (priority {current_priority}) > {existing_site_type} (priority {existing_priority})",
        "current_priority": current_priority,
        "existing_priority": existing_priority,
        "updated": True
    }

# 우선순위가 같음 (Line 2190)
elif current_priority == existing_priority:
    processing_status = 'duplicate_updated'
    duplicate_reason = {
        "reason": f"{self.site_type} (priority {current_priority}) == {existing_site_type} (priority {existing_priority}), 최신 데이터 우선",
        "current_priority": current_priority,
        "existing_priority": existing_priority,
        "updated": True
    }

# UPSERT 전 조회 실패 (Line 2216)
else:
    processing_status = 'duplicate_updated'
    duplicate_reason = {"reason": "UPSERT 전 기존 레코드 조회 실패, 업데이트됨으로 간주"}
    logger.warning("UPSERT 전 기존 레코드 조회 실패, 업데이트됨으로 간주")
```

**조건**:
- `affected_rows == 2` (UPDATE 발생)
- `current_priority >= existing_priority` 또는 기존 레코드 조회 실패

#### Case 3: 'duplicate_preserved' (Line 2203)
```python
else:
    # 현재가 더 낮은 우선순위 → 기존 유지
    processing_status = 'duplicate_preserved'
    duplicate_reason = {
        "reason": f"{self.site_type} (priority {current_priority}) < {existing_site_type} (priority {existing_priority})",
        "current_priority": current_priority,
        "existing_priority": existing_priority,
        "updated": False
    }
    logger.info(
        f"⚠️  우선순위 낮음: {self.site_type}({current_priority}) < "
        f"{existing_site_type}({existing_priority}) → 기존 데이터 유지"
    )
```

**조건**:
- `affected_rows == 2` (UPDATE 발생)
- `current_priority < existing_priority`

#### Case 4: 'failed' (Line 2147, 2222)
```python
# 논리 오류 (Line 2147)
if not domain_has_config:
    logger.error(
        f"❌ 논리 오류: url_key는 생성되었지만 domain_key_config가 없음! "
        f"domain={domain}, url_key={url_key[:50]}... "
        f"fallback 로직이 재활성화되었거나 버그일 수 있습니다."
    )
    processing_status = 'failed'
    duplicate_reason = {
        "reason": f"Logic error: url_key exists but domain_key_config missing (domain={domain})",
        "domain": domain,
        "url_key": url_key
    }

# 예상치 못한 affected_rows (Line 2222)
else:
    # 예상치 못한 경우
    processing_status = 'failed'
    duplicate_reason = {"reason": f"Unexpected affected_rows: {affected_rows}"}
    logger.warning(f"예상치 못한 affected_rows: {affected_rows}")
```

**조건**:
- url_key는 있는데 domain_has_config가 False (논리 오류)
- affected_rows가 1도 2도 아닌 경우

---

## 🔄 processing_status → duplicate_type 매핑

### 매핑 로직 (Line 2260-2268)

```python
# duplicate_type 매핑
duplicate_type_map = {
    'new_inserted': 'new_inserted',
    'duplicate_updated': 'replaced',  # 기본값 (우선순위 비교로 세부화)
    'duplicate_preserved': 'kept_existing',
    'failed': 'error'
}

# duplicate_type 결정
announcement_duplicate_type = duplicate_type_map.get(processing_status, 'unknown')  # 기본값을 'unknown'으로 변경
```

### 세부 타입 결정 (Line 2271-2281)

```python
# duplicate_updated의 경우 우선순위 비교로 세부 타입 결정
if processing_status == 'duplicate_updated' and existing_record_before_upsert:
    current_priority = self._get_priority(self.site_type)
    existing_priority_value = self._get_priority(existing_record_before_upsert.site_type)

    if current_priority == existing_priority_value:
        # 우선순위 동일 → same_type_duplicate
        announcement_duplicate_type = 'same_type_duplicate'
    elif current_priority > existing_priority_value:
        # 우선순위 높음 → replaced
        announcement_duplicate_type = 'replaced'
    # current_priority < existing_priority_value는 이론적으로 발생하지 않음 (UPSERT 조건상)
```

### 최종 매핑 테이블

| processing_status | 우선순위 조건 | duplicate_type |
|------------------|------------|----------------|
| 'new_inserted' | - | 'new_inserted' |
| 'duplicate_updated' | current == existing | 'same_type_duplicate' |
| 'duplicate_updated' | current > existing | 'replaced' |
| 'duplicate_updated' | current < existing | 'replaced' (이론적으로 불가능) |
| 'duplicate_preserved' | current < existing | 'kept_existing' |
| 'failed' | - | 'error' |
| (기타) | - | 'unknown' |

---

## 📊 실제 데이터 분석

### announcement_pre_processing.processing_status (DB 저장값)
```sql
SELECT processing_status, COUNT(*) as count
FROM announcement_pre_processing
GROUP BY processing_status
ORDER BY count DESC;

+-------------------+-------+
| processing_status | count |
+-------------------+-------+
| 제외              | 5,885 | (46.5%)
| archived          | 3,387 | (26.7%)
| 성공              | 3,232 | (25.5%)
| success           |   237 | (1.9%)
| error             |     1 | (0.01%)
+-------------------+-------+
```

**분석**:
- "제외": 제외 키워드 매칭 (정상)
- "archived": 외부에서 업데이트 (정상)
- "성공": 정상 처리 (정상)
- "success": 구 버전 (정상)
- "error": 처리 중 오류 (1건만 존재)

### announcement_duplicate_log.duplicate_type (로그 값)
```sql
SELECT duplicate_type, COUNT(*) as count
FROM announcement_duplicate_log
GROUP BY duplicate_type
ORDER BY count DESC;

+---------------------+-------+
| duplicate_type      | count |
+---------------------+-------+
| new_inserted        | 5,476 | (92.81%)
| unknown             |   422 | (7.15%)
| error               |   213 | (3.61%)
| unconfigured_domain |     2 | (0.03%)
+---------------------+-------+
```

**분석**:
- "new_inserted": 신규 삽입 (정상)
- "unknown": processing_status가 매핑에 없는 경우 (버그)
- "error": processing_status='failed' (DomainKeyExtractor 초기화 문제)
- "unconfigured_domain": url_key 없음 (정상)

---

## 🐛 문제점 요약

### 문제 1: 두 가지 processing_status 혼동
- **DB 저장용 `status`**: "성공", "제외", "error" (한글/영문)
- **내부 로직용 `processing_status`**: 'new_inserted', 'duplicate_updated', etc. (영문)
- **혼동 가능성**: 같은 이름으로 다른 용도

### 문제 2: processing_status='failed' 오판
- **원인 1**: DomainKeyExtractor 초기화 실패 → domain_has_config 항상 False
- **원인 2**: API 데이터는 외부 도메인 사용이 정상인데 'failed'로 판단

### 문제 3: 'unknown' duplicate_type 발생
- `processing_status`가 매핑 테이블에 없는 값인 경우 'unknown' 반환
- 422건 발생 (원인 조사 필요)

---

## ✅ 권장 조치

### 1. 변수명 명확화 (선택)
```python
# 현재
status: str = "성공"  # DB 저장용
processing_status = 'new_inserted'  # 내부 로직용

# 개선안
db_processing_status: str = "성공"  # DB 저장용
upsert_result_status = 'new_inserted'  # 내부 로직용
```

### 2. DomainKeyExtractor 초기화 수정 (필수)
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

### 3. 'failed' 판단 로직 개선 (권장)
```python
# Line 2141-2152
if not domain_has_config:
    if self.site_type == 'api_scrap':
        # API 데이터는 외부 도메인 정상
        processing_status = 'new_inserted'
    else:
        # 지자체 데이터는 오류
        processing_status = 'failed'
```

### 4. 'unknown' 원인 조사 (필수)
```sql
-- 어떤 processing_status 값이 'unknown'을 발생시켰는지 확인
-- (현재는 로그에 기록되지 않아 확인 불가)
```

---

**작성일**: 2025-11-05
**작성자**: AI Assistant
