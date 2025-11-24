#!/usr/bin/env node

/**
 * Jeju Province Announcement Scraper
 * 
 * 특징:
 * 1. Vue.js 기반 동적 컨텐츠 로딩
 * 2. 팝업창으로 상세 내용 표시
 * 3. 테이블 구조: 번호, 구분, 제목, 부서, 날짜, 조회수
 */

const { chromium } = require('playwright');
const axios = require('axios');
const https = require('https');
const fs = require('fs-extra');
const path = require('path');
const moment = require('moment');
const sanitize = require('sanitize-filename');
const yargs = require('yargs');
const config = require('./config');
const FailureLogger = require('./failure_logger');
const UrlManager = require('./url_manager');

class JejuAnnouncementScraper {
    constructor(options = {}) {
        this.targetYear = options.targetYear || new Date().getFullYear();
        this.baseOutputDir = options.outputDir || 'scraped_data';
        this.siteCode = options.siteCode || 'jeju';
        this.outputDir = path.join(this.baseOutputDir, this.siteCode);
        this.baseUrl = options.baseUrl || 'http://sido.jeju.go.kr/citynet/jsp/sap/SAPGosiBizProcess.do?command=searchList&flag=gosiGL&svp=Y&sido=&conIfmStdt=2025-01-01&conIfmEnddt=2025-12-31';
        this.browser = null;
        this.context = null;
        this.page = null;
        this.processedTitles = new Set();
        this.counter = 1;
        this.goPage = options.goPage || null;
        this.targetDate = options.targetDate || null;
    }

    /**
     * 상세 URL만 추출하여 DB에 저장 (다운로드 없음)
     * @param {string} batchDate - 배치 날짜 (선택)
     * @returns {Promise<{totalCount: number, pageCount: number, savedCount: number}>}
     */
    async extractAndSaveUrls(batchDate = null) {
        try {
            await this.initBrowser();

            let currentPage = 1;
            let totalCount = 0;
            let savedCount = 0;
            let consecutiveEmptyPages = 0;
            const maxConsecutiveEmptyPages = 3;

            console.log(`\n=== 상세 URL 추출 및 저장 시작 ===`);
            console.log(`사이트 코드: ${this.siteCode}`);

            if (this.targetDate) {
                const moment = require('moment');
                const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                console.log(`대상 날짜: ${targetMoment.format('YYYY-MM-DD')}`);
            } else {
                console.log(`대상 연도: ${this.targetYear}`);
            }

            while (consecutiveEmptyPages < maxConsecutiveEmptyPages) {
                try {
                    console.log(`\n페이지 ${currentPage} 확인 중...`);
                    const announcements = await this.getAnnouncementList(currentPage);

                    if (!announcements || announcements.length === 0) {
                        consecutiveEmptyPages++;
                        currentPage++;
                        continue;
                    }

                    consecutiveEmptyPages = 0;
                    let pageValidCount = 0;
                    let shouldStop = false;

                    for (const announcement of announcements) {
                        try {
                            // 날짜 확인
                            const listDate = this.extractDate(announcement.dateText || announcement.date);

                            // targetDate가 설정된 경우
                            if (this.targetDate) {
                                const moment = require('moment');
                                const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                                if (listDate && listDate.isBefore(targetMoment)) {
                                    console.log(`대상 날짜(${targetMoment.format('YYYY-MM-DD')}) 이전 공고 발견. 추출 중단.`);
                                    shouldStop = true;
                                    break;
                                }
                            }
                            // targetYear만 설정된 경우
                            else if (listDate && listDate.year() < this.targetYear) {
                                console.log(`대상 연도(${this.targetYear}) 이전 공고 발견. 추출 중단.`);
                                shouldStop = true;
                                break;
                            }

                            // 상세 URL 생성
                            const detailUrl = await this.buildDetailUrl(announcement);
                            if (!detailUrl) continue;

                            // 날짜 형식 정규화 (YYYY.MM.DD or YYYY/MM/DD → YYYY-MM-DD)
                            let normalizedDate = announcement.dateText || announcement.date || '';
                            if (normalizedDate) {
                                normalizedDate = normalizedDate.replace(/\./g, '-').replace(/\//g, '-');
                            }

                            // URL DB 저장
                            const saved = await UrlManager.saveDetailUrl({
                                site_code: this.siteCode,
                                title: announcement.title || announcement.subject || 'Unknown',
                                list_url: this.baseUrl,
                                detail_url: detailUrl,
                                list_date: normalizedDate,
                                batch_date: batchDate
                            });

                            if (saved) {
                                savedCount++;
                                const title = announcement.title || announcement.subject || 'Unknown';
                                console.log(`  ✓ ${title.substring(0, 50)}...`);
                            }
                            pageValidCount++;
                        } catch (error) {
                            continue;
                        }
                    }

                    totalCount += pageValidCount;
                    console.log(`페이지 ${currentPage}: ${pageValidCount}개 URL 추출 (저장: ${savedCount}개)`);

                    if (shouldStop) {
                        console.log(`조건 불일치로 추출 중단.`);
                        break;
                    }

                    currentPage++;
                    await this.delay(1000);
                } catch (pageError) {
                    consecutiveEmptyPages++;
                    currentPage++;
                }
            }

            console.log(`\n=== URL 추출 완료 ===`);
            console.log(`총 URL: ${totalCount}개, 저장: ${savedCount}개`);

            return { totalCount, savedCount, pageCount: currentPage - 1 };
        } catch (error) {
            console.error('URL 추출 중 오류:', error.message);
            throw error;
        } finally {
            await this.cleanup();
        }
    }

    /**
     * 기존 폴더의 제목들을 로드하여 중복 체크
     */
    async loadExistingTitles() {
        try {
            if (!await fs.pathExists(this.outputDir)) {
                return;
            }

            const items = await fs.readdir(this.outputDir);
            for (const item of items) {
                // 001_형식의 폴더명에서 제목 부분 추출
                const match = item.match(/^\d{3}_(.+)$/);
                if (match) {
                    const title = match[1];
                    // 폴더명은 sanitize된 상태이므로 원래 제목과 다를 수 있음
                    // 하지만 어느 정도 중복 감지에 도움이 됨
                    this.processedTitles.add(title);
                }
            }
            
            console.log(`기존 폴더에서 ${this.processedTitles.size}개의 제목 로드`);
        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => {});

            console.log('기존 제목 로드 중 오류:', error.message);
        }
    }

