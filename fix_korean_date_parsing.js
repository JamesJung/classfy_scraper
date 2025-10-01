#!/usr/bin/env node

const fs = require('fs-extra');
const path = require('path');
const glob = require('glob');

// 개선된 extractDate 메소드
const improvedExtractDate = `    extractDate(dateText) {
        if (!dateText) return null;

        // 텍스트 정리
        let cleanText = dateText.trim();
        
        // "2025년 9월 30일(화) 16:51:34" 형식 처리
        const koreanDateMatch = cleanText.match(/(\\d{4})년\\s*(\\d{1,2})월\\s*(\\d{1,2})일/);
        if (koreanDateMatch) {
            const [, year, month, day] = koreanDateMatch;
            cleanText = \`\${year}-\${month.padStart(2, '0')}-\${day.padStart(2, '0')}\`;
        }

        // "등록일\\n2025-09-10" 같은 형식에서 날짜만 추출
        const dateMatch = cleanText.match(/(\\d{4}[-.\\\\/]\\d{1,2}[-.\\\\/]\\d{1,2})/);
        if (dateMatch) {
            cleanText = dateMatch[1];
        }

        // 다양한 날짜 형식 시도

        // YY.MM.DD 형식 체크 (예: 24.12.31)
        const yymmddMatch = cleanText.match(/^(\\d{2})\\.(\\d{1,2})\\.(\\d{1,2})$/);
        if (yymmddMatch) {
            // 2자리 연도를 4자리로 변환 (00-99 → 2000-2099)
            const year = '20' + yymmddMatch[1];
            const month = yymmddMatch[2].padStart(2, '0');
            const day = yymmddMatch[3].padStart(2, '0');
            cleanText = \`\${year}-\${month}-\${day}\`;
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
        if (naturalDate.isValid() && cleanText.match(/\\d{4}/)) {
            return naturalDate;
        }

        return null;
    }`;

async function updateScraperFile(filePath) {
    try {
        let content = await fs.readFile(filePath, 'utf8');
        
        // icdonggu_scraper.js는 이미 수정됨
        if (filePath.includes('icdonggu_scraper.js')) {
            console.log(`✓ 스킵 (이미 수정됨): ${path.basename(filePath)}`);
            return { skipped: true, reason: 'already updated' };
        }
        
        // extractDate 메소드가 없는 파일 체크
        if (!content.includes('extractDate')) {
            console.log(`⚠ extractDate 메소드 없음: ${path.basename(filePath)}`);
            return { skipped: true, reason: 'no extractDate method' };
        }
        
        // 이미 한글 날짜 파싱이 있는지 체크
        if (content.includes('년\\s*\\d{1,2}월\\s*\\d{1,2}일') || content.includes('년 ') && content.includes('월 ') && content.includes('일')) {
            console.log(`✓ 스킵 (이미 한글 파싱 있음): ${path.basename(filePath)}`);
            return { skipped: true, reason: 'already has Korean parsing' };
        }
        
        // extractDate 메소드 전체를 찾아서 교체
        // 정규표현식으로 extractDate 메소드 전체를 매칭
        const extractDateRegex = /extractDate\(dateText\)\s*\{[\s\S]*?\n\s{4}\}/g;
        
        if (extractDateRegex.test(content)) {
            // 메소드 전체를 개선된 버전으로 교체
            content = content.replace(extractDateRegex, improvedExtractDate);
            
            // 파일 저장
            await fs.writeFile(filePath, content, 'utf8');
            console.log(`✅ 수정 완료: ${path.basename(filePath)}`);
            return { updated: true };
        } else {
            // extractDate 메소드를 정확히 찾을 수 없는 경우
            // 더 간단한 방법으로 시도 - 한글 날짜 파싱 부분만 추가
            const simpleExtractDateStart = /extractDate\(dateText\)\s*\{[\s\S]*?\/\/ 텍스트 정리\s*let cleanText = dateText\.trim\(\);/;
            
            if (simpleExtractDateStart.test(content)) {
                const replacement = `extractDate(dateText) {
        if (!dateText) return null;

        // 텍스트 정리
        let cleanText = dateText.trim();
        
        // "2025년 9월 30일(화) 16:51:34" 형식 처리
        const koreanDateMatch = cleanText.match(/(\\d{4})년\\s*(\\d{1,2})월\\s*(\\d{1,2})일/);
        if (koreanDateMatch) {
            const [, year, month, day] = koreanDateMatch;
            cleanText = \`\${year}-\${month.padStart(2, '0')}-\${day.padStart(2, '0')}\`;
        }`;
                
                content = content.replace(simpleExtractDateStart, replacement);
                
                await fs.writeFile(filePath, content, 'utf8');
                console.log(`✅ 한글 날짜 파싱 추가: ${path.basename(filePath)}`);
                return { updated: true };
            }
            
            console.log(`⚠ extractDate 메소드 구조가 다름: ${path.basename(filePath)}`);
            return { skipped: true, reason: 'different structure' };
        }
        
    } catch (error) {
        console.error(`❌ 오류 발생 (${path.basename(filePath)}): ${error.message}`);
        return { error: true, message: error.message };
    }
}

async function main() {
    console.log('한글 날짜 파싱 추가 작업 시작...\n');
    
    // 모든 스크레이퍼 파일 찾기
    const scraperFiles = glob.sync('/Users/jin/classfy_scraper/node/scraper/*_scraper.js');
    
    console.log(`총 ${scraperFiles.length}개 스크레이퍼 파일 발견\n`);
    
    let stats = {
        updated: 0,
        skipped: 0,
        error: 0,
        skipReasons: {}
    };
    
    for (const file of scraperFiles) {
        const result = await updateScraperFile(file);
        
        if (result.updated) {
            stats.updated++;
        } else if (result.skipped) {
            stats.skipped++;
            stats.skipReasons[result.reason] = (stats.skipReasons[result.reason] || 0) + 1;
        } else if (result.error) {
            stats.error++;
        }
    }
    
    console.log('\n' + '='.repeat(50));
    console.log('📊 작업 완료 통계');
    console.log('='.repeat(50));
    console.log(`✅ 수정 완료: ${stats.updated}개`);
    console.log(`⚠️  스킵: ${stats.skipped}개`);
    
    if (Object.keys(stats.skipReasons).length > 0) {
        console.log('\n스킵 이유:');
        for (const [reason, count] of Object.entries(stats.skipReasons)) {
            console.log(`  - ${reason}: ${count}개`);
        }
    }
    
    console.log(`❌ 오류: ${stats.error}개`);
    console.log('='.repeat(50));
    console.log('\n✨ 모든 파일 처리 완료!');
}

main().catch(console.error);