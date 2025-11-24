# 스크래퍼 실패 공고 추적 및 재시도 시스템

## 개요

개별 공고 스크래핑 실패 시 자동으로 DB에 기록하고, 나중에 재시도할 수 있는 시스템입니다.

## 시스템 구성

### 1. DB 테이블: `scraper_failed_announcements`

**용도**: 스크래핑 실패한 개별 공고 정보 저장

**주요 컬럼**:
- `batch_date`: 스크래핑 실행 날짜
- `site_code`: 사이트 코드 (예: andong, daegu)
- `announcement_title`: 공고 제목
- `detail_url`: 상세 페이지 URL
- `error_type`: 에러 타입
- `error_message`: 에러 메시지
- `retry_count`: 재시도 횟수 (0~3)
- `status`: pending, success, permanent_failure

**생성**:
```bash
mysql -h 192.168.0.95 -P 3309 -u root -p subvention < create_failed_announcements_table.sql
```

### 2. 공통 모듈: `node/scraper/failure_logger.js`

**용도**: 모든 스크래퍼에서 실패 시 DB에 기록

**주요 메서드**:
```javascript
// 실패 공고 기록
await FailureLogger.logFailedAnnouncement({
    site_code: 'andong',
    title: '공고 제목',
    url: 'http://...',
    detail_url: 'http://...',
    error_type: 'timeout',
    error_message: '타임아웃 발생'
});

// 오늘 실패 개수 조회
const count = await FailureLogger.getFailureCount('andong');
```

### 3. 스크래퍼 패치: 156개 파일 자동 수정

**적용 내용**:
1. 모든 `*_scraper.js` 파일에 `failure_logger.js` import 추가
2. `catch` 블록에 `FailureLogger.logFailedAnnouncement()` 호출 추가

**실행**:
```bash
# 미리보기 (dry-run)
node patch_scrapers.js --all --dry-run

# 실제 적용
node patch_scrapers.js --all

# 특정 파일만
node patch_scrapers.js --file andong
```

**백업 위치**: `/Users/jin/classfy_scraper/backup_scrapers/`

### 4. 재시도 스크립트: `retry_failed_announcements.py`

**용도**: DB에 기록된 실패 공고를 재시도

**동작**:
1. `status='pending'` 인 실패 공고 조회
2. `unified_detail_scraper.js`로 각 공고 재시도
3. 성공 시 `status='success'` 업데이트
4. 실패 시 `retry_count++`
5. 3회 초과 시 `status='permanent_failure'`

**사용법**:
```bash
# 오늘 실패한 공고 모두 재시도
python3 retry_failed_announcements.py

# 특정 사이트만
python3 retry_failed_announcements.py --site andong

# 특정 날짜
python3 retry_failed_announcements.py --date 2025-01-19

# 최대 10개만
python3 retry_failed_announcements.py --limit 10

# 상세 로그
python3 retry_failed_announcements.py --verbose
```

## 워크플로우

### 일반 스크래핑 실행

```
1. homepage_daily_date_orchestrator.py 실행
   └─> Node.js 스크래퍼 실행 (andong_scraper.js 등)
       ├─> 공고 1: 성공 → 폴더 저장
       ├─> 공고 2: 성공 → 폴더 저장
       ├─> 공고 3: 실패 → FailureLogger.logFailedAnnouncement()
       │                 └─> DB에 기록 (status='pending')
       └─> 공고 4: 성공 → 폴더 저장

2. announcement_pre_processor.py 실행
   └─> 저장된 폴더들을 DB에 적재
```

### 재시도 실행

```
3. retry_failed_announcements.py 실행
   └─> DB에서 실패 공고 조회 (status='pending')
       ├─> 공고 3 (1차 재시도)
       │   ├─> unified_detail_scraper.js 실행
       │   └─> 성공 → status='success' ✓
       │
       ├─> 공고 5 (1차 재시도)
       │   ├─> unified_detail_scraper.js 실행
       │   └─> 실패 → retry_count=1 (다음에 다시 시도)
       │
       └─> 공고 6 (3차 재시도)
           ├─> unified_detail_scraper.js 실행
           └─> 실패 → status='permanent_failure' (영구 실패)
```

