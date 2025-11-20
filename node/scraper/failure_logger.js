/**
 * 스크래퍼 실패 공고 로깅 모듈
 *
 * 용도: 개별 공고 스크래핑 실패 시 DB에 기록
 * 사용: 모든 스크래퍼에서 공통으로 사용
 */

const mysql = require('mysql2/promise');
const path = require('path');

// .env 파일 로드
try {
    require('dotenv').config({ path: path.join(__dirname, '../../.env') });
} catch (error) {
    console.warn('[FailureLogger] .env 파일 로드 실패, 환경 변수 사용');
}

class FailureLogger {
    /**
     * DB 연결 설정 가져오기
     */
    static getDbConfig() {
        return {
            host: process.env.DB_HOST || 'localhost',
            port: parseInt(process.env.DB_PORT) || 3306,
            user: process.env.DB_USER || 'root',
            password: process.env.DB_PASSWORD || '',
            database: process.env.DB_NAME || 'subvention',
            charset: 'utf8mb4',
            waitForConnections: true,
            connectionLimit: 10,
            queueLimit: 0
        };
    }

    /**
     * 실패한 공고를 DB에 기록
     *
     * @param {Object} data - 실패 정보
     * @param {string} data.site_code - 사이트 코드 (필수)
     * @param {string} data.title - 공고 제목 (선택)
     * @param {string} data.url - 공고 URL (선택)
     * @param {string} data.detail_url - 상세 페이지 URL (선택)
     * @param {string} data.error_type - 에러 타입 (선택)
     * @param {string} data.error_message - 에러 메시지 (선택)
     */
    static async logFailedAnnouncement(data) {
        let connection;

        try {
            // 필수 파라미터 체크
            if (!data.site_code) {
                console.error('[FailureLogger] site_code is required');
                return false;
            }

            // DB 연결
            connection = await mysql.createConnection(this.getDbConfig());

            // 오늘 날짜
            const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD

            // URL이 없으면 제목으로 대체 (중복 체크용)
            const uniqueUrl = data.detail_url || data.url || `fallback_${Date.now()}_${Math.random()}`;

            // INSERT ... ON DUPLICATE KEY UPDATE (중복 시 에러 카운트 증가)
            const query = `
                INSERT INTO scraper_failed_announcements (
                    batch_date,
                    site_code,
                    announcement_title,
                    announcement_url,
                    detail_url,
                    error_type,
                    error_message,
                    retry_count,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'pending')
                ON DUPLICATE KEY UPDATE
                    error_message = VALUES(error_message),
                    updated_at = CURRENT_TIMESTAMP
            `;

            const params = [
                today,
                data.site_code,
                data.title || null,
                data.url || null,
                uniqueUrl,
                data.error_type || 'unknown_error',
                data.error_message || 'No error message provided'
            ];

            const [result] = await connection.execute(query, params);

            // 성공 로그 (insertId가 0이면 UPDATE, 아니면 INSERT)
            if (result.insertId > 0) {
                console.log(`[FailureLogger] ✓ 실패 공고 기록: ${data.site_code} - ${data.title || 'No title'}`);
            } else {
                console.log(`[FailureLogger] ✓ 실패 공고 업데이트: ${data.site_code} - ${data.title || 'No title'}`);
            }

            return true;

        } catch (error) {
            console.error('[FailureLogger] DB 기록 실패:', error.message);
            // DB 로깅 실패는 전체 스크래핑을 중단하지 않음
            return false;
        } finally {
            if (connection) {
                await connection.end();
            }
        }
    }

    /**
     * 여러 실패 공고를 한 번에 기록 (배치 처리)
     *
     * @param {Array<Object>} failureList - 실패 정보 배열
     */
    static async logMultipleFailures(failureList) {
        const results = [];

        for (const failure of failureList) {
            const result = await this.logFailedAnnouncement(failure);
            results.push(result);
        }

        const successCount = results.filter(r => r === true).length;
        console.log(`[FailureLogger] 배치 처리 완료: ${successCount}/${failureList.length}개 성공`);

        return results;
    }

    /**
     * 특정 사이트의 오늘 실패 공고 개수 조회
     *
     * @param {string} site_code - 사이트 코드
     * @returns {Promise<number>} 실패 공고 개수
     */
    static async getFailureCount(site_code) {
        let connection;

        try {
            connection = await mysql.createConnection(this.getDbConfig());

            const today = new Date().toISOString().split('T')[0];

            const [rows] = await connection.execute(
                `SELECT COUNT(*) as count
                 FROM scraper_failed_announcements
                 WHERE site_code = ? AND batch_date = ? AND status = 'pending'`,
                [site_code, today]
            );

            return rows[0]?.count || 0;

        } catch (error) {
            console.error('[FailureLogger] 실패 카운트 조회 실패:', error.message);
            return 0;
        } finally {
            if (connection) {
                await connection.end();
            }
        }
    }
}

module.exports = FailureLogger;
