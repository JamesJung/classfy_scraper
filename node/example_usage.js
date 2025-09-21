#!/usr/bin/env node

/**
 * Node.js 스크래핑 시스템 사용 예제
 * 
 * 다양한 사이트 구조에 맞는 설정 예제들을 제공합니다.
 */

const AnnouncementScraper = require('./scraper');

// 예제 1: 기본 테이블 구조 사이트
async function example1_basicTable() {
    console.log('=== 예제 1: 기본 테이블 구조 ===');
    
    const scraper = new AnnouncementScraper({
        targetYear: 2025,
        outputDir: 'example1_output',
        siteCode: 'acci',
        baseUrl: 'https://www.acci.or.kr/board/list',
        listSelector: 'tbody tr',
        titleSelector: 'td:nth-child(2) a',
        dateSelector: 'td:last-child'
    });
    
    await scraper.scrape();
}

// 예제 2: div 기반 구조 사이트
async function example2_divStructure() {
    console.log('=== 예제 2: div 기반 구조 ===');
    
    const scraper = new AnnouncementScraper({
        targetYear: 2025,
        outputDir: 'example2_output', 
        siteCode: 'modern_site',
        baseUrl: 'https://example.com/notices',
        listSelector: '.notice-item',
        titleSelector: '.title a',
        dateSelector: '.date'
    });
    
    await scraper.scrape();
}

// 예제 3: 복잡한 선택자가 필요한 사이트
async function example3_complexSelectors() {
    console.log('=== 예제 3: 복잡한 선택자 ===');
    
    const scraper = new AnnouncementScraper({
        targetYear: 2025,
        outputDir: 'example3_output',
        siteCode: 'complex_site',
        baseUrl: 'https://complex.com/board',
        listSelector: 'article.post-item',
        titleSelector: 'h3.post-title a',
        dateSelector: '.post-meta .date-published'
    });
    
    await scraper.scrape();
}

// 예제 4: 커스텀 URL 빌더가 필요한 경우
class CustomScraper extends AnnouncementScraper {
    buildListUrl(pageNum) {
        // 커스텀 페이징 로직
        return `${this.baseUrl}?page=${pageNum}&category=notice&sort=date`;
    }
    
    async buildDetailUrl(announcement) {
        const link = announcement.link;
        
        // 특별한 URL 패턴 처리
        if (link.includes('viewPost(')) {
            const match = link.match(/viewPost\((\d+)\)/);
            if (match) {
                return `${this.baseUrl}/view/${match[1]}`;
            }
        }
        
        return super.buildDetailUrl(announcement);
    }
}

async function example4_customLogic() {
    console.log('=== 예제 4: 커스텀 로직 ===');
    
    const scraper = new CustomScraper({
        targetYear: 2025,
        outputDir: 'example4_output',
        siteCode: 'custom_logic',
        baseUrl: 'https://custom.com/board'
    });
    
    await scraper.scrape();
}

// 예제 5: 실제 상공회의소 사이트들
async function example5_realSites() {
    console.log('=== 예제 5: 실제 상공회의소 사이트들 ===');
    
    // 안산상공회의소
    const acciScraper = new AnnouncementScraper({
        targetYear: 2025,
        outputDir: 'acci_output',
        siteCode: 'acci',
        baseUrl: 'https://www.acci.or.kr/board/list?boardId=notice',
        listSelector: '.board-list tbody tr',
        titleSelector: '.subject a',
        dateSelector: '.date'
    });
    
    // 중소기업기술혁신협회  
    const cbtScraper = new AnnouncementScraper({
        targetYear: 2025,
        outputDir: 'cbt_output', 
        siteCode: 'cbt',
        baseUrl: 'https://www.cbt.or.kr/board/notice',
        listSelector: 'table.board-table tbody tr',
        titleSelector: 'td.title a',
        dateSelector: 'td.date'
    });
    
    console.log('ACCI 스크래핑 시작...');
    await acciScraper.scrape();
    
    console.log('CBT 스크래핑 시작...');  
    await cbtScraper.scrape();
}

