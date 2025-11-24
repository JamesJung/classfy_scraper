#!/usr/bin/env node

/**
 * 모든 스크래퍼에 --count 옵션 추가
 *
 * 기능:
 * 1. UrlManager require 추가
 * 2. extractAndSaveUrls() 메소드 추가
 * 3. CLI 옵션에 --count, --batch-date 추가
 * 4. main() 함수에서 --count 처리 로직 추가
 */

const fs = require('fs-extra');
const path = require('path');

const SCRAPER_DIR = path.join(__dirname, 'node/scraper');

// andong_scraper.js는 이미 적용됨
const EXCLUDE_FILES = [
    'andong_scraper.js',
    'announcement_scraper.js',
    'config.js',
    'failure_logger.js',
    'count_validator.js',
    'url_manager.js',
    'unified_detail_scraper.js',
    'unified_list_collector.js'
];

class CountOptionPatcher {
    /**
     * 1. UrlManager require 추가
     */
    addUrlManagerRequire(content) {
        // 이미 있으면 스킵
        if (content.includes("require('./url_manager')")) {
            return { content, modified: false };
        }

        const lines = content.split('\n');
        let insertIndex = -1;

        // FailureLogger require 라인 찾기
        for (let i = 0; i < lines.length; i++) {
            if (lines[i].includes("require('./failure_logger')")) {
                insertIndex = i + 1;
                break;
            }
        }

        // FailureLogger가 없으면 마지막 require 다음에 추가
        if (insertIndex === -1) {
            for (let i = 0; i < lines.length; i++) {
                if (lines[i].includes('require(') && !lines[i].trim().startsWith('//')) {
                    insertIndex = i + 1;
                }
            }
        }

        if (insertIndex > -1) {
            lines.splice(insertIndex, 0, "const UrlManager = require('./url_manager');");
            console.log(`  + UrlManager require 추가 (line ${insertIndex + 1})`);
            return { content: lines.join('\n'), modified: true };
        }

        return { content, modified: false };
    }

    /**
     * 2. extractAndSaveUrls() 메소드 추가
     */
    addExtractAndSaveUrlsMethod(content, className) {
        // 이미 있으면 스킵
        if (content.includes('async extractAndSaveUrls(')) {
            return { content, modified: false };
        }

        const lines = content.split('\n');
        let insertIndex = -1;

        // class 내부에서 첫 번째 메소드 앞에 삽입
        // constructor 다음이나 첫 async 메소드 앞
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            // constructor 찾기
            if (line.startsWith('constructor(')) {
                // constructor 끝 찾기
                let braceCount = 0;
                let foundStart = false;
                for (let j = i; j < lines.length; j++) {
                    for (let char of lines[j]) {
                        if (char === '{') {
                            braceCount++;
                            foundStart = true;
                        }
                        if (char === '}') braceCount--;
                    }
                    if (foundStart && braceCount === 0) {
                        insertIndex = j + 1;
                        break;
                    }
                }
                break;
            }
        }

        if (insertIndex === -1) {
            console.log('  ⚠️ constructor를 찾을 수 없음');
            return { content, modified: false };
        }

