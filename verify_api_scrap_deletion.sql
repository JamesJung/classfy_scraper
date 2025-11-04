-- ============================================================================
-- announcement_pre_processing 테이블 api_scrap 데이터 확인 쿼리
-- ============================================================================
-- 실행 방법: 각 쿼리를 순서대로 실행하여 결과 확인
-- ============================================================================

-- 1. 전체 현황
SELECT
    '=== 전체 api_scrap 데이터 현황 ===' as info;

SELECT
    COUNT(*) as total_records,
    MIN(announcement_date) as earliest_date,
    MAX(announcement_date) as latest_date
FROM announcement_pre_processing
WHERE site_type = 'api_scrap';


-- 2. 날짜 형식별 분포
SELECT
    '=== 날짜 형식별 분포 ===' as info;

SELECT
    LENGTH(announcement_date) as date_length,
    CASE
        WHEN LENGTH(announcement_date) = 8 AND announcement_date REGEXP '^[0-9]{8}$' THEN 'YYYYMMDD'
        WHEN LENGTH(announcement_date) = 10 AND announcement_date LIKE '%.%.%' THEN 'YYYY.MM.DD'
        WHEN LENGTH(announcement_date) = 10 AND announcement_date LIKE '%-%-%' THEN 'YYYY-MM-DD'
        ELSE 'Other'
    END as date_format,
    COUNT(*) as count,
    MIN(announcement_date) as min_date,
    MAX(announcement_date) as max_date
FROM announcement_pre_processing
WHERE site_type = 'api_scrap'
GROUP BY date_length, date_format
ORDER BY count DESC;


-- 3. site_code별 분포
SELECT
    '=== site_code별 분포 ===' as info;

SELECT
    site_code,
    COUNT(*) as count,
    MIN(announcement_date) as earliest,
    MAX(announcement_date) as latest
FROM announcement_pre_processing
WHERE site_type = 'api_scrap'
GROUP BY site_code
ORDER BY count DESC;


-- 4. 2025-10-30 이전 데이터 확인 (삭제 대상)
SELECT
    '=== 2025-10-30 이전 데이터 (삭제 대상) ===' as info;

SELECT
    COUNT(*) as delete_target_count
FROM announcement_pre_processing
WHERE site_type = 'api_scrap'
  AND (
    (LENGTH(announcement_date) = 8
     AND announcement_date REGEXP '^[0-9]{8}$'
     AND STR_TO_DATE(announcement_date, '%Y%m%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%.%.%'
     AND STR_TO_DATE(announcement_date, '%Y.%m.%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%-%-%'
     AND STR_TO_DATE(announcement_date, '%Y-%m-%d') < '2025-10-30')
  );


-- 5. 2025-10-30 이후 데이터 확인 (남을 데이터)
SELECT
    '=== 2025-10-30 이후 데이터 (삭제 후 남을 데이터) ===' as info;

SELECT
    COUNT(*) as will_remain
FROM announcement_pre_processing
WHERE site_type = 'api_scrap'
  AND NOT (
    (LENGTH(announcement_date) = 8
     AND announcement_date REGEXP '^[0-9]{8}$'
     AND STR_TO_DATE(announcement_date, '%Y%m%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%.%.%'
     AND STR_TO_DATE(announcement_date, '%Y.%m.%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%-%-%'
     AND STR_TO_DATE(announcement_date, '%Y-%m-%d') < '2025-10-30')
  );


-- 6. 삭제 대상 샘플 (처음 10건)
SELECT
    '=== 삭제 대상 샘플 (처음 10건) ===' as info;

SELECT
    id,
    site_code,
    folder_name,
    announcement_date,
    LEFT(title, 50) as title_preview,
    created_at
FROM announcement_pre_processing
WHERE site_type = 'api_scrap'
  AND (
    (LENGTH(announcement_date) = 8
     AND announcement_date REGEXP '^[0-9]{8}$'
     AND STR_TO_DATE(announcement_date, '%Y%m%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%.%.%'
     AND STR_TO_DATE(announcement_date, '%Y.%m.%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%-%-%'
     AND STR_TO_DATE(announcement_date, '%Y-%m-%d') < '2025-10-30')
  )
ORDER BY announcement_date
LIMIT 10;


-- 7. 첨부파일 있는 삭제 대상 확인
SELECT
    '=== 첨부파일 있는 삭제 대상 ===' as info;

SELECT
    COUNT(*) as has_attachments,
    SUM(CASE WHEN attachment_filenames IS NOT NULL AND attachment_filenames != '' THEN 1 ELSE 0 END) as with_files
FROM announcement_pre_processing
WHERE site_type = 'api_scrap'
  AND (
    (LENGTH(announcement_date) = 8
     AND announcement_date REGEXP '^[0-9]{8}$'
     AND STR_TO_DATE(announcement_date, '%Y%m%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%.%.%'
     AND STR_TO_DATE(announcement_date, '%Y.%m.%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%-%-%'
     AND STR_TO_DATE(announcement_date, '%Y-%m-%d') < '2025-10-30')
  );


-- 8. 요약
SELECT
    '=== 요약 ===' as info;

SELECT
    '총 api_scrap 레코드' as category,
    COUNT(*) as count
FROM announcement_pre_processing
WHERE site_type = 'api_scrap'

UNION ALL

SELECT
    '삭제 예정 (2025-10-30 이전)' as category,
    COUNT(*) as count
FROM announcement_pre_processing
WHERE site_type = 'api_scrap'
  AND (
    (LENGTH(announcement_date) = 8
     AND announcement_date REGEXP '^[0-9]{8}$'
     AND STR_TO_DATE(announcement_date, '%Y%m%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%.%.%'
     AND STR_TO_DATE(announcement_date, '%Y.%m.%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%-%-%'
     AND STR_TO_DATE(announcement_date, '%Y-%m-%d') < '2025-10-30')
  )

UNION ALL

SELECT
    '삭제 후 남을 데이터' as category,
    COUNT(*) as count
FROM announcement_pre_processing
WHERE site_type = 'api_scrap'
  AND NOT (
    (LENGTH(announcement_date) = 8
     AND announcement_date REGEXP '^[0-9]{8}$'
     AND STR_TO_DATE(announcement_date, '%Y%m%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%.%.%'
     AND STR_TO_DATE(announcement_date, '%Y.%m.%d') < '2025-10-30')
    OR
    (LENGTH(announcement_date) = 10
     AND announcement_date LIKE '%-%-%'
     AND STR_TO_DATE(announcement_date, '%Y-%m-%d') < '2025-10-30')
  );
