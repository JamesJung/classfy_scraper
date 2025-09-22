-- 통합 URL 레지스트리 테이블 생성
-- 안양시, 원주시 등 일반 스크래퍼의 URL 중복 체크 및 관리

-- 기존 테이블이 있으면 백업
-- DROP TABLE IF EXISTS unified_url_registry_backup;
-- CREATE TABLE unified_url_registry_backup AS SELECT * FROM unified_url_registry;

-- 테이블 생성
CREATE TABLE IF NOT EXISTS unified_url_registry (
    id INT AUTO_INCREMENT PRIMARY KEY,
    
    -- 사이트 정보
    site_code VARCHAR(50) NOT NULL COMMENT '사이트 코드 (anyang, wonju 등)',
    site_name VARCHAR(100) COMMENT '사이트명 (안양시, 원주시 등)',
    
    -- 공고 정보
    announcement_id VARCHAR(100) COMMENT '공고 ID',
    announcement_url TEXT NOT NULL COMMENT '공고 URL',
    title TEXT COMMENT '공고 제목',
    post_date DATE COMMENT '작성일',
    
    -- 저장 정보
    folder_name VARCHAR(500) COMMENT '저장된 폴더명',
    content_hash VARCHAR(64) COMMENT '콘텐츠 해시',
    has_attachments BOOLEAN DEFAULT FALSE COMMENT '첨부파일 여부',
    attachment_count INT DEFAULT 0 COMMENT '첨부파일 수',
    
    -- 메타데이터
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '수집일시',
    last_checked_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '마지막 확인일시',
    
    -- 인덱스
    UNIQUE KEY idx_site_url (site_code, announcement_url(255)),
    INDEX idx_site_id (site_code, announcement_id),
    INDEX idx_post_date (post_date),
    INDEX idx_site_date (site_code, post_date),
    INDEX idx_created (created_date),
    INDEX idx_site_code (site_code)
    
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='통합 스크래퍼 URL 레지스트리';

-- 처리 로그 테이블
CREATE TABLE IF NOT EXISTS unified_processing_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    
    -- 실행 정보
    run_date DATE NOT NULL COMMENT '실행일',
    site_code VARCHAR(50) NOT NULL COMMENT '사이트 코드',
    
    -- 통계
    total_checked INT DEFAULT 0 COMMENT '확인한 공고 수',
    new_found INT DEFAULT 0 COMMENT '신규 공고 수',
    downloaded INT DEFAULT 0 COMMENT '다운로드 성공 수',
    errors INT DEFAULT 0 COMMENT '오류 수',
    duplicates INT DEFAULT 0 COMMENT '중복 수',
    
    -- 성능
    processing_time_seconds INT COMMENT '처리 시간(초)',
    pages_collected INT COMMENT '수집한 페이지 수',
    
    -- 메타데이터
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성일시',
    
    -- 인덱스
    INDEX idx_run_date (run_date),
    INDEX idx_site (site_code, run_date)
    
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='통합 스크래퍼 처리 로그';

-- 사이트별 설정 테이블 (선택사항)
CREATE TABLE IF NOT EXISTS unified_site_config (
    site_code VARCHAR(50) PRIMARY KEY COMMENT '사이트 코드',
    site_name VARCHAR(100) NOT NULL COMMENT '사이트명',
    base_url VARCHAR(500) COMMENT '기본 URL',
    is_active BOOLEAN DEFAULT TRUE COMMENT '활성화 여부',
    collection_interval_hours INT DEFAULT 24 COMMENT '수집 주기(시간)',
    max_pages INT DEFAULT 3 COMMENT '최대 수집 페이지 수',
    custom_handler VARCHAR(100) COMMENT '커스텀 핸들러명',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='통합 스크래퍼 사이트 설정';

-- 초기 사이트 설정 삽입
INSERT INTO unified_site_config (site_code, site_name, base_url, max_pages, custom_handler) VALUES
('anyang', '안양시', 'https://www.anyang.go.kr', 3, 'anyang'),
('wonju', '원주시', 'https://www.wonju.go.kr', 3, 'wonju')
ON DUPLICATE KEY UPDATE
    updated_at = CURRENT_TIMESTAMP;

-- 통계 뷰 생성
CREATE OR REPLACE VIEW unified_daily_stats AS
SELECT 
    DATE(created_date) as collection_date,
    site_code,
    COUNT(*) as total_collected,
    COUNT(DISTINCT announcement_id) as unique_announcements,
    SUM(has_attachments) as with_attachments,
    SUM(attachment_count) as total_attachments
FROM unified_url_registry
GROUP BY DATE(created_date), site_code
ORDER BY collection_date DESC, site_code;

-- 최근 활동 뷰
CREATE OR REPLACE VIEW unified_recent_activity AS
SELECT 
    site_code,
    COUNT(*) as announcements_30d,
    MAX(created_date) as last_collection,
    COUNT(DISTINCT DATE(created_date)) as active_days
FROM unified_url_registry
WHERE created_date >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY site_code;

-- 권한 설정 (필요시)
-- GRANT SELECT, INSERT, UPDATE ON opendata.unified_url_registry TO 'scraper'@'%';
-- GRANT SELECT, INSERT ON opendata.unified_processing_log TO 'scraper'@'%';
-- GRANT SELECT ON opendata.unified_site_config TO 'scraper'@'%';

-- 테이블 정보 출력
SELECT 'Tables created successfully' as status;
SHOW TABLES LIKE 'unified%';