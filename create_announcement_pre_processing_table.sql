-- announcement_pre_processing 테이블 생성 SQL
-- 실행 방법: mysql -u [사용자명] -p < create_announcement_pre_processing_table.sql

CREATE TABLE IF NOT EXISTS announcement_pre_processing (
    id INT PRIMARY KEY AUTO_INCREMENT,
    folder_name VARCHAR(255) UNIQUE,
    site_type VARCHAR(50),
    site_code VARCHAR(50),
    content_md LONGTEXT,
    combined_content LONGTEXT,
    attachment_filenames TEXT,
    attachment_files_list JSON,
    exclusion_keyword TEXT,
    exclusion_reason TEXT,
    title VARCHAR(500),
    origin_url VARCHAR(1000),
    announcement_date VARCHAR(50),
    processing_status VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_site_code (site_code),
    INDEX idx_processing_status (processing_status),
    INDEX idx_origin_url (origin_url)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 테이블 구조 확인
DESCRIBE announcement_pre_processing;