-- =====================================================
-- 스크래퍼 실패 공고 추적 테이블
-- =====================================================
-- 목적: 개별 공고 스크래핑 실패 시 정보를 기록하여 나중에 재시도
-- 사용: failure_logger.js 모듈에서 INSERT/UPDATE
-- =====================================================

CREATE TABLE IF NOT EXISTS scraper_failed_announcements (
  id INT PRIMARY KEY AUTO_INCREMENT,

  -- 배치 정보
  batch_date DATE NOT NULL COMMENT '스크래핑 실행 날짜',
  site_code VARCHAR(50) NOT NULL COMMENT '사이트 코드 (예: andong, daegu)',

  -- 실패한 공고 정보
  announcement_title VARCHAR(500) COMMENT '공고 제목',
  announcement_url VARCHAR(1000) COMMENT '리스트에서 추출한 URL',
  detail_url VARCHAR(1000) COMMENT '실제 상세 페이지 URL',

  -- 에러 정보
  error_type VARCHAR(50) COMMENT '에러 타입: detail_fetch_failed, timeout, parse_error 등',
  error_message TEXT COMMENT '상세 에러 메시지',

  -- 재시도 정보
  retry_count INT DEFAULT 0 COMMENT '재시도 횟수',
  last_retry_at TIMESTAMP NULL COMMENT '마지막 재시도 시각',
  status VARCHAR(20) DEFAULT 'pending' COMMENT '상태: pending, retrying, success, permanent_failure',

  -- 타임스탬프
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '최초 기록 시각',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '최종 수정 시각',

  -- 인덱스
  INDEX idx_batch_site (batch_date, site_code),
  INDEX idx_status (status),
  INDEX idx_created_at (created_at),

  -- 중복 방지: 같은 날짜에 같은 URL은 하나만
  UNIQUE KEY uk_url_date (detail_url, batch_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='스크래퍼 개별 공고 실패 추적';

-- =====================================================
-- 사용 예시
-- =====================================================
-- 1. 오늘 실패한 공고 조회:
--    SELECT * FROM scraper_failed_announcements
--    WHERE batch_date = CURDATE() AND status = 'pending';
--
-- 2. 특정 사이트의 재시도 대기 공고:
--    SELECT * FROM scraper_failed_announcements
--    WHERE site_code = 'andong' AND status = 'pending'
--    ORDER BY created_at DESC;
--
-- 3. 재시도 3회 초과한 영구 실패 공고:
--    SELECT * FROM scraper_failed_announcements
--    WHERE retry_count >= 3 AND status = 'permanent_failure';
-- =====================================================
