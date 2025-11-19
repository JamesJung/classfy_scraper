const { request, Agent } = require('undici');

const testUrl = 'https://www.cs.go.kr/news/00002679/00006203.web';

async function test1() {
    console.log('테스트 1: connect 옵션 사용');
    try {
        const { statusCode } = await request(testUrl, {
            connect: {
                rejectUnauthorized: false
            }
        });
        console.log(`✅ 성공: ${statusCode}\n`);
    } catch (error) {
        console.log(`❌ 실패: ${error.message}\n`);
    }
}

async function test2() {
    console.log('테스트 2: Agent 사용');
    try {
        const agent = new Agent({
            connect: {
                rejectUnauthorized: false
            }
        });

        const { statusCode } = await request(testUrl, {
            dispatcher: agent
        });
        console.log(`✅ 성공: ${statusCode}\n`);
    } catch (error) {
        console.log(`❌ 실패: ${error.message}\n`);
    }
}

async function test3() {
    console.log('테스트 3: tls 옵션 직접 사용');
    try {
        const { statusCode } = await request(testUrl, {
            tls: {
                rejectUnauthorized: false
            }
        });
        console.log(`✅ 성공: ${statusCode}\n`);
    } catch (error) {
        console.log(`❌ 실패: ${error.message}\n`);
    }
}

async function main() {
    console.log('='.repeat(80));
    console.log('undici SSL 검증 비활성화 방법 테스트');
    console.log('='.repeat(80) + '\n');

    await test1();
    await test2();
    await test3();

    console.log('테스트 완료');
}

main();
