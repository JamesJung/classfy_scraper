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
const https = require('https');
const fs = require('fs-extra');
const path = require('path');
const moment = require('moment');
const sanitize = require('sanitize-filename');
const yargs = require('yargs');
const config = require('./config');

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
     * 브라우저 초기화
     */
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
                    console.log(`[브라우저 콘솔]: ${msg.text()}`);
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

                    const rows = document.querySelectorAll(selectors.listSelector);

                    const results = [];

                    rows.forEach((row, index) => {
                        // 헤더 행 스킵
                        if (index === 0 && row.querySelector('th')) return;

                        const titleElement = row.querySelector(selectors.titleSelector);
                        const dateElement = row.querySelector(selectors.dateSelector);
                        const linkElement = row.querySelector(".a1");

                        if (titleElement && dateElement) {
                            const title = titleElement.textContent.trim();
                            const dateText = dateElement.textContent.replace("등록일:", '').trim();
                            // 다양한 방식으로 링크 정보 추출
                            let href = titleElement.href;
                            if (linkElement) {
                                href = linkElement.href
                            }

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
                                this.processedTitles.add(announcement.title);
                                this.processedTitles.add(sanitizedTitle);
                                return false;
                            }
                        }
                    }
                }
            } catch (fsError) {
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

            this.processedTitles.add(announcement.title);
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
                        '.s-v-board-default', '.content_box', '.program--contents',
                        '.bbs_skin', '.view_box', '#content',
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

                    // 첨부파일 링크 추출
                    const attachments = [];


                    const downloadLinks = document.querySelectorAll('a[href*="download.jsp"]');

                    console.log("downloadLinks", downloadLinks)
                    downloadLinks.forEach(link => {
                        const fileName = link.textContent.trim();
                        const fileURL = link.href;

                        attachments.push({
                            name: fileName,
                            url: fileURL
                        });
                    });


                    console.log("attachments", attachments)


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

            console.log("attachment", attachment)

            console.log("downloadUrl", downloadUrl)
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
                    downloadUrl = `https://eminwon.osan.go.kr/emwp/jsp/ofr/FileDown.jsp?user_file_nm=${enc_user_file_nm}&sys_file_nm=${enc_sys_file_nm}&file_path=${enc_file_path}`;
                    // fileName = originalName; // 원본 파일명 사용
                    downloadType = 'goDownload';
                } else {
                    // 기존 onclick 이벤트에서 URL 추출 시도
                    const match = attachment.onclick.match(/(?:window\.open|location\.href|download)\(['"]([^'"]*)['"]\)/);
                    if (match) {
                        downloadUrl = match[1];
                    }
                }

            }

            // 상대 URL을 절대 URL로 변환
            if (downloadUrl && !downloadUrl.startsWith('http')) {
                console.log('상대 URL을 절대 URL로 변환')
                downloadUrl = new URL(downloadUrl, this.baseUrl).toString();
            }

            console.log("downloadUrl", downloadUrl)


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
     * 브라우저 클릭을 통한 다운로드 (실제 링크 클릭)
     */
    async downloadViaBrowserClick(url, userFileNm, sysFileNm, filePath, originalFileName, attachDir, displayFileName) {
        try {
            console.log('🖱️ 브라우저에서 실제 링크 클릭 방식 다운로드 시작...');

            // 파일명 정리
            const cleanFileName = sanitize(displayFileName, { replacement: '_' });
            const expectedFilePath = path.join(attachDir, cleanFileName);

            console.log(`다운로드할 파일: ${cleanFileName}`);
            console.log(`저장 경로: ${expectedFilePath}`);

            // 디렉토리가 없으면 먼저 생성
            await fs.ensureDir(attachDir);

            // CDP 세션 설정
            const client = await this.page.context().newCDPSession(this.page);

            // 다운로드 동작 설정
            await client.send('Page.setDownloadBehavior', {
                behavior: 'allow',
                downloadPath: attachDir
            });

            // 다운로드 이벤트 리스너 설정
            const downloadPromise = new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    reject(new Error('다운로드 타임아웃 (10초)'));
                }, 10000);

                const downloadHandler = async (download) => {
                    try {
                        clearTimeout(timeout);

                        // 다운로드가 제안한 파일명으로 저장 (서버가 제공한 이름)
                        const suggestedFilename = download.suggestedFilename();
                        const tempPath = path.join(attachDir, suggestedFilename);
                        console.log(`서버 제안 파일명: ${suggestedFilename}`);

                        await download.saveAs(tempPath);

                        // 파일 크기 확인
                        const stats = await fs.stat(tempPath);
                        console.log(`다운로드 완료: ${tempPath} (${stats.size} bytes)`);

                        // 134B 에러 파일 체크
                        if (stats.size < 200) {
                            try {
                                const content = await fs.readFile(tempPath, 'utf8');
                                if (content.includes('잘못된 경로')) {
                                    // 에러 파일 삭제
                                    await fs.unlink(tempPath);
                                    throw new Error('에러 페이지 다운로드됨 (134B)');
                                }
                            } catch (readError) {
                                // 바이너리 파일일 수 있으므로 읽기 오류는 무시
                            }
                        }

                        // 정상 파일인 경우 원하는 이름으로 변경
                        const finalPath = path.join(attachDir, cleanFileName);
                        if (tempPath !== finalPath) {
                            // 이미 존재하는 파일이 있으면 삭제
                            if (await fs.pathExists(finalPath)) {
                                await fs.unlink(finalPath);
                            }
                            await fs.move(tempPath, finalPath, { overwrite: true });
                            console.log(`파일명 변경: ${suggestedFilename} → ${cleanFileName}`);
                        }
                        console.log(`✅ 파일 저장 완료: ${finalPath} (${stats.size} bytes)`);

                        resolve({ success: true, savedPath: finalPath, fileSize: stats.size });
                    } catch (error) {
                        clearTimeout(timeout);
                        reject(error);
                    }
                };

                this.page.once('download', downloadHandler);
            });

            // 현재 페이지에서 해당 파일명의 링크를 찾아서 클릭
            console.log('페이지에서 첨부파일 링크 찾기...');

            const clicked = await this.page.evaluate((targetFileName) => {
                // 모든 첨부파일 링크 찾기
                const links = document.querySelectorAll('a[href*="gourl"]');

                for (const link of links) {
                    // 링크 텍스트나 title이 대상 파일명과 일치하는지 확인
                    if (link.textContent.includes(targetFileName.substring(0, 20)) ||
                        (link.title && link.title.includes(targetFileName.substring(0, 20)))) {
                        console.log('찾은 링크:', link.href);
                        link.click();
                        return true;
                    }
                }

                // 못 찾았으면 모든 fnFileDown 링크 중 첫번째 클릭
                if (links.length > 0) {
                    console.log('첫번째 fnFileDown 링크 클릭:', links[0].href);
                    links[0].click();
                    return true;
                }

                return false;
            }, displayFileName);

            if (!clicked) {
                throw new Error('페이지에서 다운로드 링크를 찾을 수 없음');
            }

            // 다운로드 완료 대기
            console.log('다운로드 대기 중...');
            const result = await downloadPromise;

            // 결과 검증
            if (result.fileSize < 200) {
                throw new Error(`파일이 너무 작음 (${result.fileSize} bytes) - 에러 페이지일 가능성`);
            }

            return result;

        } catch (error) {
            console.error('브라우저 실제 클릭 다운로드 실패:', error.message);

            // 타임아웃이나 다운로드 이벤트가 발생하지 않은 경우
            // 직접 HTTP 요청 방식으로 시도
            console.log('폴백: 직접 HTTP 요청 방식 시도...');

            // Referer와 Cookie를 현재 페이지에서 가져오기
            const cookies = await this.page.context().cookies();
            const cookieString = cookies.map(c => `${c.name}=${c.value}`).join('; ');
            const currentUrl = this.page.url();

            return await this.downloadViaAxiosWithSession(url, userFileNm, sysFileNm, filePath, attachDir, displayFileName, cookieString, currentUrl);
        }
    }

    /**
     * Axios를 사용한 세션 기반 다운로드
     */
    async downloadViaAxiosWithSession(url, userFileNm, sysFileNm, filePath, attachDir, displayFileName, cookieString, referer) {
        try {
            console.log('Axios 세션 기반 다운로드 시작...');

            const downloadUrl = url || 'https://eminwon.hanma.go.kr/emwp/jsp/ofr/FileDownNew.jsp';
            const postData = `user_file_nm=${userFileNm}&sys_file_nm=${sysFileNm}&file_path=${filePath}`;

            console.log(`Cookie: ${cookieString ? 'Present' : 'None'}`);
            console.log(`Referer: ${referer}`);

            const response = await axios({
                method: 'POST',
                url: downloadUrl,
                data: postData,
                responseType: 'stream',
                timeout: 30000,
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': '*/*',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': referer,
                    'Cookie': cookieString
                }
            });

            const safeFileName = displayFileName.replace(/[\/\\:*?"<>|]/g, '_');
            const savePath = path.join(attachDir, safeFileName);
            const writer = fs.createWriteStream(savePath);

            response.data.pipe(writer);

            return new Promise((resolve, reject) => {
                writer.on('finish', async () => {
                    // 파일 크기 확인
                    const stats = await fs.stat(savePath);
                    if (stats.size < 200) {
                        const content = await fs.readFile(savePath, 'utf8');
                        if (content.includes('잘못된 경로')) {
                            await fs.unlink(savePath);
                            reject(new Error('에러 페이지 다운로드됨'));
                            return;
                        }
                    }
                    console.log(`✅ 파일 다운로드 성공: ${savePath} (${stats.size} bytes)`);
                    resolve({ success: true, savedPath: savePath, fileName: displayFileName, fileSize: stats.size });
                });
                writer.on('error', reject);
            });

        } catch (error) {
            console.error('Axios 세션 다운로드 실패:', error.message);
            throw error;
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
                },
                httpsAgent: new https.Agent({
                    rejectUnauthorized: false // SSL 인증서 검증 비활성화
                })
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
                // console.log('goDownload 원본 파일명 우선 사용:', fileName);
            }

            // 파일명 정리 (한글 보존)
            const cleanFileName = sanitize(fileName, { replacement: '_' });
            const filePath = path.join(attachDir, cleanFileName);

            // console.log(`최종 파일명: ${cleanFileName}`);
            // console.log(`저장 경로: ${filePath}`);

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
                    attachInfo = `${i + 1}. ${att.name}: ${att.downloadInfo.actualDownloadUrl}`
                } else if (att.url) {
                    // downloadInfo가 없어도 원본 URL이 있으면 표시
                    attachInfo = `${i + 1}. ${att.name}: ${att.url}`
                } else {
                    attachInfo = `${i + 1}. ${att.name}`;
                }
                lines.push(attachInfo);
                lines.push('');
            });
        }

        return lines.join('\n');
    }


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

        // 2. 이미 완전한 URL인 경우
        const link = announcement.link;
        if (link && link.startsWith('http') && !link.endsWith('#')) {
            return link;
        }

        // 3. 상대 URL인 경우
        if (link && link.startsWith('/')) {
            return new URL(link, this.baseUrl).toString();
        }

        const downloadUrl = announcement.onclick
        // 4. onclick 이벤트에서 URL 추출 시도
        if (announcement.onclick) {

            //goDetialView(id, num, type, key)

            const regex = /goDetialView\('([^']+)',\s*'([^']+)',\s*'([^']*)',\s*'([^']*)'\)/;

            const matches = downloadUrl.match(regex);

            const id = matches[1];
            const num = matches[2];
            const type = matches[3];
            const key = matches[4];

            // 직접 상세 페이지 URL 구성
            const detailUrl = `https://www.haenam.go.kr/index.9is?contentUid=18e3368f7913117f01791bdc63505ada&notmgtNoView=${id}&nowPageNum=${num}&searchType2=${type}&keyword=${key}&recordCountPerPage=10`;
            console.log('구성된 상세 페이지 URL:', detailUrl);
            return detailUrl;

        }

        // JavaScript void(0) 링크의 경우 브라우저 클릭 시도
        if (link === 'javascript:void(0);' && announcement.onclick) {
            console.log('javascript:void(0) 링크 감지, 브라우저 클릭 방식 시도...');
            const clickUrl = await this.getUrlByBrowserClick(announcement);
            if (clickUrl) {
                return clickUrl;
            }
        }

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

        // "등록일\n2025-09-10" 같은 형식에서 날짜만 추출
        const dateMatch = cleanText.match(/(\d{4}[-.\\/]\d{1,2}[-.\\/]\d{1,2})/);
        if (dateMatch) {
            cleanText = dateMatch[1];
        }

        // 다양한 날짜 형식 시도

        // YY.MM.DD 형식 체크 (예: 24.12.31)
        const yymmddMatch = cleanText.match(/^(\d{2})\-(\d{1,2})\-(\d{1,2})$/);
        if (yymmddMatch) {
            // 2자리 연도를 4자리로 변환 (00-99 → 2000-2099)
            const year = '20' + yymmddMatch[1];
            const month = yymmddMatch[2].padStart(2, '0');
            const day = yymmddMatch[3].padStart(2, '0');
            cleanText = `${year}-${month}-${day}`;
        }


        const formats = [
            'YYYY-MM-DD',
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

        url.searchParams.set('curPage', pageNum);
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
            default: 'ulsan',
            required: true
        })
        .option('url', {
            alias: 'u',
            type: 'string',
            description: '기본 URL',
            default: 'https://www.ulsan.go.kr/u/rep/transfer/notice/list.ulsan?mId=001004002000000000',
            required: true
        })
        .option('list-selector', {
            type: 'string',
            description: '리스트 선택자',
            default: 'table.tbl_bd_list > tbody > tr'
        })
        .option('title-selector', {
            type: 'string',
            description: '제목 선택자',
            default: 'td:nth-child(2) a'
        })
        .option('date-selector', {
            type: 'string',
            description: '날짜 선택자',
            default: 'td:nth-child(6) '
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

    await scraper.scrape();
}

// 스크립트가 직접 실행될 때만 main 함수 호출
if (require.main === module) {
    main().catch(console.error);
}

module.exports = AnnouncementScraper;
