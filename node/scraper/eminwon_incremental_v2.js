#!/usr/bin/env node

/**
 * Eminwon 리스트 수집 전용 스크립트
 * eminwon_scraper.js의 리스트 수집 로직을 그대로 사용하되
 * 상세 페이지 다운로드는 제외
 */

const { chromium } = require('playwright');
const fs = require('fs-extra');
const path = require('path');
const yargs = require('yargs');

class EminwonListCollector {
    constructor(options = {}) {
        this.region = options.region;
        this.maxPages = options.pages || 3;

        // eminwon.json에서 호스트 정보 로드
        const eminwonHosts = JSON.parse(fs.readFileSync(path.join(__dirname, 'eminwon.json'), 'utf8'));

        if (!eminwonHosts[this.region]) {
            throw new Error(`지역 '${this.region}'에 대한 호스트 정보를 찾을 수 없습니다.`);
        }

        const hostUrl = eminwonHosts[this.region];
        this.baseUrl = `https://${hostUrl}`;
        // this.listUrl = `https://${hostUrl}/emwp/jsp/ofr/OfrNotAncmtL.jsp?not_ancmt_se_code=01,02,03,04,05&cpath=`;

        /* 2025-11-12에 확인 결과 not_ancmt_se_code=01,02,03,04,05,06으로 진행되는 부분이 있다. */
        //this.listUrl = `https://${hostUrl}/emwp/jsp/ofr/OfrNotAncmtL.jsp?not_ancmt_se_code=01,02,03,04,05&list_gubun=A`;

        this.listUrl = `https://${hostUrl}/emwp/jsp/ofr/OfrNotAncmtL.jsp?not_ancmt_se_code=01,02,03,04,05,06&list_gubun=A`;

        this.actionUrl = `https://${hostUrl}/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do`;

        this.browser = null;
        this.page = null;
        this.allAnnouncements = [];
    }

    async init() {
        this.browser = await chromium.launch({
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });

        const context = await this.browser.newContext({
            userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        });

        this.page = await context.newPage();
    }

    async delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    async processListPage(pageNum) {
        console.error(`\n--- 페이지 ${pageNum} 처리 중 ---`);
        console.error(`리스트 URL로 이동: ${this.listUrl}`);

        try {
            // eminwon_scraper.js의 로직 그대로 사용
            console.error('1단계: 초기 페이지 방문하여 세션 확보...');

            let initialLoadSuccess = false;
            let initialLoadAttempt = 0;
            const maxInitialLoadAttempts = 3;

            while (!initialLoadSuccess && initialLoadAttempt < maxInitialLoadAttempts) {
                initialLoadAttempt++;
                try {
                    console.error(`초기 페이지 로드 시도 ${initialLoadAttempt}/${maxInitialLoadAttempts}`);

                    await this.page.goto(this.listUrl, {
                        waitUntil: 'networkidle',
                        timeout: 45000
                    });

                    await this.page.waitForTimeout(4000);
                    initialLoadSuccess = true;

                } catch (error) {
                    console.error(`초기 페이지 로드 시도 ${initialLoadAttempt} 실패: ${error.message}`);

                    if (initialLoadAttempt < maxInitialLoadAttempts) {
                        console.error('잠시 대기 후 재시도...');
                        await this.delay(5000 * initialLoadAttempt);
                    }
                }
            }

            if (!initialLoadSuccess) {
                console.error('JSP URL 로드 실패. 서블릿 URL로 폴백 시도...');

                // 서블릿 URL로 직접 접근
                const servletUrl = `${this.actionUrl}?` +
                    `jndinm=OfrNotAncmtEJB&context=NTIS&method=selectList&` +
                    `methodnm=selectListOfrNotAncmt&homepage_pbs_yn=Y&subCheck=Y&` +
                    `ofr_pageSize=10&not_ancmt_se_code=01,02,03,04,05&title=고시공고&` +
                    `initValue=Y&countYn=Y&list_gubun=A&pageIndex=${pageNum}`;

                try {
                    console.error('서블릿 URL로 직접 접근:', servletUrl);
                    await this.page.goto(servletUrl, {
                        waitUntil: 'domcontentloaded',
                        timeout: 30000
                    });
                    await this.page.waitForTimeout(3000);
                    initialLoadSuccess = true;
                    console.error('서블릿 URL 접근 성공');
                } catch (servletError) {
                    console.error('서블릿 URL 접근도 실패:', servletError.message);
                    return [];
                }
            }

            console.error(`초기 페이지 URL: ${this.page.url()}`);

            // 리다이렉트 처리
            if (!this.page.url().includes('OfrAction.do')) {
                console.error('2단계: 자동 리다이렉트 대기...');

                try {
                    await this.page.waitForFunction(
                        () => window.location.href.includes('OfrAction.do'),
                        { timeout: 10000 }
                    );
                    console.error('자동 리다이렉트 완료');
                } catch (waitError) {
                    console.error('자동 리다이렉트 없음');
                }
            }

            // 페이지 네비게이션 (2페이지 이상)
            if (pageNum > 1) {
                console.error(`페이지 ${pageNum}로 이동 시도...`);

                const navigationSuccess = await this.page.evaluate((targetPage) => {
                    // goPage 함수 시도
                    if (typeof goPage === 'function') {
                        console.log(`goPage(${targetPage}) 호출`);
                        goPage(targetPage);
                        return true;
                    }

                    // fn_egov_link_page 함수 시도
                    if (typeof fn_egov_link_page === 'function') {
                        console.log(`fn_egov_link_page(${targetPage}) 호출`);
                        fn_egov_link_page(targetPage);
                        return true;
                    }

                    // 폼 제출 방식
                    const form = document.querySelector('form[action*="OfrAction.do"]');
                    if (form) {
                        const pageInput = form.querySelector('input[name="pageIndex"]');
                        if (pageInput) {
                            pageInput.value = targetPage;
                            form.submit();
                            return true;
                        }
                    }

                    return false;
                }, pageNum);

                if (navigationSuccess) {
                    await this.page.waitForTimeout(3000);
                }
            }

            // 공통 파싱 로직 사용
            const announcements = await this.extractAnnouncementsFromPage(pageNum);

            return announcements;

        } catch (error) {
            console.error(`페이지 ${pageNum} 처리 중 오류:`, error.message);
            return [];
        }
    }

