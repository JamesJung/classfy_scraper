#!/usr/bin/env python3
import re


def update_scraper_file(filepath):
    """Update scraper file to include attachment URL in content.md"""

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update saveAnnouncement function
    save_pattern = r"(async saveAnnouncement\(announcement, detailContent\) \{[\s\S]*?)(\s+// content\.md 생성\s+const contentMd = this\.generateMarkdownContent[\s\S]*?)(// 첨부파일 다운로드\s+if \(detailContent\.attachments[\s\S]*?await this\.downloadAttachments\(detailContent\.attachments, folderPath\);[\s\S]*?\})([\s\S]*?this\.counter\+\+;)"

    save_replacement = r'\1\n            // 첨부파일 다운로드 및 URL 정보 수집\n            let downloadUrlInfo = {};\n            if (detailContent.attachments && detailContent.attachments.length > 0) {\n                downloadUrlInfo = await this.downloadAttachments(detailContent.attachments, folderPath);\n                \n                // 첨부파일에 다운로드 정보 추가\n                detailContent.attachments.forEach(attachment => {\n                    const fileName = attachment.name;\n                    if (downloadUrlInfo[fileName]) {\n                        attachment.downloadInfo = downloadUrlInfo[fileName];\n                    }\n                });\n            }\n\n            // content.md 생성 (다운로드 URL 정보 포함)\n            const contentMd = this.generateMarkdownContent(announcement, detailContent);\n            await fs.writeFile(path.join(folderPath, "content.md"), contentMd, "utf8");\n\4'

    # 2. Update downloadAttachments function
    download_pattern = r"async downloadAttachments\(attachments, folderPath\) \{[\s\S]*?try \{([\s\S]*?)for \(let i = 0; i < attachments\.length; i\+\+\) \{\s+const attachment = attachments\[i\];\s+await this\.downloadSingleAttachment\(attachment, attachDir, i \+ 1\);([\s\S]*?)\}[\s\S]*?\} catch \(error\) \{[\s\S]*?\}\s+\}"

    download_replacement = r'async downloadAttachments(attachments, folderPath) {\n        const downloadUrlInfo = {};\n        try {\1for (let i = 0; i < attachments.length; i++) {\n                const attachment = attachments[i];\n                const result = await this.downloadSingleAttachment(attachment, attachDir, i + 1);\n                if (result) {\n                    Object.assign(downloadUrlInfo, result);\n                }\2}\n\n        } catch (error) {\n            console.error("첨부파일 다운로드 실패:", error);\n        }\n        return downloadUrlInfo;\n    }'

    # 3. Update downloadSingleAttachment function - add variables at start
    single_pattern = r"(async downloadSingleAttachment\(attachment, attachDir, index\) \{[\s\S]*?try \{[\s\S]*?)let downloadUrl = attachment\.url;\s+let fileName = attachment\.name \|\| `attachment_\$\{index\}`;([\s\S]*?// JavaScript 방식 처리\s+if \(attachment\.onclick\) \{)"

    single_replacement = r'\1let downloadUrl = attachment.url;\n            let fileName = attachment.name || `attachment_${index}`;\n            let actualDownloadUrl = null;\n            let downloadType = "direct";\2\n                downloadType = "onclick";'

    # 4. Add downloadType = 'goDownload' after goDownloadMatch
    godownload_pattern = r"(if \(goDownloadMatch\) \{[\s\S]*?const \[, originalName, serverName, serverPath\] = goDownloadMatch;)"
    godownload_replacement = r'\1\n                    downloadType = "goDownload";'

    # 5. Update invalid URL handling and add return statement
    invalid_pattern = r'if \(!downloadUrl \|\| !downloadUrl\.startsWith\("http"\)\) \{[\s\S]*?console\.log\(`유효하지 않은 다운로드 URL: \$\{downloadUrl\}`\);[\s\S]*?return;[\s\S]*?\}([\s\S]*?)console\.log\(`!!!!!!!!!!!!!!!!!다운로드 완료: \$\{fileName\}!!!!!!!!!!!!!!!!`\);[\s\S]*?\} catch \(error\) \{[\s\S]*?console\.error\(`첨부파일 다운로드 실패 \(\$\{attachment\.name\}\):`, error\);[\s\S]*?\}'

    invalid_replacement = r'if (!downloadUrl || !downloadUrl.startsWith("http")) {\n                console.log(`유효하지 않은 다운로드 URL: ${downloadUrl}`);\n                return {\n                    [fileName]: {\n                        originalUrl: attachment.url,\n                        originalOnclick: attachment.onclick,\n                        actualDownloadUrl: null,\n                        downloadType: downloadType,\n                        error: "Invalid URL"\n                    }\n                };\n            }\n            \n            actualDownloadUrl = downloadUrl;\1console.log(`!!!!!!!!!!!!!!!!!다운로드 완료: ${fileName}!!!!!!!!!!!!!!!!`);\n            \n            return {\n                [fileName]: {\n                    originalUrl: attachment.url,\n                    originalOnclick: attachment.onclick,\n                    actualDownloadUrl: actualDownloadUrl,\n                    downloadType: downloadType,\n                    fileName: fileName\n                }\n            };\n        } catch (error) {\n            console.error(`첨부파일 다운로드 실패 (${attachment.name}):`, error);\n            return {\n                [attachment.name || `attachment_${index}`]: {\n                    originalUrl: attachment.url,\n                    originalOnclick: attachment.onclick,\n                    actualDownloadUrl: null,\n                    downloadType: "error",\n                    error: error.message\n                }\n            };\n        }'

    # 6. Update generateMarkdownContent for attachments
    markdown_pattern = r'(if \(detailContent\.attachments && detailContent\.attachments\.length > 0\) \{[\s\S]*?lines\.push\("**첨부파일**:"\);[\s\S]*?lines\.push\(""\);[\s\S]*?)detailContent\.attachments\.forEach\(\(att, i\) => \{[\s\S]*?lines\.push\(`\$\{i \+ 1\}\. \$\{att\.name\}`\);[\s\S]*?\}\);'

    markdown_replacement = r'\1detailContent.attachments.forEach((att, i) => {\n                let attachInfo = ""\n                // 다운로드 URL 정보가 있는 경우 추가\n                if (att.downloadInfo && att.downloadInfo.actualDownloadUrl) {\n                    attachInfo = `${i + 1}. ${att.name}:${att.downloadInfo.actualDownloadUrl}`\n                } else {\n                    attachInfo = `${i + 1}. ${att.name}`;\n                }\n                lines.push(attachInfo);\n                lines.push("");\n            });'

    # Apply all replacements
    content = re.sub(save_pattern, save_replacement, content)
    content = re.sub(download_pattern, download_replacement, content)
    content = re.sub(single_pattern, single_replacement, content)
    content = re.sub(godownload_pattern, godownload_replacement, content)
    content = re.sub(invalid_pattern, invalid_replacement, content)
    content = re.sub(markdown_pattern, markdown_replacement, content)

    # Write back
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Updated: {filepath}")


# Update both files
files = [
    "/Users/jin/classfy_scraper/node/scraper/sb_scraper.js",
    "/Users/jin/classfy_scraper/node/scraper/ydp_scraper.js",
]

for file in files:
    try:
        update_scraper_file(file)
    except Exception as e:
        print(f"Error updating {file}: {e}")
