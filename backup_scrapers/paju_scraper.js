#!/usr/bin/env node

/**
 * 파주시 공고 스크래핑 시스템
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

const AnnouncementScraper = require('./announcement_scraper');
const yargs = require('yargs');
const moment = require('moment');

class PajuScraper extends AnnouncementScraper {
    constructor(options = {}) {
        const defaultOptions = {
            siteCode: 'paju',
            baseUrl: 'https://www.paju.go.kr/user/board/BD_board.list.do?bbsCd=1022&q_ctgCd=4063',
            listSelector: 'div.table table tbody tr',
            titleSelector: 'td:nth-child(2) a',
            dateSelector: 'td:nth-child(4)',  // 등록일
            paginationParam: 'q_currPage',
            dateFormat: 'YYYY/MM/DD',
            ...options
        };

        super(defaultOptions);
    }

    /**
     * 리스트 URL 구성
     */
    buildListUrl(pageNum) {
        const url = new URL(this.baseUrl);
        url.searchParams.set(this.options.paginationParam || 'q_currPage', pageNum);
        return url.toString();
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

                // moment 객체와 같은 직렬화 불가능한 객체 제외
                const { targetDate, ...safeOptions } = this.options;
                const evalOptions = { ...safeOptions, announcement }

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
                        'table.p-table', '.article-view', '.content_box', '.program--contents',
                        '.board_view', '#user_board_whole', '#contents'
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

                    const attachments = [];

                    const fileList = document.querySelector('ul.file-list');
                    const items = fileList.querySelectorAll('li');

                    items.forEach(item => {
                        const downloadLink = item.querySelector('a[href*="ND_fileDownload.do"]');
                        if (downloadLink) {
                            const fileName = downloadLink.textContent.trim();
                            const fileURL = downloadLink.href;

                            attachments.push({
                                name: fileName,
                                url: fileURL,
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
     * 상세 페이지 URL 구성
     */
    async buildDetailUrl(announcement) {
        console.log('URL 구성 중:', {
            link: announcement.link,
            onclick: announcement.onclick,
            dataAction: announcement.dataAction
        });

        // 1. JavaScript onclick이 있는 경우 (파주시는 주로 javascript:void(0) 사용)
        if (announcement.onclick) {
            //https://www.paju.go.kr/user/board/BD_board.view.do?seq=20250919165832678&bbsCd=1022&q_ctgCd=4063&q_parentCtgCd=&pageType=&showSummaryYn=N&delDesc=&q_searchKeyType=&q_searchVal=&q_startDt=&q_endDt=&q_currPage=1&q_sortName=&q_sortOrder=&q_rowPerPage=10&q_chooseCnt=10&q_rowPerPage_row=10

            console.log('onclick 분석 중:', announcement.onclick);

            const viewMatch = announcement.onclick.match(/jsView\(\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*\)/);


            if (viewMatch) {
                console.log("viewMatch", viewMatch)
                const seq = viewMatch[2];
                const bbsCd = viewMatch[1];
                let url = `https://www.paju.go.kr/user/board/BD_board.view.do?seq=${seq}&bbsCd=${bbsCd}&q_ctgCd=4063&q_parentCtgCd=&pageType=&showSummaryYn=N&delDesc=&q_searchKeyType=&q_searchVal=&q_startDt=&q_endDt=&q_currPage=1&q_sortName=&q_sortOrder=&q_rowPerPage=10&q_chooseCnt=10&q_rowPerPage_row=10`
                return url;
                // return `${baseUrl.protocol}//${baseUrl.host}/user/board/${viewUrl}`;
            }

        }

        // 2. 직접 링크가 있는 경우
        if (announcement.link && !announcement.link.startsWith('javascript:')) {
            // 절대 경로로 변환
            if (announcement.link.startsWith('/')) {
                const baseUrl = new URL(this.baseUrl);
                return `${baseUrl.protocol}//${baseUrl.host}${announcement.link}`;
            }
            // 상대 경로인 경우
            if (!announcement.link.startsWith('http')) {
                const baseUrl = new URL(this.baseUrl);
                const basePath = baseUrl.pathname.substring(0, baseUrl.pathname.lastIndexOf('/'));
                return `${baseUrl.protocol}//${baseUrl.host}${basePath}/${announcement.link}`;
            }
            return announcement.link;
        }

        console.log('상세 페이지 URL 구성 실패');
        return null;
    }
}

// CLI 실행
if (require.main === module) {

    const argv = yargs
        .option('year', {
            alias: 'y',
            description: '목표 연도',
            type: 'number',
            default: new Date().getFullYear()
        })
        .option('output', {
            alias: 'o',
            description: '출력 디렉토리',
            type: 'string',
            default: 'scraped_data'
        })
        .option('date', {
            alias: 'd',
            description: '특정 날짜까지만 수집 (YYYY-MM-DD)',
            type: 'string'
        })
        .option('page', {
            alias: 'p',
            description: '시작 페이지',
            type: 'number',
            default: 1
        })
        .help()
        .argv;

    const scraper = new PajuScraper({
        targetYear: argv.year,
        outputDir: argv.output,
        targetDate: argv.date ? moment(argv.date) : null,
        goPage: argv.page
    });

    scraper.scrape().catch(console.error);
}

module.exports = PajuScraper;