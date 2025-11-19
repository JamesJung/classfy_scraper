const axios = require('axios');
const https = require('https');

// SSL 인증서 검증 무시
const httpsAgent = new https.Agent({
    rejectUnauthorized: false,
});

async function testUrl() {
    const url = 'https://gw.riia.or.kr/board/businessAnnouncement';

    console.log('='.repeat(80));
    console.log(`테스트 URL: ${url}`);
    console.log('='.repeat(80) + '\n');

    const startTime = Date.now();

    try {
        const response = await axios.get(url, {
            timeout: 10000,
            maxRedirects: 5,
            validateStatus: () => true, // 모든 상태 코드 허용
            httpsAgent: httpsAgent,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            },
        });

        const responseTime = Date.now() - startTime;

        console.log('✅ 응답 받음\n');
        console.log(`HTTP 상태 코드: ${response.status}`);
        console.log(`응답 시간: ${responseTime}ms`);
        console.log(`Content-Type: ${response.headers['content-type']}`);
        console.log(`Content-Length: ${response.headers['content-length']}`);

        // 리다이렉트 확인
        if (response.request.res.responseUrl && response.request.res.responseUrl !== url) {
            console.log(`\n리다이렉트됨: ${response.request.res.responseUrl}`);
            console.log(`리다이렉트 횟수: ${response.request._redirectable?._redirectCount || 0}`);
        }

        // 응답 본문 일부 출력
        console.log('\n응답 본문 (처음 500자):');
        console.log('-'.repeat(80));
        const bodyText = typeof response.data === 'string'
            ? response.data
            : JSON.stringify(response.data, null, 2);
        console.log(bodyText.substring(0, 500));
        console.log('-'.repeat(80));

    } catch (error) {
        const responseTime = Date.now() - startTime;

        console.log('❌ 오류 발생\n');
        console.log(`오류 코드: ${error.code}`);
        console.log(`오류 메시지: ${error.message}`);
        console.log(`응답 시간: ${responseTime}ms`);

        if (error.response) {
            console.log(`\nHTTP 상태: ${error.response.status}`);
            console.log(`상태 텍스트: ${error.response.statusText}`);
        }
    }
}

testUrl();
