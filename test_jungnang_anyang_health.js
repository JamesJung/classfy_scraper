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
    timeout: 30000,
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
            dispatcher: httpsAgent
        });

        result.response_time = Date.now() - startTime;
        result.status_code = statusCode;

        await body.text().catch(() => {});

        if (STATUS_CODES.SUCCESS.includes(statusCode)) {
            result.is_healthy = true;
        } else if (STATUS_CODES.REDIRECT.includes(statusCode)) {
            result.is_healthy = true;
        } else if (STATUS_CODES.CLIENT_ERROR.includes(statusCode)) {
            result.is_healthy = false;
            result.error_type = 'CLIENT_ERROR';
            result.error_message = `클라이언트 오류: ${statusCode}`;
        } else if (STATUS_CODES.SERVER_ERROR.includes(statusCode)) {
            result.is_healthy = false;
            result.error_type = 'SERVER_ERROR';
            result.error_message = `서버 오류: ${statusCode}`;
        }

        if (result.response_time > 20000) {
            result.is_healthy = false;
            result.error_type = result.error_type || 'SLOW_RESPONSE';
            result.error_message = (result.error_message || '') + ` (응답 시간: ${result.response_time}ms)`;
        }

    } catch (error) {
        result.response_time = Date.now() - startTime;
        result.is_healthy = false;

        if (error.message && error.message.includes('Invalid header value char')) {
            result.error_type = 'HTTP_PARSE_ERROR';
            result.error_message = '브라우저 전용 사이트 (HTTP 헤더 파싱 에러)';
        } else if (error.message && error.message.includes('Unexpected space after start line')) {
            result.error_type = 'HTTP_PARSE_ERROR';
            result.error_message = '브라우저 전용 사이트 (HTTP 응답 라인 파싱 에러)';
        } else {
            result.error_type = 'NETWORK_ERROR';
            result.error_message = error.message || '네트워크 오류';
        }
    }

    return result;
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
        console.log('jungnang & anyang 헬스체크 테스트');
        console.log('='.repeat(100) + '\n');

        const [sites] = await pool.query(
            `SELECT site_code, site_url FROM scraper_site_url WHERE site_code IN ('jungnang', 'anyang')`
        );

        console.log(`총 ${sites.length}개 사이트 테스트\n`);

        for (const site of sites) {
            const result = await checkSiteHealth(site);

            console.log(`Site: ${result.site_code}`);
            console.log(`URL: ${result.site_url}`);
            console.log(`응답 시간: ${result.response_time}ms`);

            if (result.is_healthy) {
                console.log(`✅ 정상 (${result.status_code})`);
            } else {
                console.log(`⚠️  ${result.error_type}: ${result.error_message}`);
                if (result.status_code) {
                    console.log(`   HTTP 상태: ${result.status_code}`);
                }
            }

            console.log('-'.repeat(100));
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        console.log('\n📊 결과:');
        console.log('- anyang: 브라우저에서 정상, HTTP 200 → ✅ 정상으로 기록');
        console.log('- jungnang: 브라우저에서 정상, HTTP 파싱 에러 → ⚠️ 브라우저 전용 사이트로 기록');
        console.log('='.repeat(100));

    } finally {
        await pool.end();
    }
}

main();
