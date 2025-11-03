# daily_api_batch.sh 실행 시 DB 등록 흐름 점검 보고서

## ✅ 결론

**`daily_api_batch.sh` 실행 만으로 `announcement_pre_processing` 테이블에 데이터가 등록됩니다.**

---

## 🔍 실행 흐름 분석

### 1️⃣ daily_api_batch.sh 실행

```bash
#!/bin/bash

API_DIR="/home/zium/moabojo/incremental/api"
SITES=("bizInfo" "smes24" "kStartUp")

# 각 사이트 순차 처리
for site in "${SITES[@]}"; do
    python3 announcement_pre_processor.py -d "$API_DIR" --site-code "$site"
done
```

**실제 실행 명령:**
```bash
# bizInfo 처리
python3 announcement_pre_processor.py -d /home/zium/moabojo/incremental/api --site-code bizInfo

# smes24 처리
python3 announcement_pre_processor.py -d /home/zium/moabojo/incremental/api --site-code smes24

# kStartUp 처리
python3 announcement_pre_processor.py -d /home/zium/moabojo/incremental/api --site-code kStartUp
```

---

### 2️⃣ announcement_pre_processor.py 메인 함수

**파일**: `announcement_pre_processor.py:2055-2143`

```python
def main():
    args = parser.parse_args()

    # 디렉토리 존재 확인
    base_directory = current_dir / args.directory
    # → /home/zium/moabojo/incremental/api

    # site_type 결정
    site_type = determine_site_type(args.directory, args.site_code)
    # directory: "/home/zium/moabojo/incremental/api"
    # site_code: "bizInfo" (또는 smes24, kStartUp)
    # → site_type = "api_scrap"

    # 프로세서 초기화
    processor = AnnouncementPreProcessor(
        site_type="api_scrap",  # ← 여기
        attach_force=args.attach_force,
        site_code="bizInfo",
        lazy_init=False,
    )

    # 사이트 디렉토리 처리 실행
    results = processor.process_site_directories(
        base_directory,  # /home/zium/moabojo/incremental/api
        args.site_code,  # bizInfo
        args.force       # False (기본값)
    )
```

---

### 3️⃣ process_site_directories() - 디렉토리 검색

**파일**: `announcement_pre_processor.py:315-394`

```python
def process_site_directories(self, base_dir: Path, site_code: str, force: bool = False):
    # 처리할 디렉토리 목록 찾기
    target_directories = self._find_target_directories(base_dir, site_code, force)
    # → /home/zium/moabojo/incremental/api/bizInfo 내의 모든 content.md 있는 디렉토리

    # 각 디렉토리 순회
    for directory in target_directories:
        # 폴더명 생성 (상대 경로)
        relative_path = directory.relative_to(site_dir)
        folder_name = str(relative_path).replace("/", "_")
        # 예: "2025-11-01_BIZ_ANNOUNCEMENT_001"

        # 이미 처리됨 확인 (force가 False일 때만)
        if not force and self._is_already_processed(folder_name, site_code):
            continue  # 건너뜀

        # 디렉토리 처리 실행
        success = self.process_directory_with_custom_name(
            directory,      # /home/zium/moabojo/incremental/api/bizInfo/2025-11-01/...
            site_code,      # bizInfo
            folder_name,    # 2025-11-01_BIZ_ANNOUNCEMENT_001
            force           # False
        )
```

**주요 로직:**
- ✅ `content.md` 파일이 있는 디렉토리만 처리
- ✅ 이미 처리된 항목은 자동 건너뜀 (중복 방지)
- ✅ 각 디렉토리별로 `process_directory_with_custom_name()` 호출

---

### 4️⃣ process_directory_with_custom_name() - 데이터 추출

**파일**: `announcement_pre_processor.py:423-691`

