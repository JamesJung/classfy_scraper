#!/usr/bin/env node

/**
 * 통합 상세 페이지 스크래퍼
 * 모든 사이트의 공고 상세 내용을 다운로드하는 통합 모듈
 */

const { chromium } = require('playwright');
const fs = require('fs-extra');
const path = require('path');
const yargs = require('yargs');
const sanitize = require('sanitize-filename');
const axios = require('axios');
const https = require('https');

class UnifiedDetailScraper {
    constructor(options = {}) {
        this.siteCode = options.site;
        this.announcementUrl = options.url;
        this.outputDir = options.outputDir;
        this.folderName = options.folderName;
        this.title = options.title || '제목 없음';
        this.date = options.date || '';
        this.onclick = options.onclick || '';
        this.dataAction = options.dataAction || '';
        this.verbose = options.verbose || false;
        
        // 설정 로드
        const configPath = path.join(__dirname, 'scrapers_config.json');
        const configs = JSON.parse(fs.readFileSync(configPath, 'utf8'));
        
        if (!configs[this.siteCode]) {
            throw new Error(`사이트 '${this.siteCode}'에 대한 설정을 찾을 수 없습니다.`);
        }
        
        this.config = configs[this.siteCode];
        
        // 커스텀 핸들러 로드
        if (this.config.customHandler) {
            const handlerPath = path.join(__dirname, 'custom_handlers', `${this.config.customHandler}_handler.js`);
            if (fs.existsSync(handlerPath)) {
                this.customHandler = require(handlerPath);
                if (this.verbose) {
                    console.error(`[${this.siteCode}] 커스텀 핸들러 로드: ${this.config.customHandler}`);
                }
            }
        }
        
        // axios 설정
        this.axiosInstance = axios.create({
            httpsAgent: new https.Agent({
                rejectUnauthorized: false
            }),
            timeout: 30000,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        });
    }

    async init() {
        this.browser = await chromium.launch({
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });

        const context = await this.browser.newContext({
            userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            acceptDownloads: true,
            ignoreHTTPSErrors: true
        });

        this.page = await context.newPage();
        
        // 다운로드 이벤트 처리
        this.page.on('download', async (download) => {
            const fileName = download.suggestedFilename();
            const attachDir = path.join(this.outputDir, this.folderName, 'attachments');
            await fs.ensureDir(attachDir);
            const filePath = path.join(attachDir, fileName);
            await download.saveAs(filePath);
            if (this.verbose) {
                console.error(`[${this.siteCode}] 첨부파일 다운로드: ${fileName}`);
            }
        });
    }

    async scrapeDetail() {
        try {
            await this.init();
            
            if (this.verbose) {
                console.error(`\n=== ${this.config.name} 상세 페이지 처리 ===`);
                console.error(`제목: ${this.title}`);
                console.error(`URL: ${this.announcementUrl}`);
            }
            
            // 상세 페이지 URL 결정
            const detailUrl = await this.determineDetailUrl();
            
            if (!detailUrl) {
                throw new Error('상세 페이지 URL을 결정할 수 없습니다.');
            }
            
            if (this.verbose) {
                console.error(`[${this.siteCode}] 상세 페이지 접속: ${detailUrl}`);
            }
            
            // 상세 페이지 이동
            await this.page.goto(detailUrl, { waitUntil: 'networkidle', timeout: 30000 });
            
            // 커스텀 핸들러 실행 (있는 경우)
            if (this.customHandler?.beforeExtract) {
                await this.customHandler.beforeExtract(this.page);
            }
            
            // 콘텐츠 추출
            const content = await this.extractContent();
            
            // 첨부파일 추출
            const attachments = await this.extractAttachments();
            
            // 저장
            await this.saveContent(content, attachments);
            
            // 첨부파일 다운로드
            if (attachments.length > 0) {
                await this.downloadAttachments(attachments);
            }
            
            // 실제 제목 추출 (페이지에서)
            const actualTitle = await this.extractActualTitle();
            
            // 성공 응답
            console.log(JSON.stringify({
                status: 'success',
                site: this.siteCode,
                folder: this.folderName,
                actualTitle: actualTitle || this.title,
                attachments: attachments.length
            }));

        } catch (error) {
            console.error(`[${this.siteCode}] 오류:`, error.message);
            console.log(JSON.stringify({
                status: 'error',
                site: this.siteCode,
                error: error.message
            }));
        } finally {
            if (this.browser) {
                await this.browser.close();
            }
        }
    }

