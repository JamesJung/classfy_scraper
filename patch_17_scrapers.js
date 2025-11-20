#!/usr/bin/env node

/**
 * 17개 스크래퍼 수동 패치 스크립트
 * page.evaluate() 외부의 catch 블록만 선별적으로 패치
 */

const fs = require('fs-extra');
const path = require('path');

const SCRAPER_DIR = path.join(__dirname, 'node/scraper');

// 패치 대상 17개 파일
const TARGET_FILES = [
    'andong_scraper.js',
    'announcement_scraper.js',
    'anseong_scraper.js',
    'cheongyang_scraper.js',
    'ddm_scraper.js',
    'djjunggu_scraper.js',
    'gb_scraper.js',
    'geoje_scraper.js',
    'gokseong_scraper.js',
    'gurye_scraper.js',
    'hongseong_scraper.js',
    'jangseong_scraper.js',
    'michuhol_scraper.js',
    'shinan_scraper.js',
    'suncheon_scraper.js',
    'ui4u_scraper.js',
    'wando_scraper.js'
];

class SmartPatcher {
    /**
     * require 문 추가
     */
    addRequire(content) {
        // 이미 있으면 스킵
        if (content.includes("require('./failure_logger')")) {
            return content;
        }

        const lines = content.split('\n');
        let insertIndex = -1;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            // 주석이나 빈 줄 건너뛰기
            if (line.startsWith('//') || line.startsWith('/*') || line.startsWith('*') || !line) {
                continue;
            }

            // const require 찾기
            if (line.startsWith('const ') && line.includes('require(')) {
                insertIndex = i + 1;
            }

            // class 정의가 나오면 그 전에 삽입
            if (line.startsWith('class ')) {
                if (insertIndex === -1) {
                    insertIndex = i;
                }
                break;
            }
        }

        if (insertIndex > -1) {
            lines.splice(insertIndex, 0, "const FailureLogger = require('./failure_logger');");
            console.log(`  + require 추가 (line ${insertIndex + 1})`);
            return lines.join('\n');
        }

        return content;
    }

    /**
     * announcementError catch 블록 찾기 및 패치
     */
    patchAnnouncementError(content) {
        const lines = content.split('\n');
        let modified = false;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const trimmed = line.trim();

            // } catch (announcementError) { 찾기
            if (trimmed.match(/}\s*catch\s*\(announcementError\)\s*{/)) {
                // 다음 라인들 확인
                let nextLineIdx = i + 1;
                let hasConsoleError = false;
                let hasContinue = false;
                let hasFailureLogger = false;

                // 다음 5줄 정도 확인
                for (let j = nextLineIdx; j < nextLineIdx + 5 && j < lines.length; j++) {
                    const nextLine = lines[j].trim();
                    if (nextLine.includes('console.error')) hasConsoleError = true;
                    if (nextLine === 'continue;') hasContinue = true;
                    if (nextLine.includes('FailureLogger')) hasFailureLogger = true;
                }

                // announcementError catch 블록이 맞고, 아직 패치 안 됨
                if (hasConsoleError && hasContinue && !hasFailureLogger) {
                    const indent = line.match(/^(\s*)/)[1] + '    ';

                    // console.error 다음에 FailureLogger 추가
                    let insertIdx = nextLineIdx;
                    while (insertIdx < lines.length) {
                        if (lines[insertIdx].trim().startsWith('console.error')) {
                            insertIdx++;
                            break;
                        }
                        insertIdx++;
                    }

                    // FailureLogger 코드 생성
                    const loggerCode = [
                        ``,
                        `${indent}// 실패 공고 DB 기록`,
                        `${indent}FailureLogger.logFailedAnnouncement({`,
                        `${indent}    site_code: this.siteCode,`,
                        `${indent}    title: announcement?.title || 'Unknown',`,
                        `${indent}    url: announcement?.link || announcement?.url,`,
                        `${indent}    detail_url: announcement?.detailUrl,`,
                        `${indent}    error_type: 'announcementError',`,
                        `${indent}    error_message: announcementError.message`,
                        `${indent}}).catch(err => {});`
                    ];

                    lines.splice(insertIdx, 0, ...loggerCode);
                    console.log(`  + announcementError 패치 (line ${i + 1})`);
                    modified = true;
                    i += loggerCode.length; // 추가한 라인만큼 건너뛰기
                }
            }
        }

        return { content: lines.join('\n'), modified };
    }

    /**
     * 단일 파일 패치
     */
    async patchFile(fileName) {
        const filePath = path.join(SCRAPER_DIR, fileName);

        try {
            console.log(`\n패치 중: ${fileName}`);

            let content = await fs.readFile(filePath, 'utf-8');
            let totalModified = false;

            // 1. require 추가
            const newContent = this.addRequire(content);
            if (newContent !== content) {
                content = newContent;
                totalModified = true;
            }

            // 2. announcementError catch 블록 패치
            const { content: patchedContent, modified } = this.patchAnnouncementError(content);
            if (modified) {
                content = patchedContent;
                totalModified = true;
            }

            // 3. 변경사항이 있으면 저장
            if (totalModified) {
                await fs.writeFile(filePath, content, 'utf-8');

                // Syntax 체크
                const { execSync } = require('child_process');
                try {
                    execSync(`node -c "${filePath}"`, { stdio: 'ignore' });
                    console.log(`  ✓ 패치 완료 (Syntax OK)`);
                    return true;
                } catch (syntaxError) {
                    console.log(`  ✗ Syntax 에러 발생!`);
                    return false;
                }
            } else {
                console.log(`  ○ 변경사항 없음`);
                return false;
            }

        } catch (error) {
            console.error(`  ✗ 에러: ${error.message}`);
            return false;
        }
    }
}

async function main() {
    console.log('=' .repeat(80));
    console.log('  17개 스크래퍼 수동 패치 시작');
    console.log('  (page.evaluate() 외부 catch 블록만)');
    console.log('=' .repeat(80));
    console.log();

    const patcher = new SmartPatcher();
    let success = 0;
    let skipped = 0;
    let failed = 0;

    for (const fileName of TARGET_FILES) {
        const result = await patcher.patchFile(fileName);

        if (result === true) {
            success++;
        } else if (result === false) {
            skipped++;
        } else {
            failed++;
        }
    }

    console.log();
    console.log('=' .repeat(80));
    console.log('  패치 완료');
    console.log('=' .repeat(80));
    console.log(`성공: ${success}개`);
    console.log(`스킵: ${skipped}개`);
    console.log(`실패: ${failed}개`);
    console.log('=' .repeat(80));
}

main().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});
