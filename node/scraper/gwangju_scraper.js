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
const FailureLogger = require('./failure_logger');
const UrlManager = require('./url_manager');

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
        
        // 제목 비교를 위한 변수
        this.lastProcessedTitle = null;
        this.processedTitles = new Set();
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
     * 리스트 URL 구성 - Gwangju는 iframe에서 직접 처리
     */
    buildListUrl(pageNum) {
        return `${this.baseUrl}&currPageNo=${pageNum}`;
    }
    
    /**
     * 공고 처리 - 제목 중복 체크 제거 (부모 클래스에서 처리)
     */
    async processAnnouncement(announcement) {
        // 부모 클래스의 processAnnouncement가 중복 체크를 포함하므로
        // 여기서는 추가 중복 체크를 하지 않음
        return super.processAnnouncement(announcement);
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
     * 날짜 추출 - Gwangju 특화
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

    const scraper = new GwangjuScraper({
        targetDate: argv.date,
        goPage: argv.goPage,
        outputDir: argv.output
    });

    scraper.scrape().catch(console.error);
}

module.exports = GwangjuScraper;