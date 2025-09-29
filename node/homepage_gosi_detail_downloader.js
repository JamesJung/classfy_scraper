#!/usr/bin/env node

/**
 * 통합 상세 다운로더
 * DB의 pending 상태 항목들을 다운로드
 * 
 * 사용법:
 * node general_detail_downloader.js <site_code> [options]
 * node general_detail_downloader.js anseong --limit 10
 * node general_detail_downloader.js --url <url> --site <site_code>
 */

const { chromium } = require('playwright');
const mysql = require('mysql2/promise');
const fs = require('fs-extra');
const path = require('path');
const moment = require('moment');
const axios = require('axios');
const https = require('https');
const sanitize = require('sanitize-filename');
const yargs = require('yargs');
const TurndownService = require('turndown');

class HomepageGosiDetailDownloader {
    constructor(siteCode, options = {}) {
        this.siteCode = siteCode;
        this.limit = options.limit || 100;
        this.verbose = options.verbose || false;
        this.testMode = options.test || false;
        this.specificUrl = options.url || null;

        // 설정 파일 로드
        this.configPath = path.join(__dirname, 'configs', `${siteCode}.json`);
        if (!fs.existsSync(this.configPath)) {
            throw new Error(`설정 파일이 없습니다: ${this.configPath}`);
        }

        this.config = require(this.configPath);

        // 출력 디렉토리
        this.baseOutputDir = options.outputDir || 'scraped_incremental';
        const today = moment().format('YYYY-MM-DD');
        this.outputDir = path.join(this.baseOutputDir, today, this.siteCode);

        // HTML to Markdown 변환기
        this.turndownService = new TurndownService({
            headingStyle: 'atx',
            codeBlockStyle: 'fenced'
        });

        // 통계
        this.stats = {
            total: 0,
            success: 0,
            failed: 0,
            skipped: 0
        };

        this.browser = null;
        this.db = null;
        this.folderCounter = 1;
    }

    /**
     * 데이터베이스 연결
     */
    async connectDB() {
        require('dotenv').config();

        this.db = await mysql.createConnection({
            host: process.env.DB_HOST || 'localhost',
            port: process.env.DB_PORT || 3306,
            user: process.env.DB_USER || 'scraper',
            password: process.env.DB_PASSWORD,
            database: process.env.DB_NAME || 'opendata'
        });

        if (this.verbose) {
            console.log('✓ 데이터베이스 연결 완료');
        }
    }

    /**
     * 브라우저 초기화
     */
    async initBrowser() {
        this.browser = await chromium.launch({
            headless: !this.testMode,
            timeout: 30000
        });

        // 다운로드 설정
        const context = await this.browser.newContext({
            acceptDownloads: true,
            userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        });

        if (this.verbose) {
            console.log('✓ 브라우저 초기화 완료');
        }


        return context;
    }

    /**
     * 대기 중인 항목 조회
     */
    async getPendingItems() {
        let query;
        let params;

        if (this.specificUrl) {
            // 특정 URL만 처리
            query = `
                SELECT id, announcement_url, announcement_id, title, post_date, category, department
                FROM homepage_gosi_url_registry
                WHERE site_code = ? AND announcement_url = ?
                LIMIT 1
            `;
            params = [this.siteCode, this.specificUrl];
        } else {
            // pending 상태 항목들 처리
            query = `
                SELECT id, announcement_url, announcement_id, title, post_date, category, department
                FROM homepage_gosi_url_registry
                WHERE site_code = ? AND status = 'pending'
                ORDER BY first_seen_date DESC
                LIMIT ?
            `;
            params = [this.siteCode, this.limit];
        }

        const [rows] = await this.db.execute(query, params);
        return rows;
    }

    /**
     * 상태 업데이트
     */
    async updateStatus(id, status, folderName = null, errorMessage = null) {
        const query = `
            UPDATE homepage_gosi_url_registry 
            SET status = ?, 
                folder_name = ?,
                error_message = ?,
                last_checked_date = NOW(),
                downloaded_at = CASE WHEN ? = 'completed' THEN NOW() ELSE NULL END
            WHERE id = ?
        `;

        await this.db.execute(query, [status, folderName, errorMessage, status, id]);
    }

    /**
     * 폴더명 생성
     */
    createFolderName(item) {
        const counter = String(this.folderCounter++).padStart(3, '0');
        const safeTitle = sanitize(item.title || '제목없음')
            .substring(0, 100)
            .replace(/\s+/g, '_');

        return `${counter}_${safeTitle}`;
    }

