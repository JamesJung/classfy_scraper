#!/usr/bin/env node

/**
 * Syntax 에러 일괄 수정 스크립트
 *
 * 문제: page.evaluate() 내부에 await FailureLogger가 추가됨
 * 해결: 해당 블록 제거
 */

const fs = require('fs-extra');
const path = require('path');

const SCRAPER_DIR = path.join(__dirname, 'node/scraper');

async function fixFile(filePath) {
    try {
        let content = await fs.readFile(filePath, 'utf-8');
        let modified = false;

        // page.evaluate() 내부의 FailureLogger 블록 제거 패턴
        // } catch (error) {
        //     // 실패 공고 DB 기록
        //     await FailureLogger.logFailedAnnouncement({
        //         ...
        //     }).catch(logErr => {});
        //
        //     console.error/log(...)
        //     ...
        // }

        // 패턴 1: await FailureLogger 블록 전체 제거
        const pattern1 = /(\s*)\/\/ 실패 공고 DB 기록\n\s*await FailureLogger\.logFailedAnnouncement\({[\s\S]*?}\)\.catch\(logErr => \{\s*}\);\n\s*\n/g;
        if (pattern1.test(content)) {
            content = content.replace(pattern1, '');
            modified = true;
            console.log(`  수정: await FailureLogger 블록 제거`);
        }

        if (modified) {
            await fs.writeFile(filePath, content, 'utf-8');
            return true;
        }

        return false;

    } catch (error) {
        console.error(`  에러: ${error.message}`);
        return false;
    }
}

async function main() {
    console.log('=' * 80);
    console.log('Syntax 에러 일괄 수정 시작');
    console.log('=' * 80);

    const files = await fs.readdir(SCRAPER_DIR);
    const scraperFiles = files.filter(f => f.endsWith('_scraper.js'));

    let fixed = 0;
    let errors = 0;

    for (const file of scraperFiles) {
        const filePath = path.join(SCRAPER_DIR, file);

        // Syntax 체크
        const { execSync } = require('child_process');
        try {
            execSync(`node -c "${filePath}"`, { stdio: 'ignore' });
            // Syntax OK - 건너뛰기
            continue;
        } catch (e) {
            // Syntax 에러 있음 - 수정 시도
            console.log(`\n수정 중: ${file}`);

            if (await fixFile(filePath)) {
                // 재체크
                try {
                    execSync(`node -c "${filePath}"`, { stdio: 'ignore' });
                    console.log(`  ✓ 수정 완료`);
                    fixed++;
                } catch (recheckError) {
                    console.log(`  ✗ 수정 후에도 에러 있음`);
                    errors++;
                }
            } else {
                console.log(`  ✗ 수정 실패`);
                errors++;
            }
        }
    }

    console.log('\n' + '=' * 80);
    console.log('수정 완료');
    console.log('=' * 80);
    console.log(`수정: ${fixed}개`);
    console.log(`에러: ${errors}개`);
    console.log('=' * 80);
}

main().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});
