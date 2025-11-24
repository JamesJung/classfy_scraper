#!/usr/bin/env node

/**
 * 건수 검증을 포함한 스크래핑 실행
 *
 * 1. 예상 건수 카운트
 * 2. 실제 스크래핑 실행
 * 3. 예상 vs 실제 건수 비교 및 검증
 */

const AnnouncementScraper = require('./node/scraper/andong_scraper');
const CountValidator = require('./node/scraper/count_validator');
const moment = require('moment');
const yargs = require('yargs');

async function runScraperWithValidation(options) {
    const {
        siteCode,
        baseUrl,
        listSelector,
        titleSelector,
        dateSelector,
        targetYear,
        targetDate,
        outputDir,
        skipCount
    } = options;

    const batchDate = moment().format('YYYY-MM-DD');

    console.log('='.repeat(80));
    console.log('  건수 검증 포함 스크래핑');
    console.log('='.repeat(80));
    console.log(`사이트: ${siteCode}`);
    console.log(`날짜: ${batchDate}`);
    console.log('='.repeat(80));
    console.log();

    try {
        let expectedCount = 0;
        let pageCount = 0;

        // ========== 1단계: 예상 건수 카운트 ==========
        if (!skipCount) {
            console.log('[1/3] 예상 건수 카운트 시작...\n');

            await CountValidator.startCounting(siteCode, batchDate);

            const scraper = new AnnouncementScraper({
                targetYear: targetYear,
                targetDate: targetDate,
                outputDir: outputDir,
                siteCode: siteCode,
                baseUrl: baseUrl,
                listSelector: listSelector,
                titleSelector: titleSelector,
                dateSelector: dateSelector
            });

            const countResult = await scraper.countExpectedAnnouncements();
            expectedCount = countResult.totalCount;
            pageCount = countResult.pageCount;

            console.log(`\n예상 건수: ${expectedCount}개 (${pageCount} 페이지)\n`);

            await CountValidator.completeCounting(siteCode, expectedCount, pageCount, batchDate);

        } else {
            console.log('[1/3] 예상 건수 카운트 생략 (--skip-count 옵션)\n');
        }

        // ========== 2단계: 실제 스크래핑 ==========
        console.log('[2/3] 실제 스크래핑 시작...\n');

        await CountValidator.startScraping(siteCode, batchDate);

        const scraper2 = new AnnouncementScraper({
            targetYear: targetYear,
            targetDate: targetDate,
            outputDir: outputDir,
            siteCode: siteCode,
            baseUrl: baseUrl,
            listSelector: listSelector,
            titleSelector: titleSelector,
            dateSelector: dateSelector
        });

        const scrapeResult = await scraper2.scrape();
        const actualCount = scrapeResult.successCount;

        console.log(`\n실제 스크래핑 완료: ${actualCount}개 성공\n`);

        // ========== 3단계: 검증 ==========
        console.log('[3/3] 건수 검증 중...\n');

        const validation = await CountValidator.completeScraping(siteCode, actualCount, batchDate);

        if (validation.success) {
            console.log('='.repeat(80));
            console.log('  검증 결과');
            console.log('='.repeat(80));
            console.log(`예상 건수: ${validation.expectedCount}개`);
            console.log(`실제 건수: ${validation.actualCount}개`);
            console.log(`실패 건수: ${validation.failedCount}개`);
            console.log(`상태: ${validation.status}`);

            if (validation.mismatch) {
                console.log(`\n⚠️ 건수 불일치 감지!`);
                console.log(`누락: ${validation.expectedCount - validation.actualCount}개`);
                console.log();
                console.log('실패한 공고 확인:');
                console.log(`  SELECT * FROM scraper_failed_announcements`);
                console.log(`  WHERE site_code = '${siteCode}' AND batch_date = '${batchDate}';`);
            } else {
                console.log(`\n✅ 건수 일치 - 정상 완료`);
            }

            console.log('='.repeat(80));
        } else {
            console.error('검증 실패:', validation.error);
        }

        console.log();
        console.log('상세 결과 확인:');
        console.log(`  SELECT * FROM scraper_count_validation WHERE site_code = '${siteCode}' AND batch_date = '${batchDate}';`);
        console.log();

    } catch (error) {
        console.error('오류 발생:', error);
        console.error('스택:', error.stack);
        process.exit(1);
    }
}

// CLI 설정
function setupCLI() {
    return yargs
        .option('site', {
            alias: 's',
            type: 'string',
            description: '사이트 코드',
            default: 'andong',
            required: true
        })
        .option('url', {
            alias: 'u',
            type: 'string',
            description: '기본 URL',
            default: 'https://www.andong.go.kr/portal/saeol/gosi/list.do?seCode=04&mId=0401020300',
            required: true
        })
        .option('list-selector', {
            type: 'string',
            description: '리스트 선택자',
            default: 'table.bod_list tbody tr'
        })
        .option('title-selector', {
            type: 'string',
            description: '제목 선택자',
            default: 'td:nth-child(3) a'
        })
        .option('date-selector', {
            type: 'string',
            description: '날짜 선택자',
            default: 'td:nth-child(5)'
        })
        .option('year', {
            alias: 'y',
            type: 'number',
            description: '대상 연도',
            default: new Date().getFullYear()
        })
        .option('date', {
            alias: 'd',
            type: 'string',
            description: '대상 날짜 (YYYYMMDD 형식)',
            default: null
        })
        .option('output', {
            alias: 'o',
            type: 'string',
            description: '출력 디렉토리',
            default: 'scraped_data'
        })
        .option('skip-count', {
            type: 'boolean',
            description: '예상 건수 카운트 생략 (바로 스크래핑)',
            default: false
        })
        .example('$0 --site andong --year 2024', '안동시 2024년 공고 스크래핑 + 건수 검증')
        .example('$0 --site andong --skip-count', '건수 카운트 없이 바로 스크래핑')
        .help()
        .argv;
}

// 메인 실행
async function main() {
    const argv = setupCLI();

    await runScraperWithValidation({
        siteCode: argv.site,
        baseUrl: argv.url,
        listSelector: argv.listSelector,
        titleSelector: argv.titleSelector,
        dateSelector: argv.dateSelector,
        targetYear: argv.year,
        targetDate: argv.date,
        outputDir: argv.output,
        skipCount: argv.skipCount
    });
}

// 스크립트가 직접 실행될 때만 main 함수 호출
if (require.main === module) {
    main().catch(error => {
        console.error('치명적 오류:', error);
        process.exit(1);
    });
}

module.exports = runScraperWithValidation;
