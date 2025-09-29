#!/usr/bin/env node

/**
 * 청양군 이민원 사이트 공고 스크래핑 시스템
 * 
 * 기능:
 * 1. 날짜 기반 필터링으로 지정 연도까지 스크래핑
 * 2. 리스트 -> 상세 페이지 처리
 * 3. JavaScript 기반 동적 페이지 처리
 * 4. content.md 파일 생성 (본문만 추출)
 * 5. 첨부파일 다운로드 (POST 방식)
 * 6. 중복 게시물 스킵
 * 7. 폴더 구조: 001_게시물이름/content.md, attachments/
 * 
 * 청양군 이민원 사이트 특징:
 * - JavaScript 기반 페이징 (goPage 함수)
 * - searchDetail 함수로 상세 페이지 이동
 * - 첨부파일 다운로드 (fnFileDown 함수)
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

class CheongyangScraper {
    constructor(options = {}) {
        this.targetYear = options.targetYear || new Date().getFullYear();
        this.baseOutputDir = options.outputDir || 'scraped_data';
        this.siteCode = options.siteCode || 'cheongyang';
        this.outputDir = path.join(this.baseOutputDir, this.siteCode);
        this.baseUrl = 'https://eminwon.cheongyang.go.kr';
        this.listUrl = 'https://eminwon.cheongyang.go.kr/emwp/jsp/ofr/OfrNotAncmtLSub.jsp?not_ancmt_se_code=01,02,03,04,05&cpath=';
        this.actionUrl = 'https://eminwon.cheongyang.go.kr/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do';
        this.browser = null;
        this.context = null;
        this.page = null;
        this.processedTitles = new Set();
        this.counter = 1;

        this.targetDate = options.targetDate || null;
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
                    bypassCSP: true
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

                // this.page.on('console', (msg) => {
                //     //console.log(`[브라우저 콘솔]: ${msg.text()}`);
                // });

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

            console.log(`\n=== 청양군 이민원 스크래핑 시작 ===`);
            console.log(`대상 연도: ${this.targetYear}`);
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
                console.log(`리스트 URL로 이동: ${this.listUrl}`);

                if (!this.browser || !this.page || this.page.isClosed()) {
                    console.log('브라우저 연결이 끊어져 재초기화합니다...');
                    await this.initBrowser();
                }

                // 1단계: 먼저 초기 페이지 방문
                console.log('1단계: 초기 페이지 방문하여 세션 확보...');
                await this.page.goto(this.listUrl, {
                    waitUntil: 'domcontentloaded',
                    timeout: 30000
                });

                await this.page.waitForTimeout(2000);
                console.log(`초기 페이지 URL: ${this.page.url()}`);

                // 2단계: 페이지에서 자동으로 POST 요청이 실행되는지 대기
                console.log('2단계: 자동 리다이렉트 또는 폼 제출 대기...');

                try {
                    // 5초간 URL 변경 대기
                    await this.page.waitForFunction(
                        () => window.location.href.includes('OfrAction.do'),
                        { timeout: 10000 }
                    );
                    console.log('자동 리다이렉트 완료');
                } catch (waitError) {
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
                        console.log('폼 제출 실패. 다른 방법 시도...');
                        return [];
                    }
                }

                console.log(`최종 URL: ${this.page.url()}`);

                // 특정 페이지로 이동 (1페이지가 아닌 경우)
                if (pageNum > 1) {
                    console.log(`${pageNum} 페이지로 이동 중...`);

                    try {
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
                                    window.goPage();
                                    return true;
                                } else if (typeof window.search === 'function') {
                                    console.log('search 함수 실행');
                                    window.search();
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
                            await this.page.waitForTimeout(5000); // 페이지 로딩 대기
                        } else {
                            console.log('페이지 이동 실패');
                            return [];
                        }
                    } catch (error) {
                        console.log('페이지 이동 실패:', error.message);
                        return [];
                    }
                }

                // 페이지가 완전히 로드될 때까지 대기
                try {
                    await this.page.waitForSelector('table', { timeout: 10000 });
                } catch (error) {
                    console.log('테이블 로딩 대기 실패. 페이지 내용 확인...');

                    const pageContent = await this.page.content();
                    if (pageContent.includes('전체게시물') || pageContent.includes('공고')) {
                        console.log('페이지에 공고 관련 내용이 있지만 테이블이 다른 구조일 수 있음');
                    } else {
                        console.log('페이지에 공고 내용이 없음');
                        return [];
                    }
                }

                // 리스트 테이블에서 공고 추출
                const announcements = await this.page.evaluate(() => {
                    const results = [];

                    console.log('=== 청양군 공고 데이터 추출 ===');

                    // 모든 테이블을 확인
                    const tables = document.querySelectorAll('table');
                    console.log(`총 테이블 수: ${tables.length}`);

                    // 가장 큰 테이블에서 데이터 추출
                    let maxRowsTable = null;
                    let maxRows = 0;

                    tables.forEach((table, index) => {
                        const rows = table.querySelectorAll('tr');
                        console.log(`테이블 ${index}: ${rows.length}개 행`);

                        if (rows.length > maxRows) {
                            maxRows = rows.length;
                            maxRowsTable = table;
                        }
                    });

                    if (!maxRowsTable) {
                        console.log('유효한 테이블을 찾지 못함');
                        return [];
                    }

                    console.log(`가장 큰 테이블에서 데이터 추출: ${maxRows}개 행`);

                    // 선택된 테이블에서 모든 행 검사
                    const allRows = maxRowsTable.querySelectorAll('tr');

                    allRows.forEach((row, index) => {
                        const cells = row.querySelectorAll('td');

                        if (cells.length >= 5) {
                            // 각 셀의 텍스트 내용 확인
                            const cellTexts = Array.from(cells).map(cell => cell.textContent.trim());

                            // 숫자로 시작하는 행을 찾기 (공고 번호)
                            if (/^\d{4,}$/.test(cellTexts[0]) && cellTexts[2] && cellTexts[4]) {
                                const number = cellTexts[0];
                                const code = cellTexts[1];
                                const title = cellTexts[2];
                                const department = cellTexts[3];
                                const dateText = cellTexts[4];

                                // onclick 속성에서 관리번호 추출
                                const titleCell = cells[2];
                                const onclickAttr = titleCell.getAttribute('onclick') || '';
                                let detailMgtNo = '';

                                // searchDetail('34969') 형태에서 번호 추출
                                const onclickMatch = onclickAttr.match(/searchDetail\('(\d+)'\)/);
                                if (onclickMatch) {
                                    detailMgtNo = onclickMatch[1];
                                    console.log(`공고 발견 - ${number}: ${title} | 상세번호: ${detailMgtNo} | ${department} | ${dateText}`);
                                } else {
                                    console.log(`공고 발견 - ${number}: ${title} | onclick 없음 | ${department} | ${dateText}`);
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
                                    tableIndex: Array.from(tables).indexOf(maxRowsTable)
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
            if (this.processedTitles.has(announcement.title)) {
                console.log(`중복 게시물 스킵: ${announcement.title}`);
                return false;
            }

            // 3. 상세 페이지 내용 가져오기
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
                if (!announcement.detailMgtNo) {
                    console.log('상세 관리번호가 없어 상세 페이지 접근 불가');
                    return null;
                }

                // 매번 새로운 세션으로 상세 페이지 접근
                if (retries > 0) {
                    console.log(`재시도 ${retries}: 리스트 페이지 재로드로 세션 초기화`);
                    await this.page.goto(this.listUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
                    await this.page.waitForTimeout(2000);

                    // 자동 리다이렉트 대기
                    try {
                        await this.page.waitForFunction(
                            () => window.location.href.includes('OfrAction.do'),
                            { timeout: 10000 }
                        );
                    } catch { }
                    await this.page.waitForTimeout(2000);
                }

                console.log(`searchDetail('${announcement.detailMgtNo}') 함수로 상세 페이지 이동`);

                // searchDetail 함수를 사용하여 상세 페이지로 이동
                const navigated = await this.page.evaluate((detailMgtNo) => {
                    try {
                        console.log(`상세페이지 접근 시도: detailMgtNo=${detailMgtNo}`);

                        // 폼 확인
                        const forms = document.querySelectorAll('form');
                        console.log(`페이지의 폼 개수: ${forms.length}`);

                        let targetForm = null;
                        for (let form of forms) {
                            if (form.name === 'form1') {
                                targetForm = form;
                                console.log('form1 발견');
                                break;
                            } else if (form.name === 'form') {
                                targetForm = form;
                                console.log('form 발견');
                                break;
                            }
                        }

                        if (!targetForm && forms.length > 0) {
                            targetForm = forms[0];
                            console.log('기본 폼 사용');
                        }

                        // searchDetail 함수가 존재하는지 확인
                        if (typeof window.searchDetail === 'function') {
                            console.log('searchDetail 함수 발견, 실행 중...');
                            window.searchDetail(detailMgtNo);
                            return true;
                        } else {
                            console.log('searchDetail 함수가 없음. 수동으로 폼 제출 시도...');

                            // 수동으로 searchDetail 기능 구현
                            if (targetForm) {
                                // 폼 필드 설정
                                const mgtNoField = targetForm.querySelector('input[name="not_ancmt_mgt_no"]');
                                const methodField = targetForm.querySelector('input[name="method"]');
                                const methodNmField = targetForm.querySelector('input[name="methodnm"]');

                                if (mgtNoField) mgtNoField.value = detailMgtNo;
                                if (methodField) methodField.value = 'selectOfrNotAncmt';
                                if (methodNmField) methodNmField.value = 'selectOfrNotAncmtRegst';

                                targetForm.target = '_self';
                                targetForm.action = '/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do';

                                console.log('폼 제출 실행...');
                                targetForm.submit();
                                return true;
                            } else {
                                console.log('폼을 찾을 수 없음');
                                return false;
                            }
                        }
                    } catch (error) {
                        console.log('상세페이지 접근 오류:', error.message);
                        return false;
                    }
                }, announcement.detailMgtNo);

                if (!navigated) {
                    console.log('searchDetail 함수 실행 실패');
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
                        '.board-view',
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

                    // 날짜 추출
                    let dateText = '';
                    const dateSelectors = [
                        '.reg-date',
                        '.write-date',
                        '.post-date',
                        '[class*="date"]',
                        '[id*="date"]'
                    ];

                    for (const selector of dateSelectors) {
                        const dateElement = document.querySelector(selector);
                        if (dateElement) {
                            dateText = dateElement.textContent.trim();
                            if (dateText) break;
                        }
                    }

                    // 날짜를 못찾은 경우 본문에서 패턴으로 추출
                    if (!dateText) {
                        const datePattern = /등록일[:\s]*(\d{4}[-.\\/]\d{1,2}[-.\\/]\d{1,2})/;
                        const match = mainContent.match(datePattern);
                        if (match) {
                            dateText = match[1];
                        }
                    }

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

                    // 2. goDownLoad 패턴 (청양군 실제 사용 함수)
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
                    if (attachments.length > 0) {
                        console.log('첨부파일 목록:');
                        attachments.forEach((att, i) => {
                            console.log(`  ${i + 1}. ${att.name} (${att.type})`);
                        });
                    }

                    return {
                        content: mainContent.trim(),
                        dateText: dateText,
                        attachments: attachments
                    };
                });

                // 날짜 파싱
                const detailDate = this.extractDate(content.dateText);

                return {
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

            // 첨부파일 다운로드
            let attachmentFiles = [];
            let downloadUrlInfo = [];
            if (detailContent.attachments && detailContent.attachments.length > 0) {
                const downloadResult = await this.downloadAttachments(detailContent.attachments, folderPath);
                attachmentFiles = downloadResult.files || [];
                downloadUrlInfo = downloadResult.urlInfo || [];
            }

            // content.md 생성 및 첨부파일 정보 추가
            const contentMd = this.generateMarkdownContent(announcement, detailContent, downloadUrlInfo.length > 0 ? downloadUrlInfo : attachmentFiles);
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
        try {
            const attachDir = path.join(folderPath, 'attachments');
            await fs.ensureDir(attachDir);
            const downloadedFiles = [];
            const urlInfo = [];

            console.log(`${attachments.length}개 첨부파일 다운로드 중...`);

            for (let i = 0; i < attachments.length; i++) {
                const attachment = attachments[i];
                const result = await this.downloadSingleAttachment(attachment, attachDir, i + 1);
                if (result) {
                    if (typeof result === 'object' && result.fileName && result.downloadUrl) {
                        downloadedFiles.push(result.fileName);
                        urlInfo.push(result);
                    } else {
                        downloadedFiles.push(result);
                    }
                }
                await this.delay(500);
            }

            return { files: downloadedFiles, urlInfo: urlInfo };
        } catch (error) {
            console.error('첨부파일 다운로드 실패:', error);
            return { files: [], urlInfo: [] };
        }
    }

    /**
     * 단일 첨부파일 다운로드 (goDownLoad 함수 사용)
     */
    async downloadSingleAttachment(attachment, attachDir, index) {
        try {
            console.log(`첨부파일 다운로드 시작: ${attachment.name} (${attachment.type})`);

            let downloadUrl = attachment.href || attachment.onclick || '';

            if (attachment.type === 'goDownLoad' && attachment.userFileName) {
                // goDownLoad 함수 사용
                await this.downloadWithGoDownLoad(attachment, attachDir, index);
                downloadUrl = `goDownLoad('${attachment.userFileName}','${attachment.sysFileName}','${attachment.filePath}')`;
            } else if (attachment.onclick) {
                // 일반적인 onclick 함수 사용
                await this.downloadWithOnclick(attachment, attachDir, index);
                downloadUrl = attachment.onclick;
            } else if (attachment.href) {
                // 직접 링크 다운로드
                await this.downloadDirectLink(attachment, attachDir, index);
                downloadUrl = attachment.href;
            } else {
                console.log(`다운로드 방법을 찾을 수 없음: ${attachment.name}`);
                return null;
            }

            return { fileName: attachment.name, downloadUrl: downloadUrl };

        } catch (error) {
            console.error(`첨부파일 다운로드 실패 (${attachment.name}):`, error.message);
            return null;
        }
    }

    /**
     * goDownLoad 함수를 사용한 다운로드
     */
    async downloadWithGoDownLoad(attachment, attachDir, index) {
        try {
            console.log(`goDownLoad 함수로 다운로드: ${attachment.name}`);

            // Playwright의 다운로드 이벤트 설정 (더 긴 타임아웃)
            const downloadPromise = this.page.waitForEvent('download', { timeout: 60000 });

            // goDownLoad 함수 실행
            await this.page.evaluate((userFileName, sysFileName, filePath) => {
                if (typeof window.goDownLoad === 'function') {
                    window.goDownLoad(userFileName, sysFileName, filePath);
                } else {
                    console.error('goDownLoad 함수를 찾을 수 없음');
                    throw new Error('goDownLoad 함수를 찾을 수 없음');
                }
            }, attachment.userFileName, attachment.sysFileName, attachment.filePath);

            // 다운로드 완료 대기
            const download = await downloadPromise;

            // 파일명 정리
            const fileName = sanitize(attachment.name || `attachment_${index}`, { replacement: '_' });
            const filePath = path.join(attachDir, fileName);

            // 파일 저장
            await download.saveAs(filePath);

            console.log(`다운로드 완료: ${fileName}`);

        } catch (error) {
            console.error(`goDownLoad 함수 다운로드 실패: ${error.message}`);
            throw error;
        }
    }

    /**
     * onclick 함수를 사용한 다운로드
     */
    async downloadWithOnclick(attachment, attachDir, index) {
        try {
            // Playwright의 다운로드 이벤트 설정
            const downloadPromise = this.page.waitForEvent('download', { timeout: 30000 });

            // onclick 함수 실행
            await this.page.evaluate((onclick) => {
                eval(onclick);
            }, attachment.onclick);

            // 다운로드 완료 대기
            const download = await downloadPromise;

            // 파일명 정리
            const fileName = sanitize(attachment.name || `attachment_${index}`, { replacement: '_' });
            const filePath = path.join(attachDir, fileName);

            // 파일 저장
            await download.saveAs(filePath);

            console.log(`다운로드 완료: ${fileName}`);

        } catch (error) {
            console.error(`onclick 다운로드 실패: ${error.message}`);
            throw error;
        }
    }

    /**
     * 직접 링크로 다운로드
     */
    async downloadDirectLink(attachment, attachDir, index) {
        try {
            console.log(`직접 링크로 다운로드: ${attachment.name}`);

            // 직접 링크 클릭
            const downloadPromise = this.page.waitForEvent('download', { timeout: 30000 });

            await this.page.evaluate((href) => {
                const link = document.createElement('a');
                link.href = href;
                link.click();
            }, attachment.href);

            // 다운로드 완료 대기
            const download = await downloadPromise;

            // 파일명 정리
            const fileName = sanitize(attachment.name || `attachment_${index}`, { replacement: '_' });
            const filePath = path.join(attachDir, fileName);

            // 파일 저장
            await download.saveAs(filePath);

            console.log(`다운로드 완료: ${fileName}`);

        } catch (error) {
            console.error(`직접 링크 다운로드 실패: ${error.message}`);
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
            throw new Error(`직접 POST 다운로드 실패: ${error.message}`);
        }
    }

    /**
     * 마크다운 컨텐츠 생성
     */
    generateMarkdownContent(announcement, detailContent, attachmentFiles) {
        const lines = [];

        lines.push(`# ${announcement.title}`);
        lines.push('');
        lines.push(`**관리번호:** ${announcement.managementNo}`);
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

        if (attachmentFiles && attachmentFiles.length > 0) {
            lines.push('');
            lines.push('**첨부파일**:');
            lines.push('');
            attachmentFiles.forEach((file, i) => {
                if (typeof file === 'object' && file.fileName && file.downloadUrl) {
                    lines.push(`${i + 1}. ${file.fileName}:${file.downloadUrl}`);
                } else {
                    lines.push(`${i + 1}. ${file}`);
                }
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
                if (this.context) {
                    await this.context.close();
                }
                await this.browser.close();
                console.log('\n브라우저 정리 완료');
            } catch (error) {
                console.warn('브라우저 정리 중 오류:', error.message);
            }
        }

        console.log(`\n=== 청양군 이민원 스크래핑 완료 ===`);
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
            description: '대상 날짜 (YYYY-MM-DD 형식, year 대신 사용)',
            default: null
        })
        .option('output', {
            alias: 'o',
            type: 'string',
            description: '출력 디렉토리',
            default: 'scraped_data'
        })
        .help()
        .argv;
}

// 메인 실행
async function main() {
    const argv = setupCLI();

    const scraper = new CheongyangScraper({
        targetYear: argv.year,
        outputDir: argv.output
    });

    await scraper.scrape();
}

// 스크립트가 직접 실행될 때만 main 함수 호출
if (require.main === module) {
    main().catch(console.error);
}

module.exports = CheongyangScraper;