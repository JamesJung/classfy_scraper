# 미등록 데이터 복구 가이드

incremental 디렉토리에 있는 미처리 데이터를 DB에 등록하는 완벽 가이드

---

## 📋 목차

1. [문제 상황](#문제-상황)
2. [솔루션 개요](#솔루션-개요)
3. [사용 방법](#사용-방법)
4. [고급 사용법](#고급-사용법)
5. [cronjob 통합](#cronjob-통합)
6. [트러블슈팅](#트러블슈팅)

---

## 🚨 문제 상황

### 현재 시스템의 한계

```
Daily Cronjob (run_batch_pre_processor.sh)
  └─> batch_scraper_to_pre_processor.py
      └─> 항상 datetime.now() 날짜만 처리
          └─> 과거 날짜 폴더는 영원히 처리 안됨!
```

### 영향을 받는 경우

1. ❌ **시스템 오류로 처리 실패**
   - 2025-11-11: convertUtil.py 구문 오류로 575개 사이트 6,827개 공고 유실

2. ❌ **수동 스크립트 실행**
   - 특정 날짜에 수동으로 스크래퍼를 실행했으나 전처리를 잊어버림

3. ❌ **네트워크/서버 장애**
   - 전처리 중 서버가 다운되어 일부만 처리됨

4. ❌ **디스크 용량 부족**
   - 처리 중 디스크가 가득 차서 중단됨

---

## 💡 솔루션 개요

### 2단계 프로세스

```
1단계: 탐지 (find_unprocessed_dates.py)
  ├─ incremental/btp/*/
  ├─ incremental/eminwon/*/
  └─ incremental/homepage/*/

  각 날짜 폴더의 공고 개수와 DB를 비교
  └─> unprocessed_dates.json 생성

2단계: 복구 (batch_reprocess_dates.py)
  ├─ unprocessed_dates.json 읽기
  └─ batch_scraper_to_pre_processor.py를 날짜별로 호출
      └─> announcement_pre_processing 테이블에 INSERT
```

---

## 🚀 사용 방법

### Step 1: 미처리 데이터 검사

```bash
cd /home/zium/classfy_scraper

# 최근 30일 검사
python3 find_unprocessed_dates.py

# 최근 60일 검사
python3 find_unprocessed_dates.py --days 60

# 특정 소스만 검사
python3 find_unprocessed_dates.py --source btp

# 상세 리포트 (완료된 날짜도 표시)
python3 find_unprocessed_dates.py --report
```

#### 출력 예시

```
================================================================================
【BTP】 미처리 데이터 검사
================================================================================
  최근 30일 이내 날짜 폴더: 30개

  2025-11-11: ❌ 미등록
    폴더:  782개 | DB:    0개 | 차이:  782개
    사이트별 상세:
      - keiti              : 폴더   5개 | DB   0개 | 차이   5개
      - cceiGyeonggi       : 폴더   2개 | DB   0개 | 차이   2개

  2025-11-12: ❌ 미등록
    폴더:  456개 | DB:    0개 | 차이:  456개

  ⚠️  미처리 날짜: 2개
  📊 미등록 공고: 1,238개

================================================================================
【최종 요약】
================================================================================

  BTP       : 2개 날짜, 1,238개 공고 미등록
  EMINWON   : 2개 날짜, 1,457개 공고 미등록
  HOMEPAGE  : 2개 날짜, 4,588개 공고 미등록

  ============================================================================
  총계        : 6개 날짜, 7,283개 공고 미등록
  ============================================================================

  ⚠️  DB에 등록되지 않은 공고가 7,283개 있습니다!

  💡 재처리 명령어:
     python3 batch_reprocess_dates.py --auto

  📄 결과 저장: unprocessed_dates.json
```

### Step 2: 자동 복구

```bash
# 1. Dry-run으로 계획 확인 (실제 실행 안함)
python3 batch_reprocess_dates.py --auto --dry-run

# 2. 실제 복구 실행
python3 batch_reprocess_dates.py --auto

# 3. 강제 재처리 (이미 처리된 항목도 재처리)
python3 batch_reprocess_dates.py --auto --force
```

#### 출력 예시

```
================================================================================
자동 재처리 모드
================================================================================

검사 날짜: 2025-11-18T14:30:25.123456
검사 기간: 최근 30일

재처리 대상: 6개 날짜

================================================================================
【BTP】 2개 날짜 재처리
================================================================================

[btp] 2025-11-11 - 미등록 782개 공고

================================================================================
처리 시작: btp / 2025-11-11
================================================================================
실행 명령어: python3 batch_scraper_to_pre_processor.py --source btp --date 2025-11-11
✅ 성공 (45.3초)

[btp] 2025-11-12 - 미등록 456개 공고
✅ 성공 (38.7초)

================================================================================
【재처리 완료】
================================================================================

  총 대상   : 6개
  성공      : 6개
  실패      : 0개
  건너뜀    : 0개

  ✅ 모든 데이터 재처리 성공!
```

---

## 🔧 고급 사용법

### 1. 특정 날짜만 재처리

```bash
# 2025-11-11 재처리
python3 batch_reprocess_dates.py --date 2025-11-11

# 특정 소스만
python3 batch_reprocess_dates.py --date 2025-11-11 --source btp

# 강제 재처리
python3 batch_reprocess_dates.py --date 2025-11-11 --force
```

### 2. 날짜 범위 재처리

```bash
# 11월 11일부터 13일까지
python3 batch_reprocess_dates.py --start 2025-11-11 --end 2025-11-13

# 특정 소스만
python3 batch_reprocess_dates.py --start 2025-11-11 --end 2025-11-13 --source eminwon
```

### 3. 특정 소스만 검사 및 복구

```bash
# BTP만 검사
python3 find_unprocessed_dates.py --source btp

# BTP만 복구
python3 batch_reprocess_dates.py --auto --source btp
```

### 4. 긴 기간 검사

```bash
# 최근 90일 검사
python3 find_unprocessed_dates.py --days 90

# 최근 180일 검사
python3 find_unprocessed_dates.py --days 180

# 최근 1년 검사
python3 find_unprocessed_dates.py --days 365
```

---

## ⏰ cronjob 통합

### 방안 1: 주간 자동 복구 (권장)

매주 일요일 새벽 3시에 미처리 데이터 자동 복구

```bash
# crontab -e 에 추가
0 3 * * 0 cd /home/zium/classfy_scraper && python3 find_unprocessed_dates.py && python3 batch_reprocess_dates.py --auto >> /home/zium/classfy_scraper/logs/weekly_recovery.log 2>&1
```

### 방안 2: 매일 체크 (보수적)

매일 저녁 11시에 검사만 수행, 수동 복구

```bash
# crontab -e 에 추가
0 23 * * * cd /home/zium/classfy_scraper && python3 find_unprocessed_dates.py >> /home/zium/classfy_scraper/logs/daily_check.log 2>&1
```

### 방안 3: 통합 스크립트

```bash
#!/bin/bash
# recovery_check_and_fix.sh

cd /home/zium/classfy_scraper

echo "=== $(date) ==="
echo "미처리 데이터 검사 시작..."

# 1. 검사
python3 find_unprocessed_dates.py

# 2. JSON 파일 확인
if [ -f "unprocessed_dates.json" ]; then
    # 미처리 데이터 있는지 확인
    UNPROCESSED=$(python3 -c "import json; f=open('unprocessed_dates.json'); d=json.load(f); print(sum(len(v) for v in d['results'].values()))")

    if [ "$UNPROCESSED" -gt 0 ]; then
        echo "미처리 데이터 $UNPROCESSED개 발견. 자동 복구 시작..."
        python3 batch_reprocess_dates.py --auto
    else
        echo "✅ 미처리 데이터 없음"
    fi
else
    echo "⚠️  unprocessed_dates.json 생성 실패"
fi

echo "=== 완료 ==="
```

### 방안 4: 실패 알림 (고급)

```bash
#!/bin/bash
# recovery_with_notification.sh

cd /home/zium/classfy_scraper

python3 find_unprocessed_dates.py

if [ -f "unprocessed_dates.json" ]; then
    UNPROCESSED=$(python3 -c "import json; f=open('unprocessed_dates.json'); d=json.load(f); print(sum(len(v) for v in d['results'].values()))")

    if [ "$UNPROCESSED" -gt 0 ]; then
        echo "미처리 데이터 $UNPROCESSED개 발견" | mail -s "미처리 데이터 발견" admin@example.com

        # 자동 복구
        python3 batch_reprocess_dates.py --auto

        # 결과 알림
        echo "복구 완료" | mail -s "데이터 복구 완료" admin@example.com
    fi
fi
```

---

## 🔍 트러블슈팅

### Q1: "파일을 찾을 수 없습니다: unprocessed_dates.json"

```bash
# 먼저 검사 스크립트 실행
python3 find_unprocessed_dates.py
```

### Q2: "경로가 존재하지 않음: /home/zium/moabojo/incremental/btp"

원격 서버에서만 실행 가능합니다. 로컬 환경에서는 경로를 수정하거나 원격 서버에 SSH로 접속하세요.

```bash
# 원격 서버 접속
ssh zium@server-ip

cd /home/zium/classfy_scraper
python3 find_unprocessed_dates.py
```

### Q3: "DB 연결 실패"

.env 파일 확인:

```bash
cat .env | grep DB_
```

### Q4: "처리 시간이 너무 오래 걸림"

대량 데이터의 경우 시간이 오래 걸릴 수 있습니다.

```bash
# 소스별로 분리 실행
python3 batch_reprocess_dates.py --auto --source btp
python3 batch_reprocess_dates.py --auto --source eminwon
python3 batch_reprocess_dates.py --auto --source homepage
```

### Q5: "일부 날짜만 재처리하고 싶음"

```bash
# JSON 파일 수동 편집
vim unprocessed_dates.json

# 또는 특정 날짜만 지정
python3 batch_reprocess_dates.py --date 2025-11-11
```

### Q6: "재처리 후에도 여전히 미등록으로 표시됨"

강제 재처리:

```bash
python3 batch_reprocess_dates.py --date 2025-11-11 --force
```

또는 announcement_pre_processor.py 로그 확인:

```bash
tail -100 logs/batch_pre_processor_*.log
```

---

## 📊 모니터링

### 일일 모니터링

```bash
# 매일 실행하여 상태 확인
python3 find_unprocessed_dates.py --days 7 | tee logs/daily_check_$(date +%Y%m%d).log
```

### 주간 리포트

```bash
# 주간 리포트 생성
python3 find_unprocessed_dates.py --days 7 --report > reports/weekly_$(date +%Y%m%d).txt
```

### 통계 확인

```bash
# unprocessed_dates.json 분석
python3 << EOF
import json
with open('unprocessed_dates.json') as f:
    data = json.load(f)

total = 0
for source, items in data['results'].items():
    count = sum(item['diff'] for item in items)
    print(f"{source}: {count:,}개 공고 미등록")
    total += count

print(f"\n총계: {total:,}개")
EOF
```

---

## 🎯 권장 워크플로우

### 일회성 복구 (지금 당장)

```bash
# 1. 미처리 데이터 검사
python3 find_unprocessed_dates.py

# 2. Dry-run으로 확인
python3 batch_reprocess_dates.py --auto --dry-run

# 3. 실제 복구
python3 batch_reprocess_dates.py --auto
```

### 지속적 관리 (장기)

```bash
# 1. cronjob 설정
crontab -e

# 2. 다음 라인 추가 (매주 일요일 새벽 3시)
0 3 * * 0 cd /home/zium/classfy_scraper && python3 find_unprocessed_dates.py && python3 batch_reprocess_dates.py --auto >> /home/zium/classfy_scraper/logs/weekly_recovery_$(date +\%Y\%m\%d).log 2>&1
```

### 긴급 복구 (특정 날짜)

```bash
# 2025-11-11 데이터 즉시 복구
python3 batch_reprocess_dates.py --date 2025-11-11 --force
```

---

## 📝 로그 위치

모든 실행 로그는 다음 위치에 저장됩니다:

- **탐지 스크립트 출력**: 콘솔 + `unprocessed_dates.json`
- **복구 스크립트 출력**: 콘솔
- **batch_pre_processor 로그**: `logs/batch_pre_processor_YYYYMMDD_HHMMSS.log`
- **cronjob 로그**: `logs/weekly_recovery.log` (cronjob 설정에 따라 다름)

---

## ✅ 체크리스트

### 초기 설정

- [ ] Python 3.x 설치 확인
- [ ] pip 패키지 설치 (`mysql-connector-python`, `python-dotenv`)
- [ ] .env 파일 설정 확인
- [ ] DB 접속 확인
- [ ] incremental 디렉토리 접근 권한 확인

### 실행 전

- [ ] 디스크 용량 충분 확인
- [ ] DB 연결 확인
- [ ] 백업 완료 (선택사항)

### 실행 후

- [ ] 로그 확인
- [ ] DB 데이터 확인
- [ ] unprocessed_dates.json 재검사

---

## 🚀 빠른 시작 (Quick Start)

```bash
# 1. 디렉토리 이동
cd /home/zium/classfy_scraper

# 2. 검사
python3 find_unprocessed_dates.py

# 3. 복구
python3 batch_reprocess_dates.py --auto

# 완료!
```

---

## 📞 지원

문제가 발생하면:

1. 로그 확인: `logs/batch_pre_processor_*.log`
2. app.log 확인: `logs/app.log.*`
3. JSON 파일 확인: `unprocessed_dates.json`

---

**작성일**: 2025-11-18
**버전**: 1.0
