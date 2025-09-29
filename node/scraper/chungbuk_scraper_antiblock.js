#!/usr/bin/env node

/**
 * chungbuk 스크래퍼 - IP 차단 우회 버전
 * 
 * 주요 우회 전략:
 * 1. 랜덤 지연 시간 (사람처럼 행동)
 * 2. User-Agent 로테이션
 * 3. 요청 헤더 랜덤화
 * 4. 브라우저 지문 변조
 * 5. 배치 처리 및 세션 재시작
 */

const { chromium } = require('playwright');
const fs = require('fs-extra');
const path = require('path');
const moment = require('moment');
const sanitize = require('sanitize-filename');

// User-Agent 풀
const userAgents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
];

class ChungbukAntiBlockScraper {
    constructor(options = {}) {
        this.targetYear = options.targetYear || new Date().getFullYear();
        this.baseOutputDir = options.outputDir || 'scraped_data';
        this.siteCode = 'chungbuk';
        this.outputDir = path.join(this.baseOutputDir, this.siteCode);
        this.baseUrl = 'https://www.chungbuk.go.kr';
        this.browser = null;
        this.context = null;
        this.page = null;
        this.processedTitles = new Set();
        this.counter = 1;
        
        // IP 차단 우회 설정
        this.batchSize = 20; // 20개씩 처리 후 브라우저 재시작
        this.minDelay = 3000; // 최소 대기 시간 (ms)
        this.maxDelay = 8000; // 최대 대기 시간 (ms)
        this.sessionRestartDelay = 30000; // 세션 재시작 대기 시간 (30초)
        this.currentBatch = 0;
        this.startPage = options.startPage || 1; // 시작 페이지 옵션
        this.startItem = options.startItem || 0; // 시작 아이템 옵션
    }

    /**
     * 랜덤 지연
     */
    async randomDelay() {
        const delay = Math.floor(Math.random() * (this.maxDelay - this.minDelay) + this.minDelay);
        console.log(`⏱ ${delay}ms 대기 중...`);
        await new Promise(resolve => setTimeout(resolve, delay));
    }

    /**
     * 랜덤 User-Agent 선택
     */
    getRandomUserAgent() {
        return userAgents[Math.floor(Math.random() * userAgents.length)];
    }

