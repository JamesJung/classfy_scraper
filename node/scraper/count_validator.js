/**
 * 스크래퍼 건수 검증 모듈
 *
 * 예상 건수와 실제 스크래핑 건수를 비교하여 부분 실패를 감지
 */

const mysql = require('mysql2/promise');
const path = require('path');
const moment = require('moment');

// .env 파일 로드
try {
    require('dotenv').config({ path: path.join(__dirname, '../../.env') });
} catch (error) {
    console.warn('[CountValidator] .env 파일 로드 실패, 환경 변수 사용');
}

class CountValidator {
    /**
     * 카운트 시작 기록
     */
    static async startCounting(siteCode, batchDate = null) {
        const connection = await this.getConnection();

        try {
            const date = batchDate || moment().format('YYYY-MM-DD');

            const query = `
                INSERT INTO scraper_count_validation
                    (batch_date, site_code, status, count_started_at)
                VALUES
                    (?, ?, 'counting', NOW())
                ON DUPLICATE KEY UPDATE
                    status = 'counting',
                    count_started_at = NOW(),
                    expected_count = 0,
                    page_count = 0,
                    updated_at = NOW()
            `;

            await connection.execute(query, [date, siteCode]);
            console.log(`[CountValidator] 카운트 시작 기록: ${siteCode} (${date})`);

            return true;
        } catch (error) {
            console.error('[CountValidator] 카운트 시작 기록 실패:', error.message);
            return false;
        } finally {
            await connection.end();
        }
    }

    /**
     * 카운트 완료 기록
     */
    static async completeCounting(siteCode, expectedCount, pageCount, batchDate = null) {
        const connection = await this.getConnection();

        try {
            const date = batchDate || moment().format('YYYY-MM-DD');

            const query = `
                UPDATE scraper_count_validation
                SET
                    expected_count = ?,
                    page_count = ?,
                    status = 'counted',
                    count_completed_at = NOW(),
                    updated_at = NOW()
                WHERE
                    batch_date = ?
                    AND site_code = ?
            `;

            await connection.execute(query, [expectedCount, pageCount, date, siteCode]);
            console.log(`[CountValidator] 카운트 완료: ${siteCode} - 예상 ${expectedCount}개 (${pageCount} 페이지)`);

            return true;
        } catch (error) {
            console.error('[CountValidator] 카운트 완료 기록 실패:', error.message);
            return false;
        } finally {
            await connection.end();
        }
    }

    /**
     * 스크래핑 시작 기록
     */
    static async startScraping(siteCode, batchDate = null) {
        const connection = await this.getConnection();

        try {
            const date = batchDate || moment().format('YYYY-MM-DD');

            const query = `
                UPDATE scraper_count_validation
                SET
                    status = 'scraping',
                    scrape_started_at = NOW(),
                    updated_at = NOW()
                WHERE
                    batch_date = ?
                    AND site_code = ?
            `;

            await connection.execute(query, [date, siteCode]);
            console.log(`[CountValidator] 스크래핑 시작 기록: ${siteCode} (${date})`);

            return true;
        } catch (error) {
            console.error('[CountValidator] 스크래핑 시작 기록 실패:', error.message);
            return false;
        } finally {
            await connection.end();
        }
    }

