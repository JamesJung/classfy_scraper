#!/usr/bin/env node

/**
 * 오산시 공고 스크래핑 시스템
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

class OsanScraper extends AnnouncementScraper {
    constructor(options = {}) {
        const defaultOptions = {
            siteCode: 'osan',
            baseUrl: 'https://www.osan.go.kr/portal/saeol/gosi/list.do?mId=0302010000',
            listSelector: 'table.bod_list tbody tr',
            titleSelector: 'td.list_tit a',
            dateSelector: 'td.list_date',
            paginationParam: 'page',
            dateFormat: 'YYYY-MM-DD',
            ...options
        };

        super(defaultOptions);
    }

    /**
     * 리스트 URL 구성
     */
    buildListUrl(pageNum) {
        const url = new URL(this.baseUrl);
        url.searchParams.set(this.options.paginationParam || 'pageIndex', pageNum);
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
                        'table.p-table', '.bod_wrap', '.content_box', '.program--contents',
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

                    const fileLinks = document.querySelectorAll('#updateFileList li');
                    const results = [];

                    fileLinks.forEach(link => {
                        const anchor = link.querySelector('a');

                        if (anchor) {
                            // Extract the file name from the <span> tag
                            const fileName = anchor.querySelector('span').textContent.trim();
                            // Extract the full onclick attribute as the link
                            const downloadClick = anchor.getAttribute('onclick');
                            const downloadLink = anchor.href;

                            attachments.push({
                                name: fileName,
                                url: downloadLink,
                                onclick: downloadClick
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

        // 1. 직접 링크가 있는 경우
        // if (announcement.link && !announcement.link.startsWith('javascript:')) {
        //     // 절대 경로로 변환
        //     if (announcement.link.startsWith('/')) {
        //         const baseUrl = new URL(this.baseUrl);
        //         return `${baseUrl.protocol}//${baseUrl.host}${announcement.link}`;
        //     }
        //     // 상대 경로인 경우
        //     if (!announcement.link.startsWith('http')) {
        //         const baseUrl = new URL(this.baseUrl);
        //         const basePath = baseUrl.pathname.substring(0, baseUrl.pathname.lastIndexOf('/'));
        //         return `${baseUrl.protocol}//${baseUrl.host}${basePath}/${announcement.link}`;
        //     }
        //     return announcement.link;
        // }

        // // 2. JavaScript onclick이 있는 경우
        // if (announcement.onclick) {
        //     console.log('onclick 분석 중:', announcement.onclick);

        //     // view.do?seq=12345 패턴
        //     const viewMatch = announcement.onclick.match(/location\.href\s*=\s*['"]([^'"]+)['"]/);
        //     if (viewMatch) {
        //         const viewUrl = viewMatch[1];
        //         const baseUrl = new URL(this.baseUrl);
        //         const basePath = baseUrl.pathname.substring(0, baseUrl.pathname.lastIndexOf('/'));
        //         return `${baseUrl.protocol}//${baseUrl.host}${basePath}/${viewUrl}`;
        //     }
        // }

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

    const scraper = new OsanScraper({
        targetYear: argv.year,
        outputDir: argv.output,
        targetDate: argv.date ? moment(argv.date) : null,
        goPage: argv.page
    });

    scraper.scrape().catch(console.error);
}

module.exports = OsanScraper;