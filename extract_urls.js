#!/usr/bin/env node

/**
 * 상세 URL 추출 스크립트
 *
 * 첨부파일 다운로드나 content.md 파일 생성 없이
 * 상세 URL만 추출하여 DB에 저장
 */

const AnnouncementScraper = require('./node/scraper/andong_scraper');
const UrlManager = require('./node/scraper/url_manager');
const moment = require('moment');
const yargs = require('yargs');

async function extractUrls(options) {
    const {
        siteCode,
        baseUrl,
        listSelector,
        titleSelector,
        dateSelector,
        targetYear,
        targetDate,
        batchDate
    } = options;

    const batch = batchDate || moment().format('YYYY-MM-DD');

    console.log('='.repeat(80));
    console.log('  상세 URL 추출');
    console.log('='.repeat(80));
    console.log(`사이트: ${siteCode}`);
    console.log(`배치 날짜: ${batch}`);
    console.log('='.repeat(80));
    console.log();

    try {
        // 스크래퍼 생성
        const scraper = new AnnouncementScraper({
            targetYear: targetYear,
            targetDate: targetDate,
            outputDir: 'scraped_data', // 사용되지 않지만 필수
            siteCode: siteCode,
            baseUrl: baseUrl,
            listSelector: listSelector,
            titleSelector: titleSelector,
            dateSelector: dateSelector
        });

        // URL 추출 및 저장
        const result = await scraper.extractAndSaveUrls(batch);

        console.log();
        console.log('='.repeat(80));
        console.log('  추출 완료');
        console.log('='.repeat(80));
        console.log(`총 URL 수: ${result.totalCount}개`);
        console.log(`저장 성공: ${result.savedCount}개`);
        console.log(`확인 페이지: ${result.pageCount}개`);
        console.log('='.repeat(80));
        console.log();

        // 통계 조회
        const stats = await UrlManager.getStats(siteCode, batch);

        console.log('DB 통계:');
        console.log(`  - 전체: ${stats.total}개`);
        console.log(`  - 스크래핑 완료: ${stats.scraped}개`);
        console.log(`  - 스크래핑 대기: ${stats.unscraped}개`);
        console.log();

        console.log('확인 SQL:');
        console.log(`  SELECT * FROM scraper_detail_urls WHERE site_code = '${siteCode}' AND batch_date = '${batch}' LIMIT 10;`);
        console.log();

        console.log('통계 SQL:');
        console.log(`  SELECT scraped, COUNT(*) as count FROM scraper_detail_urls`);
        console.log(`  WHERE site_code = '${siteCode}' AND batch_date = '${batch}'`);
        console.log(`  GROUP BY scraped;`);
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
        .option('batch-date', {
            alias: 'b',
            type: 'string',
            description: '배치 날짜 (YYYY-MM-DD 형식, 기본값: 오늘)',
            default: null
        })
        .example('$0 --site andong --year 2024', '안동시 2024년 공고 URL 추출')
        .example('$0 --site andong --date 20240101', '안동시 2024-01-01 이후 공고 URL 추출')
        .help()
        .argv;
}

// 메인 실행
async function main() {
    const argv = setupCLI();

    await extractUrls({
        siteCode: argv.site,
        baseUrl: argv.url,
        listSelector: argv.listSelector,
        titleSelector: argv.titleSelector,
        dateSelector: argv.dateSelector,
        targetYear: argv.year,
        targetDate: argv.date,
        batchDate: argv.batchDate
    });
}

// 스크립트가 직접 실행될 때만 main 함수 호출
if (require.main === module) {
    main().catch(error => {
        console.error('치명적 오류:', error);
        process.exit(1);
    });
}

module.exports = extractUrls;