    /**
     * 콘텐츠 추출
     */
    async extractContent(page, item) {
        const config = this.config.selectors.detail;

        if (this.verbose) {
            console.log("detail selectors:", config);
        }


        console.log("!!!!!extractContent!!!")
        // attachment_extractors.js 파일 읽기
        const extractorsPath = path.join(__dirname, 'attachment_extractors.js');
        const extractorsCode = fs.readFileSync(extractorsPath, 'utf8');

        try {
            // 셀렉터 기반 추출 (content와 attachments만)
            const content = await page.evaluate((params) => {
                const { config, extractorsCode } = params;

                // extractors 코드를 브라우저 컨텍스트에 주입
                eval(extractorsCode);

                const data = {};

                // 내용 - 여러 후보 selector 시도
                const contentSelectors = [
                    config.content,
                    '.board_view',
                    '#board_basic_view',
                    '.bbs1view1',
                    '.contents_wrap',
                    '.program--contents',
                    '.view-content',
                    'div.table-responsive',
                ];

                let contentEl = null;
                for (const selector of contentSelectors) {
                    const element = document.querySelector(selector);
                    if (element) {
                        contentEl = element;
                        break;
                    }
                }


                if (!contentEl) {
                    contentEl = document.body;
                }

                // 불필요한 태그 제거
                const clonedContent = contentEl.cloneNode(true);
                clonedContent.querySelectorAll('script, style, nav, header, footer, .header, .footer, .nav, .menu, .sidebar, .snb, .gnb, .lnb, .breadcrumb, button, .btn').forEach(el => el.remove());

                // innerText로 텍스트만 추출
                data.content = clonedContent.innerText || clonedContent.textContent || '';


                // 첨부파일 추출
                data.attachments = [];

                if (config.attachments) {
                    // Type 1: Custom extractor (사이트별 특수 로직)
                    if (typeof config.attachments === 'object' && config.attachments.type === 'custom') {
                        const extractorName = config.attachments.extractorName;
                        // window.attachmentExtractors에서 함수 가져오기
                        if (window.attachmentExtractors && window.attachmentExtractors[extractorName]) {
                            data.attachments = window.attachmentExtractors[extractorName](document, config);
                        } else {
                            console.error(`Extractor not found: ${extractorName}`);
                        }

                    }
                    // Type 2: JavaScript 함수 호출 (goDownload 등)
                    else if (typeof config.attachments === 'object' && config.attachments.type === 'javascript') {
                        console.log("JavaScript 함수 호출 (goDownload 등)")
                        if (window.attachmentExtractors && window.attachmentExtractors.javascript_function) {

                            data.attachments = window.attachmentExtractors.javascript_function(document, config);
                        }
                    }
                    // Type 3: Direct URL (일반 href)
                    else {
                        if (window.attachmentExtractors && window.attachmentExtractors.direct_url) {
                            data.attachments = window.attachmentExtractors.direct_url(document, config);
                        }
                    }
                }

                // 원본 URL
                data.url = window.location.href;

                return data;

            }, { config, extractorsCode });

            // DB에서 가져온 정보 추가
            content.title = item.title;
            content.date = item.post_date ? moment(item.post_date).format('YYYY-MM-DD') : null;
            content.url = page.url();

            return content;

        } catch (error) {
            console.error('콘텐츠 추출 오류:', error);

            // 폴백: 전체 body 추출
            return {
                title: item.title || '제목 없음',
                date: item.post_date ? moment(item.post_date).format('YYYY-MM-DD') : null,
                content: await page.content(),
                url: page.url(),
                attachments: []
            };
        }
    }

    /**
     * Markdown 파일 생성 (eminwon_scraper.js 포맷과 동일하게)
     */
    formatContentMd(content) {
        const lines = [];

        // 제목
        lines.push(`**제목**: ${content.title || '제목 없음'}`);
        lines.push('');

        // 원본 URL
        lines.push(`**원본 URL**: ${content.url}`);
        lines.push('');

        // 작성일
        if (content.date) {
            lines.push(`**작성일**: ${content.date}`);
            lines.push('');
        }

        // 내용
        if (content.content) {
            lines.push('**내용**:');
            lines.push('');
            // HTML을 Markdown으로 변환
            const markdown = this.turndownService.turndown(content.content);
            lines.push(markdown);
        }

        // 첨부파일
        if (content.attachments && content.attachments.length > 0) {
            lines.push('');
            lines.push('**첨부파일**:');
            lines.push('');
            content.attachments.forEach((file, index) => {
                const url = file.actualUrl || file.url;
                // 파일명 디코딩 (URL 인코딩된 경우)
                let displayName = file.name;
                try {
                    if (displayName && displayName.includes('%')) {
                        displayName = decodeURIComponent(displayName);
                    }
                } catch (e) {
                    // 디코딩 실패시 원본 사용
                }
                lines.push(`${index + 1}. ${displayName}: ${url}`);
                lines.push('');
            });
        }

        return lines.join('\n');
    }

    /**
     * 첨부파일 다운로드
     */
    async downloadAttachments(page, attachments, folderPath) {
        const attachDir = path.join(folderPath, 'attachments');
        await fs.ensureDir(attachDir);

        console.log(`${attachments.length}개 첨부파일 다운로드 중...`);
        const downloadResults = {};

        for (let i = 0; i < attachments.length; i++) {
            const attachment = attachments[i];
            const downloadResult = await this.downloadSingleAttachment(page, attachment, attachDir, i + 1);
            if (downloadResult) {
                const fileName = attachment.name || `attachment_${i + 1}`;
                downloadResults[fileName] = downloadResult;
            }
            await this.delay(500);
        }

        if (Object.keys(downloadResults).length > 0) {
            console.log('\n첨부 파일 => 파일명:실제 다운로드 URL');
            for (const [fileName, result] of Object.entries(downloadResults)) {
                const url = result.actualDownloadUrl || 'N/A';
                console.log(`${fileName} : ${url}`);
            }
        }

        return downloadResults;
    }

