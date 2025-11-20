#!/usr/bin/env node

/**
 * Eminwon 개별 공고 상세 페이지 다운로드 스크립트
 * 증분 수집 시 새로 발견된 공고만 다운로드하기 위한 용도
 */

const { chromium } = require('playwright');
const fs = require('fs-extra');
const path = require('path');
const yargs = require('yargs');

class EminwonDetailScraper {
    constructor(options = {}) {
        this.region = options.region;
        this.url = options.url;
        this.outputDir = options.outputDir || `eminwon_data_new/${new Date().toISOString().split('T')[0]}/${this.region}`;
        this.folderName = options.folderName;
        this.announcementData = options.announcementData || {}; // 리스트에서 받은 공고 데이터

        this.browser = null;
        this.page = null;
    }

    async init() {
        this.browser = await chromium.launch({
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });

        const context = await this.browser.newContext({
            userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport: { width: 1920, height: 1080 },
            locale: 'ko-KR',
            extraHTTPHeaders: {
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
            }
        });

        this.page = await context.newPage();

        // 다운로드 디렉토리 설정
        const downloadPath = path.join(this.outputDir, this.folderName, 'attachments');
        await fs.ensureDir(downloadPath);

        // 다운로드 이벤트 처리는 제거 - 수동으로 처리하여 파일명 필터링 적용
    }

