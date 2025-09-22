/**
 * 원주시 커스텀 핸들러
 * 원주시 사이트의 특수한 처리를 담당
 */

module.exports = {
    /**
     * 리스트 수집 전 초기화
     */
    beforeListCollection: async (page) => {
        // 원주시 특수 처리
        await page.waitForSelector('table.p-table, table.board_list', { 
            timeout: 10000 
        }).catch(() => {});
    },

    /**
     * 상세 페이지 URL 결정
     */
    determineDetailUrl: async (scraper) => {
        // 원주시는 data-action 속성 우선 사용
        if (scraper.dataAction) {
            const fullUrl = new URL(scraper.dataAction, scraper.config.baseUrl).toString();
            return fullUrl;
        }

        // onclick에서 req.post(this) 패턴 처리
        if (scraper.onclick && scraper.onclick.includes('req.post(this)')) {
            // data-action이 있어야 함
            if (scraper.dataAction) {
                return new URL(scraper.dataAction, scraper.config.baseUrl).toString();
            }
            
            // 폴백: 기본 상세 페이지 URL 구성
            const idMatch = scraper.announcementUrl.match(/nttNo=(\d+)/);
            if (idMatch) {
                return `${scraper.config.baseUrl}/www/selectBbsNttView.do?bbsNo=140&nttNo=${idMatch[1]}&key=216`;
            }
        }

        // URL에서 직접 사용
        if (scraper.announcementUrl) {
            if (scraper.announcementUrl.startsWith('http')) {
                return scraper.announcementUrl;
            } else if (scraper.announcementUrl.startsWith('/')) {
                return new URL(scraper.announcementUrl, scraper.config.baseUrl).toString();
            }
        }

        return null;
    },

    /**
     * 리스트 추출 (원주시 특수 처리)
     */
    extractAnnouncements: async (page, config) => {
        return await page.evaluate((config) => {
            const announcements = [];
            
            // 원주시 테이블 선택자
            const rows = document.querySelectorAll('table.p-table tbody tr, table.board_list tbody tr');
            
            rows.forEach((row, index) => {
                // 헤더 행 스킵
                if (row.querySelector('th') || row.classList.contains('notice')) {
                    return;
                }
                
                // 제목 링크 찾기 (원주시 특수 선택자)
                const titleLink = row.querySelector('td.p-subject a, td.al_left a, td:nth-child(2) a');
                if (!titleLink) return;
                
                const title = titleLink.textContent.trim();
                if (!title) return;
                
                // 원주시는 data-action 속성을 자주 사용
                const href = titleLink.href || '';
                const onclick = titleLink.getAttribute('onclick') || '';
                const dataAction = titleLink.getAttribute('data-action') || '';
                
                // 날짜 추출
                let date = '';
                const dateCell = row.querySelector('td:nth-child(5), td:nth-child(4)');
                if (dateCell) {
                    date = dateCell.textContent.trim();
                }
                
                // ID 추출
                let id = '';
                
                // data-action에서 nttNo 추출
                if (dataAction) {
                    const match = dataAction.match(/nttNo=(\d+)/);
                    if (match) {
                        id = match[1];
                    }
                }
                
                // URL에서 ID 추출
                if (!id && href) {
                    const patterns = [
                        /nttNo=(\d+)/,
                        /boardSeq=(\d+)/,
                        /idx=(\d+)/,
                        /seq=(\d+)/
                    ];
                    
                    for (const pattern of patterns) {
                        const match = href.match(pattern);
                        if (match) {
                            id = match[1];
                            break;
                        }
                    }
                }
                
                // onclick에서 ID 추출
                if (!id && onclick) {
                    const match = onclick.match(/['"](\d+)['"]/);
                    if (match) {
                        id = match[1];
                    }
                }
                
                // 고유 ID 생성
                if (!id) {
                    id = `${Date.now()}_${index}`;
                }
                
                announcements.push({
                    id: id,
                    title: title,
                    url: href,
                    onclick: onclick,
                    dataAction: dataAction,  // 원주시 특수 속성
                    date: date,
                    index: index
                });
            });
            
            return announcements;
        }, config);
    },

    /**
     * 상세 페이지 콘텐츠 추출 전 처리
     */
    beforeExtract: async (page) => {
        // 원주시 콘텐츠 로딩 대기
        await page.waitForSelector('.board_view, .view_content, #content', { 
            timeout: 10000 
        }).catch(() => {});
        
        // 동적 콘텐츠 로딩 대기
        await page.waitForTimeout(1500);
    },

    /**
     * 콘텐츠 추출
     */
    extractContent: async (page, config) => {
        return await page.evaluate(() => {
            // 원주시 콘텐츠 선택자
            const selectors = [
                '.board_view .content',
                '.view_content',
                '#boardContents',
                '#content',
                '.content_view',
                'div.contents'
            ];
            
            for (const selector of selectors) {
                const element = document.querySelector(selector);
                if (element) {
                    // 불필요한 요소 제거
                    const unnecessaryElements = element.querySelectorAll(
                        '.file_list, .file_box, .btn_wrap, .button_wrap, script, style'
                    );
                    unnecessaryElements.forEach(el => el.remove());
                    
                    const text = element.innerText || element.textContent || '';
                    if (text.trim()) {
                        return text.trim();
                    }
                }
            }
            
            // 폴백: body에서 추출
            const body = document.body.innerText || document.body.textContent || '';
            return body.trim();
        });
    },

    /**
     * 첨부파일 추출
     */
    extractAttachments: async (page, config) => {
        return await page.evaluate(() => {
            const attachments = [];
            
            // 원주시 첨부파일 선택자
            const selectors = [
                '.file_list a',
                '.file_box a',
                '.attach_file a',
                'ul.file_list li a',
                'a[onclick*="fn_egov_downFile"]',
                'a[onclick*="fileDown"]',
                'a[href*="/cmm/fms/"]'
            ];
            
            const processedNames = new Set();
            
            for (const selector of selectors) {
                const links = document.querySelectorAll(selector);
                
                links.forEach(link => {
                    const name = link.textContent.trim();
                    
                    // 중복 체크
                    if (processedNames.has(name)) return;
                    
                    // "다운로드", "보기" 같은 텍스트 제외
                    if (name === '다운로드' || name === '보기' || name === '미리보기') return;
                    
                    // 파일 확장자 체크
                    const hasFileExtension = /\.(pdf|doc|docx|xls|xlsx|ppt|pptx|hwp|hwpx|zip|jpg|jpeg|png|gif|txt|csv)$/i.test(name);
                    
                    if (name && hasFileExtension) {
                        processedNames.add(name);
                        
                        const url = link.href || '';
                        const onclick = link.getAttribute('onclick') || '';
                        
                        attachments.push({
                            name: name,
                            url: url,
                            onclick: onclick
                        });
                    }
                });
            }
            
            return attachments;
        });
    },

    /**
     * 첨부파일 다운로드 (원주시 특수 처리)
     */
    downloadAttachment: async (page, attachment, attachDir) => {
        // fn_egov_downFile 함수 처리
        if (attachment.onclick && attachment.onclick.includes('fn_egov_downFile')) {
            await page.evaluate((onclick) => {
                eval(onclick);
            }, attachment.onclick);
            
            await page.waitForTimeout(3000);
            return true;
        }
        
        // 기본 처리로 위임
        return false;
    }
};