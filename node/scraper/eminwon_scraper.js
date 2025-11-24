#!/usr/bin/env node

/**
 * Eminwon 통합 스크래퍼
 *
 * 기능:
 * 1. eminwon.json에서 지역별 호스트 정보 자동 조회
 * 2. 날짜 기반 필터링 (YYYYMMDD 형태)
 * 3. 리스트 -> 상세 페이지 처리
 * 4. JavaScript 기반 동적 페이지 처리
 * 5. content.md 파일 생성 및 첨부파일 다운로드
 * 6. 중복 게시물 스킵
 * 7. 폴더 구조: 001_게시물이름/content.md, attachments/
 *
 * Eminwon 사이트 공통 특징:
 * - JavaScript 기반 페이징 (goPage 함수)
 * - searchDetail 함수로 상세 페이지 이동
 * - 첨부파일 다운로드 (goDownLoad, fnFileDown 함수)
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

class EminwonScraper {
    constructor(options = {}) {
        this.region = options.region || '청양군';
        this.targetDate = options.targetDate;
        this.baseOutputDir = options.outputDir || 'eminwon_data';
        this.siteCode = options.siteCode || this.region.replace(/시$|군$|구$/g, '');
        this.outputDir = path.join(this.baseOutputDir, this.siteCode);
        this.force = options.force || false;
        this.goPage = options.goPage || null;

        // eminwon.json에서 호스트 정보 로드
        this.eminwonHosts = this.loadEminwonHosts();
        const hostUrl = this.eminwonHosts[this.region];
        if (!hostUrl) {
            throw new Error(`지역 '${this.region}'에 대한 호스트 정보를 찾을 수 없습니다.`);
        }
        //https://eminwon.taean.go.kr/emwp/jsp/ofr/OfrNotAncmtL.jsp?not_ancmt_se_code=01,02,03,04,05&list_gubun=A

        this.baseUrl = `https://${hostUrl}`;
        // this.listUrl = `https://${hostUrl}/emwp/jsp/ofr/OfrNotAncmtL.jsp?not_ancmt_se_code=01,02,03,04,05,06&list_gubun=A`;

        this.listUrl = `https://${hostUrl}/emwp/jsp/ofr/OfrNotAncmtL.jsp?not_ancmt_se_code=01,02,03,04,05&list_gubun=A`

        this.actionUrl = `https://${hostUrl}/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do`;
        this.browser = null;
        this.context = null;
        this.page = null;
        this.processedTitles = new Set();
        this.counter = 1;
        this.options = options;
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
     * 기존 폴더에서 처리된 제목들 로드
     */
    async loadExistingTitles() {
        try {
            // 출력 디렉토리가 존재하는지 확인
            if (await fs.pathExists(this.outputDir)) {
                const existingFolders = await fs.readdir(this.outputDir);
                let loadedCount = 0;

                existingFolders.forEach(folderName => {
                    // 폴더명에서 번호_제목 패턴에서 제목 부분 추출
                    const match = folderName.match(/^\d{3}_(.+)$/);
                    if (match) {
                        const existingTitle = match[1];
                        // sanitize된 제목을 역으로 복원하기 어려우므로, 
                        // 간단히 기존 폴더명의 제목 부분을 Set에 추가
                        this.processedTitles.add(existingTitle);
                        loadedCount++;

                        // 카운터도 업데이트 (가장 큰 번호 + 1)
                        const folderNumber = parseInt(folderName.substring(0, 3));
                        if (folderNumber >= this.counter) {
                            this.counter = folderNumber + 1;
                        }
                    }
                });

                if (loadedCount > 0) {
                    console.log(`📚 기존 처리된 제목 ${loadedCount}개 로드 완료`);
                    console.log(`🔢 폴더 번호 시작점: ${this.counter}번부터`);
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
            }).catch(logErr => { });

            console.log(`📁 기존 제목 로드 실패 (정상 - 신규 시작): ${error.message}`);
        }
    }

    /**
     * eminwon.json에서 호스트 정보 로드
     */
    async loadEminwonHosts() {
        try {
            const hostsPath = path.join(__dirname, 'eminwon.json');
            const hostsData = fs.readJsonSync(hostsPath);
            console.log(`${Object.keys(hostsData).length}개 지역의 호스트 정보 로드`);
            return hostsData;
        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => { });

            console.error('eminwon.json 파일 로드 실패:', error.message);
            throw new Error('eminwon.json 파일을 찾을 수 없습니다.');
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
            }).catch(logErr => { });

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
            }).catch(logErr => { });

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
                    args: [
                        ...config.browser.launchOptions.args,
                        '--allow-running-insecure-content',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ],
                    timeout: config.browser.launchOptions.timeout
                });

                this.context = await this.browser.newContext({
                    userAgent: config.security.userAgent,
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

                // 타임아웃 설정
                this.page.setDefaultTimeout(config.browser.timeouts.default);
                this.page.setDefaultNavigationTimeout(config.browser.timeouts.navigation);

                // 에러 이벤트 리스너
                this.browser.on('disconnected', () => {
                    console.warn('브라우저 연결이 끊어졌습니다.');
                });

                this.page.on('crash', () => {
                    console.warn('페이지 크래시 발생');
                });

                this.page.on('console', (msg) => {
                    //console.log(`[브라우저 콘솔]: ${msg.text()}`);
                });

                this.page.on('pageerror', (error) => {
                    console.warn('페이지 JavaScript 오류:', error.message);
                });

                this.page.on('requestfailed', (request) => {
                    console.warn(`네트워크 요청 실패: ${request.url()} - ${request.failure()?.errorText}`);
                });

                this.page.on('response', (response) => {
                    if (response.status() >= 400) {
                        console.warn(`HTTP 오류 응답: ${response.status()} ${response.url()}`);
                    }
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
                }).catch(logErr => { });

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
                        }).catch(logErr => { });

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

            // 기존 처리된 제목들 로드
            await this.loadExistingTitles();

            let currentPage = this.goPage ? parseInt(this.goPage) : 1;
            let shouldContinue = true;
            let consecutiveErrors = 0;
            const maxConsecutiveErrors = 5;

            console.log(`\n=== ${this.region} 이민원 스크래핑 시작 ===`);
            console.log(`대상 날짜: ${this.targetDate}`);
            console.log(`사이트 코드: ${this.siteCode}`);
            console.log(`기본 URL: ${this.baseUrl}`);
            console.log(`출력 디렉토리: ${this.outputDir}`);
            if (this.goPage) {
                console.log(`시작 페이지: ${currentPage} (--go-page 옵션으로 지정됨)`);
                // 페이지 점프시 카운터 조정 (가정: 페이지당 10개 공고)
                const estimatedItemsPerPage = 10;
                this.counter = ((currentPage - 1) * estimatedItemsPerPage) + 1;
                console.log(`폴더 번호 시작점 조정: ${this.counter}번부터 시작`);
            }

            while (shouldContinue) {
                try {
                    console.log(`\n--- 페이지 ${currentPage} 처리 중 ---`);

                    const announcements = await this.getAnnouncementList(currentPage);

                    if (!announcements || announcements.length === 0) {
                        console.log('더 이상 공고가 없습니다. 스크래핑 종료.');
                        break;
                    }

                    consecutiveErrors = 0;

                    for (let i = 0; i < announcements.length; i++) {
                        const announcement = announcements[i];
                        try {
                            const shouldStop = await this.processAnnouncement(announcement);
                            if (shouldStop) {
                                console.log(`\n대상 날짜 ${this.targetDate} 이전 공고 발견. 스크래핑 종료.`);
                                shouldContinue = false;
                                break;
                            }

                            // 각 공고 처리 사이에 지연시간 추가 (서버 부하 방지)
                            if (i < announcements.length - 1) {
                                console.log('다음 공고 처리 전 잠시 대기...');
                                await this.delay(2000);
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
                            }).catch(logErr => { });

                            console.error(`공고 처리 중 오류 (${announcement.title}):`, announcementError.message);
                            // 오류 발생 시 추가 대기 시간
                            await this.delay(3000);
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
                    }).catch(logErr => { });

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
            }).catch(logErr => { });

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
                console.log(`리스트 URL로 이동: ${this.listUrl}`);

                if (!this.browser || !this.page || this.page.isClosed()) {
                    console.log('브라우저 연결이 끊어져 재초기화합니다...');
                    await this.initBrowser();
                }

                // 태안군 특별 처리: 홈페이지 메인 접근 후 리스트로 이동
                // 태안군 로직 빼기....
                // if (this.region === '태안군' && pageNum === 1) {
                //     console.log('태안군 특별 처리: 홈페이지 메인 경유 방식');

                //     try {
                //         // 1. 먼저 메인 페이지로 접근하여 세션 생성
                //         console.log('1. 태안군 홈페이지 메인 접근...');
                //         await this.page.goto('https://www.taean.go.kr/', {
                //             waitUntil: 'domcontentloaded',
                //             timeout: 30000
                //         });
                //         await this.page.waitForTimeout(2000);

                //         // 2. 이민원 메인 페이지로 이동
                //         console.log('2. 이민원 메인 페이지 접근...');
                //         await this.page.goto(`${this.baseUrl}/emwp/`, {
                //             waitUntil: 'domcontentloaded',
                //             timeout: 30000
                //         });
                //         await this.page.waitForTimeout(2000);

                //         // 3. JSP 리스트 페이지로 이동
                //         console.log('3. JSP 리스트 페이지 접근...');
                //         await this.page.goto(this.listUrl, {
                //             waitUntil: 'networkidle',
                //             timeout: 30000
                //         });
                //         await this.page.waitForTimeout(3000);

                //         // 4. 폼이 있으면 제출
                //         const formExists = await this.page.evaluate(() => {
                //             const form = document.querySelector('form[action*="OfrAction.do"]');
                //             if (form) {
                //                 const pageInput = form.querySelector('input[name="pageIndex"]');
                //                 if (pageInput) pageInput.value = '1';
                //                 form.submit();
                //                 return true;
                //             }
                //             return false;
                //         });

                //         if (formExists) {
                //             console.log('4. 폼 제출 완료, 페이지 로딩 대기...');
                //             await this.page.waitForTimeout(5000);
                //         }

                //         console.log('태안군 특별 처리 완료');
                //     } catch (taeanError) {
                // 실패 공고 DB 기록
                await FailureLogger.logFailedAnnouncement({
                    site_code: this.siteCode,
                    title: announcement?.title || 'Unknown',
                    url: announcement?.link || announcement?.url,
                    detail_url: announcement?.detailUrl,
                    error_type: 'taeanError',
                    error_message: taeanError.message
                }).catch(logErr => { });

                //         console.log('태안군 특별 처리 중 오류:', taeanError.message);
                //         console.log('일반 방식으로 계속 진행합니다...');
                //     }
                // } else {
                // 1단계: 먼저 초기 페이지 방문 (재시도 포함)
                console.log('1단계: 초기 페이지 방문하여 세션 확보...');

                let initialLoadSuccess = false;
                let initialLoadAttempt = 0;
                const maxInitialLoadAttempts = 3;

                while (!initialLoadSuccess && initialLoadAttempt < maxInitialLoadAttempts) {
                    initialLoadAttempt++;
                    try {
                        console.log(`초기 페이지 로드 시도 ${initialLoadAttempt}/${maxInitialLoadAttempts}`);

                        await this.page.goto(this.listUrl, {
                            waitUntil: 'networkidle',
                            timeout: 45000
                        });

                        await this.page.waitForTimeout(4000);
                        initialLoadSuccess = true;

                    } catch (error) {
                        // 실패 공고 DB 기록
                        await FailureLogger.logFailedAnnouncement({
                            site_code: this.siteCode,
                            title: announcement?.title || 'Unknown',
                            url: announcement?.link || announcement?.url,
                            detail_url: announcement?.detailUrl,
                            error_type: 'error',
                            error_message: error.message
                        }).catch(logErr => { });

                        console.warn(`초기 페이지 로드 시도 ${initialLoadAttempt} 실패: ${error.message}`);

                        if (initialLoadAttempt < maxInitialLoadAttempts) {
                            console.log('잠시 대기 후 재시도...');
                            await this.delay(5000 * initialLoadAttempt);
                        }
                    }
                }

                if (!initialLoadSuccess) {
                    console.log('JSP URL 로드 실패. 서블릿 URL로 폴백 시도...');

                    // 서블릿 URL로 직접 접근 시도
                    const servletUrl = `${this.baseUrl}/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do?` +
                        `jndinm=OfrNotAncmtEJB&context=NTIS&method=selectListOfrNotAncmt&` +
                        `methodnm=selectListOfrNotAncmtHomepage&homepage_pbs_yn=Y&subCheck=Y&` +
                        `ofr_pageSize=10&not_ancmt_se_code=01,02,03,04,05,06&title=%EA%B3%A0%EC%8B%9C%EA%B3%B5%EA%B3%A0&` +
                        `initValue=Y&countYn=Y&list_gubun=A&Key=B_Subject&pageIndex=${pageNum}`;

                    try {
                        console.log('서블릿 URL로 직접 접근:', servletUrl);
                        await this.page.goto(servletUrl, {
                            waitUntil: 'domcontentloaded',
                            timeout: 30000
                        });
                        await this.page.waitForTimeout(3000);
                        initialLoadSuccess = true;
                        console.log('서블릿 URL 접근 성공');
                    } catch (servletError) {
                        // 실패 공고 DB 기록
                        await FailureLogger.logFailedAnnouncement({
                            site_code: this.siteCode,
                            title: announcement?.title || 'Unknown',
                            url: announcement?.link || announcement?.url,
                            detail_url: announcement?.detailUrl,
                            error_type: 'servletError',
                            error_message: servletError.message
                        }).catch(logErr => { });

                        console.error('서블릿 URL 접근도 실패:', servletError.message);
                        throw new Error('초기 페이지 로드 실패 - JSP와 서블릿 모두 실패');
                    }
                }

                console.log(`초기 페이지 URL: ${this.page.url()}`);

                // 2단계: 페이지에서 자동으로 POST 요청이 실행되는지 대기
                // 이미 OfrAction.do로 접근한 경우 리다이렉트 대기 건너뛰기
                if (this.page.url().includes('OfrAction.do')) {
                    console.log('이미 서블릿 URL로 접근함. 리다이렉트 단계 건너뛰기');
                } else {
                    console.log('2단계: 자동 리다이렉트 또는 폼 제출 대기...');

                    try {
                        // 5초간 URL 변경 대기
                        await this.page.waitForFunction(
                            () => window.location.href.includes('OfrAction.do'),
                            { timeout: 10000 }
                        );
                        console.log('자동 리다이렉트 완료');
                    } catch (waitError) {
                        // 실패 공고 DB 기록
                        await FailureLogger.logFailedAnnouncement({
                            site_code: this.siteCode,
                            title: announcement?.title || 'Unknown',
                            url: announcement?.link || announcement?.url,
                            detail_url: announcement?.detailUrl,
                            error_type: 'waitError',
                            error_message: waitError.message
                        }).catch(logErr => { });

                        console.log('자동 리다이렉트 없음. 수동 폼 제출 시도...');

                        // 페이지에 있는 폼을 찾아서 제출
                        const formSubmitted = await this.page.evaluate(() => {
                            // 페이지의 모든 폼 확인
                            const forms = document.querySelectorAll('form');
                            console.log(`페이지에서 발견된 폼 수: ${forms.length}`);

                            for (let form of forms) {
                                console.log(`폼 액션: ${form.action}, 메소드: ${form.method}`);

                                if (form.action.includes('OfrAction.do')) {
                                    // 페이지 번호 설정
                                    const pageInput = form.querySelector('input[name="pageIndex"]');
                                    if (pageInput) {
                                        pageInput.value = '1';
                                    }

                                    form.submit();
                                    return true;
                                }
                            }

                            // 폼이 없는 경우 JavaScript 함수 실행 시도
                            if (typeof search === 'function') {
                                search();
                                return true;
                            }

                            return false;
                        });

                        if (formSubmitted) {
                            console.log('폼 제출 또는 검색 함수 실행 완료');
                            await this.page.waitForTimeout(5000);
                        } else {
                            console.log('폼 제출 실패. 서블릿 URL로 직접 접근 시도...');

                            // 서블릿 URL로 직접 접근 (폴백)
                            const servletUrl = `${this.baseUrl}/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do?` +
                                `jndinm=OfrNotAncmtEJB&context=NTIS&method=selectListOfrNotAncmt&` +
                                `methodnm=selectListOfrNotAncmtHomepage&homepage_pbs_yn=Y&subCheck=Y&` +
                                `ofr_pageSize=10&not_ancmt_se_code=01,02,03,04,05,06&title=%EA%B3%A0%EC%8B%9C%EA%B3%B5%EA%B3%A0&` +
                                `initValue=Y&countYn=Y&list_gubun=A&Key=B_Subject&pageIndex=${pageNum}`;

                            console.log('서블릿 URL로 이동:', servletUrl);

                            try {
                                await this.page.goto(servletUrl, {
                                    waitUntil: 'domcontentloaded',
                                    timeout: 30000
                                });
                                await this.page.waitForTimeout(3000);
                                console.log('서블릿 URL 접근 성공');
                            } catch (servletError) {
                                // 실패 공고 DB 기록
                                await FailureLogger.logFailedAnnouncement({
                                    site_code: this.siteCode,
                                    title: announcement?.title || 'Unknown',
                                    url: announcement?.link || announcement?.url,
                                    detail_url: announcement?.detailUrl,
                                    error_type: 'servletError',
                                    error_message: servletError.message
                                }).catch(logErr => { });

                                console.log('서블릿 URL 접근도 실패:', servletError.message);
                                return [];
                            }
                        }
                    } // catch 블록 닫기
                } // else 블록 닫기 (리다이렉트 대기 부분)
                //} // else 블록 닫기 (태안군 특별 처리)

                console.log(`최종 URL: ${this.page.url()}`);

                // 특정 페이지로 이동 (1페이지가 아닌 경우)
                if (pageNum > 1) {
                    console.log(`${pageNum} 페이지로 이동 중...`);

                    try {
                        // 수원시의 경우 직접 페이지 링크 클릭 시도
                        if (this.region === '수원시') {
                            console.log('수원시 특별 페이지 이동 처리');
                            const clicked = await this.page.evaluate((targetPage) => {
                                // 페이지 번호 링크 직접 찾기
                                const pageLinks = document.querySelectorAll('a');
                                for (const link of pageLinks) {
                                    const linkText = link.textContent.trim();
                                    if (linkText === targetPage.toString()) {
                                        console.log(`페이지 ${targetPage} 링크 클릭`);
                                        link.click();
                                        return true;
                                    }
                                }
                                // linkPage 함수로 시도
                                if (typeof window.linkPage === 'function') {
                                    console.log(`linkPage(${targetPage}) 호출`);
                                    window.linkPage(targetPage);
                                    return true;
                                }
                                return false;
                            }, pageNum);

                            if (clicked) {
                                console.log('수원시 페이지 이동 성공');
                                await this.page.waitForTimeout(5000);
                            } else {
                                console.log('수원시 페이지 이동 실패');
                                return [];
                            }
                        } else {
                            // 페이징 처리: pageIndex 설정 후 goPage/search 함수 호출
                            const pageNavigated = await this.page.evaluate((targetPage) => {
                                try {
                                    // 폼 찾기
                                    let targetForm = null;
                                    const forms = document.querySelectorAll('form');

                                    for (let form of forms) {
                                        if (form.name === 'form1' || form.name === 'form' || form.action.includes('OfrAction.do')) {
                                            targetForm = form;
                                            break;
                                        }
                                    }

                                    if (!targetForm && forms.length > 0) {
                                        targetForm = forms[0];
                                    }

                                    if (!targetForm) {
                                        console.log('페이징용 폼을 찾을 수 없음');
                                        return false;
                                    }

                                    // pageIndex 설정
                                    const pageIndexField = targetForm.querySelector('input[name="pageIndex"]');
                                    if (pageIndexField) {
                                        pageIndexField.value = targetPage.toString();
                                        console.log(`pageIndex를 ${targetPage}로 설정`);
                                    } else {
                                        console.log('pageIndex 필드를 찾을 수 없음');
                                        return false;
                                    }

                                    // goPage 함수가 있으면 사용, 없으면 search 함수 사용
                                    if (typeof window.goPage === 'function') {
                                        console.log('goPage 함수 실행');
                                        // 수원시의 경우 goPage()만 호출 (인자 없이)
                                        const regionElement = document.querySelector('meta[property="og:site_name"]');
                                        const isSuwon = regionElement && regionElement.content && regionElement.content.includes('수원');

                                        if (isSuwon) {
                                            console.log('수원시 특별 처리: goPage() 호출');
                                            window.goPage();
                                        } else {
                                            window.goPage(targetPage);
                                        }
                                        return true;
                                    } else if (typeof window.search === 'function') {
                                        console.log('search 함수 실행');
                                        window.search();
                                        return true;
                                    } else if (typeof window.linkPage === 'function') {
                                        console.log('linkPage 함수 실행');
                                        window.linkPage(targetPage);
                                        return true;
                                    } else {
                                        console.log('페이징 함수를 찾을 수 없음. 직접 폼 제출');

                                        // 폼 설정
                                        targetForm.target = '_self';
                                        targetForm.action = '/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do';

                                        const methodField = targetForm.querySelector('input[name="method"]');
                                        const methodNmField = targetForm.querySelector('input[name="methodnm"]');

                                        if (methodField) methodField.value = 'selectListOfrNotAncmt';
                                        if (methodNmField) methodNmField.value = 'selectListOfrNotAncmtHomepage';

                                        targetForm.submit();
                                        return true;
                                    }
                                } catch (error) {
                                    console.log('페이징 처리 오류:', error.message);
                                    return false;
                                }
                            }, pageNum);

                            if (pageNavigated) {
                                console.log(`페이지 ${pageNum} 이동 요청 완료`);

                                // 네비게이션 대기 (페이지 전환을 기다림)
                                try {
                                    await Promise.race([
                                        this.page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 10000 }),
                                        this.page.waitForTimeout(10000)
                                    ]);
                                } catch (navError) {
                                    // 실패 공고 DB 기록
                                    await FailureLogger.logFailedAnnouncement({
                                        site_code: this.siteCode,
                                        title: announcement?.title || 'Unknown',
                                        url: announcement?.link || announcement?.url,
                                        detail_url: announcement?.detailUrl,
                                        error_type: 'navError',
                                        error_message: navError.message
                                    }).catch(logErr => { });

                                    console.log('네비게이션 대기 중 오류 (정상일 수 있음):', navError.message);
                                }

                                // 추가 로딩 대기
                                await this.page.waitForTimeout(3000);

                                // 페이지 번호 확인
                                let currentPageNum = 1;
                                try {
                                    currentPageNum = await this.page.evaluate(() => {
                                        const pageIndexInput = document.querySelector('input[name="pageIndex"]');
                                        if (pageIndexInput) {
                                            return parseInt(pageIndexInput.value) || 1;
                                        }
                                        // 현재 페이지 번호를 표시하는 다른 요소 확인
                                        const activePageElement = document.querySelector('.active, .on, .current, strong');
                                        if (activePageElement && !isNaN(parseInt(activePageElement.textContent))) {
                                            return parseInt(activePageElement.textContent) || 1;
                                        }
                                        return 1;
                                    });
                                } catch (evalError) {
                                    // 실패 공고 DB 기록
                                    await FailureLogger.logFailedAnnouncement({
                                        site_code: this.siteCode,
                                        title: announcement?.title || 'Unknown',
                                        url: announcement?.link || announcement?.url,
                                        detail_url: announcement?.detailUrl,
                                        error_type: 'evalError',
                                        error_message: evalError.message
                                    }).catch(logErr => { });

                                    console.log('페이지 번호 확인 중 오류:', evalError.message);
                                }

                                console.log(`현재 페이지 번호 확인: ${currentPageNum}`);
                                if (currentPageNum !== pageNum) {
                                    console.log(`페이지 이동 실패: 요청 페이지 ${pageNum}, 현재 페이지 ${currentPageNum}`);
                                    // 페이지 번호 직접 클릭 시도
                                    try {
                                        const clicked = await this.page.evaluate((targetPage) => {
                                            // 페이지 번호 링크 찾기
                                            const pageLinks = document.querySelectorAll('a');
                                            for (const link of pageLinks) {
                                                if (link.textContent.trim() === targetPage.toString() ||
                                                    link.onclick && link.onclick.toString().includes(`linkPage(${targetPage})`)) {
                                                    link.click();
                                                    return true;
                                                }
                                            }
                                            return false;
                                        }, pageNum);

                                        if (clicked) {
                                            console.log('페이지 번호 직접 클릭 완료');
                                            await this.page.waitForTimeout(5000);
                                        }
                                    } catch (clickError) {
                                        // 실패 공고 DB 기록
                                        await FailureLogger.logFailedAnnouncement({
                                            site_code: this.siteCode,
                                            title: announcement?.title || 'Unknown',
                                            url: announcement?.link || announcement?.url,
                                            detail_url: announcement?.detailUrl,
                                            error_type: 'clickError',
                                            error_message: clickError.message
                                        }).catch(logErr => { });

                                        console.log('페이지 번호 클릭 실패:', clickError.message);
                                    }
                                }
                            } else {
                                console.log('페이지 이동 실패');
                                return [];
                            }
                        } // 수원시 특별 처리 else 블록 닫기
                    } catch (error) {
                        // 실패 공고 DB 기록
                        await FailureLogger.logFailedAnnouncement({
                            site_code: this.siteCode,
                            title: announcement?.title || 'Unknown',
                            url: announcement?.link || announcement?.url,
                            detail_url: announcement?.detailUrl,
                            error_type: 'error',
                            error_message: error.message
                        }).catch(logErr => { });

                        console.log('페이지 이동 실패:', error.message);
                        return [];
                    }
                }

                // 페이지가 완전히 로드될 때까지 대기
                try {
                    console.log("페이지가 완전히 로드될 때까지 대기")

                    await this.page.waitForSelector('table', { timeout: 15000 });
                } catch (error) {
                    // 실패 공고 DB 기록
                    await FailureLogger.logFailedAnnouncement({
                        site_code: this.siteCode,
                        title: announcement?.title || 'Unknown',
                        url: announcement?.link || announcement?.url,
                        detail_url: announcement?.detailUrl,
                        error_type: 'error',
                        error_message: error.message
                    }).catch(logErr => { });

                    console.log('테이블 로딩 대기 실패. 페이지 내용 확인...');

                    const pageContent = await this.page.content();
                    if (pageContent.includes('전체게시물') || pageContent.includes('공고')) {
                        console.log('페이지에 공고 관련 내용이 있지만 테이블이 다른 구조일 수 있음');
                    } else {
                        console.log('페이지에 공고 내용이 없음');
                        return [];
                    }
                }

                console.log('!!!테이블 로딩 !!! 페이지 내용 확인...');

                // 페이지 정보 먼저 Node.js에서 직접 확인
                const pageInfo = await this.page.evaluate(() => {
                    return {
                        url: window.location.href,
                        bodyHtml: document.body.innerHTML.substring(0, 1000),
                        tableCount: document.querySelectorAll('table').length,
                        trCount: document.querySelectorAll('tr').length,
                        elementCounts: {
                            'table': document.querySelectorAll('table').length,
                            '.board-list': document.querySelectorAll('.board-list').length,
                            '.list-table': document.querySelectorAll('.list-table').length,
                            '.bbsList': document.querySelectorAll('.bbsList').length,
                            'tbody': document.querySelectorAll('tbody').length,
                            'tr': document.querySelectorAll('tr').length,
                            '.row': document.querySelectorAll('.row').length,
                            '.list-item': document.querySelectorAll('.list-item').length
                        }
                    };
                });

                console.log(`=== ${this.region} 페이지 구조 분석 ===`);
                console.log(`📍 현재 페이지 URL: ${pageInfo.url}`);
                console.log(`📋 총 테이블 수: ${pageInfo.tableCount}`);
                console.log(`📋 총 행 수: ${pageInfo.trCount}`);

                // console.log('🔍 가능한 리스트 요소들:');
                // Object.entries(pageInfo.elementCounts).forEach(([selector, count]) => {
                //     console.log(`   ${selector}: ${count}개 요소`);
                // });

                if (pageInfo.tableCount === 0 && pageInfo.trCount === 0) {
                    console.log('📄 페이지 body 내용 (처음 1000자):');
                    console.log(pageInfo.bodyHtml);
                } else {
                    // 테이블이 있는 경우 각 테이블의 구조 상세 분석
                    const tableDetails = await this.page.evaluate(() => {
                        const tables = document.querySelectorAll('table');
                        const details = [];

                        tables.forEach((table, index) => {
                            const rows = table.querySelectorAll('tr');
                            const tableInfo = {
                                index: index,
                                rowCount: rows.length,
                                className: table.className || '(no class)',
                                id: table.id || '(no id)',
                                rows: []
                            };

                            rows.forEach((row, rowIndex) => {
                                const cells = row.querySelectorAll('td, th');
                                const rowInfo = {
                                    rowIndex: rowIndex,
                                    cellCount: cells.length,
                                    cells: Array.from(cells).map(cell => ({
                                        text: cell.textContent.trim().substring(0, 50),
                                        tagName: cell.tagName,
                                        className: cell.className || '(no class)'
                                    }))
                                };
                                tableInfo.rows.push(rowInfo);
                            });

                            details.push(tableInfo);
                        });

                        return details;
                    });

                    // console.log('\n🔍 테이블 상세 분석:');
                    // tableDetails.forEach(table => {
                    //     console.log(`\n테이블 ${table.index} (ID: ${table.id}, Class: ${table.className}):`);
                    //     console.log(`  - 총 ${table.rowCount}개 행`);

                    //     table.rows.forEach(row => {
                    //         if (row.cellCount > 0) {
                    //             const cellTexts = row.cells.map(cell => `${cell.text}(${cell.tagName})`).join(' | ');
                    //             console.log(`  행${row.rowIndex}: [${row.cellCount}셀] ${cellTexts}`);
                    //         }
                    //     });
                    // });
                }

                // 리스트 테이블에서 공고 추출
                const announcements = await this.page.evaluate((region) => {
                    const results = [];
                    // .cont_table 셀렉터로 테이블 찾기

                    const regionName = region.region
                    let selectorInfo = {
                        "울산북구": {
                            "table": ".cont_table",
                            "titleIndex": 2, "dateIndex": 4
                        },
                        "부산중구": {
                            "table": ".bbs_ltype",
                            "titleIndex": 2, "dateIndex": 4
                        },
                        "부산강서구": {
                            "table": ".tb_board",
                            "titleIndex": 2, "dateIndex": 4
                        },
                        "평창군": {
                            "table": ".tb_board",
                            "titleIndex": 3, "dateIndex": 7
                        },

                        "해운대구": {
                            "table": ".tstyle_list",
                            "titleIndex": 2, "dateIndex": 4
                        },
                        "수영구": {
                            "table": ".list01",
                            "titleIndex": 2, "dateIndex": 4
                        },
                        "부산진구": {
                            "table": ".board-list-wrap table",
                            "titleIndex": 2, "dateIndex": 4
                        },
                        "부산서구": {
                            "table": ".board-list-wrap table",
                            "titleIndex": 2, "dateIndex": 4
                        },
                        "광주동구": {
                            "table": ".dbody",
                            "rowSelector": "ul",
                            "cellSelector": "li",
                            "titleIndex": 2, "dateIndex": 4
                        },

                        "울산남구": {
                            "table": ".basic_table",
                            "titleIndex": 2, "dateIndex": 4
                        },
                        "울산동구": {
                            "table": ".bbs_list",
                            "titleIndex": 2, "dateIndex": 4
                        },
                        "연수구": {
                            "table": ".general_board",
                            "titleIndex": 2, "dateIndex": 4
                        }

                    }
                    let targetTableClass = ".target"
                    let titleIndex = 2;
                    let dateIndex = 4;

                    if (selectorInfo[regionName]) {
                        targetTableClass = selectorInfo[regionName].table
                        titleIndex = selectorInfo[regionName].titleIndex
                        dateIndex = selectorInfo[regionName].dateIndex
                    }

                    console.log("INDEX", titleIndex, dateIndex)

                    let targetTable = document.querySelector(targetTableClass);
                    if (!targetTable) {
                        // 폴백: 모든 테이블을 확인
                        const tables = document.querySelectorAll('table');
                        console.log(`페이지에서 찾은 테이블 수: ${tables.length}`);

                        // 가장 큰 테이블에서 데이터 추출
                        let maxRows = 0;

                        tables.forEach((table, index) => {
                            const rows = table.querySelectorAll('tr');
                            console.log(`테이블 ${index}: ${rows.length}개 행`);
                            if (rows.length > maxRows) {
                                maxRows = rows.length;
                                targetTable = table;
                            }
                        });

                        if (!targetTable) {
                            console.log('테이블을 찾을 수 없음');
                            return [];
                        }
                    }

                    // 선택된 테이블에서 모든 행 검사
                    let rowSelector = "tr";

                    if (selectorInfo[regionName] && selectorInfo[regionName].rowSelector) {
                        rowSelector = selectorInfo[regionName].rowSelector
                    }

                    const allRows = targetTable.querySelectorAll(rowSelector);
                    console.log(`선택된 테이블의 행 수: ${allRows.length}`);

                    allRows.forEach((row, index) => {
                        let cellSelector = 'td, th'
                        if (selectorInfo[regionName] && selectorInfo[regionName].cellSelector) {
                            cellSelector = selectorInfo[regionName].cellSelector
                        }
                        const cells = row.querySelectorAll(cellSelector);


                        console.log("cells", cells)
                        if (cells.length >= 5) {
                            // 각 셀의 텍스트 내용 확인
                            const cellTexts = Array.from(cells).map(cell => cell.textContent.trim());

                            console.log("cellTexts", cellTexts)
                            // 디버깅: 첫 몇 개 행의 내용 출력
                            // if (index < 3) {
                            //     console.log(`행 ${index}: ${cellTexts.join(' | ')}`);
                            // }

                            // 공고를 찾기 위한 조건:
                            // 제목 찾기 - 3번째 td (인덱스 2)로 고정
                            let title = '';
                            if (cellTexts.length > 2) {
                                title = cellTexts[titleIndex];
                            }

                            // 날짜 찾기 - 5번째 td (인덱스 4)로 고정
                            let dateText = '';


                            dateText = cellTexts[dateIndex];

                            // 첫 번째 셀이 숫자인지 확인
                            const hasNumber = /^\d{1,}$/.test(cellTexts[0]);

                            console.log("TITLE", title, dateText, hasNumber, cells.length)
                            // 공고로 인식할 조건
                            if (dateText && title && (hasNumber || cells.length >= 5)) {
                                const number = cellTexts[0];
                                const code = cellTexts[1];
                                // title은 인덱스 2, dateText는 인덱스 4에서 이미 추출
                                const department = cellTexts[3] || '';

                                // onclick 속성에서 관리번호 추출 - 다양한 패턴 지원
                                const titleCell = cells[titleIndex] || cells[2];
                                let detailMgtNo = '';

                                // 1순위: 셀 내부 링크의 onclick 속성 확인
                                const titleLink = titleCell.querySelector('a');
                                let onclickAttr = '';
                                let hrefAttr = '';

                                if (titleLink) {
                                    onclickAttr = titleLink.getAttribute('onclick') || '';
                                    hrefAttr = titleLink.href
                                }

                                // 2순위: 셀 자체의 onclick 속성 확인  
                                if (!onclickAttr) {
                                    onclickAttr = titleCell.getAttribute('onclick') || '';
                                }

                                // 다양한 onclick 패턴들을 시도
                                const patterns = [
                                    /searchDetail\('(\d+)'\)/,           // searchDetail('12345')
                                    /searchDetail\((\d+)\)/,             // searchDetail(12345)
                                    /searchDetail\('([^']+)'\)/,         // searchDetail('abc123')
                                    /searchDetail\(\"(\d+)\"\)/,         // searchDetail("12345")
                                    /viewDetail\('(\d+)'\)/,             // viewDetail('12345')
                                    /viewDetail\((\d+)\)/,               // viewDetail(12345)
                                    /goDetail\('(\d+)'\)/,               // goDetail('12345')
                                    /goDetail\((\d+)\)/,                 // goDetail(12345)
                                    /\('(\d+)'\)/,                       // 단순한 함수('12345') 패턴
                                    /\((\d+)\)/                          // 단순한 함수(12345) 패턴
                                ];

                                for (const pattern of patterns) {
                                    const match = onclickAttr.match(pattern);
                                    if (match) {
                                        detailMgtNo = match[1];
                                        console.log(`공고 발견 - ${number}: ${title} | 상세번호: ${detailMgtNo} | 패턴: ${pattern} | ${department} | ${dateText}`);
                                        break;
                                    }
                                }

                                if (!detailMgtNo) {
                                    for (const pattern of patterns) {
                                        const match = hrefAttr.match(pattern);
                                        if (match) {
                                            detailMgtNo = match[1];
                                            console.log(`HREF 공고 발견 - ${number}: ${title} | 상세번호: ${detailMgtNo} | 패턴: ${pattern} | ${department} | ${dateText}`);
                                            break;
                                        }
                                    }
                                }


                                if (!detailMgtNo) {
                                    // onclick이 없는 경우 다른 속성들에서 관리번호 찾기

                                    // href 속성도 확인 (titleLink는 이미 위에서 정의됨)
                                    if (titleLink) {
                                        const hrefAttr = titleLink.getAttribute('href') || '';
                                        const hrefMatch = hrefAttr.match(/[?&]not_ancmt_mgt_no=([^&]*)/);
                                        if (hrefMatch) {
                                            detailMgtNo = hrefMatch[1];
                                            console.log(`href에서 관리번호 발견: ${detailMgtNo}`);
                                        }
                                    }

                                    // data 속성들도 확인
                                    if (!detailMgtNo && titleCell) {
                                        const dataAttrs = ['data-mgt-no', 'data-detail-no', 'data-id', 'data-no'];
                                        for (const attr of dataAttrs) {
                                            const value = titleCell.getAttribute(attr);
                                            if (value) {
                                                detailMgtNo = value;
                                                console.log(`${attr}에서 관리번호 발견: ${detailMgtNo}`);
                                                break;
                                            }
                                        }
                                    }

                                    // 링크의 data 속성들도 확인
                                    if (!detailMgtNo && titleLink) {
                                        const linkDataAttrs = ['data-mgt-no', 'data-detail-no', 'data-id', 'data-no'];
                                        for (const attr of linkDataAttrs) {
                                            const value = titleLink.getAttribute(attr);
                                            if (value) {
                                                detailMgtNo = value;
                                                console.log(`링크 ${attr}에서 관리번호 발견: ${detailMgtNo}`);
                                                break;
                                            }
                                        }
                                    }

                                    if (!detailMgtNo) {
                                        console.log(`공고 발견 - ${number}: ${title} | 관리번호 없음 (onclick: "${onclickAttr}") | ${department} | ${dateText}`);
                                        return; // 관리번호가 없으면 스킵 (forEach에서는 return 사용)
                                    }
                                }


                                results.push({
                                    title: title,
                                    dateText: dateText,
                                    onclick: onclickAttr,
                                    managementNo: number,
                                    detailMgtNo: detailMgtNo, // 상세 페이지용 관리번호 추가
                                    department: department,
                                    announcementCode: code,
                                    rowIndex: index,
                                    tableIndex: 0  // targetTable is either .cont_table or the largest table
                                });
                            }
                        }
                    });

                    console.log(`최종 추출된 공고 수: ${results.length}`);
                    if (results.length > 0) {
                        console.log(`첫 번째 공고: ${results[0].title}`);
                        console.log(`첫 번째 날짜: ${results[0].dateText}`);
                    }

                    return results;
                }, { region: this.region });

                // 디버깅용 스크린샷 저장 (리스트가 0개인 경우)
                if (announcements.length === 0) {
                    try {
                        const screenshotPath = `debug_screenshot_${this.siteCode}_page${pageNum}_${Date.now()}.png`;
                        await this.page.screenshot({ path: screenshotPath, fullPage: true });
                        console.log(`🖼️ 디버깅용 스크린샷 저장: ${screenshotPath}`);
                    } catch (screenshotError) {
                        // 실패 공고 DB 기록
                        await FailureLogger.logFailedAnnouncement({
                            site_code: this.siteCode,
                            title: announcement?.title || 'Unknown',
                            url: announcement?.link || announcement?.url,
                            detail_url: announcement?.detailUrl,
                            error_type: 'screenshotError',
                            error_message: screenshotError.message
                        }).catch(logErr => { });

                        console.log('스크린샷 저장 실패:', screenshotError.message);
                    }
                }

                console.log(announcements)
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
                }).catch(logErr => { });

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

    /**
     * 개별 공고 처리
     */
    async processAnnouncement(announcement) {
        try {
            console.log(`\n처리 중: ${announcement.title}`);

            // 1. 리스트에서 날짜 확인
            const listDate = this.extractDate(announcement.dateText);
            console.log(`대상 날짜 설정: ${this.targetDate}`);
            console.log(`리스트 원본 날짜 텍스트: "${announcement.dateText}"`);
            console.log(`리스트 파싱된 날짜: ${listDate ? listDate.format('YYYY-MM-DD') : 'null'}`);

            if (this.targetDate && listDate) {
                const listDateStr = listDate.format('YYYYMMDD');
                console.log(`날짜 비교: 리스트 날짜 ${listDateStr} vs 대상 날짜 ${this.targetDate}`);
                if (listDateStr < this.targetDate) {
                    console.log(`리스트 날짜 ${listDate.format('YYYY-MM-DD')}가 대상 날짜(${this.targetDate}) 미만입니다. (대상 날짜 포함하여 이후 수집)`);
                    console.log(`스크래핑 중단 신호를 보냅니다.`);
                    return true; // 스크래핑 중단
                }
            } else if (this.targetDate && !listDate) {
                console.log(`⚠️  리스트에서 날짜를 파싱할 수 없어 상세 페이지에서 확인합니다.`);
            } else if (!this.targetDate) {
                console.log(`대상 날짜가 설정되지 않아 날짜 필터링을 하지 않습니다.`);
            }

            // 2. 중복 게시물 체크 (메모리 기반 - 현재 세션)
            const sanitizedTitle = sanitize(announcement.title).substring(0, 100);

            if (this.processedTitles.has(announcement.title) || this.processedTitles.has(sanitizedTitle)) {
                console.log(`🔄 메모리 기반 중복 감지: ${announcement.title}`);
                // 중복 게시물이어도 날짜 체크는 수행 (targetDate 이전인지 확인)
                // 많은 중복이 연속으로 나타날 경우 종료 조건 판단을 위함
                if (this.targetDate && listDate) {
                    const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                    if (listDate.isBefore(targetMoment)) {
                        console.log(`중복 게시물이지만 날짜가 ${listDate.format('YYYY-MM-DD')}로 대상 날짜 미만입니다. (대상 날짜 포함하여 이후 수집) 종료 신호.`);
                        return true; // 스크래핑 중단
                    }
                }
                return false;
            }

            // 3. 상세 페이지 내용 가져오기
            const detailContent = await this.getDetailContent(announcement);
            if (!detailContent) {
                console.log('상세 페이지 접근 실패');
                return false;
            }

            // 4. 상세 페이지에서 날짜 재확인
            if (this.targetDate && detailContent.date) {
                const detailDateStr = detailContent.date.format('YYYYMMDD');
                console.log(`날짜 비교: 상세 페이지 날짜 ${detailDateStr} vs 대상 날짜 ${this.targetDate}`);
                if (detailDateStr < this.targetDate) {
                    console.log(`상세 페이지 날짜 ${detailContent.date.format('YYYY-MM-DD')}가 대상 날짜(${this.targetDate}) 미만입니다. (대상 날짜 포함하여 이후 수집)`);
                    console.log(`스크래핑 중단 신호를 보냅니다.`);
                    return true; // 스크래핑 중단
                }
            } else if (this.targetDate && !detailContent.date) {
                console.log(`⚠️  상세 페이지에서 날짜를 파싱할 수 없습니다.`);
            }

            // 5. 폴더 생성 및 파일 저장
            await this.saveAnnouncement(announcement, detailContent);

            // 원본 제목과 sanitize된 제목 모두 추가
            // sanitize된 제목을 저장하여 정확한 중복 체크
            const sanitizedTitleForCheck = sanitize(announcement.title).substring(0, 100);
            this.processedTitles.add(sanitizedTitleForCheck);
            this.processedTitles.add(sanitize(announcement.title).substring(0, 100));
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
            }).catch(logErr => { });

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
                if (!announcement.detailMgtNo) {
                    console.log('상세 관리번호가 없어 상세 페이지 접근 불가');
                    return null;
                }

                // 매번 새로운 세션으로 상세 페이지 접근
                if (retries > 0) {
                    console.log(`재시도 ${retries}: 리스트 페이지 재로드로 세션 초기화`);
                    await this.page.goto(this.listUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
                    await this.page.waitForTimeout(4000);

                    // 자동 리다이렉트 대기
                    try {
                        await this.page.waitForFunction(
                            () => window.location.href.includes('OfrAction.do'),
                            { timeout: 10000 }
                        );
                    } catch { }
                    await this.page.waitForTimeout(2000);
                }

                // 직접 URL로 상세 페이지 이동 (더 안정적)
                console.log(`상세 페이지 직접 이동: detailMgtNo=${announcement.detailMgtNo}`);

                const detailUrl = `${this.actionUrl}?` + new URLSearchParams({
                    jndinm: 'OfrNotAncmtEJB',
                    context: 'NTIS',
                    method: 'selectOfrNotAncmt',
                    methodnm: 'selectOfrNotAncmtRegst',
                    not_ancmt_mgt_no: announcement.detailMgtNo,
                    homepage_pbs_yn: 'Y',
                    subCheck: 'Y',
                    ofr_pageSize: '10',
                    not_ancmt_se_code: '01,02,03,04,05',
                    title: '고시공고',
                    cha_dep_code_nm: '',
                    initValue: 'Y',
                    countYn: 'Y',
                    list_gubun: 'A',
                    not_ancmt_sj: '',
                    not_ancmt_cn: '',
                    dept_nm: '',
                    cgg_code: '',
                    not_ancmt_reg_no: '',
                    epcCheck: 'Y',
                    yyyy: '',
                    Key: 'B_Subject',
                    temp: ''
                }).toString();

                console.log(`상세 URL: ${detailUrl}`);

                // 상세 페이지로 이동 (재시도 로직 포함)
                let navigationSuccess = false;
                let navigationAttempt = 0;
                const maxNavigationAttempts = 3;

                while (!navigationSuccess && navigationAttempt < maxNavigationAttempts) {
                    navigationAttempt++;
                    try {
                        console.log(`상세 페이지 이동 시도 ${navigationAttempt}/${maxNavigationAttempts}`);

                        await this.page.goto(detailUrl, {
                            waitUntil: 'networkidle',
                            timeout: 45000
                        });

                        // 페이지가 제대로 로드되었는지 확인
                        await this.page.waitForSelector('body', { timeout: 10000 });
                        navigationSuccess = true;

                    } catch (error) {
                        // 실패 공고 DB 기록
                        await FailureLogger.logFailedAnnouncement({
                            site_code: this.siteCode,
                            title: announcement?.title || 'Unknown',
                            url: announcement?.link || announcement?.url,
                            detail_url: announcement?.detailUrl,
                            error_type: 'error',
                            error_message: error.message
                        }).catch(logErr => { });

                        console.log(`상세 페이지 이동 시도 ${navigationAttempt} 실패: ${error.message}`);

                        if (navigationAttempt < maxNavigationAttempts) {
                            console.log('잠시 대기 후 재시도...');
                            await this.delay(3000 + (navigationAttempt * 2000)); // 점진적으로 대기 시간 증가
                        }
                    }
                }

                if (!navigationSuccess) {
                    console.log('모든 상세 페이지 이동 시도 실패');
                    return null;
                }

                // 상세 페이지 로딩 대기
                console.log('상세 페이지 로딩 대기 중...');
                await this.page.waitForTimeout(3000);

                // 페이지 상태 확인
                const currentUrl = this.page.url();
                console.log(`상세 페이지 로딩 후 URL: ${currentUrl}`);

                // 페이지에 오류나 리다이렉트가 있는지 확인
                const pageStatus = await this.page.evaluate(() => {
                    const bodyText = document.body.textContent || '';
                    return {
                        hasError: bodyText.includes('오류') || bodyText.includes('에러') || bodyText.includes('Error'),
                        hasRedirect: bodyText.includes('뒤로가기') && bodyText.includes('홈으로'),
                        isEmpty: bodyText.trim().length < 100,
                        url: window.location.href
                    };
                });

                console.log('페이지 상태:', pageStatus);

                // 오류 페이지인 경우 리스트로 돌아가기
                if (pageStatus.hasError || pageStatus.hasRedirect) {
                    console.log('오류 페이지 감지. 리스트 페이지로 돌아가는 중...');
                    await this.page.goBack();
                    await this.page.waitForTimeout(2000);

                    // 재시도 횟수 증가
                    retries++;
                    console.log(`재시도 ${retries}/${maxRetries}`);
                    continue;
                }

                // 페이지 내용 추출
                const content = await this.page.evaluate(() => {
                    // 본문 내용 추출
                    let mainContent = '';
                    const contentSelectors = [
                        '.view-content',
                        '.board-view tbody',
                        '#content',
                        '.content',
                        '.detail-content',
                        '.view-area'
                    ];

                    for (const selector of contentSelectors) {
                        const element = document.querySelector(selector);
                        if (element) {
                            mainContent = element.innerText || element.textContent || '';
                            if (mainContent.trim()) break;
                        }
                    }

                    // 전체 body에서 추출 (최후의 수단)
                    if (!mainContent.trim()) {
                        // 헤더, 네비게이션, 푸터 제거 후 본문 추출
                        const excludeSelectors = [
                            'header', 'nav', 'aside', 'footer',
                            '.header', '.nav', '.sidebar', '.footer',
                            '.menu', '.navigation', '.breadcrumb', '.quick-menu'
                        ];

                        const bodyClone = document.body.cloneNode(true);
                        excludeSelectors.forEach(selector => {
                            const elements = bodyClone.querySelectorAll(selector);
                            elements.forEach(el => el.remove());
                        });

                        mainContent = bodyClone.innerText || bodyClone.textContent || '';
                    }

                    // 날짜는 리스트에서 가져온 값을 사용하므로 추출 불필요
                    let dateText = '';

                    // 첨부파일 추출 - 다양한 패턴 지원
                    const attachments = [];

                    // 1. fnFileDown 패턴 (기본)
                    const fnFileDownLinks = document.querySelectorAll('a[onclick*="fnFileDown"]');
                    fnFileDownLinks.forEach(link => {
                        const onclick = link.getAttribute('onclick');
                        const fileName = link.textContent.trim();

                        const fileMatch = onclick.match(/fnFileDown\('([^']*)',\s*'([^']*)',\s*'([^']*)'/);
                        if (fileMatch) {
                            const [, fileSeq, orgFileName, saveFileName] = fileMatch;
                            attachments.push({
                                name: orgFileName || fileName,
                                onclick: onclick,
                                fileSeq: fileSeq,
                                orgFileName: orgFileName,
                                saveFileName: saveFileName,
                                type: 'fnFileDown'
                            });
                        }
                    });

                    // 2. goDownLoad 패턴 (이민원 사이트 실제 사용 함수)
                    const goDownLoadLinks = document.querySelectorAll('a[onclick*="goDownLoad"]');
                    goDownLoadLinks.forEach(link => {
                        const onclick = link.getAttribute('onclick');
                        const fileName = link.textContent.trim();

                        // goDownLoad('user_file', 'sys_file', 'file_path') 매개변수 추출
                        const goDownLoadMatch = onclick.match(/goDownLoad\('([^']*)',\s*'([^']*)',\s*'([^']*)'/);
                        if (goDownLoadMatch) {
                            const [, userFileName, sysFileName, filePath] = goDownLoadMatch;
                            attachments.push({
                                name: userFileName || fileName,
                                onclick: onclick,
                                userFileName: userFileName,
                                sysFileName: sysFileName,
                                filePath: filePath,
                                type: 'goDownLoad'
                            });
                        }
                    });

                    // 3. fileDown 패턴 (일반적인 패턴)
                    const fileDownLinks = document.querySelectorAll('a[onclick*="fileDown"]:not([onclick*="goDownLoad"])');
                    fileDownLinks.forEach(link => {
                        const onclick = link.getAttribute('onclick');
                        const fileName = link.textContent.trim();

                        // 이미 추가된 파일은 제외
                        const alreadyAdded = attachments.some(att => att.onclick === onclick);
                        if (!alreadyAdded && fileName) {
                            attachments.push({
                                name: fileName,
                                onclick: onclick,
                                type: 'fileDown'
                            });
                        }
                    });

                    // 3. 다운로드 링크 패턴 (일반적인 href 링크)
                    const downloadLinks = document.querySelectorAll('a[href*="download"], a[href*="file"], a[href*="attach"]');
                    downloadLinks.forEach(link => {
                        const href = link.href;
                        const fileName = link.textContent.trim();

                        if (href && fileName && !attachments.some(att => att.name === fileName)) {
                            attachments.push({
                                name: fileName,
                                href: href,
                                type: 'direct'
                            });
                        }
                    });

                    // 4. 파일 확장자가 있는 모든 링크
                    const fileExtensionPattern = /\.(pdf|docx?|xlsx?|pptx?|hwp|txt|zip|rar|7z|jpg|jpeg|png|gif)$/i;
                    const allLinks = document.querySelectorAll('a');
                    allLinks.forEach(link => {
                        const href = link.href || '';
                        const text = link.textContent.trim();

                        if ((fileExtensionPattern.test(href) || fileExtensionPattern.test(text)) &&
                            !attachments.some(att => att.name === text || att.href === href)) {
                            attachments.push({
                                name: text || href.split('/').pop(),
                                href: href,
                                onclick: link.getAttribute('onclick'),
                                type: 'extension'
                            });
                        }
                    });

                    console.log(`추출된 첨부파일 수: ${attachments.length}`);
                    // if (attachments.length > 0) {
                    //     console.log('첨부파일 목록:');
                    //     attachments.forEach((att, i) => {
                    //         console.log(`  ${i + 1}. ${att.name} (${att.type})`);
                    //     });
                    // }

                    return {
                        content: mainContent.trim(),
                        attachments: attachments
                    };
                });


                // 리스트에서 가져온 제목과 날짜 사용
                let actualTitle = announcement.title || '';
                let actualDate = announcement.dateText || '';

                // 제목 불일치 관련 코드는 제거 (리스트에서 가져온 제목을 사용하므로 불필요)
                // if (!titleMatches) {
                //     console.log('⚠️ 제목 불일치 감지! 잘못된 상세 페이지에 접근했을 가능성이 있습니다.');
                //     console.log(`관리번호 ${announcement.detailMgtNo}로 접근했으나 다른 공고가 표시됨`);

                //     // 제목 불일치 시 재시도
                //     if (retries < maxRetries - 1) {
                //         retries++;
                //         console.log(`제목 불일치로 인한 재시도 ${retries}/${maxRetries}`);

                //         // 페이지를 완전히 새로 고침하여 세션 상태 초기화
                //         await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                //         await this.page.waitForTimeout(3000);

                //         // 리스트 페이지로 이동
                //         await this.page.goto(this.listUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
                //         await this.page.waitForTimeout(2000);

                //         // 자동 리다이렉트 대기
                //         try {
                //             await this.page.waitForFunction(
                //                 () => window.location.href.includes('OfrAction.do'),
                //                 { timeout: 10000 }
                //             );
                //         } catch { }
                //         await this.page.waitForTimeout(2000);

                //         continue; // 다시 시도
                //     } else {
                //         console.log('최대 재시도 횟수 도달. 제목 불일치 상태로 진행합니다.');
                //     }
                // }

                // 날짜는 리스트에서 가져온 값 사용
                const detailDate = this.extractDate(actualDate);

                return {
                    content: content.content,
                    date: detailDate,
                    attachments: content.attachments,
                    detailUrl: currentUrl
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
                }).catch(logErr => { });

                retries++;
                console.error(`상세 페이지 처리 실패 (시도 ${retries}/${maxRetries}):`, error.message);

                if (retries >= maxRetries) {
                    console.error('최대 재시도 횟수 초과. null 반환.');
                    return null;
                }

                await this.delay(2000 * retries);
            }
        }
    }

    /**
     * 공고 저장
     */
    async saveAnnouncement(announcement, detailContent) {
        try {
            // 제목 기반 중복 체크 (더 정확한 방법)
            const sanitizedTitle = sanitize(announcement.title).substring(0, 100);

            // 기존 폴더들 중에서 같은 제목으로 시작하는 폴더가 있는지 확인
            if (!this.force) {
                try {
                    const existingFolders = await fs.readdir(this.outputDir);
                    const duplicateFolder = existingFolders.find(folderName => {
                        // 폴더명에서 번호_제목 패턴에서 제목 부분 추출
                        const match = folderName.match(/^\d{3}_(.+)$/);
                        if (match) {
                            const existingTitle = match[1];
                            return existingTitle === sanitizedTitle;
                        }
                        return false;
                    });

                    if (duplicateFolder) {
                        console.log(`🔄 제목 기반 중복 감지 - 기존 폴더: ${duplicateFolder}`);
                        console.log(`🔄 현재 제목: ${announcement.title}`);
                        console.log(`⏭️ 중복 게시물 스킵`);
                        return;
                    }
                } catch (readDirError) {
                    // 실패 공고 DB 기록
                    await FailureLogger.logFailedAnnouncement({
                        site_code: this.siteCode,
                        title: announcement?.title || 'Unknown',
                        url: announcement?.link || announcement?.url,
                        detail_url: announcement?.detailUrl,
                        error_type: 'readDirError',
                        error_message: readDirError.message
                    }).catch(logErr => { });

                    console.log(`📁 출력 디렉토리 읽기 실패 (신규 생성): ${readDirError.message}`);
                }
            }

            // 폴더명 생성
            const folderName = `${String(this.counter).padStart(3, '0')}_${sanitizedTitle}`;
            const folderPath = path.join(this.outputDir, folderName);

            await fs.ensureDir(folderPath);

            let attachmentUrls = {};
            // 첨부파일 다운로드
            if (detailContent.attachments && detailContent.attachments.length > 0) {
                attachmentUrls = await this.downloadAttachments(detailContent.attachments, folderPath);
            }

            // 첨부파일에 실제 다운로드 URL 정보 추가
            if (attachmentUrls && Object.keys(attachmentUrls).length > 0) {
                console.log("📝 첨부파일 URL 정보 매핑 중...", attachmentUrls);

                if (detailContent.attachments) {
                    detailContent.attachments.forEach(function (item) {
                        const fileName = item.name;

                        // 파일명으로 URL 정보 찾기 (정확한 매칭)
                        if (attachmentUrls[fileName]) {
                            item.downloadInfo = attachmentUrls[fileName];
                            console.log(`✅ ${fileName} → URL 정보 추가됨`);
                        } else {
                            // 부분 매칭 시도 (파일명이 sanitize되어 변경된 경우)
                            const matchingKey = Object.keys(attachmentUrls).find(key =>
                                key.includes(fileName.substring(0, 10)) || fileName.includes(key.substring(0, 10))
                            );

                            if (matchingKey) {
                                item.downloadInfo = attachmentUrls[matchingKey];
                                console.log(`✅ ${fileName} → ${matchingKey}로 URL 정보 추가됨 (부분매칭)`);
                            } else {
                                console.log(`⚠️ ${fileName}에 대한 URL 정보를 찾을 수 없음`);
                            }
                        }
                    });
                }
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
            }).catch(logErr => { });

            console.error('공고 저장 실패:', error);
        }
    }

    /**
     * 첨부파일 다운로드
     */
    async downloadAttachments(attachments, folderPath) {
        try {
            const attachDir = path.join(folderPath, 'attachments');
            await fs.ensureDir(attachDir);

            console.log(`${attachments.length}개 첨부파일 다운로드 중...`);

            let allAttachmentUrls = {};

            for (let i = 0; i < attachments.length; i++) {
                const attachment = attachments[i];
                const attachmentUrlInfo = await this.downloadSingleAttachment(attachment, attachDir, i + 1);

                // 각 첨부파일의 URL 정보를 병합
                if (attachmentUrlInfo && Object.keys(attachmentUrlInfo).length > 0) {
                    allAttachmentUrls = { ...allAttachmentUrls, ...attachmentUrlInfo };
                    console.log(`📝 첨부파일 URL 정보 수집: ${Object.keys(attachmentUrlInfo).join(', ')}`);
                }

                await this.delay(500);
            }

            console.log(`📋 총 ${Object.keys(allAttachmentUrls).length}개 첨부파일 URL 정보 수집 완료`);
            return allAttachmentUrls;
        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => { });

            console.error('❌ 첨부파일 다운로드 실패:', error);
            return {};
        }
    }

    /**
     * 단일 첨부파일 다운로드 (goDownLoad 함수 사용)
     */
    async downloadSingleAttachment(attachment, attachDir, index) {
        try {
            console.log(`첨부파일 다운로드 시작: ${attachment.name} (${attachment.type})`);

            let attachmentUrlInfo = {};

            if (attachment.type === 'goDownLoad' && attachment.userFileName) {
                // goDownLoad 함수 사용
                console.log("🔄 goDownLoad 방식으로 다운로드");
                attachmentUrlInfo = await this.downloadWithGoDownLoad(attachment, attachDir, index);
            } else if (attachment.onclick) {
                // 일반적인 onclick 함수 사용
                console.log("🔄 onclick 방식으로 다운로드");
                attachmentUrlInfo = await this.downloadWithOnclick(attachment, attachDir, index);
            } else if (attachment.href) {
                // 직접 링크 다운로드
                console.log("🔄 직접 링크 방식으로 다운로드");
                attachmentUrlInfo = await this.downloadDirectLink(attachment, attachDir, index);
            } else {
                console.log(`⚠️ 다운로드 방법을 찾을 수 없음: ${attachment.name}`);
                return {};
            }

            return attachmentUrlInfo || {};
        } catch (error) {
            // 실패 공고 DB 기록
            await FailureLogger.logFailedAnnouncement({
                site_code: this.siteCode,
                title: announcement?.title || 'Unknown',
                url: announcement?.link || announcement?.url,
                detail_url: announcement?.detailUrl,
                error_type: 'error',
                error_message: error.message
            }).catch(logErr => { });

            console.error(`❌ 첨부파일 다운로드 실패 (${attachment.name}):`, error.message);
            return {};
        }
    }

    /**
     * goDownLoad 함수를 사용한 다운로드
     */
    async downloadWithGoDownLoad(attachment, attachDir, index) {
        try {
            console.log(`goDownLoad 함수로 다운로드 시작: ${attachment.name}`);

            // Playwright의 다운로드 이벤트 설정 (더 긴 타임아웃)
            const downloadPromise = this.page.waitForEvent('download', { timeout: 60000 });

            // goDownLoad 함수 실행 (인자를 객체로 전달)
            await this.page.evaluate((params) => {
                const { userFileName, sysFileName, filePath } = params;
                if (typeof window.goDownLoad === 'function') {
                    window.goDownLoad(userFileName, sysFileName, filePath);
                } else {
                    console.error('goDownLoad 함수를 찾을 수 없음');
                    throw new Error('goDownLoad 함수를 찾을 수 없음');
                }
            }, {
                userFileName: attachment.userFileName,
                sysFileName: attachment.sysFileName,
                filePath: attachment.filePath
            });

            // 다운로드 완료 대기
            const download = await downloadPromise;

            // 실제 다운로드 URL 정보 추출
            const actualDownloadUrl = download.url();

            console.log(`🔍 goDownLoad 실제 다운로드 URL: ${actualDownloadUrl}`);

            // 파일명 정리
            const fileName = sanitize(attachment.name || `attachment_${index}`, { replacement: '_' });
            const filePath = path.join(attachDir, fileName);

            // 파일 저장
            await download.saveAs(filePath);

            console.log(`✅ goDownLoad 다운로드 완료: ${fileName}`);

            return {
                [fileName]: {
                    originalOnclick: attachment.onclick,
                    actualDownloadUrl: actualDownloadUrl,
                    fileName: fileName,
                    downloadType: 'goDownLoad'
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
            }).catch(logErr => { });

            console.error(`❌ goDownLoad 함수 다운로드 실패: ${error.message}`);
            throw error;
        }
    }

    /**
     * onclick 함수를 사용한 다운로드
     */
    async downloadWithOnclick(attachment, attachDir, index) {
        try {
            console.log(`onclick 함수로 다운로드 시작: ${attachment.name}`);

            // Playwright의 다운로드 이벤트 설정
            const downloadPromise = this.page.waitForEvent('download', { timeout: 30000 });

            // onclick 함수 실행
            await this.page.evaluate((onclick) => {
                eval(onclick);
            }, attachment.onclick);

            // 다운로드 완료 대기
            const download = await downloadPromise;

            // 실제 다운로드 URL 정보 추출
            const actualDownloadUrl = download.url();

            console.log(`🔍 onclick 실제 다운로드 URL: ${actualDownloadUrl}`);

            // 파일명 정리
            const fileName = sanitize(attachment.name || `attachment_${index}`, { replacement: '_' });
            const filePath = path.join(attachDir, fileName);

            // 파일 저장
            await download.saveAs(filePath);

            console.log(`✅ onclick 다운로드 완료: ${fileName}`);

            return {
                [fileName]: {
                    originalOnclick: attachment.onclick,
                    actualDownloadUrl: actualDownloadUrl,
                    fileName: fileName,
                    downloadType: 'onclick'
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
            }).catch(logErr => { });

            console.error(`❌ onclick 다운로드 실패: ${error.message}`);
            throw error;
        }
    }

    /**
     * 직접 링크로 다운로드
     */
    async downloadDirectLink(attachment, attachDir, index) {
        try {
            console.log(`직접 링크로 다운로드 시작: ${attachment.name}`);
            console.log(`원본 링크: ${attachment.href}`);

            // 직접 링크 클릭
            const downloadPromise = this.page.waitForEvent('download', { timeout: 30000 });

            await this.page.evaluate((href) => {
                const link = document.createElement('a');
                link.href = href;
                link.click();
            }, attachment.href);

            // 다운로드 완료 대기
            const download = await downloadPromise;

            // 실제 다운로드 URL 정보 추출
            const actualDownloadUrl = download.url();

            console.log(`🔍 실제 다운로드 URL: ${actualDownloadUrl}`);

            // 파일명 정리 (제안된 파일명 우선 사용)
            const fileName = sanitize(attachment.name || `attachment_${index}`, { replacement: '_' });
            const filePath = path.join(attachDir, fileName);

            // 파일 저장
            await download.saveAs(filePath);

            console.log(`✅ downloadDirectLink 완료: ${fileName}`);

            return {
                [fileName]: {
                    originalUrl: attachment.href,
                    actualDownloadUrl: actualDownloadUrl,
                    fileName: fileName
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
            }).catch(logErr => { });

            console.error(`❌ 직접 링크 다운로드 실패: ${error.message}`);
            throw error;
        }
    }

    /**
     * 직접 POST 요청으로 다운로드 (Axios 사용)
     */
    async downloadViaDirectPost(attachment, attachDir, index) {
        try {
            const downloadUrl = `${this.baseUrl}/emwp/jsp/lga/homepage/FileDown.jsp`;

            const formData = new URLSearchParams();
            formData.append('file_seq', attachment.fileSeq);
            formData.append('org_file_nm', attachment.orgFileName);
            formData.append('save_file_nm', attachment.saveFileName);

            const response = await axios({
                method: 'POST',
                url: downloadUrl,
                data: formData,
                responseType: 'stream',
                timeout: 30000,
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': config.security.userAgent,
                    'Referer': this.listUrl
                }
            });

            const fileName = sanitize(attachment.name || `attachment_${index}`, { replacement: '_' });
            const filePath = path.join(attachDir, fileName);

            const writer = fs.createWriteStream(filePath);
            response.data.pipe(writer);

            return new Promise((resolve, reject) => {
                writer.on('finish', () => {
                    console.log(`직접 POST 다운로드 완료: ${fileName}`);
                    resolve();
                });
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
            }).catch(logErr => { });

            throw new Error(`직접 POST 다운로드 실패: ${error.message}`);
        }
    }

    /**
     * 마크다운 컨텐츠 생성
     */
    generateMarkdownContent(announcement, detailContent) {
        const lines = [];

        lines.push(`**제목**: ${announcement.title}`);
        lines.push('');

        if (detailContent.detailUrl) {
            lines.push(`**원본 URL**: ${detailContent.detailUrl}`);
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
     * 날짜 추출
     */
    extractDate(dateText) {
        if (!dateText) return null;

        let cleanText = dateText.trim();

        // 날짜 패턴 추출
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

        // 날짜처럼 보이지 않는 텍스트는 조기 반환 (숫자가 없거나 연도가 없는 경우)
        if (!cleanText.match(/\d/) || !cleanText.match(/\d{4}/)) {
            return null;
        }

        const naturalDate = moment(cleanText);
        if (naturalDate.isValid()) {
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
                }).catch(logErr => { });

                console.warn('브라우저 정리 중 오류:', error.message);
            }
        }

        console.log(`\n=== ${this.region} 이민원 스크래핑 완료 ===`);
        console.log(`처리된 공고 수: ${this.counter - 1}`);
        console.log(`출력 디렉토리: ${this.outputDir}`);
    }
}

