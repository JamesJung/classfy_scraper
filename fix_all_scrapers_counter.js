#!/usr/bin/env node

const fs = require('fs-extra');
const path = require('path');
const glob = require('glob');

// 추가할 메소드들
const newMethods = `
    /**
     * 기존 폴더의 제목들을 로드하여 중복 체크
     */
    async loadExistingTitles() {
        try {
            if (!await fs.pathExists(this.outputDir)) {
                return;
            }

            const items = await fs.readdir(this.outputDir);
            for (const item of items) {
                // 001_형식의 폴더명에서 제목 부분 추출
                const match = item.match(/^\\d{3}_(.+)$/);
                if (match) {
                    const title = match[1];
                    // 폴더명은 sanitize된 상태이므로 원래 제목과 다를 수 있음
                    // 하지만 어느 정도 중복 감지에 도움이 됨
                    this.processedTitles.add(title);
                }
            }
            
            console.log(\`기존 폴더에서 \${this.processedTitles.size}개의 제목 로드\`);
        } catch (error) {
            console.log('기존 제목 로드 중 오류:', error.message);
        }
    }

    /**
     * 기존 폴더에서 가장 큰 카운터 번호 찾기
     */
    async getLastCounterNumber() {
        try {
            // outputDir이 존재하지 않으면 0 반환
            if (!await fs.pathExists(this.outputDir)) {
                return 0;
            }

            const items = await fs.readdir(this.outputDir);
            let maxNumber = 0;

            for (const item of items) {
                // 001_형식의 폴더명에서 숫자 추출
                const match = item.match(/^(\\d{3})_/);
                if (match) {
                    const num = parseInt(match[1], 10);
                    if (num > maxNumber) {
                        maxNumber = num;
                    }
                }
            }

            return maxNumber;
        } catch (error) {
            console.log('기존 카운터 번호 확인 중 오류:', error.message);
            return 0;
        }
    }
`;

async function fixScraperFile(filePath) {
    try {
        let content = await fs.readFile(filePath, 'utf8');
        
        // djjunggu_scraper.js는 이미 수정됨
        if (filePath.includes('djjunggu_scraper.js')) {
            console.log(`✓ 스킵 (이미 수정됨): ${path.basename(filePath)}`);
            return;
        }
        
        // 이미 수정된 파일 체크
        if (content.includes('getLastCounterNumber')) {
            console.log(`✓ 스킵 (이미 수정됨): ${path.basename(filePath)}`);
            return;
        }
        
        // 1. 새로운 메소드 추가 (initBrowser 메소드 앞에 추가)
        const initBrowserRegex = /(\s*)(async initBrowser\(\))/;
        if (initBrowserRegex.test(content)) {
            content = content.replace(initBrowserRegex, `$1${newMethods.trim()}\n\n$1$2`);
        } else {
            console.log(`⚠ initBrowser 메소드를 찾을 수 없음: ${path.basename(filePath)}`);
            return;
        }
        
        // 2. scrape 메소드에서 카운터 초기화 부분 수정
        const scrapeInitRegex = /(async scrape\(\) \{[\s\S]*?await this\.initBrowser\(\);[\s\S]*?await fs\.ensureDir\(this\.outputDir\);)/;
        
        if (scrapeInitRegex.test(content)) {
            content = content.replace(scrapeInitRegex, `$1
            
            // 기존 폴더에서 마지막 카운터 번호를 가져와서 그 다음부터 시작
            const lastCounter = await this.getLastCounterNumber();
            this.counter = lastCounter + 1;
            console.log(\`시작 카운터 번호: \${this.counter} (기존 최대 번호: \${lastCounter})\`);
            
            // 기존 폴더의 제목들을 processedTitles에 추가
            await this.loadExistingTitles();`);
        }
        
        // 3. 중복 체크 로직 개선 (sanitize된 제목으로 비교)
        // "중복 게시물 체크" 부분 찾기
        const duplicateCheckRegex = /if \(this\.processedTitles\.has\(announcement\.title\)\) \{/g;
        if (duplicateCheckRegex.test(content)) {
            content = content.replace(duplicateCheckRegex, 
                `const sanitizedTitle = sanitize(announcement.title).substring(0, 100);
            if (this.processedTitles.has(sanitizedTitle)) {`);
        }
        
        // 4. processedTitles.add 부분도 수정
        const addTitleRegex = /this\.processedTitles\.add\(announcement\.title\);/g;
        if (addTitleRegex.test(content)) {
            content = content.replace(addTitleRegex, 
                `// sanitize된 제목을 저장하여 정확한 중복 체크
            const sanitizedTitleForCheck = sanitize(announcement.title).substring(0, 100);
            this.processedTitles.add(sanitizedTitleForCheck);`);
        }
        
        // 파일 저장
        await fs.writeFile(filePath, content, 'utf8');
        console.log(`✅ 수정 완료: ${path.basename(filePath)}`);
        
    } catch (error) {
        console.error(`❌ 오류 발생 (${path.basename(filePath)}): ${error.message}`);
    }
}

async function main() {
    console.log('스크레이퍼 파일 수정 시작...\n');
    
    // 모든 스크레이퍼 파일 찾기
    const scraperFiles = glob.sync('/Users/jin/classfy_scraper/node/scraper/*_scraper.js');
    
    console.log(`총 ${scraperFiles.length}개 스크레이퍼 파일 발견\n`);
    
    for (const file of scraperFiles) {
        await fixScraperFile(file);
    }
    
    console.log('\n✨ 모든 파일 처리 완료!');
}

main().catch(console.error);