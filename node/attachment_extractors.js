/**
 * 사이트별 첨부파일 추출 함수 모음
 * 각 함수는 document와 config를 받아서 attachments 배열을 반환
 */

const attachmentExtractors = {
    /**
     * anyang_complex: td ul li에서 아이콘 제거 후 추출
     */
    anyang_complex: (document, config) => {
        const attachments = [];
        const fileLinks = document.querySelectorAll(config.attachments.selector); // 'td ul li'

        fileLinks.forEach(link => {
            const downloadLink = link.querySelector('a:not(.p-attach__preview p-button)');
            if (!downloadLink) return;

            // 아이콘 span 제거하여 파일명 추출
            const clonedAnchor = downloadLink.cloneNode(true);
            const iconSpan = clonedAnchor.querySelector('.p-icon');
            if (iconSpan) {
                iconSpan.remove();
            }
            const fileName = clonedAnchor.textContent.trim();
            const downloadUrl = downloadLink.href;

            if (fileName && downloadUrl) {
                attachments.push({
                    name: fileName,
                    url: downloadUrl
                });
            }
        });

        return attachments;
    },

    /**
     * boeun: .p-attach li에서 파일명 정리 후 추출
     */
    boeun: (document, config) => {
        const attachments = [];
        const attachmentItems = document.querySelectorAll('.p-attach li');

        attachmentItems.forEach(item => {
            const downloadLinkElement = item.querySelector('a.p-attach__link');
            const fileNameElement = item.querySelector('.p-attach__link span:last-child');

            if (fileNameElement && downloadLinkElement) {
                // 파일 이름에서 이미지 태그와 alt 텍스트를 제외하고 텍스트만 가져오기
                const fileName = fileNameElement.textContent.trim();
                const href = downloadLinkElement.href;

                // 파일명에서 괄호 부분 제거 (예: .pdf (123KB) -> .pdf)
                const regex = /(\.[a-z0-9]+)\s*\([^)]*\)$/i;
                const cleanedFileName = fileName.replace(regex, '$1');

                // 중복 체크
                const isDuplicate = attachments.some(att => att.name === cleanedFileName);
                if (!isDuplicate) {
                    attachments.push({
                        url: href,
                        name: cleanedFileName
                    });
                }
            }
        });

        return attachments;
    },

    daegu: (document, config) => {
        const attachments = [];

        // fn_egov_downFile 함수를 사용하는 링크 찾기
        const fileLinks = document.querySelectorAll('a[href*="fn_egov_downFile"]');

        fileLinks.forEach(link => {
            const fileName = link.textContent.trim();
            const href = link.href;

            // fn_egov_downFile의 파라미터 추출
            const match = href.match(/fn_egov_downFile\s*\(\s*['"]?([^'"]+)['"]?\s*,\s*['"]?([^'"]+)['"]?\s*\)/);

            if (match && fileName) {
                // 파일명 정리 (바이트 정보 제거)
                const cleanName = fileName.replace(/\s*\[\d+\s*byte\]\s*$/, '');

                attachments.push({
                    name: cleanName,
                    atchFileId: match[1],
                    fileSn: match[2],
                    url: `/icms/cmm/fms/FileDown.do?atchFileId=${match[1]}&fileSn=${match[2]}`
                });
            }
        });

        return attachments

    },

    daejeon: (document, config) => {
        const attachments = [];

        // 파일 다운로드 링크 찾기
        const fileLinks = document.querySelectorAll('a[href*="FileDown"], a[href*="fileDown"], a[onclick*="download"]');

        fileLinks.forEach(link => {
            const fileName = link.textContent.trim();
            const cleanFileName = fileName.replace(/\(\d+\.?\d*KB\)/i, '').trim();

            const href = link.href;
            const onclick = link.getAttribute('onclick');

            if (fileName && (href || onclick)) {
                const regex = /fileDown\('([^']+)''\)/;
                // Regex to find "fileDown(" and capture the content inside the quotes
                const match = href.match(/fileDown\("([^"]*)"\)/);

                if (match) {
                    const filePath = match[1];
                    downloadUrl = `https://www.daejeon.go.kr/drh/drhGosiFileDownload.do?filePath=${filePath}`
                } else {
                    downloadUrl = href
                }

                attachments.push({
                    name: cleanFileName,
                    url: downloadUrl,
                    onclick: onclick
                });
            }
        });

        return attachments

    },
    dh: (document, confgi) => {
        const attachments = [];

        const fileLinks = document.querySelectorAll('li.p-attach__item');

        fileLinks.forEach(link => {
            const fileNameElement = link.querySelector('span.p-attach__text');
            const fileName = fileNameElement ? fileNameElement.textContent.trim() : null;

            // 다운로드 링크는 <a> 태그의 href 속성에서 가져옵니다.
            // "다운로드" 텍스트를 포함하는 <a> 태그를 찾아 href 속성을 추출합니다.
            const allLinksInItem = link.querySelectorAll('a');
            let downloadLink = null;
            allLinksInItem.forEach(link => {
                if (link.textContent.includes("다운로드")) {
                    downloadLink = link;
                }
            });
            const url = downloadLink ? downloadLink.href : null;

            if (fileName && url) {
                attachments.push({
                    name: fileName,
                    url,
                });
            }
        });

        return attachments;
    },
    gbgs: (document, config) => {
        // 첨부파일 링크 추출
        const attachments = [];

        const goDownloadLinks = document.querySelectorAll('a.clsFileDownload');

        console.log("goDownloadLinks", goDownloadLinks)
        goDownloadLinks.forEach(link => {
            // Get the full URL from the href attribute.
            const url = link.href;

            // Get the file name from the title attribute and remove " 다운로드".
            const fileName = link.textContent.trim();
            const onclick = link.getAttribute("onclick")
            const goDownloadMatch = onclick.match(/openDownloadFiles\(\s*([^'"]*)\s*\)/);

            console.log(fileName, onclick)
            console.log("goDownloadMatch", goDownloadMatch)
            if (goDownloadMatch) {
                const [, file_uid] = goDownloadMatch;
                // 실제 goDownload 함수와 동일한 URL 패턴 사용
                downloadUrl = `/programs/board/download.do?parm_file_uid=${file_uid}`;
            } else {
                downloadUrl = url
            }


            console.log("fileName", fileName, downloadUrl)
            if (fileName && url) {
                attachments.push({
                    name: fileName,
                    url: downloadUrl,
                    onclick
                });
            }
        });




        return attachments
    },

    gokseong: (document, config) => {
        const attachments = [];
        const selector = config.attachments.selector;
        const downloadFunction = config.attachments.downloadFunction || 'goDownLoad';
        const allLinks = document.querySelectorAll(selector);

        allLinks.forEach(link => {
            const href = link.getAttribute("href") || '';
            const linkText = link.textContent.trim();
            
            // href에 goDownLoad 함수가 있고, 링크 텍스트가 "다운로드"가 아닌 것만 처리
            if (href.includes(downloadFunction) && linkText !== "다운로드") {
                // 링크 텍스트 자체가 파일명
                const fileName = linkText;
                
                if (fileName && fileName.length > 0) {
                    attachments.push({
                        name: fileName,
                        url: href,
                        onclick: href  // href를 onclick으로도 저장 (호환성)
                    });
                }
            }
        });

        return attachments;
    },

    goryeong: (document, config) => {
        const attachments = [];


        const fileContainer = document.querySelector('td[colspan="3"]');
        const fileParagraphs = fileContainer.querySelectorAll('p');

        fileParagraphs.forEach(p => {
            const downloadLink = p.querySelector('a.subBtnSuq[href*="downFile.do"]');
            const fileNameLink = p.querySelector('a.bV_file');

            if (downloadLink && fileNameLink) {
                const fullText = fileNameLink.textContent.trim().split(' ')[0];
                const fileURL = downloadLink.href;

                const fileNameMatch = fullText.match(/^(.+?)\s+\[/);
                const fileName = fileNameMatch ? fileNameMatch[1].trim() : fullText;

                console.log(`File Name: ${fileName}`);
                console.log(`Download Link: ${fileURL}`);
                console.log('---');

                if (fileName && fileURL) {
                    attachments.push({
                        name: fileName,
                        url: fileURL
                    });
                }

            }
        });

        return attachments;
    },
    gn: (document, config) => {
        const attachments = [];

        const attachmentItems = document.querySelectorAll('.view_attach li');
        attachmentItems.forEach(item => {
            const fileNameElement = item.querySelector('.down_view span');
            const downloadLinkElement = item.querySelector('a.file_down');

            if (fileNameElement && downloadLinkElement) {
                // 파일 이름에서 이미지 태그와 alt 텍스트를 제외하고 텍스트만 가져오기
                const fileName = fileNameElement.textContent.trim();
                const href = downloadLinkElement.href;

                const regex = /(\.[a-z0-9]+)\s*\([^)]*\)$/i;

                const cleanedFileName = fileName.replace(regex, '$1');

                const isDuplicate = attachments.some(att =>
                    att.name === fileName
                );

                console.log("isDuplicate", isDuplicate)
                if (!isDuplicate) {
                    attachments.push({
                        url: href,
                        name: cleanedFileName,
                        // onclick: onclick
                    });
                }

            }
        });

        return attachments
    },
    gimje: (document, config) => {
        const attachments = [];

        const fileItems = document.querySelectorAll('.bbs_filedown dd');
        const results = [];

        fileItems.forEach(item => {
            const downloadLink = item.querySelector('a.sbtn_down');
            const fileNameElement = item.querySelector('span a');

            if (downloadLink && fileNameElement) {
                // Get the file name from the text content of the <span><a>.
                const fileName = fileNameElement.textContent.trim();
                const cleanFileName = fileName.replace(/\s+\(.*\)\s*$/, '');
                // Get the full URL from the download link's href attribute.
                const url = downloadLink.href;

                if (fileName && url) {
                    attachments.push({
                        name: cleanFileName,
                        url: url
                    });
                }
            }
        });

        return attachments
    },

    gb: (document, config) => {
        // 첨부파일 링크 추출
        const attachments = [];

        const fileList = document.querySelector('dl.attfile dd');
        const fileItems = fileList.querySelectorAll('a[href*="download.jsp"]');

        console.log("fileItems", fileItems)
        fileItems.forEach(item => {
            const fileName = item.textContent.trim();
            const downloadLink = item.href;

            attachments.push(
                { name: fileName, url: downloadLink }
            );

        });


        return attachments
    },
    gangjin: (document, config) => {
        // 첨부파일 링크 추출
        const attachments = [];

        const fileItems = document.querySelectorAll('div.file_body ul.file_list li');

        fileItems.forEach(item => {
            // 파일 이름을 포함하는 <span class="name"> 요소를 찾습니다.
            const fileNameElement = item.querySelector('span.name');
            // 다운로드 링크를 포함하는 <a class="md_btn_txt md_btn_ico ico_down"> 요소를 찾습니다.
            const downloadLink = item.querySelector('a.ico_down');

            if (fileNameElement && downloadLink) {
                // 파일 이름의 텍스트 콘텐츠를 가져와 공백을 정리합니다.
                const fileName = fileNameElement.textContent.trim();
                // 다운로드 링크의 href 속성을 가져옵니다.
                const url = downloadLink.href;

                attachments.push({
                    name: fileName,
                    url
                });
            }
        });

        return attachments
    },
    gangbuk: (document, confgi) => {
        const attachments = [];

        const fileLinks = document.querySelectorAll('li.p-attach__item');

        fileLinks.forEach(link => {
            const fileNameElement = link.querySelector('span.p-attach__text');
            const fileName = fileNameElement ? fileNameElement.textContent.trim() : null;

            // 다운로드 링크는 <a> 태그의 href 속성에서 가져옵니다.
            // "다운로드" 텍스트를 포함하는 <a> 태그를 찾아 href 속성을 추출합니다.
            const allLinksInItem = link.querySelectorAll('a');
            let downloadLink = null;
            allLinksInItem.forEach(link => {
                if (link.textContent.includes("다운로드")) {
                    downloadLink = link;
                }
            });
            const url = downloadLink ? downloadLink.href : null;

            if (fileName && url) {
                attachments.push({
                    name: fileName,
                    url,
                });
            }
        });

        return attachments;
    },
    ddc: (document, confgi) => {
        const attachments = [];
        const goDownloadLinks = document.querySelectorAll('.view_attach .down_view');

        goDownloadLinks.forEach(link => {
            // Get the full URL from the href attribute.
            const fileNameElement = link.querySelector('span');
            const fileName = fileNameElement.textContent.trim();

            // 다운로드 링크를 포함하는 <a> 태그를 찾고 href 속성을 추출합니다.
            const downloadLink = link.querySelector('a.file_down');
            const url = downloadLink ? downloadLink.href : null;

            if (fileName && url) {
                attachments.push({
                    name: fileName,
                    url: url,
                });
            }
        });
        return attachments;
    },
    cwg: (document, config) => {
        const attachments = [];

        const fileLinks = document.querySelectorAll('.p-attach li');
        const results = [];

        fileLinks.forEach(link => {
            // 파일 이름은 <a> 태그의 텍스트 콘텐츠에서 가져옵니다.
            // 이때, 불필요한 공백을 제거합니다.
            const fileNameSpan = link.querySelector('span:not(.p-icon)');
            const fileName = fileNameSpan ? fileNameSpan.textContent.trim() : null;
            // Find the download link and get its href attribute
            const downloadLink = link.querySelector('.p-attach__link');
            const downloadUrl = downloadLink ? downloadLink.href : null;

            if (fileName && downloadUrl) {
                attachments.push({
                    name: fileName,
                    url: downloadUrl
                });
            }
        });

        return attachments;
    },
    chungnam: (document, config) => {
        const attachments = [];
        const fileList = document.querySelectorAll('.view-file-list li');

        fileList.forEach(item => {
            const fileNameMatch = item.textContent.match(/^\s*([^<\n]+?\.(hwp|hwpx|png|jpg|jpeg|pdf|zip|xlsx|doc|docx|ppt|pptx))/i);
            let fileName = item.textContent.trim();

            if (fileNameMatch) {
                // The full file name (including the extension) is at index 1 of the match array.
                fileName = fileNameMatch[1].trim();
            }
            const downloadLink = item.querySelector("a.ico_file");
            const url = downloadLink.href

            attachments.push(
                { name: fileName, url: url }
            );

        });

        return attachments;
    },

    /**
     * 기본 JavaScript 함수 호출 방식 (goDownload 등)
     */
    javascript_function: (document, config) => {
        const attachments = [];
        const selector = config.attachments.selector;
        const downloadFunction = config.attachments.downloadFunction || 'goDownload';
        const allLinks = document.querySelectorAll(selector);

        allLinks.forEach(link => {
            const fileName = link.textContent.trim();
            const href = link.href || '';
            const onclick = link.getAttribute("onclick") || '';

            // downloadFunction이 포함된 링크만 처리
            if ((onclick && onclick.includes(downloadFunction)) || (href && href.includes(downloadFunction))) {
                // "다운로드", "바로보기" 등의 텍스트는 제외
                if (fileName && fileName !== "다운로드" && !fileName.includes('바로보기')) {
                    // onclick 또는 href에서 파라미터 추출
                    const source = onclick || href;
                    attachments.push({
                        name: fileName,
                        url: href,
                        onclick: source
                    });
                }
            }
        });

        // 중복 제거
        return Array.from(new Set(attachments.map(JSON.stringify))).map(JSON.parse);
    },

    /**
     * 기본 Direct URL 방식
     */
    direct_url: (document, config) => {
        const attachments = [];
        const selector = typeof config.attachments === 'string'
            ? config.attachments
            : config.attachments.selector;
        const attachEls = document.querySelectorAll(selector);

        attachEls.forEach(el => {
            const href = el.href;
            const name = el.textContent?.trim();
            const regex = /(\.[a-z0-9]+)\s*\([^)]*\)$/i;
            const cleanedFileName = name.replace(regex, '$1');

            if (href && !href.includes('javascript:')) {
                attachments.push({
                    name: cleanedFileName,
                    url: href
                });
            }
        });

        return attachments;
    }
};

// Node.js 환경에서 사용
if (typeof module !== 'undefined' && module.exports) {
    module.exports = attachmentExtractors;
}

// 브라우저 환경에서 사용 (page.evaluate 내부)
if (typeof window !== 'undefined') {
    window.attachmentExtractors = attachmentExtractors;
}