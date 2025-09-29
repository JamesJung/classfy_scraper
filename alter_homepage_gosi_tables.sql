-- homepage_gosi_url_registry 테이블을 eminwon_url_registry 구조와 유사하게 수정
-- 기존 테이블 백업 권장

-- 1. ID 타입 변경 (INT → BIGINT)
ALTER TABLE homepage_gosi_url_registry 
    MODIFY COLUMN id BIGINT AUTO_INCREMENT;

-- 2. announcement_url 타입 및 제약 조건 변경
ALTER TABLE homepage_gosi_url_registry 
    MODIFY COLUMN announcement_url VARCHAR(1000) NOT NULL,
    ADD UNIQUE KEY idx_announcement_url (announcement_url);

-- 3. title 타입 변경
ALTER TABLE homepage_gosi_url_registry 
    MODIFY COLUMN title VARCHAR(500);

-- 4. announcement_id 컬럼 추가 (공고 고유번호)
ALTER TABLE homepage_gosi_url_registry 
    ADD COLUMN announcement_id VARCHAR(100) AFTER announcement_url,
    ADD INDEX idx_announcement_id (announcement_id);

-- 5. 타임스탬프 컬럼 이름 변경 (eminwon과 일치)
ALTER TABLE homepage_gosi_url_registry 
    CHANGE COLUMN created_at first_seen_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHANGE COLUMN updated_at last_checked_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- 6. site_code를 region으로 변경하지 않음 (homepage는 사이트별이므로)
-- 하지만 인덱스는 유사하게 구성
ALTER TABLE homepage_gosi_url_registry
    ADD INDEX idx_site_date (site_code, post_date) IF NOT EXISTS;

-- 7. 불필요한 인덱스 정리 (중복 제거)
ALTER TABLE homepage_gosi_url_registry
    DROP INDEX IF EXISTS idx_site_url;  -- announcement_url이 UNIQUE가 되므로

-- 최종 테이블 구조 확인
SHOW CREATE TABLE homepage_gosi_url_registry;

-- 통계 정보
SELECT 
    'homepage_gosi_url_registry' as table_name,
    COUNT(*) as total_records,
    COUNT(DISTINCT site_code) as unique_sites,
    MIN(post_date) as earliest_date,
    MAX(post_date) as latest_date
FROM homepage_gosi_url_registry;

-- eminwon과 구조 비교
SELECT 
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_KEY
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'opendata' 
    AND TABLE_NAME IN ('eminwon_url_registry', 'homepage_gosi_url_registry')
ORDER BY TABLE_NAME, ORDINAL_POSITION;