# Eminwon 배치 처리 시스템 사용법

## 개요
`eminwon_batch_scraper_to_processor.py`는 eminwon 증분 수집 결과를 `announcement_pre_processor.py`로 병렬 처리하는 오케스트레이터입니다.

## 처리 흐름
1. **Eminwon 증분 수집** → `eminwon_data_new/YYYY-MM-DD/지역명/` 생성
2. **배치 프로세서 실행** → 각 지역별로 병렬 처리
3. **announcement_pre_processor.py** → 각 지역 데이터를 DB에 저장

## 기본 사용법

### 1. 오늘 날짜 데이터 처리
```bash
python eminwon_batch_scraper_to_processor.py
```

### 2. 특정 날짜 데이터 처리
```bash
python eminwon_batch_scraper_to_processor.py --date 2025-09-22
```

### 3. 어제 날짜 데이터 처리
```bash
python eminwon_batch_scraper_to_processor.py --yesterday
```

### 4. 워커 수 조정 (기본값: 5)
```bash
python eminwon_batch_scraper_to_processor.py --workers 10
```

### 5. 강제 재처리
```bash
# 이미 처리된 데이터도 다시 처리
python eminwon_batch_scraper_to_processor.py --force

# 첨부파일도 강제 재처리
python eminwon_batch_scraper_to_processor.py --force --attach-force
```

## 일일 배치 실행 (Cron)

### 1. Crontab 설정
```bash
crontab -e
```

### 2. 매일 새벽 2시 실행 예시
```cron
# Eminwon 증분 수집 (매일 새벽 1시)
0 1 * * * cd /Users/jin/classfy_scraper && /usr/bin/python3 eminwon_incremental_orchestrator.py >> logs/eminwon_collect.log 2>&1

# Eminwon 배치 처리 (매일 새벽 2시)
0 2 * * * cd /Users/jin/classfy_scraper && /usr/bin/python3 eminwon_batch_scraper_to_processor.py >> logs/eminwon_batch.log 2>&1
```

## 백그라운드 실행

### 1. nohup 사용
```bash
nohup python eminwon_batch_scraper_to_processor.py --date 2025-09-22 > logs/batch_$(date +%Y%m%d).log 2>&1 &
```

### 2. screen/tmux 사용
```bash
# screen 시작
screen -S eminwon_batch

# 배치 실행
python eminwon_batch_scraper_to_processor.py --date 2025-09-22

# screen 분리 (Ctrl+A, D)
```

## 로그 및 결과 확인

### 1. 실시간 로그 모니터링
```bash
tail -f logs/eminwon_batch_2025-09-22.log
```

### 2. 처리 결과 확인
```bash
# JSON 결과 파일
cat logs/eminwon_batch_results_2025-09-22.json | python -m json.tool
```

### 3. 처리 통계 확인
```bash
# 로그에서 통계 추출
grep "처리 완료 -" logs/eminwon_batch_2025-09-22.log
```

## 성능 최적화

### 워커 수 결정 가이드
- **CPU 코어 수 기준**: CPU 코어 수의 50-70%
- **메모리 기준**: 워커당 약 500MB 메모리 필요
- **추천 설정**:
  - 4코어 시스템: `--workers 2-3`
  - 8코어 시스템: `--workers 4-5`
  - 16코어 시스템: `--workers 8-10`

### 처리 시간 예상
- **평균 처리 시간**: 지역당 10-20초
- **전체 처리 시간** (74개 지역 기준):
  - 워커 2개: 약 10-15분
  - 워커 5개: 약 5-7분
  - 워커 10개: 약 3-4분

## 문제 해결

### 1. 처리 실패한 지역 재처리
```bash
# 특정 지역만 재처리
python announcement_pre_processor.py -d eminwon_data_new/2025-09-22 --site-code 광주남구 --force
```

### 2. 프로세스 중단
```bash
# 실행 중인 프로세스 찾기
ps aux | grep eminwon_batch

# 프로세스 종료
kill -9 [PID]
```

### 3. DB 연결 오류
```bash
# .env 파일 확인
cat .env | grep DB_

# DB 연결 테스트
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('DB_HOST:', os.getenv('DB_HOST'))"
```

## 모니터링 대시보드 (선택사항)

### 처리 상태 확인 쿼리
```sql
-- 오늘 처리된 데이터 확인
SELECT 
    site_code, 
    COUNT(*) as processed_count,
    MAX(created_at) as last_processed
FROM announcement_prv_processing
WHERE DATE(created_at) = CURDATE()
GROUP BY site_code
ORDER BY processed_count DESC;

-- 처리 실패 확인
SELECT 
    site_code,
    folder_name,
    error_message
FROM announcement_prv_processing
WHERE processing_status = 'failed'
AND DATE(created_at) = CURDATE();
```

## 전체 파이프라인 스크립트

`daily_eminwon_pipeline.sh` 생성:
```bash
#!/bin/bash

# 환경 변수 설정
export PATH=/usr/local/bin:$PATH
cd /Users/jin/classfy_scraper

# 날짜 설정
TODAY=$(date +%Y-%m-%d)
LOG_DIR="logs"

echo "=== Eminwon 일일 파이프라인 시작: $TODAY ==="

# 1. Eminwon 증분 수집
echo "[1/2] Eminwon 증분 수집 시작..."
python eminwon_incremental_orchestrator.py >> $LOG_DIR/eminwon_collect_$TODAY.log 2>&1

if [ $? -eq 0 ]; then
    echo "[1/2] ✅ 수집 완료"
else
    echo "[1/2] ❌ 수집 실패"
    exit 1
fi

# 2. 배치 처리
echo "[2/2] 배치 처리 시작..."
python eminwon_batch_scraper_to_processor.py --date $TODAY --workers 5 >> $LOG_DIR/eminwon_batch_$TODAY.log 2>&1

if [ $? -eq 0 ]; then
    echo "[2/2] ✅ 배치 처리 완료"
else
    echo "[2/2] ❌ 배치 처리 실패"
    exit 1
fi

echo "=== 파이프라인 완료 ==="

# 통계 출력
python -c "
import json
with open('logs/eminwon_batch_results_$TODAY.json') as f:
    data = json.load(f)
    stats = data['stats']
    print(f\"총 {stats['total_regions']}개 지역 처리\")
    print(f\"성공: {stats['success']}개, 실패: {stats['failed']}개, 스킵: {stats['skipped']}개\")
"
```

실행 권한 부여:
```bash
chmod +x daily_eminwon_pipeline.sh
```

## 주의사항

1. **메모리 사용량**: 워커가 많을수록 메모리 사용량 증가
2. **DB 연결**: 동시 연결 수 제한 확인 필요
3. **디스크 공간**: 첨부파일 처리 시 충분한 공간 필요
4. **네트워크**: Ollama API 호출 시 네트워크 대역폭 고려

## 관련 파일
- `eminwon_incremental_orchestrator.py`: Eminwon 증분 수집
- `eminwon_batch_scraper_to_processor.py`: 배치 처리 오케스트레이터  
- `announcement_pre_processor.py`: 개별 공고 처리
- `logs/eminwon_batch_YYYY-MM-DD.log`: 처리 로그
- `logs/eminwon_batch_results_YYYY-MM-DD.json`: 처리 결과