    async determineDetailUrl() {
        // 커스텀 핸들러의 URL 결정 로직 (있는 경우)
        if (this.customHandler?.determineDetailUrl) {
            return await this.customHandler.determineDetailUrl(this);
        }
        
        // 1. 이미 완전한 URL인 경우
        if (this.announcementUrl && this.announcementUrl.startsWith('http')) {
            return this.announcementUrl;
        }
        
        // 2. data-action 속성 사용 (원주시 등)
        if (this.config.detailNavigation?.useDataAction && this.dataAction) {
            return new URL(this.dataAction, this.config.baseUrl).toString();
        }
        
        // 3. onclick에서 JavaScript 패턴 추출
        if (this.onclick && this.config.detailNavigation?.patterns) {
            for (const pattern of this.config.detailNavigation.patterns) {
                const regex = new RegExp(pattern);
                const match = this.onclick.match(regex);
                if (match && match[1]) {
                    const extractedUrl = match[1];
                    if (extractedUrl.startsWith('http')) {
                        return extractedUrl;
                    } else if (extractedUrl.startsWith('/')) {
                        return new URL(extractedUrl, this.config.baseUrl).toString();
                    }
                }
            }
        }
        
        // 4. 상대 URL을 절대 URL로 변환
        if (this.announcementUrl && this.announcementUrl.startsWith('/')) {
            return new URL(this.announcementUrl, this.config.baseUrl).toString();
        }
        
        return this.announcementUrl;
    }

    async extractActualTitle() {
        try {
            return await this.page.evaluate(() => {
                // 여러 제목 선택자 시도
                const selectors = [
                    'h1.title', 'h2.title', 'h3.title',
                    '.board_view h1', '.board_view h2',
                    '.view_title', '.subject', '.tit',
                    'td.title', 'div.title'
                ];
                
                for (const selector of selectors) {
                    const element = document.querySelector(selector);
                    if (element && element.textContent.trim()) {
                        return element.textContent.trim();
                    }
                }
                
                return null;
            });
        } catch (error) {
            return null;
        }
    }

    async extractContent() {
        // 커스텀 핸들러의 콘텐츠 추출 (있는 경우)
        if (this.customHandler?.extractContent) {
            return await this.customHandler.extractContent(this.page, this.config);
        }
        
        return await this.page.evaluate((config) => {
            // 여러 콘텐츠 선택자 시도
            const selectors = config.selectors.contentArea.split(',').map(s => s.trim());
            
            for (const selector of selectors) {
                const contentElement = document.querySelector(selector);
                if (contentElement) {
                    // 텍스트만 추출
                    const textContent = contentElement.innerText || contentElement.textContent || '';
                    if (textContent.trim()) {
                        return textContent.trim();
                    }
                }
            }
            
            // 폴백: body 전체에서 추출
            const bodyText = document.body.innerText || document.body.textContent || '';
            return bodyText.trim();
        }, this.config);
    }

    async extractAttachments() {
        // 커스텀 핸들러의 첨부파일 추출 (있는 경우)
        if (this.customHandler?.extractAttachments) {
            return await this.customHandler.extractAttachments(this.page, this.config);
        }
        
        return await this.page.evaluate((config) => {
            const attachments = [];
            
            // 여러 첨부파일 선택자 시도
            const selectors = config.selectors.attachments.split(',').map(s => s.trim());
            
            for (const selector of selectors) {
                const links = document.querySelectorAll(selector);
                
                links.forEach(link => {
                    const name = link.textContent.trim();
                    const url = link.href || '';
                    const onclick = link.getAttribute('onclick') || '';
                    
                    // 파일명이 있고 중복이 아닌 경우만 추가
                    if (name && !attachments.find(a => a.name === name)) {
                        // 확장자 체크 (이미지, 문서 등)
                        const fileExtensions = [
                            '.pdf', '.doc', '.docx', '.xls', '.xlsx',
                            '.ppt', '.pptx', '.hwp', '.hwpx', '.zip',
                            '.jpg', '.jpeg', '.png', '.gif', '.txt'
                        ];
                        
                        const hasExtension = fileExtensions.some(ext => 
                            name.toLowerCase().includes(ext) || url.toLowerCase().includes(ext)
                        );
                        
                        if (hasExtension || onclick.includes('download') || onclick.includes('file')) {
                            attachments.push({
                                name: name,
                                url: url,
                                onclick: onclick
                            });
                        }
                    }
                });
            }
            
            return attachments;
        }, this.config);
    }

