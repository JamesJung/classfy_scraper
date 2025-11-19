const { request, Agent } = require('undici');

// SSL 인증서 검증 비활성화
const httpsAgent = new Agent({
    connect: {
        rejectUnauthorized: false
    }
});

const testSites = [
    {
        name: 'jungnang',
        url: 'https://www.jungnang.go.kr/portal/bbs/list/B0000117.do?menuNo=200475',
        expectedError: 'HTTP 응답 라인 파싱 에러'
    },
    {
        name: 'anyang',
        url: 'https://www.anyang.go.kr/main/emwsWebList.do?key=4101&searchGosiSe=01,04',
        expectedError: '서버 오류 503'
    }
];

async function testSite(site) {
    console.log('='.repeat(100));
    console.log(`테스트: ${site.name}`);
    console.log(`URL: ${site.url}`);
    console.log(`예상 에러: ${site.expectedError}`);
    console.log('-'.repeat(100));

    const startTime = Date.now();

    try {
        const { statusCode, headers, body } = await request(site.url, {
            method: 'GET',
            headersTimeout: 30000,
            bodyTimeout: 30000,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
            dispatcher: httpsAgent
        });

        const responseTime = Date.now() - startTime;

        console.log(`✅ undici 성공`);
        console.log(`HTTP 상태: ${statusCode}`);
        console.log(`응답 시간: ${responseTime}ms`);
        console.log(`Content-Type: ${headers['content-type']}`);

        // Body 읽기
        const bodyText = await body.text();

        // 제목 추출
        const titleMatch = bodyText.match(/<title>(.*?)<\/title>/i);
        if (titleMatch) {
            console.log(`페이지 제목: ${titleMatch[1]}`);
        }

        // 본문 길이
        console.log(`응답 크기: ${bodyText.length} bytes`);

        // 에러 페이지 체크
        const hasErrorKeywords = bodyText.includes('오류') ||
                                  bodyText.includes('error') ||
                                  bodyText.includes('503') ||
                                  bodyText.includes('Service Unavailable');

        if (hasErrorKeywords) {
            console.log(`⚠️  응답에 에러 키워드 발견`);
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

        // 응답 헤더 출력
        console.log(`\n주요 헤더:`);
        console.log(`- Server: ${headers.server || 'N/A'}`);
        console.log(`- Content-Length: ${headers['content-length'] || 'N/A'}`);
        console.log(`- Cache-Control: ${headers['cache-control'] || 'N/A'}`);

    } catch (error) {
        const responseTime = Date.now() - startTime;

        console.log(`❌ undici 에러 발생`);
        console.log(`에러 타입: ${error.code || 'N/A'}`);
        console.log(`에러 메시지: ${error.message}`);
        console.log(`응답 시간: ${responseTime}ms`);

        if (error.message.includes('Invalid header value char')) {
            console.log(`\n🔍 분석: HTTP 헤더에 유효하지 않은 문자 포함`);
            console.log(`   → 서버가 HTTP 표준을 완벽하게 따르지 않음`);
            console.log(`   → 브라우저는 관대하게 처리하므로 정상 작동`);
        } else if (error.message.includes('Unexpected space after start line')) {
            console.log(`\n🔍 분석: HTTP 응답 시작 라인에 예상치 못한 공백`);
            console.log(`   → 서버가 HTTP 프로토콜을 잘못 구현`);
            console.log(`   → 브라우저는 관대하게 처리하므로 정상 작동`);
        }
    }

    console.log('='.repeat(100) + '\n');
}

async function main() {
    console.log('\n🔍 문제 사이트 상세 분석\n');

    for (const site of testSites) {
        await testSite(site);
        await new Promise(resolve => setTimeout(resolve, 1000));
    }

    console.log('\n📊 요약');
    console.log('='.repeat(100));
    console.log('두 사이트 모두 브라우저에서는 정상 작동하지만,');
    console.log('HTTP 클라이언트에서는 에러가 발생하는 경우입니다.');
    console.log('이는 서버가 HTTP 표준을 완벽하게 따르지 않기 때문입니다.');
    console.log('='.repeat(100));
}

main();
