#!/usr/bin/env node

/**
 * 금정구청 공고 스크래핑 시스템
 * 
 * 기능:
 * 1. 날짜 기반 필터링으로 지정 날짜/연도까지 스크래핑
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

class AnnouncementScraper {
    constructor(options = {}) {
        this.targetYear = options.targetYear || new Date().getFullYear();
        this.targetDate = options.targetDate || null;
        this.baseOutputDir = options.outputDir || 'scraped_data';
        this.siteCode = options.siteCode || 'geumjeong';
        this.outputDir = path.join(this.baseOutputDir, this.siteCode);
        this.baseUrl = 'https://www.geumjeong.go.kr/board/list.geumj?boardId=BBS_0000006&menuCd=DOM_000000124002003000&contentsSid=3857&cpath=';
        this.browser = null;
        this.page = null;
        this.processedTitles = new Set();
        this.counter = 1;
        this.dateFormat = 'YYYY/MM/DD';
        this.force = options.force || false;
        this.options = options;
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

                this.page = await this.context.newPage();

                this.page.setDefaultTimeout(config.browser.timeouts.default);
                this.page.setDefaultNavigationTimeout(config.browser.timeouts.navigation);

                this.browser.on('disconnected', () => {
                    console.warn('브라우저 연결이 끊어졌습니다.');
                });

                this.page.on('crash', () => {
                    console.warn('페이지 크래시 발생');
                });

                this.page.on('console', (msg) => {
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

                    consecutiveErrors = 0;

                    for (const announcement of announcements) {
                        try {
                            const shouldStop = await this.processAnnouncement(announcement);
                            if (shouldStop) {
                                console.log(`\n대상 날짜/연도 이전 공고 발견. 스크래핑 종료.`);
                                shouldContinue = false;
                                break;
                            }
                        } catch (announcementError) {
                            console.error(`공고 처리 중 오류 (${announcement.title}):`, announcementError.message);
                            continue;
                        }
                    }

                    if (shouldContinue) {
                        currentPage++;
                        await this.delay(1000);
                    }

                } catch (pageError) {
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

                await this.page.goto(listUrl, {
                    waitUntil: 'networkidle',
                    timeout: config.browser.timeouts.navigation
                });

                await this.page.waitForSelector('tbody tr', {
                    timeout: config.browser.timeouts.default
                });

                const announcements = await this.page.evaluate(() => {
                    const rows = document.querySelectorAll('tbody tr');
                    const results = [];

                    rows.forEach(row => {
                        // 공지사항 제외
                        const isNotice = row.querySelector('.notice_ico');
                        if (isNotice) return;

                        const titleElement = row.querySelector('td:nth-child(2) a');
                        const dateElement = row.querySelector('td:nth-child(5)');
                        const deptElement = row.querySelector('td:nth-child(4)');

                        if (!titleElement || !dateElement) return;

                        const title = titleElement.textContent.trim();
                        const dateText = dateElement.textContent.trim();
                        const dept = deptElement ? deptElement.textContent.trim() : '';

                        console.log("dateText", dateText)
                        // 상세 페이지 URL 추출
                        const href = titleElement.getAttribute('href');
                        let url = '';

                        if (href) {
                            // 상대 경로인 경우
                            if (href.startsWith('/')) {
                                url = `https://www.geumjeong.go.kr${href}`;
                            } else if (href.startsWith('http')) {
                                url = href;
                            } else {
                                url = `https://www.geumjeong.go.kr/${href}`;
                            }
                        }

                        results.push({
                            title,
                            dateText,
                            dept,
                            url,
                            listDate: dateText
                        });
                    });

                    return results;
                });

                console.log(`리스트에서 ${announcements.length}개 공고 발견`);
                return announcements;

            } catch (error) {
                retries++;
                console.error(`리스트 페이지 로드 실패 (시도 ${retries}/${maxRetries}):`, error.message);

                if (retries >= maxRetries) {
                    console.error('리스트 페이지 로드 최종 실패');
                    return [];
                }

                await this.delay(3000 * retries);
            }
        }

        return [];
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
            if (this.processedTitles.has(announcement.title)) {
                console.log(`중복 게시물 스킵: ${announcement.title}`);
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

            this.processedTitles.add(announcement.title);
            console.log(`처리 완료: ${announcement.title}`);

            return false;

        } catch (error) {
            console.error(`공고 처리 실패 (${announcement.title}):`, error.message);
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
                if (!announcement.url) {
                    console.error('상세 페이지 URL이 없습니다.');
                    return null;
                }

                console.log(`상세 페이지 URL: ${announcement.url}`);

                await this.page.goto(announcement.url, {
                    waitUntil: 'networkidle',
                    timeout: config.browser.timeouts.navigation
                });

                // 콘텐츠 영역 대기
                await this.page.waitForSelector('body', {
                    timeout: config.browser.timeouts.default
                });

                const evalOptions = { ...this.options, announcement }

                const content = await this.page.evaluate((options) => {

                    const {
                        announcement
                    } = options;


                    // 본문 내용 추출 - 다양한 셀렉터 시도
                    let contentArea = document.querySelector('.board_view .view_content');
                    if (!contentArea) contentArea = document.querySelector('.content');
                    if (!contentArea) contentArea = document.querySelector('#content');
                    if (!contentArea) contentArea = document.querySelector('.board_content');
                    if (!contentArea) contentArea = document.querySelector('tbody');

                    const textContent = contentArea ? (contentArea.innerText || contentArea.textContent || '') : '';

                    // 패턴 2: 테이블에서 등록일 찾기
                    // 날짜 추출
                    let dateText = '';
                    //현재 등록일의 경우는 아예 클래스 등이 지정되어 있지 않다.
                    if (!dateText) {
                        //이 부분을 처리하자

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
                    const fileLinks = document.querySelectorAll('a[href*="/board/download.geumj"]');

                    fileLinks.forEach(link => {
                        let fileName = link.textContent.trim();
                        // 파일 크기 정보 제거 (예: "파일명.hwp(52 kb)" -> "파일명.hwp")
                        fileName = fileName.replace(/\(\d+\s*kb\s*\)$/i, '').trim();
                        let downloadUrl = link.getAttribute('href');

                        if (downloadUrl) {
                            // 상대 경로인 경우 절대 경로로 변환
                            if (downloadUrl.startsWith('/')) {
                                downloadUrl = `https://www.geumjeong.go.kr${downloadUrl}`;
                            } else if (!downloadUrl.startsWith('http')) {
                                downloadUrl = `https://www.geumjeong.go.kr/${downloadUrl}`;
                            }

                            attachments.push({
                                name: fileName,
                                url: downloadUrl
                            });
                        }
                    });

                    return {
                        content: textContent.trim(),
                        dateText: dateText,
                        attachments: attachments
                    };
                }, evalOptions);

                // 날짜 파싱
                const detailDate = this.extractDate(content.dateText);


                return {
                    url: announcement.url,
                    content: content.content,
                    date: detailDate,
                    attachments: content.attachments
                };

            } catch (error) {
                retries++;
                console.error(`상세 페이지 처리 실패 (시도 ${retries}/${maxRetries}):`, error.message);

                if (retries >= maxRetries) {
                    console.error('상세 페이지 처리 최종 실패');
                    return null;
                }

                await this.delay(3000 * retries);
            }
        }

        return null;
    }

    /**
     * 공고 저장
     */
    async saveAnnouncement(announcement, detailContent) {
        try {
            const folderName = `${String(this.counter).padStart(3, '0')}_${sanitize(announcement.title)}`;
            const folderPath = path.join(this.outputDir, folderName);

            // 폴더가 이미 존재하고 force 옵션이 false면 스킵
            if (await fs.pathExists(folderPath) && !this.force) {
                console.log(`폴더가 이미 존재하여 스킵: ${folderName}`);
                this.counter++;
                return;
            }

            await fs.ensureDir(folderPath);

            // content.md 생성
            const contentMd = this.generateMarkdownContent(announcement, detailContent);
            await fs.writeFile(path.join(folderPath, 'content.md'), contentMd, 'utf8');

            // 첨부파일 다운로드
            if (detailContent.attachments && detailContent.attachments.length > 0) {
                await this.downloadAttachments(detailContent.attachments, folderPath);
            }

            this.counter++;

        } catch (error) {
            console.error(`공고 저장 실패 (${announcement.title}):`, error);
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

            for (let i = 0; i < attachments.length; i++) {
                const attachment = attachments[i];
                await this.downloadSingleAttachment(attachment, attachDir, i + 1);
                await this.delay(500); // 0.5초 대기
            }

        } catch (error) {
            console.error('첨부파일 다운로드 실패:', error);
        }
    }

    /**
     * 단일 첨부파일 다운로드
     */
    async downloadSingleAttachment(attachment, attachDir, index) {
        try {
            let fileName = attachment.name || `attachment_${index}`;
            // 파일 크기 정보 제거 (다운로드시에도 한번 더 체크)
            fileName = fileName.replace(/\(\d+\s*kb\s*\)$/i, '').trim();
            const savePath = path.join(attachDir, sanitize(fileName));

            console.log(`다운로드 중: ${fileName}`);

            // axios를 사용하여 파일 다운로드
            const response = await axios({
                method: 'GET',
                url: attachment.url,
                responseType: 'arraybuffer',
                headers: {
                    'User-Agent': config.security.userAgent,
                    'Referer': 'https://www.geumjeong.go.kr/'
                },
                timeout: 60000,
                maxRedirects: 5
            });

            await fs.writeFile(savePath, response.data);
            console.log(`다운로드 완료: ${fileName}`);

        } catch (error) {
            console.error(`첨부파일 다운로드 실패 (${attachment.name}):`, error.message);
        }
    }

    /**
     * 마크다운 컨텐츠 생성
     */
    generateMarkdownContent(announcement, detailContent) {
        const lines = [];

        lines.push(`# ${announcement.title}`);
        lines.push('');
        lines.push(`**원본 URL**:: ${detailContent.url}`);
        lines.push('');


        if (detailContent.date) {
            lines.push(`**작성일**: ${detailContent.date.format('YYYY-MM-DD')}`);
            lines.push('');
        }

        // if (announcement.dept) {
        //     lines.push(`**담당부서:** ${announcement.dept}`);
        //     lines.push('');
        // }

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
                lines.push(`${i + 1}. ${att.name}:${att.url || ''}`);
            });
        }

        return lines.join('\n');
    }

    /**
     * 리스트 URL 구성
     */
    buildListUrl(pageNum) {
        // 금정구청은 페이지 파라미터가 startPage로 작동하는 것 같음
        // 10개씩 보여주므로 페이지당 10씩 증가
        // const startPage = (pageNum - 1) * 10 + 1;
        return `${this.baseUrl}&startPage=${pageNum}`;
    }

    /**
     * 날짜 추출 및 파싱
     */
    extractDate(dateText) {
        if (!dateText) return null;

        try {
            // 2025/09/18 형식
            if (dateText.match(/\d{4}\/\d{2}\/\d{2}/)) {
                return moment(dateText, 'YYYY/MM/DD');
            }

            // 2025-09-18 형식
            if (dateText.match(/\d{4}-\d{2}-\d{2}/)) {
                return moment(dateText, 'YYYY-MM-DD');
            }

            // 2025.09.18 형식
            if (dateText.match(/\d{4}\.\d{2}\.\d{2}/)) {
                return moment(dateText, 'YYYY.MM.DD');
            }

            // 기타 형식 시도
            const parsed = moment(dateText);
            if (parsed.isValid()) {
                return parsed;
            }

        } catch (error) {
            console.warn(`날짜 파싱 실패: ${dateText}`);
        }

        return null;
    }

    /**
     * 지연 함수
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * 정리 작업
     */
    async cleanup() {
        try {
            if (this.page) {
                await this.page.close();
            }
            if (this.context) {
                await this.context.close();
            }
            if (this.browser) {
                await this.browser.close();
            }
            console.log('\n브라우저 종료 완료');
        } catch (error) {
            console.error('브라우저 종료 중 오류:', error.message);
        }
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
            default: 'geumjeong',
            required: true
        })
        .option('force', {
            alias: 'f',
            type: 'boolean',
            description: '기존 폴더가 있어도 덮어쓰기',
            default: false
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
        outputDir: argv.output,
        siteCode: argv.site,
        force: argv.force
    });

    await scraper.scrape();
}

// 직접 실행시에만 메인 함수 호출
if (require.main === module) {
    main().catch(error => {
        console.error('치명적 오류:', error);
        process.exit(1);
    });
}

module.exports = AnnouncementScraper;