// CLI 인터페이스
function setupCLI() {
    return yargs
        .option('region', {
            alias: 'r',
            type: 'string',
            description: '지역 이름 (청양군, 서울특별시 등)',
            required: true
        })
        .option('date', {
            alias: 'd',
            type: 'string',
            description: '대상 날짜 (YYYYMMDD 형태, 예: 20240101)',
            default: null
        })
        .option('output', {
            alias: 'o',
            type: 'string',
            description: '출력 디렉토리',
            default: 'eminwon_data'
        })
        .option('force', {
            alias: 'f',
            type: 'boolean',
            description: '기존 폴더가 있어도 덮어쓰기',
            default: false
        })
        .option('go-page', {
            alias: 'p',
            type: 'number',
            description: '시작할 페이지 번호 (1부터 시작)',
            default: null
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
        .example('$0 --region 청양군 --date 20240101', '청양군 2024년 1월 1일 이후 공고 스크래핑')
        .example('$0 -r 부산광역시', '부산광역시 전체 공고 스크래핑')
        .example('$0 -r 청주시 --force', '청주시 전체 공고 스크래핑 (기존 폴더 덮어쓰기)')
        .example('$0 -r 청주시 --go-page 5', '청주시 5페이지부터 스크래핑 시작')
        .help()
        .argv;
}

// 메인 실행
async function main() {
    const argv = setupCLI();

    const scraper = new EminwonScraper({
        region: argv.region,
        targetDate: argv.date,
        outputDir: argv.output,
        force: argv.force,
        goPage: argv['go-page']
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

module.exports = EminwonScraper;
