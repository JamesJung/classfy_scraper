#!/usr/bin/env node

/**
 * Node.js 기반 공고 스크래핑 시스템
 * 
 * 기능:
 * 1. 날짜 기반 필터링으로 지정 연도까지 스크래핑
 * 2. 리스트 -> 상세 페이지 처리
 * 3. 다양한 방식의 상세 페이지 접근 (URL, JavaScript)
 * 4. content.md 파일 생성 (본문만 추출)
 * 5. 첨부파일 다운로드 (링크, POST, JavaScript 방식)
 * 6. 중복 게시물 스킵
 * 7. 폴더 구조: 001_게시물이름/content.md, attachments/
 */

const { chromium } = require('playwright');
const cheerio = require('cheerio');
const axios = require('axios');
const fs = require('fs-extra');
const path = require('path');
const moment = require('moment');
const sanitize = require('sanitize-filename');
const yargs = require('yargs');
const config = require('./config');
const FailureLogger = require('./failure_logger');
const UrlManager = require('./url_manager');

class AnnouncementScraper {
    constructor(options = {}) {
        this.targetYear = options.targetYear || new Date().getFullYear();
        this.baseOutputDir = options.outputDir || 'scraped_data';
        this.siteCode = options.siteCode || 'default';
        this.outputDir = path.join(this.baseOutputDir, this.siteCode); // 사이트별 폴더 생성
        this.baseUrl = options.baseUrl;
        this.listSelector = options.listSelector;
        this.titleSelector = options.titleSelector || 'td:nth-child(2) a';
        this.dateSelector = options.dateSelector || 'td:last-child';
        this.browser = null;
        this.page = null;
        this.processedTitles = new Set();
        this.counter = 1;
        this.dateFormat = options.dateFormat || 'YYYY-MM-DD';
        this.options = options;
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
     * 브라우저 초기화
     */
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
                // Playwright로 브라우저 실행
                this.browser = await chromium.launch({
                    headless: config.browser.devMode ? false : true,  // Playwright는 boolean만 지원
                    args: config.browser.launchOptions.args,
                    timeout: config.browser.launchOptions.timeout
                });

                // 새 컨텍스트 생성
                this.context = await this.browser.newContext({
                    userAgent: config.security.userAgent,
                    viewport: { width: 1280, height: 720 },
                    ignoreHTTPSErrors: config.browser.launchOptions.ignoreHTTPSErrors
                });

                this.page = await this.context.newPage();

                // 타임아웃 설정
                this.page.setDefaultTimeout(config.browser.timeouts.default);
                this.page.setDefaultNavigationTimeout(config.browser.timeouts.navigation);

                // 에러 이벤트 리스너 추가
                this.browser.on('disconnected', () => {
                    console.warn('브라우저 연결이 끊어졌습니다.');
                });

                this.page.on('crash', () => {
                    console.warn('페이지 크래시 발생');
                });

                this.page.on('console', (msg) => {
                    // console.log, console.warn, console.error 등 모든 브라우저 콘솔 메시지를 처리
                    //console.log(`[브라우저 콘솔]: ${msg.text()}`);
                });

                this.page.on('pageerror', (error) => {
                    console.warn('페이지 JavaScript 오류:', error.message);
                });

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

                // 재시도 전 대기
                await this.delay(2000 * retries);
            }
        }
    }

    /**
     * 기존 제목들 로드
     */
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

                        // 카운터 업데이트 (기존 폴더 중 가장 큰 번호 + 1)
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

    /**
     * 메인 스크래핑 프로세스
     */
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

                    // 성공적으로 데이터를 가져온 경우 에러 카운트 리셋
                    consecutiveErrors = 0;
                    for (const announcement of announcements) {
                        try {
                            const shouldStop = await this.processAnnouncement(announcement);
                            if (shouldStop) {
                                console.log(`\\n${this.targetYear}년 이전 공고 발견. 스크래핑 종료.`);
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
                            // 개별 공고 오류는 전체 프로세스를 중단하지 않음
                            continue;
                        }
                    }

                    if (shouldContinue) {
                        currentPage++;
                        await this.delay(1000); // 1초 대기
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

                    // 오류 발생시 더 긴 대기 시간
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

    /**
     * 공고 리스트 가져오기
     */
    async getAnnouncementList(pageNum) {
        const maxRetries = 3;
        let retries = 0;

        while (retries < maxRetries) {
            try {
                const listUrl = this.buildListUrl(pageNum);
                console.log(`리스트 URL: ${listUrl}`);

                // 브라우저나 페이지가 종료된 경우 재초기화
                if (!this.browser || !this.page || this.page.isClosed()) {
                    console.log('브라우저 연결이 끊어져 재초기화합니다...');
                    await this.initBrowser();
                }

                await this.page.goto(listUrl, {
                    waitUntil: 'networkidle',
                    timeout: 30000
                });


                // 동적 컨텐츠 로딩 대기
                await this.page.waitForTimeout(4000);

                // 리스트 요소들 추출
                const announcements = await this.page.evaluate((selectors) => {

                    console.log("selectors.listSelector", selectors.listSelector)
                    const rows = document.querySelectorAll(selectors.listSelector);

                    console.log("rows", rows)
                    const results = [];

                    rows.forEach((row, index) => {
                        // 헤더 행 스킵
                        if (index === 0 && row.querySelector('th')) return;

                        const titleElement = row.querySelector(selectors.titleSelector);
                        const dateElement = row.querySelector(selectors.dateSelector);


                        if (titleElement && dateElement) {
                            const title = titleElement.textContent.trim();
                            const dateText = dateElement.textContent.trim();

                            // 다양한 방식으로 링크 정보 추출
                            const href = titleElement.href;
                            const onclick = titleElement.getAttribute('onclick');
                            const dataAction = titleElement.getAttribute('data-action');

                            results.push({
                                title,
                                dateText,
                                link: href,
                                onclick: onclick,
                                dataAction: dataAction,
                                listDate: dateText
                            });
                        }
                    });

                    return results;
                }, {
                    listSelector: this.listSelector,
                    titleSelector: this.titleSelector,
                    dateSelector: this.dateSelector
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

                // 재시도 전 대기
                await this.delay(2000 * retries);
            }
        }
    }

    /**
     * 개별 공고 처리
     */
    async processAnnouncement(announcement) {
        try {
            console.log(`\n처리 중: ${announcement.title}`);

            // 1. 리스트에서 날짜 확인
            const listDate = this.extractDate(announcement.dateText);

            // targetDate가 설정된 경우 해당 날짜 이전 체크
            if (this.targetDate) {
                const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                if (listDate && listDate.isBefore(targetMoment)) {
                    console.log(`리스트 날짜 ${listDate.format('YYYY-MM-DD')}가 대상 날짜(${targetMoment.format('YYYY-MM-DD')}) 이전입니다.`);
                    return true; // 스크래핑 중단
                }
            }
            // targetYear 체크 (기존 호환성 유지)
            else if (listDate && listDate.year() < this.targetYear) {
                console.log(`리스트 날짜 ${listDate.format('YYYY-MM-DD')}가 대상 연도(${this.targetYear}) 이전입니다.`);
                return true; // 스크래핑 중단
            }

            // 2. 중복 게시물 체크 (제목만으로 비교)
            const sanitizedTitle = sanitize(announcement.title).substring(0, 100);

            // 메모리 기반 체크
            if (this.processedTitles.has(announcement.title) || this.processedTitles.has(sanitizedTitle)) {
                console.log(`❌ 중복 게시물 스킵 (메모리): ${announcement.title}`);
                return false;
            }

            // 파일시스템 기반 체크
            try {
                if (await fs.pathExists(this.outputDir)) {
                    const existingFolders = await fs.readdir(this.outputDir);
                    for (const folderName of existingFolders) {
                        const match = folderName.match(/^\d{3}_(.+)$/);
                        if (match) {
                            const existingTitle = match[1];
                            if (existingTitle === sanitizedTitle || existingTitle === announcement.title) {
                                console.log(`❌ 중복 게시물 스킵 (파일시스템): ${announcement.title}`);
                                // sanitize된 제목을 저장하여 정확한 중복 체크
            const sanitizedTitleForCheck = sanitize(announcement.title).substring(0, 100);
            this.processedTitles.add(sanitizedTitleForCheck);
                                this.processedTitles.add(sanitizedTitle);
                                return false;
                            }
                        }
                    }
                }
            } catch (fsError) {
                // 실패 공고 DB 기록
                await FailureLogger.logFailedAnnouncement({
                    site_code: this.siteCode,
                    title: announcement?.title || 'Unknown',
                    url: announcement?.link || announcement?.url,
                    detail_url: announcement?.detailUrl,
                    error_type: 'fsError',
                    error_message: fsError.message
                }).catch(logErr => {});

                console.log(`파일시스템 중복 체크 실패: ${fsError.message}`);
            }

            // 3. 상세 페이지로 이동
            const detailContent = await this.getDetailContent(announcement);
            if (!detailContent) {
                console.log('상세 페이지 접근 실패');
                return false;
            }

            // 4. 상세 페이지에서 날짜 재확인
            if (this.targetDate) {
                const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                if (detailContent.date && detailContent.date.isBefore(targetMoment)) {
                    console.log(`상세 페이지 날짜 ${detailContent.date.format('YYYY-MM-DD')}가 대상 날짜(${targetMoment.format('YYYY-MM-DD')}) 이전입니다.`);
                    return true; // 스크래핑 중단
                }
            }
            // targetYear 체크 (기존 호환성 유지)
            else if (detailContent.date && detailContent.date.year() < this.targetYear) {
                console.log(`상세 페이지 날짜 ${detailContent.date.format('YYYY-MM-DD')}가 대상 연도(${this.targetYear}) 이전입니다.`);
                return true; // 스크래핑 중단
            }

            // 5. 폴더 생성 및 파일 저장
            await this.saveAnnouncement(announcement, detailContent);

            // sanitize된 제목을 저장하여 정확한 중복 체크
            const sanitizedTitleForCheck = sanitize(announcement.title).substring(0, 100);
            this.processedTitles.add(sanitizedTitleForCheck);
            console.log(`처리 완료: ${announcement.title}`);

            return false; // 계속 진행

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

    /**
     * 상세 페이지 내용 가져오기
     */
    async getDetailContent(announcement) {
        const maxRetries = 3;
        let retries = 0;

        while (retries < maxRetries) {
            try {
                // 직접 URL 구성 방식 사용
                const detailUrl = await this.buildDetailUrl(announcement);

                if (!detailUrl) {
                    console.log('상세 페이지 URL 구성 실패');
                    return null;
                }

                console.log(`상세 페이지 URL: ${detailUrl}`);

                // 브라우저나 페이지가 종료된 경우 재초기화
                if (!this.browser || !this.page || this.page.isClosed()) {
                    console.log('브라우저 연결이 끊어져 재초기화합니다...');
                    await this.initBrowser();
                }

                // seosan은 직접 URL 접근 방식 사용
                await this.page.goto(detailUrl, {
                    waitUntil: 'networkidle',
                    timeout: 30000
                });
                
                await this.page.waitForTimeout(2000);

                const evalOptions = { ...this.options, announcement }

                // 페이지 내용 추출
                const content = await this.page.evaluate((options) => {
                    // 헤더, 사이드바, 푸터 등 제거
                    const excludeSelectors = [
                        'header', 'nav', 'aside', 'footer',
                        '.header', '.nav', '.sidebar', '.footer',
                        '.menu', '.navigation', '.breadcrumb'
                    ];
                    const {
                        announcement
                    } = options;

                    excludeSelectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => el.remove());
                    });

                    // 본문 추출 시도
                    let mainContent = null;
                    const contentSelectors = [
                        '#contents', '.content', 'table .view', '.main', '.article', '.post',
                        '#main', '#article', '#post',
                        '.board-content', '.view-content',
                        'div.table-responsive'
                    ];

                    for (const selector of contentSelectors) {
                        const element = document.querySelector(selector);
                        if (element) {
                            mainContent = element;
                            break;
                        }
                    }

                    if (!mainContent) {
                        mainContent = document.body;
                    }


                    // 날짜 추출
                    let dateText = '';
                    // const dateSelectors = [
                    //     '.date', '.reg-date', '.write-date', '.post-date',
                    //     '[class*="date"]', '[id*="date"]'
                    // ];

                    // for (const selector of dateSelectors) {
                    //     const dateElement = document.querySelector(selector);
                    //     if (dateElement) {
                    //         dateText = dateElement.textContent.trim();
                    //         break;
                    //     }
                    // }

                    console.log("dateText!!!!!!", dateText)
                    //현재 등록일의 경우는 아예 클래스 등이 지정되어 있지 않다.
                    if (!dateText) {
                        //이 부분을 처리하자
                        console.log("!!!!dateText 재처리")

                        //이 부분을 처리하자
                        if (announcement && announcement.listDate) {
                            dateText = announcement.listDate
                        } else {
                            const dateElement = document.querySelector('.p-author__info .p-split');

                            if (dateElement) {
                                // Get the text content, remove the "작성일 :" part, and trim whitespace
                                dateText = dateElement.textContent.replace('작성일 :', '').trim();
                            }
                        }


                    }
                    console.log("dateText ", dateText)

                    // 첨부파일 링크 추출
                    const attachments = [];

                    const downloadLinks = document.querySelectorAll('td a:not(#preview):not(#listen)');
                    const results = [];
                    console.log("downloadLinks", downloadLinks)
                    downloadLinks.forEach(link => {
                        // "바로보기"나 "듣기" 링크는 제외합니다.
                        if (link.textContent.includes('바로보기') || link.textContent.includes('듣기')) {
                            return;
                        }

                        // href 속성에서 JavaScript 코드를 가져옵니다.
                        const href = link.getAttribute('href');

                        // 정규식을 사용하여 'goDownLoad' 함수 내의 매개변수를 추출합니다.
                        const regex = /goDownLoad\('([^']*)','([^']*)','([^']*)'\)/;
                        const matches = href.match(regex);

                        if (matches) {
                            const fileName = link.textContent.trim();
                            const userFileNm = matches[1];
                            const sysFileNm = matches[2];
                            const filePath = matches[3];

                            // 추출한 매개변수를 사용하여 완전한 다운로드 URL을 재구성합니다.
                            const baseUrl = 'https://eminwon.seosan.go.kr';
                            const downloadUrl = `${baseUrl}/emwp/jsp/ofr/FileDown.jsp?user_file_nm=${encodeURIComponent(userFileNm)}&sys_file_nm=${encodeURIComponent(sysFileNm)}&file_path=${encodeURIComponent(filePath)}`;
                            console.log(fileName, downloadUrl, href)
                            attachments.push({
                                name: fileName,
                                url: downloadUrl,
                                onclick: href
                            });
                        }
                    });




                    // 텍스트만 추출 (마크다운 형식)
                    const textContent = mainContent.innerText || mainContent.textContent || '';

                    return {
                        content: textContent.trim(),
                        dateText: dateText,
                        attachments: attachments
                    };

                }, evalOptions);

                // 날짜 파싱
                const detailDate = this.extractDate(content.dateText);

                return {
                    url: detailUrl,
                    content: content.content,
                    date: detailDate,
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
                    console.error('최대 재시도 횟수 초과. null 반환.');
                    return null;
                }

                // 재시도 전 대기
                await this.delay(2000 * retries);
            }
        }
    }

    /**
     * 공고 저장
     */
    async saveAnnouncement(announcement, detailContent) {
        try {
            // 폴더명 생성
            const sanitizedTitle = sanitize(announcement.title).substring(0, 100);
            const folderName = `${String(this.counter).padStart(3, '0')}_${sanitizedTitle}`;
            const folderPath = path.join(this.outputDir, folderName);

            await fs.ensureDir(folderPath);

            // 첨부파일 다운로드 및 URL 정보 수집
            let downloadUrlInfo = {};
            if (detailContent.attachments && detailContent.attachments.length > 0) {
                downloadUrlInfo = await this.downloadAttachments(detailContent.attachments, folderPath);

                // 첨부파일에 다운로드 정보 추가
                detailContent.attachments.forEach(attachment => {
                    const fileName = attachment.name;
                    if (downloadUrlInfo[fileName]) {
                        attachment.downloadInfo = downloadUrlInfo[fileName];
                    }
                });
            }

            // content.md 생성 (다운로드 URL 정보 포함)
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

    /**
     * 첨부파일 다운로드
     */
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
                await this.delay(500); // 0.5초 대기
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

    /**
     * 단일 첨부파일 다운로드
     */
    async downloadSingleAttachment(attachment, attachDir, index) {
        try {
            let downloadUrl = attachment.url;
            let fileName = attachment.name || `attachment_${index}`;
            let actualDownloadUrl = null;
            let downloadType = 'direct';

            // JavaScript 방식 처리
            if (attachment.onclick) {
                downloadType = 'onclick';
                // goDownload 패턴 처리
                const goDownloadMatch = attachment.onclick.match(/goDownload\(\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*\)/);

                if (goDownloadMatch) {
                    const [, originalName, serverName, serverPath] = goDownloadMatch;
                    // 실제 goDownload 함수와 동일한 URL 패턴 사용
                    const enc_user_file_nm = encodeURIComponent(originalName);
                    const enc_sys_file_nm = encodeURIComponent(serverName);
                    const enc_file_path = encodeURIComponent(serverPath);
                    downloadUrl = `https://eminwon.yangsan.go.kr/emwp/jsp/ofr/FileDown.jsp?user_file_nm=${enc_user_file_nm}&sys_file_nm=${enc_sys_file_nm}&file_path=${enc_file_path}`;
                    // fileName = originalName; // 원본 파일명 사용
                    downloadType = 'goDownload';
                } else {
                    // 기존 onclick 이벤트에서 URL 추출 시도
                    const match = attachment.onclick.match(/(?:window\.open|location\.href|download)\(['"]([^'"]*)['"]\)/);
                    if (match) {
                        downloadUrl = match[1];
                    }
                }

                console.log('JAVASCRIPT 방식', downloadUrl)
            }

            // 상대 URL을 절대 URL로 변환
            if (downloadUrl && !downloadUrl.startsWith('http')) {
                console.log('상대 URL을 절대 URL로 변환')
                downloadUrl = new URL(downloadUrl, this.baseUrl).toString();
            }

            if (!downloadUrl || !downloadUrl.startsWith('http')) {
                console.log(`유효하지 않은 다운로드 URL: ${downloadUrl}`);
                return {
                    [fileName]: {
                        originalUrl: attachment.url,
                        originalOnclick: attachment.onclick,
                        actualDownloadUrl: null,
                        downloadType: downloadType,
                        error: 'Invalid URL'
                    }
                };
            }

            actualDownloadUrl = downloadUrl;

            // POST 방식 또는 특별한 처리가 필요한 경우
            if (attachment.onclick && attachment.onclick.includes('submit')) {
                await this.downloadViaForm(attachment, attachDir, fileName);
            } else {
                // 일반 링크 방식
                await this.downloadViaLink(downloadUrl, attachDir, fileName);
            }

            console.log(`!!!!!!!!!!!!!!!!!다운로드 완료: ${fileName}!!!!!!!!!!!!!!!!`);

            return {
                [fileName]: {
                    originalUrl: attachment.url,
                    originalOnclick: attachment.onclick,
                    actualDownloadUrl: actualDownloadUrl,
                    downloadType: downloadType,
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
                    originalOnclick: attachment.onclick,
                    actualDownloadUrl: null,
                    downloadType: 'error',
                    error: error.message
                }
            };
        }
    }

    /**
     * 링크 방식 다운로드
     */
    async downloadViaLink(url, attachDir, fileName) {
        try {

            const response = await axios({
                method: 'GET',
                url: url,
                responseType: 'stream',
                timeout: 30000,
                headers: {
                    'Accept': '*/*',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            });

            // 파일명 결정 (한글명 지원)
            const contentDisposition = response.headers['content-disposition'];

            // goDownload에서 온 원본 파일명이 있는 경우 우선 사용 (한글 보존)
            const isFromGoDownload = fileName && !fileName.startsWith('attachment_');

            if (!isFromGoDownload && contentDisposition) {
                // goDownload가 아닌 경우에만 Content-Disposition에서 파일명 추출
                let extractedFileName = null;

                // 1순위: UTF-8 인코딩된 파일명 처리 (filename*=UTF-8''encoded-name)
                const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
                if (utf8Match) {
                    try {
                        extractedFileName = decodeURIComponent(utf8Match[1]);
                        console.log('UTF-8 파일명 추출:', extractedFileName);
                    } catch (e) {
                        console.log('UTF-8 파일명 디코딩 실패:', e.message);
                    }
                }

                // 2순위: 일반 filename 처리
                if (!extractedFileName) {
                    const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                    if (match) {
                        extractedFileName = match[1].replace(/['"]/g, '').trim();

                        // URL 인코딩된 경우 디코딩 시도
                        if (extractedFileName.includes('%')) {
                            try {
                                const decoded = decodeURIComponent(extractedFileName);
                                extractedFileName = decoded;
                            } catch (e) {
                                console.log('파일명 디코딩 실패:', e.message);
                            }
                        }
                    }
                }

                // 추출된 파일명이 있고, 유효한 경우에만 사용
                if (extractedFileName && extractedFileName.trim() && extractedFileName !== 'attachment') {
                    fileName = extractedFileName;
                    console.log('Content-Disposition에서 파일명 사용:', fileName);
                }
            } else if (isFromGoDownload) {
                console.log('goDownload 원본 파일명 우선 사용:', fileName);
            }

            // 파일명 정리 (한글 보존)
            const cleanFileName = sanitize(fileName, { replacement: '_' });
            const filePath = path.join(attachDir, cleanFileName);

            console.log(`최종 파일명: ${cleanFileName}`);
            console.log(`저장 경로: ${filePath}`);

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

    /**
     * 폼 방식 다운로드 (POST)
     */
    async downloadViaForm(attachment, attachDir, fileName) {
        try {
            // 브라우저를 사용하여 폼 제출
            await this.page.evaluate((onclick) => {
                eval(onclick);
            }, attachment.onclick);

            // 다운로드 대기
            await this.page.waitForTimeout(3000);

            console.log(`폼 방식 다운로드 완료: ${fileName}`);

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

            throw new Error(`폼 다운로드 실패: ${error.message}`);
        }
    }

    /**
     * 마크다운 컨텐츠 생성
     */
    generateMarkdownContent(announcement, detailContent) {
        const lines = [];

        lines.push(`**제목**: ${announcement.title}`);
        lines.push('');

        lines.push(`**원본 URL**: ${detailContent.url}`);
        lines.push('');

        if (detailContent.date) {
            lines.push(`**작성일**: ${detailContent.date.format('YYYY-MM-DD')}`);
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

                let attachInfo = ""
                // 다운로드 URL 정보가 있는 경우 추가
                if (att.downloadInfo && att.downloadInfo.actualDownloadUrl) {
                    attachInfo = `${i + 1}. ${att.name}:${att.downloadInfo.actualDownloadUrl}`
                    // lines.push(`   - **원본 URL**: ${att.downloadInfo.originalUrl || att.downloadInfo.originalOnclick || '정보 없음'}`);
                    // lines.push(`   - **실제 다운로드 URL**: ${att.downloadInfo.actualDownloadUrl || '정보 없음'}`);
                    // if (att.downloadInfo.downloadType) {
                    //     lines.push(`   - **다운로드 방식**: ${att.downloadInfo.downloadType}`);
                    // }
                    // if (att.downloadInfo.suggestedFilename && att.downloadInfo.suggestedFilename !== att.name) {
                    //     lines.push(`   - **서버 제안 파일명**: ${att.downloadInfo.suggestedFilename}`);
                    // }
                } else {
                    attachInfo = `${i + 1}. ${att.name}`;
                }
                lines.push(attachInfo);
                lines.push('');
            });
        }

        return lines.join('\n');
    }


    /**
     * 상세 페이지 URL 구성
     */
    async buildDetailUrl(announcement) {
        console.log('URL 구성 중:', {
            link: announcement.link,
            onclick: announcement.onclick,
            dataAction: announcement.dataAction
        });

        // 1. data-action 속성이 있는 경우 (우선순위 높음)
        if (announcement.dataAction) {
            const detailUrl = new URL(announcement.dataAction, this.baseUrl).toString();
            return detailUrl;
        }

        // 1. JavaScript onclick이 있는 경우 (파주시는 주로 javascript:void(0) 사용)
        if (announcement.onclick) {
            console.log('onclick 분석 중:', announcement.onclick);

            // f.not_ancmt_mgt_no.value = not_ancmt_mgt_no;
            // f.target = "_self";
            // f.action = "/common/program/eminwonView.jsp";
            // f.method.value = 'selectOfrNotAncmt'; //Action
            // f.methodnm.value = 'selectOfrNotAncmtRegst';

            const viewMatch = announcement.onclick.match(/searchDetail\(\s*['"]([^'"]*)['"]\s*\)/);

            console.log(viewMatch)

            if (viewMatch) {
                const notAncmtMgtNo = viewMatch[1];
                
                // seosan 사이트의 상세페이지 접근 방식
                // iframe 내부에서 직접 상세 페이지 URL 구성
                const detailUrl = `https://www.seosan.go.kr/common/program/eminwonView.jsp?` +
                    `jndinm=OfrNotAncmtEJB&context=NTIS&` +
                    `method=selectOfrNotAncmt&methodnm=selectOfrNotAncmtRegst&` +
                    `not_ancmt_mgt_no=${notAncmtMgtNo}&` +
                    `homepage_pbs_yn=Y&subCheck=Y&not_ancmt_se_code=01%2C04%2C06&` +
                    `cha_dep_code_nm=&countYn=Y&list_gubun=&mobile_code=00`;
                
                console.log('Seosan 상세 페이지 URL 구성:', detailUrl);
                return detailUrl;
            }

        }

        // 2. 이미 완전한 URL인 경우
        const link = announcement.link;
        if (link && link.startsWith('http') && !link.endsWith('#')) {
            return link;
        }

        // 3. 상대 URL인 경우
        if (link && link.startsWith('/')) {
            return new URL(link, this.baseUrl).toString();
        }


        // 5. 브라우저에서 실제 클릭하여 URL 확인 (최후의 수단)
        if (announcement.onclick && announcement.onclick.includes('req.post')) {
            console.log('브라우저 클릭으로 실제 URL 확인 시도...');
            return await this.getUrlByBrowserClick(announcement);
        }

        console.log('상세 페이지 URL 구성 실패');
        return null;
    }

    /**
     * 브라우저에서 실제 클릭하여 URL 확인
     */
    async getUrlByBrowserClick(announcement) {
        try {
            // 현재 페이지에서 해당 제목의 링크를 찾아 클릭
            const linkClicked = await this.page.evaluate((title) => {
                const links = document.querySelectorAll('table.bod_list tbody tr td:nth-child(3) a');
                for (let link of links) {
                    if (link.textContent.trim().includes(title.substring(0, 20))) {
                        // 새 탭에서 열리도록 target 설정
                        link.setAttribute('target', '_blank');
                        link.click();
                        return true;
                    }
                }
                return false;
            }, announcement.title);

            if (linkClicked) {
                // 새 페이지 대기
                const newPage = await this.context.waitForEvent('page', { timeout: 5000 });
                await newPage.waitForLoadState('networkidle');

                const url = newPage.url();
                await newPage.close();

                console.log('브라우저 클릭으로 확인된 URL:', url);
                return url;
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

            console.log('브라우저 클릭 방식 실패:', error.message);
        }

        return null;
    }

    /**
     * 날짜 추출
     */
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

    /**
     * 대기
     */
    async delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * 정리 작업
     */
    async cleanup() {
        if (this.browser) {
            try {
                // 컨텍스트 및 브라우저 닫기
                if (this.context) {
                    await this.context.close();
                }

                await this.browser.close();
                console.log('\\n브라우저 정리 완료');

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

        console.log(`\\n=== 스크래핑 완료 ===`);
        console.log(`처리된 공고 수: ${this.counter - 1}`);
        console.log(`출력 디렉토리: ${this.outputDir}`);
    }

    /**
     * 리스트 URL 구성
     */
    buildListUrl(pageNum) {
        // 기본적으로 page 파라미터를 추가
        const url = new URL(this.baseUrl);
        url.searchParams.set('pageIndex', pageNum);
        return url.toString();
    }


}

// CLI 인터페이스 (직접 실행시에만)
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
            description: '대상 날짜 (YYYY-MM-DD 형식, year 대신 사용)',
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
            default: 'seosan',
            required: true
        })
        .option('url', {
            alias: 'u',
            type: 'string',
            description: '기본 URL',
            default: 'https://www.seosan.go.kr/common/program/eminwonView.jsp?jndinm=OfrNotAncmtEJB&context=NTIS&method=selectListOfrNotAncmt&methodnm=selectListOfrNotAncmtHomepage&not_ancmt_sj=&pageIndex=1&ofr_pageSize=10&homepage_pbs_yn=Y&subCheck=Y&not_ancmt_se_code=01%2C04%2C06&cha_dep_code_nm=&countYn=Y&list_gubun=&mobile_code=00',
            required: true
        })
        .option('list-selector', {
            type: 'string',
            description: '리스트 선택자',
            default: 'table.bbs_default tbody tr'
        })
        .option('title-selector', {
            type: 'string',
            description: '제목 선택자',
            default: 'td:nth-child(3) a'
        })
        .option('date-selector', {
            type: 'string',
            description: '날짜 선택자',
            default: 'td:nth-child(5) '
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

    const scraper = new AnnouncementScraper({
        targetYear: argv.year,
        targetDate: argv.date,
        goPage: argv.goPage,
        outputDir: argv.output,
        siteCode: argv.site,
        baseUrl: argv.url,
        listSelector: argv.listSelector,
        titleSelector: argv.titleSelector,
        dateSelector: argv.dateSelector
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

module.exports = AnnouncementScraper;
