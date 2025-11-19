const fs = require('fs');
const path = require('path');

// eminwon.json 읽기
const eminwonData = JSON.parse(fs.readFileSync('./node/scraper/eminwon.json', 'utf8'));

const results = [];

// 각 항목에 대해 site_code와 list_url 생성
Object.entries(eminwonData).forEach(([koreanName, hostUrl]) => {
    // hostUrl에서 site_code 추출
    let siteCode;

    if (hostUrl.startsWith('eminwon.')) {
        // eminwon.XXX.YYY.kr 형태
        const parts = hostUrl.replace('eminwon.', '').split('.');
        if (parts.length >= 3 && parts[1] !== 'go' && parts[1] !== 'kr') {
            // eminwon.gangseo.seoul.kr 같은 경우
            siteCode = `${parts[0]}_${parts[1]}`;
        } else {
            // eminwon.geumcheon.go.kr 같은 경우
            siteCode = parts[0];
        }
    } else {
        // dobong.eminwon.seoul.kr 형태
        const parts = hostUrl.split('.');
        if (parts.length >= 4 && parts[2] !== 'go' && parts[2] !== 'kr') {
            siteCode = `${parts[0]}_${parts[2]}`;
        } else {
            siteCode = parts[0];
        }
    }

    // list_url 생성
    const listUrl = `https://${hostUrl}/emwp/jsp/ofr/OfrNotAncmtL.jsp?not_ancmt_se_code=01,02,03,04,05,06&list_gubun=A`;

    // scraper_path와 scraper_name
    const scraperPath = `node/scraper/${siteCode}_scraper.js`;
    const scraperName = `${siteCode}_scraper.js`;

    results.push({
        site_code: siteCode,
        site_url: listUrl,
        scraper_path: scraperPath,
        scraper_name: scraperName,
        korean_name: koreanName,
        host_url: hostUrl
    });
});

// site_code로 정렬
results.sort((a, b) => a.site_code.localeCompare(b.site_code));

// 콘솔 출력
console.log('\n=== 생성된 eminwon 항목 ===\n');
results.forEach(r => {
    console.log(`${r.site_code}|${r.site_url}|${r.scraper_path}|${r.scraper_name}`);
});

console.log(`\n총 ${results.length}개의 eminwon 사이트 추가`);

// site_url.txt에 추가
const newLines = results.map(r =>
    `${r.site_code}|${r.site_url}|${r.scraper_path}|${r.scraper_name}`
).join('\n');

fs.appendFileSync('site_url.txt', '\n' + newLines);
console.log('\nsite_url.txt에 추가 완료!');
