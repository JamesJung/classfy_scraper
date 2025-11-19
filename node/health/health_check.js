/**
 * 스크래퍼 사이트 헬스체크
 *
 * 기능:
 * 1. MySQL의 scraper_site_url 테이블에서 사이트 정보 읽기
 * 2. 각 사이트 URL에 대해 헬스체크 수행
 * 3. 문제가 있는 사이트는 health_check_log 테이블에 기록
 *
 * 체크 항목:
 * - HTTP 상태 코드 (200, 404, 403, 500 등)
 * - 응답 시간 (타임아웃)
 * - 리다이렉트 감지
 * - 연결 오류 (DNS, SSL 등)
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

// 설정
const CONFIG = {
    timeout: 30000, // 30초 타임아웃 (정부 사이트는 느린 경우가 많음)
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    concurrency: 5, // 동시 실행 수
};

// 상태 코드 분류
const STATUS_CODES = {
    SUCCESS: [200, 201],
    REDIRECT: [301, 302, 303, 307, 308],
    CLIENT_ERROR: [400, 401, 403, 404, 405, 406, 407, 408, 409, 410],
    SERVER_ERROR: [500, 501, 502, 503, 504, 505],
};

/**
 * MySQL 연결 풀 생성
 */
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

/**
 * health_check_log 테이블 생성
 */
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

    try {
        await pool.query(createTableQuery);
        console.log('✅ health_check_log 테이블 생성/확인 완료');
    } catch (error) {
        console.error('❌ health_check_log 테이블 생성 실패:', error.message);
        throw error;
    }
}

/**
 * health_check_summary 테이블 생성
 */
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

    try {
        await pool.query(createTableQuery);
        console.log('✅ health_check_summary 테이블 생성/확인 완료');
    } catch (error) {
        console.error('❌ health_check_summary 테이블 생성 실패:', error.message);
        throw error;
    }
}

/**
 * scraper_site_url에서 사이트 목록 가져오기
 */
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
    `;

    try {
        const [rows] = await pool.query(query);
        console.log(`✅ ${rows.length}개 사이트 정보 로드 완료`);
        return rows;
    } catch (error) {
        console.error('❌ 사이트 목록 조회 실패:', error.message);
        throw error;
    }
}

/**
 * 단일 사이트 헬스체크
 */
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

        // 상태 코드별 처리
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
        } else {
            result.is_healthy = false;
            result.error_type = 'UNKNOWN_STATUS';
            result.error_message = `알 수 없는 상태 코드: ${statusCode}`;
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
            result.error_message = 'DNS 조회 실패 (도메인을 찾을 수 없음)';
        } else if (error.code === 'ECONNREFUSED') {
            result.error_type = 'CONNECTION_REFUSED';
            result.error_message = '연결 거부됨';
        } else if (error.code === 'UND_ERR_CONNECT_TIMEOUT' || error.code === 'UND_ERR_HEADERS_TIMEOUT' || error.code === 'UND_ERR_BODY_TIMEOUT') {
            result.error_type = 'TIMEOUT';
            result.error_message = `연결 타임아웃 (${CONFIG.timeout}ms)`;
        } else if (error.code === 'ETIMEDOUT' || error.code === 'ECONNABORTED') {
            result.error_type = 'TIMEOUT';
            result.error_message = `연결 타임아웃 (${CONFIG.timeout}ms)`;
        } else if (error.code === 'CERT_HAS_EXPIRED' || error.message.includes('certificate')) {
            result.error_type = 'SSL_ERROR';
            result.error_message = 'SSL/TLS 인증서 오류';
        } else if (error.code === 'ERR_TLS_CERT_ALTNAME_INVALID') {
            result.error_type = 'SSL_ERROR';
            result.error_message = 'SSL 인증서 도메인 불일치';
        } else {
            result.error_type = 'NETWORK_ERROR';
            result.error_message = error.message || '네트워크 오류';
        }
    }

    return result;
}

/**
 * 헬스체크 결과 로그 저장 (UPSERT)
 */
async function saveHealthCheckLog(pool, checkDate, result) {
    // 정상인 경우 로그 저장 안 함
    if (result.is_healthy) {
        return;
    }

    // UPSERT 쿼리: check_date와 site_code가 동일하면 업데이트, 없으면 삽입
    const upsertQuery = `
        INSERT INTO health_check_log (
            check_date,
            site_code,
            site_url,
            status_code,
            error_type,
            error_message,
            response_time,
            redirect_url,
            redirect_count
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

    try {
        await pool.query(upsertQuery, [
            checkDate,
            result.site_code,
            result.site_url,
            result.status_code,
            result.error_type,
            result.error_message,
            result.response_time,
            result.redirect_url,
            result.redirect_count,
        ]);
    } catch (error) {
        console.error(`❌ 로그 저장 실패 (${result.site_code}):`, error.message);
    }
}

/**
 * 배치로 사이트 헬스체크 수행
 */
