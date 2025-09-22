#!/bin/bash

# Apply changes to ydp_scraper.js file
# This script applies the same changes as sb_scraper.js to ydp_scraper.js

# Change 1: Update saveAnnouncement function
sed -i '' '/async saveAnnouncement/,/this\.counter++/c\
    async saveAnnouncement(announcement, detailContent) {\
        try {\
            // 폴더명 생성\
            const sanitizedTitle = sanitize(announcement.title).substring(0, 100);\
            const folderName = `${String(this.counter).padStart(3, "0")}_${sanitizedTitle}`;\
            const folderPath = path.join(this.outputDir, folderName);\
\
            // 폴더 중복 검사 (force 옵션이 없는 경우)\
            if (!this.force && await fs.pathExists(folderPath)) {\
                console.log(`폴더가 이미 존재하여 스킵: ${folderName}`);\
                return;\
            }\
\
            await fs.ensureDir(folderPath);\
\
            // 첨부파일 다운로드 및 URL 정보 수집\
            let downloadUrlInfo = {};\
            if (detailContent.attachments && detailContent.attachments.length > 0) {\
                downloadUrlInfo = await this.downloadAttachments(detailContent.attachments, folderPath);\
                \
                // 첨부파일에 다운로드 정보 추가\
                detailContent.attachments.forEach(attachment => {\
                    const fileName = attachment.name;\
                    if (downloadUrlInfo[fileName]) {\
                        attachment.downloadInfo = downloadUrlInfo[fileName];\
                    }\
                });\
            }\
\
            // content.md 생성 (다운로드 URL 정보 포함)\
            const contentMd = this.generateMarkdownContent(announcement, detailContent);\
            await fs.writeFile(path.join(folderPath, "content.md"), contentMd, "utf8");\
\
            this.counter++;' ydp_scraper.js