#!/usr/bin/env node

/**
 * Seoul 공고 스크래핑 시스템
 * 
 * 기능:
 * 1. 날짜 기반 필터링
 * 2. SPA 기반 리스트 -> 상세 페이지 처리
 * 3. content.md 파일 생성
 * 4. 첨부파일 다운로드
 * 5. 중복 게시물 스킵
 */

const AnnouncementScraper = require('./announcement_scraper');
const moment = require('moment');

class SeoulScraper extends AnnouncementScraper {
    constructor(options = {}) {
        super({
            ...options,
            baseUrl: options.baseUrl || 'https://www.seoul.go.kr/news/news_notice.do',
            listSelector: 'tbody tr',
            titleSelector: 'td.sib-lst-type-basic-subject a',
            dateSelector: 'td:nth-child(5)',  // 등록일 column
            siteCode: 'seoul',
            ...options
        });
    }

    /**
     * 리스트 URL 구성 - Seoul은 hash 기반
     */
    buildListUrl(pageNum) {
        return `${this.baseUrl}#list/${pageNum}`;
    }

    /**
     * 공고 리스트 가져오기 - Seoul 특화 (JSON API 사용)
     */
    async getAnnouncementList(pageNum) {
        const maxRetries = 3;
        let retries = 0;

        while (retries < maxRetries) {
            try {
                console.log(`페이지 ${pageNum} 로딩 중...`);

                // 브라우저나 페이지가 종료된 경우 재초기화
                if (!this.browser || !this.page || this.page.isClosed()) {
                    console.log('브라우저 연결이 끊어져 재초기화합니다...');
                    await this.initBrowser();
                }

                // JSON API를 통해 리스트 가져오기
                const apiUrl = `https://seoulboard.seoul.go.kr/front/bbs.json?bbsNo=277&curPage=${pageNum}&schTy=&schData=`;
                console.log(`API 호출: ${apiUrl}`);

                const response = await this.page.evaluate(async (url) => {
                    try {
                        const res = await fetch(url);
                        return await res.json();
                    } catch (e) {
                        return null;
                    }
                }, apiUrl);

                if (!response || !response.bbsListVO) {
                    console.log('API 응답 없음, 페이지 방식으로 시도...');

                    // Fallback: 페이지 직접 로드
                    const listUrl = this.buildListUrl(pageNum);
                    await this.page.goto(listUrl, {
                        waitUntil: 'networkidle',
                        timeout: 30000
                    });

                    await this.page.waitForTimeout(3000);

                    // DOM에서 직접 추출
                    const announcements = await this.page.evaluate(() => {
                        const rows = document.querySelectorAll('tbody tr');
                        const results = [];

                        rows.forEach((row) => {
                            if (row.querySelector('th') || !row.querySelector('td')) return;
                            const cells = row.querySelectorAll('td');
                            if (cells.length < 6) return;

                            const titleCell = cells[1];
                            const titleLink = titleCell ? titleCell.querySelector('a') : null;
                            if (!titleLink) return;

                            const title = titleLink.textContent.trim();
                            const dataCode = titleLink.getAttribute('data-code');
                            const department = cells[3] ? cells[3].textContent.trim() : '';
                            const dateText = cells[4] ? cells[4].textContent.trim() : '';

                            if (title && dataCode) {
                                results.push({
                                    title,
                                    dateText,
                                    department,
                                    dataCode,
                                    listDate: dateText
                                });
                            }
                        });
                        return results;
                    });

                    console.log(`리스트에서 ${announcements.length}개 공고 발견`);
                    return announcements;
                }

                // API 응답에서 데이터 추출
                const announcements = [];

                if (response.bbsListVO && response.bbsListVO.listOutptObject) {
                    response.bbsListVO.listOutptObject.forEach(item => {
                        // 제목, 날짜, 부서 등 추출
                        const title = item.nttSj || item.title || '';
                        const dataCode = item.bbsCd || item.nttNo || '';
                        const dateText = item.regDt || item.registDt || '';
                        const department = item.writngDept || item.department || '';

                        if (title && dataCode) {
                            announcements.push({
                                title: title.trim(),
                                dateText: dateText.trim(),
                                department: department.trim(),
                                dataCode: dataCode.toString(),
                                listDate: dateText.trim()
                            });
                        }
                    });
                }

                console.log(`API에서 ${announcements.length}개 공고 발견`);
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
     * 상세 페이지 내용 가져오기 - Seoul 특화 (DOM 렌더링 방식)
     */
    async getDetailContent(announcement) {
        const maxRetries = 3;
        let retries = 0;

        while (retries < maxRetries) {
            try {
                console.log(`상세 페이지 보기: ${announcement.title}`);

                // 브라우저나 페이지가 종료된 경우 재초기화
                if (!this.browser || !this.page || this.page.isClosed()) {
                    console.log('브라우저 연결이 끊어져 재초기화합니다...');
                    await this.initBrowser();
                }

                // 상세 페이지 URL로 직접 이동
                const pageUrl = `https://www.seoul.go.kr/news/news_notice.do#view/${announcement.dataCode}`;
                console.log(`상세 페이지 URL: ${pageUrl}`);

                await this.page.goto(pageUrl, {
                    waitUntil: 'networkidle',
                    timeout: 30000
                });

                // 페이지 렌더링 대기
                await this.page.waitForTimeout(5000);

                // JavaScript를 통해 상세 view 트리거
                await this.page.evaluate((dataCode) => {
                    // SCB 객체가 있으면 직접 호출
                    if (typeof SCB !== 'undefined' && SCB.view) {
                        SCB.view(dataCode);
                    }
                    // 또는 detailCheck 함수가 있으면 호출
                    else if (typeof detailCheck !== 'undefined') {
                        detailCheck(dataCode);
                    }
                }, announcement.dataCode);

                // 상세 콘텐츠 로드 대기
                await this.page.waitForTimeout(3000);

                // DOM에서 직접 내용 추출
                let response = null;
                try {
                    // 먼저 API로 시도 (세션이 있을 경우)
                    const viewApiUrl = `https://seoulboard.seoul.go.kr/front/${announcement.dataCode}/bbs.json?bbsNo=277&nttNo=${announcement.dataCode}`;
                    const apiResponse = await this.page.evaluate(async (url) => {
                        try {
                            const res = await fetch(url);
                            const text = await res.text();
                            if (!text.includes('<!DOCTYPE') && !text.includes('<html')) {
                                return JSON.parse(text);
                            }
                        } catch (e) {
                            return null;
                        }
                        return null;
                    }, viewApiUrl);

                    if (apiResponse && apiResponse.bbsVO) {
                        response = apiResponse;
                    }
                } catch (error) {
                    console.log('API 호출 실패, DOM 추출로 전환');
                }

                if (response && response.bbsVO) {
                    // API 응답에서 데이터 추출
                    const data = response.bbsVO;

                    // 내용 추출 - HTML 태그 제거
                    let content = data.nttCn || data.bbsCn || data.content || '';
                    // HTML 태그 제거
                    content = content.replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').trim();

                    // 첨부파일 추출
                    const attachments = [];
                    if (response.fileList && Array.isArray(response.fileList)) {
                        response.fileList.forEach(file => {
                            if (file.orginlFileNm || file.fileNm) {
                                attachments.push({
                                    name: file.orginlFileNm || file.fileNm,
                                    url: `https://seoulboard.seoul.go.kr/front/file/download.do?fileNo=${file.fileNo}&bbsCd=${announcement.dataCode}`,
                                    size: file.fileSize || 0
                                });
                            }
                        });
                    }

                    // 날짜 파싱
                    const detailDate = this.extractDate(data.regDt || data.writngDe || announcement.dateText);

                    return {
                        url: pageUrl,
                        content: content || announcement.title,
                        date: detailDate,
                        attachments: attachments
                    };
                }

                // DOM에서 직접 추출
                console.log('DOM에서 내용 추출 시도');

                // 페이지에서 내용 추출
                const pageData = await this.page.evaluate(() => {
                    // 상세 뷰 콘테이너 찾기
                    const viewContainer = document.querySelector('#viewTable, .board_view, .view_content, #viewForm');
                    let contentText = '';
                    let attachments = [];

                    if (viewContainer) {
                        // 제목 추출
                        const titleElem = viewContainer.querySelector('.sib-tit, .view_title, h2, h3');
                        const title = titleElem ? titleElem.innerText.trim() : '';

                        // 본문 내용 추출
                        const contentElem = viewContainer.querySelector('.sib-cont, .view_cont, .content_body, .board-view-content');
                        if (contentElem) {
                            contentText = contentElem.innerText || contentElem.textContent || '';
                        } else {
                            // 전체 컨테이너에서 추출
                            const fullText = viewContainer.innerText || viewContainer.textContent || '';

                            // 제목 이후 내용 추출
                            if (title && fullText.includes(title)) {
                                const titleIndex = fullText.indexOf(title);
                                const afterTitle = fullText.substring(titleIndex + title.length);

                                // 불필요한 부분 제거
                                const endMarkers = ['본 저작물은', '페이지 만족도', '공유하기', '프린트'];
                                let endIndex = afterTitle.length;
                                endMarkers.forEach(marker => {
                                    const idx = afterTitle.indexOf(marker);
                                    if (idx > -1 && idx < endIndex) {
                                        endIndex = idx;
                                    }
                                });

                                contentText = afterTitle.substring(0, endIndex).trim();
                            } else {
                                contentText = fullText;
                            }
                        }
                    }

                    // 그래도 못 찾으면 전체 body에서 시도
                    if (!contentText) {
                        const bodyText = document.body.innerText || document.body.textContent || '';

                        // 공고 시작 마커 찾기
                        const startMarkers = ['서울특별시 공고', '고시·공고 게시물 보기', '공고내용'];
                        let startIdx = -1;
                        for (const marker of startMarkers) {
                            const idx = bodyText.indexOf(marker);
                            if (idx > -1) {
                                startIdx = idx;
                                break;
                            }
                        }

                        if (startIdx > -1) {
                            const afterStart = bodyText.substring(startIdx);
                            const endMarkers = ['본 저작물은', '페이지 만족도', '목록보기'];
                            let endIndex = afterStart.length;
                            endMarkers.forEach(marker => {
                                const idx = afterStart.indexOf(marker);
                                if (idx > -1 && idx < endIndex) {
                                    endIndex = idx;
                                }
                            });
                            contentText = afterStart.substring(0, endIndex).trim();
                        }
                    }

                    // 첨부파일 찾기 - Seoul 특화 (data 속성 사용)
                    const fileArea = document.querySelector('.sib-viw-type-basic-file, .sib-viw-file-list');
                    
                    if (fileArea) {
                        // p 태그의 data 속성을 이용한 파일 정보 추출
                        const fileParagraphs = fileArea.querySelectorAll('p[data-srvcid]');
                        fileParagraphs.forEach(p => {
                            const fileLink = p.querySelector('a');
                            if (fileLink) {
                                const fileName = fileLink.textContent.trim();
                                
                                // data 속성에서 파일 정보 추출
                                const srvcId = p.dataset.srvcid || 'BBSTY1';
                                const upperNo = p.dataset.upperno;
                                const fileTy = p.dataset.filety || 'ATTACH';
                                const fileNo = p.dataset.fileno;
                                const bbsNo = p.dataset.downbbsno || '277';
                                
                                if (fileName && upperNo && fileNo) {
                                    // Seoul 다운로드 URL 패턴
                                    const downloadUrl = `https://seoulboard.seoul.go.kr/comm/getFile?srvcId=${srvcId}&upperNo=${upperNo}&fileTy=${fileTy}&fileNo=${fileNo}&bbsNo=${bbsNo}`;
                                    
                                    attachments.push({
                                        name: fileName,
                                        url: downloadUrl
                                    });
                                }
                            }
                        });
                        
                        // 대체 방법: a 태그 직접 확인
                        if (attachments.length === 0) {
                            const fileLinks = fileArea.querySelectorAll('a');
                            fileLinks.forEach(link => {
                                const fileName = link.textContent.trim();
                                if (fileName && !fileName.includes('바로보기') && !fileName.includes('바로듣기')) {
                                    // 부모 p 태그에서 data 속성 확인
                                    const parentP = link.closest('p[data-srvcid]');
                                    if (parentP) {
                                        const srvcId = parentP.dataset.srvcid || 'BBSTY1';
                                        const upperNo = parentP.dataset.upperno;
                                        const fileTy = parentP.dataset.filety || 'ATTACH';
                                        const fileNo = parentP.dataset.fileno;
                                        const bbsNo = parentP.dataset.downbbsno || '277';
                                        
                                        if (upperNo && fileNo) {
                                            const downloadUrl = `https://seoulboard.seoul.go.kr/comm/getFile?srvcId=${srvcId}&upperNo=${upperNo}&fileTy=${fileTy}&fileNo=${fileNo}&bbsNo=${bbsNo}`;
                                            attachments.push({
                                                name: fileName,
                                                url: downloadUrl
                                            });
                                        }
                                    }
                                }
                            });
                        }
                    }
                    
                    // 그래도 못 찾으면 버튼의 data-url 확인
                    if (attachments.length === 0) {
                        const previewButtons = document.querySelectorAll('button[data-type="preview"]');
                        previewButtons.forEach(button => {
                            const url = button.dataset.url;
                            const name = button.dataset.name;
                            if (url && name) {
                                attachments.push({
                                    name: name,
                                    url: url
                                });
                            }
                        });
                    }

                    return {
                        content: contentText,
                        attachments: attachments,
                        found: contentText.length > 0
                    };
                });

                // 날짜 추출
                const detailDate = this.extractDate(announcement.dateText);

                return {
                    url: pageUrl,
                    content: pageData.content || announcement.title,
                    date: detailDate,
                    attachments: pageData.attachments || []
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
     * 날짜 추출 - Seoul 특화
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
     * 상세 페이지 URL 구성 - Seoul은 SPA이므로 클릭으로 처리
     */
    async buildDetailUrl(announcement) {
        // Seoul은 SPA이므로 URL 구성 불필요
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

    const scraper = new SeoulScraper({
        targetDate: argv.date,
        goPage: argv.goPage,
        outputDir: argv.output
    });

    scraper.scrape().catch(console.error);
}

module.exports = SeoulScraper;