#!/usr/bin/env node

/**
 * 통합 리스트 수집기
 * 모든 사이트의 공고 리스트를 수집하고 중복 체크를 수행
 * 
 * 사용법:
 * node general_list_collector.js <site_code> [options]
 * node general_list_collector.js anseong --pages 3
 * node general_list_collector.js cs --pages 5 --verbose
 */

const { chromium } = require('playwright');
const mysql = require('mysql2/promise');
const fs = require('fs-extra');
const path = require('path');
const moment = require('moment');
const yargs = require('yargs');

class HomepageGosiListCollector {
    constructor(siteCode, options = {}) {
        this.siteCode = siteCode;
        this.startPage = options.startPage || 1;  // 시작 페이지
        this.maxPages = options.pages || 3;
        this.verbose = options.verbose || false;
        this.testMode = options.test || false;
        this.noInsert = options.noInsert || false;  // DB INSERT 비활성화 옵션 (조회는 함)

        // 설정 파일 로드
        this.configPath = path.join(__dirname, 'configs', `${siteCode}.json`);
        if (!fs.existsSync(this.configPath)) {
            throw new Error(`설정 파일이 없습니다: ${this.configPath}`);
        }
        this.config = require(this.configPath);

        // 통계
        this.stats = {
            totalItems: 0,
            newItems: 0,
            duplicates: 0,
            errors: 0,
            pages: 0
        };

        // 연속 중복 카운터
        this.consecutiveDuplicates = 0;
        this.maxConsecutiveDuplicates = 30;

        // 최신 완료 항목의 날짜 (초기화 시 DB에서 가져옴)
        this.latestCompletedDate = null;

        this.browser = null;
        this.page = null;
        this.db = null;
    }

    /**
     * 데이터베이스 연결
     */
    async connectDB() {
        // noInsert 모드에서도 DB 연결은 필요 (조회용)
        if (this.noInsert && this.verbose) {
            console.log('✓ DB INSERT 비활성화 모드 (조회만 수행)');
        }

        // .env 파일에서 환경 변수 로드
        require('dotenv').config();

        this.db = await mysql.createConnection({
            host: process.env.DB_HOST || 'localhost',
            port: process.env.DB_PORT || 3306,
            user: process.env.DB_USER || 'scraper',
            password: process.env.DB_PASSWORD,
            database: process.env.DB_NAME || 'opendata'
        });

        if (this.verbose) {
            console.log('✓ 데이터베이스 연결 완료');
        }

        // completed 항목 중 가장 최신 날짜 조회
        await this.loadLatestCompletedDate();
    }

    /**
     * completed 상태인 항목들 중 가장 최신 날짜 조회
     */
    async loadLatestCompletedDate() {
        if (!this.db) return;

        try {
            const [rows] = await this.db.execute(
                `SELECT DATE(MAX(post_date)) as latest_date 
                 FROM homepage_gosi_url_registry 
                 WHERE site_code = ? AND status = 'completed'`,
                [this.siteCode]
            );

            if (rows && rows[0] && rows[0].latest_date) {
                const rawDate = rows[0].latest_date;
                const dateStr = rawDate instanceof Date
                    ? rawDate.toISOString().split('T')[0]
                    : String(rawDate).split(' ')[0];

                this.latestCompletedDate = new Date(dateStr + 'T00:00:00');
                console.log(`✓ 최신 완료 항목 날짜: ${dateStr}`);
            }
        } catch (error) {
            console.error('최신 날짜 조회 오류:', error.message);
        }
    }

