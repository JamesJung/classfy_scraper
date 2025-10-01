-- MySQL 최대 연결 수 증가 스크립트

-- 1. 현재 설정 확인
SELECT @@max_connections AS 'Current Max Connections';
SELECT @@max_user_connections AS 'Current Max User Connections';

-- 2. 현재 사용 중인 연결 수 확인
SELECT COUNT(*) as 'Active Connections' FROM information_schema.processlist;

-- 3. 임시로 최대 연결 수 증가 (재시작시 초기화)
SET GLOBAL max_connections = 500;
SET GLOBAL max_user_connections = 100;

-- 4. 변경 확인
SELECT @@max_connections AS 'New Max Connections';
SELECT @@max_user_connections AS 'New Max User Connections';

-- 5. 불필요한 연결 정리 (선택사항)
-- 특정 사용자의 연결 종료
-- SELECT CONCAT('KILL ', id, ';') FROM information_schema.processlist WHERE user = 'specific_user';

-- 6. Sleep 상태의 오래된 연결 종료 (선택사항)
-- SELECT CONCAT('KILL ', id, ';') FROM information_schema.processlist WHERE Command = 'Sleep' AND Time > 300;