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
        this.force = options.force || false;

        this.targetDate = options.targetDate || null;
        this.options = options;
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
                retries++;
                console.error(`브라우저 초기화 실패 (시도 ${retries}/${maxRetries}):`, error.message);

                if (this.browser) {
                    try {
                        await this.browser.close();
                    } catch (closeError) {
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
     * 상세 URL만 추출하여 DB에 저장 (다운로드 없음)
     * @param {string} batchDate - 배치 날짜 (선택)
     * @returns {Promise<{totalCount: number, pageCount: number, savedCount: number}>} URL 추출 결과
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

            if (this.targetDate) {
                const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                console.log(`대상 날짜: ${targetMoment.format('YYYY-MM-DD')} (${this.targetDate} 이후 공고만)`);
            } else {
                console.log(`대상 연도: ${this.targetYear}`);
            }
            console.log(`사이트 코드: ${this.siteCode}`);

            while (consecutiveEmptyPages < maxConsecutiveEmptyPages) {
                try {
                    console.log(`\n페이지 ${currentPage} 확인 중...`);

                    const announcements = await this.getAnnouncementList(currentPage);

                    if (!announcements || announcements.length === 0) {
                        console.log('공고가 없습니다.');
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
                            const listDate = this.extractDate(announcement.dateText);

                            // targetDate가 설정된 경우
                            if (this.targetDate) {
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

                            if (!detailUrl) {
                                console.warn(`URL 생성 실패: ${announcement.title}`);
                                continue;
                            }

                            // URL DB 저장
                            const saved = await UrlManager.saveDetailUrl({
                                site_code: this.siteCode,
                                title: announcement.title,
                                list_url: this.baseUrl,
                                detail_url: detailUrl,
                                list_date: announcement.dateText,
                                batch_date: batchDate
                            });

                            if (saved) {
                                savedCount++;
                                console.log(`  ✓ ${announcement.title.substring(0, 50)}...`);
                            }

                            pageValidCount++;

                        } catch (error) {
                            console.warn(`공고 처리 중 오류 (${announcement.title}):`, error.message);
                            continue;
                        }
                    }

                    totalCount += pageValidCount;
                    console.log(`페이지 ${currentPage}: ${pageValidCount}개 URL 추출 (저장: ${savedCount}개, 누적: ${totalCount}개)`);

                    if (shouldStop) {
                        console.log(`조건 불일치로 추출 중단.`);
                        break;
                    }

                    currentPage++;
                    await this.delay(1000); // 1초 대기

                } catch (pageError) {
                    console.error(`페이지 ${currentPage} 확인 중 오류:`, pageError.message);
                    consecutiveEmptyPages++;
                    currentPage++;
                }
            }

            console.log(`\n=== URL 추출 완료 ===`);
            console.log(`총 URL 수: ${totalCount}개`);
            console.log(`DB 저장 성공: ${savedCount}개`);
            console.log(`확인한 페이지 수: ${currentPage - 1}개`);

            return {
                totalCount: totalCount,
                savedCount: savedCount,
                pageCount: currentPage - 1
            };

        } catch (error) {
            console.error('URL 추출 중 오류:', error.message);
            throw error;
        } finally {
            await this.cleanup();
        }
    }

    /**
     * 예상 공고 건수 카운트 (실제 다운로드 없이)
     * @returns {Promise<{totalCount: number, pageCount: number}>} 예상 건수 정보
     */
    async countExpectedAnnouncements() {
        try {
            await this.initBrowser();

            let currentPage = 1;
            let totalCount = 0;
            let consecutiveEmptyPages = 0;
            const maxConsecutiveEmptyPages = 3;

            console.log(`\n=== 예상 공고 건수 카운트 시작 ===`);

            if (this.targetDate) {
                const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                console.log(`대상 날짜: ${targetMoment.format('YYYY-MM-DD')} (${this.targetDate} 이후 공고만 카운트)`);
            } else {
                console.log(`대상 연도: ${this.targetYear}`);
            }
            console.log(`사이트 코드: ${this.siteCode}`);

            while (consecutiveEmptyPages < maxConsecutiveEmptyPages) {
                try {
                    console.log(`\n페이지 ${currentPage} 확인 중...`);

                    const announcements = await this.getAnnouncementList(currentPage);

                    if (!announcements || announcements.length === 0) {
                        console.log('공고가 없습니다.');
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
                            const listDate = this.extractDate(announcement.dateText);

                            // targetDate가 설정된 경우
                            if (this.targetDate) {
                                const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                                if (listDate && listDate.isBefore(targetMoment)) {
                                    console.log(`대상 날짜(${targetMoment.format('YYYY-MM-DD')}) 이전 공고 발견. 카운트 중단.`);
                                    shouldStop = true;
                                    break;
                                }
                            }
                            // targetYear만 설정된 경우
                            else if (listDate && listDate.year() < this.targetYear) {
                                console.log(`대상 연도(${this.targetYear}) 이전 공고 발견. 카운트 중단.`);
                                shouldStop = true;
                                break;
                            }

                            // 조건에 맞으면 카운트
                            pageValidCount++;

                        } catch (error) {
                            console.warn(`공고 확인 중 오류 (${announcement.title}):`, error.message);
                            continue;
                        }
                    }

                    totalCount += pageValidCount;
                    console.log(`페이지 ${currentPage}: ${pageValidCount}개 공고 (누적: ${totalCount}개)`);

                    if (shouldStop) {
                        console.log(`조건 불일치로 카운트 중단.`);
                        break;
                    }

                    currentPage++;
                    await this.delay(1000); // 1초 대기

                } catch (pageError) {
                    console.error(`페이지 ${currentPage} 확인 중 오류:`, pageError.message);
                    consecutiveEmptyPages++;
                    currentPage++;
                }
            }

            console.log(`\n=== 카운트 완료 ===`);
            console.log(`총 예상 공고 수: ${totalCount}개`);
            console.log(`확인한 페이지 수: ${currentPage - 1}개`);

            return {
                totalCount: totalCount,
                pageCount: currentPage - 1
            };

        } catch (error) {
            console.error('공고 카운트 중 오류:', error.message);
            throw error;
        } finally {
            await this.cleanup();
        }
    }

    /**
     * 메인 스크래핑 프로세스
     * @returns {Promise<{successCount: number, startCounter: number, endCounter: number}>}
     */
    async scrape() {
        const startCounter = this.counter;
        let successCount = 0;

        try {
            await this.initBrowser();
            await fs.ensureDir(this.outputDir);

            // 기존 폴더에서 마지막 카운터 번호를 가져와서 그 다음부터 시작
            const lastCounter = await this.getLastCounterNumber();
            this.counter = lastCounter + 1;
            console.log(`시작 카운터 번호: ${this.counter} (기존 최대 번호: ${lastCounter})`);

            // 기존 폴더의 제목들을 processedTitles에 추가
            await this.loadExistingTitles();

            let currentPage = 1;
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
                            // 성공한 경우에만 카운트 증가
                            successCount++;
                        } catch (announcementError) {
                            console.error(`공고 처리 중 오류 (${announcement.title}):`, announcementError.message);

                            // 실패 공고 DB 기록
                            FailureLogger.logFailedAnnouncement({
                                site_code: this.siteCode,
                                title: announcement?.title || 'Unknown',
                                url: announcement?.link || announcement?.url,
                                detail_url: announcement?.detailUrl,
                                error_type: 'announcementError',
                                error_message: announcementError.message
                            }).catch(err => {});
                            // 개별 공고 오류는 전체 프로세스를 중단하지 않음
                            continue;
                        }
                    }

                    if (shouldContinue) {
                        currentPage++;
                        await this.delay(1000); // 1초 대기
                    }

                } catch (pageError) {
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

            // 성공 건수 반환
            const endCounter = this.counter - 1;
            console.log(`\n스크래핑 성공: ${successCount}개 공고 처리`);

            return {
                successCount: successCount,
                startCounter: lastCounter + 1,
                endCounter: endCounter
            };

        } catch (error) {
            console.error('스크래핑 중 치명적 오류 발생:', error.message);
            console.error('스택 트레이스:', error.stack);

            // 오류 발생 시에도 현재까지 성공 건수 반환
            return {
                successCount: successCount,
                startCounter: startCounter,
                endCounter: this.counter - 1,
                error: error.message
            };
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
                            const title = titleElement.textContent.replace("NEW", "").trim();
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
            // targetYear만 설정된 경우 연도 체크
            else if (listDate && listDate.year() < this.targetYear) {
                console.log(`리스트 날짜 ${listDate.format('YYYY-MM-DD')}가 대상 연도(${this.targetYear}) 이전입니다.`);
                return true; // 스크래핑 중단
            }
            // 2. 중복 게시물 체크
            const sanitizedTitle = sanitize(announcement.title).substring(0, 100);
            if (this.processedTitles.has(sanitizedTitle)) {
                console.log(`중복 게시물 스킵: ${announcement.title}`);
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
            // targetYear만 설정된 경우 연도 체크 
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

                // 상세 페이지로 이동
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
                        '#contents', 'tbody.p-table--th-left', '#sub_body', '.contents_wrap', '.program--contents',
                        '.board_view', '#board_basic_view',
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
                    //현재 등록일의 경우는 아예 클래스 등이 지정되어 있지 않다.
                    if (!dateText) {
                        //이 부분을 처리하자
                        console.log("!!!!dateText 재처리")


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
                    const fileItems = document.querySelectorAll('a[href *= "goDownload"]');

                    fileItems.forEach(link => {

                        let href = link.href;
                        const text = link.textContent.trim();

                        // javascript:goDownload(...) 형태를 실제 다운로드 URL로 변환
                        // if (href.startsWith('javascript:')) {
                        //     const regex = /goDownload\('([^']+)',\s*'([^']+)',\s*'([^']+)'\)/;
                        //     const matches = href.match(regex);

                        //     if (matches) {
                        //         const [, fileNm, sysFileNm, filePath] = matches;
                        //         // eminwon 서버의 파일 다운로드 URL 패턴
                        //         // href = `https://eminwon.andong.go.kr/emwp/jsp/ofr/FileDown.jsp?user_file_nm=${fileNm}&sys_file_nm=${sysFileNm}&file_path=${encodeURIComponent(filePath)}`;
                        //     }
                        // }

                        attachments.push({
                            name: text,
                            url: href
                        });

                    });




                    // 텍스트만 추출 (마크다운 형식)
                    const textContent = mainContent.innerText || mainContent.textContent || '';

                    console.log("attachments", attachments)

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
     * 단일 첨부파일 다운로드 (개선된 디버깅 및 에러 처리)
     */
    async downloadSingleAttachment(attachment, attachDir, index) {
        const startTime = Date.now();
        console.log(`\n📥 === 첨부파일 다운로드 시작 (${index}) ===`);
        console.log(`파일명: ${attachment.name}`);
        console.log(`URL: ${attachment.url}`);

        try {
            let downloadUrl = attachment.url;
            let fileName = attachment.name || `attachment_${index}`;


            // // Use a regular expression to parse the goDownLoad() function arguments
            // const regex = /goDownLoad\('([^']+)',\s*'([^']+)',\s*'([^']+)'\)/;
            // const matches = href.match(regex);

            // if (matches && matches.length === 4) {
            //     const fileName = matches[1];
            //     const systemFileName = matches[2];
            //     const filePath = matches[3];

            //     // Construct the final download URL
            //     const fullUrl = `https://eminwon.shinan.go.kr/emwp/jsp/ofr/FileDownNew.jsp?user_file_nm=${decodeURIComponent(fileName)}&sys_file_nm=${decodeURIComponent(systemFileName)}&file_path=${decodeURIComponent(filePath)}`;

            //     if (fileName && fullUrl) {
            //     }
            // }


            // goDownLoad(fileNm, sysFileNm, filePath) 패턴 처리 - POST 방식
            const regex = /goDownload\('([^']+)',\s*'([^']+)',\s*'([^']+)'\)/;
            const matches = downloadUrl.match(regex);

            if (matches) {
                const [, fileNm, sysFileNm, filePath] = matches;
                fileName = fileNm; // 원본 파일명 사용

                console.log('🎯 goDownLoad 패턴 감지:', {
                    fileNm: decodeURIComponent(fileNm),
                    sysFileNm: decodeURIComponent(sysFileNm),
                    filePath: filePath
                });

                // POST 방식으로 다운로드 (여러 방법 시도)
                let downloadResult = null;
                let lastError = null;

                // 방법들을 순차적으로 시도
                const downloadMethods = [
                    {
                        name: 'EgovPost',
                        method: async () => {
                            const result = await this.downloadViaEgovPost(fileNm, sysFileNm, filePath, attachDir, fileName);
                            return result;
                        }
                    },
                ];

                for (const { name, method } of downloadMethods) {
                    try {
                        console.log(`🔄 ${name} 방식 시도 중...`);
                        downloadResult = await method();

                        if (downloadResult && downloadResult.success) {
                            const elapsed = Date.now() - startTime;
                            // Return with fileName and downloadUrl for URL tracking
                            return {
                                ...downloadResult,
                                fileName: fileName,
                                downloadUrl: downloadUrl
                            };
                        }
                    } catch (error) {
                        lastError = error;
                        console.warn(`⚠️ ${name} 방식 실패: ${error.message}`);

                        // 다음 방법을 시도하기 전에 잠시 대기
                        await new Promise(resolve => setTimeout(resolve, 1000));
                    }
                }

                // 모든 방법이 실패한 경우
                throw lastError || new Error('모든 다운로드 방법 실패');

            } else {
                console.log('❌ goDownLoad 패턴이 감지되지 않음');
                console.log('지원하지 않는 첨부파일 형식입니다.');
                return { success: false, reason: 'unsupported_pattern' };
            }

        } catch (error) {
            const elapsed = Date.now() - startTime;
            // console.error(`❌ 첨부파일 다운로드 최종 실패 (${attachment.name}):`);
            // console.error(`   오류: ${error.message}`);
            // console.error(`   처리 시간: ${elapsed}ms`);

            return {
                success: false,
                error: error.message,
                processingTime: elapsed,
                fileName: attachment.name
            };
        } finally {
            console.log(`📥 === 첨부파일 다운로드 종료 (${index}) ===\n`);
        }
    }


    /**
     * 대구광역시 fn_egov_downFile 함수 직접 실행 방식 (개선된 다운로드 처리)
     */
    async downloadViaEgovPost(fileNm, sysFileNm, filePath, attachDir, fileName) {
        try {

            // 파일명 디코딩 및 정리
            const cleanFileName = sanitize(decodeURIComponent(fileNm), { replacement: '_' });
            const expectedFilePath = path.join(attachDir, cleanFileName);

            // 1단계: CDP를 통한 다운로드 설정
            await this.setupDownloadBehavior(attachDir);

            // 2단계: 네트워크 요청 모니터링 설정 (실제 다운로드 URL 캡처)
            let capturedDownloadUrl = null;
            let capturedPostData = null;
            const requestListener = (request) => {
                const url = request.url();
                // FileDown.jsp 요청 감지
                if (url.includes('FileDown')) {
                    capturedDownloadUrl = url;
                    console.log('🔍 캡처된 다운로드 URL:', url);

                    // POST 요청인 경우 POST 데이터도 확인
                    const postData = request.postData();
                    if (postData) {
                        capturedPostData = postData;
                        console.log('📤 POST 데이터:', postData);
                    }
                }
            };

            this.page.on('request', requestListener);

            // 3단계: 다운로드 이벤트 리스너 설정을 Promise로 감싸기
            let downloadResolve, downloadReject;
            let downloadTimeout;

            const downloadPromise = new Promise((resolve, reject) => {
                downloadResolve = resolve;
                downloadReject = reject;
                downloadTimeout = setTimeout(() => {
                    reject(new Error('다운로드 타임아웃 (60초)'));
                }, 60000);
            });

            const downloadHandler = async (download) => {
                try {
                    clearTimeout(downloadTimeout);

                    const suggestedFileName = download.suggestedFilename();
                    const finalFileName = suggestedFileName || cleanFileName;
                    const savePath = path.join(attachDir, sanitize(finalFileName, { replacement: '_' }));

                    // 디렉토리가 없으면 생성
                    const saveDir = path.dirname(savePath);
                    fs.ensureDirSync(saveDir);

                    await download.saveAs(savePath);

                    // 파일이 실제로 저장되었는지 확인
                    if (await fs.pathExists(savePath)) {
                        const stats = await fs.stat(savePath);
                        console.log(`✅ 파일 저장 성공: ${savePath} (${stats.size} bytes)`);

                        // 이벤트 리스너 제거
                        this.page.off('download', downloadHandler);

                        // 캡처된 URL 정보 포함
                        downloadResolve({
                            success: true,
                            savedPath: savePath,
                            size: stats.size,
                            capturedUrl: capturedDownloadUrl,
                            capturedPostData: capturedPostData
                        });
                    } else {
                        throw new Error('파일이 저장되지 않았습니다');
                    }
                } catch (error) {
                    clearTimeout(downloadTimeout);
                    this.page.off('download', downloadHandler);
                    downloadReject(error);
                }
            };

            // 다운로드 이벤트 리스너 등록
            this.page.on('download', downloadHandler);
            console.log('다운로드 이벤트 리스너 설정 완료');

            // 3단계: 네트워크 인터셉트를 설정하고 폼 제출 (한 번만 다운로드)
            const networkInterceptPromise = this.setupNetworkInterceptForDownload(fileNm, sysFileNm, filePath, attachDir);

            // 4단계: 폼 제출 실행

            // URL 디코딩을 한 번만 수행 (과도한 인코딩 방지)
            const decodedFileNm = decodeURIComponent(fileNm);
            const decodedSysFileNm = decodeURIComponent(sysFileNm);

            console.log('디코딩된 파라미터:', {
                originalFileNm: fileNm,
                decodedFileNm: decodedFileNm,
                originalSysFileNm: sysFileNm,
                decodedSysFileNm: decodedSysFileNm,
                filePath: filePath
            });

            const execResult = await this.page.evaluate((params) => {
                const { decodedFileNm, decodedSysFileNm, filePath } = params;

                console.log('fn_egov_downFile 실행 (디코딩된 파라미터):', {
                    decodedFileNm, decodedSysFileNm, filePath
                });

                try {
                    // 대구광역시의 실제 fn_egov_downFile 함수 호출
                    if (typeof fn_egov_downFile === 'function') {
                        fn_egov_downFile(decodedFileNm, decodedSysFileNm, filePath);
                        return { success: true, method: 'direct_function_call' };
                    } else {
                        // 함수가 없으면 수동 폼 제출
                        const form = document.getElementById('fileForm') || document.createElement('form');
                        form.id = 'fileForm';
                        form.method = 'post';
                        form.action = 'https://eminwon.andong.go.kr/emwp/jsp/ofr/FileDownNew.jsp';
                        form.target = '_self';
                        form.style.display = 'none';

                        // 기존 input 제거 후 새로 추가
                        form.innerHTML = '';

                        const inputs = [
                            { name: 'user_file_nm', value: decodedFileNm },
                            { name: 'sys_file_nm', value: decodedSysFileNm },
                            { name: 'file_path', value: filePath }
                        ];

                        inputs.forEach(input => {
                            const hiddenInput = document.createElement('input');
                            hiddenInput.type = 'hidden';
                            hiddenInput.name = input.name;
                            hiddenInput.value = input.value;
                            form.appendChild(hiddenInput);
                        });

                        if (!document.body.contains(form)) {
                            document.body.appendChild(form);
                        }

                        console.log('폼 제출 실행 (디코딩된 값으로)...');
                        form.submit();
                        return { success: true, method: 'manual_form_submit' };
                    }
                } catch (error) {
                    console.error('함수 실행 오류:', error);
                    return { success: false, error: error.message };
                }
            }, { decodedFileNm, decodedSysFileNm, filePath });

            console.log('fn_egov_downFile 실행 결과:', execResult);

            // 5단계: 네트워크 인터셉트 또는 CDP 다운로드 완료 대기
            try {
                // 네트워크 인터셉트가 먼저 성공하면 그것을 사용
                const result = await Promise.race([
                    networkInterceptPromise,
                    downloadPromise
                ]);

                if (result && result.success) {
                    // 리스너 제거
                    this.page.off('download', downloadHandler);
                    this.page.off('request', requestListener);

                    // 캡처된 URL 출력
                    if (capturedDownloadUrl) {
                        console.log('📋 최종 다운로드 URL:', capturedDownloadUrl);
                    }

                    console.log(`✅ 파일 다운로드 성공: ${result.savedPath || result.fileName}`);

                    // 캡처한 URL 정보가 없으면 추가
                    if (!result.capturedUrl && capturedDownloadUrl) {
                        result.capturedUrl = capturedDownloadUrl;
                        result.capturedPostData = capturedPostData;
                    }

                    return result;
                }
            } catch (error) {
                console.log(`❌ 다운로드 실패: ${error.message}`);

                // 리스너 제거
                this.page.off('download', downloadHandler);
                this.page.off('request', requestListener);

                // 캡처된 URL이 있으면 출력 (디버깅용)
                if (capturedDownloadUrl) {
                    console.log('⚠️ 다운로드 실패했지만 URL은 캡처됨:', capturedDownloadUrl);
                }

                throw error;
            }

        } catch (error) {
            console.error('대구광역시 fn_egov_downFile 실행 중 오류:', error.message);
            throw error;
        }
    }

    /**
     * 네트워크 인터셉트 설정 (Promise 반환)
     */
    async setupNetworkInterceptForDownload(fileNm, sysFileNm, filePath, attachDir) {
        console.log('네트워크 인터셉트 설정 중...');
        const cleanFileName = sanitize(decodeURIComponent(fileNm), { replacement: '_' });
        const savePath = path.join(attachDir, cleanFileName);

        // 네트워크 요청 인터셉트 Promise 반환
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                this.page.unroute('**/*');
                reject(new Error('네트워크 인터셉트 타임아웃'));
            }, 30000);

            const requestHandler = async (route) => {
                const request = route.request();

                if (request.url().includes('FileDown.jsp') || request.url().includes('FileDownNew.jsp')) {
                    console.log('FileDown 요청 인터셉트:', request.url());

                    try {
                        const response = await route.fetch();
                        const buffer = await response.body();
                        console.log(`응답 수신: ${response.status()} - ${buffer.length} bytes`);

                        const contentType = response.headers()['content-type'] || '';
                        const contentDisposition = response.headers()['content-disposition'] || '';

                        if (buffer.length > 200 && !contentType.includes('text/html')) {
                            // 파일 저장
                            await fs.writeFile(savePath, buffer);

                            if (await fs.pathExists(savePath)) {
                                const stats = await fs.stat(savePath);
                                console.log(`✅ 네트워크 인터셉트로 파일 저장 성공: ${savePath} (${stats.size} bytes)`);

                                clearTimeout(timeout);
                                this.page.unroute('**/*', requestHandler);

                                // 빈 응답으로 응답 (추가 다운로드 방지)
                                try {
                                    await route.fulfill({
                                        status: 200,
                                        contentType: 'text/plain',
                                        body: ''
                                    });
                                } catch (e) {
                                    // 이미 처리된 경우 무시
                                    console.log('Route already handled, ignoring');
                                }

                                resolve({
                                    success: true,
                                    savedPath: savePath,
                                    size: stats.size,
                                    downloadMethod: 'NetworkIntercept',
                                    fileName: cleanFileName
                                });
                                return;
                            }
                        }
                        // 파일이 아니면 계속 진행
                        await route.continue();
                    } catch (error) {
                        console.error('네트워크 인터셉트 처리 중 오류:', error);
                        await route.continue();
                    }
                } else {
                    await route.continue();
                }
            };

            // 라우트 설정
            this.page.route('**/*', requestHandler);
        });
    }

    /**
     * 네트워크 인터셉트를 통한 파일 다운로드 (강력한 fallback)
     */
    async downloadViaNetworkIntercept(fileNm, sysFileNm, filePath, attachDir, fileName) {
        try {
            console.log('네트워크 인터셉트 방식 다운로드 시작...');

            const cleanFileName = sanitize(decodeURIComponent(fileNm), { replacement: '_' });
            const savePath = path.join(attachDir, cleanFileName);

            // 실제 다운로드 URL 구성
            const actualDownloadUrl = 'https://eminwon.andong.go.kr/emwp/jsp/ofr/FileDown.jsp';
            const downloadParams = {
                user_file_nm: decodeURIComponent(fileNm),
                sys_file_nm: decodeURIComponent(sysFileNm),
                file_path: filePath
            };
            const fullDownloadUrl = `${actualDownloadUrl}?user_file_nm=${encodeURIComponent(downloadParams.user_file_nm)}&sys_file_nm=${encodeURIComponent(downloadParams.sys_file_nm)}&file_path=${encodeURIComponent(downloadParams.file_path)}`;

            console.log('네트워크 인터셉트 - 실제 다운로드 URL:', fullDownloadUrl);

            // 네트워크 요청 인터셉트 설정
            const interceptPromise = new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    reject(new Error('네트워크 인터셉트 타임아웃'));
                }, 30000);

                const requestHandler = async (route) => {
                    const request = route.request();

                    if (request.url().includes('FileDown.jsp') || request.url().includes('FileDownNew.jsp')) {
                        console.log('FileDown 요청 인터셉트:', request.url());
                        console.log('POST 데이터:', request.postData());

                        try {
                            // 원래 요청을 그대로 실행하고 응답 받기
                            const response = await route.fetch();
                            const buffer = await response.body();

                            console.log(`응답 수신: ${response.status()} - ${buffer.length} bytes`);

                            // 응답이 파일인지 확인 (HTML 에러 페이지가 아닌지)
                            const contentType = response.headers()['content-type'] || '';
                            const contentDisposition = response.headers()['content-disposition'] || '';

                            // 파일명 추출
                            let suggestedFileName = cleanFileName;
                            if (contentDisposition) {
                                const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                                if (filenameMatch) {
                                    suggestedFileName = filenameMatch[1].replace(/['"]/g, '').trim();
                                    if (suggestedFileName.includes('%')) {
                                        try {
                                            suggestedFileName = decodeURIComponent(suggestedFileName);
                                        } catch (e) {
                                            console.log('파일명 디코딩 실패:', e.message);
                                        }
                                    }
                                }
                            }

                            if (buffer.length > 200 && !contentType.includes('text/html')) {
                                // 파일 저장
                                await fs.writeFile(savePath, buffer);

                                // 저장 확인
                                if (await fs.pathExists(savePath)) {
                                    const stats = await fs.stat(savePath);
                                    console.log(`✅ 네트워크 인터셉트로 파일 저장 성공: ${savePath} (${stats.size} bytes)`);
                                    console.log(`📎 실제 다운로드 URL: ${fullDownloadUrl}`);

                                    clearTimeout(timeout);

                                    // route.fulfill()로 응답 완료 처리 (추가 다운로드 방지)
                                    await route.fulfill({
                                        status: 200,
                                        contentType: contentType || 'application/octet-stream',
                                        body: buffer,
                                        headers: {
                                            'content-disposition': contentDisposition || `attachment; filename="${suggestedFileName}"`
                                        }
                                    });

                                    resolve({
                                        success: true,
                                        savedPath: savePath,
                                        size: stats.size,
                                        actualDownloadUrl: fullDownloadUrl,
                                        downloadMethod: 'NetworkIntercept',
                                        fileName: suggestedFileName,
                                        contentType: contentType
                                    });
                                    return;
                                }
                            } else {
                                console.log('응답이 파일이 아닌 것으로 판단:', {
                                    contentType,
                                    size: buffer.length,
                                    preview: buffer.toString('utf-8', 0, 100)
                                });
                            }

                            // 정상 응답이 아니면 계속 진행
                            await route.continue();

                        } catch (error) {
                            console.error('네트워크 인터셉트 처리 중 오류:', error);
                            await route.continue();
                        }
                    } else {
                        // 다른 요청은 그대로 통과
                        await route.continue();
                    }
                };

                // 라우트 설정
                this.page.route('**/*', requestHandler);

                // 5초 후 라우트 해제 (무한 대기 방지)
                setTimeout(() => {
                    this.page.unroute('**/*', requestHandler);
                }, 35000);
            });

            // fn_egov_downFile 함수 재실행 (디코딩된 파라미터 사용)
            const decodedFileNm = decodeURIComponent(fileNm);
            const decodedSysFileNm = decodeURIComponent(sysFileNm);

            await this.page.evaluate((params) => {
                const { decodedFileNm, decodedSysFileNm, filePath } = params;
                console.log('네트워크 인터셉트용 fn_egov_downFile 재실행 (디코딩된 파라미터)');

                if (typeof fn_egov_downFile === 'function') {
                    fn_egov_downFile(decodedFileNm, decodedSysFileNm, filePath);
                } else {
                    // 수동 폼 제출
                    const form = document.createElement('form');
                    form.method = 'post';
                    form.action = 'https://eminwon.andong.go.kr/emwp/jsp/ofr/FileDown.jsp';
                    form.style.display = 'none';

                    const inputs = [
                        { name: 'user_file_nm', value: decodedFileNm },
                        { name: 'sys_file_nm', value: decodedSysFileNm },
                        { name: 'file_path', value: filePath }
                    ];

                    inputs.forEach(input => {
                        const hiddenInput = document.createElement('input');
                        hiddenInput.type = 'hidden';
                        hiddenInput.name = input.name;
                        hiddenInput.value = input.value;
                        form.appendChild(hiddenInput);
                    });

                    document.body.appendChild(form);
                    form.submit();
                    form.remove();
                }
            }, { decodedFileNm, decodedSysFileNm, filePath });

            // 네트워크 인터셉트 결과 대기
            const result = await interceptPromise;
            console.log(`📁 네트워크 인터셉트 다운로드 완료:`, {
                fileName: result.fileName,
                actualUrl: result.actualDownloadUrl,
                method: result.downloadMethod
            });
            return result;

        } catch (error) {
            console.error('네트워크 인터셉트 다운로드 실패:', error.message);
            throw error;
        }
    }

    /**
     * CDP를 통한 다운로드 동작 설정
     */
    async setupDownloadBehavior(downloadPath) {
        try {
            console.log(`CDP 다운로드 설정 - 경로: ${downloadPath}`);

            // CDP 세션 생성
            const client = await this.page.context().newCDPSession(this.page);

            // 다운로드 동작 설정
            await client.send('Page.setDownloadBehavior', {
                behavior: 'allow',
                downloadPath: downloadPath
            });

            // 브라우저 다운로드 허용 설정
            await client.send('Browser.setDownloadBehavior', {
                behavior: 'allow',
                downloadPath: downloadPath
            });

            console.log('✅ CDP 다운로드 설정 완료');
            return client;
        } catch (error) {
            console.warn(`⚠️ CDP 설정 실패 (계속 진행): ${error.message}`);
            return null;
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

            // 폴더 중복 검사 (force 옵션이 없는 경우)
            if (!this.force && await fs.pathExists(folderPath)) {
                console.log(`폴더가 이미 존재하여 스킵: ${folderName}`);
                return;
            }

            await fs.ensureDir(folderPath);

            // 첨부파일 다운로드 먼저 실행 (실제 URL 캡처)
            let actualUrlInfo = [];
            if (detailContent.attachments && detailContent.attachments.length > 0) {
                actualUrlInfo = await this.downloadAttachments(detailContent.attachments, folderPath);
            }

            // 실제 다운로드 URL 정보를 포함해서 content.md 생성
            const contentMd = this.generateMarkdownContent(announcement, detailContent, actualUrlInfo);
            await fs.writeFile(path.join(folderPath, 'content.md'), contentMd, 'utf8');

            this.counter++;

        } catch (error) {
            console.error('공고 저장 실패:', error);
        }
    }

    /**
     * 첨부파일 다운로드
     */
    /**
     * 첨부파일 다운로드
     * @returns {Array} 실제 다운로드 URL 정보가 포함된 배열
     */
    async downloadAttachments(attachments, folderPath) {
        const actualUrlInfo = [];

        try {
            const attachDir = path.join(folderPath, 'attachments');
            await fs.ensureDir(attachDir);

            console.log(`${attachments.length}개 첨부파일 다운로드 중...`);

            for (let i = 0; i < attachments.length; i++) {
                const attachment = attachments[i];
                const result = await this.downloadSingleAttachment(attachment, attachDir, i + 1);

                // 다운로드 결과에서 실제 URL 정보 저장
                if (result && result.capturedUrl) {
                    actualUrlInfo.push({
                        name: attachment.name,
                        originalUrl: attachment.url,
                        actualUrl: result.capturedUrl,
                        postData: result.capturedPostData
                    });
                }

                await this.delay(500); // 0.5초 대기
            }

        } catch (error) {
            console.error('첨부파일 다운로드 실패:', error);
        }

        return actualUrlInfo;
    }

    /**
     * 단일 첨부파일 다운로드
     */
    // async downloadSingleAttachment(attachment, attachDir, index) {
    //     try {
    //         let downloadUrl = attachment.url;
    //         let fileName = attachment.name || `attachment_${index}`;

    //         // JavaScript 방식 처리
    //         if (attachment.onclick) {
    //             // goDownload 패턴 처리
    //             const goDownloadMatch = attachment.onclick.match(/goDownload\(\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*\)/);

    //             if (goDownloadMatch) {
    //                 const [, originalName, serverName, serverPath] = goDownloadMatch;
    //                 // 실제 goDownload 함수와 동일한 URL 패턴 사용
    //                 const enc_user_file_nm = encodeURIComponent(originalName);
    //                 const enc_sys_file_nm = encodeURIComponent(serverName);
    //                 const enc_file_path = encodeURIComponent(serverPath);
    //                 downloadUrl = `https://eminwon.icheon.go.kr/emwp/jsp/ofr/FileDown.jsp?user_file_nm=${enc_user_file_nm}&sys_file_nm=${enc_sys_file_nm}&file_path=${enc_file_path}`;
    //                 fileName = originalName; // 원본 파일명 사용
    //             } else {
    //                 // 기존 onclick 이벤트에서 URL 추출 시도
    //                 const match = attachment.onclick.match(/(?:window\.open|location\.href|download)\(['"]([^'"]*)['"]\)/);
    //                 if (match) {
    //                     downloadUrl = match[1];
    //                 }
    //             }

    //             console.log('JAVASCRIPT 방식', downloadUrl)
    //         }

    //         // 상대 URL을 절대 URL로 변환
    //         if (downloadUrl && !downloadUrl.startsWith('http')) {
    //             console.log('상대 URL을 절대 URL로 변환')
    //             downloadUrl = new URL(downloadUrl, this.baseUrl).toString();
    //         }

    //         if (!downloadUrl || !downloadUrl.startsWith('http')) {
    //             console.log(`유효하지 않은 다운로드 URL: ${downloadUrl}`);
    //             return;
    //         }


    //         // POST 방식 또는 특별한 처리가 필요한 경우
    //         if (attachment.onclick && attachment.onclick.includes('submit')) {
    //             await this.downloadViaForm(attachment, attachDir, fileName);
    //         } else {
    //             // 일반 링크 방식
    //             await this.downloadViaLink(downloadUrl, attachDir, fileName);
    //         }

    //         console.log(`!!!!!!!!!!!!!!!!!다운로드 완료: ${fileName}!!!!!!!!!!!!!!!!`);
    //     } catch (error) {
    //         console.error(`첨부파일 다운로드 실패 (${attachment.name}):`, error);
    //     }
    // }

    /**
     * 링크 방식 다운로드
     */
    async downloadViaLink(url, attachDir, fileName) {
        try {
            console.log("다운로드 시작:", url);

            // 장흥군의 eminwon_download는 2단계 다운로드 시스템
            if (url.includes('eminwon_download')) {
                return await this.downloadViaEminwon(url, attachDir, fileName);
            }

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
            throw new Error(`링크 다운로드 실패: ${error.message}`);
        }
    }

    /**
     * 장흥군 eminwon 시스템의 2단계 다운로드
     */
    async downloadViaEminwon(url, attachDir, fileName) {
        try {
            console.log("장흥군 eminwon 2단계 다운로드:", url);

            // 1단계: HTML 폼 가져오기
            const formResponse = await axios({
                method: 'GET',
                url: url,
                timeout: 30000,
                headers: {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            });

            console.log(`폼 응답 상태: ${formResponse.status}, HTML 크기: ${formResponse.data.length} bytes`);

            // HTML에서 폼 데이터 추출
            const $ = cheerio.load(formResponse.data);
            const form = $('form[name="nnn"]');
            const action = form.attr('action');
            const userFileName = $('input[name="user_file_nm"]').val();
            const sysFileName = $('input[name="sys_file_nm"]').val();
            const filePath = $('input[name="file_path"]').val();

            if (!action || !userFileName || !sysFileName || !filePath) {
                throw new Error('폼 데이터 추출 실패');
            }

            console.log(`폼 액션: ${action}`);
            console.log(`HTML에서 추출된 파일명: ${userFileName}`);

            // Base64 URL에서 원본 파일명 추출 시도
            let originalFileName = fileName; // 기본값
            try {
                const base64Param = url.split('get_file=')[1];
                const decodedData = Buffer.from(decodeURIComponent(base64Param), 'base64').toString('utf8');
                console.log(`Base64 디코딩 데이터: ${decodedData.substring(0, 200)}...`);

                // PHP 직렬화 데이터에서 user_file_nm 추출
                const userFileMatch = decodedData.match(/s:\d+:"user_file_nm";s:\d+:"([^"]+)"/);
                if (userFileMatch) {
                    const encodedFileName = userFileMatch[1];
                    console.log(`추출된 인코딩 파일명: ${encodedFileName}`);

                    // URL 디코딩
                    const decodedFileName = decodeURIComponent(encodedFileName);
                    console.log(`URL 디코딩된 파일명: ${decodedFileName}`);

                    if (decodedFileName && !this.hasCorruptedKorean(decodedFileName)) {
                        originalFileName = decodedFileName;
                        console.log(`Base64에서 복원된 파일명 사용: ${originalFileName}`);
                    }
                }
            } catch (e) {
                console.log(`Base64 파일명 추출 실패: ${e.message}`);
            }

            // 2단계: 폼 데이터로 실제 파일 다운로드
            const formData = new URLSearchParams();
            formData.append('user_file_nm', userFileName);
            formData.append('sys_file_nm', sysFileName);
            formData.append('file_path', filePath);

            const fileResponse = await axios({
                method: 'POST',
                url: action,
                data: formData.toString(),
                responseType: 'arraybuffer',
                timeout: 30000,
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': '*/*',
                    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Referer': url
                }
            });

            console.log(`실제 파일 응답 상태: ${fileResponse.status}, 크기: ${fileResponse.data.byteLength} bytes`);

            // 실제 파일인지 확인 (HTML이 아닌지 체크)
            const responseText = Buffer.from(fileResponse.data).toString('utf8', 0, 100);
            if (responseText.includes('<!DOCTYPE') || responseText.includes('<html')) {
                console.log('여전히 HTML 응답:', responseText.substring(0, 200));
                throw new Error('여전히 HTML 응답이 반환됨 - 다운로드 실패');
            }

            // 파일명 결정 - 한글 처리 개선
            let finalFileName = originalFileName; // Base64에서 복원된 파일명 사용

            // Content-Disposition 헤더에서 파일명 추출 시도
            const contentDisposition = fileResponse.headers['content-disposition'];
            if (contentDisposition) {
                console.log(`Content-Disposition: ${contentDisposition}`);

                // UTF-8 인코딩된 파일명 처리 시도
                const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
                if (utf8Match) {
                    try {
                        finalFileName = decodeURIComponent(utf8Match[1]);
                        console.log(`UTF-8 파일명 추출: ${finalFileName}`);
                    } catch (e) {
                        console.log(`UTF-8 디코딩 실패: ${e.message}`);
                    }
                } else {
                    // 일반 filename 처리
                    const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                    if (match) {
                        let extractedName = match[1].replace(/['"]/g, '').trim();

                        // URL 인코딩 디코딩 시도
                        if (extractedName.includes('%')) {
                            try {
                                extractedName = decodeURIComponent(extractedName);
                                console.log(`URL 디코딩 파일명: ${extractedName}`);
                            } catch (e) {
                                console.log(`URL 디코딩 실패: ${e.message}`);
                            }
                        }

                        if (extractedName && extractedName !== 'attachment') {
                            finalFileName = extractedName;
                        }
                    }
                }
            }

            // 파일명이 여전히 깨져있으면 원본 fileName 사용
            if (this.hasCorruptedKorean(finalFileName)) {
                console.log(`파일명이 깨져서 원본 사용: ${fileName}`);
                finalFileName = fileName;
            }

            // 파일명 정리 (한글 보존하면서 안전한 문자만 사용)
            const cleanFileName = this.sanitizeKoreanFileName(finalFileName);
            const savePath = path.join(attachDir, cleanFileName);

            await fs.writeFile(savePath, Buffer.from(fileResponse.data));

            console.log(`장흥군 파일 다운로드 완료: ${cleanFileName} (${fileResponse.data.byteLength} bytes)`);

        } catch (error) {
            throw new Error(`장흥군 eminwon 다운로드 실패: ${error.message}`);
        }
    }

    /**
     * 한글이 깨져있는지 확인
     */
    hasCorruptedKorean(filename) {
        // UTF-8 깨진 패턴들 (ë__, ì_, ê³_ 등)
        return /[ëì]_+|[ê][³ł°µ¹±¸²]_|[ì][°ª­²¦¬¥­¨_]|[³_]+/.test(filename);
    }

    /**
     * 한글 파일명을 안전하게 정리
     */
    sanitizeKoreanFileName(filename) {
        if (!filename) return 'attachment';

        // 이미 깨진 파일명인 경우는 그대로 사용하지 않음
        if (this.hasCorruptedKorean(filename)) {
            return 'attachment';
        }

        // 위험한 문자들만 교체 (한글은 보존)
        return filename
            .replace(/[<>:"/\\|?*]/g, '_')  // 파일시스템에서 위험한 문자들
            .replace(/\s+/g, ' ')          // 연속 공백을 하나로
            .trim();
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
            throw new Error(`폼 다운로드 실패: ${error.message}`);
        }
    }

    /**
     * 마크다운 컨텐츠 생성
     */
    /**
     * goDownLoad/goDownload JavaScript 호출을 실제 다운로드 URL로 변환
     * andong 사이트는 encodeURI()를 사용함
     */
    convertJsDownloadToUrl(jsUrl) {
        // goDownLoad 또는 goDownload 패턴 파싱 (대소문자 모두 지원)
        const regex = /goDownload\('([^']+)',\s*'([^']+)',\s*'([^']+)'\)/i;
        const matches = jsUrl.match(regex);

        if (matches && matches.length === 4) {
            const [, fileNm, sysFileNm, filePath] = matches;

            // andong 사이트의 실제 goDownload 함수와 동일하게 encodeURI() 사용
            const enc_user_file_nm = encodeURI(fileNm);
            const enc_sys_file_nm = encodeURI(sysFileNm);
            const enc_file_path = encodeURI(filePath);

            return `https://eminwon.andong.go.kr/emwp/jsp/ofr/FileDown.jsp?user_file_nm=${enc_user_file_nm}&sys_file_nm=${enc_sys_file_nm}&file_path=${enc_file_path}`;
        }

        return jsUrl; // 변환 실패시 원본 반환
    }

    generateMarkdownContent(announcement, detailContent, actualUrlInfo = []) {
        const lines = [];

        lines.push(`# ${announcement.title}`);
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
                // actualUrlInfo에서 실제 다운로드 정보 찾기
                const actualInfo = actualUrlInfo.find(info => info.name === att.name);

                if (actualInfo && actualInfo.actualUrl) {
                    // 실제 캡처된 URL과 POST 데이터를 쿼리스트링으로 합치기

                    console.log("실제 캡처된 URL과 POST 데이터를 쿼리스트링으로 합치기")
                    let fullUrl = actualInfo.actualUrl;
                    if (actualInfo.postData) {
                        fullUrl = `${actualInfo.actualUrl}?${actualInfo.postData}`;
                    }
                    lines.push(`${i + 1}. ${att.name}: ${fullUrl}`);
                } else {
                    console.log("캡처된 정보가 없으면 기존 방식으로")
                    // 캡처된 정보가 없으면 기존 방식으로
                    let downloadUrl = att.url;
                    if (downloadUrl && /godownload/i.test(downloadUrl)) {
                        downloadUrl = this.convertJsDownloadToUrl(downloadUrl);
                    }
                    lines.push(`${i + 1}. ${att.name}: ${downloadUrl}`);
                }
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

        ///board/GosiView.do?pageIndex=1&menuNo=115004002001&not_ancmt_se_code=01,04,06,07' + '&not_ancmt_mgt_no=' + not_ancmt_mgt_no;

        // 1. data-action 속성이 있는 경우 (우선순위 높음)
        if (announcement.dataAction) {
            const detailUrl = new URL(announcement.dataAction, this.baseUrl).toString();
            return detailUrl;
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

        // 4. onclick 이벤트에서 URL 추출 시도
        if (announcement.onclick) {
            console.log('onclick 분석 중:', announcement.onclick);

            // req.post(this) 패턴 - data-action 사용
            if (announcement.onclick.includes('req.post(this)') && announcement.dataAction) {
                const detailUrl = new URL(announcement.dataAction, this.baseUrl).toString();
                console.log('onclick + data-action으로 구성된 URL:', detailUrl);
                return detailUrl;
            }

            // 일반적인 JavaScript URL 패턴들
            const jsPatterns = [
                /location\.href\s*=\s*['"]([^'"]+)['"]/,
                /window\.open\s*\(\s*['"]([^'"]+)['"]/,
                /goView\s*\(\s*['"]([^'"]+)['"]/,
                /href\s*=\s*['"]([^'"]+)['"]/
            ];

            for (const pattern of jsPatterns) {
                const match = announcement.onclick.match(pattern);
                if (match) {
                    const extractedUrl = match[1];
                    if (extractedUrl.startsWith('/')) {
                        const detailUrl = new URL(extractedUrl, this.baseUrl).toString();
                        console.log('JavaScript 패턴으로 추출된 URL:', detailUrl);
                        return detailUrl;
                    } else if (extractedUrl.startsWith('http')) {
                        console.log('JavaScript에서 추출된 완전 URL:', extractedUrl);
                        return extractedUrl;
                    }
                }
            }
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
        url.searchParams.set('page', pageNum);
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
            default: 'andong',
            required: true
        })
        .option('url', {
            alias: 'u',
            type: 'string',
            description: '기본 URL',
            default: 'https://www.andong.go.kr/portal/saeol/gosi/list.do?seCode=04&mId=0401020300',
            required: true
        })
        .option('list-selector', {
            type: 'string',
            description: '리스트 선택자',
            default: 'table.bod_list tbody tr'
        })
        .option('title-selector', {
            type: 'string',
            description: '제목 선택자',
            default: 'td:nth-child(3) a'
        })
        .option('date-selector', {
            type: 'string',
            description: '날짜 선택자',
            default: 'td:nth-child(5)'
        })
        .option('force', {
            alias: 'f',
            type: 'boolean',
            description: '기존 폴더가 있어도 덮어쓰기',
            default: false
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
            description: '배치 날짜 (YYYY-MM-DD 형식, count 모드에서 사용)',
            default: null
        })
        .example('$0 --site andong --year 2024', '안동시 2024년 공고 스크래핑')
        .example('$0 --site andong --year 2024 --count', '안동시 2024년 공고 URL만 추출')
        .example('$0 --site andong --date 20240101 --count', '안동시 2024-01-01 이후 공고 URL 추출')
        .help()
        .argv;
}


// 메인 실행
async function main() {
    const argv = setupCLI();

    const scraper = new AnnouncementScraper({
        targetYear: argv.year,
        targetDate: argv.date,
        outputDir: argv.output,
        siteCode: argv.site,
        baseUrl: argv.url,
        listSelector: argv.listSelector,
        titleSelector: argv.titleSelector,
        dateSelector: argv.dateSelector,
        force: argv.force
    });

    // --count 옵션이 있으면 URL만 추출
    if (argv.count) {
        console.log('URL 추출 모드 (다운로드 없음)');
        const result = await scraper.extractAndSaveUrls(argv.batchDate);

        console.log('\n=== 완료 ===');
        console.log(`총 URL: ${result.totalCount}개`);
        console.log(`저장 성공: ${result.savedCount}개`);
        console.log(`페이지 수: ${result.pageCount}개`);

        // 통계 출력
        const UrlManager = require('./url_manager');
        const stats = await UrlManager.getStats(argv.site, argv.batchDate || moment().format('YYYY-MM-DD'));
        console.log(`\nDB 통계:`);
        console.log(`  전체: ${stats.total}개`);
        console.log(`  스크래핑 완료: ${stats.scraped}개`);
        console.log(`  스크래핑 대기: ${stats.unscraped}개`);
    } else {
        // 기존 스크래핑 모드
        await scraper.scrape();
    }
}

// 스크립트가 직접 실행될 때만 main 함수 호출
if (require.main === module) {
    main().catch(console.error);
}

module.exports = AnnouncementScraper;
