#!/usr/bin/env node

/**
 * 간단한 Puppeteer 테스트
 */

const puppeteer = require('puppeteer');

async function simpleTest() {
    console.log('=== 간단한 Puppeteer 테스트 ===\n');
    
    try {
        console.log('1. 브라우저 실행 중...');
        const browser = await puppeteer.launch({ 
            headless: "new",
            timeout: 10000
        });
        console.log('✅ 브라우저 실행 성공');
        
        console.log('2. 새 페이지 생성 중...');
        const page = await browser.newPage();
        console.log('✅ 페이지 생성 성공');
        
        console.log('3. Google 접속 테스트...');
        await page.goto('https://www.google.com', { 
            waitUntil: 'domcontentloaded',
            timeout: 10000 
        });
        console.log('✅ 페이지 접속 성공');
        
        const title = await page.title();
        console.log(`페이지 제목: ${title}`);
        
        console.log('4. 브라우저 종료 중...');
        await browser.close();
        console.log('✅ 브라우저 종료 성공');
        
        console.log('\n=== 모든 테스트 통과! ===');
        console.log('Puppeteer가 정상적으로 작동합니다.');
        
    } catch (error) {
        console.error('❌ 테스트 실패:', error.message);
        console.error('\n상세 오류:', error);
    }
}

if (require.main === module) {
    simpleTest();
}

module.exports = simpleTest;