        // extractAndSaveUrls 메소드 생성
        const indent = '    ';
        const method = [
            '',
            `${indent}/**`,
            `${indent} * 상세 URL만 추출하여 DB에 저장 (다운로드 없음)`,
            `${indent} * @param {string} batchDate - 배치 날짜 (선택)`,
            `${indent} * @returns {Promise<{totalCount: number, pageCount: number, savedCount: number}>}`,
            `${indent} */`,
            `${indent}async extractAndSaveUrls(batchDate = null) {`,
            `${indent}    try {`,
            `${indent}        await this.initBrowser();`,
            ``,
            `${indent}        let currentPage = 1;`,
            `${indent}        let totalCount = 0;`,
            `${indent}        let savedCount = 0;`,
            `${indent}        let consecutiveEmptyPages = 0;`,
            `${indent}        const maxConsecutiveEmptyPages = 3;`,
            ``,
            `${indent}        console.log(\`\\n=== 상세 URL 추출 및 저장 시작 ===\`);`,
            `${indent}        console.log(\`사이트 코드: \${this.siteCode}\`);`,
            ``,
            `${indent}        if (this.targetDate) {`,
            `${indent}            const moment = require('moment');`,
            `${indent}            const targetMoment = moment(this.targetDate, 'YYYYMMDD');`,
            `${indent}            console.log(\`대상 날짜: \${targetMoment.format('YYYY-MM-DD')}\`);`,
            `${indent}        } else {`,
            `${indent}            console.log(\`대상 연도: \${this.targetYear}\`);`,
            `${indent}        }`,
            ``,
            `${indent}        while (consecutiveEmptyPages < maxConsecutiveEmptyPages) {`,
            `${indent}            try {`,
            `${indent}                console.log(\`\\n페이지 \${currentPage} 확인 중...\`);`,
            `${indent}                const announcements = await this.getAnnouncementList(currentPage);`,
            ``,
            `${indent}                if (!announcements || announcements.length === 0) {`,
            `${indent}                    consecutiveEmptyPages++;`,
            `${indent}                    currentPage++;`,
            `${indent}                    continue;`,
            `${indent}                }`,
            ``,
            `${indent}                consecutiveEmptyPages = 0;`,
            `${indent}                let pageValidCount = 0;`,
            `${indent}                let shouldStop = false;`,
            ``,
            `${indent}                for (const announcement of announcements) {`,
            `${indent}                    try {`,
            `${indent}                        // 날짜 확인`,
            `${indent}                        const listDate = this.extractDate(announcement.dateText || announcement.date);`,
            ``,
            `${indent}                        // targetDate가 설정된 경우`,
            `${indent}                        if (this.targetDate) {`,
            `${indent}                            const moment = require('moment');`,
            `${indent}                            const targetMoment = moment(this.targetDate, 'YYYYMMDD');`,
            `${indent}                            if (listDate && listDate.isBefore(targetMoment)) {`,
            `${indent}                                console.log(\`대상 날짜(\${targetMoment.format('YYYY-MM-DD')}) 이전 공고 발견. 추출 중단.\`);`,
            `${indent}                                shouldStop = true;`,
            `${indent}                                break;`,
            `${indent}                            }`,
            `${indent}                        }`,
            `${indent}                        // targetYear만 설정된 경우`,
            `${indent}                        else if (listDate && listDate.year() < this.targetYear) {`,
            `${indent}                            console.log(\`대상 연도(\${this.targetYear}) 이전 공고 발견. 추출 중단.\`);`,
            `${indent}                            shouldStop = true;`,
            `${indent}                            break;`,
            `${indent}                        }`,
            ``,
            `${indent}                        // 상세 URL 생성`,
            `${indent}                        const detailUrl = await this.buildDetailUrl(announcement);`,
            `${indent}                        if (!detailUrl) continue;`,
            ``,
            `${indent}                        // 날짜 형식 정규화 (YYYY.MM.DD or YYYY/MM/DD → YYYY-MM-DD)`,
            `${indent}                        let normalizedDate = announcement.dateText || announcement.date || '';`,
            `${indent}                        if (normalizedDate) {`,
            `${indent}                            normalizedDate = normalizedDate.replace(/\\./g, '-').replace(/\\//g, '-');`,
            `${indent}                        }`,
            ``,
            `${indent}                        // URL DB 저장`,
            `${indent}                        const saved = await UrlManager.saveDetailUrl({`,
            `${indent}                            site_code: this.siteCode,`,
            `${indent}                            title: announcement.title || announcement.subject || 'Unknown',`,
            `${indent}                            list_url: this.baseUrl,`,
            `${indent}                            detail_url: detailUrl,`,
            `${indent}                            list_date: normalizedDate,`,
            `${indent}                            batch_date: batchDate`,
            `${indent}                        });`,
            ``,
            `${indent}                        if (saved) {`,
            `${indent}                            savedCount++;`,
            `${indent}                            const title = announcement.title || announcement.subject || 'Unknown';`,
            `${indent}                            console.log(\`  ✓ \${title.substring(0, 50)}...\`);`,
            `${indent}                        }`,
            `${indent}                        pageValidCount++;`,
            `${indent}                    } catch (error) {`,
            `${indent}                        continue;`,
            `${indent}                    }`,
            `${indent}                }`,
            ``,
            `${indent}                totalCount += pageValidCount;`,
            `${indent}                console.log(\`페이지 \${currentPage}: \${pageValidCount}개 URL 추출 (저장: \${savedCount}개)\`);`,
            ``,
            `${indent}                if (shouldStop) {`,
            `${indent}                    console.log(\`조건 불일치로 추출 중단.\`);`,
            `${indent}                    break;`,
            `${indent}                }`,
            ``,
            `${indent}                currentPage++;`,
            `${indent}                await this.delay(1000);`,
            `${indent}            } catch (pageError) {`,
            `${indent}                consecutiveEmptyPages++;`,
            `${indent}                currentPage++;`,
            `${indent}            }`,
            `${indent}        }`,
            ``,
            `${indent}        console.log(\`\\n=== URL 추출 완료 ===\`);`,
            `${indent}        console.log(\`총 URL: \${totalCount}개, 저장: \${savedCount}개\`);`,
            ``,
            `${indent}        return { totalCount, savedCount, pageCount: currentPage - 1 };`,
            `${indent}    } catch (error) {`,
            `${indent}        console.error('URL 추출 중 오류:', error.message);`,
            `${indent}        throw error;`,
            `${indent}    } finally {`,
            `${indent}        await this.cleanup();`,
            `${indent}    }`,
            `${indent}}`
        ];