```python
def process_directory_with_custom_name(self, directory_path, site_code, folder_name, force):
    # 1. 제외 키워드 체크
    excluded_keywords = self._check_exclusion_keywords(folder_name)

    # 2. API 사이트 특수 처리 (bizInfo, smes24, kStartUp)
    if site_code in ["kStartUp", "bizInfo", "smes24"]:
        # content.md 읽기
        content_md_path = directory_path / "content.md"
        with open(content_md_path, "r", encoding="utf-8") as f:
            content_md = f.read()

        # content.md에서 정보 추출
        title = self._extract_title_from_content(content_md)
        origin_url = self._extract_origin_url_from_content(content_md)
        scraping_url = self._extract_scraping_url_from_content(content_md)

        # JSON 파일에서 announcement_date 추출
        # 우선순위: announcement.json → data.json → info.json → 기타 .json
        json_files = ["announcement.json", "data.json", "info.json"]
        for json_name in json_files:
            json_path = directory_path / json_name
            if json_path.exists():
                json_data = json.load(open(json_path))
                announcement_date = self._convert_to_yyyymmdd(
                    json_data.get("announcementDate", "")
                )
                break

    # 3. URL 정규화 (url_key 생성)
    url_key = self.url_key_extractor.extract_url_key(origin_url, site_code)

    # 4. 첨부파일 처리
    combined_content, attachment_filenames, attachment_files_info = \
        self._process_attachments_separately(directory_path)

    # 5. 제외 키워드가 있으면 제외 처리로 저장
    if excluded_keywords:
        return self._save_processing_result(
            folder_name, site_code, content_md, combined_content,
            status="제외", exclusion_keywords=excluded_keywords, ...
        )

    # 6. 데이터베이스에 저장 ← 여기서 DB 등록!
    record_id = self._save_processing_result(
        folder_name,           # 2025-11-01_BIZ_ANNOUNCEMENT_001
        site_code,             # bizInfo
        content_md,            # content.md 내용
        combined_content,      # 첨부파일 내용
        attachment_filenames,  # ["file1.pdf", "file2.hwp"]
        attachment_files_info, # [{"filename": "file1.pdf", "content": "..."}, ...]
        title,                 # 공고 제목
        announcement_date,     # 20251101
        origin_url,            # https://www.bizinfo.go.kr/...
        url_key,               # 정규화된 URL
        scraping_url,          # 스크래핑한 URL
        status="성공",
        force=False
    )
```

**핵심 데이터 추출:**
- ✅ `content.md` 파일 읽기
- ✅ JSON 파일에서 날짜 정보 추출
- ✅ URL 정규화 (url_key 생성)
- ✅ 첨부파일 처리
- ✅ 제외 키워드 체크

---

### 5️⃣ _save_processing_result() - DB 저장

**파일**: `announcement_pre_processor.py:1650-1850`

#### INSERT 쿼리 (force=False 일 때)

```python
def _save_processing_result(self, folder_name, site_code, content_md, ...):
    with self.db_manager.SessionLocal() as session:
        # force가 False인 경우 (기본값)
        sql = text("""
            INSERT INTO announcement_pre_processing (
                folder_name, site_type, site_code, content_md, combined_content,
                attachment_filenames, attachment_files_list, exclusion_keyword, exclusion_reason,
                title, origin_url, url_key, scraping_url, announcement_date,
                processing_status, error_message, created_at, updated_at
            ) VALUES (
                :folder_name, :site_type, :site_code, :content_md, :combined_content,
                :attachment_filenames, :attachment_files_list, :exclusion_keyword, :exclusion_reason,
                :title, :origin_url, :url_key, :scraping_url, :announcement_date,
                :processing_status, :error_message, NOW(), NOW()
            )
        """)

        # 파라미터 바인딩
        params = {
            "folder_name": folder_name,               # 2025-11-01_BIZ_ANNOUNCEMENT_001
            "site_type": self.site_type,              # "api_scrap"
            "site_code": site_code,                   # "bizInfo"
            "content_md": content_md,                 # content.md 내용
            "combined_content": combined_content,     # 첨부파일 내용
            "attachment_filenames": ",".join(attachment_filenames),
            "attachment_files_list": json.dumps(attachment_files_info),
            "exclusion_keyword": ",".join(exclusion_keywords) if exclusion_keywords else None,
            "exclusion_reason": exclusion_reason,
            "title": title,                           # 공고 제목
            "origin_url": origin_url,                 # 원본 URL
            "url_key": url_key,                       # 정규화된 URL
            "scraping_url": scraping_url,             # 스크래핑 URL
            "announcement_date": announcement_date,   # 20251101
            "processing_status": status,              # "성공"
            "error_message": error_message,           # None
        }

        # 쿼리 실행
        result = session.execute(sql, params)
        session.commit()

        # 삽입된 레코드 ID 반환
        return result.lastrowid
```

