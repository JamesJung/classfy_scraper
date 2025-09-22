#!/usr/bin/env node

/**
 * 통합 리스트 수집기
 * 모든 사이트의 공고 리스트를 수집하는 통합 모듈
 */

const { chromium } = require('playwright');
const fs = require('fs-extra');
const path = require('path');
const yargs = require('yargs');
const moment = require('moment');

class UnifiedListCollector {
    constructor(options = {}) {
        this.siteCode = options.site;
        this.maxPages = options.pages || 3;
        this.verbose = options.verbose || false;
        
        // 설정 파일 로드
        const configPath = path.join(__dirname, 'scrapers_config.json');
        const configs = JSON.parse(fs.readFileSync(configPath, 'utf8'));
        
        if (!configs[this.siteCode]) {
            throw new Error(`사이트 '${this.siteCode}'에 대한 설정을 찾을 수 없습니다.`);
        }
        
        this.config = configs[this.siteCode];
        this.allAnnouncements = [];
        
        // 커스텀 핸들러 로드 (있는 경우)
        if (this.config.customHandler) {
            const handlerPath = path.join(__dirname, 'custom_handlers', `${this.config.customHandler}_handler.js`);
            if (fs.existsSync(handlerPath)) {
                this.customHandler = require(handlerPath);
                if (this.verbose) {
                    console.error(`[${this.siteCode}] 커스텀 핸들러 로드: ${this.config.customHandler}`);
                }
            }
        }
    }

    async init() {
        this.browser = await chromium.launch({
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });

        const context = await this.browser.newContext({
            userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport: { width: 1920, height: 1080 },
            ignoreHTTPSErrors: true
        });

        this.page = await context.newPage();
        
        // 페이지 타임아웃 설정
        this.page.setDefaultTimeout(30000);
        this.page.setDefaultNavigationTimeout(30000);
    }

