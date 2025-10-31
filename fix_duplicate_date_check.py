#!/usr/bin/env python3
"""
모든 스크래퍼의 중복 체크 로직에 날짜 확인 추가
changwon_scraper.js와 동일한 로직을 다른 모든 스크래퍼에 적용
"""

import os
import re
import glob

def fix_scraper_duplicate_check(filepath):
    """스크래퍼 파일의 중복 체크 로직 수정"""
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 이미 수정된 파일인지 확인
    if '중복 게시물이지만 날짜가' in content:
        print(f"  ✓ 이미 수정됨: {os.path.basename(filepath)}")
        return False
    
    # 패턴 1: processedTitles.has 체크하는 부분 찾기
    pattern1 = r'(if\s*\(\s*this\.processedTitles\.has\s*\([^)]+\)\s*(?:\|\|[^{]+)?\)\s*\{[^}]*console\.log\s*\([^)]*중복[^)]*\);?\s*return\s+false;\s*\})'
    
    # 패턴 2: 메모리 기반 체크 포함
    pattern2 = r'(// 메모리 기반 체크\s*\n\s*if\s*\(\s*this\.processedTitles\.has\s*\([^)]+\)\s*(?:\|\|[^{]+)?\)\s*\{[^}]*console\.log\s*\([^)]*중복[^)]*\);?\s*return\s+false;\s*\})'
    
    modified = False
    
    # 패턴 2 먼저 시도 (더 구체적)
    matches = list(re.finditer(pattern2, content))
    if not matches:
        # 패턴 1 시도
        matches = list(re.finditer(pattern1, content))
    
    if matches:
        # 마지막 매치부터 역순으로 처리 (인덱스 보존)
        for match in reversed(matches):
            old_code = match.group(1)
            
            # return false; 앞에 날짜 체크 코드 추가
            new_code = old_code.replace(
                'return false;',
                '''// 중복 게시물이어도 날짜 체크는 수행 (targetDate 이전인지 확인)
                // 많은 중복이 연속으로 나타날 경우 종료 조건 판단을 위함
                if (this.targetDate && listDate) {
                    const targetMoment = moment(this.targetDate, 'YYYYMMDD');
                    if (listDate.isBefore(targetMoment)) {
                        console.log(`중복 게시물이지만 날짜가 ${listDate.format('YYYY-MM-DD')}로 대상 날짜 이전입니다. 종료 신호.`);
                        return true; // 스크래핑 중단
                    }
                }
                return false;'''
            )
            
            content = content[:match.start()] + new_code + content[match.end():]
            modified = True
    
    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✅ 수정 완료: {os.path.basename(filepath)}")
        return True
    else:
        print(f"  ⚠️ 패턴 못 찾음: {os.path.basename(filepath)}")
        return False

def main():
    """모든 스크래퍼 파일 처리"""
    
    # 현재 경로에서 node/scraper 디렉토리 찾기
    scraper_dir = os.path.join(os.path.dirname(__file__), 'node', 'scraper')
    
    scraper_files = glob.glob(os.path.join(scraper_dir, '*_scraper.js'))
    
    # config.js 제외
    scraper_files = [f for f in scraper_files if not f.endswith('config.js')]
    
    print(f"\n🔧 {len(scraper_files)}개 스크래퍼 파일 처리 시작\n")
    
    modified_count = 0
    skipped_count = 0
    failed_count = 0
    
    for filepath in sorted(scraper_files):
        try:
            if fix_scraper_duplicate_check(filepath):
                modified_count += 1
            elif '중복 게시물이지만 날짜가' in open(filepath, 'r', encoding='utf-8').read():
                skipped_count += 1
            else:
                failed_count += 1
        except Exception as e:
            print(f"  ❌ 오류: {os.path.basename(filepath)} - {e}")
            failed_count += 1
    
    print(f"\n📊 처리 결과:")
    print(f"  ✅ 수정됨: {modified_count}개")
    print(f"  ✓ 이미 수정됨: {skipped_count}개")
    print(f"  ⚠️ 처리 실패: {failed_count}개")
    print(f"  📁 전체: {len(scraper_files)}개")

if __name__ == "__main__":
    main()