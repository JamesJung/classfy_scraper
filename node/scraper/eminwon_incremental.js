#!/usr/bin/env node

/**
 * Eminwon 증분 수집용 리스트 수집기
 * 
 * Python orchestrator와 연동하여 공고 리스트만 수집
 * 실제 다운로드는 기존 eminwon_scraper.js 활용
 */

const { chromium } = require('playwright');
const cheerio = require('cheerio');
const fs = require('fs-extra');
const path = require('path');
const moment = require('moment');
const yargs = require('yargs');

class EminwonListCollector {
    constructor(options = {}) {
        this.region = options.region || '청주';
        this.maxPages = options.maxPages || 3;
        this.mode = options.mode || 'list';
        
        // eminwon.json에서 호스트 정보 로드
        this.eminwonHosts = this.loadEminwonHosts();
        const hostUrl = this.eminwonHosts[this.region];
        
        if (!hostUrl) {
            throw new Error(`지역 '${this.region}'에 대한 호스트 정보를 찾을 수 없습니다.`);
        }
        
        this.baseUrl = `https://${hostUrl}`;
        this.listUrl = `https://${hostUrl}/emwp/jsp/ofr/OfrNotAncmtL.jsp?not_ancmt_se_code=01,02,03,04,05&list_gubun=A`;
        this.actionUrl = `https://${hostUrl}/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do`;
        
        // 지역별 테이블 셀렉터 정보
        this.selectorInfo = {
            "울산북구": {
                "table": ".cont_table",
                "titleIndex": 2, "dateIndex": 4
            },
            "부산중구": {
                "table": ".bbs_ltype",
                "titleIndex": 1, "dateIndex": 3
            },
            "부산강서구": {
                "table": ".tb_board",
                "titleIndex": 1, "dateIndex": 3
            },
            "평창군": {
                "table": ".tb_board",
                "titleIndex": 3, "dateIndex": 7
            },
            "해운대구": {
                "table": ".tstyle_list",
                "titleIndex": 1, "dateIndex": 3
            },
            "수영구": {
                "table": ".list01",
                "titleIndex": 1, "dateIndex": 3
            },
            "부산진구": {
                "table": ".board-list-wrap table",
                "titleIndex": 1, "dateIndex": 3
            },
            "부산서구": {
                "table": ".board-list-wrap table",
                "titleIndex": 1, "dateIndex": 3
            },
            "광주동구": {
                "table": ".dbody",
                "rowSelector": "ul",
                "cellSelector": "li",
                "titleIndex": 2, "dateIndex": 4
            },
            "울산남구": {
                "table": ".basic_table",
                "titleIndex": 1, "dateIndex": 3
            },
            "울산동구": {
                "table": ".bbs_list",
                "titleIndex": 1, "dateIndex": 3
            },
            "연수구": {
                "table": ".general_board",
                "titleIndex": 1, "dateIndex": 3
            }
        };
        
        this.browser = null;
        this.page = null;
    }
    
    loadEminwonHosts() {
        try {
            const hostPath = path.join(__dirname, 'eminwon.json');
            return JSON.parse(fs.readFileSync(hostPath, 'utf8'));
        } catch (error) {
            console.error('eminwon.json 파일을 읽을 수 없습니다:', error);
            process.exit(1);
        }
    }
    
    async init() {
        this.browser = await chromium.launch({
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });
        
        const context = await this.browser.newContext({
            userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        });
        
        this.page = await context.newPage();
        
        // 네트워크 타임아웃 설정
        this.page.setDefaultTimeout(30000);
    }
    
    async collectListPage(pageNum) {
        const announcements = [];
        
        try {
            if (pageNum === 1) {
                // 서블릿 URL로 바로 접근 (JSP는 리다이렉트 문제 있음)
                const servletUrl = this.buildServletUrl(1);
                console.error(`서블릿 URL로 접근: ${servletUrl}`);
                try {
                    await this.page.goto(servletUrl, {
                        waitUntil: 'domcontentloaded',
                        timeout: 10000
                    });
                    console.error(`페이지 로드 성공`);
                    await this.page.waitForTimeout(2000);
                } catch (error) {
                    console.error(`페이지 로드 실패: ${error.message}`);
                    return announcements;
                }
            } else {
                // 다음 페이지는 JavaScript 함수 호출
                await this.page.evaluate((page) => {
                    if (typeof goPage === 'function') {
                        goPage(page);
                    } else if (typeof fn_egov_link_page === 'function') {
                        fn_egov_link_page(page);
                    }
                }, pageNum);
                
                // 페이지 로드 대기
                await this.page.waitForTimeout(2000);
            }
            
            // HTML 가져오기 - 더 간단한 방식으로
            console.error(`페이지 컨텐츠 가져오기...`);
            
            // 간단한 evaluate로 테이블 행만 가져오기
            const tableRows = await this.page.evaluate(() => {
                const rows = [];
                const allRows = document.querySelectorAll('tr[onclick]');
                
                allRows.forEach(row => {
                    const onclick = row.getAttribute('onclick') || '';
                    const cells = row.querySelectorAll('td');
                    const cellTexts = Array.from(cells).map(cell => cell.textContent.trim());
                    
                    if (cellTexts.length >= 3) {
                        rows.push({
                            onclick: onclick,
                            cells: cellTexts
                        });
                    }
                });
                
                return rows;
            }).catch(err => {
                console.error('evaluate 실행 오류:', err.message);
                return [];
            });
            
            console.error(`발견된 행 개수: ${tableRows.length}`);
            
            // 행 데이터 파싱
            for (const row of tableRows) {
                let announcementId = '';
                
                // onclick에서 ID 추출
                const searchDetailMatch = row.onclick.match(/searchDetail\(['"]([^'"]+)['"]\)/);
                if (searchDetailMatch) {
                    announcementId = searchDetailMatch[1];
                }
                
                const jfViewMatch = row.onclick.match(/jf_view\(['"]([^'"]+)['"]\)/);
                if (jfViewMatch) {
                    const params = jfViewMatch[1];
                    const idMatch = params.match(/not_ancmt_mgt_no=(\d+)/);
                    if (idMatch) {
                        announcementId = idMatch[1];
                    }
                }
                
                // 제목과 날짜 추출 (기본 인덱스)
                const cells = row.cells;
                let title = cells[2] || cells[1] || '';
                let date = '';
                
                // 날짜 찾기
                for (const cell of cells) {
                    if (/\d{4}[-.\s]\d{2}[-.\s]\d{2}/.test(cell)) {
                        date = cell;
                        break;
                    }
                }
                
                if (announcementId && title) {
                    const detailUrl = this.constructDetailUrl(announcementId);
                    announcements.push({
                        id: announcementId,
                        title: title,
                        date: date || '',
                        url: detailUrl
                    });
                    
                    console.error(`  - ${announcementId}: ${title.substring(0, 50)}...`);
                }
            }
            
            console.error(`[Page ${pageNum}] 수집된 공고: ${announcements.length}개`);
            
        } catch (error) {
            console.error(`[Page ${pageNum}] 리스트 수집 중 오류:`, error.message);
        }
        
        return announcements;
    }
    
