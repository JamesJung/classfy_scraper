#!/usr/bin/env python3
"""
데이터베이스에 저장된 한글 텍스트를 NFC 형태로 정규화하는 스크립트

macOS에서 저장된 NFD 형태의 한글을 윈도우 호환 NFC 형태로 변환합니다.
"""

import sys
import unicodedata
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.logConfig import setup_logging
from src.models.announcementPrvDatabase import AnnouncementPrvDatabaseManager
from src.models.announcementDatabase import AnnouncementDatabaseManager

logger = setup_logging(__name__)


def normalize_korean_text(text: str) -> str:
    """한글 텍스트를 NFC(Composed) 형태로 정규화합니다."""
    if not text:
        return text
    return unicodedata.normalize('NFC', text)


def normalize_prv_table():
    """announcement_prv_processing 테이블의 한글 텍스트를 정규화합니다."""
    prv_db = AnnouncementPrvDatabaseManager()
    
    try:
        with prv_db.SessionLocal() as session:
            from sqlalchemy import text
            
            # 모든 레코드 조회
            result = session.execute(text("""
                SELECT id, folder_name, combined_content, attachment_filenames 
                FROM announcement_prv_processing 
                WHERE folder_name IS NOT NULL OR combined_content IS NOT NULL OR attachment_filenames IS NOT NULL
            """))
            
            records = result.fetchall()
            logger.info(f"PRV 테이블에서 {len(records)}개 레코드 발견")
            
            updated_count = 0
            
            for record in records:
                record_id = record[0]
                original_folder_name = record[1]
                original_combined_content = record[2]
                original_attachment_filenames = record[3]
                
                # 정규화 수행
                normalized_folder_name = normalize_korean_text(original_folder_name) if original_folder_name else None
                normalized_combined_content = normalize_korean_text(original_combined_content) if original_combined_content else None
                normalized_attachment_filenames = normalize_korean_text(original_attachment_filenames) if original_attachment_filenames else None
                
                # 변경사항이 있는지 확인
                needs_update = False
                if original_folder_name != normalized_folder_name:
                    needs_update = True
                    logger.debug(f"folder_name 변경 필요: {original_folder_name} -> {normalized_folder_name}")
                
                if original_combined_content != normalized_combined_content:
                    needs_update = True
                    logger.debug(f"combined_content 변경 필요 (ID: {record_id})")
                
                if original_attachment_filenames != normalized_attachment_filenames:
                    needs_update = True
                    logger.debug(f"attachment_filenames 변경 필요: {original_attachment_filenames} -> {normalized_attachment_filenames}")
                
                if needs_update:
                    # 업데이트 실행
                    session.execute(text("""
                        UPDATE announcement_prv_processing 
                        SET folder_name = :folder_name,
                            combined_content = :combined_content,
                            attachment_filenames = :attachment_filenames,
                            updated_at = NOW()
                        WHERE id = :record_id
                    """), {
                        'record_id': record_id,
                        'folder_name': normalized_folder_name,
                        'combined_content': normalized_combined_content,
                        'attachment_filenames': normalized_attachment_filenames
                    })
                    updated_count += 1
                    
                    if updated_count % 100 == 0:
                        logger.info(f"PRV 테이블 업데이트 진행: {updated_count}개")
            
            session.commit()
            logger.info(f"PRV 테이블 정규화 완료: {updated_count}개 레코드 업데이트")
            
    except Exception as e:
        logger.error(f"PRV 테이블 정규화 중 오류: {e}")
        raise


def normalize_announcement_table():
    """announcement_processing 테이블의 한글 텍스트를 정규화합니다."""
    announce_db = AnnouncementDatabaseManager()
    
    try:
        with announce_db.SessionLocal() as session:
            from sqlalchemy import text
            
            # 모든 레코드 조회
            result = session.execute(text("""
                SELECT id, folder_name, combined_content, attachment_filenames 
                FROM announcement_processing 
                WHERE folder_name IS NOT NULL OR combined_content IS NOT NULL OR attachment_filenames IS NOT NULL
            """))
            
            records = result.fetchall()
            logger.info(f"일반 테이블에서 {len(records)}개 레코드 발견")
            
            updated_count = 0
            
            for record in records:
                record_id = record[0]
                original_folder_name = record[1]
                original_combined_content = record[2]
                original_attachment_filenames = record[3]
                
                # 정규화 수행
                normalized_folder_name = normalize_korean_text(original_folder_name) if original_folder_name else None
                normalized_combined_content = normalize_korean_text(original_combined_content) if original_combined_content else None
                normalized_attachment_filenames = normalize_korean_text(original_attachment_filenames) if original_attachment_filenames else None
                
                # 변경사항이 있는지 확인
                needs_update = False
                if original_folder_name != normalized_folder_name:
                    needs_update = True
                    logger.debug(f"folder_name 변경 필요: {original_folder_name} -> {normalized_folder_name}")
                
                if original_combined_content != normalized_combined_content:
                    needs_update = True
                    logger.debug(f"combined_content 변경 필요 (ID: {record_id})")
                
                if original_attachment_filenames != normalized_attachment_filenames:
                    needs_update = True
                    logger.debug(f"attachment_filenames 변경 필요: {original_attachment_filenames} -> {normalized_attachment_filenames}")
                
                if needs_update:
                    # 업데이트 실행
                    session.execute(text("""
                        UPDATE announcement_processing 
                        SET folder_name = :folder_name,
                            combined_content = :combined_content,
                            attachment_filenames = :attachment_filenames,
                            updated_at = NOW()
                        WHERE id = :record_id
                    """), {
                        'record_id': record_id,
                        'folder_name': normalized_folder_name,
                        'combined_content': normalized_combined_content,
                        'attachment_filenames': normalized_attachment_filenames
                    })
                    updated_count += 1
                    
                    if updated_count % 100 == 0:
                        logger.info(f"일반 테이블 업데이트 진행: {updated_count}개")
            
            session.commit()
            logger.info(f"일반 테이블 정규화 완료: {updated_count}개 레코드 업데이트")
            
    except Exception as e:
        logger.error(f"일반 테이블 정규화 중 오류: {e}")
        raise


def main():
    """메인 함수"""
    logger.info("데이터베이스 한글 텍스트 정규화 시작")
    
    try:
        print("1. announcement_prv_processing 테이블 정규화 중...")
        normalize_prv_table()
        
        print("2. announcement_processing 테이블 정규화 중...")
        normalize_announcement_table()
        
        print("✅ 모든 테이블의 한글 텍스트 정규화 완료!")
        
    except Exception as e:
        logger.error(f"정규화 과정에서 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()