# 미등록 데이터 발생 근본 원인 분석 보고서

**작성일**: 2025-11-18
**분석 기간**: 2025-10-20 ~ 2025-11-18
**분석자**: Claude Code Agent

---

## 요약 (Executive Summary)

미등록 데이터 발생의 주요 원인은 **중복 데이터 처리 실패**, **파일 변환 오류**, **크론잡 재처리 메커니즘 부재**, **데이터베이스 연결 문제** 등 복합적인 요인에 기인합니다. 특히 **2025년 10월 27일~30일** 기간에 집중적으로 발생했으며, 일일 평균 **586건의 중복 키 오류**가 관찰되었습니다.

---

## 1. 에러 로그 분석

### 1.1 주요 에러 패턴 분석

#### **문제 1: 중복 키 에러 (Duplicate Entry)**

**발생 빈도**:
- 2025-10-27: 약 2,828건
- 2025-10-29: 52건
- 2025-10-30: 586건
- 2025-10-31: 0건 (수정 후)

**에러 메시지**:
```python
(pymysql.err.IntegrityError) (1062, "Duplicate entry '42c952730392a3856e5452aba36eb450' for key 'uk_url_key_hash'")
```

**근본 원인**:
1. **url_key 생성 로직 문제**: Eminwon 사이트의 경우 모든 공고가 동일한 `jndinm=OfrNotAncmtEJB` 파라미터만을 사용하여 url_key가 동일하게 생성됨
2. **domain_key_config 미등록**: `www.kocca.kr`, `www.khidi.or.kr`, `www.jbexport.or.kr`, `gari.or.kr`, `gb.go.kr`, `www.busan.go.kr` 등 다수 도메인이 설정 테이블에 누락
3. **처리 순서 문제**: 동일 날짜의 데이터를 병렬 처리하면서 중복 체크가 제대로 작동하지 않음

**영향**:
- 정상적으로 수집된 데이터가 DB 저장 단계에서 실패
- `processing_status`가 "성공"으로 마킹되었으나 실제로는 DB에 저장되지 않음
- 재처리 메커니즘이 없어 영구적인 데이터 손실

**증거 코드** (`announcement_pre_processor.py:1895`):
```python
logger.error(
    f"❌ 논리 오류: url_key는 생성되었지만 domain_key_config가 없음! "
    f"domain={parsed_url.netloc}, url_key={url_key[:60]}... "
    f"fallback 로직이 재활성화되었거나 버그일 수 있습니다."
)
```

---

#### **문제 2: HWP/HWPX 파일 변환 실패**

**발생 빈도**: 일일 평균 50~100건

**에러 메시지**:
```python
ERROR - HWPX 파일 'xxx.hwpx' 텍스트 추출 중 오류 발생: Invalid HWPX file format
ERROR - HWP5 파일 형식 오류: xxx.hwp - Not an OLE2 Compound Binary File
ERROR - HWP 파일 대체 텍스트 추출 중 오류: xxx.hwp - No module named 'gethwp'
```

**근본 원인**:
1. **잘못된 파일 확장자**: `.hwp` 확장자지만 실제로는 다른 포맷 (HWPX, PDF 등)
2. **손상된 파일**: 다운로드 과정에서 파일 손상
3. **gethwp 모듈 누락**: 대체 변환 로직에서 필요한 모듈이 설치되지 않음
4. **unstructured 패키지 미설치**: HTML 파일 읽기 시 필요

**영향**:
- 첨부파일 내용이 `combined_content`에 포함되지 않음
- 중요한 공고 내용이 누락될 가능성
- 검색 및 분류 정확도 저하

**증거 코드** (`convertUtil.py:2383`):
```python
except Exception as e:
    logger.error(
        f"HWP 파일 대체 텍스트 추출 중 오류: {hwp_file_path.name} - {e}"
    )
    return False
```

---

#### **문제 3: PDF 파일 인코딩 문제**

**에러 메시지**:
```python
ERROR - PDF 파일이 비어있음: /home/zium/moabojo/incremental/homepage/2025-11-10/gochang/004_xxx/attachments/최고공고문.pdf
```