    constructDetailUrl(announcementId) {
        const params = new URLSearchParams({
            'jndinm': 'OfrNotAncmtEJB',
            'context': 'NTIS',
            'method': 'selectOfrNotAncmt',
            'methodnm': 'selectOfrNotAncmtRegst',
            'not_ancmt_mgt_no': announcementId,
            'homepage_pbs_yn': 'Y',
            'subCheck': 'Y'
        });

        return `${this.actionUrl}?${params.toString()}`;
    }

    async navigateAndCollect(pageNum) {
        try {
            console.error(`--- 페이지 ${pageNum}로 네비게이션 ---`);

            // 현재 URL 저장 (변경 확인용)
            const currentUrl = this.page.url();

            // 페이지 이동 실행 (eminwon_scraper.js 방식)
            const navigationMethod = await this.page.evaluate((targetPage) => {
                try {
                    // 폼 찾기
                    let targetForm = null;
                    const forms = document.querySelectorAll('form');

                    for (let form of forms) {
                        if (form.name === 'form1' || form.name === 'form' ||
                            form.action.includes('OfrAction.do')) {
                            targetForm = form;
                            break;
                        }
                    }

                    if (!targetForm && forms.length > 0) {
                        targetForm = forms[0];
                    }

                    // pageIndex 설정 (중요!)
                    if (targetForm) {
                        const pageIndexField = targetForm.querySelector('input[name="pageIndex"]');
                        if (pageIndexField) {
                            pageIndexField.value = targetPage.toString();
                            console.log(`pageIndex를 ${targetPage}로 설정`);
                        }
                    }

                    // goPage 함수 시도 (파라미터 전달)
                    if (typeof goPage === 'function') {
                        console.log(`goPage(${targetPage}) 호출`);
                        goPage(targetPage);
                        return 'goPage';
                    }

                    // fn_egov_link_page 함수 시도
                    if (typeof fn_egov_link_page === 'function') {
                        console.log(`fn_egov_link_page(${targetPage}) 호출`);
                        fn_egov_link_page(targetPage);
                        return 'fn_egov_link_page';
                    }

                    // linkPage 함수 시도
                    if (typeof linkPage === 'function') {
                        console.log(`linkPage(${targetPage}) 호출`);
                        linkPage(targetPage);
                        return 'linkPage';
                    }

                    // search 함수 시도 (pageIndex 설정 후)
                    if (typeof search === 'function') {
                        console.log('search() 함수 호출');
                        search();
                        return 'search';
                    }

                    // 직접 폼 제출
                    if (targetForm) {
                        console.log('직접 폼 제출');
                        targetForm.submit();
                        return 'form_submit';
                    }
                } catch (error) {
                    console.log('페이징 처리 오류:', error.message);
                }

                // 페이지 번호 링크 직접 클릭
                const pageLinks = document.querySelectorAll('a');
                for (const link of pageLinks) {
                    if (link.textContent.trim() === String(targetPage)) {
                        link.click();
                        return 'direct_click';
                    }
                }

                return false;
            }, pageNum);

            console.error(`네비게이션 방법: ${navigationMethod}`);

            if (navigationMethod) {
                // 네비게이션 대기 또는 URL 변경 대기
                try {
                    await this.page.waitForNavigation({
                        waitUntil: 'networkidle',
                        timeout: 10000
                    });
                } catch (navError) {
                    // 네비게이션이 없는 경우 URL 변경 또는 컨텐츠 변경 대기
                    console.error('네비게이션 대기 실패, URL 변경 확인...');
                    await this.page.waitForFunction(
                        (oldUrl, targetPage) => {
                            // URL에 pageIndex가 포함되었는지 확인
                            return window.location.href.includes(`pageIndex=${targetPage}`) ||
                                window.location.href !== oldUrl;
                        },
                        { timeout: 5000 },
                        currentUrl,
                        pageNum
                    ).catch(() => { });
                }

                // 추가 대기
                await this.page.waitForTimeout(2000);
            } else {
                console.error('페이지 이동 방법을 찾을 수 없음');
            }

            // processListPage의 파싱 로직 재사용 (지역별 설정 포함)
            const announcements = await this.extractAnnouncementsFromPage(pageNum);

            return announcements;

        } catch (error) {
            console.error(`페이지 ${pageNum} 네비게이션 중 오류:`, error.message);
            return [];
        }
    }

