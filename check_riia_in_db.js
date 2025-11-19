const mysql = require('mysql2/promise');
try {
    require('dotenv').config();
} catch (e) {
    // dotenv가 없으면 환경변수 직접 사용
}

async function checkRiiaInDb() {
    const pool = mysql.createPool({
        host: process.env.DB_HOST || '192.168.0.95',
        port: parseInt(process.env.DB_PORT || '3309'),
        user: process.env.DB_USER || 'root',
        password: process.env.DB_PASSWORD,
        database: process.env.DB_NAME || 'subvention',
        waitForConnections: true,
        connectionLimit: 10,
        queueLimit: 0,
    });

    try {
        const [rows] = await pool.query(
            "SELECT site_code, site_url, scraper_name FROM scraper_site_url WHERE site_url LIKE '%riia.or.kr%'"
        );

        console.log('RIIA 관련 사이트:');
        console.log('='.repeat(120));
        rows.forEach(row => {
            console.log(`Site Code: ${row.site_code}`);
            console.log(`URL: ${row.site_url}`);
            console.log(`Scraper: ${row.scraper_name}`);
            console.log('-'.repeat(120));
        });
        console.log(`\n총 ${rows.length}개 발견`);

        // 헬스체크 로그 확인
        const [logRows] = await pool.query(
            `SELECT check_date, site_code, status_code, error_type, error_message, response_time
             FROM health_check_log
             WHERE site_code IN (SELECT site_code FROM scraper_site_url WHERE site_url LIKE '%riia.or.kr%')
             ORDER BY check_date DESC
             LIMIT 10`
        );

        if (logRows.length > 0) {
            console.log('\n최근 헬스체크 로그:');
            console.log('='.repeat(120));
            logRows.forEach(log => {
                console.log(`날짜: ${log.check_date}, 코드: ${log.site_code}, 상태: ${log.status_code || 'N/A'}, 에러: ${log.error_type || 'N/A'}, 응답시간: ${log.response_time}ms`);
            });
        }

    } finally {
        await pool.end();
    }
}

checkRiiaInDb();
