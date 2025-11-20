#!/usr/bin/env node

/**
 * 스크래퍼 자동 패치 스크립트
 *
 * 기능:
 * 1. 모든 *_scraper.js 파일에 failure_logger.js 모듈 추가
 * 2. catch 블록에 FailureLogger.logFailedAnnouncement() 호출 추가
 * 3. 백업 생성
 *
 * 사용법:
 *   node patch_scrapers.js --dry-run      # 실제 수정 없이 미리보기
 *   node patch_scrapers.js --file andong  # 특정 파일만 패치
 *   node patch_scrapers.js --all          # 전체 파일 패치
 */

const fs = require('fs-extra');
const path = require('path');

// 간단한 argv 파싱
const argv = {
    dryRun: process.argv.includes('--dry-run'),
    file: null,
    all: process.argv.includes('--all'),
    backup: !process.argv.includes('--no-backup')
};

// --file 옵션 파싱
const fileIndex = process.argv.indexOf('--file');
if (fileIndex > -1 && process.argv[fileIndex + 1]) {
    argv.file = process.argv[fileIndex + 1];
}

const SCRAPER_DIR = path.join(__dirname, 'node/scraper');
const BACKUP_DIR = path.join(__dirname, 'backup_scrapers');

class ScraperPatcher {
    constructor(options = {}) {
        this.dryRun = options.dryRun || false;
        this.backup = options.backup !== false;
        this.stats = {
            total: 0,
            patched: 0,
            skipped: 0,
            errors: 0
        };
    }

    /**
     * 파일이 이미 패치되었는지 확인
     */
    isAlreadyPatched(content) {
        return content.includes("require('./failure_logger')") ||
               content.includes('require("./failure_logger")') ||
               content.includes('FailureLogger');
    }

    /**
     * require 문 추가
     */
    addRequireStatement(content) {
        // const 선언이 있는 첫 번째 라인 찾기
        const lines = content.split('\n');
        let insertIndex = -1;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            // 주석이나 빈 줄 건너뛰기
            if (line.startsWith('//') || line.startsWith('/*') || line.startsWith('*') || !line) {
                continue;
            }

            // const, require 찾기
            if (line.startsWith('const ') && line.includes('require(')) {
                insertIndex = i + 1;
            }

            // class 정의가 나오면 그 전에 삽입
            if (line.startsWith('class ')) {
                if (insertIndex === -1) {
                    insertIndex = i;
                }
                break;
            }
        }

        // 삽입 위치를 찾았으면 추가
        if (insertIndex > -1) {
            lines.splice(insertIndex, 0, "const FailureLogger = require('./failure_logger');");
            return lines.join('\n');
        }

