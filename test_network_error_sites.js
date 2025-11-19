const axios = require('axios');
const https = require('https');

// SSL 인증서 검증 무시
const httpsAgent = new https.Agent({
    rejectUnauthorized: false,
});

const testSites = [
    {
        site_code: 'haman',
        url: 'https://www.haman.go.kr/00059/06642/06644.web',
        error: 'Parse Error: Invalid header value char'
    },
    {
        site_code: 'jungnang',
        url: 'https://www.jungnang.go.kr/portal/bbs/list/B0000117.do?menuNo=200475',
        error: 'Parse Error: Unexpected space after start line'
    },
    {
        site_code: 'shinan',
        url: 'https://www.shinan.go.kr/home/www/openinfo/participation_07/participation_07_04/page.wscms',
        error: 'stream has been aborted'
    },
    {
        site_code: 'kohi',
        url: 'https://www.kohi.or.kr/user/bbs/BD_selectBbsList.do?q_bbsCode=1013',
        error: 'stream has been aborted'
    }
];

async function testSite(site) {
    console.log('='.repeat(100));
    console.log(`Site: ${site.site_code}`);
    console.log(`URL: ${site.url}`);
    console.log(`예상 에러: ${site.error}`);
    console.log('-'.repeat(100));

    const startTime = Date.now();

    try {
        const response = await axios.get(site.url, {
            timeout: 10000,
            maxRedirects: 5,
            validateStatus: () => true,
            httpsAgent: httpsAgent,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
        });

        const responseTime = Date.now() - startTime;

        console.log(`✅ 응답 받음`);
        console.log(`HTTP 상태: ${response.status}`);
        console.log(`응답 시간: ${responseTime}ms`);
        console.log(`Content-Type: ${response.headers['content-type']}`);
        console.log(`Content-Length: ${response.headers['content-length'] || 'unknown'}`);

        // HTML 제목 확인
        if (typeof response.data === 'string') {
            const titleMatch = response.data.match(/<title>(.*?)<\/title>/i);
            if (titleMatch) {
                console.log(`페이지 제목: ${titleMatch[1]}`);
            }

            // 본문 일부 출력
            const cleanText = response.data
                .replace(/<script[\s\S]*?<\/script>/gi, '')
                .replace(/<style[\s\S]*?<\/style>/gi, '')
                .replace(/<[^>]*>/g, ' ')
                .replace(/\s+/g, ' ')
                .trim();

            console.log(`\n본문 미리보기 (처음 200자):`);
            console.log(cleanText.substring(0, 200));
        }

    } catch (error) {
        const responseTime = Date.now() - startTime;

        console.log(`❌ 오류 발생`);
        console.log(`오류 코드: ${error.code || 'N/A'}`);
        console.log(`오류 메시지: ${error.message}`);
        console.log(`응답 시간: ${responseTime}ms`);

        if (error.response) {
            console.log(`HTTP 상태: ${error.response.status}`);
        }

        // 에러 스택 일부
        if (error.stack) {
            const stackLines = error.stack.split('\n').slice(0, 3);
            console.log(`\n에러 스택:`);
            stackLines.forEach(line => console.log(`  ${line}`));
        }
    }

    console.log('='.repeat(100) + '\n');
}

async function testAll() {
    console.log('\n🔍 NETWORK_ERROR 사이트 테스트 시작\n');
    console.log(`총 ${testSites.length}개 사이트 테스트\n\n`);

    for (const site of testSites) {
        await testSite(site);
        // 각 요청 사이에 잠시 대기
        await new Promise(resolve => setTimeout(resolve, 1000));
    }

    console.log('\n✅ 모든 테스트 완료\n');
}

testAll();
