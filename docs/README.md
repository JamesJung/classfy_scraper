# 공고 수집 및 처리 시스템 문서

이 디렉토리는 공고 수집 및 처리 시스템의 핵심 기술 문서를 포함합니다.

## 📚 문서 구조

### 🏗️ 시스템 아키텍처

| 문서 | 설명 | 업데이트 |
|------|------|----------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 시스템 전체 아키텍처, 병렬 처리 구현, 성능 최적화 | 2025-09-08 |
| [ANNOUNCEMENT_PROCESSOR_GUIDE.md](./ANNOUNCEMENT_PROCESSOR_GUIDE.md) | 첨부파일 처리 프로그램 전체 가이드 | - |
| [API_BATCH_FLOW.md](./API_BATCH_FLOW.md) | daily_api_batch.sh 실행 흐름 및 DB 등록 프로세스 | 2025-11-01 |
| [DATABASE_MANAGEMENT.md](./DATABASE_MANAGEMENT.md) | MySQL 연결 관리 및 최적화 | - |
| [AGENTS_REFERENCE.md](./AGENTS_REFERENCE.md) | Agent 시스템 레퍼런스 | - |

### 🔄 데이터 흐름 및 처리

| 문서 | 설명 | 업데이트 |
|------|------|----------|
| **[DUPLICATE_CHECK_DESIGN.md](./DUPLICATE_CHECK_DESIGN.md)** | **중복 체크 로직, 테이블 설계, 우선순위 규칙** ⭐ | **2025-11-03** |
| [URL_KEY_SYSTEM.md](./URL_KEY_SYSTEM.md) | URL 키 정규화 및 해시 시스템 전체 분석 | - |
| [URL_KEY_HASH_SYSTEM.md](./URL_KEY_HASH_SYSTEM.md) | url_key_hash 검증 및 데이터 무결성 | - |
| [API_REGISTRY_MAPPING.md](./API_REGISTRY_MAPPING.md) | API URL 레지스트리 매핑 분석 | - |
| [UPSERT_LOGIC.md](./UPSERT_LOGIC.md) | UPSERT 우선순위 로직 상세 | - |
| [DEDUP_PRIORITY.md](./DEDUP_PRIORITY.md) | 전역 중복 제거 우선순위 시스템 | - |
| [URL_RELATIONSHIPS.md](./URL_RELATIONSHIPS.md) | URL 간 관계 분석 (origin_url vs scraping_url) | - |

### 🔍 핵심 로직

| 문서 | 설명 | 업데이트 |
|------|------|----------|
| [DUPLICATE_CHECK_LOGIC.md](./DUPLICATE_CHECK_LOGIC.md) | 중복 체크 상세 로직 분석 | - |
| [CODE_REVIEW.md](./CODE_REVIEW.md) | 코드 리뷰 결과 및 개선 사항 | - |

### 📖 사용자 가이드

| 문서 | 설명 | 업데이트 |
|------|------|----------|
| [guides/EMINWON_GUIDE.md](./guides/EMINWON_GUIDE.md) | Eminwon 증분 수집 가이드 | - |
| [guides/CRONTAB_SETUP.md](./guides/CRONTAB_SETUP.md) | 크론탭 설정 가이드 | - |
| [guides/SCRAPER_BATCH_GUIDE.md](./guides/SCRAPER_BATCH_GUIDE.md) | Scraper 배치 처리 가이드 | - |
| [guides/ATTACHMENT_EXTRACTOR.md](./guides/ATTACHMENT_EXTRACTOR.md) | 첨부파일 추출 가이드 | - |
| [guides/EMINWON_BATCH.md](./guides/EMINWON_BATCH.md) | Eminwon 배치 처리 가이드 | - |
| [guides/ATTACHMENT_TYPES.md](./guides/ATTACHMENT_TYPES.md) | 첨부파일 유형별 처리 방법 | - |
| [guides/SCRAPER_TITLE_LOGIC.md](./guides/SCRAPER_TITLE_LOGIC.md) | Scraper 제목 추출 로직 | - |
| [guides/CRONTAB_LEGACY.md](./guides/CRONTAB_LEGACY.md) | 레거시 크론탭 설정 | - |

---

## 🎯 빠른 시작 가이드

### 시스템 이해하기

1. **전체 아키텍처**: [ARCHITECTURE.md](./ARCHITECTURE.md) - 시스템 전체 구조 파악
2. **데이터 처리 흐름**: [API_BATCH_FLOW.md](./API_BATCH_FLOW.md) - 배치 처리 흐름 이해
3. **중복 체크 로직**: [DUPLICATE_CHECK_DESIGN.md](./DUPLICATE_CHECK_DESIGN.md) - 핵심 중복 체크 로직

### 개발자 가이드

#### 중복 체크 시스템 개발

```
1. DUPLICATE_CHECK_DESIGN.md - 전체 설계 이해
   ↓
2. URL_KEY_SYSTEM.md - URL 정규화 로직
   ↓
3. UPSERT_LOGIC.md - 우선순위 기반 UPSERT
```

#### 배치 스크립트 개발

```
1. guides/SCRAPER_BATCH_GUIDE.md - 배치 스크립트 작성법
   ↓
2. guides/CRONTAB_SETUP.md - 스케줄링 설정
```

#### 첨부파일 처리 개발

