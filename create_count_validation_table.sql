-- 스크래퍼 건수 검증 테이블
-- 예상 건수와 실제 스크래핑 건수를 비교하여 부분 실패를 감지

CREATE TABLE IF NOT EXISTS scraper_count_validation (
    id INT PRIMARY KEY AUTO_INCREMENT,
    batch_date DATE NOT NULL COMMENT '스크래핑 날짜',
    site_code VARCHAR(50) NOT NULL COMMENT '사이트 코드',
    expected_count INT DEFAULT 0 COMMENT '예상 공고 건수 (카운트 단계)',
    actual_count INT DEFAULT 0 COMMENT '실제 스크래핑 성공 건수',
    failed_count INT DEFAULT 0 COMMENT '실패한 공고 건수',
    page_count INT DEFAULT 0 COMMENT '확인한 페이지 수',
    status VARCHAR(20) DEFAULT 'counting' COMMENT '상태: counting, scraping, completed, mismatch',
    count_started_at TIMESTAMP NULL COMMENT '카운트 시작 시간',
    count_completed_at TIMESTAMP NULL COMMENT '카운트 완료 시간',
    scrape_started_at TIMESTAMP NULL COMMENT '스크래핑 시작 시간',
    scrape_completed_at TIMESTAMP NULL COMMENT '스크래핑 완료 시간',
    mismatch_reason TEXT NULL COMMENT '불일치 사유',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_batch_site (batch_date, site_code),
    INDEX idx_status (status),
    INDEX idx_batch_date (batch_date),
    UNIQUE KEY uk_batch_site (batch_date, site_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='스크래퍼 건수 검증 테이블';
