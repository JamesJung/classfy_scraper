#!/usr/bin/env node

/**
 * 의정부시 공고 스크래핑 시스템
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
const sanitize = require('sanitize-filename');
const path = require('path');
const fs = require('fs-extra');
const axios = require('axios');
const https = require('https');
const FailureLogger = require('./failure_logger');
const UrlManager = require('./url_manager');

class Ui4uScraper extends AnnouncementScraper {
    constructor(options = {}) {
        const defaultOptions = {
            siteCode: 'ui4u',
            baseUrl: 'https://www.ui4u.go.kr/portal/saeol/gosiList.do?seCode=01&mId=0301040000',
            listSelector: 'table.board-list tbody tr, table tbody tr',
            titleSelector: 'td.subject a, td.tit a, td:nth-child(3) a',
            dateSelector: 'td.date, td:nth-child(6), td:last-child',
            paginationParam: 'page',
            dateFormat: 'YYYY-MM-DD',
            ...options
        };

        super(defaultOptions);
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
     * 리스트 URL 구성
     */
    buildListUrl(pageNum) {
        const url = new URL(this.baseUrl);
        url.searchParams.set(this.options.paginationParam || 'page', pageNum);
        return url.toString();
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

        // 2. JavaScript onclick이 있는 경우
        if (announcement.onclick) {
            console.log('onclick 분석 중:', announcement.onclick);

            //boardView

            const viewMatch = announcement.onclick.match(/boardView\(\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*\)/);
            // gosiView.do?seq=12345 패턴
            // const viewMatch = announcement.onclick.match(/location\.href\s*=\s*['"]([^'"]+)['"]/);
            if (viewMatch) {

                //`/portal/saeol/gosiView.do?notAncmtMgtNo='+idx+'&mId=0301040000`
                let idx = viewMatch[2]


                let viewUrl = `https://www.ui4u.go.kr/portal/saeol/gosiView.do?notAncmtMgtNo=${idx}&mId=0301040000`
                console.log("viewUrl", viewUrl)
                return viewUrl
            }
        }


        console.log('상세 페이지 URL 구성 실패');
        return null;
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
                        'table.p-table', '#conts', '.content_box', '.program--contents',
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

                    // 의정부 첨부파일 처리
                    const fileLinks = document.querySelectorAll('a[href*="goDownload"], a[onclick*="goDownload"], .file a, .attach a');

                    fileLinks.forEach(link => {
                        const fileName = link.textContent.trim();
                        const href = link.href;
                        const onclick = link.getAttribute('onclick');
                        
                        // goDownload 함수 파라미터 추출
                        let downloadInfo = null;
                        if (onclick && onclick.includes('goDownload')) {
                            const match = onclick.match(/goDownload\s*\(\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*\)/);
                            if (match) {
                                downloadInfo = {
                                    userFileName: match[1],
                                    sysFileName: match[2],
                                    filePath: match[3]
                                };
                            }
                        } else if (href && href.includes('goDownload')) {
                            const match = href.match(/goDownload\s*\(\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*\)/);
                            if (match) {
                                downloadInfo = {
                                    userFileName: match[1],
                                    sysFileName: match[2],
                                    filePath: match[3]
                                };
                            }
                        }
                        
                        if (fileName && (href || onclick || downloadInfo)) {
                            attachments.push({
                                name: fileName,
                                url: href,
                                onclick: onclick,
                                downloadInfo: downloadInfo
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
     * fn_egov_downFile 함수 직접 실행 방식 (개선된 다운로드 처리)
     */
    async downloadViaPost(fileNm, sysFileNm, filePath, attachDir, fileName) {
        try {
            console.log('!!!!!!!!!!!!!함수 개선된 다운로드 시작 !!!!!!!!!!!!!!!!!!!!');

            // 파일명 디코딩 및 정리
            const cleanFileName = sanitize(decodeURIComponent(fileNm), { replacement: '_' });
            const expectedFilePath = path.join(attachDir, cleanFileName);
            console.log(`다운로드할 파일: ${cleanFileName}`);
            console.log(`저장 경로: ${expectedFilePath}`);

            // 1단계: CDP를 통한 다운로드 설정
            await this.setupDownloadBehavior(attachDir);

            // 2단계: 다운로드 이벤트 리스너 설정 (함수 실행 전에)
            const downloadPromise = new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    reject(new Error('다운로드 타임아웃 (60초)'));
                }, 60000); // 60초 타임아웃

                const downloadHandler = async (download) => {
                    try {
                        clearTimeout(timeout);

                        const suggestedFileName = download.suggestedFilename();
                        const finalFileName = suggestedFileName || cleanFileName;
                        const savePath = path.join(attachDir, sanitize(finalFileName, { replacement: '_' }));

                        console.log('!!!!!!!!!!다운로드 이벤트 감지!!!!!!!!!!!!!!', {
                            suggestedFileName,
                            finalFileName,
                            savePath
                        });

                        // 디렉토리가 없으면 생성
                        const saveDir = path.dirname(savePath);
                        fs.ensureDirSync(saveDir);
                        
                        await download.saveAs(savePath);

                        // 파일이 실제로 저장되었는지 확인
                        if (await fs.pathExists(savePath)) {
                            const stats = await fs.stat(savePath);
                            console.log(`✅ 파일 저장 성공: ${savePath} (${stats.size} bytes)`);

                            // 이벤트 리스너 제거
                            this.page.off('download', downloadHandler);
                            resolve({ success: true, savedPath: savePath, size: stats.size });
                        } else {
                            throw new Error('파일이 저장되지 않았습니다');
                        }
                    } catch (error) {
                        clearTimeout(timeout);
                        this.page.off('download', downloadHandler);
                        reject(error);
                    }
                };

                // 다운로드 이벤트 리스너 등록
                this.page.on('download', downloadHandler);

                console.log('다운로드 이벤트 리스너 설정 완료');
            });

            // 3단계: fn_egov_downFile 함수 실행 (디코딩된 파라미터 사용)
            console.log('!!!!!!!!!!!!!!!!!!!!! downloadViaPost 함수 실행 준비...');

            // URL 디코딩을 한 번만 수행 (과도한 인코딩 방지)
            const decodedFileNm = decodeURIComponent(fileNm);
            const decodedSysFileNm = decodeURIComponent(sysFileNm);

            console.log('@@디코딩된 파라미터:', {
                originalFileNm: fileNm,
                decodedFileNm: decodedFileNm,
                originalSysFileNm: sysFileNm,
                decodedSysFileNm: decodedSysFileNm,
                filePath: filePath
            });

            const execResult = await this.page.evaluate((params) => {
                const { decodedFileNm, decodedSysFileNm, filePath } = params;


                try {
                    // 
                    if (typeof goDownload === 'function') {
                        console.log("실제 함수를 바로 부른다!!!!!!!1")
                        goDownload(decodedFileNm, decodedSysFileNm, filePath);
                        return { success: true, method: 'direct_function_call' };
                    } else {
                        // 함수가 없으면 수동 폼 제출
                        const form = document.getElementById('fileForm') || document.createElement('form');
                        form.id = 'fileForm';
                        form.method = 'post';
                        form.action = 'https://eminwon.ui4u.go.kr/emwp/jsp/ofr/FileDown.jsp';
                        form.target = '_self';
                        form.style.display = 'none';

                        // 기존 input 제거 후 새로 추가
                        form.innerHTML = '';

                        const inputs = [
                            { name: 'user_file_nm', value: decodedFileNm },
                            { name: 'sys_file_nm', value: decodedSysFileNm },
                            { name: 'file_path', value: filePath }
                        ];

                        inputs.forEach(input => {
                            const hiddenInput = document.createElement('input');
                            hiddenInput.type = 'hidden';
                            hiddenInput.name = input.name;
                            hiddenInput.value = input.value;
                            form.appendChild(hiddenInput);
                        });

                        if (!document.body.contains(form)) {
                            document.body.appendChild(form);
                        }

                        console.log('폼 제출 실행 (디코딩된 값으로)...');
                        form.submit();
                        return { success: true, method: 'manual_form_submit' };
                    }
                } catch (error) {
                    console.error('함수 실행 오류:', error);
                    return { success: false, error: error.message };
                }
            }, { decodedFileNm, decodedSysFileNm, filePath });

            console.log('fn_egov_downFile 실행 결과:', execResult);

            // 4단계: 다운로드 완료 대기
            try {
                const downloadResult = await downloadPromise;
                console.log(`✅ 대구광역시 파일 다운로드 성공: ${downloadResult.savedPath}`);
                return downloadResult;
            } catch (downloadError) {
                console.log(`❌ 다운로드 이벤트 캐치 실패: ${downloadError.message}`);

                // Fallback: 네트워크 인터셉트 방식 시도
                return await this.downloadViaNetworkIntercept(fileNm, sysFileNm, filePath, attachDir, fileName);
            }

        } catch (error) {
            console.error('fn_egov_downFile 실행 중 오류:', error.message);
            throw error;
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

            // goDownload 함수 처리
            if (attachment.downloadInfo || attachment.onclick?.includes('goDownload')) {
                let userFileName, sysFileName, filePath;
                
                if (attachment.downloadInfo) {
                    userFileName = attachment.downloadInfo.userFileName;
                    sysFileName = attachment.downloadInfo.sysFileName;
                    filePath = attachment.downloadInfo.filePath;
                } else {
                    const match = attachment.onclick.match(/goDownload\s*\(\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*\)/);
                    if (match) {
                        [, userFileName, sysFileName, filePath] = match;
                    }
                }
                
                if (userFileName && sysFileName && filePath) {
                    // 파일명 처리 - 디코딩해서 실제 파일명 추출
                    try {
                        fileName = userFileName.includes('%') ? decodeURIComponent(userFileName) : userFileName;
                    } catch (e) {
                        fileName = userFileName;
                    }
                    
                    // 의정부시 eminwon 다운로드 URL 생성
                    // 파라미터가 이미 인코딩된 경우 그대로 사용, 아니면 인코딩
                    let finalUserFileName = userFileName;
                    let finalSysFileName = sysFileName;
                    let finalFilePath = filePath;
                    
                    // 파라미터가 이미 인코딩되어 있는지 확인 (% 포함 여부로 판단)
                    if (!userFileName.includes('%')) {
                        finalUserFileName = encodeURIComponent(userFileName);
                    }
                    if (!sysFileName.includes('%')) {
                        finalSysFileName = encodeURIComponent(sysFileName);
                    }
                    if (!filePath.includes('%')) {
                        finalFilePath = encodeURIComponent(filePath);
                    }
                    
                    downloadUrl = `https://eminwon.ui4u.go.kr/emwp/jsp/ofr/FileDown.jsp?user_file_nm=${finalUserFileName}&sys_file_nm=${finalSysFileName}&file_path=${finalFilePath}`;
                    actualDownloadUrl = downloadUrl;


                }
            }
            
            // 상대 URL을 절대 URL로 변환
            if (downloadUrl && !downloadUrl.startsWith('http')) {
                downloadUrl = new URL(downloadUrl, this.baseUrl).toString();
            }
            
            if (!downloadUrl || !downloadUrl.startsWith('http')) {
                console.log(`유효하지 않은 다운로드 URL: ${downloadUrl}`);
                return { 
                    fileName: attachment.name, 
                    downloadUrl: null,
                    error: 'Invalid URL'
                };
            }
            
            // 일반 다운로드 방식 사용
            await this.downloadViaLink(downloadUrl, attachDir, fileName);
            
            return {
                fileName: fileName,
                downloadUrl: actualDownloadUrl || downloadUrl
            };

        } catch (error) {
            console.error(`첨부파일 다운로드 실패 (${attachment.name}):`, error);
            return {
                fileName: attachment.name,
                downloadUrl: null,
                error: error.message
            };
        }
    }
    
    /**
     * 링크 방식 다운로드
     */
    async downloadViaLink(url, attachDir, fileName) {
        try {
            const response = await axios({
                method: 'GET',
                url: url,
                responseType: 'stream',
                timeout: 30000,
                headers: {
                    'Accept': '*/*',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                },
                httpsAgent: new https.Agent({
                    rejectUnauthorized: false
                })
            });
            
            // 파일명 결정
            const contentDisposition = response.headers['content-disposition'];
            if (contentDisposition) {
                const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
                if (utf8Match) {
                    try {
                        fileName = decodeURIComponent(utf8Match[1]);
                    } catch (e) {
                        console.log('UTF-8 파일명 디코딩 실패');
                    }
                }
            }
            
            const cleanFileName = sanitize(fileName, { replacement: '_' });
            const filePath = path.join(attachDir, cleanFileName);
            
            const writer = fs.createWriteStream(filePath);
            response.data.pipe(writer);
            
            return new Promise((resolve, reject) => {
                writer.on('finish', resolve);
                writer.on('error', reject);
            });
            
        } catch (error) {
            throw new Error(`링크 다운로드 실패: ${error.message}`);
        }
    }
    
    /**
     * 첨부파일 다운로드
     */
    async downloadAttachments(attachments, folderPath) {
        const downloadUrlInfo = {};
        try {
            const attachDir = path.join(folderPath, 'attachments');
            await fs.ensureDir(attachDir);
            
            console.log(`${attachments.length}개 첨부파일 다운로드 중...`);
            
            for (let i = 0; i < attachments.length; i++) {
                const attachment = attachments[i];
                const result = await this.downloadSingleAttachment(attachment, attachDir, i + 1);
                if (result) {
                    downloadUrlInfo[result.fileName || attachment.name] = result.downloadUrl;
                }
                await this.delay(500);
            }
            
            // 첨부파일에 다운로드 URL 정보 추가
            attachments.forEach(att => {
                if (downloadUrlInfo[att.name]) {
                    att.downloadUrl = downloadUrlInfo[att.name];
                }
            });
            
        } catch (error) {
            console.error('첨부파일 다운로드 실패:', error);
        }
        return downloadUrlInfo;
    }
    
    /**
     * 공고 저장
     */
    async saveAnnouncement(announcement, detailContent) {
        try {
            // 제목에서 '새글' 등 제거
            const cleanTitle = announcement.title
                .replace(/\s*\[새글\]\s*/g, '')
                .replace(/\s*NEW\s*/gi, '')
                .replace(/\s*\[진행중\]\s*/g, '')
                .replace(/\s*\[마감\]\s*/g, '')
                .replace(/\s*새글\s*/g, '')
                .trim();
            
            // 폴더명 생성
            const sanitizedTitle = sanitize(cleanTitle).substring(0, 100);
            const folderName = `${String(this.counter).padStart(3, '0')}_${sanitizedTitle}`;
            const folderPath = path.join(this.outputDir, folderName);
            
            await fs.ensureDir(folderPath);
            
            // 첨부파일 다운로드
            if (detailContent.attachments && detailContent.attachments.length > 0) {
                await this.downloadAttachments(detailContent.attachments, folderPath);
            }
            
            // content.md 생성
            const contentMd = this.generateMarkdownContent(announcement, detailContent);
            await fs.writeFile(path.join(folderPath, 'content.md'), contentMd, 'utf8');
            
            this.counter++;
            
        } catch (error) {
            console.error('공고 저장 실패:', error);
        }
    }
    
    /**
     * 마크다운 컨텐츠 생성
     */
    generateMarkdownContent(announcement, detailContent) {
        const lines = [];
        
        // 제목에서 '새글' 등 제거
        const cleanTitle = announcement.title
            .replace(/\s*\[새글\]\s*/g, '')
            .replace(/\s*NEW\s*/gi, '')
            .replace(/\s*\[진행중\]\s*/g, '')
            .replace(/\s*\[마감\]\s*/g, '')
            .replace(/\s*새글\s*/g, '')
            .trim();
        
        lines.push(`**제목**: ${cleanTitle}`);
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
                // 실제 다운로드 URL 생성
                let downloadUrl = att.downloadUrl;
                if (!downloadUrl && att.downloadInfo) {
                    // 파라미터가 이미 인코딩되어 있는지 확인하고 처리
                    let userFileName = att.downloadInfo.userFileName;
                    let sysFileName = att.downloadInfo.sysFileName;
                    let filePath = att.downloadInfo.filePath;
                    
                    // 이미 인코딩된 경우 그대로 사용, 아니면 인코딩
                    if (!userFileName.includes('%')) {
                        userFileName = encodeURIComponent(userFileName);
                    }
                    if (!sysFileName.includes('%')) {
                        sysFileName = encodeURIComponent(sysFileName);
                    }
                    if (!filePath.includes('%')) {
                        filePath = encodeURIComponent(filePath);
                    }
                    
                    downloadUrl = `https://eminwon.ui4u.go.kr/emwp/jsp/ofr/FileDown.jsp?user_file_nm=${userFileName}&sys_file_nm=${sysFileName}&file_path=${filePath}`;
                }
                downloadUrl = downloadUrl || att.url;
                lines.push(`${i + 1}. ${att.name}:${downloadUrl}`);
            });
        }
        
        return lines.join('\n');
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

    const scraper = new Ui4uScraper({
        targetYear: argv.year,
        outputDir: argv.output,
        targetDate: argv.date ? moment(argv.date) : null,
        goPage: argv.page
    });

    scraper.scrape().catch(console.error);
}

module.exports = Ui4uScraper;