    async extractAnnouncementsFromPage(pageNum) {
        // processListPage의 파싱 로직을 추출하여 재사용
        const announcements = await this.page.evaluate((regionName) => {
            const selectorInfo = {
                "울산북구": { "table": ".cont_table", "titleIndex": 2, "dateIndex": 4 },
                "부산중구": { "table": ".bbs_ltype", "titleIndex": 1, "dateIndex": 3 },
                "부산강서구": { "table": ".tb_board", "titleIndex": 1, "dateIndex": 3 },
                "평창군": { "table": ".tb_board", "titleIndex": 3, "dateIndex": 7 },
                "해운대구": { "table": ".tstyle_list", "titleIndex": 1, "dateIndex": 3 },
                "수영구": { "table": ".list01", "titleIndex": 1, "dateIndex": 3 },
                "부산진구": { "table": ".board-list-wrap table", "titleIndex": 1, "dateIndex": 3 },
                "부산서구": { "table": ".board-list-wrap table", "titleIndex": 1, "dateIndex": 3 },
                "광주동구": { "table": ".dbody", "rowSelector": "ul", "cellSelector": "li", "titleIndex": 2, "dateIndex": 4 },
                "울산남구": { "table": ".basic_table", "titleIndex": 1, "dateIndex": 3 },
                "울산동구": { "table": ".bbs_list", "titleIndex": 1, "dateIndex": 3 },
                "연수구": { "table": ".general_board", "titleIndex": 1, "dateIndex": 3 }
            };

            let targetTableClass = ".target";
            let titleIndex = 2;
            let dateIndex = 4;

            if (selectorInfo[regionName]) {
                targetTableClass = selectorInfo[regionName].table;
                titleIndex = selectorInfo[regionName].titleIndex;
                dateIndex = selectorInfo[regionName].dateIndex;
            }

            let targetTable = document.querySelector(targetTableClass);
            if (!targetTable) {
                const tables = document.querySelectorAll('table');
                let maxRows = 0;
                tables.forEach((table) => {
                    const rows = table.querySelectorAll('tr');
                    if (rows.length > maxRows) {
                        maxRows = rows.length;
                        targetTable = table;
                    }
                });
                if (!targetTable) return [];
            }

            let rowSelector = "tr";
            if (selectorInfo[regionName] && selectorInfo[regionName].rowSelector) {
                rowSelector = selectorInfo[regionName].rowSelector;
            }

            const allRows = targetTable.querySelectorAll(rowSelector);
            const results = [];

            allRows.forEach((row) => {
                let cellSelector = 'td, th';
                if (selectorInfo[regionName] && selectorInfo[regionName].cellSelector) {
                    cellSelector = selectorInfo[regionName].cellSelector;
                }

                const cells = row.querySelectorAll(cellSelector);

                if (cells.length >= 3) {
                    const cellTexts = Array.from(cells).map(cell => cell.textContent.trim());

                    let title = cellTexts[titleIndex] || '';
                    let dateText = '';

                    // 날짜 추출 - 수정된 로직
                    if (cellTexts[dateIndex]) {
                        if (/\d{4}[-.]\d{2}[-.]\d{2}/.test(cellTexts[dateIndex])) {
                            dateText = cellTexts[dateIndex].match(/\d{4}[-.]\d{2}[-.]\d{2}/)[0].replace(/\./g, '-');
                        }
                    }

                    if (!dateText) {
                        if (cellTexts[3] && /\d{4}[-.]\d{2}[-.]\d{2}/.test(cellTexts[3])) {
                            dateText = cellTexts[3].match(/\d{4}[-.]\d{2}[-.]\d{2}/)[0].replace(/\./g, '-');
                        } else if (cellTexts[4] && /\d{4}[-.]\d{2}[-.]\d{2}/.test(cellTexts[4])) {
                            dateText = cellTexts[4].match(/\d{4}[-.]\d{2}[-.]\d{2}/)[0].replace(/\./g, '-');
                        } else {
                            for (let i = 2; i < cellTexts.length; i++) {
                                if (/\d{4}[-.]\d{2}[-.]\d{2}/.test(cellTexts[i])) {
                                    dateText = cellTexts[i].match(/\d{4}[-.]\d{2}[-.]\d{2}/)[0].replace(/\./g, '-');
                                    break;
                                }
                            }
                        }
                    }

                    const hasNumber = /^\d{1,}$/.test(cellTexts[0]);

                    if (dateText && title && (hasNumber || cells.length >= 5)) {
                        const titleCell = cells[titleIndex] || cells[2];
                        let detailMgtNo = '';

                        const titleLink = titleCell.querySelector('a');
                        let onclickAttr = '';

                        if (titleLink) {
                            onclickAttr = titleLink.getAttribute('onclick') || '';
                        }

                        if (!onclickAttr) {
                            onclickAttr = titleCell.getAttribute('onclick') || '';
                        }

                        const patterns = [
                            /searchDetail\('(\d+)'\)/,
                            /searchDetail\((\d+)\)/,
                            /searchDetail\('([^']+)'\)/,
                            /searchDetail\("(\d+)"\)/,
                            /viewDetail\('(\d+)'\)/,
                            /viewDetail\((\d+)\)/,
                            /goDetail\('(\d+)'\)/,
                            /goDetail\((\d+)\)/,
                            /\('(\d+)'\)/,
                            /\((\d+)\)/
                        ];

                        for (const pattern of patterns) {
                            const match = onclickAttr.match(pattern);
                            if (match) {
                                detailMgtNo = match[1];
                                break;
                            }
                        }

                        if (detailMgtNo) {
                            results.push({
                                id: detailMgtNo,
                                title: title.replace(/\[.*?\]/g, '').trim(),
                                date: dateText,
                                department: cellTexts[3] || ''
                            });
                        }
                    }
                }
            });

            return results;
        }, this.region);

