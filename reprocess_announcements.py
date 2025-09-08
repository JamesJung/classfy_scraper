#!/usr/bin/env python3
"""
공고 재처리 스크립트

특정 ID의 공고들을 다시 Ollama로 분석하여 지원내용과 지원대상을 재추출합니다.

사용법:
    python reprocess_announcements.py PRV 1,2,3,4,5
    python reprocess_announcements.py SCRAP 10,11,12,13

파라미터:
    table_type: PRV 또는 SCRAP
    ids: 재처리할 레코드 ID들 (콤마로 구분)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import time

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.config import ConfigManager
from src.config.logConfig import setup_logging
from src.utils.ollamaClient import AnnouncementPrvAnalyzer, AnnouncementAnalyzer
from src.models.announcementPrvDatabase import AnnouncementPrvDatabaseManager
from src.models.announcementDatabase import AnnouncementDatabaseManager

logger = setup_logging(__name__)
config = ConfigManager().get_config()


class AnnouncementReprocessor:
    """공고 재처리 클래스"""
    
    def __init__(self):
        print("DB Manager 초기화 중...")
        self.prv_db_manager = AnnouncementPrvDatabaseManager()
        self.scrap_db_manager = AnnouncementDatabaseManager()
        print("DB Manager 초기화 완료")
        
        print("Ollama Analyzer 초기화 중...")
        self.prv_analyzer = AnnouncementPrvAnalyzer()
        print("PRV Analyzer 초기화 완료")
        self.scrap_analyzer = AnnouncementAnalyzer()
        print("SCRAP Analyzer 초기화 완료")
        
        # 데이터베이스 연결 확인은 실제 사용 시에 수행
    
    def _check_database_connections(self):
        """데이터베이스 연결 상태를 확인합니다."""
        try:
            logger.info("PRV 데이터베이스 연결 확인 중...")
            prv_ok = self.prv_db_manager.test_connection()
            logger.info(f"PRV 데이터베이스 연결: {'성공' if prv_ok else '실패'}")
            
            logger.info("SCRAP 데이터베이스 연결 확인 중...")
            scrap_ok = self.scrap_db_manager.test_connection()  
            logger.info(f"SCRAP 데이터베이스 연결: {'성공' if scrap_ok else '실패'}")
            
            if not prv_ok:
                logger.error("PRV 데이터베이스 연결 실패")
                raise Exception("PRV 데이터베이스 연결 실패")
            
            if not scrap_ok:
                logger.error("SCRAP 데이터베이스 연결 실패")
                raise Exception("SCRAP 데이터베이스 연결 실패")
                
            logger.info("데이터베이스 연결 확인 완료")
            
        except Exception as e:
            logger.error(f"데이터베이스 연결 확인 중 오류: {e}")
            raise
    
    def fetch_records(self, table_type: str, ids: List[int]) -> List[Dict[str, Any]]:
        """
        지정된 ID의 레코드들을 가져옵니다.
        
        Args:
            table_type: 'PRV' 또는 'SCRAP'
            ids: 가져올 레코드 ID 목록
            
        Returns:
            레코드 정보 딕셔너리 목록
        """
        records = []
        
        try:
            if table_type.upper() == 'PRV':
                table_name = 'announcement_prv_processing'
                db_manager = self.prv_db_manager
            elif table_type.upper() == 'SCRAP':
                table_name = 'announcement_processing'
                db_manager = self.scrap_db_manager
            else:
                raise ValueError(f"지원하지 않는 테이블 타입: {table_type}")
            
            # SQL 쿼리로 레코드 조회
            ids_str = ','.join(map(str, ids))
            query = f"""
                SELECT id, folder_name, content_md, combined_content,
                       extracted_content, extracted_target,
                       processing_status, error_message
                FROM {table_name}
                WHERE id IN ({ids_str})
            """
            
            with db_manager.SessionLocal() as session:
                from sqlalchemy import text
                result = session.execute(text(query))
                
                for row in result:
                    records.append({
                        'id': row[0],
                        'folder_name': row[1],
                        'content_md': row[2],
                        'combined_content': row[3],
                        'extracted_content': row[4],
                        'extracted_target': row[5],
                        'processing_status': row[6] if len(row) > 6 else None,
                        'error_message': row[7] if len(row) > 7 else None
                    })
                    
            logger.info(f"{table_type} 테이블에서 {len(records)}개 레코드 조회 완료")
            return records
            
        except Exception as e:
            logger.error(f"레코드 조회 중 오류: {e}")
            raise
    
    def _needs_reprocessing(self, record: Dict[str, Any]) -> bool:
        """
        재처리가 필요한지 확인합니다.
        지원내용(extracted_content)과 지원대상(extracted_target)이 비어있거나 불완전한 경우 재처리가 필요합니다.
        
        Args:
            record: 레코드 정보
            
        Returns:
            재처리 필요 여부
        """
        extracted_content = record.get('extracted_content', '') or ''
        extracted_target = record.get('extracted_target', '') or ''
        
        # 지원내용이나 지원대상이 비어있는 경우
        if not extracted_content.strip() or not extracted_target.strip():
            return True
        
        # '없음', '정보없음', '미상' 등의 불완전한 답변인 경우
        incomplete_answers = [
            '없음', '정보없음', '미상', '확인불가', '불명', 
            '해당없음', '없습니다', '확인되지 않음', '언급되지 않음'
        ]
        
        content_incomplete = any(answer in extracted_content.lower() for answer in incomplete_answers)
        target_incomplete = any(answer in extracted_target.lower() for answer in incomplete_answers)
        
        if content_incomplete or target_incomplete:
            return True
        
        # 너무 짧은 답변인 경우 (10자 미만)
        if len(extracted_content.strip()) < 10 or len(extracted_target.strip()) < 10:
            return True
        
        return False
    
    def _analyze_with_ollama(self, content: str, analyzer, stage: str = "1차") -> Optional[Dict[str, Any]]:
        """
        Ollama를 사용하여 내용을 분석합니다.
        
        Args:
            content: 분석할 내용
            analyzer: 사용할 분석기 (PRV 또는 SCRAP)
            stage: 분석 단계 ("1차" 또는 "2차")
            
        Returns:
            분석 결과 딕셔너리
        """
        try:
            logger.info(f"{stage} Ollama 분석 시작 (내용 길이: {len(content)} 문자)")
            
            # 분석기 타입에 따라 다른 메서드 호출
            if hasattr(analyzer, 'analyze_announcement'):
                # analyze_announcement 메서드는 튜플을 반환: (data, prompt)
                raw_result = analyzer.analyze_announcement(content)
                
                if isinstance(raw_result, tuple) and len(raw_result) == 2:
                    extracted_data, used_prompt = raw_result
                    # 성공적인 결과로 포장
                    result = {
                        'success': True,
                        'extracted_data': extracted_data,
                        'ollama_response': str(raw_result),  # 전체 응답을 문자열로 저장
                        'used_prompt': used_prompt
                    }
                else:
                    # 예상치 못한 형식
                    result = {
                        'success': False,
                        'error': f'예상치 못한 응답 형식: {type(raw_result)}'
                    }
            else:
                logger.error(f"분석기에 analyze_announcement 메서드가 없음")
                return None
            
            if result and result.get('success'):
                logger.info(f"{stage} Ollama 분석 성공")
                return result
            else:
                logger.warning(f"{stage} Ollama 분석 실패: {result.get('error', '알 수 없는 오류') if result else '결과 없음'}")
                return None
                
        except Exception as e:
            logger.error(f"{stage} Ollama 분석 중 오류: {e}")
            return None
    
    def _update_record(self, table_type: str, record_id: int, analysis_result: Dict[str, Any]) -> bool:
        """
        분석 결과로 레코드를 업데이트합니다.
        
        Args:
            table_type: 'PRV' 또는 'SCRAP'
            record_id: 업데이트할 레코드 ID
            analysis_result: Ollama 분석 결과
            
        Returns:
            업데이트 성공 여부
        """
        try:
            if table_type.upper() == 'PRV':
                table_name = 'announcement_prv_processing'
                db_manager = self.prv_db_manager
            else:
                table_name = 'announcement_processing'
                db_manager = self.scrap_db_manager
            
            # 분석 결과에서 필요한 필드 추출
            extracted_data = analysis_result.get('extracted_data', {})
            
            # 대소문자 변환을 위한 매핑
            field_mapping = {
                'extracted_content': ['EXTRACTED_CONTENT', 'extracted_content'],
                'extracted_target': ['EXTRACTED_TARGET', 'extracted_target'],
                'extracted_title': ['EXTRACTED_TITLE', 'extracted_title'],
                'extracted_amount': ['EXTRACTED_AMOUNT', 'extracted_amount'],
                'extracted_period': ['EXTRACTED_PERIOD', 'extracted_period']
            }
            
            def get_field_value(data, field_names):
                """여러 가능한 필드명에서 값을 찾아 반환"""
                for field_name in field_names:
                    if field_name in data and data[field_name]:
                        return data[field_name]
                return ''
            
            update_fields = {
                'extracted_content': get_field_value(extracted_data, field_mapping['extracted_content']),
                'extracted_target': get_field_value(extracted_data, field_mapping['extracted_target']),
                'extracted_title': get_field_value(extracted_data, field_mapping['extracted_title']),
                'extracted_amount': get_field_value(extracted_data, field_mapping['extracted_amount']),
                'extracted_period': get_field_value(extracted_data, field_mapping['extracted_period']),
                'ollama_response': analysis_result.get('ollama_response', ''),
                'processing_status': '재처리완료',
                'error_message': None
            }
            
            # PRV 테이블의 경우 추가 필드
            if table_type.upper() == 'PRV':
                prv_field_mapping = {
                    'extracted_schedule': ['EXTRACTED_SCHEDULE', 'extracted_schedule'],
                    'extracted_announcement_date': ['EXTRACTED_ANNOUNCEMENT_DATE', 'extracted_announcement_date'],
                    'is_support_program': ['IS_SUPPORT_PROGRAM', 'is_support_program'],
                    'support_program_reason': ['SUPPORT_PROGRAM_REASON', 'support_program_reason']
                }
                
                update_fields.update({
                    'extracted_schedule': get_field_value(extracted_data, prv_field_mapping['extracted_schedule']),
                    'extracted_announcement_date': get_field_value(extracted_data, prv_field_mapping['extracted_announcement_date']),
                    'is_support_program': extracted_data.get('IS_SUPPORT_PROGRAM', extracted_data.get('is_support_program', True)),
                    'support_program_reason': get_field_value(extracted_data, prv_field_mapping['support_program_reason'])
                })
            
            # UPDATE 쿼리 생성
            set_clauses = []
            for field, value in update_fields.items():
                if value is not None:
                    set_clauses.append(f"{field} = :{field}")
            
            update_query = f"""
                UPDATE {table_name}
                SET {', '.join(set_clauses)}
                WHERE id = :record_id
            """
            
            with db_manager.SessionLocal() as session:
                from sqlalchemy import text
                
                # 파라미터 준비
                params = {**update_fields, 'record_id': record_id}
                
                session.execute(text(update_query), params)
                session.commit()
                
            logger.info(f"레코드 ID {record_id} 업데이트 완료")
            return True
            
        except Exception as e:
            logger.error(f"레코드 업데이트 중 오류 (ID: {record_id}): {e}")
            return False
    
    def reprocess_records(self, table_type: str, ids: List[int]) -> Dict[str, int]:
        """
        지정된 레코드들을 재처리합니다.
        
        Args:
            table_type: 'PRV' 또는 'SCRAP'
            ids: 재처리할 레코드 ID 목록
            
        Returns:
            처리 결과 통계
        """
        stats = {
            'total': len(ids),
            'processed': 0,
            'skipped': 0,
            'failed': 0
        }
        
        try:
            # 레코드 조회
            records = self.fetch_records(table_type, ids)
            if not records:
                logger.warning("조회된 레코드가 없습니다.")
                return stats
            
            # 분석기 선택
            analyzer = self.prv_analyzer if table_type.upper() == 'PRV' else self.scrap_analyzer
            
            for i, record in enumerate(records, 1):
                record_id = record['id']
                folder_name = record['folder_name']
                
                logger.info(f"[{i}/{len(records)}] 레코드 처리 중: ID {record_id} ({folder_name})")
                
                # 재처리 필요성 확인
                if not self._needs_reprocessing(record):
                    logger.info(f"재처리가 필요하지 않음: ID {record_id}")
                    stats['skipped'] += 1
                    continue
                
                # 1차 분석: content_md 사용
                content_md = record.get('content_md', '')
                analysis_result = None
                
                if content_md and content_md.strip():
                    logger.info(f"1차 분석 시작: content_md 사용 (ID: {record_id})")
                    analysis_result = self._analyze_with_ollama(content_md, analyzer, "1차")
                
                # 1차 분석 결과 확인 및 2차 분석 필요성 판단
                if not analysis_result or not self._is_analysis_complete(analysis_result):
                    combined_content = record.get('combined_content', '')
                    
                    if combined_content and combined_content.strip():
                        logger.info(f"2차 분석 시작: combined_content 사용 (ID: {record_id})")
                        analysis_result = self._analyze_with_ollama(combined_content, analyzer, "2차")
                
                # 분석 결과 저장
                if analysis_result and analysis_result.get('success'):
                    if self._update_record(table_type, record_id, analysis_result):
                        stats['processed'] += 1
                        logger.info(f"레코드 ID {record_id} 재처리 완료")
                    else:
                        stats['failed'] += 1
                        logger.error(f"레코드 ID {record_id} 업데이트 실패")
                else:
                    stats['failed'] += 1
                    logger.error(f"레코드 ID {record_id} 분석 실패")
                
                # 잠시 대기 (서버 부하 방지)
                time.sleep(1)
            
            return stats
            
        except Exception as e:
            logger.error(f"재처리 중 오류: {e}")
            raise
    
    def _is_analysis_complete(self, analysis_result: Dict[str, Any]) -> bool:
        """
        분석 결과가 완전한지 확인합니다.
        
        Args:
            analysis_result: Ollama 분석 결과
            
        Returns:
            분석 결과 완전성 여부
        """
        if not analysis_result or not analysis_result.get('success'):
            return False
        
        extracted_data = analysis_result.get('extracted_data', {})
        extracted_content = (extracted_data.get('EXTRACTED_CONTENT') or 
                           extracted_data.get('extracted_content') or '')
        extracted_target = (extracted_data.get('EXTRACTED_TARGET') or 
                          extracted_data.get('extracted_target') or '')
        
        # 지원내용과 지원대상이 모두 추출되었는지 확인
        if not extracted_content.strip() or not extracted_target.strip():
            return False
        
        # 불완전한 답변인지 확인
        incomplete_answers = ['없음', '정보없음', '미상', '확인불가', '불명']
        
        content_incomplete = any(answer in extracted_content.lower() for answer in incomplete_answers)
        target_incomplete = any(answer in extracted_target.lower() for answer in incomplete_answers)
        
        if content_incomplete and target_incomplete:  # 둘 다 불완전한 경우만 false
            return False
        
        return True


def main():
    """메인 함수"""
    print("=== 공고 재처리 스크립트 시작 ===")
    
    parser = argparse.ArgumentParser(description='공고 재처리 스크립트')
    parser.add_argument('table_type', choices=['PRV', 'SCRAP'], 
                       help='테이블 타입 (PRV: announcement_prv_processing, SCRAP: announcement_processing)')
    parser.add_argument('ids', help='재처리할 레코드 ID들 (콤마로 구분, 예: 1,2,3,4,5)')
    
    args = parser.parse_args()
    print(f"인자 파싱 완료: {args.table_type}, {args.ids}")
    
    try:
        # ID 목록 파싱
        ids = []
        for id_str in args.ids.split(','):
            try:
                ids.append(int(id_str.strip()))
            except ValueError:
                logger.error(f"잘못된 ID 형식: {id_str}")
                sys.exit(1)
        
        if not ids:
            logger.error("유효한 ID가 없습니다.")
            sys.exit(1)
        
        logger.info(f"재처리 시작: {args.table_type} 테이블, {len(ids)}개 레코드")
        logger.info(f"대상 ID: {ids}")
        
        # 재처리 실행
        print("AnnouncementReprocessor 초기화 시작...")
        reprocessor = AnnouncementReprocessor()
        print("AnnouncementReprocessor 초기화 완료")
        
        print("재처리 시작...")
        stats = reprocessor.reprocess_records(args.table_type, ids)
        print("재처리 완료")
        
        # 결과 출력
        logger.info("=" * 50)
        logger.info("재처리 완료!")
        logger.info(f"전체 레코드: {stats['total']}")
        logger.info(f"재처리 완료: {stats['processed']}")
        logger.info(f"생략 (재처리 불필요): {stats['skipped']}")
        logger.info(f"실패: {stats['failed']}")
        logger.info("=" * 50)
        
        # 실패가 있으면 종료 코드 1로 종료
        if stats['failed'] > 0:
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"예상치 못한 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()