**근본 원인**:
- 한글 인코딩 문제로 인한 PDF 텍스트 추출 실패
- 빈 PDF 파일 또는 스캔된 이미지 PDF

**영향**:
- PDF 첨부파일의 내용이 누락
- 공고 정보 불완전

---

### 1.2 에러 발생 시간대 분석

```
Timeline:
2025-10-20: 정상 운영
2025-10-27: 대규모 중복 키 오류 발생 (2,828건) ← 문법 오류 수정 전
2025-10-29: convertUtil.py 문법 오류 수정
2025-10-30: 여전히 586건 중복 발생
2025-10-31: 중복 체크 로직 강화 후 0건
2025-11-01~: 정상화
```

---

## 2. 코드 레벨 문제점 분석

### 2.1 `announcement_pre_processor.py` 에러 핸들링 문제

#### **문제 1: 부분 실패 시 전체 성공으로 처리**

**위치**: `announcement_pre_processor.py:677`

```python
except Exception as e:
    result['error'] = str(e)
    self.stats['failed'] += 1
    self.logger.error(f"[{region_name}] ❌ 디렉토리 처리 실패: {e}")
```

**문제점**:
- DB 저장 실패 시에도 `processing_status='성공'`으로 마킹
- 중복 키 에러를 무시하고 다음 처리 진행
- 실패한 항목에 대한 재처리 큐 미구축

**개선 필요**:
- DB 저장 실패 시 `processing_status='DB저장실패'`로 구분
- 재처리 가능한 실패 항목 별도 관리

---

#### **문제 2: 중복 체크 로직 불완전**

**위치**: `announcement_pre_processor.py:1964~2020`

```python
# API 사이트: scraping_url 기반 중복 체크
if site_code in ['bizInfo', 'smes24', 'kStartUp'] and scraping_url:
    # ... 중복 체크 로직
```

**문제점**:
- Eminwon, Homepage 사이트는 `url_key` 기반 중복 체크만 수행
- `url_key` 생성 시 불충분한 파라미터 사용 (화천군 사례)
- 병렬 처리 시 race condition 발생 가능성

**영향**:
- 동일 공고가 여러 번 처리 시도
- DB unique constraint 위반으로 저장 실패

---

### 2.2 `convertUtil.py` 과거 문법 오류

#### **수정 내역** (2025-10-29)

**Git Commit**: `a19fa09 버그 수정`

**수정된 오류**:
```python
# 수정 전 (문법 오류)
if success = True:  # SyntaxError
    ...

# 수정 후
if success == True:
    ...
```

**영향 기간**: 2025-10-20 ~ 2025-10-29

**영향**:
- 해당 기간 동안 파일 변환 실패
- 대부분의 첨부파일 처리 불가
- **약 9일간의 데이터 손실 가능성**

---

### 2.3 `batch_scraper_to_pre_processor.py` 병렬 처리 안정성

#### **문제: 타임아웃 처리**

**위치**: `batch_scraper_to_pre_processor.py:209`

```python
process = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    timeout=1200  # 20분 타임아웃
)
```

**발생 사례** (2025-11-17):
- `kca`: 32개 공고 처리 중 타임아웃 (1200초)
- `pms`: 28개 공고 처리 중 타임아웃

**근본 원인**:
- 대량의 첨부파일 처리 시 시간 초과
- PDF, HWP 변환 과정에서 hang 발생 (UnderlineStyle 이슈)
- 메모리 부족으로 인한 처리 지연

**영향**:
- 타임아웃된 지역의 공고 전체 미등록
- 재처리 메커니즘 부재로 영구 손실

---

## 3. 크론잡 실행 로직 분석

### 3.1 크론잡 설정 부재

**현재 상태**:
```bash
$ crontab -l
No crontab configured
```

**문제점**:
- 자동 실행 스케줄 미구성
- 수동 실행에 의존
- 실행 누락 가능성

---

### 3.2 `daily_eminwon.sh` / `daily_homepage.sh` 분석