    async collectList() {
        try {
            await this.init();
            
            if (this.verbose) {
                console.error(`\n=== ${this.config.name} 리스트 수집 시작 ===`);
            }
            
            // 리스트 페이지 이동
            const listUrl = this.config.baseUrl + this.config.endpoints.list;
            if (this.verbose) {
                console.error(`[${this.siteCode}] 리스트 페이지 접속: ${listUrl}`);
            }
            
            await this.page.goto(listUrl, { waitUntil: 'networkidle', timeout: 30000 });
            
            // 커스텀 핸들러의 초기화 실행 (있는 경우)
            if (this.customHandler?.beforeListCollection) {
                await this.customHandler.beforeListCollection(this.page);
            }

            // 페이지별 수집
            for (let pageNum = 1; pageNum <= this.maxPages; pageNum++) {
                if (this.verbose) {
                    console.error(`[${this.siteCode}] 페이지 ${pageNum}/${this.maxPages} 수집 중...`);
                }
                
                // 페이지 네비게이션 (첫 페이지 제외)
                if (pageNum > 1) {
                    const navigated = await this.navigateToPage(pageNum);
                    if (!navigated) {
                        console.error(`[${this.siteCode}] 페이지 ${pageNum} 네비게이션 실패`);
                        break;
                    }
                }

                // 리스트 추출
                const announcements = await this.extractAnnouncements();
                
                if (this.verbose) {
                    console.error(`[${this.siteCode}] 페이지 ${pageNum}에서 ${announcements.length}개 공고 발견`);
                }
                
                // 빈 페이지면 중단
                if (announcements.length === 0) {
                    if (this.verbose) {
                        console.error(`[${this.siteCode}] 더 이상 공고가 없습니다.`);
                    }
                    break;
                }
                
                this.allAnnouncements.push(...announcements);
            }

            // 디버깅용 상세 출력
            if (this.verbose && this.allAnnouncements.length > 0) {
                console.error(`\n=== 수집된 공고 목록 ===`);
                this.allAnnouncements.forEach((ann, index) => {
                    console.error(`${(index + 1).toString().padStart(3, ' ')}. [${ann.id}] ${ann.title} (${ann.date})`);
                });
                console.error('===================================\n');
            }

            // JSON으로 출력 (stdout)
            console.log(JSON.stringify({
                status: 'success',
                site: this.siteCode,
                siteName: this.config.name,
                count: this.allAnnouncements.length,
                data: this.allAnnouncements
            }));

        } catch (error) {
            console.error(`[${this.siteCode}] 오류 발생:`, error.message);
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

    async navigateToPage(pageNum) {
        try {
            // 커스텀 핸들러의 페이지 네비게이션 (있는 경우)
            if (this.customHandler?.navigateListPage) {
                return await this.customHandler.navigateListPage(this.page, pageNum);
            }
            
            // 페이지네이션 처리
            if (this.config.pagination.type === 'javascript') {
                // JavaScript 함수 호출 방식
                await this.page.evaluate((funcName, pageNum) => {
                    if (typeof window[funcName] === 'function') {
                        window[funcName](pageNum);
                    }
                }, this.config.pagination.function, pageNum);
                
                await this.page.waitForLoadState('networkidle', { timeout: 10000 });
                await this.delay(1000);
            } else if (this.config.pagination.type === 'parameter') {
                // URL 파라미터 방식
                const url = new URL(this.page.url());
                url.searchParams.set(this.config.pagination.param, pageNum);
                await this.page.goto(url.toString(), { waitUntil: 'networkidle', timeout: 30000 });
            }
            
            return true;
        } catch (error) {
            console.error(`[${this.siteCode}] 페이지 네비게이션 오류:`, error.message);
            return false;
        }
    }

    async extractAnnouncements() {
        // 커스텀 핸들러의 추출 로직 (있는 경우)
        if (this.customHandler?.extractAnnouncements) {
            return await this.customHandler.extractAnnouncements(this.page, this.config);
        }
        
        return await this.page.evaluate((config) => {
            const announcements = [];
            
            // 여러 선택자 시도 (쉼표로 구분된 선택자들)
            const selectors = config.selectors.listTable.split(',').map(s => s.trim());
            let rows = [];
            
            for (const selector of selectors) {
                rows = document.querySelectorAll(selector);
                if (rows.length > 0) break;
            }
            
            rows.forEach((row, index) => {
                // 헤더 행이나 공지사항 행 스킵
                if (row.classList.contains('notice') || 
                    row.classList.contains('header') ||
                    row.querySelector('th')) {
                    return;
                }
                
                // 제목 추출 (여러 선택자 시도)
                const titleSelectors = config.selectors.listTitle.split(',').map(s => s.trim());
                let titleElement = null;
                
                for (const selector of titleSelectors) {
                    titleElement = row.querySelector(selector);
                    if (titleElement) break;
                }
                
                if (!titleElement) return;
                
                const title = titleElement.textContent.trim();
                if (!title || title === '') return;
                
                const href = titleElement.href || '';
                const onclick = titleElement.getAttribute('onclick') || '';
                const dataAction = titleElement.getAttribute('data-action') || '';
                
                // 날짜 추출 (여러 선택자 시도)
                const dateSelectors = config.selectors.listDate.split(',').map(s => s.trim());
                let dateElement = null;
                let date = '';
                
                for (const selector of dateSelectors) {
                    dateElement = row.querySelector(selector);
                    if (dateElement && dateElement.textContent.trim()) {
                        date = dateElement.textContent.trim();
                        break;
                    }
                }
                
                // ID 추출 (URL, onclick, data-action에서)
                let id = '';
                
                // URL에서 ID 추출
                if (href) {
                    const idPatterns = [
                        /[?&]idx=(\d+)/,
                        /[?&]no=(\d+)/,
                        /[?&]seq=(\d+)/,
                        /[?&]boardSeq=(\d+)/,
                        /[?&]nttNo=(\d+)/,
                        /[?&]not_ancmt_mgt_no=(\d+)/
                    ];
                    
                    for (const pattern of idPatterns) {
                        const match = href.match(pattern);
                        if (match) {
                            id = match[1];
                            break;
                        }
                    }
                }
                
                // onclick에서 ID 추출
                if (!id && onclick) {
                    const match = onclick.match(/['"](\d+)['"]/);
                    if (match) {
                        id = match[1];
                    }
                }
                
                // data-action에서 ID 추출
                if (!id && dataAction) {
                    const match = dataAction.match(/[?&]nttNo=(\d+)/);
                    if (match) {
                        id = match[1];
                    }
                }
                
                // 고유 ID 생성 (없는 경우)
                if (!id) {
                    id = `${Date.now()}_${index}`;
                }
                
                announcements.push({
                    id: id,
                    title: title,
                    url: href,
                    onclick: onclick,
                    dataAction: dataAction,
                    date: date,
                    index: index
                });
            });
            
            return announcements;
        }, this.config);
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// CLI 설정
const argv = yargs
    .option('site', {
        alias: 's',
        description: '사이트 코드 (anyang, wonju 등)',
        type: 'string',
        demandOption: true
    })
    .option('pages', {
        alias: 'p',
        description: '수집할 페이지 수',
        type: 'number',
        default: 3
    })
    .option('verbose', {
        alias: 'v',
        description: '상세 로그 출력',
        type: 'boolean',
        default: false
    })
    .help()
    .alias('help', 'h')
    .example('$0 --site anyang --pages 5', '안양시 5페이지 수집')
    .example('$0 --site wonju --pages 3 --verbose', '원주시 3페이지 수집 (상세 로그)')
    .argv;

// 실행
const collector = new UnifiedListCollector(argv);
collector.collectList();