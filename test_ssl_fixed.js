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
            // SSL 인증서 검증 비활성화
            tls: {
                rejectUnauthorized: false
            }
        });

        const responseTime = Date.now() - startTime;
        await body.text().catch(() => {});

        return {
            site_code: site.site_code,
            site_url: site.site_url,
            status: statusCode,
            response_time: responseTime,
            is_success: statusCode >= 200 && statusCode < 400
        };

    } catch (error) {
        const responseTime = Date.now() - startTime;

        return {
            site_code: site.site_code,
            site_url: site.site_url,
            error: error.message,
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
        console.log('SSL 검증 비활성화 후 재테스트');
        console.log('='.repeat(100) + '\n');

        // SSL_ERROR 사이트 조회 (5개만)
        const [sslSites] = await pool.query(
            `SELECT DISTINCT l.site_code, s.site_url
             FROM health_check_log l
             JOIN scraper_site_url s ON l.site_code = s.site_code
             WHERE l.error_type = 'SSL_ERROR'
             LIMIT 5`
        );

        console.log(`📋 SSL_ERROR 사이트 ${sslSites.length}개 테스트\n`);

        let successCount = 0;
        let failCount = 0;

        for (const site of sslSites) {
            const result = await checkSite(site);

            console.log(`Site: ${result.site_code}`);
            console.log(`URL: ${result.site_url}`);

            if (result.is_success) {
                console.log(`✅ 정상 (${result.status}) - ${result.response_time}ms`);
                successCount++;
            } else if (result.status) {
                console.log(`⚠️  HTTP ${result.status} - ${result.response_time}ms`);
                failCount++;
            } else {
                console.log(`❌ ${result.error} - ${result.response_time}ms`);
                failCount++;
            }

            console.log('-'.repeat(100));
            await new Promise(resolve => setTimeout(resolve, 300));
        }

        // REDIRECT 사이트 조회
        const [redirectSites] = await pool.query(
            `SELECT DISTINCT l.site_code, s.site_url
             FROM health_check_log l
             JOIN scraper_site_url s ON l.site_code = s.site_code
             WHERE l.error_type = 'REDIRECT'
             LIMIT 5`
        );

        console.log(`\n📋 REDIRECT 사이트 ${redirectSites.length}개 테스트\n`);

        for (const site of redirectSites) {
            const result = await checkSite(site);

            console.log(`Site: ${result.site_code}`);
            console.log(`URL: ${result.site_url}`);

            if (result.is_success) {
                console.log(`✅ 정상 (${result.status}) - ${result.response_time}ms`);
                successCount++;
            } else if (result.status) {
                console.log(`⚠️  HTTP ${result.status} - ${result.response_time}ms`);
                failCount++;
            } else {
                console.log(`❌ ${result.error} - ${result.response_time}ms`);
                failCount++;
            }

            console.log('-'.repeat(100));
            await new Promise(resolve => setTimeout(resolve, 300));
        }

        console.log('\n' + '='.repeat(100));
        console.log('📊 결과');
        console.log('='.repeat(100));
        console.log(`총 테스트: ${successCount + failCount}개`);
        console.log(`✅ 정상: ${successCount}개`);
        console.log(`❌ 실패: ${failCount}개`);
        console.log(`성공률: ${((successCount / (successCount + failCount)) * 100).toFixed(1)}%`);
        console.log('='.repeat(100));

    } finally {
        await pool.end();
    }
}

main();