    /**
     * 스크래핑 완료 및 검증
     */
    static async completeScraping(siteCode, actualCount, batchDate = null) {
        const connection = await this.getConnection();

        try {
            const date = batchDate || moment().format('YYYY-MM-DD');

            // 1. 현재 expected_count 조회
            const [rows] = await connection.execute(
                'SELECT expected_count, actual_count, failed_count FROM scraper_count_validation WHERE batch_date = ? AND site_code = ?',
                [date, siteCode]
            );

            if (rows.length === 0) {
                console.warn(`[CountValidator] 기록이 없음: ${siteCode} (${date})`);
                return false;
            }

            const expectedCount = rows[0].expected_count;
            const currentFailedCount = rows[0].failed_count || 0;

            // 2. 실패한 공고 건수 조회 (scraper_failed_announcements 테이블)
            const [failedRows] = await connection.execute(
                `SELECT COUNT(*) as count
                 FROM scraper_failed_announcements
                 WHERE batch_date = ? AND site_code = ? AND status = 'pending'`,
                [date, siteCode]
            );

            const failedCount = failedRows[0].count;

            // 3. 상태 판단
            let status = 'completed';
            let mismatchReason = null;

            // 예상 건수와 실제 건수 비교
            if (expectedCount > 0 && actualCount < expectedCount) {
                status = 'mismatch';
                const missing = expectedCount - actualCount;
                mismatchReason = `예상 ${expectedCount}개 중 ${actualCount}개만 성공 (${missing}개 누락, 실패 ${failedCount}개)`;
                console.warn(`[CountValidator] ⚠️ 건수 불일치: ${mismatchReason}`);
            } else if (actualCount === expectedCount) {
                console.log(`[CountValidator] ✅ 건수 일치: 예상 ${expectedCount}개 = 실제 ${actualCount}개`);
            }

            // 4. DB 업데이트
            const query = `
                UPDATE scraper_count_validation
                SET
                    actual_count = ?,
                    failed_count = ?,
                    status = ?,
                    mismatch_reason = ?,
                    scrape_completed_at = NOW(),
                    updated_at = NOW()
                WHERE
                    batch_date = ?
                    AND site_code = ?
            `;

            await connection.execute(query, [
                actualCount,
                failedCount,
                status,
                mismatchReason,
                date,
                siteCode
            ]);

            return {
                success: true,
                status: status,
                expectedCount: expectedCount,
                actualCount: actualCount,
                failedCount: failedCount,
                mismatch: status === 'mismatch'
            };

        } catch (error) {
            console.error('[CountValidator] 스크래핑 완료 기록 실패:', error.message);
            return { success: false, error: error.message };
        } finally {
            await connection.end();
        }
    }

    /**
     * 검증 결과 조회
     */
    static async getValidationResult(siteCode, batchDate = null) {
        const connection = await this.getConnection();

        try {
            const date = batchDate || moment().format('YYYY-MM-DD');

            const query = `
                SELECT
                    batch_date,
                    site_code,
                    expected_count,
                    actual_count,
                    failed_count,
                    page_count,
                    status,
                    mismatch_reason,
                    count_started_at,
                    count_completed_at,
                    scrape_started_at,
                    scrape_completed_at
                FROM scraper_count_validation
                WHERE batch_date = ? AND site_code = ?
            `;

            const [rows] = await connection.execute(query, [date, siteCode]);

            return rows.length > 0 ? rows[0] : null;

        } catch (error) {
            console.error('[CountValidator] 검증 결과 조회 실패:', error.message);
            return null;
        } finally {
            await connection.end();
        }
    }

    /**
     * 불일치 목록 조회
     */
    static async getMismatchList(batchDate = null, limit = 100) {
        const connection = await this.getConnection();

        try {
            const date = batchDate || moment().format('YYYY-MM-DD');

            const query = `
                SELECT
                    batch_date,
                    site_code,
                    expected_count,
                    actual_count,
                    failed_count,
                    status,
                    mismatch_reason,
                    scrape_completed_at
                FROM scraper_count_validation
                WHERE batch_date = ?
                  AND status = 'mismatch'
                ORDER BY (expected_count - actual_count) DESC
                LIMIT ?
            `;

            const [rows] = await connection.execute(query, [date, limit]);

            return rows;

        } catch (error) {
            console.error('[CountValidator] 불일치 목록 조회 실패:', error.message);
            return [];
        } finally {
            await connection.end();
        }
    }

    /**
     * DB 연결
     */
    static async getConnection() {
        return await mysql.createConnection({
            host: process.env.DB_HOST || 'localhost',
            port: parseInt(process.env.DB_PORT) || 3306,
            user: process.env.DB_USER || 'root',
            password: process.env.DB_PASSWORD || '',
            database: process.env.DB_NAME || 'subvention'
        });
    }
}

module.exports = CountValidator;
