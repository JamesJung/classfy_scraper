#!/usr/bin/env python3

import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.models.announcementDatabase import AnnouncementDatabaseManager

def simple_reprocess_test(record_id: int):
    """간단한 재처리 테스트"""
    try:
        print(f"=== 레코드 ID {record_id} 재처리 테스트 ===")
        
        # 데이터베이스 연결
        db_manager = AnnouncementDatabaseManager()
        
        # 레코드 조회
        with db_manager.SessionLocal() as session:
            from sqlalchemy import text
            result = session.execute(text("""
                SELECT id, folder_name, content_md, combined_content,
                       extracted_content, extracted_target
                FROM announcement_processing
                WHERE id = :record_id
            """), {'record_id': record_id})
            
            record = result.fetchone()
            if not record:
                print(f"❌ 레코드 ID {record_id}를 찾을 수 없습니다.")
                return
            
            print(f"✅ 레코드 조회 성공:")
            print(f"  - ID: {record[0]}")
            print(f"  - 폴더명: {record[1]}")
            print(f"  - content_md 길이: {len(record[2] or '')}")
            print(f"  - combined_content 길이: {len(record[3] or '')}")
            print(f"  - 기존 지원내용: {record[4] or '없음'}")
            print(f"  - 기존 지원대상: {record[5] or '없음'}")
            
            # 재처리 필요성 확인
            extracted_content = record[4] or ''
            extracted_target = record[5] or ''
            
            needs_reprocess = (
                not extracted_content.strip() or 
                not extracted_target.strip() or
                len(extracted_content.strip()) < 10 or
                len(extracted_target.strip()) < 10 or
                any(word in extracted_content.lower() for word in ['없음', '정보없음', '미상']) or
                any(word in extracted_target.lower() for word in ['없음', '정보없음', '미상'])
            )
            
            if needs_reprocess:
                print("✅ 재처리가 필요합니다.")
                
                # content_md로 분석 시도
                content_md = record[2] or ''
                if content_md.strip():
                    print(f"  - content_md 사용 가능 (길이: {len(content_md)})")
                
                # combined_content로 분석 시도
                combined_content = record[3] or ''
                if combined_content.strip():
                    print(f"  - combined_content 사용 가능 (길이: {len(combined_content)})")
                    
            else:
                print("ℹ️  재처리가 필요하지 않습니다.")
            
            # 업데이트 테스트 (실제로는 하지 않음)
            print("✅ 테스트 완료")
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용법: python simple_test.py <record_id>")
        sys.exit(1)
    
    try:
        record_id = int(sys.argv[1])
        simple_reprocess_test(record_id)
    except ValueError:
        print("❌ 올바른 숫자를 입력해주세요.")
        sys.exit(1)