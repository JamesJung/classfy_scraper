#!/usr/bin/env node

/**
 * Daegu 공고 스크래핑 시스템
 * 
 * 기능:
 * 1. 날짜 기반 필터링
 * 2. fn_goLinkView 함수를 통한 상세 페이지 접근
 * 3. content.md 파일 생성
 * 4. fn_egov_downFile 방식 첨부파일 다운로드
 * 5. 중복 게시물 스킵
 */

const AnnouncementScraper = require('./announcement_scraper');
const moment = require('moment');
const path = require('path');
const fs = require('fs-extra');
const FailureLogger = require('./failure_logger');
const UrlManager = require('./url_manager');

class DaeguScraper extends AnnouncementScraper {
    constructor(options = {}) {
        super({
            ...options,
            baseUrl: options.baseUrl || 'https://www.daegu.go.kr/index.do?menu_id=00940170',
            listSelector: 'table.gosi tbody tr',
            titleSelector: 'td:nth-child(2) a',
            dateSelector: 'td:nth-child(4)',
            siteCode: 'daegu',
            ...options
        });
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
     * 리스트 URL 구성 - Daegu 페이지네이션
     */
    buildListUrl(pageNum) {
        const url = new URL(this.baseUrl);
        if (pageNum > 1) {
            url.searchParams.set('pageIndex', pageNum);
        }
        return url.toString();
    }

    /**
     * 공고 리스트 가져오기 - Daegu 특화
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

                // 페이지 로딩 대기
                await this.page.waitForTimeout(3000);

                // 테이블이 로드될 때까지 대기
                try {
                    await this.page.waitForSelector('table.gosi tbody tr', {
                        timeout: 5000
                    });
                } catch (e) {
                    console.log('공고 테이블을 찾을 수 없습니다.');
                }

                // 리스트 요소들 추출 - Daegu 특화
                const announcements = await this.page.evaluate(() => {
                    const rows = document.querySelectorAll('table.gosi tbody tr');
                    const results = [];

                    rows.forEach((row) => {
                        // 헤더 행이나 빈 행 스킵
                        if (row.querySelector('th') || !row.querySelector('td')) return;

                        const cells = row.querySelectorAll('td');
                        if (cells.length < 4) return; // 충분한 셀이 없으면 스킵

                        // 번호, 제목, 접수기관, 등록일 순서
                        const numberCell = cells[0];
                        const titleCell = cells[1];
                        const organizationCell = cells[2];
                        const dateCell = cells[3];

                        const titleLink = titleCell ? titleCell.querySelector('a') : null;
                        if (!titleLink) return;

                        const title = titleLink.textContent.trim();
                        const href = titleLink.href;

                        // fn_goLinkView 함수의 파라미터 추출
                        let sno = null;
                        let gosiGbn = null;

                        if (href && href.includes('fn_goLinkView')) {
                            const match = href.match(/fn_goLinkView\s*\(\s*['"]?(\d+)['"]?\s*,\s*['"]?([A-Z])['"]?\s*\)/);
                            if (match) {
                                sno = match[1];
                                gosiGbn = match[2];
                            }
                        }

                        const organization = organizationCell ? organizationCell.textContent.trim() : '';
                        const dateText = dateCell ? dateCell.textContent.trim() : '';

                        if (title && sno && gosiGbn) {
                            results.push({
                                title,
                                dateText,
                                organization,
                                sno,
                                gosiGbn,
                                listDate: dateText
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
     * 상세 페이지 내용 가져오기 - Daegu 특화
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

                // 직접 URL로 이동 시도
                const detailUrl = `https://www.daegu.go.kr/index.do?menu_id=00940170&menu_link=/front/daeguSidoGosi/daeguSidoGosiView.do&sno=${announcement.sno}&gosi_gbn=${announcement.gosiGbn}`;
                console.log(`상세 페이지 URL: ${detailUrl}`);
                
                try {
                    // 직접 URL 이동
                    await this.page.goto(detailUrl, { waitUntil: 'networkidle' });
                } catch (navError) {
                    // 실패 공고 DB 기록
                    await FailureLogger.logFailedAnnouncement({
                        site_code: this.siteCode,
                        title: announcement?.title || 'Unknown',
                        url: announcement?.link || announcement?.url,
                        detail_url: announcement?.detailUrl,
                        error_type: 'navError',
                        error_message: navError.message
                    }).catch(logErr => {});

                    console.log('직접 URL 이동 실패, JavaScript 방식 시도...');
                    
                    // 기존 방식으로 폴백
                    await this.page.evaluate(({ sno, gosiGbn }) => {
                        // fn_goLinkView 함수가 있으면 호출
                        if (typeof fn_goLinkView === 'function') {
                            fn_goLinkView(sno, gosiGbn);
                        } else {
                            // 함수가 없으면 폼 제출 방식 시도
                            const form = document.getElementById('sidoGosiAPIVO');
                            if (form) {
                                // hidden input 설정
                                const snoInput = form.querySelector('input[name="sno"]') || document.createElement('input');
                                snoInput.type = 'hidden';
                                snoInput.name = 'sno';
                                snoInput.value = sno;
                                if (!form.contains(snoInput)) form.appendChild(snoInput);

                                const gosiGbnInput = form.querySelector('input[name="gosi_gbn"]') || document.createElement('input');
                                gosiGbnInput.type = 'hidden';
                                gosiGbnInput.name = 'gosi_gbn';
                                gosiGbnInput.value = gosiGbn;
                                if (!form.contains(gosiGbnInput)) form.appendChild(gosiGbnInput);

                                // action 설정
                                form.action = '?menu_id=00940170&menu_link=/front/daeguSidoGosi/daeguSidoGosiView.do';
                                form.submit();
                            }
                        }
                    }, { sno: announcement.sno, gosiGbn: announcement.gosiGbn });
                }

                // 페이지 로드 대기
                await this.page.waitForLoadState('networkidle');
                await this.page.waitForTimeout(2000);

                // 현재 URL 확인 - 오류 페이지인지 체크
                const currentUrl = this.page.url();
                console.log(`현재 URL: ${currentUrl}`);
                
                if (currentUrl.startsWith('chrome-error://') || currentUrl.includes('error')) {
                    console.log('페이지 로드 실패 - 오류 페이지 감지');
                    // 리스트로 돌아가기
                    await this.page.goBack();
                    await this.page.waitForTimeout(1000);
                    return null;
                }

                // 페이지 내용 추출 - Daegu 특화
                const content = await this.page.evaluate(() => {
                    // 본문 추출
                    let mainContent = null;

                    // Daegu 사이트의 콘텐츠 선택자
                    const contentSelectors = [
                        '#bbsView',            // 메인 콘텐츠
                        '.view_content',       // 본문 영역
                        '.board_view',         // 게시판 뷰
                        '.detail',             // 상세
                        'td.content'           // 내용 셀
                    ];

                    for (const selector of contentSelectors) {
                        const element = document.querySelector(selector);
                        if (element && element.textContent.trim().length > 100) {
                            mainContent = element;
                            break;
                        }
                    }

                    // 못 찾으면 전체 body 사용
                    if (!mainContent) {
                        mainContent = document.body;
                    }

                    // mainContent가 여전히 null이면 빈 객체 반환
                    if (!mainContent) {
                        return {
                            content: '',
                            dateText: '',
                            attachments: [],
                            url: window.location.href
                        };
                    }

                    // 불필요한 요소 제거
                    const excludeSelectors = [
                        'header', 'nav', 'aside', 'footer',
                        '.header', '.nav', '.sidebar', '.footer',
                        '.menu', '.navigation', '.breadcrumb',
                        '.btn_area', '.button_area',
                        'script', 'style'  // 스크립트와 스타일 태그도 제거
                    ];

                    const tempContent = mainContent.cloneNode(true);
                    excludeSelectors.forEach(selector => {
                        const elements = tempContent.querySelectorAll(selector);
                        elements.forEach(el => el.remove());
                    });

                    // 날짜 추출
                    let dateText = '';

                    // 테이블에서 등록일 찾기
                    const rows = document.querySelectorAll('tr');
                    for (const row of rows) {
                        const th = row.querySelector('th');
                        if (th && (th.textContent.includes('등록일') || th.textContent.includes('작성일'))) {
                            const td = row.querySelector('td');
                            if (td) {
                                dateText = td.textContent.trim();
                                break;
                            }
                        }
                    }

                    // 첨부파일 추출 - fn_egov_downFile 방식
                    const attachments = [];

                    // fn_egov_downFile 함수를 사용하는 링크 찾기
                    const fileLinks = document.querySelectorAll('a[href*="fn_egov_downFile"]');

                    fileLinks.forEach(link => {
                        const fileName = link.textContent.trim();
                        const href = link.href;

                        // fn_egov_downFile의 파라미터 추출
                        const match = href.match(/fn_egov_downFile\s*\(\s*['"]?([^'"]+)['"]?\s*,\s*['"]?([^'"]+)['"]?\s*\)/);

                        if (match && fileName) {
                            // 파일명 정리 (바이트 정보 제거)
                            const cleanName = fileName.replace(/\s*\[\d+\s*byte\]\s*$/, '');

                            attachments.push({
                                name: cleanName,
                                atchFileId: match[1],
                                fileSn: match[2],
                                url: `/icms/cmm/fms/FileDown.do?atchFileId=${match[1]}&fileSn=${match[2]}`
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

                // 리스트로 돌아가기
                await this.page.goBack();
                await this.page.waitForTimeout(1000);

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
     * 첨부파일 다운로드 - Daegu 특화
     */
    async downloadSingleAttachment(attachment, attachDir, index) {
        try {
            console.log(`첨부파일 다운로드 시작 (${index}): ${attachment.name}`);

            // Daegu는 직접 URL 다운로드 방식
            if (attachment.url) {
                const downloadUrl = new URL(attachment.url, 'https://www.daegu.go.kr').toString();
                console.log(`다운로드 URL: ${downloadUrl}`);

                // Playwright의 다운로드 처리
                const downloadPromise = this.page.waitForEvent('download', { timeout: 30000 });

                // 새 탭에서 다운로드 URL 열기
                await this.page.evaluate((url) => {
                    window.open(url, '_blank');
                }, downloadUrl);

                try {
                    const download = await downloadPromise;
                    const fileName = attachment.name || download.suggestedFilename();
                    const savePath = path.join(attachDir, fileName);

                    // 디렉토리가 없으면 생성
                    const saveDir = path.dirname(savePath);
                    fs.ensureDirSync(saveDir);
                    
                    await download.saveAs(savePath);
                    console.log(`다운로드 완료: ${fileName}`);
                } catch (downloadError) {
                    // 실패 공고 DB 기록
                    await FailureLogger.logFailedAnnouncement({
                        site_code: this.siteCode,
                        title: announcement?.title || 'Unknown',
                        url: announcement?.link || announcement?.url,
                        detail_url: announcement?.detailUrl,
                        error_type: 'downloadError',
                        error_message: downloadError.message
                    }).catch(logErr => {});

                    console.log(`다운로드 타임아웃, URL 저장: ${downloadUrl}`);
                    // 다운로드 실패시 URL 정보를 저장
                    const urlInfoPath = path.join(attachDir, `${attachment.name}.url.txt`);
                    await fs.writeFile(urlInfoPath, downloadUrl, 'utf8');
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
            }).catch(logErr => {});

            console.error(`첨부파일 다운로드 실패 (${attachment.name}):`, error.message);
        }
    }

    /**
     * 마크다운 컨텐츠 생성 - Daegu 특화 (첨부파일 URL 포함)
     */
    generateMarkdownContent(announcement, detailContent) {
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
                // URL이 있으면 파일명: URL 형식으로 표시
                if (att.url) {
                    const fullUrl = att.url.startsWith('/')
                        ? `https://www.daegu.go.kr${att.url}`
                        : att.url;
                    lines.push(`${i + 1}. ${att.name}: ${fullUrl}`);
                } else {
                    lines.push(`${i + 1}. ${att.name}`);
                }
            });
        }

        return lines.join('\n');
    }

    /**
     * 날짜 추출 - Daegu 특화
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
     * 상세 페이지 URL 구성 - Daegu는 JavaScript 함수 사용
     */
    async buildDetailUrl(announcement) {
        // Daegu는 fn_goLinkView 함수를 사용하므로 URL 구성 불필요
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

    const scraper = new DaeguScraper({
        targetDate: argv.date,
        goPage: argv.goPage,
        outputDir: argv.output
    });

    scraper.scrape().catch(console.error);
}

module.exports = DaeguScraper;