async function checkSitesInBatch(pool, sites, checkDate) {
    const results = {
        total: sites.length,
        healthy: 0,
        unhealthy: 0,
        errors: [],
        responseTimes: [], // 평균 응답시간 계산용
    };

    console.log(`\n📊 총 ${sites.length}개 사이트 헬스체크 시작...`);
    console.log(`동시 실행 수: ${CONFIG.concurrency}\n`);

    // 배치 처리
    for (let i = 0; i < sites.length; i += CONFIG.concurrency) {
        const batch = sites.slice(i, i + CONFIG.concurrency);
        const batchNumber = Math.floor(i / CONFIG.concurrency) + 1;
        const totalBatches = Math.ceil(sites.length / CONFIG.concurrency);

        console.log(`[배치 ${batchNumber}/${totalBatches}] ${batch.length}개 사이트 체크 중...`);

        const promises = batch.map(site => checkSiteHealth(site));
        const batchResults = await Promise.all(promises);

        // 결과 처리
        for (const result of batchResults) {
            // 응답시간 수집
            if (result.response_time) {
                results.responseTimes.push(result.response_time);
            }

            if (result.is_healthy) {
                results.healthy++;
                console.log(`  ✅ ${result.site_code}: 정상 (${result.response_time}ms)`);
            } else {
                results.unhealthy++;
                results.errors.push(result);
                console.log(`  ❌ ${result.site_code}: ${result.error_type} - ${result.error_message}`);

                // DB에 로그 저장
                await saveHealthCheckLog(pool, checkDate, result);
            }
        }

        // 다음 배치 전 짧은 대기
        if (i + CONFIG.concurrency < sites.length) {
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
    }

    return results;
}

/**
 * 헬스체크 요약 저장
 */
async function saveHealthCheckSummary(pool, checkDate, results) {
    // 평균 응답시간 계산
    const avgResponseTime = results.responseTimes.length > 0
        ? Math.round(results.responseTimes.reduce((a, b) => a + b, 0) / results.responseTimes.length)
        : null;

    const upsertQuery = `
        INSERT INTO health_check_summary (
            check_date,
            total_count,
            success_count,
            failure_count,
            avg_response_time
        ) VALUES (?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
            total_count = VALUES(total_count),
            success_count = VALUES(success_count),
            failure_count = VALUES(failure_count),
            avg_response_time = VALUES(avg_response_time),
            updated_at = CURRENT_TIMESTAMP
    `;

    try {
        await pool.query(upsertQuery, [
            checkDate,
            results.total,
            results.healthy,
            results.unhealthy,
            avgResponseTime,
        ]);
        console.log(`\n✅ 요약 정보 저장 완료 (성공: ${results.healthy}, 실패: ${results.unhealthy}, 평균응답: ${avgResponseTime}ms)`);
    } catch (error) {
        console.error('❌ 요약 정보 저장 실패:', error.message);
    }
}

/**
 * 헬스체크 요약 출력
 */
function printSummary(results, duration) {
    console.log('\n' + '='.repeat(80));
    console.log('📊 헬스체크 결과 요약');
    console.log('='.repeat(80));
    console.log(`총 사이트 수:     ${results.total}개`);
    console.log(`정상:            ${results.healthy}개 (${(results.healthy / results.total * 100).toFixed(1)}%)`);
    console.log(`문제 있음:        ${results.unhealthy}개 (${(results.unhealthy / results.total * 100).toFixed(1)}%)`);
    console.log(`소요 시간:        ${(duration / 1000).toFixed(1)}초`);
    console.log('='.repeat(80));

    if (results.unhealthy > 0) {
        console.log('\n⚠️  문제가 있는 사이트 목록:');
        console.log('-'.repeat(80));

        // 오류 타입별 그룹화
        const errorsByType = {};
        results.errors.forEach(error => {
            if (!errorsByType[error.error_type]) {
                errorsByType[error.error_type] = [];
            }
            errorsByType[error.error_type].push(error);
        });

        Object.keys(errorsByType).forEach(errorType => {
            console.log(`\n[${errorType}] ${errorsByType[errorType].length}개`);
            errorsByType[errorType].forEach(error => {
                console.log(`  - ${error.site_code}: ${error.site_url}`);
                console.log(`    ${error.error_message}`);
            });
        });
    }
}

/**
 * 메인 함수
 */
async function main() {
    const startTime = Date.now();
    const now = new Date();
    const checkDate = now.toISOString().split('T')[0]; // YYYY-MM-DD 형식

    console.log('='.repeat(80));
    console.log('🏥 스크래퍼 사이트 헬스체크 시작');
    console.log('='.repeat(80));
    console.log(`체크 시간: ${now.toLocaleString('ko-KR')}`);
    console.log(`체크 날짜: ${checkDate}`);
    console.log(`타임아웃: ${CONFIG.timeout}ms`);
    console.log(`SSL 검증: 비활성화 (브라우저와 동일)`);
    console.log('='.repeat(80));

    let pool;

    try {
        // MySQL 연결
        pool = createPool();
        console.log('✅ MySQL 연결 완료');

        // 테이블 생성
        await createHealthCheckLogTable(pool);
        await createHealthCheckSummaryTable(pool);

        // 사이트 목록 가져오기
        const sites = await getSiteList(pool);

        if (sites.length === 0) {
            console.log('⚠️  체크할 사이트가 없습니다.');
            return;
        }

        // 헬스체크 수행
        const results = await checkSitesInBatch(pool, sites, checkDate);

        // 요약 정보 저장
        await saveHealthCheckSummary(pool, checkDate, results);

        // 결과 요약
        const duration = Date.now() - startTime;
        printSummary(results, duration);

        console.log('\n✅ 헬스체크 완료');

    } catch (error) {
        console.error('\n❌ 헬스체크 실행 중 오류 발생:', error);
        process.exit(1);
    } finally {
        if (pool) {
            await pool.end();
            console.log('✅ MySQL 연결 종료');
        }
    }
}

// 스크립트 실행
if (require.main === module) {
    main().catch(error => {
        console.error('❌ 치명적 오류:', error);
        process.exit(1);
    });
}

module.exports = {
    checkSiteHealth,
    createHealthCheckLogTable,
};