        console.error(`페이지 ${pageNum}에서 ${announcements.length}개 공고 발견`);

        announcements.forEach(ann => {
            ann.url = this.constructDetailUrl(ann.id);
            console.error(`  - ${ann.id}: ${ann.title.substring(0, 50)}...`);
        });

        return announcements;
    }

    async run() {
        try {
            await this.init();

            console.error(`=== ${this.region} 리스트 수집 시작 ===`);
            console.error(`최대 ${this.maxPages} 페이지 수집`);

            // 첫 페이지는 항상 초기 로드
            const firstPageAnnouncements = await this.processListPage(1);
            this.allAnnouncements.push(...firstPageAnnouncements);

            // 2페이지 이상은 같은 페이지에서 네비게이션
            if (this.maxPages > 1 && firstPageAnnouncements.length > 0) {
                for (let pageNum = 2; pageNum <= this.maxPages; pageNum++) {
                    await this.delay(2000);

                    // 현재 페이지에서 직접 네비게이션
                    const pageAnnouncements = await this.navigateAndCollect(pageNum);
                    if (pageAnnouncements.length === 0) {
                        console.error(`페이지 ${pageNum}에 더 이상 공고가 없습니다.`);
                        break;
                    }
                    this.allAnnouncements.push(...pageAnnouncements);
                }
            }

            console.error(`\n✅ 총 ${this.allAnnouncements.length}개 공고 수집 완료`);

            // 디버깅: 수집된 공고 제목 상세 출력
            console.error('\n=== 수집된 공고 목록 (디버깅) ===');
            this.allAnnouncements.forEach((ann, index) => {
                console.error(`${(index + 1).toString().padStart(3, ' ')}. [${ann.id}] ${ann.title} (${ann.date})`);
            });
            console.error('===================================\n');

            // JSON으로 출력 (Python에서 파싱용)
            console.log(JSON.stringify({
                status: 'success',
                region: this.region,
                count: this.allAnnouncements.length,
                data: this.allAnnouncements
            }, null, 2));

        } catch (error) {
            console.error('수집 중 오류:', error);
            console.log(JSON.stringify({
                status: 'error',
                region: this.region,
                error: error.message,
                data: []
            }));
        } finally {
            if (this.browser) {
                await this.browser.close();
            }
        }
    }
}

// CLI 인터페이스
const argv = yargs
    .option('region', {
        alias: 'r',
        description: '수집할 지역명',
        type: 'string',
        demandOption: true
    })
    .option('pages', {
        alias: 'p',
        description: '수집할 페이지 수',
        type: 'number',
        default: 3
    })
    .help()
    .argv;

// 실행
const collector = new EminwonListCollector({
    region: argv.region,
    pages: argv.pages
});

collector.run();