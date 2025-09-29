#!/usr/bin/env node

/**
 * Fix content.md files for andong to replace javascript: URLs with actual download URLs
 * 
 * This script scans andong content.md files and replaces javascript:goDownload(...) URLs
 * with actual download URLs for the attachments.
 */

const fs = require('fs-extra');
const path = require('path');

const SCRAPED_DATA_DIR = path.join(__dirname, '..', 'scraped_data', 'andong');

function extractGoDownloadParams(jsUrl) {
    // Extract parameters from javascript:goDownload('file.pdf', 'sys123', '/path')
    const regex = /goDownload\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)/;
    const match = jsUrl.match(regex);
    
    if (!match) {
        return null;
    }
    
    const [, userFileNm, sysFileNm, filePath] = match;
    return { userFileNm, sysFileNm, filePath };
}

function generateActualUrl(userFileNm, sysFileNm, filePath, domain = 'andong.go.kr') {
    // Generate actual download URL
    const downloadEndpoint = `https://eminwon.${domain}/emwp/jsp/ofr/FileDownNew.jsp`;
    
    // Decode if already encoded, to avoid double encoding
    let decodedUserFileNm = userFileNm;
    let decodedSysFileNm = sysFileNm;
    let decodedFilePath = filePath;
    
    try {
        // Try to decode (if already encoded)
        decodedUserFileNm = decodeURIComponent(userFileNm);
        decodedSysFileNm = decodeURIComponent(sysFileNm);
        decodedFilePath = decodeURIComponent(filePath);
    } catch (e) {
        // If decode fails, use as-is
    }
    
    return `${downloadEndpoint}?user_file_nm=${encodeURIComponent(decodedUserFileNm)}&sys_file_nm=${encodeURIComponent(decodedSysFileNm)}&file_path=${encodeURIComponent(decodedFilePath)}`;
}

function fixContentMd(contentMdPath) {
    const content = fs.readFileSync(contentMdPath, 'utf-8');
    const lines = content.split('\n');
    
    let modified = false;
    const fixedLines = lines.map(line => {
        // Match attachment lines like: "1. filename.pdf:javascript:goDownload(...)"
        const attachmentRegex = /^(\d+\.\s+)([^:]+):javascript:(.+)$/;
        const match = line.match(attachmentRegex);
        
        if (match) {
            const [, prefix, fileName, jsCode] = match;
            const params = extractGoDownloadParams(jsCode);
            
            if (params) {
                const actualUrl = generateActualUrl(params.userFileNm, params.sysFileNm, params.filePath);
                modified = true;
                return `${prefix}${fileName}: ${actualUrl}`;
            }
        }
        
        return line;
    });
    
    if (modified) {
        fs.writeFileSync(contentMdPath, fixedLines.join('\n'), 'utf-8');
        return true;
    }
    
    return false;
}

async function scanAndFix() {
    console.log('🔍 Scanning andong directories...\n');
    
    if (!await fs.pathExists(SCRAPED_DATA_DIR)) {
        console.error(`❌ Directory not found: ${SCRAPED_DATA_DIR}`);
        process.exit(1);
    }
    
    const dirs = await fs.readdir(SCRAPED_DATA_DIR);
    let fixedCount = 0;
    let totalCount = 0;
    
    for (const dir of dirs) {
        const contentMdPath = path.join(SCRAPED_DATA_DIR, dir, 'content.md');
        
        if (await fs.pathExists(contentMdPath)) {
            totalCount++;
            try {
                const fixed = fixContentMd(contentMdPath);
                if (fixed) {
                    fixedCount++;
                    console.log(`✅ Fixed: ${dir}`);
                }
            } catch (error) {
                console.error(`❌ Error processing ${dir}:`, error.message);
            }
        }
    }
    
    console.log('\n' + '='.repeat(60));
    console.log(`📊 Summary:`);
    console.log(`   Total content.md files: ${totalCount}`);
    console.log(`   Fixed files: ${fixedCount}`);
    console.log(`   Unchanged files: ${totalCount - fixedCount}`);
    console.log('='.repeat(60));
}

// Run
scanAndFix().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});