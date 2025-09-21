#!/usr/bin/env node

/**
 * Daejeon 공고 스크래핑 시스템
 * 
 * 기능:
 * 1. 날짜 기반 필터링
 * 2. 리스트 -> 상세 페이지 처리 
 * 3. content.md 파일 생성
 * 4. 첨부파일 다운로드
 * 5. 중복 게시물 스킵
 */

const AnnouncementScraper = require('./announcement_scraper');
const moment = require('moment');

class DaejeonScraper extends AnnouncementScraper {
    constructor(options = {}) {
        super({
            ...options,
            baseUrl: options.baseUrl || 'https://www.daejeon.go.kr/drh/drhGosiList.do?gosigbn=A&menuSeq=1908',
            listSelector: 'table tbody tr',
            titleSelector: 'td:nth-child(2) a',
            dateSelector: 'td:nth-child(4)',
            siteCode: 'daejeon',
            ...options
        });
    }

    /**
     * 리스트 URL 구성
     */
    buildListUrl(pageNum) {
        const url = new URL(this.baseUrl);
        // Daejeon은 pageIndex 파라미터 사용
        url.searchParams.set('pageIndex', pageNum);
        // 기존 파라미터 유지
        if (!url.searchParams.has('gosigbn')) {
            url.searchParams.set('gosigbn', 'A');
        }
        if (!url.searchParams.has('menuSeq')) {
            url.searchParams.set('menuSeq', '1908');
        }
        return url.toString();
    }

    /**
     * 공고 리스트 가져오기 - Daejeon 특화
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
                await this.page.waitForTimeout(3000);

                // 리스트 요소들 추출 - Daejeon 특화
                const announcements = await this.page.evaluate(() => {
                    const rows = document.querySelectorAll('table tbody tr');
                    const results = [];

                    rows.forEach((row) => {
                        // 헤더 행이나 빈 행 스킵
                        if (row.querySelector('th') || !row.querySelector('td')) return;

                        const cells = row.querySelectorAll('td');
                        if (cells.length < 4) return; // 충분한 셀이 없으면 스킵

                        // 번호, 제목, 담당부서, 등록일 순서
                        const titleCell = cells[1];
                        const departmentCell = cells[2];
                        const dateCell = cells[3];

                        const titleLink = titleCell ? titleCell.querySelector('a') : null;
                        if (!titleLink) return;

                        const title = titleLink.textContent.trim();
                        const href = titleLink.href;
                        const department = departmentCell ? departmentCell.textContent.trim() : '';
                        const dateText = dateCell ? dateCell.textContent.trim() : '';

                        // 상세 URL 구성 - href가 이미 완전한 URL
                        results.push({
                            title,
                            dateText,
                            link: href,
                            department,
                            listDate: dateText
                        });
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
     * 단일 첨부파일 다운로드 (브라우저 클릭 방식)
     */
    async downloadSingleAttachment(attachment, attachDir, index) {
        const startTime = Date.now();
        console.log(`\n📥 === 첨부파일 다운로드 시작 (${index}) ===`);
        console.log(`파일명: ${attachment.name}`);
        console.log(`URL: ${attachment.url}`);

        try {
            let downloadUrl = attachment.url;
            let fileName = attachment.name || `attachment_${index}`;
            let actualDownloadUrl = null;
            let downloadType = 'direct';

            // gourl 패턴 처리 - hanam은 3개 파라미터 사용
            // gourl('user_file_nm', 'sys_file_nm', 'file_path')
            const regex = /fileDown\('([^']+)''\)/;
            // Regex to find "fileDown(" and capture the content inside the quotes
            const match = downloadUrl.match(/fileDown\("([^"]*)"\)/);

            if (match && match[1]) {
                const filePath = match[1];


                downloadUrl = `https://www.daejeon.go.kr/drh/drhGosiFileDownload.do?filePath=${filePath}`

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
            }
            // console.log(matches)
            // if (matches) {
            //     const [, userFileNm, sysFileNm, filePath] = matches;