    buildServletUrl(pageIndex = 1) {
        // 서블릿 URL 직접 구성
        const params = new URLSearchParams({
            'jndinm': 'OfrNotAncmtEJB',
            'context': 'NTIS',
            'method': 'selectList',
            'methodnm': 'selectListOfrNotAncmt',
            'homepage_pbs_yn': 'Y',
            'subCheck': 'Y',
            'ofr_pageSize': '10',
            'not_ancmt_se_code': '01,02,03,04,05',
            'title': '고시공고',
            'cha_dep_code_nm': '',
            'initValue': 'Y',
            'countYn': 'Y',
            'list_gubun': 'A',
            'not_ancmt_sj': '',
            'not_ancmt_cn': '',
            'dept_nm': '',
            'pageIndex': pageIndex.toString(),
            'pageUnit': '10'
        });
        
        return `${this.actionUrl}?${params.toString()}`;
    }
    
    constructDetailUrl(announcementId) {
        // Eminwon 상세 페이지 URL 구성
        const params = new URLSearchParams({
            'jndinm': 'OfrNotAncmtEJB',
            'context': 'NTIS',
            'method': 'selectOfrNotAncmt',
            'methodnm': 'selectOfrNotAncmtRegst',
            'not_ancmt_mgt_no': announcementId,
            'homepage_pbs_yn': 'Y',
            'subCheck': 'Y',
            'ofr_pageSize': '10',
            'not_ancmt_se_code': '01,02,03,04,05',
            'title': '고시공고',
            'cha_dep_code_nm': '',
            'initValue': 'Y',
            'countYn': 'Y',
            'list_gubun': 'A',
            'not_ancmt_sj': '',
            'not_ancmt_cn': '',
            'dept_nm': '',
            'cgg_code': '',
            'not_ancmt_reg_no': '',
            'epcCheck': 'Y',
            'yyyy': '',
            'Key': 'B_Subject',
            'temp': ''
        });
        
        return `${this.actionUrl}?${params.toString()}`;
    }
    
    async collectAllLists() {
        const allAnnouncements = [];
        
        try {
            await this.init();
            
            for (let pageNum = 1; pageNum <= this.maxPages; pageNum++) {
                console.error(`\n📄 ${this.region} - 페이지 ${pageNum}/${this.maxPages} 수집 중...`);
                
                const pageAnnouncements = await this.collectListPage(pageNum);
                allAnnouncements.push(...pageAnnouncements);
                
                // 페이지 간 대기
                if (pageNum < this.maxPages) {
                    await this.page.waitForTimeout(1000);
                }
            }
            
            console.error(`\n✅ ${this.region} - 총 ${allAnnouncements.length}개 공고 수집 완료`);
            
        } catch (error) {
            console.error(`❌ 리스트 수집 실패:`, error);
        } finally {
            if (this.browser) {
                await this.browser.close();
            }
        }
        
        return allAnnouncements;
    }
    
    async run() {
        if (this.mode === 'list') {
            const announcements = await this.collectAllLists();
            
            // JSON으로 출력 (stdout으로 Python에 전달)
            console.log(JSON.stringify({
                status: 'success',
                region: this.region,
                count: announcements.length,
                data: announcements
            }, null, 2));
            
            return announcements;
        } else if (this.mode === 'detail') {
            // 상세 페이지 다운로드는 기존 eminwon_scraper.js 사용
            console.error('상세 페이지 다운로드는 eminwon_scraper.js를 사용하세요');
            process.exit(1);
        }
    }
}

// CLI 인터페이스
if (require.main === module) {
    const argv = yargs
        .option('region', {
            alias: 'r',
            describe: '수집할 지역 (예: 청주, 광주남)',
            type: 'string',
            demandOption: true
        })
        .option('mode', {
            alias: 'm',
            describe: '수집 모드 (list: 리스트만, detail: 상세)',
            type: 'string',
            default: 'list'
        })
        .option('pages', {
            alias: 'p',
            describe: '수집할 페이지 수',
            type: 'number',
            default: 3
        })
        .help()
        .argv;
    
    const collector = new EminwonListCollector({
        region: argv.region,
        mode: argv.mode,
        maxPages: argv.pages
    });
    
    collector.run().catch(error => {
        console.error('실행 실패:', error);
        process.exit(1);
    });
}

module.exports = EminwonListCollector;