        lines.splice(insertIndex, 0, ...method);
        console.log(`  + extractAndSaveUrls() 메소드 추가`);
        return { content: lines.join('\n'), modified: true };
    }

    /**
     * 3. CLI 옵션 추가
     */
    addCliOptions(content) {
        // 이미 있으면 스킵
        if (content.includes("option('count'") || content.includes('option("count"')) {
            return { content, modified: false };
        }

        const lines = content.split('\n');
        let modified = false;

        // .option('force' 또는 .example 앞에 추가
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            // .example( 또는 .help() 찾기
            if ((line.includes('.example(') || line.includes('.help()')) && !modified) {
                // 그 앞에 옵션 추가
                const indent = line.match(/^(\s*)/)[1];
                const options = [
                    `${indent}.option('count', {`,
                    `${indent}    alias: 'c',`,
                    `${indent}    type: 'boolean',`,
                    `${indent}    description: 'URL만 추출하여 DB에 저장 (다운로드 없음)',`,
                    `${indent}    default: false`,
                    `${indent}})`,
                    `${indent}.option('batch-date', {`,
                    `${indent}    alias: 'b',`,
                    `${indent}    type: 'string',`,
                    `${indent}    description: '배치 날짜 (YYYY-MM-DD 형식)',`,
                    `${indent}    default: null`,
                    `${indent}})` // 여기를 }) 로 수정
                ];

                lines.splice(i, 0, ...options);
                console.log(`  + CLI 옵션 추가`);
                modified = true;
                break;
            }
        }

        return { content: lines.join('\n'), modified };
    }

    /**
     * 4. main() 함수 수정
     */
    addMainFunctionLogic(content) {
        // 이미 있으면 스킵
        if (content.includes('if (argv.count)') || content.includes('if(argv.count)')) {
            return { content, modified: false };
        }

        const lines = content.split('\n');
        let modified = false;

        // await scraper.scrape() 찾기
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            if (line.includes('await scraper.scrape()') && !line.startsWith('//')) {
                const indent = lines[i].match(/^(\s*)/)[1];

                // 이 라인을 if-else로 감싸기
                const logic = [
                    `${indent}// --count 옵션이 있으면 URL만 추출`,
                    `${indent}if (argv.count) {`,
                    `${indent}    console.log('URL 추출 모드');`,
                    `${indent}    const result = await scraper.extractAndSaveUrls(argv.batchDate);`,
                    `${indent}    console.log(\`완료: \${result.totalCount}개 URL, \${result.savedCount}개 저장\`);`,
                    `${indent}    `,
                    `${indent}    const UrlManager = require('./url_manager');`,
                    `${indent}    const moment = require('moment');`,
                    `${indent}    const batchDate = argv.batchDate || moment().format('YYYY-MM-DD');`,
                    `${indent}    const stats = await UrlManager.getStats(argv.site, batchDate);`,
                    `${indent}    console.log(\`DB 통계: 전체 \${stats.total}개, 완료 \${stats.scraped}개, 대기 \${stats.unscraped}개\`);`,
                    `${indent}} else {`,
                    `${indent}    ${line}`,
                    `${indent}}`
                ];

                lines.splice(i, 1, ...logic);
                console.log(`  + main() 함수 로직 추가`);
                modified = true;
                break;
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

            // 클래스명 추출
            const classMatch = content.match(/class\s+(\w+)/);
            const className = classMatch ? classMatch[1] : 'AnnouncementScraper';

            // 1. UrlManager require 추가
            let result = this.addUrlManagerRequire(content);
            if (result.modified) {
                content = result.content;
                totalModified = true;
            }

            // 2. extractAndSaveUrls() 메소드 추가
            result = this.addExtractAndSaveUrlsMethod(content, className);
            if (result.modified) {
                content = result.content;
                totalModified = true;
            }

            // 3. CLI 옵션 추가
            result = this.addCliOptions(content);
            if (result.modified) {
                content = result.content;
                totalModified = true;
            }

            // 4. main() 함수 로직 추가
            result = this.addMainFunctionLogic(content);
            if (result.modified) {
                content = result.content;
                totalModified = true;
            }

            // 변경사항이 있으면 저장
            if (totalModified) {
                await fs.writeFile(filePath, content, 'utf-8');

                // Syntax 체크
                const { execSync } = require('child_process');
                try {
                    execSync(`node -c "${filePath}"`, { stdio: 'ignore' });
                    console.log(`  ✓ 패치 완료 (Syntax OK)`);
                    return true;
                } catch (syntaxError) {
                    console.log(`  ✗ Syntax 에러!`);
                    return false;
                }
            } else {
                console.log(`  ○ 변경사항 없음 (이미 적용됨)`);
                return false;
            }

        } catch (error) {
            console.error(`  ✗ 에러: ${error.message}`);
            return false;
        }
    }
}

async function main() {
    console.log('='.repeat(80));
    console.log('  모든 스크래퍼에 --count 옵션 추가');
    console.log('='.repeat(80));
    console.log();

    // 모든 스크래퍼 파일 목록
    const scraperFiles = (await fs.readdir(SCRAPER_DIR))
        .filter(file => file.endsWith('_scraper.js'))
        .filter(file => !EXCLUDE_FILES.includes(file));

    console.log(`대상 파일: ${scraperFiles.length}개`);
    console.log();

    const patcher = new CountOptionPatcher();
    let success = 0;
    let skipped = 0;
    let failed = 0;

    for (const fileName of scraperFiles) {
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
    console.log('='.repeat(80));
    console.log('  패치 완료');
    console.log('='.repeat(80));
    console.log(`성공: ${success}개`);
    console.log(`스킵: ${skipped}개 (이미 적용됨)`);
    console.log(`실패: ${failed}개`);
    console.log('='.repeat(80));
}

main().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});
