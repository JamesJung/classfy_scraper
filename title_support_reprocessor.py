#!/usr/bin/env python3
"""
제목 기반으로 지원사업 판정된 공고들을 재분석하는 프로세서

1. announcement_prv_processing에서 is_support_program=1, support_program_reason='제목에 지원이라는 단어 들어감' 레코드 조회
2. content_md로 1차 Ollama 분석
3. IS_SUPPORT_PROGRAM=0이면 다음으로 진행  
4. IS_SUPPORT_PROGRAM=1이지만 지원내용/지원대상 부족시 첨부파일 처리 후 2차 분석
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.logConfig import setup_logging
from src.models.announcementPrvDatabase import AnnouncementPrvDatabaseManager
from src.utils.ollamaClient import AnnouncementPrvAnalyzer
from src.utils.attachmentProcessor import AttachmentProcessor

logger = setup_logging(__name__)


@dataclass
class ReprocessingRecord:
    """재처리할 레코드 정보"""
    id: int
    folder_name: str
    content_md: str
    combined_content: str
    attachment_filenames: str


class TitleSupportReprocessor:
    """제목 기반 지원사업 재분석 프로세서"""
    
    def __init__(self):
        """초기화"""
        self.db_manager = AnnouncementPrvDatabaseManager()
        self.announcement_analyzer = AnnouncementPrvAnalyzer()
        self.attachment_processor = AttachmentProcessor()
        
        logger.info("TitleSupportReprocessor 초기화 완료")

    def get_title_support_records(self, limit: Optional[int] = None) -> List[ReprocessingRecord]:
        """제목 기반 지원사업 레코드들을 조회합니다."""
        try:
            with self.db_manager.SessionLocal() as session:
                from sqlalchemy import text
                
                sql = """
                    SELECT id, folder_name, content_md, combined_content, attachment_filenames
                    FROM announcement_prv_processing 
                    WHERE is_support_program = 1 
                      AND support_program_reason = '제목에 지원이라는 단어 들어감'
                    ORDER BY id
                """
                
                if limit:
                    sql += f" LIMIT {limit}"
                
                result = session.execute(text(sql))
                records = result.fetchall()
                
                reprocessing_records = []
                for record in records:
                    reprocessing_records.append(ReprocessingRecord(
                        id=record[0],
                        folder_name=record[1] or "",
                        content_md=record[2] or "",
                        combined_content=record[3] or "",
                        attachment_filenames=record[4] or ""
                    ))
                
                logger.info(f"제목 기반 지원사업 레코드 {len(reprocessing_records)}개 조회됨")
                return reprocessing_records
                
        except Exception as e:
            logger.error(f"제목 기반 지원사업 레코드 조회 실패: {e}")
            return []

    def analyze_with_ollama(self, content: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """Ollama를 사용하여 내용을 분석합니다."""
        try:
            if not content.strip():
                logger.warning("분석할 내용이 없음")
                return None, ""
            
            logger.debug(f"Ollama 분석 시작: {len(content)} 문자")
            response, prompt = self.announcement_analyzer.analyze_announcement(content)
            
            if response:
                logger.info(f"Ollama 분석 성공")
                logger.debug(f"응답: {response}")
                return response, prompt
            else:
                logger.warning("Ollama 분석 실패 - 응답 없음")
                return None, prompt
                
        except Exception as e:
            logger.error(f"Ollama 분석 중 오류: {e}")
            return None, ""

    def process_attachments_from_folder(self, folder_name: str, force: bool = False) -> Tuple[str, List[str]]:
        """폴더명을 기반으로 첨부파일을 처리합니다."""
        try:
            # 폴더명에서 경로 추출 (예: "강원특별자치도_홍천군_6_2025년..." -> "prv1/강원특별자치도/홍천군/6_2025년...")
            parts = folder_name.split('_')
            if len(parts) < 3:
                logger.warning(f"폴더명 형식이 올바르지 않음: {folder_name}")
                return "", []
            
            # prv1 기본 경로 구성
            base_path = Path(f"prv1/{parts[0]}/{parts[1]}")
            folder_suffix = '_'.join(parts[2:])
            
            # 해당 폴더 찾기
            if not base_path.exists():
                logger.warning(f"기본 경로가 존재하지 않음: {base_path}")
                return "", []
            
            target_folder = None
            for item in base_path.iterdir():
                if item.is_dir() and item.name.startswith(folder_suffix):
                    target_folder = item
                    break
            
            if not target_folder:
                logger.warning(f"대상 폴더를 찾을 수 없음: {base_path}/{folder_suffix}")
                return "", []
            
            attachments_dir = target_folder / "attachments"
            if not attachments_dir.exists():
                logger.info(f"첨부파일 디렉토리가 없음: {attachments_dir}")
                return "", []
            
            # 첨부파일 처리
            logger.info(f"첨부파일 처리 시작: {attachments_dir}")
            combined_content, attachment_filenames = self.attachment_processor.process_attachments_separately(
                attachments_dir, force=force
            )
            
            logger.info(f"첨부파일 처리 완료: {len(combined_content)} 문자, {len(attachment_filenames)}개 파일")
            return combined_content, attachment_filenames
            
        except Exception as e:
            logger.error(f"첨부파일 처리 실패 ({folder_name}): {e}")
            return "", []

    def has_valid_target_info(self, response: Optional[Dict[str, Any]]) -> bool:
        """지원대상 정보가 유효한지 확인합니다."""
        if not response:
            return False
            
        target = response.get("EXTRACTED_TARGET", "")
        return target and target not in ["정보 없음", "해당없음", "", "N/A"]

    def has_valid_content_info(self, response: Optional[Dict[str, Any]]) -> bool:
        """지원내용 정보가 유효한지 확인합니다."""
        if not response:
            return False
            
        amount = response.get("EXTRACTED_AMOUNT", "")
        return amount and amount not in ["정보 없음", "해당없음", "", "N/A"]

    def is_support_program(self, response: Optional[Dict[str, Any]]) -> bool:
        """지원사업인지 확인합니다."""
        if not response:
            return False
        return response.get("IS_SUPPORT_PROGRAM", False) == True

    def update_processing_result(self, record_id: int, ollama_response: Dict[str, Any], 
                               ollama_prompt: str, combined_content: str = "", 
                               attachment_filenames: List[str] = None, 
                               first_response: Dict[str, Any] = None) -> bool:
        """처리 결과를 데이터베이스에 업데이트합니다."""
        try:
            with self.db_manager.SessionLocal() as session:
                from sqlalchemy import text
                
                # Ollama 응답에서 데이터 추출
                extracted_data = {}
                if ollama_response:
                    extracted_data = {
                        'is_support_program': 1 if ollama_response.get('IS_SUPPORT_PROGRAM') == True else 0,
                        'support_program_reason': ollama_response.get('SUPPORT_PROGRAM_REASON', ''),
                        'extracted_target': ollama_response.get('EXTRACTED_TARGET', ''),
                        'extracted_target_type': ollama_response.get('EXTRACTED_TARGET_TYPE', ''),
                        'extracted_amount': ollama_response.get('EXTRACTED_AMOUNT', ''),
                        'extracted_title': ollama_response.get('EXTRACTED_TITLE', ''),
                        'extracted_announcement_date': ollama_response.get('EXTRACTED_ANNOUNCEMENT_DATE', ''),
                        'extracted_period': ollama_response.get('EXTRACTED_APPLICATION_PERIOD', ''),
                        'extracted_content': ollama_response.get('EXTRACTED_CONTENT', ''),
                        'extracted_schedule': ollama_response.get('EXTRACTED_SCHEDULE', ''),
                        'extracted_gov24_url': ollama_response.get('EXTRACTED_GOV24_URL', ''),
                        'extracted_origin_url': ollama_response.get('EXTRACTED_ORIGIN_URL', '')
                    }
                
                # SQL 업데이트
                sql = text("""
                    UPDATE announcement_prv_processing 
                    SET ollama_response = :ollama_response,
                        ollama_prompt = :ollama_prompt,
                        ollama_first_response = :ollama_first_response,
                        combined_content = :combined_content,
                        attachment_filenames = :attachment_filenames,
                        processing_status = '성공',
                        is_support_program = :is_support_program,
                        support_program_reason = :support_program_reason,
                        extracted_target = :extracted_target,
                        extracted_target_type = :extracted_target_type,
                        extracted_amount = :extracted_amount,
                        extracted_title = :extracted_title,
                        extracted_announcement_date = :extracted_announcement_date,
                        extracted_period = :extracted_period,
                        extracted_content = :extracted_content,
                        extracted_schedule = :extracted_schedule,
                        extracted_gov24_url = :extracted_gov24_url,
                        extracted_origin_url = :extracted_origin_url,
                        updated_at = NOW()
                    WHERE id = :record_id
                """)
                
                params = {
                    'record_id': record_id,
                    'ollama_response': json.dumps(ollama_response, ensure_ascii=False) if ollama_response else None,
                    'ollama_prompt': ollama_prompt,
                    'ollama_first_response': json.dumps(first_response, ensure_ascii=False) if first_response else None,
                    'combined_content': combined_content,
                    'attachment_filenames': json.dumps(attachment_filenames, ensure_ascii=False) if attachment_filenames else "",
                    **extracted_data
                }
                
                session.execute(sql, params)
                session.commit()
                
                logger.info(f"처리 결과 업데이트 완료: ID {record_id}")
                return True
                
        except Exception as e:
            logger.error(f"처리 결과 업데이트 실패: {e}")
            print(f"  ❌ 데이터베이스 업데이트 실패: {e}")
            import traceback
            print(f"  상세 오류: {traceback.format_exc()}")
            return False

    def reprocess_single_record(self, record: ReprocessingRecord) -> bool:
        """단일 레코드를 재처리합니다."""
        try:
            print(f"\n📋 레코드 재처리 시작: {record.folder_name[:80]}...")
            logger.info(f"레코드 재처리 시작: ID {record.id}, {record.folder_name}")
            
            if not record.content_md.strip():
                logger.warning(f"content_md가 없음: ID {record.id}")
                return False
            
            # 1차 Ollama 분석 (content_md)
            print("  📋 1차 Ollama 분석 중 (content_md)...")
            first_response, first_prompt = self.analyze_with_ollama(record.content_md)
            
            if not first_response:
                logger.warning(f"1차 Ollama 분석 실패: ID {record.id}")
                return False
            
            # IS_SUPPORT_PROGRAM 확인
            if not self.is_support_program(first_response):
                print("  ❌ 지원사업이 아님 - 완료")
                logger.info(f"지원사업이 아님: ID {record.id}")
                return self.update_processing_result(record.id, first_response, first_prompt)
            
            print("  ✅ 지원사업 확인됨")
            
            # 지원내용/지원대상 정보 확인
            has_target = self.has_valid_target_info(first_response)
            has_content = self.has_valid_content_info(first_response)
            
            if has_target and has_content:
                print("  ✅ 1차 분석 완료 - 필요한 정보 모두 추출됨")
                logger.info(f"1차 분석 완료: ID {record.id}")
                return self.update_processing_result(record.id, first_response, first_prompt)
            
            # 2차 분석 필요 - 첨부파일 처리
            print(f"  📂 첨부파일 처리 필요 (지원대상: {'✓' if has_target else '✗'}, 지원내용: {'✓' if has_content else '✗'})")
            
            # 기존 combined_content가 없으면 새로 처리
            combined_content = record.combined_content
            attachment_filenames = []
            
            if record.attachment_filenames:
                try:
                    attachment_filenames = json.loads(record.attachment_filenames)
                except:
                    attachment_filenames = []
            
            if not combined_content.strip():
                print("  📂 첨부파일 변환 중...")
                combined_content, attachment_filenames = self.process_attachments_from_folder(record.folder_name)
            else:
                print("  📂 기존 첨부파일 내용 사용")
            
            if not combined_content.strip():
                print("  ⚠️ 첨부파일 내용 없음 - 1차 결과로 완료")
                logger.info(f"첨부파일 내용 없음: ID {record.id}")
                return self.update_processing_result(record.id, first_response, first_prompt, 
                                                  combined_content, attachment_filenames, first_response)
            
            # 2차 Ollama 분석 (첨부파일만)
            print("  📋 2차 Ollama 분석 중 (첨부파일만)...")
            second_response, second_prompt = self.analyze_with_ollama(combined_content)
            
            if not second_response:
                print("  ⚠️ 2차 분석 실패 - 1차 결과로 완료")
                logger.warning(f"2차 Ollama 분석 실패: ID {record.id}")
                return self.update_processing_result(record.id, first_response, first_prompt,
                                                  combined_content, attachment_filenames, first_response)
            
            print("  ✅ 2차 분석 완료")
            logger.info(f"2차 분석 완료: ID {record.id}")
            return self.update_processing_result(record.id, second_response, second_prompt,
                                              combined_content, attachment_filenames, first_response)
            
        except Exception as e:
            logger.error(f"레코드 재처리 중 오류 (ID: {record.id}): {e}")
            return False

    def run_reprocessing(self, limit: Optional[int] = None, start_id: Optional[int] = None):
        """제목 기반 지원사업 재처리를 실행합니다."""
        try:
            print("🔄 제목 기반 지원사업 재처리 시작")
            logger.info("제목 기반 지원사업 재처리 시작")
            
            # 재처리할 레코드 조회
            records = self.get_title_support_records(limit)
            
            if not records:
                print("📋 재처리할 레코드가 없습니다.")
                return
            
            # start_id 필터링
            if start_id:
                records = [r for r in records if r.id >= start_id]
                logger.info(f"start_id {start_id} 이상 레코드만 처리: {len(records)}개")
            
            print(f"📋 총 {len(records)}개 레코드 재처리 예정")
            
            success_count = 0
            failure_count = 0
            
            for i, record in enumerate(records, 1):
                print(f"\n[{i}/{len(records)}] 처리 중...")
                
                if self.reprocess_single_record(record):
                    success_count += 1
                    print(f"  ✅ 성공")
                else:
                    failure_count += 1
                    print(f"  ❌ 실패")
                
                # 진행상황 출력
                if i % 10 == 0:
                    print(f"\n📊 진행상황: {i}/{len(records)} (성공: {success_count}, 실패: {failure_count})")
            
            print(f"\n🎉 재처리 완료!")
            print(f"📊 최종 결과: 성공 {success_count}개, 실패 {failure_count}개")
            logger.info(f"재처리 완료: 성공 {success_count}개, 실패 {failure_count}개")
            
        except Exception as e:
            logger.error(f"재처리 실행 중 오류: {e}")
            print(f"❌ 재처리 실행 중 오류: {e}")


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='제목 기반 지원사업 재처리')
    parser.add_argument('--limit', type=int, help='처리할 레코드 수 제한')
    parser.add_argument('--start-id', type=int, help='시작할 레코드 ID')
    parser.add_argument('--test', action='store_true', help='테스트 모드 (limit=5)')
    
    args = parser.parse_args()
    
    # 테스트 모드
    if args.test:
        args.limit = 5
        print("🧪 테스트 모드: 5개 레코드만 처리")
    
    processor = TitleSupportReprocessor()
    processor.run_reprocessing(limit=args.limit, start_id=args.start_id)


if __name__ == "__main__":
    main()