/**
 * 헬스체크 테스트 스크립트 (처음 10개 사이트만)
 */

const mysql = require('mysql2/promise');
const { request, Agent } = require('undici');
require('dotenv').config();

// SSL 인증서 검증 비활성화를 위한 Agent 생성 (브라우저와 동일한 동작)
const httpsAgent = new Agent({
    connect: {
        rejectUnauthorized: false
    }
});

const CONFIG = {
    timeout: 30000, // 30초 타임아웃 (정부 사이트는 느린 경우가 많음)
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    concurrency: 3,
    testLimit: 10, // 테스트용: 처음 10개만
};

const STATUS_CODES = {
    SUCCESS: [200, 201],
    REDIRECT: [301, 302, 303, 307, 308],
    CLIENT_ERROR: [400, 401, 403, 404, 405, 406, 407, 408, 409, 410],
    SERVER_ERROR: [500, 501, 502, 503, 504, 505],
};

function createPool() {
    return mysql.createPool({
        host: process.env.DB_HOST || '192.168.0.95',
        port: parseInt(process.env.DB_PORT || '3309'),
        user: process.env.DB_USER || 'root',
        password: process.env.DB_PASSWORD,
        database: process.env.DB_NAME || 'subvention',
        waitForConnections: true,
        connectionLimit: 10,
        queueLimit: 0,
    });
}

async function createHealthCheckLogTable(pool) {
    const createTableQuery = `
        CREATE TABLE IF NOT EXISTS health_check_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            check_date DATE NOT NULL,
            site_code VARCHAR(100) NOT NULL,
            site_url VARCHAR(1000) NOT NULL,
            status_code INT,
            error_type VARCHAR(100),
            error_message TEXT,
            response_time INT COMMENT '응답시간(ms)',
            redirect_url VARCHAR(1000) COMMENT '리다이렉트된 URL',
            redirect_count INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY unique_check (check_date, site_code),
            INDEX idx_check_date (check_date),
            INDEX idx_site_code (site_code),
            INDEX idx_status_code (status_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        COMMENT='스크래퍼 사이트 헬스체크 로그'
    `;

    await pool.query(createTableQuery);
    console.log('✅ health_check_log 테이블 생성/확인 완료');
}

async function createHealthCheckSummaryTable(pool) {
    const createTableQuery = `
        CREATE TABLE IF NOT EXISTS health_check_summary (
            id INT AUTO_INCREMENT PRIMARY KEY,
            check_date DATE NOT NULL,
            total_count INT NOT NULL DEFAULT 0 COMMENT '총 체크 사이트 수',
            success_count INT NOT NULL DEFAULT 0 COMMENT '성공 건수',
            failure_count INT NOT NULL DEFAULT 0 COMMENT '실패 건수',
            avg_response_time INT COMMENT '평균 응답시간(ms)',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY unique_date (check_date),
            INDEX idx_check_date (check_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        COMMENT='헬스체크 일별 요약'
    `;

    await pool.query(createTableQuery);
    console.log('✅ health_check_summary 테이블 생성/확인 완료');
}

async function getSiteList(pool) {
    const query = `
        SELECT
            id,
            site_code,
            site_url,
            scraper_name
        FROM scraper_site_url
        WHERE site_url IS NOT NULL
        AND site_url != ''
        ORDER BY id
        LIMIT ${CONFIG.testLimit}
    `;

    const [rows] = await pool.query(query);
    console.log(`✅ ${rows.length}개 사이트 정보 로드 완료 (테스트 모드)`);
    return rows;
}

