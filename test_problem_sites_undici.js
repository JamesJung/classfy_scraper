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

const STATUS_CODES = {
    SUCCESS: [200, 201],
    REDIRECT: [301, 302, 303, 307, 308],
    CLIENT_ERROR: [400, 401, 403, 404, 405, 406, 407, 408, 409, 410],
    SERVER_ERROR: [500, 501, 502, 503, 504, 505],
};

async function checkSiteHealth(site) {
    const startTime = Date.now();
    const result = {
        site_code: site.site_code,
        site_url: site.site_url,
        status_code: null,
        error_type: null,
        error_message: null,
        response_time: null,
        is_healthy: true,
    };

    try {
        const { statusCode, body } = await request(site.site_url, {
            method: 'GET',
            headersTimeout: CONFIG.timeout,
            bodyTimeout: CONFIG.timeout,
            headers: {
                'User-Agent': CONFIG.userAgent,
            },
        });

        result.response_time = Date.now() - startTime;
        result.status_code = statusCode;

        await body.text().catch(() => {});

        if (STATUS_CODES.SUCCESS.includes(statusCode)) {
            result.is_healthy = true;
        } else if (STATUS_CODES.SERVER_ERROR.includes(statusCode)) {
            result.is_healthy = false;
            result.error_type = 'SERVER_ERROR';
            result.error_message = `서버 오류: ${statusCode}`;
        } else {
            result.is_healthy = false;
            result.error_type = 'OTHER_ERROR';
            result.error_message = `상태 코드: ${statusCode}`;
        }

    } catch (error) {
        result.response_time = Date.now() - startTime;
        result.is_healthy = false;

        if (error.message && error.message.includes('Invalid header value char')) {
            result.error_type = 'HTTP_PARSE_ERROR';
            result.error_message = 'HTTP 헤더 파싱 에러 (브라우저 전용 사이트)';
        } else if (error.message && error.message.includes('Unexpected space after start line')) {
            result.error_type = 'HTTP_PARSE_ERROR';
            result.error_message = 'HTTP 응답 라인 파싱 에러 (브라우저 전용 사이트)';
        } else {
            result.error_type = 'NETWORK_ERROR';
            result.error_message = error.message || '네트워크 오류';
        }
    }

    return result;
}

async function testProblemSites() {
    const pool = mysql.createPool({
        host: process.env.DB_HOST || '192.168.0.95',
        port: parseInt(process.env.DB_PORT || '3309'),
        user: process.env.DB_USER || 'root',
        password: process.env.DB_PASSWORD,
        database: process.env.DB_NAME || 'subvention',
    });

    try {
        console.log('='.repeat(100));
        console.log('문제 사이트 undici 테스트');
        console.log('='.repeat(100) + '\n');

        // 문제가 있던 사이트 코드들
        const problemSiteCodes = ['haman', 'jungnang', 'shinan', 'kohi', 'gwba', 'sjria'];

        const [sites] = await pool.query(
            `SELECT site_code, site_url FROM scraper_site_url WHERE site_code IN (?)`,
            [problemSiteCodes]
        );

        console.log(`총 ${sites.length}개 문제 사이트 테스트\n`);

        for (const site of sites) {
            const result = await checkSiteHealth(site);

            console.log(`Site: ${result.site_code}`);
            console.log(`URL: ${result.site_url}`);
            console.log(`응답 시간: ${result.response_time}ms`);

            if (result.is_healthy) {
                console.log(`✅ 정상 (${result.status_code})`);
            } else {
                console.log(`❌ ${result.error_type}: ${result.error_message}`);
                if (result.status_code) {
                    console.log(`   상태 코드: ${result.status_code}`);
                }
            }

            console.log('-'.repeat(100));
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        console.log('\n✅ 테스트 완료\n');

    } finally {
        await pool.end();
    }
}

testProblemSites();