    async downloadAttachments(attachments) {
        const attachDir = path.join(this.outputDir, this.folderName, 'attachments');
        await fs.ensureDir(attachDir);
        
        for (const attachment of attachments) {
            try {
                // 커스텀 핸들러의 다운로드 로직 (있는 경우)
                if (this.customHandler?.downloadAttachment) {
                    await this.customHandler.downloadAttachment(this.page, attachment, attachDir);
                    continue;
                }
                
                // 직접 URL 다운로드
                if (attachment.url && attachment.url.startsWith('http')) {
                    const fileName = sanitize(attachment.name);
                    const filePath = path.join(attachDir, fileName);
                    
                    const response = await this.axiosInstance.get(attachment.url, {
                        responseType: 'stream'
                    });
                    
                    const writer = fs.createWriteStream(filePath);
                    response.data.pipe(writer);
                    
                    await new Promise((resolve, reject) => {
                        writer.on('finish', resolve);
                        writer.on('error', reject);
                    });
                    
                    if (this.verbose) {
                        console.error(`[${this.siteCode}] 첨부파일 다운로드 완료: ${fileName}`);
                    }
                } else if (attachment.onclick) {
                    // JavaScript 클릭 방식
                    await this.page.evaluate((onclick) => {
                        eval(onclick);
                    }, attachment.onclick);
                    
                    // 다운로드 대기
                    await this.delay(2000);
                }
            } catch (error) {
                console.error(`[${this.siteCode}] 첨부파일 다운로드 실패 (${attachment.name}):`, error.message);
            }
        }
    }

    async saveContent(content, attachments) {
        const folderPath = path.join(this.outputDir, this.folderName);
        await fs.ensureDir(folderPath);
        
        // content.md 생성
        let markdown = `# ${this.title}\n\n`;
        markdown += `**원본 URL**: ${this.announcementUrl}\n\n`;
        markdown += `**작성일**: ${this.date}\n\n`;
        markdown += `## 내용\n\n${content}\n`;
        
        // 첨부파일 정보 추가
        if (attachments.length > 0) {
            markdown += `\n## 첨부파일\n`;
            for (const att of attachments) {
                markdown += `- ${att.name}`;
                if (att.url) {
                    markdown += `: ${att.url}`;
                }
                markdown += '\n';
            }
        }
        
        // 파일 저장
        const contentPath = path.join(folderPath, 'content.md');
        await fs.writeFile(contentPath, markdown, 'utf-8');
        
        if (this.verbose) {
            console.error(`[${this.siteCode}] content.md 저장 완료: ${folderPath}`);
        }
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// CLI 설정
const argv = yargs
    .option('site', {
        alias: 's',
        type: 'string',
        description: '사이트 코드 (anyang, wonju 등)',
        demandOption: true
    })
    .option('url', {
        alias: 'u',
        type: 'string',
        description: '공고 URL',
        demandOption: true
    })
    .option('output-dir', {
        alias: 'o',
        type: 'string',
        description: '출력 디렉토리',
        demandOption: true
    })
    .option('folder-name', {
        alias: 'f',
        type: 'string',
        description: '폴더명',
        demandOption: true
    })
    .option('title', {
        type: 'string',
        description: '공고 제목'
    })
    .option('date', {
        type: 'string',
        description: '작성일'
    })
    .option('onclick', {
        type: 'string',
        description: 'onclick 속성'
    })
    .option('data-action', {
        type: 'string',
        description: 'data-action 속성'
    })
    .option('verbose', {
        alias: 'v',
        type: 'boolean',
        description: '상세 로그 출력',
        default: false
    })
    .help()
    .alias('help', 'h')
    .example('$0 --site anyang --url "https://..." --output-dir "./data" --folder-name "001_공고"', '안양시 상세 페이지 다운로드')
    .argv;

// 실행
const scraper = new UnifiedDetailScraper(argv);
scraper.scrapeDetail();