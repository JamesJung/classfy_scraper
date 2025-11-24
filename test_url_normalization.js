#!/usr/bin/env node

/**
 * URL 정규화 테스트
 *
 * page 파라미터 제거 기능 테스트
 */

const UrlManager = require('./node/scraper/url_manager');

function testUrlNormalization() {
    console.log('='.repeat(80));
    console.log('  URL 정규화 테스트');
    console.log('='.repeat(80));
    console.log();

    // 테스트 케이스
    const testCases = [
        {
            name: '경기도 - page 파라미터 제거',
            original: 'https://www.gg.go.kr/bbs/boardView.do?bIdx=201528470&bsIdx=469&bcIdx=0&menuId=1547&isManager=false&isCharge=false&page=10',
            expected: 'https://www.gg.go.kr/bbs/boardView.do?bIdx=201528470&bsIdx=469&bcIdx=0&menuId=1547'
        },
        {
            name: '경기도 - 다른 page 번호',
            original: 'https://www.gg.go.kr/bbs/boardView.do?bIdx=201528459&bsIdx=469&bcIdx=0&menuId=1547&isManager=false&isCharge=false&page=11',
            expected: 'https://www.gg.go.kr/bbs/boardView.do?bIdx=201528459&bsIdx=469&bcIdx=0&menuId=1547'
        },
        {
            name: '거제시 - page 파라미터 없음',
            original: 'https://www.gjcity.go.kr/portal/saeol/gosi/view.do?notAncmtMgtNo=73994&mId=0202010000',
            expected: 'https://www.gjcity.go.kr/portal/saeol/gosi/view.do?notAncmtMgtNo=73994&mId=0202010000'
        },
        {
            name: '거제시 - 다른 공고',
            original: 'https://www.gjcity.go.kr/portal/saeol/gosi/view.do?notAncmtMgtNo=73903&mId=0202010000',
            expected: 'https://www.gjcity.go.kr/portal/saeol/gosi/view.do?notAncmtMgtNo=73903&mId=0202010000'
        },
        {
            name: 'pageNum 파라미터',
            original: 'https://example.com/board/view?id=123&pageNum=5',
            expected: 'https://example.com/board/view?id=123'
        },
        {
            name: 'pageIndex 파라미터',
            original: 'https://example.com/board/view?id=456&pageIndex=3&size=20',
            expected: 'https://example.com/board/view?id=456'
        },
        {
            name: 'currentPage 파라미터',
            original: 'https://example.com/board/view?id=789&currentPage=2',
            expected: 'https://example.com/board/view?id=789'
        },
        {
            name: '여러 page 관련 파라미터',
            original: 'https://example.com/board/view?id=999&page=1&pageSize=10&offset=20',
            expected: 'https://example.com/board/view?id=999'
        }
    ];

    let passCount = 0;
    let failCount = 0;

    testCases.forEach((testCase, index) => {
        const normalized = UrlManager.normalizeUrl(testCase.original);
        const hash = UrlManager.hashUrl(normalized);
        const isPassed = normalized === testCase.expected;

        console.log(`[테스트 ${index + 1}] ${testCase.name}`);
        console.log(`  원본:     ${testCase.original}`);
        console.log(`  정규화:   ${normalized}`);
        console.log(`  예상:     ${testCase.expected}`);
        console.log(`  해시:     ${hash.substring(0, 16)}...`);
        console.log(`  결과:     ${isPassed ? '✅ 통과' : '❌ 실패'}`);
        console.log();

        if (isPassed) {
            passCount++;
        } else {
            failCount++;
        }
    });

    console.log('='.repeat(80));
    console.log('  테스트 결과');
    console.log('='.repeat(80));
    console.log(`통과: ${passCount}개`);
    console.log(`실패: ${failCount}개`);
    console.log(`전체: ${testCases.length}개`);
    console.log('='.repeat(80));
    console.log();

    // 중복 체크 테스트
    console.log('중복 체크 테스트:');
    const url1 = 'https://www.gg.go.kr/bbs/boardView.do?bIdx=201528470&bsIdx=469&bcIdx=0&menuId=1547&isManager=false&isCharge=false&page=10';
    const url2 = 'https://www.gg.go.kr/bbs/boardView.do?bIdx=201528470&bsIdx=469&bcIdx=0&menuId=1547&isManager=false&isCharge=false&page=99';
    const url3 = 'https://www.gg.go.kr/bbs/boardView.do?bIdx=999999999&bsIdx=469&bcIdx=0&menuId=1547&isManager=false&isCharge=false&page=1';

    const hash1 = UrlManager.hashUrl(UrlManager.normalizeUrl(url1));
    const hash2 = UrlManager.hashUrl(UrlManager.normalizeUrl(url2));
    const hash3 = UrlManager.hashUrl(UrlManager.normalizeUrl(url3));

    console.log(`  URL1 (page=10) 해시: ${hash1.substring(0, 16)}...`);
    console.log(`  URL2 (page=99) 해시: ${hash2.substring(0, 16)}...`);
    console.log(`  URL3 (다른 bIdx)  해시: ${hash3.substring(0, 16)}...`);
    console.log();
    console.log(`  URL1 === URL2: ${hash1 === hash2 ? '✅ 같음 (정상)' : '❌ 다름 (오류)'}`);
    console.log(`  URL1 === URL3: ${hash1 === hash3 ? '❌ 같음 (오류)' : '✅ 다름 (정상)'}`);
    console.log();
}

// 실행
testUrlNormalization();
