-- MySQL 연결 수 확인 SQL 쿼리 모음

-- 1. 현재 최대 연결 수 설정 확인
SHOW VARIABLES LIKE 'max_connections';

-- 2. 현재 활성 연결 수 확인
SHOW STATUS LIKE 'Threads_connected';

-- 3. 지금까지의 최대 동시 연결 수 확인
SHOW STATUS LIKE 'Max_used_connections';

-- 4. 연결 제한에 도달한 횟수 확인
SHOW STATUS LIKE 'Connection_errors_max_connections';

-- 5. 현재 연결된 모든 프로세스 목록 확인
SHOW FULL PROCESSLIST;

-- 6. 사용자별 연결 수 확인
SELECT user, host, COUNT(*) as connections
FROM information_schema.processlist
GROUP BY user, host
ORDER BY connections DESC;

-- 7. 데이터베이스별 연결 수 확인
SELECT db, COUNT(*) as connections
FROM information_schema.processlist
WHERE db IS NOT NULL
GROUP BY db
ORDER BY connections DESC;

-- 8. 연결 관련 모든 설정 확인
SHOW VARIABLES LIKE '%connect%';

-- 9. 대기 시간 설정 확인
SHOW VARIABLES LIKE 'wait_timeout';
SHOW VARIABLES LIKE 'interactive_timeout';

-- 10. 사용자별 최대 연결 수 제한 확인
SELECT user, host, max_connections, max_user_connections
FROM mysql.user
WHERE user != '';