const mysql = require('mysql2/promise');
const axios = require('axios');
const https = require('https');

// dotenv 로드
const path = require('path');
const fs = require('fs');
const envPath = path.join(__dirname, '.env');
if (fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, 'utf-8');
    envContent.split('\n').forEach(line => {
        const match = line.match(/^([^=]+)=(.*)$/);
        if (match) {
            process.env[match[1].trim()] = match[2].trim();
        }
    });
}

// SSL 인증서 검증 무시
const httpsAgent = new https.Agent({
    rejectUnauthorized: false,
});

async function checkRiia() {
    const pool = mysql.createPool({
        host: process.env.DB_HOST || '192.168.0.95',
        port: parseInt(process.env.DB_PORT || '3309'),
        user: process.env.DB_USER || 'root',
        password: process.env.DB_PASSWORD,
        database: process.env.DB_NAME || 'subvention',
    });

    try {
        // 1. DB에서 riia.or.kr 사이트 찾기
        console.log('='.repeat(100));
        console.log('RIIA 사이트 정보 조회');
        console.log('='.repeat(100) + '\n');

        const [sites] = await pool.query(
            "SELECT site_code, site_url, scraper_name FROM scraper_site_url WHERE site_url LIKE '%riia.or.kr%'"
        );

        if (sites.length === 0) {
            console.log('❌ riia.or.kr 사이트를 찾을 수 없습니다.');
            return;
        }

        console.log(`✅ ${sites.length}개 사이트 발견:\n`);
        sites.forEach(site => {
            console.log(`Site Code: ${site.site_code}`);
            console.log(`URL: ${site.site_url}`);
            console.log(`Scraper: ${site.scraper_name}`);
            console.log('-'.repeat(100));
        });

        // 2. 헬스체크 수행
        console.log('\n헬스체크 수행...\n');
        for (const site of sites) {
            const startTime = Date.now();
            try {
                const response = await axios.get(site.site_url, {
                    timeout: 10000,
                    maxRedirects: 5,
                    validateStatus: () => true,
                    httpsAgent: httpsAgent,
                    headers: {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    },
                });

                const responseTime = Date.now() - startTime;

                console.log(`Site: ${site.site_code}`);
                console.log(`URL: ${site.site_url}`);
                console.log(`상태 코드: ${response.status}`);
                console.log(`응답 시간: ${responseTime}ms`);

                if (response.status === 500) {
                    console.log('❌ 서버 오류 (500 Internal Server Error)');
                } else if (response.status >= 200 && response.status < 300) {
                    console.log('✅ 정상');
                } else {
                    console.log(`⚠️  비정상 상태: ${response.status}`);
                }

                console.log('-'.repeat(100) + '\n');

            } catch (error) {
                const responseTime = Date.now() - startTime;
                console.log(`Site: ${site.site_code}`);
                console.log(`❌ 오류: ${error.message}`);
                console.log(`응답 시간: ${responseTime}ms`);
                console.log('-'.repeat(100) + '\n');
            }
        }

        // 3. 헬스체크 로그 조회
        console.log('최근 헬스체크 로그:\n');
        const [logs] = await pool.query(
            `SELECT check_date, site_code, status_code, error_type, error_message, response_time
             FROM health_check_log
             WHERE site_code IN (SELECT site_code FROM scraper_site_url WHERE site_url LIKE '%riia.or.kr%')
             ORDER BY check_date DESC
             LIMIT 10`
        );

        if (logs.length > 0) {
            logs.forEach(log => {
                console.log(`날짜: ${log.check_date}`);
                console.log(`코드: ${log.site_code}`);
                console.log(`상태: ${log.status_code || 'N/A'}`);
                console.log(`에러: ${log.error_type || 'N/A'} - ${log.error_message || 'N/A'}`);
                console.log(`응답시간: ${log.response_time}ms`);
                console.log('-'.repeat(100));
            });
        } else {
            console.log('로그가 없습니다.');
        }

    } finally {
        await pool.end();
    }
}

checkRiia();