    /**
     * CDP를 통한 다운로드 동작 설정
     */
    async setupDownloadBehavior(page, downloadPath) {
        try {
            console.log(`CDP 다운로드 설정 - 경로: ${downloadPath}`);
            const client = await page.context().newCDPSession(page);
            await client.send('Page.setDownloadBehavior', {
                behavior: 'allow',
                downloadPath: downloadPath
            });
            await client.send('Browser.setDownloadBehavior', {
                behavior: 'allow',
                downloadPath: downloadPath
            });
            console.log('✅ CDP 다운로드 설정 완료');
            return client;
        } catch (error) {
            console.warn(`⚠️ CDP 설정 실패 (계속 진행): ${error.message}`);
            return null;
        }
    }

    /**
     * goDownload 함수 - Playwright download 이벤트와 폼 제출 방식
     * 혹시 몰라 이 부분을 남겨준다.
     */
    async downloadViaGoDownload(page, userFileNm, sysFileNm, filePath, attachDir, fileName, functionName) {
        try {
            console.log('goDownload 함수 다운로드 시작 (Playwright 방식)...');

            // 파일명 디코딩 및 정리
            const cleanFileName = sanitize(decodeURIComponent(userFileNm), { replacement: '_' });
            const expectedFilePath = path.join(attachDir, cleanFileName);

            // 1단계: CDP를 통한 다운로드 설정
            await this.setupDownloadBehavior(page, attachDir);

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

                        console.log('다운로드 이벤트 감지:', {
                            suggestedFileName,
                            finalFileName,
                            savePath
                        });

                        await download.saveAs(savePath);

                        // 파일이 실제로 저장되었는지 확인
                        if (await fs.pathExists(savePath)) {
                            const stats = await fs.stat(savePath);
                            console.log(`✅ 파일 저장 성공: ${savePath} (${stats.size} bytes)`);

                            // 이벤트 리스너 제거
                            page.off('download', downloadHandler);
                            resolve({ success: true, savedPath: savePath, size: stats.size });
                        } else {
                            throw new Error('파일이 저장되지 않았습니다');
                        }
                    } catch (error) {
                        clearTimeout(timeout);
                        page.off('download', downloadHandler);
                        reject(error);
                    }
                };

                // 다운로드 이벤트 리스너 등록
                page.on('download', downloadHandler);

