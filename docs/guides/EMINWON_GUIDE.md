# Eminwon 증분 수집 시스템 사용 가이드

## 📋 목차
1. [개요](#개요)
2. [시스템 구성](#시스템-구성)
3. [초기 설정](#초기-설정)
4. [사용법](#사용법)
5. [운영 가이드](#운영-가이드)
6. [트러블슈팅](#트러블슈팅)

## 🎯 개요

Eminwon 증분 수집 시스템은 100개 지역의 eminwon 사이트에서 공고를 효율적으로 수집하는 시스템입니다.
- **URL 기반 중복 제거**: 이미 수집한 공고는 다시 다운로드하지 않음
- **증분 수집**: 매일 새로운 공고만 수집
- **병렬 처리**: 여러 지역 동시 처리로 속도 향상

## 🔧 시스템 구성

### 주요 스크립트

| 스크립트 | 용도 | 실행 빈도 |
|---------|------|----------|
| `index_existing_eminwon.py` | 기존 데이터 인덱싱 | 초기 1회, 필요시 |
| `eminwon_incremental_crawler.py` | 새 공고 수집 | 매일 |
| `eminwon_daily_batch.py` | 전체 프로세스 자동화 | 매일 (cron) |
| `check_indexing_status.py` | 인덱싱 상태 확인 | 필요시 |
| `test_eminwon_system.py` | 시스템 테스트 | 설정 변경시 |

### 데이터베이스 구조

```sql
-- eminwon_url_registry 테이블
CREATE TABLE eminwon_url_registry (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    region VARCHAR(50),              -- 지역명 (예: 청주, 광주남)
    folder_name VARCHAR(500),         -- 폴더명
    announcement_url VARCHAR(1000),   -- 공고 URL (UNIQUE)
    announcement_id VARCHAR(100),     -- 공고 ID (not_ancmt_mgt_no)
    title VARCHAR(500),               -- 공고 제목
    post_date DATE,                   -- 게시일
    content_hash VARCHAR(64),         -- 컨텐츠 해시값
    first_seen_date TIMESTAMP,        -- 최초 수집일
    last_checked_date TIMESTAMP       -- 마지막 확인일
);
```

### 디렉토리 구조

```
classfy_scraper/
├── eminwon_data/              # 기존 수집 데이터
│   ├── 청주/
│   ├── 광주남/
│   └── ...
├── eminwon_data_new/          # 새로 수집된 데이터
│   └── 2025-09-21/
│       ├── 청주/
│       └── ...
├── node/scraper/
│   └── eminwon.json          # 지역별 도메인 설정
├── logs/batch/               # 배치 실행 로그
└── reports/                  # 일일 리포트
```

## 🚀 초기 설정

### 1. 환경 설정

`.env` 파일에 데이터베이스 정보 설정:
```bash
DB_HOST=192.168.0.95
DB_USER=root
DB_PASSWORD=yourpassword
DB_NAME=subvention
DB_PORT=3309
```

### 2. 필요 패키지 설치

```bash
pip install mysql-connector-python python-dotenv tqdm requests beautifulsoup4
```

### 3. 초기 인덱싱 (최초 1회)

기존 `eminwon_data` 폴더의 21,159개 파일을 데이터베이스에 인덱싱:

```bash
# 전체 인덱싱
python index_existing_eminwon.py

# 특정 지역만 인덱싱
python index_existing_eminwon.py -r 청주 광주남

# 진행 상황 확인
python check_indexing_status.py
```

## 📖 사용법

### 1. index_existing_eminwon.py - 초기 인덱싱

#### 기본 사용법
```bash
# 전체 지역 인덱싱
python index_existing_eminwon.py
```

#### 옵션
| 옵션 | 설명 | 예시 |
|-----|------|-----|
| `-r, --regions` | 특정 지역만 인덱싱 | `-r 청주 광주남` |
| `--force` | 기존 데이터 삭제 후 재인덱싱 | `--force` |
| `--list` | 사용 가능한 지역 목록 표시 | `--list` |

#### 사용 예시
```bash
# 사용 가능한 지역 확인
python index_existing_eminwon.py --list

# 특정 지역만 인덱싱
python index_existing_eminwon.py -r 청주 광주남 대전서

# 특정 지역 강제 재인덱싱 (기존 데이터 삭제)
python index_existing_eminwon.py -r 청주 --force

# 전체 강제 재인덱싱 (주의: 모든 데이터 삭제)
python index_existing_eminwon.py --force
```

### 2. eminwon_incremental_crawler.py - 증분 수집

#### 기본 사용법
```bash
# 전체 지역 새 공고 수집 (최근 3페이지)
python eminwon_incremental_crawler.py
```

#### 옵션
| 옵션 | 설명 | 예시 |
|-----|------|-----|
| `--test` | 테스트 모드 (제한된 수집) | `--test` |
| `--regions` | 특정 지역만 수집 | `--regions 청주 광주남` |

#### 사용 예시
```bash
# 테스트 실행 (각 지역 2개씩만)
python eminwon_incremental_crawler.py --test

# 특정 지역만 수집
python eminwon_incremental_crawler.py --regions 청주 광주남

# 테스트 모드로 특정 지역
python eminwon_incremental_crawler.py --test --regions 청주
```

### 3. eminwon_daily_batch.py - 일일 배치

#### 기본 사용법
```bash
# 전체 배치 프로세스 실행
python eminwon_daily_batch.py
```

#### 옵션
| 옵션 | 설명 | 예시 |
|-----|------|-----|
| `--config` | 설정 파일 경로 | `--config config/batch_config.json` |
| `--index` | 초기 인덱싱 강제 실행 | `--index` |
| `--no-process` | 공고 처리 건너뛰기 | `--no-process` |
| `--no-cleanup` | 오래된 데이터 정리 건너뛰기 | `--no-cleanup` |

#### 배치 설정 파일 (config/batch_config.json)
```json
{
  "run_indexing": false,          // 초기 인덱싱 실행 여부
  "max_pages_per_region": 3,      // 지역별 최대 페이지 수
  "parallel_workers": 5,           // 병렬 워커 수
  "enable_email_notification": false,  // 이메일 알림
  "email_recipients": [],          // 수신자 목록
  "process_announcements": true,   // 공고 처리 여부
  "cleanup_old_data": true,        // 오래된 데이터 정리
  "cleanup_days": 30              // 보관 기간(일)
}
```

### 4. check_indexing_status.py - 상태 확인

```bash
# 인덱싱 상태 확인
python check_indexing_status.py
```

출력 예시:
```
Total indexed URLs: 21,159

Indexed regions (99):
----------------------------------------
  청주                   :  1,720 announcements
  봉화                   :    778 announcements
  화성                   :    634 announcements
  ...
```

## 🔄 운영 가이드

### 일일 운영 프로세스

#### 1. 수동 실행
```bash
# 증분 수집 실행
python eminwon_incremental_crawler.py

# 또는 배치로 전체 자동화
python eminwon_daily_batch.py
```

#### 2. 자동화 (Cron 설정)
```bash
# crontab 편집
crontab -e

# 매일 새벽 2시 실행
0 2 * * * cd /Users/jin/classfy_scraper && /usr/bin/python3 eminwon_daily_batch.py >> logs/cron.log 2>&1

# 매일 오전 9시 추가 실행
0 9 * * * cd /Users/jin/classfy_scraper && /usr/bin/python3 eminwon_incremental_crawler.py >> logs/cron.log 2>&1
```

### 모니터링

#### 실시간 모니터링
```bash
# 로그 실시간 확인
tail -f logs/batch/batch_$(date +%Y-%m-%d).log

# 수집 통계 확인
cat eminwon_data_new/$(date +%Y-%m-%d)/collection_stats.json
```

#### 일일 리포트 확인
```bash
# 오늘 리포트
cat reports/batch_report_$(date +%Y-%m-%d).txt

# 최근 7일 통계
for i in {0..6}; do
  date=$(date -d "$i days ago" +%Y-%m-%d)
  echo "=== $date ==="
  grep "New announcements:" reports/batch_report_$date.txt 2>/dev/null
done
```

### 데이터 관리

#### 수집 데이터 백업
```bash
# 일일 백업
tar -czf backup/eminwon_$(date +%Y%m%d).tar.gz eminwon_data_new/

# S3 업로드 (AWS CLI 필요)
aws s3 cp backup/eminwon_$(date +%Y%m%d).tar.gz s3://your-bucket/eminwon/
```

#### 오래된 데이터 정리
```bash
# 30일 이상 된 데이터 삭제
find eminwon_data_new/ -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \;

# 데이터베이스 최적화
mysql -h192.168.0.95 -P3309 -uroot -p subvention -e "OPTIMIZE TABLE eminwon_url_registry;"
```

## 🔧 트러블슈팅

### 문제 1: 인덱싱 실패

**증상**: `index_existing_eminwon.py` 실행시 오류

**해결 방법**:
```bash
# 데이터베이스 연결 확인
mysql -h192.168.0.95 -P3309 -uroot -p -e "SELECT 1"

# 테이블 존재 확인
mysql -h192.168.0.95 -P3309 -uroot -p subvention -e "SHOW TABLES LIKE 'eminwon_url_registry'"

# 테이블 재생성
mysql -h192.168.0.95 -P3309 -uroot -p subvention -e "DROP TABLE IF EXISTS eminwon_url_registry"
python index_existing_eminwon.py
```

### 문제 2: 중복 수집

**증상**: 같은 공고가 계속 수집됨

**해결 방법**:
```bash
# 특정 지역 재인덱싱
python index_existing_eminwon.py -r 청주 --force

# URL 중복 확인
mysql -h192.168.0.95 -P3309 -uroot -p subvention -e "
SELECT announcement_url, COUNT(*) as cnt 
FROM eminwon_url_registry 
GROUP BY announcement_url 
HAVING cnt > 1"
```

### 문제 3: 크롤링 속도 저하

**증상**: 수집이 너무 느림

**해결 방법**:
```python
# eminwon_incremental_crawler.py 수정
# 워커 수 증가 (기본값: 5)
with ThreadPoolExecutor(max_workers=10) as executor:
```

### 문제 4: 메모리 부족

**증상**: 대용량 지역 처리시 메모리 에러

**해결 방법**:
```bash
# 지역별 순차 처리
for region in 청주 광주남 대전서; do
    python eminwon_incremental_crawler.py --regions $region
    sleep 60  # 1분 대기
done
```

## 📊 성능 지표

### 처리 속도
- **초기 인덱싱**: 21,159개 파일 / 약 30-40분
- **일일 증분 수집**: 100개 지역 / 약 5-10분
- **병렬 처리**: 5개 워커로 2.5배 속도 향상

### 저장 용량
- **기존 데이터**: 약 2-3GB (eminwon_data/)
- **일일 신규**: 약 10-50MB (평균 50-100개 공고)
- **데이터베이스**: 약 100-200MB

### 네트워크 사용량
- **일일 수집**: 약 100-500MB
- **피크 시간**: 새벽 2-3시 (배치 실행)

## 🚨 주의사항

1. **강제 재인덱싱 (`--force`)**
   - 기존 데이터를 삭제하므로 신중히 사용
   - 전체 재인덱싱은 가급적 피할 것

2. **데이터베이스 백업**
   - 주기적으로 `eminwon_url_registry` 테이블 백업
   - 중요 작업 전 스냅샷 생성

3. **크롤링 예의**
   - 과도한 요청 자제 (워커 수 제한)
   - 서버 부하 시간대 피하기

4. **로그 관리**
   - 로그 파일 주기적 정리
   - 디스크 용량 모니터링

## 📞 문의

시스템 관련 문의사항:
- 시스템 구조 및 설정
- 오류 해결 방법
- 성능 최적화

---

**마지막 업데이트**: 2025-09-21  
**버전**: 1.0  
**상태**: 운영 중 ✅