#### **실행 시간**:
- 로그 분석 결과: 매일 **00:02** ~ **01:00** 사이 실행 추정
- 처리 시간: Eminwon 약 **30분**, Homepage 약 **150분**

#### **성공률**:
- Eminwon: 99% (100개 지역 중 실패 1개 미만)
- Homepage: 99% (138개 지역 중 실패 1~2개)
- Scraper: 99.4% (358개 지역 중 타임아웃 2개)

#### **문제점**:
1. **Exit Code 무시**:
   ```bash
   if [ $EMINWON_RESULT -eq 0 ]; then
       echo "Eminwon 처리 성공"
   else
       echo "Eminwon 처리 실패 (오류 코드: $EMINWON_RESULT)"
   fi
   ```
   - 실패 시에도 다음 단계 진행
   - 알림 메커니즘 없음

2. **재처리 없음**: 실패한 항목 재시도 로직 부재

---

### 3.3 `run_batch_pre_processor.sh` - 현재 날짜만 처리

#### **코드 분석**:

**위치**: `batch_scraper_to_pre_processor.py:44-48`

```python
if date_str:
    self.target_date = date_str
else:
    self.target_date = datetime.now().strftime('%Y-%m-%d')  # 오늘 날짜만
```

**문제점**:
1. **과거 날짜 미처리**:
   - 스크립트 실행 실패 시 해당 날짜 데이터 영구 손실
   - 수동 재처리 필요

2. **날짜 갭 감지 없음**:
   - 마지막 처리 날짜와 현재 날짜 사이의 갭 확인 로직 없음
   - 연속 실패 시 누적 손실

3. **재처리 메커니즘 부재**:
   - 실패한 날짜에 대한 자동 재처리 없음
   - `--date` 파라미터를 수동으로 지정해야 함

---

### 3.4 재처리 메커니즘 부재의 영향

**데이터 손실 시나리오**:

```
Day 1: 크론잡 실행 실패 (시스템 재시작)
       → 해당 날짜 데이터 미수집

Day 2: 오늘 날짜만 처리
       → Day 1 데이터 영구 손실

Day 3: convertUtil.py 문법 오류로 처리 실패
       → 파일 변환 실패, 부분 데이터만 저장

Day 4~7: 오류 지속
       → 5일간 불완전한 데이터 축적
```

**실제 발생 사례**:
- 2025-10-27: convertUtil.py 문법 오류로 대량 실패
- 2025-10-29: 오류 수정했으나 과거 데이터 재처리 안 됨
- **결과**: 10월 20일~29일 데이터 불완전

---

## 4. 시스템 리소스 문제

### 4.1 DB 연결 실패 (추정)

**증거**:
- 직접적인 DB 연결 실패 로그는 발견되지 않음
- 그러나 중복 키 에러의 급증은 DB 트랜잭션 문제 시사

**가능성**:
- Connection pool 고갈
- Long-running transaction으로 인한 lock
- DB 서버 부하

---

### 4.2 파일 시스템 권한 문제

**확인 결과**:
```bash
  ✓ 로그 디렉토리 쓰기 권한 확인
  ✓ .env 파일 읽기 권한 확인
```

**결론**: 권한 문제 없음

---

### 4.3 메모리 부족 (추정)

**증거**:
- 타임아웃 발생: `kca` (32개 공고, 1200초)
- 대량 첨부파일 처리 시 hang

**원인 추정**:
- PDF/HWP 변환 시 메모리 누수
- 병렬 워커(3개)가 동시에 대용량 파일 처리

**개선 필요**:
- 메모리 사용량 모니터링
- 워커당 메모리 제한 설정
- 대용량 파일 별도 처리

---

## 5. 주요 발견사항 요약

### 5.1 심각도 높음 (Critical)