                console.log('다운로드 이벤트 리스너 설정 완료');
            });

            // URL 디코딩을 한 번만 수행 (과도한 인코딩 방지)
            const decodedFileNm = decodeURIComponent(userFileNm);
            const decodedSysFileNm = decodeURIComponent(sysFileNm);

            console.log('디코딩된 파라미터:', {
                originalFileNm: userFileNm,
                decodedFileNm: decodedFileNm,
                originalSysFileNm: sysFileNm,
                decodedSysFileNm: decodedSysFileNm,
                filePath: filePath
            });

            const execResult = await page.evaluate((params) => {
                const { decodedFileNm, decodedSysFileNm, filePath, functionName, baseUrl } = params;
                // baseUrl에서 도메인 추출 후 eminwon 서브도메인으로 변경
                const domain = baseUrl.match(/https?:\/\/(?:www\.)?([^\/]+)/)[1];
                const downloadEndpoint = `https://eminwon.${domain}/emwp/jsp/ofr/FileDownNew.jsp`;

                try {
                    // config에서 지정된 다운로드 함수 호출
                    if (typeof window[functionName] === 'function') {
                        window[functionName](decodedFileNm, decodedSysFileNm, filePath);
                        return { success: true, method: 'direct_function_call', usedFunction: functionName };
                    } else {
                        // 함수가 없으면 수동 폼 제출
                        const form = document.getElementById('fileForm') || document.createElement('form');
                        form.id = 'fileForm';
                        form.method = 'post';
                        form.action = downloadEndpoint;
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
            }, { decodedFileNm, decodedSysFileNm, filePath, functionName, baseUrl: this.config.baseUrl });

            // console.log('downFile 실행 결과:', execResult);

            // 4단계: 다운로드 완료 대기
            try {
                const downloadResult = await downloadPromise;
                console.log(`✅ 파일 다운로드 성공: ${downloadResult.savedPath}`);
                return downloadResult;
            } catch (downloadError) {
                console.log(`❌ 다운로드 이벤트 캐치 실패: ${downloadError.message}`);

                // Fallback: 네트워크 인터셉트 방식 시도
                return await this.downloadViaNetworkIntercept(page, userFileNm, sysFileNm, filePath, attachDir, fileName);

                // Fallback: 네트워크 인터셉트 방식 시도
                // throw downloadError
            }

        } catch (error) {
            console.error('downFile 실행 중 오류:', error.message);
            throw error;
        }
    }

    /**
     * GM 사이트 POST 방식 다운로드 (gm_scraper 방식)
     */
    async downloadViaGmPost(param1, param2, param3, attachDir, fileName, functionName) {
        try {
            const baseUrl = this.config.baseUrl;
            const domain = baseUrl.match(/https?:\/\/(?:www\.)?([^\/]+)/)[1];
            const downloadUrl = `https://eminwon.${domain}/emwp/jsp/ofr/FileDownNew.jsp`;

            console.log(`GM POST 다운로드 시작: ${downloadUrl}`);
            console.log('파라미터:', { param1, param2, param3 });

            const formData = new URLSearchParams();
            formData.append('sys_file_nm', param1);    // 첫 번째 = 시스템 파일명
            formData.append('user_file_nm', param2);   // 두 번째 = 원본 파일명
            formData.append('file_path', param3);

            const response = await axios({
                method: 'POST',
                url: downloadUrl,
                data: formData.toString(),
                responseType: 'stream',
                timeout: 30000,
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': '*/*',
                    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': baseUrl
                },
                maxRedirects: 5
            });

            const cleanFileName = sanitize(fileName, { replacement: '_' });
            const filePath = path.join(attachDir, cleanFileName);

            await fs.ensureDir(attachDir);
            console.log(`파일 저장: ${filePath}`);

            const writer = fs.createWriteStream(filePath);
            response.data.pipe(writer);

            return new Promise((resolve, reject) => {
                writer.on('finish', () => {
                    console.log(`GM POST 다운로드 완료: ${cleanFileName}`);
                    resolve({
                        success: true,
                        fileName: cleanFileName,
                        downloadMethod: 'GM_POST',
                        actualDownloadUrl: `${downloadUrl}?sys_file_nm=${encodeURIComponent(param2)}&user_file_nm=${encodeURIComponent(param1)}&file_path=${encodeURIComponent(param3)}`
                    });
                });
                writer.on('error', reject);
            });

        } catch (error) {
            console.error(`GM POST 다운로드 실패: ${error.message}`);
            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * 네트워크 인터셉트를 통한 파일 다운로드 (강력한 fallback)
     * 현재 이걸로 사용한다.
     */
    async downloadViaNetworkIntercept(page, fileNm, sysFileNm, filePath, attachDir, fileName, functionName) {
        try {

            const cleanFileName = sanitize(fileName, { replacement: '_' });
            const savePath = path.join(attachDir, cleanFileName);

            const baseUrl = this.config.baseUrl
            // 실제 다운로드 URL 구성
            const domain = baseUrl.match(/https?:\/\/(?:www\.)?([^\/]+)/)[1];

            // FileDown.jsp와 FileDownNew.jsp 두 가지 URL 준비
            const downloadUrls = [
                `https://eminwon.${domain}/emwp/jsp/ofr/FileDown.jsp`,
                `https://eminwon.${domain}/emwp/jsp/ofr/FileDownNew.jsp`
            ];

            const downloadParams = {
                user_file_nm: decodeURIComponent(fileNm),
                sys_file_nm: decodeURIComponent(sysFileNm),
                file_path: filePath
            };

            // console.log('네트워크 인터셉트 - 두 가지 다운로드 URL 시도:', downloadUrls);

            // 네트워크 요청 인터셉트 설정
            let cleanupTimer = null;
            let currentDownloadUrl = null; // 현재 시도 중인 다운로드 URL 추적

            const interceptPromise = new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    reject(new Error('네트워크 인터셉트 타임아웃'));
                }, 30000);

                const requestHandler = async (route) => {
                    const request = route.request();

                    if (request.url().includes('FileDown.jsp') || request.url().includes('FileDownNew.jsp')) {
                        // 요청된 URL과 POST 데이터를 파싱하여 전체 URL 구성
                        const baseUrl = request.url();
                        const postData = request.postData();

                        // POST 데이터를 파싱하여 파라미터 추출
                        let fullUrl = baseUrl;
                        if (postData) {
                            const params = new URLSearchParams(postData);
                            fullUrl = `${baseUrl}?${params.toString()}`;
                        }

                        currentDownloadUrl = fullUrl;
                        // console.log('FileDown.jsp 또는 FileDownNew.jsp 요청 인터셉트:', currentDownloadUrl);
                        // console.log('POST 데이터:', postData);

                        try {
                            // 원래 요청을 그대로 실행하고 응답 받기
                            const response = await route.fetch();
                            const buffer = await response.body();

                            // console.log(`응답 수신: ${response.status()} - ${buffer.length} bytes`);

                            // 응답이 파일인지 확인 (HTML 에러 페이지가 아닌지)
                            const contentType = response.headers()['content-type'] || '';
                            const contentDisposition = response.headers()['content-disposition'] || '';

                            // 파일명 추출
                            let suggestedFileName = cleanFileName;
                            if (contentDisposition) {
                                const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                                if (filenameMatch) {
                                    suggestedFileName = filenameMatch[1].replace(/['"]/g, '').trim();
                                    if (suggestedFileName.includes('%')) {
                                        try {
                                            suggestedFileName = decodeURIComponent(suggestedFileName);
                                        } catch (e) {
                                            console.log('파일명 디코딩 실패:', e.message);
                                        }
                                    }
                                }
                            }

                            if (buffer.length > 200 && !contentType.includes('text/html')) {
                                // 파일 저장
                                await fs.writeFile(savePath, buffer);

                                // 저장 확인
                                if (await fs.pathExists(savePath)) {
                                    const stats = await fs.stat(savePath);
                                    console.log(`✅ 네트워크 인터셉트로 파일 저장 성공: ${savePath} (${stats.size} bytes)`);
                                    console.log(`📎 실제 다운로드 URL: ${currentDownloadUrl}`);

                                    clearTimeout(timeout);

                                    // cleanup timer도 정리
                                    if (cleanupTimer) {
                                        clearTimeout(cleanupTimer);
                                    }

                                    // route는 계속 진행
                                    route.continue();

                                    // 실제 저장된 파일명 사용 (cleanFileName = 디코딩된 한글 파일명)
                                    resolve({
                                        success: true,
                                        savedPath: savePath,
                                        size: stats.size,
                                        actualDownloadUrl: currentDownloadUrl,
                                        downloadMethod: 'NetworkIntercept',
                                        fileName: cleanFileName,  // suggestedFileName 대신 cleanFileName 사용
                                        contentType: contentType
                                    });
                                    return;
                                }
                            } else {
                                console.log('응답이 파일이 아닌 것으로 판단:', {
                                    contentType,
                                    size: buffer.length,
                                    preview: buffer.toString('utf-8', 0, 100)
                                });
                            }

                            // 정상 응답이 아니면 계속 진행
                            route.continue();

                        } catch (error) {
                            console.error('네트워크 인터셉트 처리 중 오류:', error);
                            route.continue();
                        }
                    } else {
                        // 다른 요청은 그대로 통과
                        route.continue();
                    }
                };

                // 라우트 설정
                page.route('**/*', requestHandler);

                // 5초 후 라우트 해제 (무한 대기 방지)
                cleanupTimer = setTimeout(() => {
                    // 페이지가 닫히지 않았을 때만 unroute 실행
                    if (!page.isClosed()) {
                        page.unroute('**/*', requestHandler).catch(() => {
                            // 페이지가 닫혔으면 무시
                        });
                    }
                }, 55000);
            });

            // downFile 함수 재실행 (디코딩된 파라미터 사용)
            const decodedFileNm = decodeURIComponent(fileNm);
            const decodedSysFileNm = decodeURIComponent(sysFileNm);

            // 두 URL 순차적으로 시도
            let result = null;
            for (const downloadUrl of downloadUrls) {
                console.log(`⏳ ${downloadUrl} 시도 중... (functionName: ${functionName})`);

                // 파라미터가 포함된 전체 다운로드 URL 생성
                const fullDownloadUrl = `${downloadUrl}?user_file_nm=${encodeURIComponent(decodedFileNm)}&sys_file_nm=${encodeURIComponent(decodedSysFileNm)}&file_path=${encodeURIComponent(filePath)}`;

                const evalResult = await page.evaluate((params) => {
                    const { decodedFileNm, decodedSysFileNm, filePath, functionName, downloadUrl } = params;

                    if (typeof window[functionName] === 'function') {
                        console.log(`${functionName} 함수 호출`);
                        window[functionName](decodedFileNm, decodedSysFileNm, filePath);
                        return { success: true, method: 'function_call' };
                    } else {
                        console.log(`${functionName} 함수 없음 - 폼 제출`);
                        // 수동 폼 제출
                        const form = document.createElement('form');
                        form.method = 'post';
                        form.action = downloadUrl;
                        form.style.display = 'none';

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

                        document.body.appendChild(form);
                        form.submit();
                        form.remove();
                        return { success: true, method: 'form_submit' };
                    }
                }, { decodedFileNm, decodedSysFileNm, functionName, filePath, downloadUrl });

                console.log('Evaluate 결과:', evalResult);

                // 2초 대기하여 다운로드 완료 확인
                await page.waitForTimeout(2000);

                // 파일이 저장되었는지 확인
                if (await fs.pathExists(savePath)) {
                    const stats = await fs.stat(savePath);
                    if (stats.size > 200) {
                        // console.log(`✅ ${downloadUrl}로 다운로드 성공`);
                        result = {
                            success: true,
                            savedPath: savePath,
                            size: stats.size,
                            actualDownloadUrl: fullDownloadUrl,  // 파라미터 포함된 전체 URL
                            downloadMethod: 'NetworkIntercept',
                            fileName: cleanFileName,
                            contentType: 'application/octet-stream'
                        };
                        break;
                    }
                }
            }

            // 네트워크 인터셉트 결과 대기 (5초 타임아웃)
            if (!result) {
                try {
                    result = await Promise.race([
                        interceptPromise,
                        new Promise((_, reject) => setTimeout(() => reject(new Error('파일 다운로드 타임아웃')), 5000))
                    ]);
                } catch (e) {
                    console.log(`⚠️ 다운로드 실패: ${e.message}`);
                }
            }

            if (!result || !result.success) {
                throw new Error('두 가지 다운로드 URL 모두 실패');
            }

            // console.log(`📁 네트워크 인터셉트 다운로드 완료:`, {
            //     fileName: result.fileName,
            //     actualUrl: result.actualDownloadUrl,
            //     method: result.downloadMethod
            // });
            return result;

        } catch (error) {
            console.error('네트워크 인터셉트 다운로드 실패:', error.message);
            throw error;
        }
    }



    /**
     * 단일 첨부파일 다운로드
     */
    async downloadSingleAttachment(page, attachment, attachDir, index) {
        const startTime = Date.now();
        console.log(`\n📥 === 첨부파일 다운로드 시작 (${index}) ===`);
        // console.log(`파일명: ${attachment.name}`);
        // console.log(`URL: ${attachment.url}`);

        try {
            let downloadUrl = attachment.url;
            let downloadOnClick = attachment.onclick || "";

            let fileName = attachment.name || `attachment_${index}`;


            // config에서 downloadFunction 읽기 (실제 다운로드 함수 이름)
            const downloadFunction = this.config?.selectors?.detail?.attachments?.downloadFunction || 'goDownload';

            // 동적으로 함수 패턴 생성 (goDownload, fn_egov_downFile 등)
            const functionPattern = `${downloadFunction}\\s*\\(\\s*'([^']+)'\\s*,\\s*'([^']+)'\\s*,\\s*'([^']+)'\\s*\\)`;
            const functionRegex = new RegExp(functionPattern);
            const urlFunctionMatches = downloadUrl.match(functionRegex);
            const onclickFunctionMatches = downloadOnClick.match(functionRegex);


            if (urlFunctionMatches) {
                const [, userFileNm, sysFileNm, filePath] = urlFunctionMatches;

                let displayFileName = fileName;
                try {
                    if (userFileNm && userFileNm.includes('%')) {
                        displayFileName = decodeURIComponent(userFileNm);
                    }
                } catch (e) {
                    displayFileName = userFileNm || fileName;
                }

                console.log(`🎯 ${downloadFunction} 패턴 감지:`, {
                    userFileNm: userFileNm,
                    sysFileNm: sysFileNm,
                    filePath: filePath,
                    fileName: displayFileName,
                    downloadFunction: downloadFunction
                });

                const downloadResult = await this.downloadViaNetworkIntercept(page, userFileNm, sysFileNm, filePath, attachDir,
                    displayFileName, downloadFunction);

                if (downloadResult && downloadResult.success) {
                    const elapsed = Date.now() - startTime;
                    console.log(`✅ goDownload 방식으로 다운로드 성공!`);
                    console.log(`📊 처리 시간: ${elapsed}ms`);
                    return downloadResult;
                } else {
                    throw new Error('goDownload 다운로드 실패');
                }
            } else if (onclickFunctionMatches) {
                const [, param1, param2, param3] = onclickFunctionMatches;

                console.log(`🎯 ${downloadFunction} 패턴 감지 (onclick):`, {
                    param1: param1,
                    param2: param2,
                    param3: param3,
                    fileName: fileName,
                    downloadFunction: downloadFunction
                });

                
                const downloadResult = await this.downloadViaGmPost(
                    param1, param2, param3,
                    attachDir, fileName, downloadFunction
                );

                if (downloadResult && downloadResult.success) {
                    const elapsed = Date.now() - startTime;
                    console.log(`✅ ${downloadFunction} (POST) 방식으로 다운로드 성공!`);
                    console.log(`📊 처리 시간: ${elapsed}ms`);
                    return downloadResult;
                } else {
                    throw new Error(`${downloadFunction} (POST) 다운로드 실패`);
                }
            } else {
                // Direct URL 방식 (타입 3)
                console.log('🔗 Direct URL 다운로드 방식', downloadUrl);

                // 상대 URL을 절대 URL로 변환
                if (downloadUrl && !downloadUrl.startsWith('http')) {
                    console.log('상대 URL을 절대 URL로 변환');
                    downloadUrl = new URL(downloadUrl, this.config.baseUrl).toString();
                    console.log('변환된 URL:', downloadUrl);
                }

                if (!downloadUrl || !downloadUrl.startsWith('http')) {
                    console.log(`❌ 유효하지 않은 다운로드 URL: ${downloadUrl}`);
                    return { success: false, reason: 'invalid_url' };
                }

                // 링크 방식 다운로드 실행
                await this.downloadViaLink(downloadUrl, attachDir, fileName);

                const elapsed = Date.now() - startTime;
                console.log(`✅ Direct URL 방식으로 다운로드 성공!`);
                console.log(`📊 처리 시간: ${elapsed}ms`);

                return {
                    success: true,
                    fileName: fileName,
                    downloadMethod: 'DirectURL',
                    actualDownloadUrl: downloadUrl
                };
            }

        } catch (error) {
            const elapsed = Date.now() - startTime;
            console.error(`❌ 첨부파일 다운로드 실패 (${elapsed}ms):`, error.message);
            return { success: false, error: error.message };
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
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                },
                httpsAgent: new https.Agent({
                    rejectUnauthorized: false // SSL 인증서 검증 비활성화
                })
            });

            // 파일명 결정 (한글명 지원)
            const contentDisposition = response.headers['content-disposition'];

            // goDownload에서 온 원본 파일명이 있는 경우 우선 사용 (한글 보존)
            const isFromGoDownload = fileName && !fileName.startsWith('attachment_');

            if (!isFromGoDownload && contentDisposition) {
                // goDownload가 아닌 경우에만 Content-Disposition에서 파일명 추출
                let extractedFileName = null;

                // 1순위: UTF-8 인코딩된 파일명 처리 (filename*=UTF-8''encoded-name)
                const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
                if (utf8Match) {
                    try {
                        extractedFileName = decodeURIComponent(utf8Match[1]);
                        console.log('UTF-8 파일명 추출:', extractedFileName);
                    } catch (e) {
                        console.log('UTF-8 파일명 디코딩 실패:', e.message);
                    }
                }

                // 2순위: 일반 filename 처리
                if (!extractedFileName) {
                    const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                    if (match) {
                        extractedFileName = match[1].replace(/['"]/g, '').trim();

                        // URL 인코딩된 경우 디코딩 시도
                        if (extractedFileName.includes('%')) {
                            try {
                                const decoded = decodeURIComponent(extractedFileName);
                                extractedFileName = decoded;
                            } catch (e) {
                                console.log('파일명 디코딩 실패:', e.message);
                            }
                        }
                    }
                }

                // 추출된 파일명이 있고, 유효한 경우에만 사용
                if (extractedFileName && extractedFileName.trim() && extractedFileName !== 'attachment') {
                    fileName = extractedFileName;
                    // console.log('Content-Disposition에서 파일명 사용:', fileName);
                }
            } else if (isFromGoDownload) {
                // console.log('goDownload 원본 파일명 우선 사용:', fileName);
            }

            // 파일명 정리 (한글 보존)
            const cleanFileName = sanitize(fileName, { replacement: '_' });
            const filePath = path.join(attachDir, cleanFileName);

            // console.log(`최종 파일명: ${cleanFileName}`);
            // console.log(`저장 경로: ${filePath}`);

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
     * 지연 함수
     */
    async delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * 단일 항목 처리
     */
    async processItem(context, item) {
        const page = await context.newPage();
        page.on('console', (msg) => {
            console.log(`[브라우저 콘솔]: ${msg.text()}`);
        });


        this.stats.total++;

        console.log(`\n[${this.stats.total}] ${item.title?.substring(0, 50)}...`);

        try {
            // 상태 업데이트: downloading
            await this.updateStatus(item.id, 'downloading');

            // 상세 페이지 이동
            await page.goto(item.announcement_url, {
                waitUntil: 'networkidle',
                timeout: 30000
            });

            // 동적 컨텐츠 대기
            await page.waitForTimeout(2000);

            // 콘텐츠 추출
            const content = await this.extractContent(page, item);

            // 폴더 생성
            const folderName = this.createFolderName(item);
            const folderPath = path.join(this.outputDir, folderName);

            if (this.verbose) {
                console.log(`  Creating folder: ${folderPath}`);
            }

            await fs.ensureDir(folderPath);


            // content.md 저장
            const contentMd = this.formatContentMd(content);
            const contentFile = path.join(folderPath, 'content.md');

            if (this.verbose) {
                console.log(`  Writing content.md to: ${contentFile}`);
            }

            await fs.writeFile(contentFile, contentMd, 'utf-8');

            // content hash 생성
            const crypto = require('crypto');
            const contentHash = crypto.createHash('sha256')
                .update(contentMd)
                .digest('hex');

            // 첨부파일 다운로드
            if (content.attachments && content.attachments.length > 0) {
                console.log(`  첨부파일: ${content.attachments.length}개`);
                const downloadResults = await this.downloadAttachments(page, content.attachments, folderPath);

                // 다운로드 성공한 파일의 실제 URL과 파일명으로 업데이트
                content.attachments.forEach((att, i) => {
                    const fileName = att.name || `attachment_${i + 1}`;
                    console.log(`\n[업데이트] 파일명: ${fileName}`);
                    console.log(`  downloadResults에 존재: ${!!downloadResults[fileName]}`);

                    if (downloadResults && downloadResults[fileName]) {
                        console.log(`  다운로드 결과:`, downloadResults[fileName]);
                        att.actualUrl = downloadResults[fileName].actualDownloadUrl || att.url;
                        console.log(`  actualUrl 업데이트: ${att.actualUrl}`);

                        // 추출된 실제 파일명으로 업데이트
                        if (downloadResults[fileName].fileName) {
                            att.name = downloadResults[fileName].fileName;
                            console.log(`  파일명 업데이트: ${att.name}`);
                        }
                    } else {
                        console.log(`  ⚠️ downloadResults에서 "${fileName}" 키를 찾을 수 없음`);
                        console.log(`  사용 가능한 키:`, Object.keys(downloadResults));
                    }
                });

                // 업데이트된 attachment 정보로 content.md 재생성
                const updatedContentMd = this.formatContentMd(content);
                await fs.writeFile(contentFile, updatedContentMd, 'utf-8');

                // DB 업데이트
                await this.db.execute(
                    'UPDATE homepage_gosi_url_registry SET has_attachments = TRUE, attachment_count = ? WHERE id = ?',
                    [content.attachments.length, item.id]
                );
            }

            // 상태 업데이트: completed (content_hash 포함)
            await this.db.execute(
                'UPDATE homepage_gosi_url_registry SET status = ?, folder_name = ?, content_hash = ?, last_checked_date = NOW(), downloaded_at = NOW() WHERE id = ?',
                ['completed', folderName, contentHash, item.id]
            );
            this.stats.success++;

            console.log(`  ✓ 완료: ${folderPath}`);

        } catch (error) {
            console.error(`  ✗ 오류: ${error.message}`);

            // 상태 업데이트: failed
            await this.updateStatus(item.id, 'failed', null, error.message);
            this.stats.failed++;

            // 재시도 카운트 증가
            await this.db.execute(
                'UPDATE homepage_gosi_url_registry SET retry_count = retry_count + 1 WHERE id = ?',
                [item.id]
            );

        } finally {
            await page.close();
        }
    }

    /**
     * 메인 다운로드 프로세스
     */
    async download() {
        const startTime = Date.now();

        try {
            console.log('\n' + '='.repeat(60));
            console.log(`상세 다운로드 시작: ${this.config.siteName} (${this.siteCode})`);
            console.log('='.repeat(60));

            // 초기화
            await this.connectDB();
            const context = await this.initBrowser();
            await fs.ensureDir(this.outputDir);

            // 대기 중인 항목 조회
            const items = await this.getPendingItems();
            console.log(`대상 항목: ${items.length}개\n`);

            if (items.length === 0) {
                console.log('처리할 항목이 없습니다.');
                return;
            }

            // 폴더 카운터 설정: completed 상태인 항목 개수 + 1부터 시작
            const [completedCount] = await this.db.execute(
                'SELECT COUNT(*) as count FROM homepage_gosi_url_registry WHERE site_code = ? AND status = ?',
                [this.siteCode, 'completed']
            );
            this.folderCounter = (completedCount[0].count || 0) + 1;

            // 항목별 처리
            for (const item of items) {
                await this.processItem(context, item);

                // 대기 시간
                if (items.indexOf(item) < items.length - 1) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
            }

            // 처리 시간 계산
            const elapsedTime = Math.round((Date.now() - startTime) / 1000);

            // 통계 출력
            console.log('\n' + '='.repeat(60));
            console.log('다운로드 완료');
            console.log('='.repeat(60));
            console.log(`처리 시간: ${elapsedTime}초`);
            console.log(`전체: ${this.stats.total}개`);
            console.log(`성공: ${this.stats.success}개`);
            console.log(`실패: ${this.stats.failed}개`);
            console.log(`스킵: ${this.stats.skipped}개`);

            // 처리 로그 업데이트
            if (this.db) {
                await this.db.execute(
                    `UPDATE homepage_gosi_processing_log 
                    SET downloaded = ?, failed = ?, download_time = ?, total_time = ?
                    WHERE site_code = ? AND run_date = CURDATE()
                    ORDER BY created_at DESC LIMIT 1`,
                    [
                        this.stats.success,
                        this.stats.failed,
                        elapsedTime,
                        elapsedTime,
                        this.siteCode
                    ]
                );
            }

        } catch (error) {
            console.error('치명적 오류:', error);
            process.exit(1);

        } finally {
            // 정리
            if (this.browser) await this.browser.close();
            if (this.db) await this.db.end();
        }
    }
}

// CLI 인터페이스
const argv = yargs
    .usage('사용법: $0 <site_code> [options]')
    .command('$0 <site_code>', '사이트 상세 다운로드', (yargs) => {
        yargs.positional('site_code', {
            describe: '사이트 코드',
            type: 'string'
        });
    })
    .option('limit', {
        alias: 'l',
        describe: '다운로드할 항목 수',
        type: 'number',
        default: 100
    })
    .option('url', {
        alias: 'u',
        describe: '특정 URL만 다운로드',
        type: 'string'
    })
    .option('verbose', {
        alias: 'v',
        describe: '상세 로그 출력',
        type: 'boolean',
        default: false
    })
    .option('test', {
        alias: 't',
        describe: '테스트 모드 (브라우저 표시)',
        type: 'boolean',
        default: false
    })
    .option('output-dir', {
        alias: 'o',
        describe: '출력 디렉토리',
        type: 'string',
        default: 'scraped_incremental'
    })
    .help()
    .alias('help', 'h')
    .argv;

// 실행
if (argv.site_code || argv.url) {
    const siteCode = argv.site_code || argv.site;

    const downloader = new HomepageGosiDetailDownloader(siteCode, {
        limit: argv.limit,
        url: argv.url,
        verbose: argv.verbose,
        test: argv.test,
        outputDir: argv.outputDir
    });

    downloader.download().catch(error => {
        console.error('실행 오류:', error);
        process.exit(1);
    });
} else {
    yargs.showHelp();
}