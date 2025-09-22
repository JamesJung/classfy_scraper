/**
 * 안양시 커스텀 핸들러
 * 안양시 사이트의 특수한 처리를 담당
 */

module.exports = {
    /**
     * 리스트 수집 전 초기화
     */
    beforeListCollection: async (page) => {
        // 안양시 특수 처리가 필요한 경우
        await page.waitForSelector('table.p-table', { timeout: 10000 }).catch(() => {});
    },

    /**
     * 리스트 페이지 네비게이션
     */
    navigateListPage: async (page, pageNum) => {
        try {
            // 안양시는 goPage 함수 사용
            const hasGoPage = await page.evaluate(() => {
                return typeof window.goPage === 'function';
            });

            if (hasGoPage) {
                await page.evaluate((pageNum) => {
                    window.goPage(pageNum);
                }, pageNum);
                
                await page.waitForLoadState('networkidle', { timeout: 10000 });
                await page.waitForTimeout(1000);
            } else {
                // 폴백: URL 파라미터 방식
                const url = new URL(page.url());
                url.searchParams.set('pageIndex', pageNum);
                await page.goto(url.toString(), { waitUntil: 'networkidle' });
            }
            
            return true;
        } catch (error) {
            console.error('[anyang] 페이지 네비게이션 실패:', error.message);
            return false;
        }
    },

    /**
     * 상세 페이지 URL 결정
     */
    determineDetailUrl: async (scraper) => {
        // onclick에서 goView 함수 추출
        if (scraper.onclick) {
            // goView('12345') 패턴
            const goViewMatch = scraper.onclick.match(/goView\s*\(\s*['"]([^'"]+)['"]/);
            if (goViewMatch) {
                const viewId = goViewMatch[1];
                // 안양시 상세 페이지 URL 구성
                return `${scraper.config.baseUrl}/main/emwsWebView.do?key=4101&idx=${viewId}`;
            }

            // location.href 패턴
            const hrefMatch = scraper.onclick.match(/location\.href\s*=\s*['"]([^'"]+)['"]/);
            if (hrefMatch) {
                const href = hrefMatch[1];
                if (href.startsWith('http')) {
                    return href;
                } else if (href.startsWith('/')) {
                    return new URL(href, scraper.config.baseUrl).toString();
                }
            }
        }

        // 기본 URL 사용
        if (scraper.announcementUrl && scraper.announcementUrl.startsWith('http')) {
            return scraper.announcementUrl;
        }

        return null;
    },

    /**
     * 상세 페이지 콘텐츠 추출 전 처리
     */
    beforeExtract: async (page) => {
        // 동적 콘텐츠 로딩 대기
        await page.waitForSelector('.board_view, .view_content, .content', { 
            timeout: 10000 
        }).catch(() => {});
        
        // 추가 스크립트 실행 대기
        await page.waitForTimeout(1000);
    },

    /**
     * 콘텐츠 추출
     */
    extractContent: async (page, config) => {
        return await page.evaluate(() => {
            // 안양시 특수 콘텐츠 선택자
            const selectors = [
                '.board_view .content',
                '.view_content',
                '#content',
                '.content_body',
                'div[class*="content"]'
            ];
            
            for (const selector of selectors) {
                const element = document.querySelector(selector);
                if (element) {
                    // 불필요한 요소 제거
                    const unnecessaryElements = element.querySelectorAll('.file_list, .btn_wrap, script, style');
                    unnecessaryElements.forEach(el => el.remove());
                    
                    const text = element.innerText || element.textContent || '';
                    if (text.trim()) {
                        return text.trim();
                    }
                }
            }
            
            // 폴백
            return document.body.innerText || '';
        });
    },

    /**
     * 첨부파일 추출
     */
    extractAttachments: async (page, config) => {
        return await page.evaluate(() => {
            const attachments = [];
            
            // 안양시 첨부파일 선택자
            const selectors = [
                '.file_list a',
                '.fileBox a',
                'a[onclick*="fileDown"]',
                'a[onclick*="download"]',
                'a[href*="/file/"]'
            ];
            
            const processedNames = new Set();
            
            for (const selector of selectors) {
                const links = document.querySelectorAll(selector);
                
                links.forEach(link => {
                    const name = link.textContent.trim();
                    
                    // 중복 체크
                    if (processedNames.has(name)) return;
                    
                    // 파일 확장자 체크
                    const hasFileExtension = /\.(pdf|doc|docx|xls|xlsx|ppt|pptx|hwp|hwpx|zip|jpg|jpeg|png|gif|txt)$/i.test(name);
                    
                    if (name && hasFileExtension) {
                        processedNames.add(name);
                        
                        attachments.push({
                            name: name,
                            url: link.href || '',
                            onclick: link.getAttribute('onclick') || ''
                        });
                    }
                });
            }
            
            return attachments;
        });
    },

    /**
     * 첨부파일 다운로드
     */
    downloadAttachment: async (page, attachment, attachDir) => {
        // 안양시 특수 다운로드 처리
        if (attachment.onclick && attachment.onclick.includes('fileDown')) {
            // fileDown 함수 실행
            await page.evaluate((onclick) => {
                eval(onclick);
            }, attachment.onclick);
            
            // 다운로드 대기
            await page.waitForTimeout(3000);
            
            return true;
        }
        
        // 기본 처리로 위임
        return false;
    }
};