```
1. ANNOUNCEMENT_PROCESSOR_GUIDE.md - 전체 프로세스
   ↓
2. guides/ATTACHMENT_EXTRACTOR.md - 추출 로직
   ↓
3. guides/ATTACHMENT_TYPES.md - 유형별 처리
```

---

## 🔑 핵심 개념

### 1. 중복 체크 시스템

**목적**: 동일한 공고가 여러 소스(API, 지자체 홈페이지, 민원 등)에서 수집될 때 중복 방지

**핵심 메커니즘**:
- `url_key`: origin_url 정규화 (domain_key_config 기반)
- `url_key_hash`: url_key의 MD5 해시 (GENERATED COLUMN)
- `duplicate_type`: 중복 유형 분류 (unconfigured_domain, new_inserted, replaced, kept_existing, same_type_duplicate 등)

**우선순위**:
```
지자체 데이터 (Eminwon/Homepage/Scraper) = 3
API 데이터 (api_scrap) = 1
Unknown = 0
```

**상세**: [DUPLICATE_CHECK_DESIGN.md](./DUPLICATE_CHECK_DESIGN.md)

### 2. URL 키 시스템

**목적**: 다양한 URL 형식을 표준화하여 동일 공고 식별

**처리 과정**:
1. origin_url 추출 (content.md에서)
2. domain_key_config 조회
3. key_params 기반 URL 정규화
4. url_key 생성
5. url_key_hash 자동 생성 (GENERATED COLUMN)

**Fallback 정책**: 비활성화 (domain_key_config 없으면 url_key = NULL)

**상세**: [URL_KEY_SYSTEM.md](./URL_KEY_SYSTEM.md)

### 3. UPSERT 로직

**동작 방식**:
```sql
INSERT INTO announcement_pre_processing (...)
VALUES (...)
ON DUPLICATE KEY UPDATE
    site_type = CASE
        WHEN VALUES(우선순위) >= 기존_우선순위 THEN VALUES(site_type)
        ELSE site_type
    END,
    ...
```

**affected_rows 해석**:
- `1`: INSERT됨 (신규)
- `2`: UPDATE됨 (중복)
- 기타: 오류

**상세**: [UPSERT_LOGIC.md](./UPSERT_LOGIC.md)

---

## 📊 주요 데이터베이스 테이블

### announcement_pre_processing
공고 전처리 메인 테이블
- `id`: 기본키
- `url_key`: 정규화된 URL 키
- `url_key_hash`: MD5 해시 (GENERATED COLUMN, UNIQUE)
- `site_type`: 소스 타입 (Eminwon, Homepage, Scraper, api_scrap)
- `site_code`: 사이트 코드

### announcement_duplicate_log
중복 처리 로그 테이블
- `preprocessing_id`: announcement_pre_processing.id
- `duplicate_type`: 중복 유형
- `url_key_hash`: URL 키 해시
- `new_priority` / `existing_priority`: 우선순위 비교
- `duplicate_detail`: 상세 정보 (JSON)

### domain_key_config
도메인별 URL 정규화 설정
- `domain`: 도메인명
- `path_pattern`: 경로 패턴
- `key_params`: 키 파라미터 목록 (JSON)

---

## 🛠️ 자주 사용하는 쿼리

### 중복 체크 로그 조회
```sql
-- URL별 처리 이력
SELECT *
FROM announcement_duplicate_log
WHERE url_key_hash = MD5('정규화된_URL_키')
ORDER BY created_at ASC;

-- 일별 중복 발생 통계
SELECT
    DATE(created_at) as date,
    duplicate_type,
    COUNT(*) as count
FROM announcement_duplicate_log
WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
GROUP BY date, duplicate_type;
```

더 많은 쿼리 예시: [DUPLICATE_CHECK_DESIGN.md](./DUPLICATE_CHECK_DESIGN.md#활용-방안)

---

## 🔄 문서 업데이트 이력

### 2025-11-03
- **docs/ 디렉토리 구조 생성**
- 핵심 문서 20개를 docs/로 이동 및 정리
- DUPLICATE_CHECK_DESIGN.md 실제 구현 내용 반영 (v1.1)
- docs/README.md (이 문서) 생성

### 2025-11-01
- DUPLICATE_CHECK_DESIGN.md 초기 작성 (v1.0)
- API_BATCH_FLOW.md 작성

---

## 📝 문서 작성 가이드

### 새 문서 추가 시

1. **카테고리 결정**: 아키텍처 / 데이터 흐름 / 핵심 로직 / 가이드
2. **파일명 규칙**: `대문자_언더스코어.md` (예: `NEW_FEATURE_GUIDE.md`)
3. **위치**:
   - 시스템 문서: `docs/`
   - 사용자 가이드: `docs/guides/`
4. **이 README 업데이트**: 해당 카테고리 표에 추가

### 문서 업데이트 시

- 문서 하단에 **버전** 및 **변경 이력** 추가
- 이 README의 "업데이트" 컬럼에 날짜 기재

---

## 🔗 관련 링크

- 프로젝트 루트: `../`
- 소스 코드: `../src/`
- 테스트: `../tests/`
- 스크립트: `../node/`, `../scripts/`

---

**마지막 업데이트**: 2025-11-03
**관리자**: Claude Code Development Team
