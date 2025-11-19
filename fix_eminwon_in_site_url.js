const fs = require('fs');

// 1. 기존 site_url.txt에서 기본 스크래퍼만 남기기 (eminwon 제거)
const existingContent = fs.readFileSync('site_url.txt', 'utf8');
const lines = existingContent.split('\n');

// 헤더와 기본 스크래퍼만 유지 (eminwon URL 제외)
const filteredLines = lines.filter(line => {
    if (!line.trim()) return false;
    if (line.includes('site_code|site_url')) return true; // 헤더
    if (line.includes('---')) return true; // 구분선
    if (line.includes('총') && line.includes('스크래퍼')) return false; // 요약 제거
    if (line.includes('eminwon.') || line.includes('.eminwon.')) return false; // eminwon 항목 제거
    return true;
});

// 2. eminwon.json 읽기
const eminwonData = JSON.parse(fs.readFileSync('./node/scraper/eminwon.json', 'utf8'));

const eminwonResults = [];

// 3. eminwon 항목 생성
Object.entries(eminwonData).forEach(([koreanName, hostUrl]) => {
    const siteCode = `prv_${koreanName}`;
    const listUrl = `https://${hostUrl}/emwp/jsp/ofr/OfrNotAncmtL.jsp?not_ancmt_se_code=01,02,03,04,05,06&list_gubun=A`;
    const scraperPath = 'node/scraper/eminwon_scraper.js';
    const scraperName = koreanName;

    eminwonResults.push({
        site_code: siteCode,
        site_url: listUrl,
        scraper_path: scraperPath,
        scraper_name: scraperName
    });
});

// 4. site_code로 정렬
eminwonResults.sort((a, b) => a.site_code.localeCompare(b.site_code));

// 5. 새로운 내용 생성
const newLines = [];
newLines.push(...filteredLines);
newLines.push(''); // 빈 줄

// eminwon 항목 추가
eminwonResults.forEach(r => {
    newLines.push(`${r.site_code}|${r.site_url}|${r.scraper_path}|${r.scraper_name}`);
});

// 6. 요약 추가
const baseScraperCount = filteredLines.filter(line =>
    line.trim() &&
    !line.includes('site_code|site_url') &&
    !line.includes('---')
).length;

newLines.push('');
newLines.push(`총 ${baseScraperCount}개의 기본 스크래퍼 + ${eminwonResults.length}개의 eminwon 사이트 = ${baseScraperCount + eminwonResults.length}개`);

// 7. 파일 저장
const output = newLines.join('\n');
fs.writeFileSync('site_url.txt', output, 'utf8');

console.log('=== site_url.txt 업데이트 완료 ===');
console.log(`기본 스크래퍼: ${baseScraperCount}개`);
console.log(`eminwon 사이트: ${eminwonResults.length}개`);
console.log(`총: ${baseScraperCount + eminwonResults.length}개`);
console.log('\n=== eminwon 샘플 (처음 5개) ===');
eminwonResults.slice(0, 5).forEach(r => {
    console.log(`${r.site_code}|${r.site_url}|${r.scraper_path}|${r.scraper_name}`);
});
