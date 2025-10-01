-- 스크래퍼 실행 로그 테이블 생성
CREATE TABLE IF NOT EXISTS scraper_execution_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    site_code VARCHAR(50) NOT NULL,
    execution_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL, -- 'success', 'failed', 'timeout', 'error', 'skipped'
    error_message TEXT,
    elapsed_time FLOAT,
    scraper_file VARCHAR(255),
    from_date DATE,
    to_date DATE,
    output_dir VARCHAR(500),
    scraped_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_site_code (site_code),
    INDEX idx_execution_date (execution_date),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 타임아웃 및 에러에 대한 알림 기록 테이블
CREATE TABLE IF NOT EXISTS scraper_alert_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    log_id INT,
    site_code VARCHAR(50) NOT NULL,
    alert_type VARCHAR(20) NOT NULL, -- 'timeout', 'error', 'failure'
    alert_message TEXT,
    recipients TEXT, -- JSON 배열로 저장
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (log_id) REFERENCES scraper_execution_log(id),
    INDEX idx_site_code (site_code),
    INDEX idx_alert_type (alert_type),
    INDEX idx_sent_at (sent_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;