    /**
     * 브라우저 초기화
     */
    async initBrowser() {
        this.browser = await chromium.launch({
            headless: !this.testMode,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--allow-running-insecure-content',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ],

            timeout: 30000
        });

        this.context = await this.browser.newContext({
            viewport: { width: 1280, height: 720 },
            ignoreHTTPSErrors: true,
            bypassCSP: true,
            extraHTTPHeaders: {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
        });

        this.page = await this.context.newPage();

        // this.page = await this.browser.newPage();

        // User-Agent 설정
        await this.page.setExtraHTTPHeaders({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'
        });

        this.browser.on('disconnected', () => {
            console.warn('브라우저 연결이 끊어졌습니다.');
        });

        this.page.on('crash', () => {
            console.warn('페이지 크래시 발생');
        });

        this.page.on('console', (msg) => {
            console.log(`[브라우저 콘솔]: ${msg.text()}`);
        });


        if (this.verbose) {
            console.log('✓ 브라우저 초기화 완료');
        }
    }

    /**
     * URL 중복 체크
     */
    async checkDuplicate(url, announcementId = null) {
        // noInsert 모드에서는 중복 체크는 하지만 INSERT는 안함
        if (this.noInsert) {
            return false;
        }

        try {
            // announcement_id가 있으면 우선적으로 체크
            if (announcementId) {
                const [rows] = await this.db.execute(
                    'SELECT id FROM homepage_gosi_url_registry WHERE site_code = ? AND announcement_id = ?',
                    [this.siteCode, announcementId]
                );
                if (rows.length > 0) {
                    return true;
                }
            }

            // URL로 체크 (fallback)
            const [rows] = await this.db.execute(
                'SELECT id FROM homepage_gosi_url_registry WHERE site_code = ? AND announcement_url = ?',
                [this.siteCode, url]
            );
            return rows.length > 0;
        } catch (error) {
            console.error('중복 체크 오류:', error.message);
            return false;
        }
    }

    /**
     * 날짜 문자열을 Date 객체로 파싱
     */
    parseDate(dateStr) {
        if (!dateStr) return null;

        try {
            // 날짜 형식: 2025.09.26, 2025-09-26, 2025/09/26 등
            const cleaned = dateStr.replace(/[.\-\/]/g, '-');
            const parts = cleaned.split('-');

            if (parts.length === 3) {
                let year = parseInt(parts[0]);
                const month = parseInt(parts[1]) - 1; // JavaScript month is 0-indexed
                const day = parseInt(parts[2]);

                // 2자리 연도를 4자리로 변환 (00-99 -> 2000-2099)
                if (year < 100) {
                    year += 2000;
                }

                if (!isNaN(year) && !isNaN(month) && !isNaN(day)) {
                    return new Date(year, month, day);
                }
            }
        } catch (e) {
            // 파싱 실패 시 null 반환
        }

        return null;
    }

    /**
     * 신규 항목 DB 저장
     */
    async saveNewItem(item) {
        // noInsert 모드에서는 저장하지 않음
        if (this.noInsert) {
            return;
        }

        try {
            // URL에서 announcement_id 추출 시도 (config 기반)
            let announcementId = null;


            if (this.config.announcementIdPattern && this.config.announcementIdPattern.urlParams) {
                // config에 정의된 파라미터들로 시도
                const params = this.config.announcementIdPattern.urlParams.join('|');
                const regex = new RegExp(`[?&](${params})=([^&\\s]+)`, 'i');
                const idMatch = item.url.match(regex);
                if (idMatch) {
                    announcementId = idMatch[2];
                }
            } else {
                // 기본 패턴 사용
                const idMatch = item.url.match(/[?&](seq|id|no|idx|notAncmtMgtNo)=([^&\s]+)/i);
                if (idMatch) {
                    announcementId = idMatch[2];
                }
            }

            await this.db.execute(
                `INSERT INTO homepage_gosi_url_registry 
                (site_code, site_name, announcement_url, announcement_id, title, post_date, 
                 status, first_seen_date) 
                VALUES (?, ?, ?, ?, ?, ?, 'pending', NOW())`,
                [
                    this.siteCode,
                    this.config.siteName,
                    item.url,
                    announcementId,
                    item.title ? item.title.substring(0, 500) : null,  // VARCHAR(500) 제한
                    item.date ? moment(item.date, this.config.dateFormat).format('YYYY-MM-DD') : null
                ]
            );

            if (this.verbose) {
                console.log(`  ✓ 저장: ${item.title.substring(0, 50)}...`);
            }
        } catch (error) {
            console.error('항목 저장 오류:', error.message);
            this.stats.errors++;
        }
    }

    /**
     * 페이지별 리스트 수집
     */
    async collectPage(pageNum) {
        console.log(`\n[페이지 ${pageNum}] 수집 시작...`);
        this.stats.pages++;

        try {
            // 브라우저나 페이지가 종료된 경우 재초기화
            if (!this.browser || !this.page || this.page.isClosed()) {
                console.log('브라우저 연결이 끊어져 재초기화합니다...');
                await this.initBrowser();
            }

            // 첫 페이지만 전체 URL 로드
            if (pageNum === 1) {
                const listUrl = this.config.listUrl;
                console.log("listUrl", listUrl)
                await this.page.goto(listUrl, {
                    waitUntil: 'networkidle',
                    timeout: 30000
                });

                // 페이지 로딩 대기
                await this.page.waitForTimeout(3000);
            } else {
                // 2페이지 이상: JavaScript 함수로 이동
                let pageNavSuccess = false;

                pageNavSuccess = await this.page.evaluate((targetPage) => {
                    if (typeof gotoPage === 'function') {
                        console.log(`gotoPage(${targetPage}) 함수 호출`);
                        gotoPage(targetPage);
                        return true;
                    }
                    return false;
                }, pageNum);

                if (pageNavSuccess) {
                    console.log(`JavaScript 함수로 페이지 ${pageNum} 이동 완료`);
                    // AJAX 로딩 대기
                    await this.page.waitForTimeout(2000);

                    // 테이블 재로드 대기
                    try {
                        await this.page.waitForSelector(this.config.selectors.list, {
                            timeout: 5000
                        });
                        console.log(`테이블 로드 완료`);
                    } catch (e) {
                        console.log('테이블 로드 대기 중...');
                    }

                    // 추가 안정화 대기
                    await this.page.waitForTimeout(1000);
                } else {
                    // JavaScript 함수가 없으면 URL 파라미터 방식 사용
                    if (this.config.pagination?.type === 'query') {
                        const listUrl = `${this.config.listUrl}${this.config.pagination.param}=${pageNum}`;
                        console.log("listUrl (query)", listUrl)
                        await this.page.goto(listUrl, {
                            waitUntil: 'networkidle',
                            timeout: 30000
                        });
                        await this.page.waitForTimeout(3000);
                    }
                }
            }

            // 테이블이 로드될 때까지 대기
            try {
                await this.page.waitForSelector(this.config.selectors.list, {
                    timeout: 5000
                });
            } catch (e) {
                console.log('공고 테이블을 찾을 수 없습니다.');
            }
            ///////////////////////////////////////////////////////////////////////////////            


            // 페이지네이션 처리 (JavaScript 방식)
            if (pageNum > 1 && this.config.pagination?.type === 'javascript') {
                const pageFunc = this.config.pagination.function;

                // JavaScript 함수 실행 전 페이지 상태 확인
                const functionExists = await this.page.evaluate((func) => {
                    return typeof window[func] === 'function';
                }, pageFunc);

                if (!functionExists) {
                    console.warn(`[경고] 페이지네이션 함수 '${pageFunc}'를 찾을 수 없습니다.`);
                } else {
                    // 함수 실행
                    await this.page.evaluate(({ func, num }) => {
                        if (window[func]) {
                            window[func](num);
                        }
                    }, { func: pageFunc, num: pageNum });

                    // 페이지 로딩 대기 (네트워크 완료 또는 타임아웃)
                    try {
                        await this.page.waitForLoadState('networkidle', { timeout: 5000 });
                    } catch {
                        // 타임아웃이 발생해도 계속 진행
                        await this.page.waitForTimeout(2000);
                    }
                }
            }

            // // 페이지 로딩 대기
            // await this.page.waitForTimeout(3000);


            // console.log(this.config.selectors.list)

            // // 리스트 컨테이너 대기
            // await this.page.waitForSelector(this.config.selectors.list, { timeout: 10000 });

            // 리스트 추출
            const items = await this.page.evaluate((config) => {
                const rows = document.querySelectorAll(config.selectors.row);
                const items = [];

                console.log("rows", rows)

                for (const row of rows) {
                    try {

                        console.log("config.selectors.link", config.selectors.link)
                        // 제목과 링크
                        const linkEl = row.querySelector(config.selectors.link);
                        if (!linkEl) continue;

                        const onclick = linkEl.getAttribute("onclick")
                        const dataAction = linkEl.getAttribute("data-action")

                        let title;
                        if (config.selectors.title !== config.selectors.link) {
                            const titleEl = row.querySelector(config.selectors.title);
                            title = titleEl ? titleEl.textContent?.trim() : linkEl.textContent?.trim();
                        } else {
                            title = linkEl.textContent?.trim();
                        }

                        title = title.replace(/^\[\d+\]\s*(.*?)\s*첨부파일 있음$/, '$1').trim();

                        /*
                        if (titleElement) {
                            // Use textContent to get all the text inside <strong>, then trim whitespace
                            const fullTitle = titleElement.textContent.trim();
                            cleanTitle = fullTitle.replace(/^\[\d+\]\s*(.*?)\s*첨부파일 있음$/, '$1').trim();

                            title = cleanTitle
                        }

                        if (dateElement) {
                            // Use a regular expression to find the date after "등록일 :"
                            const dateMatch = dateElement.textContent.match(/등록일\s*:\s*(\d{4}-\d{2}-\d{2})/);
                            if (dateMatch && dateMatch[1]) {
                                dateText = dateMatch[1];
                            }
                        }
                        */


                        console.log("title", title)
                        title = title.replace("새로운글", "").replace("NEW", "")
                        let url = linkEl.href;

                        console.log("url", url, title)

                        // 1. data-action 우선 처리 (req.post(this) 패턴)
                        if (dataAction && onclick && onclick.includes('req.post')) {
                            url = dataAction;
                            console.log(`data-action 사용: ${url}`);
                        }
                        // 2. onclick에서 파라미터 추출 (config의 패턴 사용)
                        else if (config.onclickPatterns && config.onclickPatterns.length > 0) {
                            let urlFound = false;
                            let checkStr = onclick;
                            if (!checkStr) checkStr = url

                            console.log("config.onclickPatterns 사용!!!")
                            for (const patternConfig of config.onclickPatterns) {
                                const regex = new RegExp(patternConfig.pattern);

                                const match = checkStr.match(regex);

                                if (match) {
                                    // urlTemplate에서 {1}, {2} 등을 match 그룹으로 치환
                                    url = patternConfig.urlTemplate;
                                    for (let i = 1; i < match.length; i++) {
                                        url = url.replace(`{${i}}`, match[i]);
                                    }
                                    console.log(`패턴 매칭: ${patternConfig.description} -> ${url}`);
                                    urlFound = true;
                                    break;
                                }
                            }

                            // config에 패턴이 없거나 매칭되지 않으면 기본 패턴 시도
                            if (!urlFound) {
                                // 기본 패턴1: goView('12345') 또는 fn_view(12345)
                                let match = onclick.match(/['"]\s*(\d+)\s*['"]/);
                                if (match) {
                                    if (config.detailUrl) {
                                        url = `${config.detailUrl}?seq=${match[1]}`;
                                    } else {
                                        url = `${config.baseUrl}/view.do?seq=${match[1]}`;
                                    }
                                } else {
                                    // 기본 패턴2: location.href='url'
                                    match = onclick.match(/location\.href\s*=\s*['"]([^'"]+)['"]/);
                                    if (match) {
                                        url = match[1];
                                    }
                                }
                            }
                        } else if (onclick) {
                            // config.onclickPatterns가 없는 경우 기존 로직 사용
                            let match = onclick.match(/['"]\s*(\d+)\s*['"]/);
                            if (match) {
                                if (config.detailUrl) {
                                    url = `${config.detailUrl}?seq=${match[1]}`;
                                } else {
                                    url = `${config.baseUrl}/view.do?seq=${match[1]}`;
                                }
                            } else {
                                match = onclick.match(/location\.href\s*=\s*['"]([^'"]+)['"]/);
                                if (match) {
                                    url = match[1];
                                }
                            }
                        }

                        // 여전히 유효한 URL이 없으면 건너뛰기
                        if (!url || url.includes('javascript:')) {
                            console.log(`URL 추출 실패: ${title}`);
                            continue;
                        }
                        // }

                        // 상대 URL을 절대 URL로 변환
                        if (url && !url.startsWith('http')) {
                            // baseUrl 또는 현재 페이지 기준으로 절대 URL 생성
                            const baseUrl = config.baseUrl || window.location.origin;
                            url = new URL(url, baseUrl).href;
                        }

                        // 날짜
                        const dateEl = row.querySelector(config.selectors.date);
                        let date = dateEl?.textContent?.trim();
                        const dateMatch = date.match(/등록일\s*:\s*(\d{4}-\d{2}-\d{2})/);
                        if (dateMatch && dateMatch[1]) {
                            date = dateMatch[1];
                        }

                        // date = date.replace("등록일 :", "").trim()

                        // 날짜 범위인 경우 (예: 2025-09-15~2025-09-29) 첫 번째 날짜만 추출
                        if (date && date.includes('~')) {
                            date = date.split('~')[0].trim();
                        }

                        // 카테고리
                        // const 
                        //     row.querySelector(config.selectors.category) : null;
                        // const category = categoryEl?.textContent?.trim();

                        // 부서
                        // const deptEl = config.selectors.department ?
                        //     row.querySelector(config.selectors.department) : null;
                        // const department = deptEl?.textContent?.trim();

                        items.push({
                            title,
                            url,
                            date,
                            // category,
                            // department
                        });

                    } catch (err) {
                        console.error('항목 추출 오류:', err);
                    }
                }

                return items;

            }, this.config);

            console.log(`  추출: ${items.length}개 항목`);
            this.stats.totalItems += items.length;

            // 중복 체크 및 저장
            const newItems = [];
            const duplicateItems = [];
            let pageConsecutiveDuplicates = 0;

            for (const item of items) {
                if (!item.url || !item.title) continue;

                // URL에서 announcement_id 추출
                let announcementId = null;
                if (this.config.announcementIdPattern && this.config.announcementIdPattern.urlParams) {
                    const params = this.config.announcementIdPattern.urlParams.join('|');
                    const regex = new RegExp(`[?&](${params})=([^&\\s]+)`, 'i');
                    const idMatch = item.url.match(regex);
                    if (idMatch) {
                        announcementId = idMatch[2];
                    }
                } else {
                    const idMatch = item.url.match(/[?&](seq|id|no|idx|notAncmtMgtNo|dataSid)=(\d+)/i);
                    if (idMatch) {
                        announcementId = idMatch[2];
                    }
                }

                const isDuplicate = await this.checkDuplicate(item.url, announcementId);

                if (isDuplicate) {
                    this.stats.duplicates++;
                    pageConsecutiveDuplicates++;
                    this.consecutiveDuplicates++;
                    duplicateItems.push(item);

                    if (this.verbose) {
                        console.log(`  - 중복: ${item.title.substring(0, 50)}...`);
                    }

                    // 연속 중복 체크 (noInsert 모드에서는 체크 안함)
                    if (!this.noInsert && this.consecutiveDuplicates >= this.maxConsecutiveDuplicates) {
                        console.log(`\n연속 ${this.consecutiveDuplicates}개 중복 발견 - 수집 종료`);
                        return { items: newItems, shouldStop: true };
                    }

                } else {
                    // 신규 항목
                    this.consecutiveDuplicates = 0;  // 리셋
                    this.stats.newItems++;

                    newItems.push(item);
                    await this.saveNewItem(item);

                    if (this.verbose) {
                        console.log(`  + 신규: ${item.title.substring(0, 50)}...`);
                    }
                }
            }

            console.log(`  결과: ${newItems.length}개 신규, ${pageConsecutiveDuplicates}개 중복`);

            // 조기 종료 조건 체크 (noInsert 모드에서도 체크함)
            if (items.length > 0) {
                // 1. 페이지 내 중복이 1/3 이상인 경우
                const duplicateRatio = pageConsecutiveDuplicates / items.length;
                if (duplicateRatio >= 1 / 3) {
                    console.log(`\n중복 비율 ${(duplicateRatio * 100).toFixed(1)}% (${pageConsecutiveDuplicates}/${items.length}) - 수집 종료`);
                    return { items: newItems, shouldStop: true };
                }


                // 3. 날짜 기반 조기 종료
                if (items.length > 0) {
                    let pageOldestDate = null;
                    for (const item of items) {
                        const itemDate = this.parseDate(item.date);
                        if (itemDate && (!pageOldestDate || itemDate < pageOldestDate)) {
                            pageOldestDate = itemDate;
                        }
                    }

                    if (pageOldestDate) {
                        // 3-1. completed 날짜와 비교 (우선)
                        if (this.latestCompletedDate && pageOldestDate < this.latestCompletedDate) {
                            console.log(`\n현재 페이지 최소 날짜(${pageOldestDate.toISOString().split('T')[0]})가 완료된 항목 날짜(${this.latestCompletedDate.toISOString().split('T')[0]})보다 이전 - 수집 종료`);
                            return { items: newItems, shouldStop: true };
                        }

                        // 3-2. completed 데이터가 없으면 1개월 이전 데이터는 수집 안함
                        if (!this.latestCompletedDate) {
                            const oneMonthAgo = new Date();
                            oneMonthAgo.setMonth(oneMonthAgo.getMonth() - 1);

                            if (pageOldestDate < oneMonthAgo) {
                                console.log(`\n현재 페이지 최소 날짜(${pageOldestDate.toISOString().split('T')[0]})가 1개월 이전 - 수집 종료`);
                                return { items: newItems, shouldStop: true };
                            }
                        }
                    }
                }
            }

            return {
                items: newItems,
                allItems: items,  // 전체 항목 (noDb 모드용)
                shouldStop: false
            };

        } catch (error) {
            console.error(`페이지 ${pageNum} 수집 오류:`, error.message);
            this.stats.errors++;

            // 404 오류나 페이지 닫힘 오류는 상위로 전파
            if (error.message.includes('404') || error.message.includes('closed') || error.message.includes('Target')) {
                throw error;
            }

            return { items: [], allItems: [], shouldStop: false };
        }
    }

    /**
     * 메인 수집 프로세스
     */
    async collect() {
        const startTime = Date.now();
        const allNewItems = [];
        const allItems = [];  // 모든 항목 저장 (noDb 모드용)

        try {
            console.log('\n' + '='.repeat(60));
            console.log(`리스트 수집 시작: ${this.config.siteName} (${this.siteCode})`);
            console.log('='.repeat(60));
            console.log(`수집 범위: ${this.startPage}페이지 ~ ${this.maxPages}페이지`);
            console.log(`URL: ${this.config.listUrl}`);

            // 초기화
            await this.connectDB();
            await this.initBrowser();

            // 페이지별 수집
            for (let page = this.startPage; page <= this.maxPages; page++) {
                try {

                    console.log("GO TO PAGE", page)
                    const result = await this.collectPage(page);

                    if (result.items.length > 0) {
                        allNewItems.push(...result.items);
                    }

                    // noInsert 모드일 때는 모든 항목 저장
                    if (this.noInsert && result.allItems) {
                        allItems.push(...result.allItems);
                    }

                    if (result.shouldStop) {
                        break;
                    }

                    // 페이지 간 대기
                    if (page < this.maxPages) {
                        await this.page.waitForTimeout(1000);
                    }
                } catch (pageError) {
                    console.error(`페이지 ${page} 수집 오류:`, pageError.message);
                    this.stats.errors++;

                    // 페이지가 닫혔거나 404 오류인 경우 재시작 시도
                    if (pageError.message.includes('closed') || pageError.message.includes('404')) {
                        console.log('브라우저 페이지 재시작 시도...');

                        try {
                            // 현재 페이지 닫기
                            if (this.page && !this.page.isClosed()) {
                                await this.page.close().catch(() => { });
                            }

                            // 새 페이지 생성
                            this.page = await this.context.newPage();

                            // 콘솔 로그 핸들러 재설정
                            this.page.on('console', msg => {
                                if (this.verbose) {
                                    console.log('[브라우저 콘솔]:', msg.text());
                                }
                            });

                            console.log('브라우저 페이지 재시작 완료');

                            // 첫 페이지로 다시 이동
                            await this.page.goto(this.config.listUrl, {
                                waitUntil: 'networkidle',
                                timeout: 30000
                            });

                            continue;
                        } catch (restartError) {
                            console.error('브라우저 재시작 실패:', restartError.message);
                            break;
                        }
                    }

                    // 연속 3번 오류 시 중단
                    if (this.stats.errors >= 3) {
                        console.error('연속된 오류로 수집 중단');
                        break;
                    }
                }
            }

            // 처리 시간 계산
            const elapsedTime = Math.round((Date.now() - startTime) / 1000);

            // 통계 출력
            console.log('\n' + '='.repeat(60));
            console.log('수집 완료');
            console.log('='.repeat(60));
            console.log(`처리 시간: ${elapsedTime}초`);
            console.log(`페이지: ${this.stats.pages}개`);
            console.log(`전체 항목: ${this.stats.totalItems}개`);
            console.log(`신규: ${this.stats.newItems}개`);
            console.log(`중복: ${this.stats.duplicates}개`);
            console.log(`오류: ${this.stats.errors}개`);

            // 처리 로그 저장
            if (this.db) {
                await this.db.execute(
                    `INSERT INTO homepage_gosi_processing_log 
                    (run_date, site_code, total_checked, new_found, duplicates, 
                     list_collection_time, pages_collected) 
                    VALUES (CURDATE(), ?, ?, ?, ?, ?, ?)`,
                    [
                        this.siteCode,
                        this.stats.totalItems,
                        this.stats.newItems,
                        this.stats.duplicates,
                        elapsedTime,
                        this.stats.pages
                    ]
                );
            }

            // JSON 결과 출력 (파이프라인용)
            const result = {
                siteCode: this.siteCode,
                siteName: this.config.siteName,
                stats: this.stats,
                newItems: allNewItems,
                allItems: this.noInsert ? allItems : undefined,  // noInsert 모드면 전체 항목도 포함
                elapsedTime: elapsedTime
            };

            console.log('\nJSON_OUTPUT_START');
            console.log(JSON.stringify(result));
            console.log('JSON_OUTPUT_END');

        } catch (error) {
            console.error('치명적 오류:', error);
            process.exit(1);

        } finally {
            // 정리
            if (this.browser) await this.browser.close();
            if (this.db) await this.db.end();
        }
    }
}

// CLI 인터페이스
const argv = yargs
    .usage('사용법: $0 <site_code> [options]')
    .command('$0 <site_code>', '사이트 리스트 수집', (yargs) => {
        yargs.positional('site_code', {
            describe: '사이트 코드 (예: anseong, cs, cwg)',
            type: 'string'
        });
    })
    .option('pages', {
        alias: 'p',
        describe: '수집할 마지막 페이지 번호',
        type: 'number',
        default: 5
    })
    .option('start-page', {
        describe: '수집을 시작할 페이지 번호',
        type: 'number',
        default: 1
    })
    .option('verbose', {
        alias: 'v',
        describe: '상세 로그 출력',
        type: 'boolean',
        default: false
    })
    .option('test', {
        alias: 't',
        describe: '테스트 모드 (브라우저 표시)',
        type: 'boolean',
        default: false
    })
    .option('insert', {
        describe: 'DB INSERT 활성화',
        type: 'boolean',
        default: true
    })
    .help()
    .alias('help', 'h')
    .argv;

// 실행
if (argv.site_code) {
    const noInsertOption = !argv.insert;  // --no-insert는 argv.insert를 false로 만듦

    const collector = new HomepageGosiListCollector(argv.site_code, {
        startPage: argv.startPage || argv['start-page'],
        pages: argv.pages,
        verbose: argv.verbose,
        test: argv.test,
        noInsert: noInsertOption  // --no-insert 옵션 처리
    });

    collector.collect().catch(error => {
        console.error('실행 오류:', error);
        process.exit(1);
    });
} else {
    yargs.showHelp();
}