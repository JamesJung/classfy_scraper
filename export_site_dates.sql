-- eminwon_site_announcement_date 테이블 데이터를 JSON 형태로 추출
SELECT 
    JSON_OBJECT(
        'site_code', site_code,
        'host_url', host_url, 
        'latest_announcement_date', latest_announcement_date,
        'last_updated', last_updated
    ) as site_info
FROM eminwon_site_announcement_date 
ORDER BY site_code;