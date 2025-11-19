const mysql = require('mysql2/promise');
const { request, Agent } = require('undici');

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

// SSL 인증서 검증 비활성화
const httpsAgent = new Agent({
    connect: {
        rejectUnauthorized: false
    }
});

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
            dispatcher: httpsAgent
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
        console.log('최종 SSL + REDIRECT 수정 확인');
        console.log('='.repeat(100) + '\n');

        // 이전에 문제가 있던 사이트들
        const sslSiteCodes = ['cs', 'cwg', 'ganghwa', 'gbmg', 'gokseong'];
        const redirectSiteCodes = ['buan', 'gimje', 'seogu', 'uljin'];

        const allSiteCodes = [...sslSiteCodes, ...redirectSiteCodes];

        const [sites] = await pool.query(
            `SELECT site_code, site_url FROM scraper_site_url WHERE site_code IN (?)`,
            [allSiteCodes]
        );

        console.log(`총 ${sites.length}개 사이트 테스트\n`);

        let sslSuccess = 0;
        let sslFail = 0;
        let redirectSuccess = 0;
        let redirectFail = 0;

        for (const site of sites) {
            const result = await checkSite(site);
            const wasSSL = sslSiteCodes.includes(site.site_code);
            const wasRedirect = redirectSiteCodes.includes(site.site_code);

            console.log(`Site: ${result.site_code}`);
            console.log(`URL: ${result.site_url}`);
            if (wasSSL) console.log(`이전 문제: SSL_ERROR`);
            if (wasRedirect) console.log(`이전 문제: REDIRECT`);

            if (result.is_success) {
                console.log(`✅ 정상 (${result.status}) - ${result.response_time}ms`);
                if (wasSSL) sslSuccess++;
                if (wasRedirect) redirectSuccess++;
            } else if (result.status) {
                console.log(`⚠️  HTTP ${result.status} - ${result.response_time}ms`);
                if (wasSSL) sslFail++;
                if (wasRedirect) redirectFail++;
            } else {
                console.log(`❌ ${result.error} - ${result.response_time}ms`);
                if (wasSSL) sslFail++;
                if (wasRedirect) redirectFail++;
            }

            console.log('-'.repeat(100));
            await new Promise(resolve => setTimeout(resolve, 300));
        }

        console.log('\n' + '='.repeat(100));
        console.log('📊 최종 결과');
        console.log('='.repeat(100));
        console.log(`SSL_ERROR 수정: ${sslSuccess}/${sslSiteCodes.length}개 성공 (${((sslSuccess/sslSiteCodes.length)*100).toFixed(1)}%)`);
        console.log(`REDIRECT 수정: ${redirectSuccess}/${redirectSiteCodes.length}개 성공 (${((redirectSuccess/redirectSiteCodes.length)*100).toFixed(1)}%)`);
        console.log(`\n전체: ${sslSuccess + redirectSuccess}/${allSiteCodes.length}개 성공 (${(((sslSuccess + redirectSuccess)/allSiteCodes.length)*100).toFixed(1)}%)`);
        console.log('='.repeat(100));

    } finally {
        await pool.end();
    }
}

main();
