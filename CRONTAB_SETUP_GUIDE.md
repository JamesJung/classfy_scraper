# 크론탭 설정 가이드 - run_batch_pre_processor.sh

## 📋 개요
`run_batch_pre_processor.sh`는 수집된 공고 데이터의 첨부파일을 자동으로 처리하는 배치 스크립트입니다.

## 🚀 빠른 설정 (자동)

### Linux 서버에서:
```bash
# 1. 스크립트에 실행 권한 부여
chmod +x setup_batch_pre_processor_cron_linux.sh

# 2. 크론탭 자동 설정
./setup_batch_pre_processor_cron_linux.sh
```

### macOS에서:
```bash
# 1. 스크립트에 실행 권한 부여  
chmod +x setup_batch_pre_processor_cron.sh

# 2. 크론탭 자동 설정
./setup_batch_pre_processor_cron.sh
```

## 🔧 수동 설정

### 1. 크론탭 편집
```bash
crontab -e
```

### 2. 다음 중 하나를 추가

#### 권장 설정 (새벽 3시 30분 - 스크래퍼 실행 후)
```bash
# 배치 프리프로세서 - 매일 새벽 3시 30분 실행
30 3 * * * /home/zium/classfy_scraper/run_batch_pre_processor.sh >> /home/zium/classfy_scraper/logs/cron_execution.log 2>&1
```

#### 하루 3번 실행 (더 자주 처리)
```bash
# 배치 프리프로세서 - 오전 6시, 오후 2시, 밤 10시
0 6,14,22 * * * /home/zium/classfy_scraper/run_batch_pre_processor.sh >> /home/zium/classfy_scraper/logs/cron_execution.log 2>&1
```

#### 매 4시간마다 실행
```bash
# 배치 프리프로세서 - 매 4시간마다
0 */4 * * * /home/zium/classfy_scraper/run_batch_pre_processor.sh >> /home/zium/classfy_scraper/logs/cron_execution.log 2>&1
```

## 📅 크론 표현식 이해

```
* * * * * command
┬ ┬ ┬ ┬ ┬
│ │ │ │ │
│ │ │ │ └─── 요일 (0-7, 0과 7은 일요일)
│ │ │ └───── 월 (1-12)
│ │ └─────── 일 (1-31)
│ └───────── 시 (0-23)
└─────────── 분 (0-59)
```

### 예시:
- `30 3 * * *` = 매일 03:30
- `0 6,14,22 * * *` = 매일 06:00, 14:00, 22:00
- `0 */4 * * *` = 0:00, 4:00, 8:00, 12:00, 16:00, 20:00
- `0 10 * * 1-5` = 평일 10:00

## 🔍 모니터링

### 크론탭 확인
```bash
# 현재 설정된 크론탭 보기
crontab -l

# 배치 프리프로세서 크론탭만 보기
crontab -l | grep batch_pre_processor
```

### 로그 확인
```bash
# 최신 로그 확인
tail -f ~/classfy_scraper/logs/batch_pre_processor_*.log

# 크론 실행 로그 확인
tail -f ~/classfy_scraper/logs/cron_execution.log

# 시스템 크론 로그 확인 (Linux)
tail -f /var/log/cron
# 또는
journalctl -u crond -f
```

### 처리 결과 확인
```bash
# JSON 결과 파일 확인
ls -la ~/classfy_scraper/logs/*batch_results*.json

# 최신 결과 보기
cat ~/classfy_scraper/logs/eminwon_batch_results_$(date +%Y-%m-%d).json | jq '.'
```

## 📊 데이터베이스 확인

```sql
-- 오늘 처리된 데이터 확인
SELECT 
    site_type,
    site_code,
    COUNT(*) as count,
    MIN(created_at) as first_processed,
    MAX(created_at) as last_processed
FROM announcement_pre_processing
WHERE DATE(created_at) = CURDATE()
GROUP BY site_type, site_code
ORDER BY last_processed DESC;

-- 첨부파일 처리 상태 확인
SELECT 
    processing_status,
    COUNT(*) as count,
    COUNT(CASE WHEN attachment_filenames IS NOT NULL THEN 1 END) as with_attachments
FROM announcement_pre_processing
WHERE DATE(created_at) = CURDATE()
GROUP BY processing_status;
```

## 🐛 트러블슈팅

### 크론이 실행되지 않는 경우

1. **크론 서비스 확인**
```bash
# Linux
systemctl status crond
# 또는
systemctl status cron

# 서비스 시작
sudo systemctl start crond
sudo systemctl enable crond
```

2. **스크립트 경로 확인**
```bash
# 절대 경로 확인
which python3
pwd
ls -la run_batch_pre_processor.sh
```

3. **권한 확인**
```bash
# 실행 권한 부여
chmod +x run_batch_pre_processor.sh
```

4. **환경 변수 문제**
크론은 제한된 환경에서 실행되므로 전체 경로 사용 필요:
```bash
# 잘못된 예
python3 batch_scraper_to_pre_processor.py

# 올바른 예
/usr/bin/python3 /home/zium/classfy_scraper/batch_scraper_to_pre_processor.py
```

### NumPy 버전 충돌 (첨부파일 처리 실패)

```bash
# NumPy 다운그레이드
pip install --user 'numpy<2.0'

# 또는 fix 스크립트 실행
./fix_numpy_dependency.sh
```

### 로그 파일이 너무 커지는 경우

```bash
# logrotate 설정 추가
sudo cat > /etc/logrotate.d/batch_pre_processor << EOF
/home/zium/classfy_scraper/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 zium zium
}
EOF
```

## 🎯 권장 사항

1. **실행 시간 조정**
   - 스크래퍼가 새벽 2시에 실행된다면, 프리프로세서는 3시 30분에 실행
   - 데이터 양이 많다면 시간 간격을 더 두기

2. **모니터링 설정**
   - 실패 시 알림 받기 위해 이메일 설정 추가
   - 처리 시간이 너무 오래 걸리면 워커 수 조정

3. **정기 점검**
   - 주 1회 로그 확인
   - 월 1회 오래된 데이터 정리

## 📞 도움말

추가 도움이 필요하시면:
- 로그 파일 확인: `~/classfy_scraper/logs/`
- 설정 스크립트 재실행: `./setup_batch_pre_processor_cron_linux.sh`
- 수동 실행 테스트: `./run_batch_pre_processor.sh`