    /**
     * 기존 폴더에서 가장 큰 카운터 번호 찾기
     */
    async getLastCounterNumber() {
        try {
            // outputDir이 존재하지 않으면 0 반환
            if (!await fs.pathExists(this.outputDir)) {
                return 0;
            }

            const items = await fs.readdir(this.outputDir);
            let maxNumber = 0;

            for (const item of items) {
                // 001_형식의 폴더명에서 숫자 추출
                const match = item.match(/^(\d{3})_/);
                if (match) {
                    const num = parseInt(match[1], 10);
                    if (num > maxNumber) {
                        maxNumber = num;
                    }
                }
            }

            return maxNumber;
        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => {});

            console.log('기존 카운터 번호 확인 중 오류:', error.message);
            return 0;
        }
    }



    async initBrowser() {
        console.log('브라우저 초기화 중...');

        const maxRetries = 3;
        let retries = 0;

        while (retries < maxRetries) {
            try {
                this.browser = await chromium.launch({
                    headless: config.browser.devMode ? false : true,
                    args: config.browser.launchOptions.args,
                    timeout: config.browser.launchOptions.timeout
                });

                this.context = await this.browser.newContext({
                    userAgent: config.security.userAgent,
                    viewport: { width: 1280, height: 720 },
                    ignoreHTTPSErrors: config.browser.launchOptions.ignoreHTTPSErrors
                });

                // 팝업 핸들러 설정
                this.context.on('page', async (popup) => {
                    console.log('팝업 감지:', popup.url());
                    this.currentPopup = popup;
                });

                this.page = await this.context.newPage();

                this.page.setDefaultTimeout(config.browser.timeouts.default);
                this.page.setDefaultNavigationTimeout(config.browser.timeouts.navigation);

                console.log('브라우저 초기화 완료');
                return;

            } catch (error) {
                // 실패 공고 DB 기록
                await FailureLogger.logFailedAnnouncement({
                    site_code: this.siteCode,
                    title: announcement?.title || 'Unknown',
                    url: announcement?.link || announcement?.url,
                    detail_url: announcement?.detailUrl,
                    error_type: 'error',
                    error_message: error.message
                }).catch(logErr => {});

                retries++;
                console.error(`브라우저 초기화 실패 (시도 ${retries}/${maxRetries}):`, error.message);

                if (this.browser) {
                    try {
                        await this.browser.close();
                    } catch (closeError) {
                        // 실패 공고 DB 기록
                        await FailureLogger.logFailedAnnouncement({
                            site_code: this.siteCode,
                            title: announcement?.title || 'Unknown',
                            url: announcement?.link || announcement?.url,
                            detail_url: announcement?.detailUrl,
                            error_type: 'closeError',
                            error_message: closeError.message
                        }).catch(logErr => {});

                        console.warn('브라우저 종료 중 오류:', closeError.message);
                    }
                }

                if (retries >= maxRetries) {
                    throw new Error(`브라우저 초기화 ${maxRetries}회 실패: ${error.message}`);
                }

                await this.delay(2000 * retries);
            }
        }
    }

    async loadExistingTitles() {
        try {
            if (await fs.pathExists(this.outputDir)) {
                const existingFolders = await fs.readdir(this.outputDir);
                console.log(`📁 기존 폴더 ${existingFolders.length}개 발견`);

                existingFolders.forEach(folderName => {
                    const match = folderName.match(/^\d{3}_(.+)$/);
                    if (match) {
                        const existingTitle = match[1];
                        this.processedTitles.add(existingTitle);

                        const folderNumber = parseInt(folderName.substring(0, 3));
                        if (folderNumber >= this.counter) {
                            this.counter = folderNumber + 1;
                        }
                    }
                });

                console.log(`📝 기존 처리된 제목 ${this.processedTitles.size}개 로드 완료`);
                console.log(`🔢 다음 카운터: ${this.counter}`);
            } else {
                console.log('📂 신규 출력 디렉토리 생성');
            }
        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => {});

            console.log(`📁 기존 제목 로드 실패 (정상 - 신규 시작): ${error.message}`);
        }
    }

    async scrape() {
        try {
            await this.initBrowser();
            await fs.ensureDir(this.outputDir);
            
            // 기존 폴더에서 마지막 카운터 번호를 가져와서 그 다음부터 시작
            const lastCounter = await this.getLastCounterNumber();
            this.counter = lastCounter + 1;
            console.log(`시작 카운터 번호: ${this.counter} (기존 최대 번호: ${lastCounter})`);
            
            // 기존 폴더의 제목들을 processedTitles에 추가
            await this.loadExistingTitles();
            await this.loadExistingTitles();

            let currentPage = this.goPage || 1;
            let shouldContinue = true;
            let consecutiveErrors = 0;
            const maxConsecutiveErrors = 5;

            console.log(`\n=== 스크래핑 시작 ===`);
            if (this.targetDate) {
                const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                console.log(`대상 날짜: ${targetMoment.format('YYYY-MM-DD')} (${this.targetDate} 이후 공고만 수집)`);
            } else {
                console.log(`대상 연도: ${this.targetYear}`);
            }
            if (this.goPage) {
                console.log(`시작 페이지: ${this.goPage}`);
            }
            console.log(`사이트 코드: ${this.siteCode}`);
            console.log(`기본 URL: ${this.baseUrl}`);
            console.log(`출력 디렉토리: ${this.outputDir}`);

            while (shouldContinue) {
                try {
                    console.log(`\n--- 페이지 ${currentPage} 처리 중 ---`);

                    const announcements = await this.getAnnouncementList(currentPage);

                    if (!announcements || announcements.length === 0) {
                        console.log('더 이상 공고가 없습니다. 스크래핑 종료.');
                        break;
                    }

                    consecutiveErrors = 0;
                    for (const announcement of announcements) {
                        try {
                            const shouldStop = await this.processAnnouncement(announcement);
                            if (shouldStop) {
                                console.log(`\n${this.targetYear}년 이전 공고 발견. 스크래핑 종료.`);
                                shouldContinue = false;
                                break;
                            }
                        } catch (announcementError) {
                            // 실패 공고 DB 기록
                            await FailureLogger.logFailedAnnouncement({
                                site_code: this.siteCode,
                                title: announcement?.title || 'Unknown',
                                url: announcement?.link || announcement?.url,
                                detail_url: announcement?.detailUrl,
                                error_type: 'announcementError',
                                error_message: announcementError.message
                            }).catch(logErr => {});

                            console.error(`공고 처리 중 오류 (${announcement.title}):`, announcementError.message);
                            continue;
                        }
                    }

                    if (shouldContinue) {
                        currentPage++;
                        await this.delay(1000);
                    }

                } catch (pageError) {
                    // 실패 공고 DB 기록
                    await FailureLogger.logFailedAnnouncement({
                        site_code: this.siteCode,
                        title: announcement?.title || 'Unknown',
                        url: announcement?.link || announcement?.url,
                        detail_url: announcement?.detailUrl,
                        error_type: 'pageError',
                        error_message: pageError.message
                    }).catch(logErr => {});

                    consecutiveErrors++;
                    console.error(`페이지 ${currentPage} 처리 중 오류 (${consecutiveErrors}/${maxConsecutiveErrors}):`, pageError.message);

                    if (consecutiveErrors >= maxConsecutiveErrors) {
                        console.error('연속 오류 한도 초과. 스크래핑을 중단합니다.');
                        break;
                    }

                    await this.delay(5000 * consecutiveErrors);
                    currentPage++;
                }
            }

        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => {});

            console.error('스크래핑 중 치명적 오류 발생:', error.message);
            console.error('스택 트레이스:', error.stack);
        } finally {
            await this.cleanup();
        }
    }

    async getAnnouncementList(pageNum) {
        const maxRetries = 3;
        let retries = 0;

        while (retries < maxRetries) {
            try {
                // 페이지로 이동 - sido.jeju.go.kr은 다른 페이지네이션 방식 사용
                const listUrl = pageNum === 1 ? this.baseUrl : this.baseUrl;
                console.log(`리스트 URL: ${listUrl} (페이지 ${pageNum})`);

                if (!this.browser || !this.page || this.page.isClosed()) {
                    console.log('브라우저 연결이 끊어져 재초기화합니다...');
                    await this.initBrowser();
                }

                await this.page.goto(listUrl, {
                    waitUntil: 'networkidle',
                    timeout: 30000
                });

                // 페이지 로딩 대기
                await this.page.waitForTimeout(2000);

                // 페이지 변경 (sido.jeju.go.kr 페이지네이션)
                if (pageNum > 1) {
                    // goPage 함수 호출
                    const pageChangeSuccess = await this.page.evaluate((targetPage) => {
                        if (typeof goPage === 'function') {
                            goPage(targetPage);
                            return true;
                        }
                        return false;
                    }, pageNum);

                    if (pageChangeSuccess) {
                        console.log(`페이지 ${pageNum}로 이동 중...`);
                        await this.page.waitForTimeout(3000);
                    }
                }

                // 테이블에서 데이터 추출
                const announcements = await this.page.evaluate(() => {
                    const rows = document.querySelectorAll('tbody tr');
                    const results = [];

                    rows.forEach((row) => {
                        // onclick 속성이 있는 행만 처리 (실제 데이터 행)
                        const onclickAttr = row.getAttribute('onclick');
                        if (onclickAttr && onclickAttr.includes('viewData')) {
                            const cells = row.querySelectorAll('td');
                            if (cells.length >= 5) {
                                // viewData 파라미터 추출
                                const match = onclickAttr.match(/viewData\('(\d+)','([A-Z])'\)/);
                                let sno = '';
                                let gosiGbn = '';
                                if (match) {
                                    sno = match[1];
                                    gosiGbn = match[2];
                                }

                                const noticeNo = cells[0].textContent.trim();
                                const title = cells[1].textContent.trim();
                                const department = cells[2].textContent.trim();
                                const dateText = cells[3].textContent.trim();
                                const views = cells[4].textContent.trim();

                                // 유효한 데이터인지 확인 (번호가 있고 제목이 있는 경우)
                                if (noticeNo && title && noticeNo.match(/\d{4}-\d+/)) {
                                    results.push({
                                        noticeNo,
                                        sno,
                                        gosiGbn,
                                        title,
                                        department,
                                        dateText,
                                        views,
                                        listDate: dateText
                                    });
                                }
                            }
                        }
                    });

                    return results;
                });

                console.log(`리스트에서 ${announcements.length}개 공고 발견`);
                return announcements;

            } catch (error) {
                // 실패 공고 DB 기록
                await FailureLogger.logFailedAnnouncement({
                    site_code: this.siteCode,
                    title: announcement?.title || 'Unknown',
                    url: announcement?.link || announcement?.url,
                    detail_url: announcement?.detailUrl,
                    error_type: 'error',
                    error_message: error.message
                }).catch(logErr => {});

                retries++;
                console.error(`리스트 가져오기 실패 (시도 ${retries}/${maxRetries}):`, error.message);

                if (retries >= maxRetries) {
                    console.error('최대 재시도 횟수 초과. 빈 배열 반환.');
                    return [];
                }

                await this.delay(2000 * retries);
            }
        }
    }

    async processAnnouncement(announcement) {
        try {
            console.log(`\n처리 중: ${announcement.title}`);

            // 날짜 확인
            const listDate = this.extractDate(announcement.dateText);

            if (this.targetDate) {
                const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                if (listDate && listDate.isBefore(targetMoment)) {
                    console.log(`리스트 날짜 ${listDate.format('YYYY-MM-DD')}가 대상 날짜(${targetMoment.format('YYYY-MM-DD')}) 이전입니다.`);
                    return true;
                }
            } else if (listDate && listDate.year() < this.targetYear) {
                console.log(`리스트 날짜 ${listDate.format('YYYY-MM-DD')}가 대상 연도(${this.targetYear}) 이전입니다.`);
                return true;
            }

            // 중복 체크
            const sanitizedTitle = sanitize(announcement.title).substring(0, 100);

            if (this.processedTitles.has(announcement.title) || this.processedTitles.has(sanitizedTitle)) {
                console.log(`❌ 중복 게시물 스킵: ${announcement.title}`);
                // 중복 게시물이어도 날짜 체크는 수행 (targetDate 이전인지 확인)
                // 많은 중복이 연속으로 나타날 경우 종료 조건 판단을 위함
                if (this.targetDate && listDate) {
                    const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                    if (listDate.isBefore(targetMoment)) {
                        console.log(`중복 게시물이지만 날짜가 ${listDate.format('YYYY-MM-DD')}로 대상 날짜 이전입니다. 종료 신호.`);
                        return true; // 스크래핑 중단
                    }
                }
                return false;
            }

            // 상세 내용 가져오기
            const detailContent = await this.getDetailContent(announcement);
            if (!detailContent) {
                console.log('상세 페이지 접근 실패');
                return false;
            }

            // 저장
            await this.saveAnnouncement(announcement, detailContent);

            // sanitize된 제목을 저장하여 정확한 중복 체크
            const sanitizedTitleForCheck = sanitize(announcement.title).substring(0, 100);
            this.processedTitles.add(sanitizedTitleForCheck);
            console.log(`처리 완료: ${announcement.title}`);

            return false;

        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => {});

            console.error(`공고 처리 중 오류 (${announcement.title}):`, error);
            return false;
        }
    }

    async getDetailContent(announcement) {
        const maxRetries = 3;
        let retries = 0;

        while (retries < maxRetries) {
            try {
                console.log('상세 내용 가져오기 시작...');

                const noticeNo = announcement.noticeNo;
                const sno = announcement.sno;
                const gosiGbn = announcement.gosiGbn;

                // sido.jeju.go.kr 상세 페이지 직접 호출
                if (sno && gosiGbn) {
                    const viewUrl = `http://sido.jeju.go.kr/citynet/jsp/sap/SAPGosiBizProcess.do?command=searchDetail&flag=gosiGL&svp=Y&sido=&sno=${sno}&gosiGbn=${gosiGbn}`;
                    console.log(`상세 페이지 직접 호출: ${viewUrl}`);

                    // 상세 페이지로 이동
                    await this.page.goto(viewUrl, {
                        waitUntil: 'networkidle',
                        timeout: 30000
                    });

                    await this.page.waitForTimeout(2000);

                    // 상세 페이지에서 콘텐츠 추출
                    const viewContent = await this.page.evaluate(() => {
                        // 상세 내용 찾기
                        let content = '';
                        const attachments = [];

                        // 테이블에서 내용 찾기
                        const tables = document.querySelectorAll('table');
                        for (const table of tables) {
                            const rows = table.querySelectorAll('tr');
                            for (const row of rows) {
                                const headers = row.querySelectorAll('td.h_tb');
                                for (const header of headers) {
                                    const headerText = header.textContent.trim();
                                    if (headerText === '내 용' || headerText === '내용' || 
                                        headerText.includes('내용') || headerText === '공고문' || 
                                        headerText === '상세내용' || headerText === '본문') {
                                        // 다음 td에서 내용 추출
                                        const nextCell = header.nextElementSibling;
                                        if (nextCell) {
                                            const cellContent = nextCell.innerText || nextCell.textContent;
                                            if (cellContent && cellContent.trim().length > 20) {
                                                content = cellContent.trim();
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // 첨부파일 찾기
                        const fileLinks = document.querySelectorAll('a[href*="download"], a[onclick*="download"], a[onclick*="file"]');
                        fileLinks.forEach(link => {
                            const fileName = link.textContent.trim();
                            let downloadUrl = null;
                            
                            // onclick에서 다운로드 정보 추출
                            const onclick = link.getAttribute('onclick');
                            if (onclick) {
                                // download 함수 파라미터 추출
                                const fidMatch = onclick.match(/fid=([^&'"]+)/);
                                const indexMatch = onclick.match(/index=(\d+)/);
                                if (fidMatch) {
                                    const fid = fidMatch[1];
                                    const index = indexMatch ? indexMatch[1] : '0';
                                    downloadUrl = `http://sido.jeju.go.kr/citynet/jsp/cmm/attach/download.jsp?mode=download&fid=${fid}&index=${index}`;
                                }
                            } else if (link.href && !link.href.includes('javascript:')) {
                                downloadUrl = link.href;
                            }

                            if (fileName && downloadUrl) {
                                attachments.push({
                                    name: fileName,
                                    url: downloadUrl
                                });
                            }
                        });

                        // content가 없으면 전체 body 텍스트에서 추출
                        if (!content) {
                            const body = document.body;
                            if (body) {
                                const fullText = body.innerText || body.textContent || '';
                                // 불필요한 부분 제거
                                const lines = fullText.split('\n');
                                const contentLines = [];
                                let startCapture = false;
                                for (const line of lines) {
                                    if (line.includes('내용') || line.includes('내 용')) {
                                        startCapture = true;
                                        continue;
                                    }
                                    if (startCapture && line.trim()) {
                                        if (line.includes('첨부파일') || line.includes('목록')) {
                                            break;
                                        }
                                        contentLines.push(line);
                                    }
                                }
                                if (contentLines.length > 0) {
                                    content = contentLines.join('\n').trim();
                                }
                            }
                        }

                        return {
                            content: content,
                            attachments: attachments
                        };
                    });

                    // 상세 페이지 콘텐츠가 유효하면 반환
                    if (viewContent && viewContent.content && viewContent.content.length > 20) {
                        console.log('상세 페이지에서 콘텐츠 획득 성공');
                        return {
                            url: viewUrl,
                            content: viewContent.content,
                            date: this.extractDate(announcement.dateText),
                            attachments: viewContent.attachments || []
                        };
                    } else {
                        console.log('상세 페이지에서 콘텐츠를 찾을 수 없음');
                    }
                }

                // viewData 함수 호출로 상세 페이지 열기 시도
                if (sno && gosiGbn) {
                    const detailLoaded = await this.page.evaluate(({ sno, gosiGbn }) => {
                        // viewData 함수가 있으면 호출
                        if (typeof viewData === 'function') {
                            viewData(sno, gosiGbn);
                            return true;
                        }
                        return false;
                    }, { sno, gosiGbn });

                    if (detailLoaded) {
                        console.log('viewData 함수로 상세 페이지 열기 시도');
                        // 모달/팝업이 열릴 때까지 대기
                        await this.page.waitForTimeout(3000);
                    } else {
                        throw new Error('상세 페이지를 열 수 없습니다.');
                    }
                } else {
                    throw new Error('sno 또는 gosiGbn이 없습니다.');
                }

                // iframe 확인 및 처리
                let iframeContent = null;
                const frames = this.page.frames();
                console.log(`발견된 frame 수: ${frames.length}`);

                if (frames.length > 1) {
                    // iframe이 있는 경우
                    for (const frame of frames) {
                        if (frame !== this.page.mainFrame()) {
                            try {
                                // iframe 내부에서 콘텐츠 추출
                                iframeContent = await frame.evaluate(() => {
                                    const body = document.body;
                                    if (!body) return null;

                                    // 제목과 내용 추출
                                    let content = '';

                                    // 일반적인 콘텐츠 컨테이너 찾기
                                    const contentSelectors = [
                                        '.content', '#content', '.board-content',
                                        '.view-content', '.detail-content',
                                        'table', '.table-responsive', 'body'
                                    ];

                                    for (const selector of contentSelectors) {
                                        const elem = document.querySelector(selector);
                                        if (elem && elem.innerText && elem.innerText.length > 50) {
                                            content = elem.innerText;
                                            break;
                                        }
                                    }

                                    // 콘텐츠가 없으면 전체 body 텍스트 사용
                                    if (!content) {
                                        content = body.innerText || body.textContent || '';
                                    }

                                    // 첨부파일 찾기
                                    const attachments = [];
                                    const fileLinks = document.querySelectorAll('a[href*="download"], a[href*="Download"], a[href*="file"]');
                                    fileLinks.forEach(link => {
                                        const fileName = link.textContent.trim();
                                        const href = link.href;
                                        if (fileName && href && !href.includes('javascript:')) {
                                            attachments.push({
                                                name: fileName,
                                                url: href
                                            });
                                        }
                                    });

                                    return {
                                        content: content,
                                        attachments: attachments,
                                        url: window.location.href
                                    };
                                });

                                if (iframeContent && iframeContent.content) {
                                    console.log('iframe에서 콘텐츠 발견');
                                    break;
                                }
                            } catch (e) {
                                console.log('iframe 접근 오류:', e.message);
                            }
                        }
                    }
                }

                // iframe 콘텐츠가 있으면 반환
                if (iframeContent && iframeContent.content && iframeContent.content.length > 50) {
                    return {
                        url: iframeContent.url || `${this.baseUrl}#view_${noticeNo}`,
                        content: iframeContent.content,
                        date: this.extractDate(announcement.dateText),
                        attachments: iframeContent.attachments || []
                    };
                }

                // iframe이 없거나 콘텐츠가 없으면 메인 페이지에서 추출
                const content = await this.page.evaluate(() => {
                    // 상세 뷰 컨테이너 찾기
                    let mainContent = '';
                    const viewSelectors = [
                        '#viewContainer', '.view-container', '.detail-view',
                        '.modal-body', '.popup-content', '.dialog-content',
                        '.view-modal', '#viewModal', '.announcement-view',
                        '.modal.show .modal-content', '.modal-dialog .modal-body',
                        '.boardView', '.board-view', '.view-content'
                    ];

                    for (const selector of viewSelectors) {
                        const element = document.querySelector(selector);
                        if (element && element.innerText && element.innerText.length > 50) {
                            mainContent = element.innerText || element.textContent || '';
                            break;
                        }
                    }

                    // Vue 컴포넌트 데이터 확인
                    if (!mainContent && window.app && app.$data) {
                        const viewData = app.$data.viewData || app.$data.selectedItem || app.$data.currentView;
                        if (viewData) {
                            if (typeof viewData === 'string') {
                                mainContent = viewData;
                            } else if (viewData.content) {
                                mainContent = viewData.content;
                            } else if (viewData.notiContents) {
                                mainContent = viewData.notiContents;
                            } else if (viewData.html) {
                                // HTML 콘텐츠에서 텍스트 추출
                                const tempDiv = document.createElement('div');
                                tempDiv.innerHTML = viewData.html;
                                mainContent = tempDiv.innerText || tempDiv.textContent || '';
                            }
                        }
                    }

                    // AJAX로 로드된 영역 확인
                    if (!mainContent) {
                        const ajaxContent = document.querySelector('[data-ajax-content], .ajax-content, .dynamic-content');
                        if (ajaxContent) {
                            mainContent = ajaxContent.innerText || ajaxContent.textContent || '';
                        }
                    }

                    // 첨부파일 찾기
                    const attachments = [];

                    // 일반적인 첨부파일 링크
                    const fileLinks = document.querySelectorAll('a[href*="download"], a[href*="Download"], a[href*="file"], .file a, .attach a, .attachment a');
                    fileLinks.forEach(link => {
                        const fileName = link.textContent.trim();
                        let href = link.href;
                        const onclick = link.getAttribute('onclick');

                        // 상대 URL을 절대 URL로 변환
                        if (href && !href.startsWith('http')) {
                            href = new URL(href, 'https://www.jeju.go.kr').toString();
                        }

                        if (fileName && href && !href.includes('javascript:')) {
                            attachments.push({
                                name: fileName,
                                url: href,
                                onclick: onclick
                            });
                        }
                    });

                    // Vue 데이터에서 첨부파일 정보 확인
                    if (window.app && app.$data) {
                        const viewData = app.$data.viewData || app.$data.selectedItem;
                        if (viewData) {
                            // files 배열 확인
                            if (viewData.files && Array.isArray(viewData.files)) {
                                viewData.files.forEach(file => {
                                    let fileUrl = file.downloadUrl || file.url || file.filePath;
                                    if (fileUrl && !fileUrl.startsWith('http')) {
                                        fileUrl = 'https://www.jeju.go.kr' + fileUrl;
                                    }
                                    if (file.fileName || file.name) {
                                        attachments.push({
                                            name: file.fileName || file.name,
                                            url: fileUrl
                                        });
                                    }
                                });
                            }
                            // attachments 배열 확인
                            if (viewData.attachments && Array.isArray(viewData.attachments)) {
                                viewData.attachments.forEach(file => {
                                    let fileUrl = file.url || file.path;
                                    if (fileUrl && !fileUrl.startsWith('http')) {
                                        fileUrl = 'https://www.jeju.go.kr' + fileUrl;
                                    }
                                    if (file.name) {
                                        attachments.push({
                                            name: file.name,
                                            url: fileUrl
                                        });
                                    }
                                });
                            }
                        }
                    }

                    return {
                        content: mainContent.trim(),
                        attachments: attachments
                    };
                });

                // 모달 닫기 (있는 경우)
                await this.page.evaluate(() => {
                    // 모달 닫기 버튼 클릭
                    const closeButtons = document.querySelectorAll('.modal .close, .modal .btn-close, .modal [data-dismiss="modal"], .btn-cancel, .btn-back');
                    if (closeButtons.length > 0) {
                        closeButtons[0].click();
                    }

                    // Vue 함수로 닫기
                    if (window.app) {
                        if (typeof app.closeView === 'function') {
                            app.closeView();
                        } else if (typeof app.close === 'function') {
                            app.close();
                        } else if (app.$data) {
                            // 상태 초기화
                            app.$data.viewData = null;
                            app.$data.showModal = false;
                            app.$data.isViewMode = false;
                        }
                    }

                    // ESC 키 이벤트 트리거
                    const event = new KeyboardEvent('keydown', {
                        key: 'Escape',
                        keyCode: 27,
                        bubbles: true
                    });
                    document.dispatchEvent(event);
                });

                await this.page.waitForTimeout(500);

                return {
                    url: `${this.baseUrl}#view_${noticeNo}`,
                    content: content.content || `제목: ${announcement.title}\n구분: ${category}\n부서: ${announcement.department}\n날짜: ${announcement.dateText}`,
                    date: this.extractDate(announcement.dateText),
                    attachments: content.attachments
                };

            } catch (error) {
                // 실패 공고 DB 기록
                await FailureLogger.logFailedAnnouncement({
                    site_code: this.siteCode,
                    title: announcement?.title || 'Unknown',
                    url: announcement?.link || announcement?.url,
                    detail_url: announcement?.detailUrl,
                    error_type: 'error',
                    error_message: error.message
                }).catch(logErr => {});

                retries++;
                console.error(`상세 페이지 처리 실패 (시도 ${retries}/${maxRetries}):`, error.message);

                if (retries >= maxRetries) {
                    console.error('최대 재시도 횟수 초과. 기본 정보로 반환.');
                    // 실패시 기본 정보만 반환
                    return {
                        url: this.baseUrl,
                        content: `제목: ${announcement.title}\n구분: ${announcement.category}\n부서: ${announcement.department}\n날짜: ${announcement.dateText}`,
                        date: this.extractDate(announcement.dateText),
                        attachments: []
                    };
                }

                await this.delay(2000 * retries);
            }
        }
    }

    async saveAnnouncement(announcement, detailContent) {
        try {
            const sanitizedTitle = sanitize(announcement.title).substring(0, 100);
            const folderName = `${String(this.counter).padStart(3, '0')}_${sanitizedTitle}`;
            const folderPath = path.join(this.outputDir, folderName);

            await fs.ensureDir(folderPath);

            // 첨부파일 다운로드
            let downloadUrlInfo = {};
            if (detailContent.attachments && detailContent.attachments.length > 0) {
                downloadUrlInfo = await this.downloadAttachments(detailContent.attachments, folderPath);

                detailContent.attachments.forEach(attachment => {
                    const fileName = attachment.name;
                    if (downloadUrlInfo[fileName]) {
                        attachment.downloadInfo = downloadUrlInfo[fileName];
                    }
                });
            }

            // content.md 생성
            const contentMd = this.generateMarkdownContent(announcement, detailContent);
            await fs.writeFile(path.join(folderPath, 'content.md'), contentMd, 'utf8');

            this.counter++;

        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => {});

            console.error('공고 저장 실패:', error);
        }
    }

    async downloadAttachments(attachments, folderPath) {
        const downloadUrlInfo = {};
        try {
            const attachDir = path.join(folderPath, 'attachments');
            await fs.ensureDir(attachDir);

            console.log(`${attachments.length}개 첨부파일 다운로드 중...`);

            for (let i = 0; i < attachments.length; i++) {
                const attachment = attachments[i];
                const result = await this.downloadSingleAttachment(attachment, attachDir, i + 1);
                if (result) {
                    Object.assign(downloadUrlInfo, result);
                }
                await this.delay(500);
            }

        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => {});

            console.error('첨부파일 다운로드 실패:', error);
        }
        return downloadUrlInfo;
    }

    async downloadSingleAttachment(attachment, attachDir, index) {
        try {
            let downloadUrl = attachment.url;
            let fileName = attachment.name || `attachment_${index}`;

            // 상대 URL을 절대 URL로 변환
            if (downloadUrl && !downloadUrl.startsWith('http')) {
                downloadUrl = new URL(downloadUrl, 'http://sido.jeju.go.kr').toString();
            }

            if (!downloadUrl || !downloadUrl.startsWith('http')) {
                console.log(`유효하지 않은 다운로드 URL: ${downloadUrl}`);
                return {
                    [fileName]: {
                        originalUrl: attachment.url,
                        actualDownloadUrl: null,
                        error: 'Invalid URL'
                    }
                };
            }

            // 다운로드
            await this.downloadViaLink(downloadUrl, attachDir, fileName);

            return {
                [fileName]: {
                    originalUrl: attachment.url,
                    actualDownloadUrl: downloadUrl,
                    fileName: fileName
                }
            };
        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => {});

            console.error(`첨부파일 다운로드 실패 (${attachment.name}):`, error);
            return {
                [attachment.name || `attachment_${index}`]: {
                    originalUrl: attachment.url,
                    actualDownloadUrl: null,
                    error: error.message
                }
            };
        }
    }

    async downloadViaLink(url, attachDir, fileName) {
        try {
            const response = await axios({
                method: 'GET',
                url: url,
                responseType: 'stream',
                timeout: 30000,
                headers: {
                    'Accept': '*/*',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                },
                httpsAgent: new https.Agent({
                    rejectUnauthorized: false
                })
            });

            // Content-Disposition에서 파일명 추출
            const contentDisposition = response.headers['content-disposition'];
            if (contentDisposition) {
                // filename*=UTF-8'' 형식 먼저 확인 (RFC 5987)
                const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
                if (utf8Match && utf8Match[1]) {
                    fileName = decodeURIComponent(utf8Match[1]);
                } else {
                    // 일반 filename= 형식 확인
                    const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                    if (match && match[1]) {
                        fileName = match[1].replace(/['"]/g, '').trim();

                        // URL 인코딩된 경우 디코딩
                        if (fileName.includes('%')) {
                            try {
                                fileName = decodeURIComponent(fileName);
                            } catch (e) {
                                // 디코딩 실패시 그대로 사용
                            }
                        }
                        
                        // EUC-KR 또는 잘못된 인코딩 처리
                        if (fileName.includes('?') || /[\x80-\xFF]/.test(fileName)) {
                            try {
                                // ISO-8859-1로 인코딩된 것을 바이트로 변환 후 UTF-8로 디코딩
                                const bytes = [];
                                for (let i = 0; i < fileName.length; i++) {
                                    const code = fileName.charCodeAt(i);
                                    if (code <= 0xFF) {
                                        bytes.push(code);
                                    }
                                }
                                // Buffer를 사용하여 EUC-KR로 해석
                                const buffer = Buffer.from(bytes);
                                const iconv = require('iconv-lite');
                                fileName = iconv.decode(buffer, 'EUC-KR');
                            } catch (e) {
                                // 변환 실패시 원본 사용
                                console.log('파일명 인코딩 변환 실패:', e.message);
                            }
                        }
                    }
                }
            }

            const cleanFileName = sanitize(fileName, { replacement: '_' });
            const filePath = path.join(attachDir, cleanFileName);

            const writer = fs.createWriteStream(filePath);
            response.data.pipe(writer);

            return new Promise((resolve, reject) => {
                writer.on('finish', resolve);
                writer.on('error', reject);
            });

        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => {});

            throw new Error(`링크 다운로드 실패: ${error.message}`);
        }
    }

    generateMarkdownContent(announcement, detailContent) {
        const lines = [];

        lines.push(`**제목**: ${announcement.title}`);
        lines.push('');

        if (detailContent.url) {
            lines.push(`**원본 URL**: ${detailContent.url}`);
            lines.push('');
        }

        if (detailContent.date) {
            lines.push(`**작성일**: ${detailContent.date.format('YYYY-MM-DD')}`);
            lines.push('');
        } else if (announcement.dateText) {
            // 날짜 객체가 없으면 리스트의 원본 텍스트 사용
            lines.push(`**작성일**: ${announcement.dateText}`);
            lines.push('');
        }

        if (detailContent.content) {
            lines.push('**내용**:');
            lines.push('');
            lines.push(detailContent.content);
        }


        if (detailContent.attachments && detailContent.attachments.length > 0) {
            lines.push('');
            lines.push('**첨부파일**:');
            lines.push('');
            detailContent.attachments.forEach((att, i) => {
                let attachInfo = "";
                if (att.downloadInfo && att.downloadInfo.actualDownloadUrl) {
                    attachInfo = `${i + 1}. ${att.name}: ${att.downloadInfo.actualDownloadUrl}`;
                } else {
                    attachInfo = `${i + 1}. ${att.name}`;
                }
                lines.push(attachInfo);
                lines.push('');
            });
        }

        return lines.join('\n');
    }

        extractDate(dateText) {
        if (!dateText) return null;

        // 텍스트 정리
        let cleanText = dateText.trim();
        
        // "2025년 9월 30일(화) 16:51:34" 형식 처리
        const koreanDateMatch = cleanText.match(/(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일/);
        if (koreanDateMatch) {
            const [, year, month, day] = koreanDateMatch;
            cleanText = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
        }

        // "등록일\n2025-09-10" 같은 형식에서 날짜만 추출
        const dateMatch = cleanText.match(/(\d{4}[-.\\/]\d{1,2}[-.\\/]\d{1,2})/);
        if (dateMatch) {
            cleanText = dateMatch[1];
        }

        // 다양한 날짜 형식 시도

        // YY.MM.DD 형식 체크 (예: 24.12.31)
        const yymmddMatch = cleanText.match(/^(\d{2})\.(\d{1,2})\.(\d{1,2})$/);
        if (yymmddMatch) {
            // 2자리 연도를 4자리로 변환 (00-99 → 2000-2099)
            const year = '20' + yymmddMatch[1];
            const month = yymmddMatch[2].padStart(2, '0');
            const day = yymmddMatch[3].padStart(2, '0');
            cleanText = `${year}-${month}-${day}`;
        }
        
        const formats = [
            'YYYY-MM-DD',
            'YYYY.MM.DD',
            'YYYY/MM/DD',
            'MM-DD-YYYY',
            'MM.DD.YYYY',
            'MM/DD/YYYY'
        ];

        for (const format of formats) {
            const date = moment(cleanText, format, true);
            if (date.isValid()) {
                return date;
            }
        }

        // 자연어 형식 시도 (조심스럽게)
        const naturalDate = moment(cleanText);
        if (naturalDate.isValid() && cleanText.match(/\d{4}/)) {
            return naturalDate;
        }

        return null;
    }

    async delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    async cleanup() {
        if (this.browser) {
            try {
                if (this.context) {
                    await this.context.close();
                }

                await this.browser.close();
                console.log('\n브라우저 정리 완료');

            } catch (error) {
                // 실패 공고 DB 기록
                await FailureLogger.logFailedAnnouncement({
                    site_code: this.siteCode,
                    title: announcement?.title || 'Unknown',
                    url: announcement?.link || announcement?.url,
                    detail_url: announcement?.detailUrl,
                    error_type: 'error',
                    error_message: error.message
                }).catch(logErr => {});

                console.warn('브라우저 정리 중 오류:', error.message);
            }
        }

        console.log(`\n=== 스크래핑 완료 ===`);
        console.log(`처리된 공고 수: ${this.counter - 1}`);
        console.log(`출력 디렉토리: ${this.outputDir}`);
    }
}

// CLI 인터페이스
function setupCLI() {
    return yargs
        .option('year', {
            alias: 'y',
            type: 'number',
            description: '대상 연도',
            default: new Date().getFullYear()
        })
        .option('date', {
            alias: 'd',
            type: 'string',
            description: '대상 날짜 (YYYYMMDD 형식)',
            default: null
        })
        .option('go-page', {
            alias: 'g',
            type: 'number',
            description: '시작 페이지 번호',
            default: 1
        })
        .option('output', {
            alias: 'o',
            type: 'string',
            description: '출력 디렉토리',
            default: 'scraped_data'
        })
        .option('site', {
            alias: 's',
            type: 'string',
            description: '사이트 코드',
            default: 'jeju'
        })
        .option('url', {
            alias: 'u',
            type: 'string',
            description: '기본 URL',
            default: 'http://sido.jeju.go.kr/citynet/jsp/sap/SAPGosiBizProcess.do?command=searchList&flag=gosiGL&svp=Y&sido=&conIfmStdt=2025-01-01&conIfmEnddt=2025-12-31'
        })
        .option('count', {
            alias: 'c',
            type: 'boolean',
            description: 'URL만 추출하여 DB에 저장 (다운로드 없음)',
            default: false
        })
        .option('batch-date', {
            alias: 'b',
            type: 'string',
            description: '배치 날짜 (YYYY-MM-DD 형식)',
            default: null
        })
        .help()
        .argv;
}

// 메인 실행
async function main() {
    const argv = setupCLI();

    const scraper = new JejuAnnouncementScraper({
        targetYear: argv.year,
        targetDate: argv.date,
        goPage: argv.goPage,
        outputDir: argv.output,
        siteCode: argv.site,
        baseUrl: argv.url
    });

    // --count 옵션이 있으면 URL만 추출
    if (argv.count) {
        console.log('URL 추출 모드');
        const result = await scraper.extractAndSaveUrls(argv.batchDate);
        console.log(`완료: ${result.totalCount}개 URL, ${result.savedCount}개 저장`);
        
        const UrlManager = require('./url_manager');
        const moment = require('moment');
        const batchDate = argv.batchDate || moment().format('YYYY-MM-DD');
        const stats = await UrlManager.getStats(argv.site, batchDate);
        console.log(`DB 통계: 전체 ${stats.total}개, 완료 ${stats.scraped}개, 대기 ${stats.unscraped}개`);
    } else {
        await scraper.scrape();
    }
}

// 스크립트가 직접 실행될 때만 main 함수 호출
if (require.main === module) {
    main().catch(console.error);
}

module.exports = JejuAnnouncementScraper;