// 예제 6: 고급 첨부파일 처리
class AdvancedAttachmentScraper extends AnnouncementScraper {
    async downloadSingleAttachment(attachment, attachDir, index) {
        try {
            // 특별한 첨부파일 처리 로직
            if (attachment.onclick && attachment.onclick.includes('downloadFile(')) {
                // JavaScript 함수 호출 방식
                const match = attachment.onclick.match(/downloadFile\((\d+),\s*'([^']+)'\)/);
                if (match) {
                    const fileId = match[1];
                    const fileName = match[2];
                    
                    // POST 요청으로 다운로드
                    const downloadUrl = `${this.baseUrl}/download`;
                    const response = await this.page.evaluate(async (url, fileId) => {
                        const formData = new FormData();
                        formData.append('fileId', fileId);
                        
                        return await fetch(url, {
                            method: 'POST',
                            body: formData
                        });
                    }, downloadUrl, fileId);
                    
                    console.log(`고급 다운로드 완료: ${fileName}`);
                    return;
                }
            }
            
            // 기본 처리 방식으로 폴백
            await super.downloadSingleAttachment(attachment, attachDir, index);
            
        } catch (error) {
            console.error(`고급 첨부파일 처리 실패: ${error.message}`);
            await super.downloadSingleAttachment(attachment, attachDir, index);
        }
    }
}

async function example6_advancedAttachment() {
    console.log('=== 예제 6: 고급 첨부파일 처리 ===');
    
    const scraper = new AdvancedAttachmentScraper({
        targetYear: 2025,
        outputDir: 'advanced_attachment_output',
        siteCode: 'advanced_site',
        baseUrl: 'https://advanced.com/board'
    });
    
    await scraper.scrape();
}

// 예제 7: 병렬 처리 (여러 사이트 동시 스크래핑)
async function example7_parallelScraping() {
    console.log('=== 예제 7: 병렬 처리 ===');
    
    const sites = [
        {
            name: 'site1',
            config: {
                targetYear: 2025,
                outputDir: 'parallel_site1',
                siteCode: 'site1',
                baseUrl: 'https://site1.com/board'
            }
        },
        {
            name: 'site2', 
            config: {
                targetYear: 2025,
                outputDir: 'parallel_site2',
                siteCode: 'site2', 
                baseUrl: 'https://site2.com/notices'
            }
        }
    ];
    
    // 병렬 실행
    const promises = sites.map(site => {
        const scraper = new AnnouncementScraper(site.config);
        return scraper.scrape().catch(error => {
            console.error(`${site.name} 스크래핑 실패:`, error);
        });
    });
    
    await Promise.all(promises);
    console.log('모든 사이트 스크래핑 완료');
}

// 메인 함수 - 원하는 예제 주석 해제하여 실행
async function main() {
    console.log('Node.js 스크래핑 시스템 예제 실행\\n');
    
    try {
        // 실행할 예제 선택 (하나씩 주석 해제하여 테스트)
        
        // await example1_basicTable();
        // await example2_divStructure(); 
        // await example3_complexSelectors();
        // await example4_customLogic();
        // await example5_realSites();
        // await example6_advancedAttachment();
        // await example7_parallelScraping();
        
        console.log('\\n예제 실행 완료! 위의 주석을 해제하여 원하는 예제를 실행하세요.');
        
    } catch (error) {
        console.error('예제 실행 중 오류:', error);
    }
}

// CLI에서 직접 실행시에만 main 함수 호출
if (require.main === module) {
    main();
}

module.exports = {
    example1_basicTable,
    example2_divStructure,
    example3_complexSelectors,
    example4_customLogic,
    example5_realSites,
    example6_advancedAttachment,
    example7_parallelScraping,
    CustomScraper,
    AdvancedAttachmentScraper
};