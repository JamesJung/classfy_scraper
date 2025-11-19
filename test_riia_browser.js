const { chromium } = require('playwright');

async function testWithBrowser() {
    const url = 'https://gw.riia.or.kr/board/businessAnnouncement';

    console.log('='.repeat(100));
    console.log('Playwright 브라우저 테스트');
    console.log('='.repeat(100) + '\n');
    console.log(`URL: ${url}\n`);

    const browser = await chromium.launch({
        headless: true,
    });

    try {
        const context = await browser.newContext({
            userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            ignoreHTTPSErrors: true,
        });

        const page = await context.newPage();

        // 응답 이벤트 리스너
        page.on('response', response => {
            if (response.url() === url) {
                console.log(`📡 초기 응답 상태: ${response.status()}`);
                console.log(`Content-Type: ${response.headers()['content-type']}`);
            }
        });

        const startTime = Date.now();

        // 페이지 로드
        const response = await page.goto(url, {
            waitUntil: 'networkidle',
            timeout: 30000,
        });

        const loadTime = Date.now() - startTime;

        console.log(`\n최종 HTTP 상태: ${response.status()}`);
        console.log(`로드 시간: ${loadTime}ms`);
        console.log(`최종 URL: ${page.url()}`);

        // 페이지 제목
        const title = await page.title();
        console.log(`페이지 제목: ${title}`);

        // 에러 메시지가 있는지 확인
        const errorCode = await page.locator('.error-code').textContent().catch(() => null);
        const errorMessage = await page.locator('.error-message').textContent().catch(() => null);

        if (errorCode || errorMessage) {
            console.log(`\n❌ 에러 감지:`);
            console.log(`에러 코드: ${errorCode || 'N/A'}`);
            console.log(`에러 메시지: ${errorMessage || 'N/A'}`);
        }

        // 페이지 내용 확인 (h1, h2 태그)
        const headings = await page.locator('h1, h2').allTextContents();
        if (headings.length > 0) {
            console.log(`\n📄 페이지 제목들:`);
            headings.forEach((h, i) => {
                if (h.trim()) {
                    console.log(`  ${i + 1}. ${h.trim()}`);
                }
            });
        }

        // 게시판 항목이 있는지 확인
        const hasTable = await page.locator('table, .board-list, .list-group').count();
        console.log(`\n게시판 요소: ${hasTable}개`);

        // 스크린샷 저장
        await page.screenshot({ path: '/tmp/riia_screenshot.png', fullPage: true });
        console.log(`\n✅ 스크린샷 저장: /tmp/riia_screenshot.png`);

        // 콘솔 로그나 에러 확인
        page.on('console', msg => {
            if (msg.type() === 'error') {
                console.log(`\n🔴 브라우저 콘솔 에러: ${msg.text()}`);
            }
        });

    } finally {
        await browser.close();
    }
}

testWithBrowser().catch(console.error);