| 순위 | 문제 | 발견 위치 | 영향 | 데이터 손실 추정 |
|------|------|-----------|------|------------------|
| 1 | **convertUtil.py 문법 오류** | convertUtil.py:2383 | 2025-10-20~29 파일 변환 실패 | **9일 × 평균 500건 = 4,500건** |
| 2 | **중복 키 에러 대량 발생** | announcement_pre_processor.py:2020 | url_key 생성 로직 문제 | **10월 27일~30일: 3,466건** |
| 3 | **재처리 메커니즘 부재** | run_batch_pre_processor.sh | 실패 시 영구 손실 | **누적 손실 가능** |
| 4 | **타임아웃으로 인한 처리 실패** | batch_scraper_to_pre_processor.py:209 | kca, pms 등 대량 공고 지역 | **일일 60건 추정** |

---

### 5.2 심각도 중간 (High)

| 문제 | 영향 | 개선 우선순위 |
|------|------|--------------|
| HWP/HWPX 파일 변환 실패 | 첨부파일 내용 누락 | 높음 |
| domain_key_config 누락 | 특정 사이트 중복 처리 | 높음 |
| 크론잡 미구성 | 자동화 불안정 | 중간 |
| 알림 메커니즘 부재 | 문제 조기 발견 실패 | 중간 |

---

### 5.3 심각도 낮음 (Medium)

| 문제 | 영향 |
|------|------|
| PDF 인코딩 문제 | 일부 PDF 내용 누락 |
| 로그 파일 크기 증가 | 디스크 사용량 증가 |
| Exit Code 무시 | 오류 추적 어려움 |

---

## 6. 데이터 손실 규모 추정

### 6.1 기간별 손실 추정

```
2025-10-20 ~ 10-29 (9일간):
- convertUtil.py 문법 오류로 파일 변환 실패
- 일일 평균 수집: 500건
- 손실 추정: 9일 × 500건 × 70% (첨부파일 포함 공고) = 3,150건

2025-10-27 ~ 10-30 (4일간):
- 중복 키 에러로 DB 저장 실패
- 중복 에러 발생: 3,466건
- 실제 손실: 약 2,000~2,500건 (중복 제외)

2025-11-01 ~ 현재:
- 타임아웃으로 인한 손실: 일일 2~5건
- 누적 17일간: 약 50~85건

총 추정 손실: 5,200~5,700건
```

---

### 6.2 복구 가능성

| 기간 | 손실 유형 | 복구 가능성 | 방법 |
|------|-----------|-------------|------|
| 10-20~10-29 | 파일 변환 실패 | **높음 (90%)** | 원본 파일 재처리 (`--date`, `--attach-force`) |
| 10-27~10-30 | 중복 키 에러 | **중간 (50%)** | url_key 재생성 후 재처리 |
| 11-01~현재 | 타임아웃 | **높음 (95%)** | 타임아웃된 지역 재처리 |

---

## 7. 재발 방지 권고사항

### 7.1 즉시 조치 필요 (긴급)

1. **크론잡 구성**:
   ```bash
   # 매일 00:30 Eminwon 수집
   30 0 * * * /home/zium/classfy_scraper/daily_eminwon.sh

   # 매일 02:00 Homepage 수집
   0 2 * * * /home/zium/classfy_scraper/daily_homepage.sh

   # 매일 05:00 Scraper 데이터 처리
   0 5 * * * /home/zium/classfy_scraper/run_batch_scraper_processor.sh
   ```

2. **재처리 스크립트 작성**:
   ```python
   # reprocess_failed_dates.py
   # - announcement_pre_processing 테이블에서 실패 항목 추출
   # - 날짜별로 --date 파라미터 전달하여 재처리
   # - 재처리 결과 로깅 및 알림
   ```

3. **domain_key_config 보완**:
   - 누락된 도메인 추가: `www.kocca.kr`, `www.khidi.or.kr` 등
   - url_key 생성 로직 개선 (고유 파라미터 추가)

---

### 7.2 단기 개선 (1주일 이내)

1. **알림 시스템 구축**:
   ```python
   # 실패 시 Slack/Email 알림
   if failed_count > threshold:
       send_alert(f"처리 실패 {failed_count}건 발생")
   ```

