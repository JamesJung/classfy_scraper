# MySQL 연결 수 관리 가이드

## 📊 현재 상황
- DB 서버: 192.168.0.95:3309
- 문제: 최대 연결 수 제한으로 새 연결 차단
- 기존 연결: 4개 (announcement_pre_processor.py 사용 중)

## 🔍 연결 수 확인 방법

### 1. Python 스크립트 사용 (로컬에서)
```bash
python3 check_db_connections.py
```

### 2. MySQL 직접 접속 (서버에서)
```bash
mysql -h 192.168.0.95 -P 3309 -u root -p subvention

# 또는 SQL 파일 실행
mysql -h 192.168.0.95 -P 3309 -u root -p subvention < check_mysql_connections.sql
```

### 3. 주요 확인 명령어
```sql
-- 최대 연결 수 확인
SHOW VARIABLES LIKE 'max_connections';

-- 현재 연결 수 확인
SHOW STATUS LIKE 'Threads_connected';

-- 연결 목록 보기
SHOW PROCESSLIST;

-- 사용자별 연결 수
SELECT user, COUNT(*) FROM information_schema.processlist GROUP BY user;
```

## 🔧 연결 수 늘리기

### 방법 1: 임시 변경 (즉시 적용, 재시작시 초기화)
```sql
-- MySQL에 접속 후 실행
SET GLOBAL max_connections = 500;
SET GLOBAL max_user_connections = 100;

-- 확인
SHOW VARIABLES LIKE 'max_connections';
```

### 방법 2: 영구 변경 (서버 재시작 필요)

#### Linux/Unix (my.cnf)
```bash
# /etc/mysql/my.cnf 또는 /etc/my.cnf 편집
sudo vi /etc/mysql/my.cnf

# [mysqld] 섹션에 추가
[mysqld]
max_connections = 500
max_user_connections = 100
wait_timeout = 28800
interactive_timeout = 28800

# MySQL 재시작
sudo systemctl restart mysql
# 또는
sudo service mysql restart
```

#### Windows (my.ini)
```ini
# C:\ProgramData\MySQL\MySQL Server X.X\my.ini 편집

[mysqld]
max_connections = 500
max_user_connections = 100

# MySQL 서비스 재시작
net stop MySQL
net start MySQL
```

## 🧹 불필요한 연결 정리

### 1. Sleep 상태의 오래된 연결 찾기
```sql
SELECT id, user, host, command, time 
FROM information_schema.processlist 
WHERE command = 'Sleep' AND time > 300;
```

### 2. 특정 연결 종료
```sql
-- 특정 ID의 연결 종료
KILL [connection_id];

-- 예시
KILL 1234;
```

### 3. 특정 사용자의 모든 연결 종료
```sql
-- 종료 명령 생성
SELECT CONCAT('KILL ', id, ';') AS kill_command
FROM information_schema.processlist 
WHERE user = 'specific_user';

-- 생성된 명령 실행
```

## 📈 권장 설정값

### 소규모 서버 (메모리 4-8GB)
```ini
max_connections = 200
max_user_connections = 50
```

### 중규모 서버 (메모리 8-16GB)
```ini
max_connections = 500
max_user_connections = 100
```

### 대규모 서버 (메모리 16GB+)
```ini
max_connections = 1000
max_user_connections = 200
```

## ⚠️ 주의사항

1. **메모리 계산**: 각 연결은 약 1-3MB 메모리 사용
   - max_connections = 500 → 약 500-1500MB 필요

2. **시스템 리소스 확인**:
   ```sql
   -- 메모리 사용량 확인
   SHOW STATUS LIKE 'innodb_buffer_pool_size';
   ```

3. **File Descriptor 한계**:
   - OS의 open files 제한 확인 필요
   ```bash
   ulimit -n  # 현재 제한 확인
   ulimit -n 65535  # 제한 증가
   ```

## 🔄 현재 프로젝트에 적용

### 1. 즉시 해결 (임시)
```bash
# DB 서버에 접속 가능한 곳에서
mysql -h 192.168.0.95 -P 3309 -u root -p subvention < increase_mysql_connections.sql
```

### 2. 영구 해결
DB 서버 관리자에게 요청:
- max_connections를 200 이상으로 증가
- my.cnf 파일 수정 및 MySQL 재시작

### 3. 애플리케이션 개선
- 연결 풀(Connection Pool) 사용
- 사용 후 연결 즉시 반환
- 장시간 미사용 연결 자동 종료

## 📞 문제 발생시

1. 연결 수 확인: `python3 check_db_connections.py`
2. 불필요한 프로세스 종료: `ps aux | grep announcement`
3. DB 업데이트 실행: `python3 run_incremental_scrapers_v2.py`

---
작성일: 2024-11-29