#### UPSERT 쿼리 (force=True 일 때)

```python
# force=True인 경우 ON DUPLICATE KEY UPDATE 사용
sql = text("""
    INSERT INTO announcement_pre_processing (...)
    VALUES (...)
    ON DUPLICATE KEY UPDATE
        site_type = IF(
            VALUES(site_type) IN ('Eminwon', 'Homepage', 'Scraper') OR
            site_type NOT IN ('Eminwon', 'Homepage', 'Scraper'),
            VALUES(site_type),
            site_type
        ),
        content_md = IF(...),
        ... (모든 필드에 대해 동일한 우선순위 로직)
        updated_at = NOW()
""")
```

**UPSERT 우선순위:**
- ✅ 지자체 사이트 (Eminwon, Homepage, Scraper) > API 사이트 (api_scrap)
- ✅ 지자체 데이터가 있으면 API 데이터로 덮어쓰지 않음
- ✅ API 데이터가 있고 지자체 데이터가 없으면 업데이트

---

## 📊 DB 저장 데이터 상세

### announcement_pre_processing 테이블에 저장되는 컬럼

| 컬럼명 | 데이터 예시 | 출처 |
|--------|-----------|------|
| folder_name | `2025-11-01_BIZ_ANNOUNCEMENT_001` | 디렉토리 상대 경로 |
| site_type | `api_scrap` | `determine_site_type()` |
| site_code | `bizInfo` | 명령행 인자 |
| content_md | `# 공고 제목\n\n공고 내용...` | content.md 파일 |
| combined_content | `첨부파일1 내용\n\n첨부파일2 내용...` | 첨부파일 변환 결과 |
| attachment_filenames | `file1.pdf,file2.hwp` | attachments 디렉토리 |
| attachment_files_list | `[{"filename":"file1.pdf","content":"..."}]` | 첨부파일 상세 정보 |
| exclusion_keyword | `NULL` 또는 `keyword1,keyword2` | 제외 키워드 매칭 |
| exclusion_reason | `NULL` 또는 `제외 사유` | 제외 사유 |
| title | `2025년 지원사업 공고` | content.md에서 추출 |
| origin_url | `https://www.bizinfo.go.kr/...` | content.md에서 추출 |
| url_key | `bizinfo.go.kr_web_lay1_bbs.do_bid=123` | URL 정규화 결과 |
| scraping_url | `https://www.bizinfo.go.kr/scrape/...` | content.md에서 추출 |
| announcement_date | `20251101` | JSON 파일에서 추출 |
| processing_status | `성공` | 처리 결과 |
| error_message | `NULL` 또는 에러 메시지 | 예외 발생 시 |
| created_at | `2025-11-01 10:00:00` | NOW() |
| updated_at | `2025-11-01 10:00:00` | NOW() |

---

## 🔄 전체 흐름 요약

```
daily_api_batch.sh
    ↓
API_DIR="/home/zium/moabojo/incremental/api"
    ↓
for site in bizInfo, smes24, kStartUp
    ↓
python3 announcement_pre_processor.py -d $API_DIR --site-code $site
    ↓
main()
    ├─ determine_site_type() → "api_scrap"
    └─ AnnouncementPreProcessor(site_type="api_scrap")
        ↓
    process_site_directories()
        ├─ _find_target_directories() → content.md 있는 디렉토리 찾기
        └─ for each directory:
            ↓
        process_directory_with_custom_name()
            ├─ content.md 읽기
            ├─ JSON에서 날짜 추출
            ├─ URL 정규화 (url_key)
            ├─ 첨부파일 처리
            ├─ 제외 키워드 체크
            └─ _save_processing_result()
                ↓
            INSERT INTO announcement_pre_processing (
                folder_name, site_type, site_code, content_md, ...
            ) VALUES (...)
                ↓
            ✅ DB 저장 완료
```