    /**
     * 브라우저 초기화 (스텔스 모드)
     */
    async initBrowser() {
        console.log('🔧 스텔스 브라우저 초기화 중...');
        
        try {
            // 브라우저 실행 옵션
            this.browser = await chromium.launch({
                headless: false, // 헤드리스 모드 비활성화 (더 자연스러움)
                args: [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-features=IsolateOrigins,site-per-process',
                    `--window-size=${1366 + Math.floor(Math.random() * 200)},${768 + Math.floor(Math.random() * 200)}`,
                ]
            });

            // 컨텍스트 생성 (매번 다른 설정)
            this.context = await this.browser.newContext({
                userAgent: this.getRandomUserAgent(),
                viewport: { 
                    width: 1366 + Math.floor(Math.random() * 200), 
                    height: 768 + Math.floor(Math.random() * 200) 
                },
                ignoreHTTPSErrors: true,
                // 추가 헤더 설정
                extraHTTPHeaders: {
                    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'Sec-Ch-Ua-Mobile': '?0',
                    'Sec-Ch-Ua-Platform': '"Windows"',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1'
                }
            });

            // 페이지 생성
            this.page = await this.context.newPage();
            
            // 자동화 감지 우회
            await this.page.addInitScript(() => {
                // webdriver 속성 제거
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Chrome 속성 추가
                window.chrome = {
                    runtime: {}
                };
                
                // Permissions 수정
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
                );
                
                // Plugin 추가
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Language 설정
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ko-KR', 'ko', 'en-US', 'en']
                });
            });

            // 타임아웃 설정
            this.page.setDefaultTimeout(60000);
            this.page.setDefaultNavigationTimeout(60000);

            console.log('✅ 스텔스 브라우저 초기화 완료');
            
        } catch (error) {
            console.error('❌ 브라우저 초기화 실패:', error);
            throw error;
        }
    }

    /**
     * 브라우저 재시작
     */
    async restartBrowser() {
        console.log('🔄 브라우저 세션 재시작 중...');
        
        if (this.browser) {
            await this.browser.close();
            this.browser = null;
            this.context = null;
            this.page = null;
        }
        
        console.log(`⏰ ${this.sessionRestartDelay/1000}초 대기...`);
        await new Promise(resolve => setTimeout(resolve, this.sessionRestartDelay));
        
        await this.initBrowser();
    }

    /**
     * 스크래핑 실행
     */
    async scrape() {
        await fs.ensureDir(this.outputDir);
        await this.initBrowser();

        try {
            let pageNum = this.startPage;
            let shouldContinue = true;
            let itemCount = 0;

            while (shouldContinue) {
                console.log(`\n📄 페이지 ${pageNum} 처리 중...`);
                
                // 배치 체크
                if (this.currentBatch >= this.batchSize) {
                    console.log(`\n🔄 배치 ${this.batchSize}개 완료. 브라우저 재시작...`);
                    await this.restartBrowser();
                    this.currentBatch = 0;
                }
                
                const url = `${this.baseUrl}/www/selectBbsNttList.do?bbsNo=19&pageUnit=10&pageIndex=${pageNum}&key=194`;
                
                try {
                    // 페이지 로드 (재시도 로직 포함)
                    let retries = 0;
                    const maxRetries = 3;
                    
                    while (retries < maxRetries) {
                        try {
                            await this.page.goto(url, { 
                                waitUntil: 'networkidle',
                                timeout: 30000 
                            });
                            break;
                        } catch (error) {
                            retries++;
                            console.log(`⚠️ 페이지 로드 실패 (시도 ${retries}/${maxRetries})`);
                            if (retries >= maxRetries) throw error;
                            await this.randomDelay();
                        }
                    }
                    
                    // 랜덤 대기
                    await this.randomDelay();
                    
                    // 마우스 움직임 시뮬레이션 (사람처럼 행동)
                    await this.simulateHumanBehavior();
                    
                    // 공고 목록 추출
                    const announcements = await this.page.evaluate(() => {
                        const rows = document.querySelectorAll('tbody tr');
                        const results = [];
                        
                        rows.forEach(row => {
                            const titleElement = row.querySelector('td.p-subject a');
                            const dateElement = row.querySelector('td:nth-child(5)');
                            
                            if (titleElement && dateElement) {
                                results.push({
                                    title: titleElement.textContent.trim(),
                                    link: titleElement.href,
                                    date: dateElement.textContent.trim()
                                });
                            }
                        });
                        
                        return results;
                    });
                    
                    // 항목 처리
                    for (let i = 0; i < announcements.length; i++) {
                        itemCount++;
                        
                        // 시작 위치 스킵
                        if (pageNum === this.startPage && itemCount < this.startItem) {
                            console.log(`⏩ 항목 ${itemCount} 스킵 (시작 위치: ${this.startItem})`);
                            continue;
                        }
                        
                        const announcement = announcements[i];
                        
                        // 날짜 체크
                        const date = moment(announcement.date, 'YYYY-MM-DD');
                        if (date.isValid() && date.year() < this.targetYear) {
                            console.log(`🛑 ${this.targetYear}년 이전 데이터 도달. 스크래핑 종료.`);
                            shouldContinue = false;
                            break;
                        }
                        
                        // 중복 체크
                        if (this.processedTitles.has(announcement.title)) {
                            console.log(`⏩ 중복 건너뛰기: ${announcement.title}`);
                            continue;
                        }
                        
                        // 상세 페이지 처리
                        await this.processDetail(announcement, itemCount);
                        this.processedTitles.add(announcement.title);
                        this.currentBatch++;
                        
                        // 항목 간 랜덤 대기
                        await this.randomDelay();
                    }
                    
                    if (!shouldContinue) break;
                    
                    // 다음 페이지 체크
                    const hasNext = await this.page.evaluate(() => {
                        const nextButton = document.querySelector('.paging a.next');
                        return nextButton && !nextButton.classList.contains('disabled');
                    });
                    
                    if (!hasNext) {
                        console.log('📭 마지막 페이지 도달');
                        break;
                    }
                    
                    pageNum++;
                    
                } catch (error) {
                    console.error(`❌ 페이지 ${pageNum} 처리 중 오류:`, error.message);
                    
                    // IP 차단 의심 시
                    if (error.message.includes('blocked') || error.message.includes('403') || 
                        error.message.includes('timeout')) {
                        console.log('🚨 IP 차단 의심. 긴 대기 후 재시도...');
                        await new Promise(resolve => setTimeout(resolve, 60000)); // 1분 대기
                        await this.restartBrowser();
                        // 같은 페이지부터 재시작
                        continue;
                    }
                    
                    throw error;
                }
            }
            
        } finally {
            if (this.browser) {
                await this.browser.close();
            }
        }
    }

    /**
     * 사람처럼 행동하기
     */
    async simulateHumanBehavior() {
        try {
            // 랜덤 스크롤
            const scrollY = Math.floor(Math.random() * 500);
            await this.page.evaluate((y) => window.scrollTo(0, y), scrollY);
            await new Promise(resolve => setTimeout(resolve, Math.random() * 1000));
            
            // 마우스 움직임
            const x = Math.floor(Math.random() * 1000) + 100;
            const y = Math.floor(Math.random() * 500) + 100;
            await this.page.mouse.move(x, y);
            
        } catch (error) {
            // 무시
        }
    }

    /**
     * 상세 페이지 처리
     */
    async processDetail(announcement, itemNum) {
        const folderName = `${String(this.counter).padStart(3, '0')}_${sanitize(announcement.title)}`;
        const folderPath = path.join(this.outputDir, folderName);
        
        if (await fs.pathExists(folderPath)) {
            console.log(`📁 이미 존재: ${folderName}`);
            return;
        }
        
        console.log(`📥 [${itemNum}] 처리 중: ${announcement.title}`);
        
        try {
            // 새 탭에서 상세 페이지 열기
            const newPage = await this.context.newPage();
            await newPage.goto(announcement.link, { waitUntil: 'networkidle' });
            
            // 컨텐츠 추출
            const content = await newPage.evaluate(() => {
                const contentElement = document.querySelector('.view-cont');
                return contentElement ? contentElement.innerText : '';
            });
            
            // 저장
            await fs.ensureDir(folderPath);
            await fs.writeFile(
                path.join(folderPath, 'content.md'),
                `**제목**: ${announcement.title}\n\n**날짜**: ${announcement.date}\n\n**내용**:\n\n${content}`
            );
            
            await newPage.close();
            this.counter++;
            
        } catch (error) {
            console.error(`❌ 상세 처리 실패: ${announcement.title}`, error.message);
        }
    }
}

// CLI 실행
const argv = require('yargs')
    .option('year', {
        alias: 'y',
        type: 'number',
        description: '대상 연도',
        default: new Date().getFullYear()
    })
    .option('start-page', {
        alias: 'p',
        type: 'number',
        description: '시작 페이지',
        default: 1
    })
    .option('start-item', {
        alias: 'i',
        type: 'number',
        description: '시작 아이템 번호',
        default: 0
    })
    .help()
    .argv;

const scraper = new ChungbukAntiBlockScraper({
    targetYear: argv.year,
    startPage: argv['start-page'],
    startItem: argv['start-item']
});

console.log(`
=====================================
충북도청 스크래퍼 (IP 차단 우회 버전)
=====================================
- 대상 연도: ${argv.year}
- 시작 페이지: ${argv['start-page']}
- 시작 아이템: ${argv['start-item']}
- 배치 크기: ${scraper.batchSize}개
- 대기 시간: ${scraper.minDelay}~${scraper.maxDelay}ms
=====================================
`);

scraper.scrape()
    .then(() => console.log('✅ 스크래핑 완료'))
    .catch(error => console.error('❌ 스크래핑 실패:', error));