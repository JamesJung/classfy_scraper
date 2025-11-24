/**
 * URL 관리 및 정규화 모듈
 *
 * 용도:
 * - 상세 URL 정규화 (page 파라미터 제거)
 * - URL DB 저장 및 중복 체크
 */

const mysql = require('mysql2/promise');
const crypto = require('crypto');
const path = require('path');
const moment = require('moment');

// .env 파일 로드
try {
    require('dotenv').config({ path: path.join(__dirname, '../../.env') });
} catch (error) {
    console.warn('[UrlManager] .env 파일 로드 실패, 환경 변수 사용');
}

class UrlManager {
    /**
     * URL 정규화 - page 관련 파라미터 제거
     *
     * @param {string} url - 원본 URL
     * @returns {string} 정규화된 URL
     */
    static normalizeUrl(url) {
        if (!url) return '';

        try {
            const urlObj = new URL(url);
            const params = new URLSearchParams(urlObj.search);

            // 제거할 page 관련 파라미터 목록
            const pageParams = [
                'page', 'pageNum', 'pageNo', 'pageIndex', 'pageNumber',
                'startPage', 'currentPage', 'p', 'pg', 'pn',
                'offset', 'start', 'from',
                'pageSize', 'pagesize', 'size', 'limit',
                'isManager', 'isCharge' // 불필요한 상태 파라미터도 제거
            ];

            // page 관련 파라미터 제거
            pageParams.forEach(param => {
                if (params.has(param)) {
                    params.delete(param);
                }
            });

            // 정규화된 URL 생성
            urlObj.search = params.toString();
            let normalizedUrl = urlObj.toString();

            // 쿼리스트링이 비어있으면 ? 제거
            if (normalizedUrl.endsWith('?')) {
                normalizedUrl = normalizedUrl.slice(0, -1);
            }

            return normalizedUrl;

        } catch (error) {
            console.warn('[UrlManager] URL 파싱 실패:', url, error.message);
            return url;
        }
    }

    /**
     * URL 해시 생성 (SHA256)
     *
     * @param {string} url - URL
     * @returns {string} SHA256 해시
     */
    static hashUrl(url) {
        return crypto.createHash('sha256').update(url).digest('hex');
    }

    /**
     * 상세 URL 저장
     *
     * @param {Object} data - URL 정보
     * @param {string} data.site_code - 사이트 코드
     * @param {string} data.title - 공고 제목
     * @param {string} data.list_url - 리스트 URL
     * @param {string} data.detail_url - 상세 URL
     * @param {string} data.list_date - 리스트 날짜
     * @param {string} data.batch_date - 배치 날짜 (선택)
     * @returns {Promise<boolean>} 저장 성공 여부
     */
    static async saveDetailUrl(data) {
        const connection = await this.getConnection();

        try {
            const {
                site_code,
                title,
                list_url,
                detail_url,
                list_date,
                batch_date
            } = data;

            // URL 정규화 및 해시 생성
            const normalizedUrl = this.normalizeUrl(detail_url);
            const urlHash = this.hashUrl(normalizedUrl);
            const batchDate = batch_date || moment().format('YYYY-MM-DD');

            const query = `
                INSERT INTO scraper_detail_urls
                    (batch_date, site_code, title, list_url, detail_url, normalized_url, url_hash, list_date, scraped)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    list_url = VALUES(list_url),
                    detail_url = VALUES(detail_url),
                    list_date = VALUES(list_date),
                    updated_at = NOW()
            `;

            await connection.execute(query, [
                batchDate,
                site_code,
                title,
                list_url,
                detail_url,
                normalizedUrl,
                urlHash,
                list_date
            ]);

            return true;

        } catch (error) {
            console.error('[UrlManager] URL 저장 실패:', error.message);
            return false;
        } finally {
            await connection.end();
        }
    }