async function checkSiteHealth(site) {
    const startTime = Date.now();
    const result = {
        site_code: site.site_code,
        site_url: site.site_url,
        status_code: null,
        error_type: null,
        error_message: null,
        response_time: null,
        redirect_url: null,
        redirect_count: 0,
        is_healthy: true,
    };

    try {
        const { statusCode, headers, body } = await request(site.site_url, {
            method: 'GET',
            headersTimeout: CONFIG.timeout,
            bodyTimeout: CONFIG.timeout,
            headers: {
                'User-Agent': CONFIG.userAgent,
            },
            // SSL 인증서 검증 비활성화 (브라우저와 동일한 동작)
            dispatcher: httpsAgent
        });

        result.response_time = Date.now() - startTime;
        result.status_code = statusCode;

        // Body 소비 (메모리 누수 방지)
        await body.text().catch(() => {});

        if (STATUS_CODES.SUCCESS.includes(statusCode)) {
            result.is_healthy = true;
        } else if (STATUS_CODES.REDIRECT.includes(statusCode)) {
            // undici는 자동으로 리다이렉트를 따라가므로 3xx는 정상으로 처리
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

        // 응답 시간 체크 (20초 이상이면 느린 것으로 간주)
        if (result.response_time > 20000) {
            result.is_healthy = false;
            result.error_type = result.error_type || 'SLOW_RESPONSE';
            result.error_message = (result.error_message || '') + ` (응답 시간: ${result.response_time}ms)`;
        }

    } catch (error) {
        result.response_time = Date.now() - startTime;
        result.is_healthy = false;

        // HTTP 파싱 에러 처리 (브라우저에서는 정상 작동하는 사이트)
        if (error.message && error.message.includes('Invalid header value char')) {
            result.error_type = 'HTTP_PARSE_ERROR';
            result.error_message = '브라우저 전용 사이트 (HTTP 헤더 파싱 에러)';
        } else if (error.message && error.message.includes('Unexpected space after start line')) {
            result.error_type = 'HTTP_PARSE_ERROR';
            result.error_message = '브라우저 전용 사이트 (HTTP 응답 라인 파싱 에러)';
        } else if (error.code === 'ENOTFOUND') {
            result.error_type = 'DNS_ERROR';
            result.error_message = 'DNS 조회 실패';
        } else if (error.code === 'ECONNREFUSED') {
            result.error_type = 'CONNECTION_REFUSED';
            result.error_message = '연결 거부됨';
        } else if (error.code === 'UND_ERR_CONNECT_TIMEOUT' || error.code === 'UND_ERR_HEADERS_TIMEOUT' || error.code === 'UND_ERR_BODY_TIMEOUT') {
            result.error_type = 'TIMEOUT';
            result.error_message = `타임아웃 (${CONFIG.timeout}ms)`;
        } else if (error.code === 'ETIMEDOUT' || error.code === 'ECONNABORTED') {
            result.error_type = 'TIMEOUT';
            result.error_message = `타임아웃 (${CONFIG.timeout}ms)`;
        } else if (error.code === 'CERT_HAS_EXPIRED' || error.message.includes('certificate')) {
            result.error_type = 'SSL_ERROR';
            result.error_message = 'SSL/TLS 인증서 오류';
        } else {
            result.error_type = 'NETWORK_ERROR';
            result.error_message = error.message || '네트워크 오류';
        }
    }

    return result;
}

async function saveHealthCheckLog(pool, checkDate, result) {
    if (result.is_healthy) return;

    const upsertQuery = `
        INSERT INTO health_check_log (
            check_date, site_code, site_url, status_code,
            error_type, error_message, response_time,
            redirect_url, redirect_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
            site_url = VALUES(site_url),
            status_code = VALUES(status_code),
            error_type = VALUES(error_type),
            error_message = VALUES(error_message),
            response_time = VALUES(response_time),
            redirect_url = VALUES(redirect_url),
            redirect_count = VALUES(redirect_count),
            updated_at = CURRENT_TIMESTAMP
    `;

    await pool.query(upsertQuery, [
        checkDate, result.site_code, result.site_url, result.status_code,
        result.error_type, result.error_message, result.response_time,
        result.redirect_url, result.redirect_count,
    ]);
}

async function main() {
    const startTime = Date.now();
    const now = new Date();
    const checkDate = now.toISOString().split('T')[0]; // YYYY-MM-DD

    console.log('='.repeat(80));
    console.log('🏥 스크래퍼 사이트 헬스체크 (테스트 모드)');
    console.log('='.repeat(80));
    console.log(`체크 시간: ${now.toLocaleString('ko-KR')}`);
    console.log(`체크 날짜: ${checkDate}`);
    console.log(`테스트 사이트 수: ${CONFIG.testLimit}개`);
    console.log(`SSL 검증: 비활성화 (브라우저와 동일)`);
    console.log('='.repeat(80) + '\n');

    const pool = createPool();

    try {
        await createHealthCheckLogTable(pool);
        await createHealthCheckSummaryTable(pool);
        const sites = await getSiteList(pool);

        console.log('\n헬스체크 시작...\n');

        const results = {
            total: sites.length,
            healthy: 0,
            unhealthy: 0,
            errors: [],
            responseTimes: []
        };

        for (const site of sites) {
            const result = await checkSiteHealth(site);

            if (result.response_time) {
                results.responseTimes.push(result.response_time);
            }

            if (result.is_healthy) {
                results.healthy++;
                console.log(`✅ ${result.site_code}: 정상 (${result.response_time}ms)`);
            } else {
                results.unhealthy++;
                results.errors.push(result);
                console.log(`❌ ${result.site_code}: ${result.error_type} - ${result.error_message}`);
                await saveHealthCheckLog(pool, checkDate, result);
            }

            await new Promise(resolve => setTimeout(resolve, 500));
        }

        // 요약 정보 저장
        const avgResponseTime = results.responseTimes.length > 0
            ? Math.round(results.responseTimes.reduce((a, b) => a + b, 0) / results.responseTimes.length)
            : null;

        const summaryQuery = `
            INSERT INTO health_check_summary (
                check_date, total_count, success_count, failure_count, avg_response_time
            ) VALUES (?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                total_count = VALUES(total_count),
                success_count = VALUES(success_count),
                failure_count = VALUES(failure_count),
                avg_response_time = VALUES(avg_response_time),
                updated_at = CURRENT_TIMESTAMP
        `;
        await pool.query(summaryQuery, [
            checkDate, results.total, results.healthy, results.unhealthy, avgResponseTime
        ]);

        const duration = Date.now() - startTime;

        console.log('\n' + '='.repeat(80));
        console.log('📊 테스트 결과');
        console.log('='.repeat(80));
        console.log(`총 사이트:   ${results.total}개`);
        console.log(`정상:        ${results.healthy}개`);
        console.log(`문제 있음:   ${results.unhealthy}개`);
        console.log(`평균 응답:   ${avgResponseTime}ms`);
        console.log(`소요 시간:   ${(duration / 1000).toFixed(1)}초`);
        console.log('='.repeat(80));

        if (results.unhealthy > 0) {
            console.log('\n⚠️  문제가 있는 사이트:');
            results.errors.forEach(error => {
                console.log(`  - ${error.site_code}: ${error.error_message}`);
            });
        }

        console.log('\n✅ 테스트 완료');

    } finally {
        await pool.end();
    }
}

main().catch(console.error);
