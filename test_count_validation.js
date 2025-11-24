#!/usr/bin/env node

/**
 * 건수 검증 기능 테스트
 *
 * andong_scraper의 countExpectedAnnouncements() 메소드를 테스트하고
 * 결과를 DB에 저장
 */

const AnnouncementScraper = require('./node/scraper/andong_scraper');
const CountValidator = require('./node/scraper/count_validator');
const moment = require('moment');

async function testCountValidation() {
    console.log('='.repeat(80));
    console.log('  건수 검증 기능 테스트');
    console.log('='.repeat(80));
    console.log();

    const siteCode = 'andong';
    const batchDate = moment().format('YYYY-MM-DD');

    try {
        // 1. 카운트 시작 기록
        console.log('[1단계] 카운트 시작 기록...');
        await CountValidator.startCounting(siteCode, batchDate);
        console.log();

        // 2. andong_scraper로 예상 건수 카운트
        console.log('[2단계] 예상 건수 카운트 시작...');
        const scraper = new AnnouncementScraper({
            targetYear: 2024,
            outputDir: 'scraped_data',
            siteCode: siteCode,
            baseUrl: 'https://www.andong.go.kr/portal/saeol/gosi/list.do?seCode=04&mId=0401020300',
            listSelector: 'table.bod_list tbody tr',
            titleSelector: 'td:nth-child(3) a',
            dateSelector: 'td:nth-child(5)'
        });

        const result = await scraper.countExpectedAnnouncements();

        console.log();
        console.log('카운트 결과:');
        console.log(`  - 예상 건수: ${result.totalCount}개`);
        console.log(`  - 페이지 수: ${result.pageCount}개`);
        console.log();

        // 3. 카운트 완료 기록
        console.log('[3단계] 카운트 완료 기록...');
        await CountValidator.completeCounting(
            siteCode,
            result.totalCount,
            result.pageCount,
            batchDate
        );
        console.log();

        // 4. 검증 결과 조회
        console.log('[4단계] 검증 결과 조회...');
        const validation = await CountValidator.getValidationResult(siteCode, batchDate);

        if (validation) {
            console.log('검증 결과:');
            console.log(`  - 사이트: ${validation.site_code}`);
            console.log(`  - 날짜: ${validation.batch_date}`);
            console.log(`  - 예상 건수: ${validation.expected_count}개`);
            console.log(`  - 페이지 수: ${validation.page_count}개`);
            console.log(`  - 상태: ${validation.status}`);
            console.log(`  - 카운트 시작: ${validation.count_started_at}`);
            console.log(`  - 카운트 완료: ${validation.count_completed_at}`);
        }

        console.log();
        console.log('='.repeat(80));
        console.log('  테스트 완료');
        console.log('='.repeat(80));
        console.log();
        console.log('다음 단계:');
        console.log('1. 실제 스크래핑 실행');
        console.log('2. CountValidator.completeScraping()으로 결과 기록');
        console.log('3. 예상 건수와 실제 건수 비교');
        console.log();
        console.log('확인 SQL:');
        console.log(`  SELECT * FROM scraper_count_validation WHERE site_code = '${siteCode}' AND batch_date = '${batchDate}';`);
        console.log();

    } catch (error) {
        console.error('테스트 실패:', error);
        console.error('스택:', error.stack);
        process.exit(1);
    }
}

// 실행
testCountValidation().catch(error => {
    console.error('치명적 오류:', error);
    process.exit(1);
});
