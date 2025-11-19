const { request } = require('undici');

const testSites = [
    {
        site_code: 'haman',
        url: 'https://www.haman.go.kr/00059/06642/06644.web',
        originalError: 'Parse Error: Invalid header value char'
    },
    {
        site_code: 'jungnang',
        url: 'https://www.jungnang.go.kr/portal/bbs/list/B0000117.do?menuNo=200475',
        originalError: 'Parse Error: Unexpected space after start line'
    },
    {
        site_code: 'shinan',
        url: 'https://www.shinan.go.kr/home/www/openinfo/participation_07/participation_07_04/page.wscms',
        originalError: 'stream has been aborted'
    },
    {
        site_code: 'kohi',
        url: 'https://www.kohi.or.kr/user/bbs/BD_selectBbsList.do?q_bbsCode=1013',
        originalError: 'stream has been aborted'
    },
    {
        site_code: 'gwba',
        url: 'https://gw.riia.or.kr/board/businessAnnouncement',
        originalError: 'SERVER_ERROR - 서버 오류: 500'
    }
];

async function testWithUndici(site) {
    console.log('='.repeat(100));
    console.log(`Site: ${site.site_code}`);
    console.log(`URL: ${site.url}`);
    console.log(`Axios 에러: ${site.originalError}`);
    console.log('-'.repeat(100));

    const startTime = Date.now();

    try {
        const { statusCode, headers, body } = await request(site.url, {
            method: 'GET',
            headersTimeout: 10000,
            bodyTimeout: 10000,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
        });

        const responseTime = Date.now() - startTime;

        console.log(`✅ undici로 응답 받음`);
        console.log(`HTTP 상태: ${statusCode}`);
        console.log(`응답 시간: ${responseTime}ms`);
        console.log(`Content-Type: ${headers['content-type']}`);
        console.log(`Content-Length: ${headers['content-length'] || 'unknown'}`);

        // Body 읽기
        let bodyText = '';
        try {
            bodyText = await body.text();

            // 제목 추출
            const titleMatch = bodyText.match(/<title>(.*?)<\/title>/i);
            if (titleMatch) {
                console.log(`페이지 제목: ${titleMatch[1]}`);
            }

            // 본문 미리보기
            const cleanText = bodyText
                .replace(/<script[\s\S]*?<\/script>/gi, '')
                .replace(/<style[\s\S]*?<\/style>/gi, '')
                .replace(/<[^>]*>/g, ' ')
                .replace(/\s+/g, ' ')
                .trim();

            console.log(`\n본문 미리보기 (처음 200자):`);
            console.log(cleanText.substring(0, 200));

            // 에러 페이지 체크
            const hasErrorCode = bodyText.includes('error-code') || bodyText.includes('오류 코드');
            if (hasErrorCode) {
                console.log(`\n⚠️  에러 페이지로 보임 (HTML은 로드되었으나 내용은 에러)`);
            }

        } catch (e) {
            console.log(`⚠️  Body 읽기 실패: ${e.message}`);
        }

    } catch (error) {
        const responseTime = Date.now() - startTime;

        console.log(`❌ undici에서도 오류 발생`);
        console.log(`오류 코드: ${error.code || 'N/A'}`);
        console.log(`오류 메시지: ${error.message}`);
        console.log(`응답 시간: ${responseTime}ms`);

        if (error.cause) {
            console.log(`원인: ${error.cause.message || error.cause}`);
        }
    }

    console.log('='.repeat(100) + '\n');
}

async function testAll() {
    console.log('\n🔍 undici로 문제 사이트 재테스트\n');
    console.log(`총 ${testSites.length}개 사이트 테스트\n\n`);

    for (const site of testSites) {
        await testWithUndici(site);
        // 각 요청 사이에 잠시 대기
        await new Promise(resolve => setTimeout(resolve, 1000));
    }

    console.log('\n✅ 모든 테스트 완료\n');

    console.log('📊 요약:');
    console.log('undici는 더 관대한 HTTP 파서를 사용하므로');
    console.log('axios에서 실패하는 사이트들도 처리할 수 있습니다.');
}

testAll();
