-- 스크래퍼 상세 URL 저장 테이블
-- URL만 추출하여 저장 후 실제 스크래핑 시 중복 체크에 사용

CREATE TABLE IF NOT EXISTS scraper_detail_urls (
    id INT PRIMARY KEY AUTO_INCREMENT,
    batch_date DATE NOT NULL COMMENT '스크래핑 날짜',
    site_code VARCHAR(50) NOT NULL COMMENT '사이트 코드',
    title VARCHAR(500) NULL COMMENT '공고 제목',
    list_url TEXT NULL COMMENT '리스트 페이지 URL',
    detail_url TEXT NOT NULL COMMENT '상세 페이지 원본 URL',
    normalized_url TEXT NOT NULL COMMENT '정규화된 URL (page 파라미터 제거)',
    url_hash VARCHAR(64) NOT NULL COMMENT '정규화 URL의 SHA256 해시 (중복 체크용)',
    list_date VARCHAR(50) NULL COMMENT '리스트에서 추출한 날짜',
    scraped TINYINT(1) DEFAULT 0 COMMENT '스크래핑 완료 여부 (0: 미완료, 1: 완료)',
    scraped_at TIMESTAMP NULL COMMENT '스크래핑 완료 시간',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_batch_site (batch_date, site_code),
    INDEX idx_url_hash (url_hash),
    INDEX idx_scraped (scraped),
    INDEX idx_site_scraped (site_code, scraped),
    UNIQUE KEY uk_site_url_hash (site_code, url_hash, batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='스크래퍼 상세 URL 저장 테이블';
