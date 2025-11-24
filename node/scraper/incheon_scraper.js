#!/usr/bin/env node

/**
 * Incheon 공고 스크래핑 시스템
 * 
 * 기능:
 * 1. 날짜 기반 필터링
 * 2. 리스트 -> 상세 페이지 처리 (JavaScript viewData 함수 사용)
 * 3. content.md 파일 생성
 * 4. 첨부파일 다운로드
 * 5. 중복 게시물 스킵
 */

const AnnouncementScraper = require('./announcement_scraper');
const moment = require('moment');
const FailureLogger = require('./failure_logger');
const UrlManager = require('./url_manager');

class IncheonScraper extends AnnouncementScraper {
    constructor(options = {}) {
        super({
            ...options,
            baseUrl: options.baseUrl || 'https://announce.incheon.go.kr/citynet/jsp/sap/SAPGosiBizProcess.do',
            listSelector: 'table tbody tr',
            titleSelector: 'td:nth-child(2)',  // Title is in 2nd column
            dateSelector: 'td:nth-child(4)',   // Date is in 4th column
            siteCode: 'incheon',
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
     * 리스트 URL 구성 - POST 방식으로 처리
     */
    buildListUrl(pageNum) {
        // Incheon uses POST request, so we return base URL
        return this.baseUrl;
    }
    
    /**
     * 공고 처리 - 제목 중복 체크 추가
     */
    async processAnnouncement(announcement) {
        // 제목 중복 체크
        if (this.processedTitles.has(announcement.title)) {
            console.log(`이미 처리된 공고 (제목 중복): ${announcement.title}`);
            return false;
        }
        
        // 이전 제목과 같으면 스킵
        if (this.lastProcessedTitle === announcement.title) {
            console.log(`이전과 동일한 제목 발견, 스크래핑 종료: ${announcement.title}`);
            return true; // 스크래핑 종료 신호
        }
        
        // 처리된 제목 기록
        this.processedTitles.add(announcement.title);
        this.lastProcessedTitle = announcement.title;
        
        // 부모 클래스의 processAnnouncement 호출
        return super.processAnnouncement(announcement);
    }

    /**
     * 공고 리스트 가져오기 - Incheon 특화
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

                // 첫 페이지일 경우, 먼저 홈페이지로 이동하여 세션 초기화
                if (pageNum === 1) {
                    console.log('세션 초기화를 위해 홈페이지 방문...');
                    await this.page.goto('https://announce.incheon.go.kr', {
                        waitUntil: 'domcontentloaded',
                        timeout: 30000
                    });
                    await this.page.waitForTimeout(2000);
                }

                // GET 요청으로 직접 리스트 페이지 로드
                const listUrl = `https://announce.incheon.go.kr/citynet/jsp/sap/SAPGosiBizProcess.do?command=searchList&flag=gosiGL&svp=Y&sido=ic&currentPageNo=${pageNum}`;
                console.log(`리스트 URL로 이동: ${listUrl}`);
                await this.page.goto(listUrl, {
                    waitUntil: 'domcontentloaded',
                    timeout: 30000
                });

                // 페이지 데이터 로드 대기
                await this.page.waitForTimeout(2000);

                if (pageNum > 1) {
                    // 다음 페이지로 이동
                    await this.page.evaluate((pageNo) => {
                        // goPage 함수 호출
                        if (typeof goPage === 'function') {
                            goPage(pageNo);
                        } else {
                            // 폼 제출 방식
                            const form = document.querySelector('form[name="myform"]');
                            if (form) {
                                const pageField = form.querySelector('input[name="currentPageNo"]');
                                if (pageField) {
                                    pageField.value = pageNo;
                                }
                                form.submit();
                            }
                        }
                    }, pageNum);

                    await this.page.waitForLoadState('networkidle');
                }

                // 동적 컨텐츠 로딩 대기
                await this.page.waitForTimeout(3000);

                // 리스트 요소들 추출 - Incheon 특화
                const announcements = await this.page.evaluate(() => {
                    // Find the main table with announcements
                    const tables = document.querySelectorAll('table.toolBoardList');
                    let dataTable = null;

                    console.log("tables", tables.length)
                    // Look for table with actual data rows
                    for (const table of tables) {
                        const rows = table.querySelectorAll('tbody tr');
                        for (const row of rows) {
                            const onclick = row.getAttribute("onclick")
                            if (onclick && onclick.includes('viewData')) {
                                dataTable = table;
                                break;
                            }
                        }
                        if (dataTable) break;
                    }

                    console.log("dataTable found:", !!dataTable)

                    if (!dataTable) return [];

                    const rows = dataTable.querySelectorAll('tbody tr');
                    const results = [];

                    console.log("rows to process:", rows.length)
                    rows.forEach((row) => {
                        // Check for onclick on the row itself first
                        const rowOnclick = row.getAttribute('onclick');
                        let sno = null;
                        let gosiGbn = null;
                        
                        if (rowOnclick && rowOnclick.includes('viewData')) {
                            const match = rowOnclick.match(/viewData\s*\(\s*['"]?(\d+)['"]?\s*,\s*['"]?([^'"\)]+)['"]?\s*\)/);
                            if (match) {
                                sno = match[1];
                                gosiGbn = match[2];
                            }
                        }
                        
                        const cells = row.querySelectorAll('td');
                        if (cells.length < 4) return;

                        // 번호, 제목, 담당부서, 게재일 순서
                        const numberCell = cells[0];
                        const titleCell = cells[1];
                        const departmentCell = cells[2];
                        const dateCell = cells[3];

                        const title = titleCell ? titleCell.textContent.trim() : '';
                        const department = departmentCell ? departmentCell.textContent.trim() : '';
                        const dateText = dateCell ? dateCell.textContent.trim() : '';

                        // If not found in row, check in cells
                        if (!sno || !gosiGbn) {
                            // Check onclick in title cell
                            const onclickAttr = titleCell ? titleCell.getAttribute('onclick') : '';
                            
                            if (!onclickAttr) {
                                // onclick이 td가 아닌 a 태그에 있을 수도 있음
                                const link = titleCell ? titleCell.querySelector('a') : null;
                                if (link) {
                                    const linkOnclick = link.getAttribute('onclick');
                                    if (linkOnclick && linkOnclick.includes('viewData')) {
                                        const match = linkOnclick.match(/viewData\s*\(\s*['"]?(\d+)['"]?\s*,\s*['"]?([^'"\)]+)['"]?\s*\)/);
                                        if (match) {
                                            sno = match[1];
                                            gosiGbn = match[2];
                                        }
                                    }
                                }
                            } else if (onclickAttr.includes('viewData')) {
                                const match = onclickAttr.match(/viewData\s*\(\s*['"]?(\d+)['"]?\s*,\s*['"]?([^'"\)]+)['"]?\s*\)/);
                                if (match) {
                                    sno = match[1];
                                    gosiGbn = match[2];
                                }
                            }
                        }

                        if (title && dateText) {
                            results.push({
                                title,
                                dateText,
                                department,
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
     * 상세 페이지 내용 가져오기 - Incheon 특화
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

                // 직접 URL로 상세 페이지 접근
                if (announcement.sno && announcement.gosiGbn) {
                    const detailUrl = `https://announce.incheon.go.kr/citynet/jsp/sap/SAPGosiBizProcess.do?command=searchDetail&flag=gosiGL&svp=Y&sido=ic&sno=${announcement.sno}&gosiGbn=${announcement.gosiGbn}`;
                    console.log(`상세 페이지 URL: ${detailUrl}`);
                    
                    // 새 페이지에서 상세 내용 열기
                    await this.page.goto(detailUrl, {
                        waitUntil: 'networkidle',
                        timeout: 30000
                    });
                    
                    // 페이지 로드 대기
                    await this.page.waitForTimeout(3000);
                } else {
                    // viewData 함수 호출하여 상세 페이지로 이동
                    await this.page.evaluate(({ sno, gosiGbn }) => {
                        // viewData 함수가 있으면 호출
                        if (typeof viewData === 'function') {
                            console.log("viewData")
                            viewData(sno, gosiGbn);
                        } else {
                        // 폼 제출 방식
                        const form = document.querySelector('form[name="myform"]');
                        if (form) {
                            // sno와 gosiGbn 설정
                            let snoField = form.querySelector('input[name="sno"]');
                            if (!snoField) {
                                snoField = document.createElement('input');
                                snoField.type = 'hidden';
                                snoField.name = 'sno';
                                form.appendChild(snoField);
                            }
                            snoField.value = sno;

                            let gosiGbnField = form.querySelector('input[name="gosiGbn"]');
                            if (!gosiGbnField) {
                                gosiGbnField = document.createElement('input');
                                gosiGbnField.type = 'hidden';
                                gosiGbnField.name = 'gosiGbn';
                                form.appendChild(gosiGbnField);
                            }
                            gosiGbnField.value = gosiGbn;

                            // command 설정
                            let commandField = form.querySelector('input[name="command"]');
                            if (!commandField) {
                                commandField = document.createElement('input');
                                commandField.type = 'hidden';
                                commandField.name = 'command';
                                form.appendChild(commandField);
                            }
                            commandField.value = 'gosiview';

                            form.submit();
                            }
                        }
                    }, { sno: announcement.sno, gosiGbn: announcement.gosiGbn });
                    
                    // 페이지 로드 대기
                    await this.page.waitForLoadState('networkidle');
                    await this.page.waitForTimeout(4000);
                }

                // 페이지 내용 추출 - Incheon 특화
                const content = await this.page.evaluate(() => {
                    // 본문 추출 - Incheon은 내용이 별도 행에 있음
                    let mainContent = null;
                    let contentText = '';
                    
                    // 모든 테이블 행 확인 - 더 다양한 패턴 지원
                    const rows = document.querySelectorAll('tr');
                    let contentRowFound = false;
                    
                    for (let i = 0; i < rows.length; i++) {
                        const row = rows[i];
                        const th = row.querySelector('th');
                        
                        if (th) {
                            const headerText = th.textContent.replace(/\s+/g, ' ').trim();
                            // '내 용', '내용', '공고내용' 등 다양한 헤더 찾기
                            if (headerText === '내 용' || headerText === '내용' || 
                                headerText.includes('내용') || headerText === '공고문' || 
                                headerText === '상세내용' || headerText === '본문') {
                                console.log("Found content header at row", i, ":", headerText);
                                
                                // 1. 같은 행의 td 확인
                                const sameTd = row.querySelector('td');
                                if (sameTd) {
                                    const text = sameTd.innerText || sameTd.textContent || '';
                                    if (text.trim().length > 20) {
                                        contentText = text;
                                        mainContent = sameTd;
                                        contentRowFound = true;
                                        console.log("Found content in same row, length:", text.length);
                                        break;
                                    }
                                }
                                
                                // 2. 다음 몇 개 행 확인 (최대 5개)
                                for (let j = i + 1; j < rows.length && j < i + 5; j++) {
                                    const nextRow = rows[j];
                                    // colspan이 있는 td 또는 일반 td
                                    const nextTd = nextRow.querySelector('td[colspan], td');
                                    if (nextTd) {
                                        const text = nextTd.innerText || nextTd.textContent || '';
                                        // 더 낮은 임계값으로 내용 확인
                                        if (text.trim().length > 20 && !text.includes('첨부파일')) {
                                            contentText = text;
                                            mainContent = nextTd;
                                            contentRowFound = true;
                                            console.log("Found content in row", j, ", length:", text.length);
                                            break;
                                        }
                                    }
                                }
                                
                                if (contentRowFound) break;
                            }
                        }
                    }
                    
                    // 못 찾으면 colspan이 있는 td 또는 큰 텍스트가 있는 td 찾기
                    if (!contentRowFound) {
                        // 1. colspan이 있는 td 확인
                        const colspanTds = document.querySelectorAll('td[colspan]');
                        let largestContent = '';
                        let largestTd = null;
                        
                        colspanTds.forEach(td => {
                            const text = td.innerText || td.textContent || '';
                            // 더 낮은 임계값 (50자 이상)
                            if (text.length > largestContent.length && text.length > 50 && 
                                !text.includes('첨부파일') && !text.includes('목록')) {
                                largestContent = text;
                                largestTd = td;
                            }
                        });
                        
                        // 2. colspan이 없어도 큰 텍스트를 가진 td 확인
                        if (!largestContent) {
                            const allTds = document.querySelectorAll('td');
                            allTds.forEach(td => {
                                const text = td.innerText || td.textContent || '';
                                if (text.length > largestContent.length && text.length > 100) {
                                    // 날짜나 번호가 아닌 실제 내용인지 확인
                                    if (!text.match(/^\d{4}-\d{2}-\d{2}$/) && 
                                        !text.match(/^\d+$/) &&
                                        !text.includes('첨부파일')) {
                                        largestContent = text;
                                        largestTd = td;
                                    }
                                }
                            });
                        }
                        
                        if (largestContent) {
                            contentText = largestContent;
                            mainContent = largestTd;
                            console.log("Found content in td, length:", largestContent.length);
                        }
                    }
                    
                    // 그래도 못 찾으면 다른 선택자 시도
                    if (!contentText) {
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
                                contentText = element.innerText || element.textContent || '';
                                console.log("Found content with selector:", selector);
                                break;
                            }
                        }
                    }

                    console.log("mainContent found:", !!mainContent, "contentLength:", contentText.length)

                    // 못 찾으면 전체 페이지에서 의미있는 텍스트 추출
                    if (!mainContent || contentText.length < 20) {
                        // 테이블 전체 텍스트에서 의미있는 부분 추출
                        const tables = document.querySelectorAll('table');
                        for (const table of tables) {
                            const tableText = table.innerText || table.textContent || '';
                            // 헤더와 푸터를 제외한 중간 부분 추출
                            if (tableText.length > 200 && tableText.includes('내용')) {
                                const lines = tableText.split('\n').filter(line => line.trim().length > 0);
                                // 내용 이후의 텍스트 찾기
                                let foundContent = false;
                                let extractedLines = [];
                                for (const line of lines) {
                                    if (foundContent) {
                                        if (line.includes('첨부파일') || line.includes('목록') || line.includes('이전글')) {
                                            break;
                                        }
                                        extractedLines.push(line);
                                    } else if (line.includes('내용') || line.includes('공고문')) {
                                        foundContent = true;
                                    }
                                }
                                if (extractedLines.length > 0) {
                                    contentText = extractedLines.join('\n');
                                    mainContent = table;
                                    console.log("Extracted content from table text");
                                    break;
                                }
                            }
                        }
                    }
                    
                    // 그래도 못 찾으면 기본값
                    if (!contentText || contentText.length < 20) {
                        contentText = document.body.innerText || document.body.textContent || '';
                        console.log("Using body text as fallback");
                    }

                    // 날짜 추출
                    let dateText = '';

                    // 테이블에서 게재일 찾기
                    for (const row of rows) {
                        const th = row.querySelector('th');
                        if (th && (th.textContent.includes('게재일') || th.textContent.includes('게재 일자') || th.textContent.includes('등록일'))) {
                            const td = row.querySelector('td');
                            if (td) {
                                dateText = td.textContent.trim();
                                break;
                            }
                        }
                    }
                    console.log("dateText", dateText)

                    // 첨부파일 추출
                    const attachments = [];

                    // 다운로드 링크 찾기
                    const fileLinks = document.querySelectorAll('a[href*="download"], a[onclick*="download"], a[href*="FileDown"]');

                    console.log("fileLinks", fileLinks.length)
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

                    console.log("attachments found:", attachments.length)

                    // console.log("textContent", textContent)
                    return {
                        content: contentText.trim(),
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
     * 날짜 추출 - Incheon 특화
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
     * 상세 페이지 URL 구성 - Incheon은 JavaScript 함수 사용
     */
    async buildDetailUrl(announcement) {
        // Incheon은 viewData 함수를 사용하므로 URL 구성 불필요
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

    const scraper = new IncheonScraper({
        targetDate: argv.date,
        goPage: argv.goPage,
        outputDir: argv.output
    });

    scraper.scrape().catch(console.error);
}

module.exports = IncheonScraper;