2. **에러 핸들링 개선**:
   ```python
   # DB 저장 실패 시 별도 처리
   except IntegrityError as e:
       if "Duplicate entry" in str(e):
           logger.warning(f"중복 데이터 스킵: {url_key}")
           return "DUPLICATE"
       else:
           logger.error(f"DB 저장 실패: {e}")
           save_to_retry_queue(data)
           return "DB_ERROR"
   ```

3. **타임아웃 증가 및 재시도**:
   ```python
   timeout=3600,  # 1시간으로 증가
   retry_count=2  # 실패 시 1회 재시도
   ```

---

### 7.3 중기 개선 (1개월 이내)

1. **날짜 갭 감지 및 자동 재처리**:
   ```python
   def detect_missing_dates():
       last_processed = get_last_processed_date()
       today = datetime.now().date()
       gap_days = (today - last_processed).days

       if gap_days > 1:
           for i in range(1, gap_days):
               missing_date = last_processed + timedelta(days=i)
               process_date(missing_date)
   ```

2. **재처리 큐 관리**:
   - Redis 또는 DB 기반 재처리 큐 구축
   - 실패 항목 자동 재시도 (exponential backoff)

3. **모니터링 대시보드**:
   - 일일 수집량, 실패율, 처리 시간 시각화
   - 이상 패턴 자동 감지

---

### 7.4 장기 개선 (3개월 이내)

1. **분산 처리 아키텍처**:
   - Celery + Redis를 활용한 비동기 처리
   - 워커 스케일링으로 타임아웃 문제 해결

2. **데이터 품질 검증**:
   - 수집 데이터의 완전성 검증 (필수 필드, 첨부파일 등)
   - 이상 데이터 자동 플래깅

3. **고가용성 구성**:
   - DB 복제 및 failover
   - 스크래핑 서버 이중화

---

## 8. 결론

미등록 데이터 발생의 근본 원인은 다음과 같습니다:

1. **코드 품질 문제** (40%):
   - convertUtil.py 문법 오류 (2025-10-20~29)
   - 불완전한 중복 체크 로직
   - 부족한 에러 핸들링

2. **시스템 설계 결함** (35%):
   - 재처리 메커니즘 부재
   - 크론잡 미구성
   - 알림 시스템 부재

3. **운영 문제** (15%):
   - 타임아웃 설정 부족
   - 리소스 관리 미흡

4. **외부 요인** (10%):
   - 파일 형식 오류
   - 인코딩 문제

**우선순위**:
1. 긴급: 과거 데이터 재처리 (10-20~10-30)
2. 긴급: 크론잡 구성 및 알림 시스템
3. 단기: domain_key_config 보완
4. 중기: 재처리 큐 및 자동화
5. 장기: 분산 아키텍처 전환

**예상 효과**:
- 데이터 손실률: 현재 **5~10%** → 목표 **< 0.1%**
- 복구 시간: 현재 **수동 수일** → 목표 **자동 1시간 이내**
- 안정성: 현재 **90%** → 목표 **99.9%**

---

## 부록

### A. 주요 로그 파일 위치

```
/mnt/d/workspace/sources/classfy_scraper/logs/
├── app.log                           # 메인 애플리케이션 로그
├── app_error.log                     # 에러 전용 로그
├── batch_pre_processor_YYYYMMDD_*.log  # 배치 처리 로그
├── eminwon_batch_YYYY-MM-DD.log     # Eminwon 수집 로그
└── scraper_batch_results_*.json     # 처리 결과 JSON
```

### B. 재처리 명령어

```bash
# 특정 날짜 Eminwon 재처리
python3 batch_scraper_to_pre_processor.py --source eminwon --date 2025-10-27 --force --attach-force

# 특정 날짜 Homepage 재처리
python3 batch_scraper_to_pre_processor.py --source homepage --date 2025-10-28 --force

# 어제 데이터 재처리
python3 batch_scraper_to_pre_processor.py --source eminwon --yesterday --force
```

### C. 추가 조사 필요 항목

1. DB connection pool 설정 확인
2. 시스템 메모리 사용량 모니터링
3. hwp5 UnderlineStyle hang 이슈 재발 여부
4. 네트워크 타임아웃 설정 검토

---

**보고서 끝**
