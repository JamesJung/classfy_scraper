const fs = require('fs');
const path = require('path');

const scraperDir = './node/scraper';
const files = fs.readdirSync(scraperDir).filter(f => f.endsWith('_scraper.js'));

const results = [];

files.forEach(file => {
    const filePath = path.join(scraperDir, file);
    const content = fs.readFileSync(filePath, 'utf8');

    // site 추출
    const siteMatch = content.match(/\.option\('site'[^}]+default:\s*['"]([^'"]+)['"]/);
    const site = siteMatch ? siteMatch[1] : null;

    // url 추출 (여러 줄에 걸쳐있을 수 있음)
    const urlMatch = content.match(/\.option\('url'[^}]+default:\s*['"]([^'"]+)['"]/s);
    const url = urlMatch ? urlMatch[1] : null;

    if (site && url) {
        results.push({
            site_code: site,
            site_url: url,
            scraper_path: filePath,
            scraper_name: file
        });
    }
});

// 정렬
results.sort((a, b) => a.site_code.localeCompare(b.site_code));

// 출력 및 파일 저장
const lines = [];
lines.push('site_code|site_url|scraper_path|scraper_name');
lines.push('-'.repeat(120));

results.forEach(r => {
    lines.push(`${r.site_code}|${r.site_url}|${r.scraper_path}|${r.scraper_name}`);
});

lines.push('');
lines.push(`총 ${results.length}개의 스크래퍼 발견`);

const output = lines.join('\n');

// 콘솔 출력
console.log(output);

// site_url.txt에 overwrite
fs.writeFileSync('site_url.txt', output, 'utf8');
console.log('\nsite_url.txt에 저장 완료!');
