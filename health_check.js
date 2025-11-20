#!/usr/bin/env node
/**
 * 스크래퍼 사이트 Health Check 스크립트
 *
 * 기능:
 * 1. scraper_site_url 테이블에서 사이트 목록 조회
 * 2. 각 사이트 URL에 HTTP 요청
 * 3. 상태 코드, 응답 시간, 리다이렉트 정보 수집
 * 4. health_check_log 테이블에 결과 저장 (UPSERT)
 *
 * 실행: node health_check.js
 */

const mysql = require('mysql2/promise');
const https = require('https');
const http = require('http');
const { URL } = require('url');

// 데이터베이스 연결 설정
const DB_CONFIG = {
  host: '192.168.0.95',
  port: 3309,
  user: 'root',
  password: 'b3UvSDS232GbdZ42',
  database: 'subvention',
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0
};

// HTTP 요청 타임아웃 (ms)
const REQUEST_TIMEOUT = 10000;

// 리다이렉트 최대 횟수
const MAX_REDIRECTS = 5;

/**
 * URL Health Check 수행
 * @param {string} url - 체크할 URL
 * @returns {Promise<Object>} - { statusCode, errorType, errorMessage, responseTime, redirectUrl, redirectCount }
 */
async function checkUrl(url) {
  const startTime = Date.now();
  let redirectCount = 0;
  let currentUrl = url;
  let finalStatusCode = null;
  let finalRedirectUrl = null;
  let errorType = null;
  let errorMessage = null;

  try {
    // URL 파싱
    const parsedUrl = new URL(currentUrl);
    const isHttps = parsedUrl.protocol === 'https:';
    const httpModule = isHttps ? https : http;

    // 리다이렉트 추적
    for (let i = 0; i < MAX_REDIRECTS; i++) {
      const result = await new Promise((resolve, reject) => {
        const options = {
          method: 'GET',
          timeout: REQUEST_TIMEOUT,
          headers: {
            'User-Agent': 'Mozilla/5.0 (compatible; HealthCheck/1.0)',
          }
        };

        const req = httpModule.get(currentUrl, options, (res) => {
          const { statusCode, headers } = res;

          // 데이터 소비 (메모리 누수 방지)
          res.resume();

          // 리다이렉트 처리 (3xx)
          if (statusCode >= 300 && statusCode < 400 && headers.location) {
            resolve({
              isRedirect: true,
              statusCode,
              location: headers.location
            });
          } else {
            resolve({
              isRedirect: false,
              statusCode
            });
          }
        });

        req.on('error', (error) => {
          reject(error);
        });

        req.on('timeout', () => {
          req.destroy();
          reject(new Error('Request timeout'));
        });
      });

      if (result.isRedirect) {
        redirectCount++;
        finalRedirectUrl = result.location;

        // 상대 경로를 절대 경로로 변환
        if (!result.location.startsWith('http')) {
          const baseUrl = new URL(currentUrl);
          finalRedirectUrl = new URL(result.location, baseUrl.origin).href;
        }

        currentUrl = finalRedirectUrl;
        finalStatusCode = result.statusCode;
      } else {
        finalStatusCode = result.statusCode;
        break;
      }
    }

    const responseTime = Date.now() - startTime;

    return {
      statusCode: finalStatusCode,
      errorType: null,
      errorMessage: null,
      responseTime,
      redirectUrl: redirectCount > 0 ? finalRedirectUrl : null,
      redirectCount
    };

  } catch (error) {
    const responseTime = Date.now() - startTime;

    // 에러 타입 분류
    if (error.code === 'ENOTFOUND') {
      errorType = 'DNS_ERROR';
      errorMessage = 'DNS resolution failed';
    } else if (error.code === 'ECONNREFUSED') {
      errorType = 'CONNECTION_REFUSED';
      errorMessage = 'Connection refused';
    } else if (error.code === 'ETIMEDOUT' || error.message === 'Request timeout') {
      errorType = 'TIMEOUT';
      errorMessage = 'Request timeout';
    } else if (error.code === 'CERT_HAS_EXPIRED' || error.code === 'UNABLE_TO_VERIFY_LEAF_SIGNATURE') {
      errorType = 'SSL_ERROR';
      errorMessage = `SSL certificate error: ${error.code}`;
    } else {
      errorType = 'UNKNOWN_ERROR';
      errorMessage = error.message;
    }

    return {
      statusCode: null,
      errorType,
      errorMessage,
      responseTime,
      redirectUrl: null,
      redirectCount: 0
    };
  }
}