        return content;
    }

    /**
     * catch 블록에 FailureLogger 호출 추가
     */
    addFailureLogging(content) {
        const lines = content.split('\n');
        const newLines = [];
        let inCatchBlock = false;
        let catchIndent = '';

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const trimmed = line.trim();

            newLines.push(line);

            // catch 블록 시작 감지
            // 예: } catch (announcementError) {
            //     } catch (pageError) {
            //     catch (error) {
            if (trimmed.match(/catch\s*\((\w+)\)\s*\{/)) {
                const match = trimmed.match(/catch\s*\((\w+)\)\s*\{/);
                const errorVar = match[1];
                catchIndent = line.match(/^(\s*)/)[1] + '    '; // 들여쓰기

                // 다음 라인이 console.error인지 확인
                const nextLine = i + 1 < lines.length ? lines[i + 1].trim() : '';

                // announcement, page, detail 관련 catch만 로깅
                if (errorVar.includes('announcement') || errorVar.includes('Error') || errorVar === 'error') {
                    // FailureLogger 호출 코드 생성
                    const logCode = [
                        `${catchIndent}// 실패 공고 DB 기록`,
                        `${catchIndent}await FailureLogger.logFailedAnnouncement({`,
                        `${catchIndent}    site_code: this.siteCode,`,
                        `${catchIndent}    title: announcement?.title || 'Unknown',`,
                        `${catchIndent}    url: announcement?.link || announcement?.url,`,
                        `${catchIndent}    detail_url: announcement?.detailUrl,`,
                        `${catchIndent}    error_type: '${errorVar}',`,
                        `${catchIndent}    error_message: ${errorVar}.message`,
                        `${catchIndent}}).catch(logErr => {});`,
                        ``
                    ];

                    // console.error 다음에 추가
                    if (nextLine.startsWith('console.error')) {
                        // console.error 라인 다음에 추가
                        newLines.push(...logCode);
                        i++; // console.error 라인 건너뛰기
                        newLines.push(lines[i]);
                    } else {
                        // console.error가 없으면 바로 추가
                        newLines.push(...logCode);
                    }
                }
            }
        }

        return newLines.join('\n');
    }

    /**
     * 단일 파일 패치
     */
    async patchFile(filePath) {
        try {
            this.stats.total++;

            // 파일 읽기
            const content = await fs.readFile(filePath, 'utf-8');

            // 이미 패치되었는지 확인
            if (this.isAlreadyPatched(content)) {
                console.log(`  ⊙ 스킵 (이미 패치됨): ${path.basename(filePath)}`);
                this.stats.skipped++;
                return;
            }

            // 백업 생성
            if (this.backup && !this.dryRun) {
                const backupPath = path.join(BACKUP_DIR, path.basename(filePath));
                await fs.ensureDir(BACKUP_DIR);
                await fs.copy(filePath, backupPath);
            }

            // 패치 적용
            let patchedContent = content;

            // 1. require 문 추가
            patchedContent = this.addRequireStatement(patchedContent);

            // 2. catch 블록에 로깅 추가
            patchedContent = this.addFailureLogging(patchedContent);

            // 변경사항이 있는지 확인
            if (patchedContent === content) {
                console.log(`  ⊙ 스킵 (변경사항 없음): ${path.basename(filePath)}`);
                this.stats.skipped++;
                return;
            }

            if (this.dryRun) {
                console.log(`  ✓ 패치 예정: ${path.basename(filePath)}`);
                this.stats.patched++;
            } else {
                // 파일 저장
                await fs.writeFile(filePath, patchedContent, 'utf-8');
                console.log(`  ✓ 패치 완료: ${path.basename(filePath)}`);
                this.stats.patched++;
            }

        } catch (error) {
            console.error(`  ✗ 패치 실패: ${path.basename(filePath)} - ${error.message}`);
            this.stats.errors++;
        }
    }

    /**
     * 모든 스크래퍼 파일 패치
     */
    async patchAll(targetFile = null) {
        console.log('================================================================================');
        console.log('  스크래퍼 자동 패치 시작');
        console.log('================================================================================');
        console.log(`모드: ${this.dryRun ? 'DRY-RUN (미리보기)' : '실제 패치'}`);
        console.log(`백업: ${this.backup ? '생성' : '건너뛰기'}`);
        console.log('');

        // 스크래퍼 파일 목록
        const files = await fs.readdir(SCRAPER_DIR);
        const scraperFiles = files.filter(f => f.endsWith('_scraper.js'));

        // 특정 파일만 패치
        let filesToPatch = scraperFiles;
        if (targetFile) {
            filesToPatch = scraperFiles.filter(f => f.startsWith(targetFile));
            if (filesToPatch.length === 0) {
                console.error(`✗ 파일을 찾을 수 없음: ${targetFile}_scraper.js`);
                return;
            }
        }

        console.log(`대상 파일: ${filesToPatch.length}개\n`);

        // 각 파일 패치
        for (const file of filesToPatch) {
            const filePath = path.join(SCRAPER_DIR, file);
            await this.patchFile(filePath);
        }

        // 요약
        console.log('');
        console.log('================================================================================');
        console.log('  패치 완료');
        console.log('================================================================================');
        console.log(`전체: ${this.stats.total}개`);
        console.log(`패치: ${this.stats.patched}개`);
        console.log(`스킵: ${this.stats.skipped}개`);
        console.log(`에러: ${this.stats.errors}개`);
        if (this.backup && !this.dryRun && this.stats.patched > 0) {
            console.log(`백업 위치: ${BACKUP_DIR}`);
        }
        console.log('================================================================================');
    }
}

// 메인 실행
async function main() {
    const patcher = new ScraperPatcher({
        dryRun: argv.dryRun,
        backup: argv.backup
    });

    if (argv.file) {
        await patcher.patchAll(argv.file);
    } else if (argv.all) {
        await patcher.patchAll();
    } else {
        console.log('사용법:');
        console.log('  node patch_scrapers.js --dry-run      # 미리보기');
        console.log('  node patch_scrapers.js --file andong  # 특정 파일만');
        console.log('  node patch_scrapers.js --all          # 전체 파일');
        console.log('');
        console.log('옵션을 지정하세요. --help로 도움말 확인');
    }
}

main().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});