## 크론 설정 (선택)

매일 메인 스크래핑 후 3시간 뒤 재시도:

```bash
# 메인 스크래핑: 매일 자정
0 0 * * * /Users/jin/classfy_scraper/daily_homepage.sh

# 실패 재시도: 매일 오전 3시
0 3 * * * cd /Users/jin/classfy_scraper && python3 retry_failed_announcements.py >> logs/retry_$(date +\%Y\%m\%d).log 2>&1
```

## DB 조회 예시

### 오늘 실패한 공고 확인

```sql
SELECT site_code, announcement_title, error_type, retry_count, status
FROM scraper_failed_announcements
WHERE batch_date = CURDATE()
ORDER BY created_at DESC;
```

### 사이트별 실패 통계

```sql
SELECT site_code,
       COUNT(*) as total,
       SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
       SUM(CASE WHEN status = 'permanent_failure' THEN 1 ELSE 0 END) as permanent_failure
FROM scraper_failed_announcements
WHERE batch_date = CURDATE()
GROUP BY site_code
ORDER BY total DESC;
```

### 영구 실패 공고 확인

```sql
SELECT site_code, announcement_title, detail_url, error_message
FROM scraper_failed_announcements
WHERE status = 'permanent_failure'
ORDER BY created_at DESC
LIMIT 20;
```

### 재시도 필요한 공고 (pending)

```sql
SELECT site_code, announcement_title, retry_count, last_retry_at
FROM scraper_failed_announcements
WHERE status = 'pending'
  AND retry_count < 3
ORDER BY retry_count ASC, created_at ASC;
```

## 파일 구조

```
/Users/jin/classfy_scraper/
├── create_failed_announcements_table.sql   # DB 테이블 생성 SQL
├── patch_scrapers.js                       # 스크래퍼 자동 패치 도구
├── retry_failed_announcements.py           # 재시도 스크립트
├── SCRAPER_FAILURE_RETRY_README.md         # 이 파일
│
├── node/scraper/
│   ├── failure_logger.js                   # 공통 로깅 모듈
│   ├── unified_detail_scraper.js           # 개별 공고 스크래퍼
│   ├── andong_scraper.js                   # ✓ 패치 완료
│   ├── daegu_scraper.js                    # ✓ 패치 완료
│   └── ... (156개 모두 패치 완료)
│
├── backup_scrapers/                        # 패치 전 백업
│   ├── andong_scraper.js
│   └── ...
│
└── retry_failed_output/                    # 재시도 결과 저장
    └── 2025-01-19/
        ├── andong/
        └── daegu/
```

## 문제 해결

### 재시도 스크립트 실행 시 에러

```bash
# Python 패키지 설치
pip3 install pymysql python-dotenv

# .env 파일 확인
cat .env | grep DB_
```

### 재시도가 성공했는데 DB가 업데이트 안 됨

- `retry_failed_announcements.py`의 `update_retry_status()` 함수 확인
- DB 연결 정보 확인

### 특정 사이트만 계속 실패

```bash
# 해당 사이트만 재시도
python3 retry_failed_announcements.py --site andong --verbose

# 로그 확인
tail -f logs/retry_*.log
```

### 패치된 스크래퍼 원복

```bash
# 백업에서 복원
cp backup_scrapers/andong_scraper.js node/scraper/andong_scraper.js
```

## Announcement Viewer 연동 (향후 계획)

실패 공고 조회 화면 추가:

- 경로: `/failed-announcements`
- 기능:
  - 사이트별/날짜별 필터링
  - 재시도 상태 확인
  - 수동 재시도 버튼
  - 영구 실패 공고 목록

## 문의

문제 발생 시:
1. 로그 파일 확인: `logs/retry_*.log`
2. DB 테이블 확인: `SELECT * FROM scraper_failed_announcements`
3. 담당자에게 문의
