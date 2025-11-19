const axios = require('axios');
const https = require('https');
const fs = require('fs');

// SSL 인증서 검증 무시
const httpsAgent = new https.Agent({
    rejectUnauthorized: false,
});

async function testUrl() {
    const url = 'https://gw.riia.or.kr/board/businessAnnouncement';

    console.log('='.repeat(80));
    console.log(`테스트 URL: ${url}`);
    console.log('='.repeat(80) + '\n');

    try {
        const response = await axios.get(url, {
            timeout: 10000,
            maxRedirects: 5,
            validateStatus: () => true,
            httpsAgent: httpsAgent,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            },
        });

        console.log(`HTTP 상태 코드: ${response.status}`);
        console.log(`Content-Type: ${response.headers['content-type']}`);

        // HTML 파일로 저장
        const htmlContent = typeof response.data === 'string'
            ? response.data
            : JSON.stringify(response.data, null, 2);

        fs.writeFileSync('/tmp/riia_response.html', htmlContent, 'utf-8');
        console.log('\n✅ HTML 응답을 /tmp/riia_response.html에 저장했습니다.');

        // HTML에서 title 태그 찾기
        const titleMatch = htmlContent.match(/<title>(.*?)<\/title>/i);
        if (titleMatch) {
            console.log(`\n페이지 제목: ${titleMatch[1]}`);
        }

        // 에러 메시지 찾기
        const errorPatterns = [
            /<h1[^>]*>(.*?)<\/h1>/gi,
            /<div[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)<\/div>/gi,
            /error|오류|실패/gi
        ];

        console.log('\n에러 관련 내용:');
        console.log('-'.repeat(80));

        // h1 태그 검색
        const h1Matches = htmlContent.match(/<h1[^>]*>(.*?)<\/h1>/gi);
        if (h1Matches) {
            h1Matches.forEach(match => {
                const text = match.replace(/<[^>]*>/g, '').trim();
                if (text) {
                    console.log(`H1: ${text}`);
                }
            });
        }

        // body 태그 내용 일부 출력
        const bodyMatch = htmlContent.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
        if (bodyMatch) {
            const bodyContent = bodyMatch[1];
            // script, style 태그 제거
            const cleanBody = bodyContent
                .replace(/<script[\s\S]*?<\/script>/gi, '')
                .replace(/<style[\s\S]*?<\/style>/gi, '')
                .replace(/<[^>]*>/g, ' ')
                .replace(/\s+/g, ' ')
                .trim();

            console.log('\nBody 내용 (처음 1000자):');
            console.log(cleanBody.substring(0, 1000));
        }

    } catch (error) {
        console.log('❌ 오류 발생');
        console.log(`오류: ${error.message}`);
    }
}

testUrl();