---

## ✅ 점검 결과

### 1. DB 등록 여부
**✅ YES** - `daily_api_batch.sh` 실행 만으로 `announcement_pre_processing` 테이블에 데이터가 등록됩니다.

### 2. 등록되는 테이블
- **테이블명**: `announcement_pre_processing`
- **스키마**: folder_name (PK), site_type, site_code, content_md, combined_content, ...

### 3. site_type 값
- **값**: `"api_scrap"`
- **결정 근거**:
  1. site_code가 `["bizInfo", "smes24", "kStartUp"]` 중 하나
  2. directory에 `/incremental/api` 포함

### 4. 중복 처리
- **중복 방지**: `folder_name` + `site_code` 조합으로 이미 처리된 항목 자동 건너뜀
- **강제 재처리**: `--force` 옵션 사용 시 UPSERT 로직으로 업데이트

### 5. 처리 범위
- **대상**: `/home/zium/moabojo/incremental/api/{bizInfo,smes24,kStartUp}/` 내의 모든 `content.md` 있는 디렉토리
- **제외**: 이미 처리된 항목, 제외 키워드가 있는 항목

---

## 🧪 검증 방법

### 프로덕션 서버에서 테스트

```bash
# SSH 접속
ssh zium@server

# 배치 스크립트 실행
cd /home/zium/classfy_scraper
./daily_api_batch.sh

# DB 확인
mysql -u $DB_USER -p$DB_PASSWORD $DB_NAME -e "
SELECT
    COUNT(*) as total,
    site_type,
    site_code,
    processing_status
FROM announcement_pre_processing
WHERE site_type = 'api_scrap'
GROUP BY site_type, site_code, processing_status
ORDER BY site_code, processing_status;
"

# 최근 등록된 데이터 확인
mysql -u $DB_USER -p$DB_PASSWORD $DB_NAME -e "
SELECT
    id,
    folder_name,
    site_type,
    site_code,
    title,
    announcement_date,
    processing_status,
    created_at
FROM announcement_pre_processing
WHERE site_type = 'api_scrap'
ORDER BY created_at DESC
LIMIT 10;
"
```

### 예상 출력

```
[INFO] bizInfo 처리 시작
[1/50 : 2.0%] 2025-11-01_BIZ_ANNOUNCEMENT_001
  ✓ 처리 완료 (2.3초)
[2/50 : 4.0%] 2025-11-01_BIZ_ANNOUNCEMENT_002
  ✓ 이미 처리됨, 건너뜀 (0.1초)
...
[SUCCESS] bizInfo 처리 완료 (총 50개, 성공 30개, 건너뜀 20개)

[INFO] smes24 처리 시작
...
```

---

## 📋 최종 결론

### ✅ 확인 사항
1. **DB 등록**: YES - `announcement_pre_processing` 테이블에 자동 등록
2. **site_type**: `"api_scrap"` 고정값
3. **중복 방지**: folder_name + site_code 조합으로 자동 건너뜀
4. **데이터 추출**: content.md + JSON 파일에서 모든 필드 자동 추출
5. **첨부파일 처리**: attachments 디렉토리의 모든 파일 변환 및 저장

### 🎯 동작 보장
`daily_api_batch.sh` 실행 만으로:
- ✅ bizInfo, smes24, kStartUp 세 사이트의 모든 공고 자동 처리
- ✅ `announcement_pre_processing` 테이블에 자동 등록
- ✅ 중복 데이터 자동 방지
- ✅ 에러 발생 시에도 로그 및 error_message 저장

---

**작성일**: 2025-11-01
**분석 대상**: `daily_api_batch.sh` + `announcement_pre_processor.py`
**결론**: ✅ 정상 동작 - DB 자동 등록 확인
**우선순위**: 🟢 정보 제공