    async downloadDetailPage() {
        try {
            console.error(`상세 페이지 접근: ${this.url}`);

            // 상세 페이지 로드
            await this.page.goto(this.url, {
                waitUntil: 'networkidle',
                timeout: 30000
            });

            await this.page.waitForTimeout(3000);

            // 페이지 내용 추출
            const content = await this.page.evaluate(() => {
                const result = {
                    title: '',
                    content: '',
                    metadata: {},
                    attachments: []
                };

                // 제목 추출 (우선순위: 테이블에서 찾기 -> h3/h4 태그)
                // 테이블 방식으로 제목 찾기 (이민원 사이트 특징)
                const tables = document.querySelectorAll('table');
                for (const table of tables) {
                    const rows = table.querySelectorAll('tr');
                    for (const row of rows) {
                        const cells = row.querySelectorAll('td, th');
                        if (cells.length >= 2) {
                            const labelText = cells[0].textContent.trim();
                            if (labelText === '제목' || labelText.includes('제목')) {
                                result.title = cells[1].textContent.trim();
                                break;
                            }
                        }
                    }
                    if (result.title) break;
                }

                // 테이블에서 못찾았으면 일반 선택자로 시도
                if (!result.title) {
                    const titleElement = document.querySelector('.view_subject, .tit_view, .board-view-title, h3, h4');
                    if (titleElement) {
                        result.title = titleElement.textContent.trim();
                    }
                }

                // 본문 추출
                const contentElement = document.querySelector('.view_content, .cont_view, .board-view-content, .content');
                if (contentElement) {
                    result.content = contentElement.textContent.trim();
                } else {
                    // 폴백: 전체 텍스트
                    result.content = document.body.textContent.trim();
                }

                // 메타데이터 추출 (작성일, 부서 등)
                const metaElements = document.querySelectorAll('.view_info li, .info_view li, .board-view-info li');
                metaElements.forEach(el => {
                    const text = el.textContent.trim();
                    if (text.includes('작성일') || text.includes('등록일')) {
                        result.metadata.date = text.split(':').pop().trim();
                    }
                    if (text.includes('부서') || text.includes('담당')) {
                        result.metadata.department = text.split(':').pop().trim();
                    }
                });

                // 첨부파일 정보 추출
                // 모든 a 태그 검사 (onclick 또는 href에 goDownLoad가 있는 경우)
                const allLinks = document.querySelectorAll('a');
                allLinks.forEach(link => {
                    const onclickAttr = link.getAttribute('onclick') || '';
                    const hrefAttr = link.getAttribute('href') || '';
                    const linkText = link.textContent.trim();

                    // href에 javascript:goDownLoad가 있는 경우
                    if (hrefAttr.includes('javascript:goDownLoad')) {
                        const jsCode = hrefAttr.replace('javascript:', '');
                        // goDownLoad('user_file', 'sys_file', 'file_path') 매개변수 추출
                        const match = jsCode.match(/goDownLoad\(['"]([^'"]*)['"],\s*['"]([^'"]*)['"],\s*['"]([^'"]*)['"]/);
                        if (match) {
                            const [, userFileName, sysFileName, filePath] = match;
                            // URL 디코딩
                            const decodedName = decodeURIComponent(userFileName);

                            // 실제 다운로드 URL 구성 (content.md에 표시용)
                            const baseUrl = window.location.origin;
                            const downloadUrl = `${baseUrl}/emwp/jsp/lga/homepage/FileDown.jsp?file_seq=${encodeURIComponent(sysFileName)}&org_file_nm=${encodeURIComponent(userFileName)}&save_file_nm=${encodeURIComponent(sysFileName)}&file_path=${encodeURIComponent(filePath)}`;

                            result.attachments.push({
                                name: decodedName || linkText,
                                url: downloadUrl,  // content.md에 표시할 실제 다운로드 URL
                                onclick: jsCode,
                                userFileName: userFileName,
                                sysFileName: sysFileName,
                                filePath: filePath,
                                type: 'goDownLoad'  // goDownLoad 함수 사용
                            });
                        }
                    }
                    // onclick에 goDownLoad가 있는 경우
                    else if (onclickAttr.includes('goDownLoad')) {
                        const match = onclickAttr.match(/goDownLoad\(['"]([^'"]*)['"],\s*['"]([^'"]*)['"],\s*['"]([^'"]*)['"]/);
                        if (match) {
                            const [, userFileName, sysFileName, filePath] = match;
                            const decodedName = decodeURIComponent(userFileName);

                            // 실제 다운로드 URL 구성 (content.md에 표시용)
                            const baseUrl = window.location.origin;
                            const downloadUrl = `${baseUrl}/emwp/jsp/lga/homepage/FileDown.jsp?file_seq=${encodeURIComponent(sysFileName)}&org_file_nm=${encodeURIComponent(userFileName)}&save_file_nm=${encodeURIComponent(sysFileName)}&file_path=${encodeURIComponent(filePath)}`;

                            result.attachments.push({
                                name: decodedName || linkText,
                                url: downloadUrl,  // content.md에 표시할 실제 다운로드 URL
                                onclick: onclickAttr,
                                userFileName: userFileName,
                                sysFileName: sysFileName,
                                filePath: filePath,
                                type: 'goDownLoad'  // goDownLoad 함수 사용
                            });
                        }
                    }
                });

                // fileDown 패턴도 추가
                const fileDownLinks = document.querySelectorAll('a[onclick*="fileDown"]:not([onclick*="goDownLoad"])');
                fileDownLinks.forEach(link => {
                    const onclickAttr = link.getAttribute('onclick');
                    const linkText = link.textContent.trim();

                    if (onclickAttr && linkText) {
                        result.attachments.push({
                            name: linkText,
                            url: `javascript:${onclickAttr}`,
                            onclick: onclickAttr,
                            type: 'fileDown'
                        });
                    }
                });

                return result;
            });

            // content.md 파일 생성 (announcementData 전달)
            const contentMd = this.formatContentMd(content, this.announcementData);
            const contentPath = path.join(this.outputDir, this.folderName, 'content.md');
            await fs.ensureDir(path.dirname(contentPath));
            await fs.writeFile(contentPath, contentMd, 'utf8');
            console.error(`✓ content.md 저장 완료`);

            // 첨부파일 다운로드 (eminwon_scraper.js 방식)
            if (content.attachments.length > 0) {
                console.error(`첨부파일 ${content.attachments.length}개 다운로드 시작...`);

                for (const attachment of content.attachments) {
                    // 불필요한 파일 필터링
                    if (!attachment.name ||
                        attachment.name === '_ _' ||
                        attachment.name === '_  _' ||
                        attachment.name.trim() === '' ||
                        attachment.name.includes('FileDown.jsp') ||
                        attachment.name.includes('.jsp') ||
                        attachment.name.length < 3) {
                        console.error(`  ✗ 건너뛰기: ${attachment.name} (불필요한 파일)`);
                        continue;
                    }

                    try {
                        console.error(`  다운로드 시도: ${attachment.name}`);

                        // goDownLoad 타입인 경우
                        if (attachment.type === 'goDownLoad' && attachment.userFileName) {
                            console.error(`    goDownLoad 방식: ${attachment.userFileName}`);

                            const downloadPromise = this.page.waitForEvent('download', { timeout: 60000 });

                            await this.page.evaluate((params) => {
                                const { userFileName, sysFileName, filePath } = params;
                                if (typeof window.goDownLoad === 'function') {
                                    window.goDownLoad(userFileName, sysFileName, filePath);
                                } else {
                                    console.error('goDownLoad 함수를 찾을 수 없음');
                                    throw new Error('goDownLoad 함수를 찾을 수 없음');
                                }
                            }, {
                                userFileName: attachment.userFileName,
                                sysFileName: attachment.sysFileName,
                                filePath: attachment.filePath
                            });

                            const download = await downloadPromise;
                            let fileName = attachment.name || `attachment_${content.attachments.indexOf(attachment) + 1}`;
                            fileName = fileName.replace(/[<>:"/\\|?*]/g, '_');
                            const downloadPath = path.join(this.outputDir, this.folderName, 'attachments', fileName);
                            await download.saveAs(downloadPath);
                            console.error(`    ✓ 저장: ${fileName}`);
                        }
                        // onclick이 있는 경우
                        else if (attachment.onclick) {
                            console.error(`    onclick 방식: ${attachment.onclick.substring(0, 50)}...`);

                            const downloadPromise = this.page.waitForEvent('download', { timeout: 60000 });

                            await this.page.evaluate((onclick) => {
                                eval(onclick);
                            }, attachment.onclick);

                            const download = await downloadPromise;
                            let fileName = attachment.name || `attachment_${content.attachments.indexOf(attachment) + 1}`;
                            fileName = fileName.replace(/[<>:"/\\|?*]/g, '_');
                            const downloadPath = path.join(this.outputDir, this.folderName, 'attachments', fileName);
                            await download.saveAs(downloadPath);
                            console.error(`    ✓ 저장: ${fileName}`);
                        }
                        // href가 있는 경우 (직접 링크)
                        else if (attachment.href) {
                            console.error(`    직접 링크 방식: ${attachment.href.substring(0, 50)}...`);

                            const downloadPromise = this.page.waitForEvent('download', { timeout: 60000 });

                            await this.page.evaluate((href) => {
                                const link = document.querySelector(`a[href="${href}"]`);
                                if (link) {
                                    link.click();
                                } else {
                                    window.location.href = href;
                                }
                            }, attachment.href);

                            const download = await downloadPromise;
                            let fileName = attachment.name || `attachment_${content.attachments.indexOf(attachment) + 1}`;
                            fileName = fileName.replace(/[<>:"/\\|?*]/g, '_');
                            const downloadPath = path.join(this.outputDir, this.folderName, 'attachments', fileName);
                            await download.saveAs(downloadPath);
                            console.error(`    ✓ 저장: ${fileName}`);
                        } else {
                            console.error(`    ✗ 다운로드 방법을 찾을 수 없음`);
                            continue;
                        }

                        await this.page.waitForTimeout(500);
                    } catch (err) {
                        console.error(`    ✗ 첨부파일 다운로드 실패: ${attachment.name} - ${err.message}`);
                    }
                }
            }

            // 스크린샷 저장
            const screenshotPath = path.join(this.outputDir, this.folderName, 'screenshot.png');
            await this.page.screenshot({ path: screenshotPath, fullPage: true });
            console.error(`✓ 스크린샷 저장 완료`);

            // 실제 제목 반환 (폴더명 생성용)
            const actualTitle = content.title || this.announcementData?.title || '제목 없음';

            // JSON으로 결과 출력 (Python에서 파싱용)
            console.log(JSON.stringify({
                status: 'success',
                actualTitle: actualTitle,
                folderName: this.folderName
            }));

            return true;

        } catch (error) {
            console.error(`상세 페이지 다운로드 실패: ${error.message}`);
            return false;
        }
    }

    formatContentMd(content, announcementData) {
        // 제목: 페이지에서 추출한 제목이 없거나 "제목 없음"이면 리스트에서 받은 제목 사용
        let title = content.title;
        if (!title || title === '제목 없음' || title.trim() === '') {
            title = announcementData?.title || '제목 없음';
        }

        // 제목에서 공고 번호 패턴 제거
        // 예: "증평군 공고 제2025-856호" -> "증평군 공고 제2025-856호"로 유지 (공고번호가 유일한 제목일 수 있음)
        // 하지만 폴더명은 공고번호를 포함해야 함

        let md = `# ${title}\n\n`;

        // URL
        md += `**원본 URL**: ${this.url}\n\n`;

        // 날짜 정보 추가
        const date = content.metadata.date || announcementData?.date;
        console.log("content.metadata", content.metadata)
        console.log("announcementData", announcementData)


        console.log("date", date)
        if (date) {
            md += `**작성일**: ${date}\n\n`;
        }

        // 기타 메타데이터
        if (Object.keys(content.metadata).length > 0) {
            md += `## 정보\n`;
            for (const [key, value] of Object.entries(content.metadata)) {
                if (key !== 'date') { // 날짜는 이미 위에서 처리
                    md += `- **${key}**: ${value}\n`;
                }
            }
            md += `\n`;
        }

        // 본문
        md += `## 내용\n\n${content.content}\n\n`;

        // 첨부파일 (URL 형식 포함)
        if (content.attachments.length > 0) {
            md += `**첨부파일**:\n`;
            content.attachments.forEach(att => {
                // URL 형식: 파일명: URL
                if (att.url) {
                    md += `- ${att.name}: ${att.url}\n`;
                } else {
                    md += `- ${att.name}\n`;
                }
            });
        }

        return md;
    }

    async run() {
        try {
            await this.init();

            console.error(`=== ${this.region} 상세 페이지 다운로드 ===`);
            console.error(`폴더: ${this.folderName}`);
            console.error(`출력: ${this.outputDir}`);

            const success = await this.downloadDetailPage();

            if (success) {
                console.error(`✅ 다운로드 완료`);
                process.exit(0);
            } else {
                console.error(`❌ 다운로드 실패`);
                process.exit(1);
            }

        } catch (error) {
            console.error('실행 중 오류:', error);
            process.exit(1);
        } finally {
            if (this.browser) {
                await this.browser.close();
            }
        }
    }
}

// CLI 인터페이스
const argv = yargs
    .option('region', {
        alias: 'r',
        description: '지역명',
        type: 'string',
        demandOption: true
    })
    .option('url', {
        alias: 'u',
        description: '상세 페이지 URL',
        type: 'string',
        demandOption: true
    })
    .option('output-dir', {
        alias: 'o',
        description: '출력 디렉토리',
        type: 'string'
    })
    .option('folder-name', {
        alias: 'f',
        description: '폴더명',
        type: 'string',
        demandOption: true
    })
    .option('title', {
        description: '공고 제목 (리스트에서 가져온)',
        type: 'string'
    })
    .option('date', {
        description: '공고 날짜 (리스트에서 가져온)',
        type: 'string'
    })
    .help()
    .argv;

// 실행
const scraper = new EminwonDetailScraper({
    region: argv.region,
    url: argv.url,
    outputDir: argv['output-dir'],
    folderName: argv['folder-name'],
    announcementData: {
        title: argv.title,
        date: argv.date
    }
});

scraper.run();