/**
 * Health Check 로그를 DB에 저장 (UPSERT)
 * @param {Object} connection - MySQL 연결
 * @param {string} siteCode - 사이트 코드
 * @param {string} siteUrl - 사이트 URL
 * @param {Object} checkResult - Health Check 결과
 */
async function saveHealthCheckLog(connection, siteCode, siteUrl, checkResult) {
  const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD

  const query = `
    INSERT INTO health_check_log (
      check_date,
      site_code,
      site_url,
      status_code,
      error_type,
      error_message,
      response_time,
      redirect_url,
      redirect_count,
      created_at,
      updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW(), NOW())
    ON DUPLICATE KEY UPDATE
      site_url = VALUES(site_url),
      status_code = VALUES(status_code),
      error_type = VALUES(error_type),
      error_message = VALUES(error_message),
      response_time = VALUES(response_time),
      redirect_url = VALUES(redirect_url),
      redirect_count = VALUES(redirect_count),
      updated_at = NOW()
  `;

  const params = [
    today,
    siteCode,
    siteUrl,
    checkResult.statusCode,
    checkResult.errorType,
    checkResult.errorMessage,
    checkResult.responseTime,
    checkResult.redirectUrl,
    checkResult.redirectCount
  ];

  await connection.execute(query, params);
}

/**
 * 메인 실행 함수
 */
async function main() {
  let connection;

  try {
    console.log('========================================');
    console.log('  스크래퍼 사이트 Health Check 시작');
    console.log(`  실행 시각: ${new Date().toISOString()}`);
    console.log('========================================\n');

    // 데이터베이스 연결
    connection = await mysql.createConnection(DB_CONFIG);
    console.log('✓ 데이터베이스 연결 성공\n');

    // 사이트 목록 조회
    const [sites] = await connection.execute(`
      SELECT site_code, site_url
      FROM scraper_site_url
      WHERE site_url IS NOT NULL
      ORDER BY site_code
    `);

    console.log(`총 ${sites.length}개 사이트 체크 시작...\n`);

    let successCount = 0;
    let errorCount = 0;

    // 각 사이트 Health Check
    for (let i = 0; i < sites.length; i++) {
      const { site_code, site_url } = sites[i];

      process.stdout.write(`[${i + 1}/${sites.length}] ${site_code} ... `);

      try {
        const checkResult = await checkUrl(site_url);

        // 결과 저장
        await saveHealthCheckLog(connection, site_code, site_url, checkResult);

        if (checkResult.statusCode === 200) {
          console.log(`✓ OK (${checkResult.responseTime}ms)`);
          successCount++;
        } else if (checkResult.statusCode && checkResult.statusCode >= 300 && checkResult.statusCode < 400) {
          console.log(`⇢ Redirect ${checkResult.statusCode} (${checkResult.redirectCount}회)`);
          successCount++;
        } else if (checkResult.errorType) {
          console.log(`✗ ${checkResult.errorType}: ${checkResult.errorMessage}`);
          errorCount++;
        } else {
          console.log(`⚠ HTTP ${checkResult.statusCode}`);
          errorCount++;
        }

      } catch (error) {
        console.log(`✗ 체크 실패: ${error.message}`);
        errorCount++;
      }
    }

    console.log('\n========================================');
    console.log('  Health Check 완료');
    console.log('========================================');
    console.log(`총 사이트: ${sites.length}개`);
    console.log(`정상: ${successCount}개`);
    console.log(`오류: ${errorCount}개`);
    console.log('========================================\n');

  } catch (error) {
    console.error('❌ Health Check 실행 중 오류 발생:', error);
    process.exit(1);
  } finally {
    if (connection) {
      await connection.end();
    }
  }
}

// 스크립트 직접 실행 시
if (require.main === module) {
  main().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
  });
}

module.exports = { checkUrl, saveHealthCheckLog };
