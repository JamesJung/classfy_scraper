#!/usr/bin/env node

/**
 * Gwangju 공고 스크래핑 시스템
 * 
 * 기능:
 * 1. 날짜 기반 필터링
 * 2. iframe 기반 리스트 -> 상세 페이지 처리
 * 3. content.md 파일 생성
 * 4. 첨부파일 다운로드
 * 5. 중복 게시물 스킵
 */

const AnnouncementScraper = require('./announcement_scraper');
const moment = require('moment');

class GwangjuScraper extends AnnouncementScraper {
    constructor(options = {}) {
        super({
            ...options,
            baseUrl: options.baseUrl || 'https://sido.gwangju.go.kr/citynet/jsp/sap/SAPGosiBizProcess.do?command=searchList&flag=gosiGL&svp=Y',
            listSelector: 'tbody tr',
            titleSelector: 'td:nth-child(2)',  // Title is in 2nd column
            dateSelector: 'td:nth-child(4)',   // Date is in 4th column
            siteCode: 'gwangju',
            ...options
        });
    }

    /**
     * 리스트 URL 구성 - Gwangju는 iframe에서 직접 처리
     */
    buildListUrl(pageNum) {
        return `${this.baseUrl}&currPageNo=${pageNum}`;
    }

    /**
     * 공고 리스트 가져오기 - Gwangju 특화 (iframe 직접 접근)
     */
    async getAnnouncementList(pageNum) {
        const maxRetries = 3;
        let retries = 0;

        while (retries < maxRetries) {
            try {
                console.log(`리스트 페이지 ${pageNum} 로딩 중...`);

                // 브라우저나 페이지가 종료된 경우 재초기화
                if (!this.browser || !this.page || this.page.isClosed()) {
                    console.log('브라우저 연결이 끊어져 재초기화합니다...');
                    await this.initBrowser();
                }

                // iframe URL에 직접 접근
                const listUrl = this.buildListUrl(pageNum);
                console.log(`iframe URL로 직접 이동: ${listUrl}`);
                await this.page.goto(listUrl, {
                    waitUntil: 'domcontentloaded',
                    timeout: 30000
                });

                // 페이지 데이터 로드 대기
                await this.page.waitForTimeout(3000);

                // 리스트 요소들 추출 - Gwangju 특화
                const announcements = await this.page.evaluate(() => {
                    const rows = document.querySelectorAll('tbody tr, table tr');
                    const results = [];

                    rows.forEach((row) => {
                        const cells = row.querySelectorAll('td');
                        if (cells.length < 4) return; // 충분한 셀이 없으면 스킵

                        // 헤더 행 스킵
                        if (row.querySelector('th')) return;

                        // 번호, 제목, 담당부서, 게재일자, 조회수 순서
                        const numberCell = cells[0];
                        const titleCell = cells[1];
                        const departmentCell = cells[2];
                        const dateCell = cells[3];

                        const title = titleCell ? titleCell.textContent.trim() : '';
                        const department = departmentCell ? departmentCell.textContent.trim() : '';
                        const dateText = dateCell ? dateCell.textContent.trim() : '';
                        const number = numberCell ? numberCell.textContent.trim() : '';

                        // 유효한 공고인지 확인 (제목이 충분히 길고 날짜가 있는지)
                        if (title.length > 5 && dateText && number) {
                            // viewData 함수의 내부 ID 추출
                            const rowOnclick = row.getAttribute('onclick');
                            let internalId = null;
                            let dataType = null;

                            if (rowOnclick && rowOnclick.includes('viewData')) {
                                // onclick="viewData('34782','A')" 형식에서 ID 추출
                                const match = rowOnclick.match(/viewData\('([^']+)','([^']+)'\)/);
                                if (match) {
                                    internalId = match[1];
                                    dataType = match[2];
                                }
                            }

                            results.push({
                                title,
                                dateText,
                                department,
                                number,
                                listDate: dateText,
                                internalId: internalId,
                                dataType: dataType
                            });
                        }
                    });

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

                // 재시도 전 대기
                await this.delay(2000 * retries);
            }
        }
    }

    /**
     * 상세 페이지 내용 가져오기 - Gwangju 특화
     */
    async getDetailContent(announcement) {
        const maxRetries = 3;
        let retries = 0;

        while (retries < maxRetries) {
            try {
                console.log(`상세 페이지 이동: ${announcement.title}`);

                // 브라우저나 페이지가 종료된 경우 재초기화
                if (!this.browser || !this.page || this.page.isClosed()) {
                    console.log('브라우저 연결이 끊어져 재초기화합니다...');
                    await this.initBrowser();
                }

                // 내부 ID를 사용해서 상세 페이지 URL로 이동
                if (announcement.internalId) {
                    const detailUrl = `https://sido.gwangju.go.kr/citynet/jsp/sap/SAPGosiBizProcess.do?command=searchDetail&flag=gosiGL&svp=Y&sido=&sno=${announcement.internalId}&gosiGbn=%EA%B3%B5%EA%B3%A0`;

                    console.log(`내부 ID(${announcement.internalId})로 상세 페이지 이동: ${detailUrl}`);
                    await this.page.goto(detailUrl, {
                        waitUntil: 'domcontentloaded',
                        timeout: 30000
                    });

                    // 페이지 로드 대기
                    await this.page.waitForTimeout(3000);
                } else {
                    console.log(`내부 ID를 찾을 수 없음 (${announcement.number}): viewData 파라미터가 없습니다`);
                    return null;
                }

                // 페이지 내용 추출 - Gwangju 특화
                const content = await this.page.evaluate(() => {
                    // 본문 추출
                    let mainContent = null;

                    // Gwangju 사이트의 콘텐츠 선택자
                    const contentSelectors = [
                        '.view_content',       // 본문 영역
                        '.board_view',         // 게시판 뷰
                        '#content',            // 콘텐츠
                        'table.view',          // 테이블 뷰
                        '.detail',             // 상세
                        'td.content'           // 내용 셀
                    ];

                    for (const selector of contentSelectors) {
                        const element = document.querySelector(selector);
                        if (element) {
                            mainContent = element;
                            break;
                        }
                    }

                    // 못 찾으면 전체 body 사용
                    if (!mainContent) {
                        mainContent = document.body;
                    }

                    // 불필요한 요소 제거
                    const excludeSelectors = [
                        'header', 'nav', 'aside', 'footer',
                        '.header', '.nav', '.sidebar', '.footer',
                        '.menu', '.navigation', '.breadcrumb',
                        '.btn_area', '.button_area',
                        'script', 'style'  // JavaScript/CSS 제거
                    ];

                    const tempContent = mainContent.cloneNode(true);
                    excludeSelectors.forEach(selector => {
                        const elements = tempContent.querySelectorAll(selector);
                        elements.forEach(el => el.remove());
                    });

                    // 날짜 추출
                    let dateText = '';

                    // 테이블에서 게재일 찾기
                    const rows = document.querySelectorAll('tr');
                    for (const row of rows) {
                        const th = row.querySelector('th');
                        if (th && (th.textContent.includes('게재일') || th.textContent.includes('등록일'))) {
                            const td = row.querySelector('td');
                            if (td) {
                                dateText = td.textContent.trim();
                                break;
                            }
                        }
                    }

                    // 첨부파일 추출
                    const attachments = [];

                    // 다운로드 링크 찾기
                    const fileLinks = document.querySelectorAll('a[href*="download"], a[onclick*="download"], a[href*="FileDown"]');

                    fileLinks.forEach(link => {
                        const fileName = link.textContent.trim();
                        const href = link.href;
                        const onclick = link.getAttribute('onclick');

                        if (fileName && (href || onclick)) {
                            attachments.push({
                                name: fileName,
                                url: href,
                                onclick: onclick
                            });
                        }
                    });

                    // 텍스트만 추출
                    const textContent = tempContent.innerText || tempContent.textContent || '';

                    return {
                        content: textContent.trim(),
                        dateText: dateText,
                        attachments: attachments,
                        url: window.location.href
                    };
                });

                // 날짜 파싱
                const detailDate = this.extractDate(content.dateText || announcement.dateText);

                return {
                    url: content.url,
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
     * 날짜 추출 - Gwangju 특화
     */
    extractDate(dateText) {
        if (!dateText) return null;

        // 텍스트 정리
        let cleanText = dateText.trim();

        // "2025-09-19" 또는 "2025.09.19" 같은 형식 추출
        const dateMatch = cleanText.match(/(\d{4}[-.\\/]\d{1,2}[-.\\/]\d{1,2})/);
        if (dateMatch) {
            cleanText = dateMatch[1];
        }

        // 다양한 날짜 형식 시도
        const formats = [
            'YYYY-MM-DD',
            'YYYY.MM.DD',
            'YYYY/MM/DD',
            'YY-MM-DD',
            'YY.MM.DD'
        ];

        for (const format of formats) {
            const date = moment(cleanText, format, true);
            if (date.isValid()) {
                return date;
            }
        }

        return null;
    }

    /**
     * 상세 페이지 URL 구성 - Gwangju는 viewData 함수 사용
     */
    async buildDetailUrl(announcement) {
        // Gwangju는 viewData 함수를 사용하므로 URL 구성 불필요
        return null;
    }
}

// CLI 실행
if (require.main === module) {
    const yargs = require('yargs');

    const argv = yargs
        .option('date', {
            alias: 'd',
            type: 'string',
            description: '대상 날짜 (YYYY-MM-DD 형식)',
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
        .help()
        .argv;

    const scraper = new GwangjuScraper({
        targetDate: argv.date,
        goPage: argv.goPage,
        outputDir: argv.output
    });

    scraper.scrape().catch(console.error);
}

module.exports = GwangjuScraper;