            //     // userFileNm 디코딩하여 실제 파일명 얻기
            //     let displayFileName = userFileNm;
            //     try {
            //         if (userFileNm.includes('%')) {
            //             displayFileName = decodeURIComponent(userFileNm);
            //         }
            //     } catch (e) {
            //         displayFileName = userFileNm;
            //     }

            //     fileName = displayFileName || attachment.name;

            //     console.log('🎯 gourl 패턴 감지:', {
            //         userFileNm: userFileNm,
            //         sysFileNm: sysFileNm,
            //         filePath: filePath,
            //         fileName: displayFileName
            //     });

            //     // goDownLoad 함수 실행 방식으로 다운로드
            //     const downloadResult = await this.downloadViaEgovPost(userFileNm, sysFileNm, filePath, attachDir, displayFileName);

            //     if (downloadResult && downloadResult.success) {
            //         const elapsed = Date.now() - startTime;
            //         console.log(`✅ gourl 패턴 다운로드 성공!`);
            //         console.log(`📊 처리 시간: ${elapsed}ms`);
            //         // 파일명을 키로 사용하여 다운로드 정보 반환
            //         const resultKey = fileName || attachment.name;
            //         return { [resultKey]: downloadResult };
            //     } else {
            //         // 다운로드 실패해도 URL 정보는 반환
            //         const actualUrl = `https://eminwon.hanam.go.kr/emwp/jsp/ofr/FileDown.jsp?user_file_nm=${encodeURIComponent(userFileNm)}&sys_file_nm=${encodeURIComponent(sysFileNm)}&file_path=${encodeURIComponent(filePath)}`;
            //         console.log(`⚠️ 다운로드 실패, URL 정보만 저장: ${actualUrl}`);
            //         const resultKey = fileName || attachment.name;
            //         return { [resultKey]: { actualDownloadUrl: actualUrl } };
            //     }

