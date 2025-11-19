/**
 * Playwright를 사용한 스크래퍼 사이트 헬스체크
 *
 * 기능:
 * 1. HTTP 파싱 에러가 발생하는 사이트들을 실제 브라우저로 체크
 * 2. 일반 HTTP 클라이언트로 접근 불가능한 사이트 검증
 * 3. JavaScript 렌더링이 필요한 SPA 사이트 체크
 */

const mysql = require('mysql2/promise');
const { chromium } = require('playwright');
require('dotenv').config();

// 설정
const CONFIG = {
    timeout: 30000, // 30초 타임아웃
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    concurrency: 3, // 동시 실행 수 (브라우저는 리소스를 많이 사용하므로 적게)
    headless: true, // headless 모드
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
 * HTTP_PARSE_ERROR가 발생한 사이트 목록 가져오기
 */
async function getHttpParseErrorSites(pool) {
    const query = `
        SELECT DISTINCT s.site_code, s.site_url, s.scraper_name
        FROM scraper_site_url s
        LEFT JOIN health_check_log l ON s.site_code = l.site_code
            AND l.check_date = CURDATE()
            AND l.error_type = 'HTTP_PARSE_ERROR'
        WHERE l.id IS NOT NULL
        ORDER BY s.site_code
    `;

    try {
        const [rows] = await pool.query(query);
        console.log(`✅ ${rows.length}개 HTTP_PARSE_ERROR 사이트 로드 완료`);
        return rows;
    } catch (error) {
        console.error('❌ 사이트 목록 조회 실패:', error.message);
        throw error;
    }
}

/**
 * 모든 사이트 목록 가져오기 (전체 체크용)
 */
async function getAllSites(pool) {
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
 * Playwright로 단일 사이트 헬스체크
 */
async function checkSiteHealthWithPlaywright(browser, site) {
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

    let page = null;

    try {
        // 새 페이지 생성
        page = await browser.newPage({
            userAgent: CONFIG.userAgent,
            ignoreHTTPSErrors: true, // SSL 인증서 검증 비활성화
        });

        // 타임아웃 설정
        page.setDefaultTimeout(CONFIG.timeout);

        // 페이지 로드
        const response = await page.goto(site.site_url, {
            waitUntil: 'domcontentloaded', // DOM이 로드되면 완료
            timeout: CONFIG.timeout,
        });

        result.response_time = Date.now() - startTime;

        if (response) {
            result.status_code = response.status();

            // 상태 코드별 처리
            if (STATUS_CODES.SUCCESS.includes(result.status_code)) {
                result.is_healthy = true;
            } else if (STATUS_CODES.REDIRECT.includes(result.status_code)) {
                // Playwright는 자동으로 리다이렉트를 따라가므로 정상
                result.is_healthy = true;
            } else if (STATUS_CODES.CLIENT_ERROR.includes(result.status_code)) {
                result.is_healthy = false;
                result.error_type = 'CLIENT_ERROR';
                result.error_message = `클라이언트 오류: ${result.status_code}`;
            } else if (STATUS_CODES.SERVER_ERROR.includes(result.status_code)) {
                result.is_healthy = false;
                result.error_type = 'SERVER_ERROR';
                result.error_message = `서버 오류: ${result.status_code}`;
            }

            // 응답 시간 체크
            if (result.response_time > 20000) {
                result.is_healthy = false;
                result.error_type = result.error_type || 'SLOW_RESPONSE';
                result.error_message = (result.error_message || '') + ` (응답 시간: ${result.response_time}ms)`;
            }

            // 에러 페이지 감지 (페이지 내용 확인)
            try {
                const pageTitle = await page.title();
                const pageContent = await page.content();

                if (pageTitle.toLowerCase().includes('error') ||
                    pageTitle.includes('오류') ||
                    pageContent.includes('error-code') ||
                    pageContent.includes('오류 코드')) {

                    // 하지만 200이면 일부 내용만 에러일 수 있으므로 경고만
                    if (result.status_code === 200) {
                        console.log(`    ⚠️  페이지에 에러 내용 포함 (제목: ${pageTitle})`);
                    }
                }
            } catch (e) {
                // 페이지 내용 확인 실패는 무시
            }

        } else {
            result.is_healthy = false;
            result.error_type = 'NO_RESPONSE';
            result.error_message = '응답 없음';
        }

    } catch (error) {
        result.response_time = Date.now() - startTime;
        result.is_healthy = false;

        // 오류 타입 분류
        if (error.message.includes('Timeout') || error.message.includes('timeout')) {
            result.error_type = 'TIMEOUT';
            result.error_message = `연결 타임아웃 (${CONFIG.timeout}ms)`;
        } else if (error.message.includes('net::ERR_NAME_NOT_RESOLVED')) {
            result.error_type = 'DNS_ERROR';
            result.error_message = 'DNS 조회 실패';
        } else if (error.message.includes('net::ERR_CONNECTION_REFUSED')) {
            result.error_type = 'CONNECTION_REFUSED';
            result.error_message = '연결 거부됨';
        } else if (error.message.includes('net::ERR_CERT')) {
            result.error_type = 'SSL_ERROR';
            result.error_message = 'SSL/TLS 인증서 오류';
        } else {
            result.error_type = 'BROWSER_ERROR';
            result.error_message = error.message || '브라우저 오류';
        }
    } finally {
        // 페이지 닫기
        if (page) {
            try {
                await page.close();
            } catch (e) {
                // 페이지 닫기 실패 무시
            }
        }
    }

    return result;
}

/**
 * 헬스체크 결과 로그 저장 (UPSERT)
 */
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

    try {
        await pool.query(upsertQuery, [
            checkDate, result.site_code, result.site_url, result.status_code,
            result.error_type, result.error_message, result.response_time,
            null, 0,
        ]);
    } catch (error) {
        console.error(`❌ 로그 저장 실패 (${result.site_code}):`, error.message);
    }
}

/**
 * 헬스체크 요약 저장 (UPSERT)
 */
async function saveHealthCheckSummary(pool, checkDate, results) {
    const avgResponseTime = results.responseTimes.length > 0
        ? Math.round(results.responseTimes.reduce((a, b) => a + b, 0) / results.responseTimes.length)
        : null;

    const upsertQuery = `
        INSERT INTO health_check_summary (
            check_date, total_count, success_count, failure_count, avg_response_time
        ) VALUES (?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
            total_count = total_count + VALUES(total_count),
            success_count = success_count + VALUES(success_count),
            failure_count = failure_count + VALUES(failure_count),
            avg_response_time = (avg_response_time + VALUES(avg_response_time)) / 2,
            updated_at = CURRENT_TIMESTAMP
    `;

    try {
        await pool.query(upsertQuery, [
            checkDate, results.total, results.healthy, results.unhealthy, avgResponseTime
        ]);
    } catch (error) {
        console.error('❌ 요약 저장 실패:', error.message);
    }
}

/**
 * 배치로 사이트 체크
 */
async function checkSitesInBatch(browser, sites, pool, checkDate, results) {
    for (let i = 0; i < sites.length; i += CONFIG.concurrency) {
        const batch = sites.slice(i, i + CONFIG.concurrency);
        const batchResults = await Promise.all(
            batch.map(site => checkSiteHealthWithPlaywright(browser, site))
        );

        for (const result of batchResults) {
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
        }

        // 배치 간 대기
        if (i + CONFIG.concurrency < sites.length) {
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
    }
}

/**
 * 메인 함수
 */
async function main() {
    const startTime = Date.now();
    const now = new Date();
    const checkDate = now.toISOString().split('T')[0]; // YYYY-MM-DD

    // 명령행 인자 확인
    const checkOnlyParseErrors = process.argv.includes('--parse-errors-only');
    const checkAll = process.argv.includes('--all');

    console.log('='.repeat(80));
    console.log('🏥 Playwright 브라우저 헬스체크');
    console.log('='.repeat(80));
    console.log(`체크 시간: ${now.toLocaleString('ko-KR')}`);
    console.log(`체크 날짜: ${checkDate}`);
    if (checkOnlyParseErrors) {
        console.log(`모드: HTTP_PARSE_ERROR 사이트만 체크`);
    } else if (checkAll) {
        console.log(`모드: 전체 사이트 체크`);
    } else {
        console.log(`모드: HTTP_PARSE_ERROR 사이트만 체크 (기본)`);
    }
    console.log('='.repeat(80) + '\n');

    const pool = createPool();
    let browser = null;

    try {
        // 사이트 목록 가져오기
        let sites;
        if (checkAll) {
            sites = await getAllSites(pool);
        } else {
            sites = await getHttpParseErrorSites(pool);

            // HTTP_PARSE_ERROR 사이트가 없으면 종료
            if (sites.length === 0) {
                console.log('✅ HTTP_PARSE_ERROR 사이트가 없습니다. 체크할 사이트가 없습니다.');
                console.log('   일반 헬스체크를 먼저 실행하세요: node node/health/health_check.js');
                return;
            }
        }

        console.log('\n브라우저 시작 중...');
        browser = await chromium.launch({
            headless: CONFIG.headless,
        });
        console.log('✅ 브라우저 시작 완료\n');

        console.log('헬스체크 시작...\n');

        const results = {
            total: sites.length,
            healthy: 0,
            unhealthy: 0,
            errors: [],
            responseTimes: []
        };

        // 배치로 체크
        await checkSitesInBatch(browser, sites, pool, checkDate, results);

        // 요약 저장
        await saveHealthCheckSummary(pool, checkDate, results);

        const duration = Date.now() - startTime;
        const avgResponseTime = results.responseTimes.length > 0
            ? Math.round(results.responseTimes.reduce((a, b) => a + b, 0) / results.responseTimes.length)
            : 0;

        console.log('\n' + '='.repeat(80));
        console.log('📊 Playwright 헬스체크 결과');
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

        console.log('\n✅ Playwright 헬스체크 완료');

    } catch (error) {
        console.error('\n❌ 헬스체크 실패:', error);
        throw error;
    } finally {
        if (browser) {
            await browser.close();
            console.log('✅ 브라우저 종료');
        }
        await pool.end();
    }
}

// 실행
if (require.main === module) {
    main().catch(error => {
        console.error('Fatal error:', error);
        process.exit(1);
    });
}

module.exports = { main, checkSiteHealthWithPlaywright };
