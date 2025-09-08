#!/usr/bin/env python3
"""
제목 기반 지원사업 재처리 테스트 스크립트
"""

import sys
import json
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.logConfig import setup_logging
from src.models.announcementPrvDatabase import AnnouncementPrvDatabaseManager

logger = setup_logging(__name__)


def create_test_records():
    """테스트용 레코드를 생성합니다."""
    try:
        db_manager = AnnouncementPrvDatabaseManager()
        
        with db_manager.SessionLocal() as session:
            from sqlalchemy import text
            
            # 테스트용 레코드 생성
            test_records = [
                {
                    'folder_name': '테스트_지역_1_2025년 중소기업 창업 지원사업 공고',
                    'content_md': '''# 2025년 중소기업 창업 지원사업 공고

## 사업개요
- 사업기간: 2025.1.1 ~ 2025.12.31
- 지원대상: 창업 3년 이내 중소기업
- 지원내용: 사업비의 70% 지원 (최대 5천만원)

## 신청방법
- 접수기간: 2025.1.15 ~ 2025.2.15
- 제출처: 중소벤처기업부

## 문의처
- 담당자: 홍길동 (02-1234-5678)
''',
                    'site_code': 'TEST001'
                },
                {
                    'folder_name': '테스트_지역_2_2025년 농업인 교육 프로그램 안내',
                    'content_md': '''# 2025년 농업인 교육 프로그램 안내

## 교육개요
- 교육기간: 2025.3.1 ~ 2025.11.30
- 교육대상: 농업에 관심있는 일반인
- 교육내용: 스마트팜, 친환경농업 등

## 신청방법
- 접수: 상시접수
- 문의: 농업기술센터

교육비는 무료이며, 수료증을 발급합니다.
''',
                    'site_code': 'TEST002'
                }
            ]
            
            # 기존 테스트 레코드 삭제
            session.execute(text("DELETE FROM announcement_prv_processing WHERE folder_name LIKE '테스트_%'"))
            
            # 새 테스트 레코드 삽입
            for i, record in enumerate(test_records, 1):
                sql = text("""
                    INSERT INTO announcement_prv_processing (
                        folder_name, content_md, site_code, processing_status,
                        is_support_program, support_program_reason, created_at, updated_at
                    ) VALUES (
                        :folder_name, :content_md, :site_code, '성공',
                        1, '제목에 지원이라는 단어 들어감', NOW(), NOW()
                    )
                """)
                
                session.execute(sql, record)
                print(f"테스트 레코드 {i} 생성됨: {record['folder_name']}")
            
            session.commit()
            print(f"✅ {len(test_records)}개 테스트 레코드 생성 완료")
            
        return True
        
    except Exception as e:
        logger.error(f"테스트 레코드 생성 실패: {e}")
        print(f"❌ 테스트 레코드 생성 실패: {e}")
        return False


def run_test():
    """테스트를 실행합니다."""
    print("🧪 제목 기반 지원사업 재처리 테스트 시작")
    
    # 1. 테스트 레코드 생성
    print("\n📋 1단계: 테스트 레코드 생성")
    if not create_test_records():
        return
    
    # 2. 재처리 실행
    print("\n🔄 2단계: 재처리 실행")
    from title_support_reprocessor import TitleSupportReprocessor
    
    try:
        processor = TitleSupportReprocessor()
        
        # 테스트 레코드만 조회하여 처리
        db_manager = AnnouncementPrvDatabaseManager()
        with db_manager.SessionLocal() as session:
            from sqlalchemy import text
            
            result = session.execute(text("""
                SELECT id, folder_name, content_md, combined_content, attachment_filenames
                FROM announcement_prv_processing 
                WHERE folder_name LIKE '테스트_%'
                  AND is_support_program = 1 
                  AND support_program_reason = '제목에 지원이라는 단어 들어감'
                ORDER BY id
            """))
            
            records = result.fetchall()
            
            if not records:
                print("❌ 테스트할 레코드가 없습니다.")
                return
            
            print(f"📋 {len(records)}개 테스트 레코드 발견")
            
            from title_support_reprocessor import ReprocessingRecord
            
            success_count = 0
            for i, record_data in enumerate(records, 1):
                test_record = ReprocessingRecord(
                    id=record_data[0],
                    folder_name=record_data[1] or "",
                    content_md=record_data[2] or "",
                    combined_content=record_data[3] or "",
                    attachment_filenames=record_data[4] or ""
                )
                
                print(f"\n[{i}/{len(records)}] 테스트 레코드 처리: {test_record.folder_name}")
                
                if processor.reprocess_single_record(test_record):
                    success_count += 1
                    print("  ✅ 성공")
                else:
                    print("  ❌ 실패")
            
            print(f"\n🎉 테스트 완료: 성공 {success_count}/{len(records)}")
        
        # 3. 결과 확인
        print("\n📊 3단계: 결과 확인")
        with db_manager.SessionLocal() as session:
            result = session.execute(text("""
                SELECT folder_name, is_support_program, support_program_reason, 
                       extracted_target, extracted_amount, processing_status
                FROM announcement_prv_processing 
                WHERE folder_name LIKE '테스트_%'
                ORDER BY id
            """))
            
            results = result.fetchall()
            
            for i, result_data in enumerate(results, 1):
                print(f"\n레코드 {i}:")
                print(f"  폴더명: {result_data[0]}")
                print(f"  지원사업: {'예' if result_data[1] == 1 else '아니오'}")
                print(f"  판단근거: {result_data[2] or 'N/A'}")
                print(f"  지원대상: {result_data[3] or 'N/A'}")
                print(f"  지원금액: {result_data[4] or 'N/A'}")
                print(f"  처리상태: {result_data[5]}")
        
    except Exception as e:
        logger.error(f"테스트 실행 중 오류: {e}")
        print(f"❌ 테스트 실행 중 오류: {e}")


def cleanup_test_records():
    """테스트 레코드를 정리합니다."""
    try:
        db_manager = AnnouncementPrvDatabaseManager()
        
        with db_manager.SessionLocal() as session:
            from sqlalchemy import text
            
            # 테스트 레코드 삭제
            result = session.execute(text("DELETE FROM announcement_prv_processing WHERE folder_name LIKE '테스트_%'"))
            deleted_count = result.rowcount
            session.commit()
            
            print(f"🗑️ {deleted_count}개 테스트 레코드 삭제됨")
            
    except Exception as e:
        logger.error(f"테스트 레코드 정리 실패: {e}")
        print(f"❌ 테스트 레코드 정리 실패: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='제목 기반 지원사업 재처리 테스트')
    parser.add_argument('--cleanup', action='store_true', help='테스트 레코드만 삭제')
    
    args = parser.parse_args()
    
    if args.cleanup:
        cleanup_test_records()
    else:
        run_test()