    /**
     * URL 중복 체크
     *
     * @param {string} site_code - 사이트 코드
     * @param {string} detail_url - 상세 URL
     * @param {string} batch_date - 배치 날짜 (선택)
     * @returns {Promise<boolean>} 중복 여부 (true: 중복, false: 중복 아님)
     */
    static async isDuplicate(site_code, detail_url, batch_date = null) {
        const connection = await this.getConnection();

        try {
            const normalizedUrl = this.normalizeUrl(detail_url);
            const urlHash = this.hashUrl(normalizedUrl);
            const batchDate = batch_date || moment().format('YYYY-MM-DD');

            const query = `
                SELECT COUNT(*) as count
                FROM scraper_detail_urls
                WHERE site_code = ?
                  AND url_hash = ?
                  AND batch_date = ?
            `;

            const [rows] = await connection.execute(query, [site_code, urlHash, batchDate]);

            return rows[0].count > 0;

        } catch (error) {
            console.error('[UrlManager] 중복 체크 실패:', error.message);
            return false;
        } finally {
            await connection.end();
        }
    }

    /**
     * 스크래핑 완료 표시
     *
     * @param {string} site_code - 사이트 코드
     * @param {string} detail_url - 상세 URL
     * @param {string} batch_date - 배치 날짜 (선택)
     * @returns {Promise<boolean>} 성공 여부
     */
    static async markAsScraped(site_code, detail_url, batch_date = null) {
        const connection = await this.getConnection();

        try {
            const normalizedUrl = this.normalizeUrl(detail_url);
            const urlHash = this.hashUrl(normalizedUrl);
            const batchDate = batch_date || moment().format('YYYY-MM-DD');

            const query = `
                UPDATE scraper_detail_urls
                SET scraped = 1,
                    scraped_at = NOW(),
                    updated_at = NOW()
                WHERE site_code = ?
                  AND url_hash = ?
                  AND batch_date = ?
            `;

            await connection.execute(query, [site_code, urlHash, batchDate]);

            return true;

        } catch (error) {
            console.error('[UrlManager] 스크래핑 완료 표시 실패:', error.message);
            return false;
        } finally {
            await connection.end();
        }
    }

    /**
     * 미스크래핑 URL 조회
     *
     * @param {string} site_code - 사이트 코드
     * @param {string} batch_date - 배치 날짜 (선택)
     * @param {number} limit - 조회 개수 제한
     * @returns {Promise<Array>} 미스크래핑 URL 목록
     */
    static async getUnscrapedUrls(site_code, batch_date = null, limit = 100) {
        const connection = await this.getConnection();

        try {
            const batchDate = batch_date || moment().format('YYYY-MM-DD');

            const query = `
                SELECT
                    id,
                    site_code,
                    title,
                    detail_url,
                    normalized_url,
                    list_date
                FROM scraper_detail_urls
                WHERE site_code = ?
                  AND batch_date = ?
                  AND scraped = 0
                ORDER BY created_at ASC
                LIMIT ?
            `;

            const [rows] = await connection.execute(query, [site_code, batchDate, limit]);

            return rows;

        } catch (error) {
            console.error('[UrlManager] 미스크래핑 URL 조회 실패:', error.message);
            return [];
        } finally {
            await connection.end();
        }
    }

    /**
     * 통계 조회
     *
     * @param {string} site_code - 사이트 코드
     * @param {string} batch_date - 배치 날짜 (선택)
     * @returns {Promise<Object>} 통계 정보
     */
    static async getStats(site_code, batch_date = null) {
        const connection = await this.getConnection();

        try {
            const batchDate = batch_date || moment().format('YYYY-MM-DD');

            const query = `
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN scraped = 1 THEN 1 ELSE 0 END) as scraped,
                    SUM(CASE WHEN scraped = 0 THEN 1 ELSE 0 END) as unscraped
                FROM scraper_detail_urls
                WHERE site_code = ?
                  AND batch_date = ?
            `;

            const [rows] = await connection.execute(query, [site_code, batchDate]);

            return rows[0] || { total: 0, scraped: 0, unscraped: 0 };

        } catch (error) {
            console.error('[UrlManager] 통계 조회 실패:', error.message);
            return { total: 0, scraped: 0, unscraped: 0 };
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

module.exports = UrlManager;
