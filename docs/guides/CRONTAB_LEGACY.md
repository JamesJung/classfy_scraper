# Crontab 설정 가이드

## 1. 스크립트 실행 권한 설정

```bash
# 스크립트 실행 권한 부여
chmod +x /home/zium/classfy_scraper/daily_eminwon_batch_processor.sh

# 테스트 실행
/home/zium/classfy_scraper/daily_eminwon_batch_processor.sh
```

## 2. Crontab 편집

```bash
crontab -e
```

## 3. Crontab 내용 추가

다음 내용을 crontab에 추가하세요:

```cron
# ========================================
# Eminwon 배치 처리 시스템
# ========================================

# 환경 변수 설정
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
HOME=/home/zium

# 매일 새벽 6시 20분: Eminwon 배치 프로세서 실행
# (전날 수집된 데이터를 처리)
20 6 * * * /home/zium/classfy_scraper/daily_eminwon_batch_processor.sh

# 선택사항: Eminwon 증분 수집 (필요시)
# 0 1 * * * cd /home/zium/classfy_scraper && /usr/bin/python3 eminwon_incremental_orchestrator.py >> logs/eminwon_collect.log 2>&1

# ========================================
```

## 4. Crontab 설정 확인

```bash
# 현재 설정된 crontab 확인
crontab -l

# cron 서비스 상태 확인
systemctl status cron
# 또는
service cron status
```

## 5. 로그 모니터링

```bash
# 실시간 로그 모니터링
tail -f /home/zium/classfy_scraper/logs/eminwon_batch_*.log

# 오늘 처리 로그 확인
tail -100 /home/zium/classfy_scraper/logs/eminwon_batch_$(date +%Y%m%d).log

# 어제 처리 결과 확인
cat /home/zium/classfy_scraper/logs/eminwon_batch_results_$(date -d "yesterday" +%Y-%m-%d).json | python3 -m json.tool
```

## 6. 문제 해결

### 스크립트가 실행되지 않을 때

1. **권한 확인**
```bash
ls -la /home/zium/classfy_scraper/daily_eminwon_batch_processor.sh
# -rwxr-xr-x 형태여야 함
```

2. **경로 확인**
```bash
which python3
# /usr/bin/python3 확인
```

3. **수동 테스트**
```bash
cd /home/zium/classfy_scraper
./daily_eminwon_batch_processor.sh
```

4. **Cron 로그 확인**
```bash
grep CRON /var/log/syslog | tail -20
```

### DB 연결 오류

1. **.env 파일 확인**
```bash
cat /home/zium/classfy_scraper/.env | grep DB_
```

2. **MySQL 연결 테스트**
```bash
mysql -h $DB_HOST -P $DB_PORT -u $DB_USER -p$DB_PASSWORD $DB_NAME -e "SELECT 1"
```

## 7. 수동 실행 명령어

```bash
# 오늘 날짜 처리
cd /home/zium/classfy_scraper
python3 eminwon_batch_processor.py

# 특정 날짜 처리
python3 eminwon_batch_processor.py --date 2025-09-22

# 어제 날짜 처리
python3 eminwon_batch_processor.py --yesterday

# 강제 재처리
python3 eminwon_batch_processor.py --force
```

## 8. 전체 파이프라인 (선택사항)

Eminwon 수집과 배치 처리를 모두 포함하려면:

```cron
# 1. 새벽 1시: 증분 수집
0 1 * * * cd /home/zium/classfy_scraper && /usr/bin/python3 eminwon_incremental_orchestrator.py >> logs/eminwon_collect.log 2>&1

# 2. 새벽 6시 20분: 배치 처리
20 6 * * * /home/zium/classfy_scraper/daily_eminwon_batch_processor.sh
```

## 9. 알림 설정 (선택사항)

처리 실패 시 이메일 알림을 받으려면 스크립트에 다음 추가:

```bash
# daily_eminwon_batch_processor.sh 수정
if [ $EXIT_CODE -ne 0 ]; then
    echo "처리 실패: $(date)" | mail -s "Eminwon Batch Failed" admin@example.com
fi
```

## 10. 주의사항

- **시간대**: 서버 시간대 확인 (`date` 명령으로 확인)
- **메모리**: 배치 처리 시 충분한 메모리 필요
- **디스크**: 로그 파일 용량 관리 (스크립트에 30일 자동 삭제 포함)
- **DB 연결**: 동시 연결 수 제한 확인