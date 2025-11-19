const mysql = require('mysql2/promise');
const { request } = require('undici');

// .env 로드
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

const CONFIG = {
    timeout: 10000,
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
};

async function checkSite(site) {
    const startTime = Date.now();

    try {
        const { statusCode, body } = await request(site.site_url, {
            method: 'GET',
            headersTimeout: CONFIG.timeout,
            bodyTimeout: CONFIG.timeout,
            headers: {
                'User-Agent': CONFIG.userAgent,
            },
        });

        const responseTime = Date.now() - startTime;
        await body.text().catch(() => {});

        return {
            site_code: site.site_code,
            site_url: site.site_url,
            old_error: site.error_type,
            old_message: site.error_message,
            new_status: statusCode,
            response_time: responseTime,
            is_success: statusCode >= 200 && statusCode < 300
        };

    } catch (error) {
        const responseTime = Date.now() - startTime;

        return {
            site_code: site.site_code,
            site_url: site.site_url,
            old_error: site.error_type,
            old_message: site.error_message,
            new_error: error.message,
            response_time: responseTime,
            is_success: false
        };
    }
}

async function main() {
    const pool = mysql.createPool({
        host: process.env.DB_HOST || '192.168.0.95',
        port: parseInt(process.env.DB_PORT || '3309'),
        user: process.env.DB_USER || 'root',
        password: process.env.DB_PASSWORD,
        database: process.env.DB_NAME || 'subvention',
    });

    try {
        console.log('='.repeat(100));
        console.log('SSL_ERROR 및 REDIRECT 에러 사이트 재검증');
        console.log('='.repeat(100) + '\n');

        // SSL_ERROR 사이트 조회
        console.log('📋 SSL_ERROR 사이트:\n');
        const [sslSites] = await pool.query(
            `SELECT DISTINCT l.site_code, s.site_url, l.error_type, l.error_message, l.check_date
             FROM health_check_log l
             JOIN scraper_site_url s ON l.site_code = s.site_code
             WHERE l.error_type = 'SSL_ERROR'
             ORDER BY l.check_date DESC
             LIMIT 10`
        );

        console.log(`총 ${sslSites.length}개 발견\n`);

        for (const site of sslSites) {
            const result = await checkSite(site);

            console.log(`Site: ${result.site_code}`);
            console.log(`URL: ${result.site_url}`);
            console.log(`이전 에러: ${result.old_error} - ${result.old_message}`);

            if (result.is_success) {
                console.log(`✅ undici 테스트: 정상 (${result.new_status}) - ${result.response_time}ms`);
            } else if (result.new_status) {
                console.log(`⚠️  undici 테스트: HTTP ${result.new_status} - ${result.response_time}ms`);
            } else {
                console.log(`❌ undici 테스트: ${result.new_error} - ${result.response_time}ms`);
            }

            console.log('-'.repeat(100));
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        // REDIRECT 사이트 조회
        console.log('\n📋 REDIRECT 에러 사이트:\n');
        const [redirectSites] = await pool.query(
            `SELECT DISTINCT l.site_code, s.site_url, l.error_type, l.error_message, l.status_code, l.check_date
             FROM health_check_log l
             JOIN scraper_site_url s ON l.site_code = s.site_code
             WHERE l.error_type = 'REDIRECT'
             ORDER BY l.check_date DESC
             LIMIT 10`
        );

        console.log(`총 ${redirectSites.length}개 발견\n`);

        for (const site of redirectSites) {
            const result = await checkSite(site);

            console.log(`Site: ${result.site_code}`);
            console.log(`URL: ${result.site_url}`);
            console.log(`이전 에러: ${result.old_error} - ${result.old_message}`);

            if (result.is_success) {
                console.log(`✅ undici 테스트: 정상 (${result.new_status}) - ${result.response_time}ms`);
                console.log(`   참고: undici는 자동으로 리다이렉트를 따라가므로 최종 페이지 상태를 반환합니다`);
            } else if (result.new_status) {
                console.log(`⚠️  undici 테스트: HTTP ${result.new_status} - ${result.response_time}ms`);
            } else {
                console.log(`❌ undici 테스트: ${result.new_error} - ${result.response_time}ms`);
            }

            console.log('-'.repeat(100));
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        console.log('\n✅ 검증 완료\n');

    } finally {
        await pool.end();
    }
}

main();
