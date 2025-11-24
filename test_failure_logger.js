#!/usr/bin/env node

/**
 * FailureLogger 테스트 스크립트
 *
 * 실제 실패 공고를 시뮬레이션하여 DB 기록 테스트
 */

const FailureLogger = require('./node/scraper/failure_logger');

async function testFailureLogger() {
    console.log('=' .repeat(80));
    console.log('  FailureLogger 테스트 시작');
    console.log('=' .repeat(80));
    console.log();

    // 테스트 데이터
    const testFailures = [
        {
            site_code: 'test_site_1',
            title: '테스트 공고 1 - 타임아웃',
            url: 'http://test.com/list/1',
            detail_url: 'http://test.com/detail/1',
            error_type: 'timeout',
            error_message: 'Request timeout after 10 seconds'
        },
        {
            site_code: 'test_site_1',
            title: '테스트 공고 2 - 네트워크 에러',
            url: 'http://test.com/list/2',
            detail_url: 'http://test.com/detail/2',
            error_type: 'network_error',
            error_message: 'ECONNREFUSED'
        },
        {
            site_code: 'test_site_2',
            title: '테스트 공고 3 - 파싱 에러',
            url: 'http://test2.com/list/3',
            detail_url: 'http://test2.com/detail/3',
            error_type: 'parse_error',
            error_message: 'Cannot read property of undefined'
        }
    ];

    console.log(`${testFailures.length}개의 테스트 실패 공고 기록 중...\n`);

    // 각 실패 공고 기록
    for (const [index, failure] of testFailures.entries()) {
        console.log(`[${index + 1}/${testFailures.length}] ${failure.title}`);

        const result = await FailureLogger.logFailedAnnouncement(failure);

        if (result) {
            console.log('  ✓ DB 기록 성공');
        } else {
            console.log('  ✗ DB 기록 실패');
        }

        console.log();
    }

    // 기록된 개수 확인
    console.log('=' .repeat(80));
    console.log('  기록 완료 - DB에서 확인하세요');
    console.log('=' .repeat(80));
    console.log();
    console.log('확인 SQL:');
    console.log('  SELECT * FROM scraper_failed_announcements');
    console.log("  WHERE site_code LIKE 'test_site_%'");
    console.log('  ORDER BY created_at DESC;');
    console.log();
    console.log('삭제 SQL (테스트 후):');
    console.log("  DELETE FROM scraper_failed_announcements WHERE site_code LIKE 'test_site_%';");
    console.log();
}

// 실행
testFailureLogger().catch(error => {
    console.error('테스트 실패:', error);
    process.exit(1);
});