            // } else {
            //     console.log('❌ gourl 패턴이 감지되지 않음');
            //     console.log('지원하지 않는 첨부파일 형식입니다.');
            //     return { success: false, reason: 'unsupported_pattern' };
            // }

        } catch (error) {
            const elapsed = Date.now() - startTime;
            console.error(`❌ 첨부파일 다운로드 최종 실패 (${attachment.name}):`);
            console.error(`   오류: ${error.message}`);
            console.error(`   처리 시간: ${elapsed}ms`);

            // 실패시 파일 크기 확인
            const failedFilePath = path.join(attachDir, sanitize(attachment.name || `attachment_${index}`, { replacement: '_' }));
            if (await fs.pathExists(failedFilePath)) {
                const stats = await fs.stat(failedFilePath);
                console.error(`   다운로드된 파일 크기: ${stats.size} bytes`);
                if (stats.size < 200) {
                    const content = await fs.readFile(failedFilePath, 'utf8');
                    console.error(`   파일 내용: ${content.substring(0, 100)}...`);
                }
            }

            return {
                success: false,
                error: error.message,
                processingTime: elapsed,
                fileName: attachment.name
            };
        } finally {
            console.log(`📥 === 첨부파일 다운로드 종료 (${index}) ===\n`);
        }
    }


    /**
     * 상세 페이지 내용 가져오기 - Daejeon 특화
     */
    async getDetailContent(announcement) {
        const maxRetries = 3;
        let retries = 0;

        while (retries < maxRetries) {
            try {
                // Daejeon은 이미 완전한 URL을 가지고 있음
                const detailUrl = announcement.link;

                if (!detailUrl || !detailUrl.startsWith('http')) {
                    console.log('유효하지 않은 상세 페이지 URL:', detailUrl);
                    return null;
                }

                console.log(`상세 페이지 이동: ${detailUrl}`);

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

                // 페이지 내용 추출 - Daejeon 특화
                const content = await this.page.evaluate(() => {
                    // 본문 추출
                    let mainContent = null;

                    // Daejeon 사이트의 콘텐츠 선택자
                    const contentSelectors = [
                        '.view_content',       // 본문 영역
                        '.board_view',         // 게시판 뷰
                        '.content_view',       // 콘텐츠 뷰
                        '#viewForm',           // 뷰 폼
                        'table.board_view',    // 테이블 형식 뷰
                        '#content'             // 일반 콘텐츠
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
                        '.btn_area', '.button_area'
                    ];

                    excludeSelectors.forEach(selector => {
                        const elements = mainContent.querySelectorAll(selector);
                        elements.forEach(el => el.remove());
                    });

                    // 날짜 추출
                    let dateText = '';
                    const dateSelectors = [
                        'td:contains("등록일") + td',
                        '.date',
                        '.reg_date',
                        '[class*="date"]'
                    ];

                    // jQuery 스타일 선택자를 일반 선택자로 변환
                    const dateRow = Array.from(document.querySelectorAll('tr')).find(tr => {
                        const th = tr.querySelector('th');
                        return th && th.textContent.includes('등록일');
                    });

                    if (dateRow) {
                        const dateTd = dateRow.querySelector('td');
                        if (dateTd) {
                            dateText = dateTd.textContent.trim();
                        }
                    }

                    // 첨부파일 추출
                    const attachments = [];

                    // 파일 다운로드 링크 찾기
                    const fileLinks = document.querySelectorAll('a[href*="FileDown"], a[href*="fileDown"], a[onclick*="download"]');

                    fileLinks.forEach(link => {
                        const fileName = link.textContent.trim();
                        const cleanFileName = fileName.replace(/\(\d+\.?\d*KB\)/i, '').trim();

                        const href = link.href;
                        const onclick = link.getAttribute('onclick');

                        if (fileName && (href || onclick)) {
                            attachments.push({
                                name: cleanFileName,
                                url: href,
                                onclick: onclick
                            });
                        }
                    });

                    console.log("attachments", attachments)
                    // 파일 목록이 테이블 형태로 있는 경우도 처리
                    const fileTable = document.querySelector('.file_list, .attach_list, [class*="file"]');
                    if (fileTable) {
                        const fileRows = fileTable.querySelectorAll('tr, li');
                        fileRows.forEach(row => {
                            const link = row.querySelector('a');
                            if (link && !attachments.some(a => a.name === link.textContent.trim())) {
                                attachments.push({
                                    name: link.textContent.trim(),
                                    url: link.href,
                                    onclick: link.getAttribute('onclick')
                                });
                            }
                        });
                    }

                    // 텍스트만 추출
                    const textContent = mainContent.innerText || mainContent.textContent || '';

                    return {
                        content: textContent.trim(),
                        dateText: dateText,
                        attachments: attachments
                    };
                });

                // 날짜 파싱
                const detailDate = this.extractDate(content.dateText || announcement.dateText);

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
     * 날짜 추출 - Daejeon 특화
     */
    extractDate(dateText) {
        if (!dateText) return null;

        // 텍스트 정리
        let cleanText = dateText.trim();

        // "2025-09-19" 같은 형식 추출
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
     * 페이지네이션 처리 - Daejeon 특화
     */
    async hasNextPage(currentPage) {
        try {
            // 페이지네이션 영역 확인
            const hasNext = await this.page.evaluate((currentPage) => {
                // Daejeon 사이트의 페이지네이션
                const pagination = document.querySelector('.paging, .pagination, .page_navi');
                if (!pagination) return false;

                // 다음 페이지 링크 찾기
                const nextLinks = pagination.querySelectorAll('a');
                for (const link of nextLinks) {
                    const text = link.textContent.trim();
                    const onclick = link.getAttribute('onclick');

                    // 다음 페이지 번호나 "다음" 버튼 찾기
                    if (text === String(currentPage + 1) ||
                        text === '다음' ||
                        text === 'Next' ||
                        (onclick && onclick.includes(`pageIndex=${currentPage + 1}`))) {
                        return true;
                    }
                }

                return false;
            }, currentPage);

            return hasNext;
        } catch (error) {
            console.log('페이지네이션 확인 실패:', error.message);
            return false;
        }
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

    const scraper = new DaejeonScraper({
        targetDate: argv.date,
        goPage: argv.goPage,
        outputDir: argv.output
    });

    scraper.scrape().catch(console.error);
}

module.exports = DaejeonScraper;