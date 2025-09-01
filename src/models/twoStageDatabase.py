"""
2단계 Ollama 처리 전용 데이터베이스 모델

기존 announcement_processing 테이블을 참조하여 
2단계 처리에 최적화된 별도 테이블을 생성
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

# 환경변수 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pymysql
from sqlalchemy import (
    create_engine, 
    Column, 
    Integer, 
    String, 
    Text, 
    DateTime, 
    Boolean,
    JSON,
    TypeDecorator
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.mysql import LONGTEXT

try:
    from src.config.config import ConfigManager
    from src.config.logConfig import setup_logging
except ImportError:
    # 절대 import 시도
    import sys
    from pathlib import Path
    
    # 프로젝트 루트를 path에 추가
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    
    from src.config.config import ConfigManager
    from src.config.logConfig import setup_logging

logger = setup_logging(__name__)
config = ConfigManager().get_config()

# Base 모델
Base = declarative_base()


class KoreanJSON(TypeDecorator):
    """한글을 제대로 저장하는 커스텀 JSON 타입"""
    
    impl = JSON
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            # 저장할 때 한글 보존
            return json.loads(json.dumps(value, ensure_ascii=False))
        return value
    
    def process_result_value(self, value, dialect):
        # 읽어올 때는 그대로 반환
        return value


class TwoStageAnnouncementProcessing(Base):
    """2단계 Ollama 공고 처리 결과를 저장하는 전용 테이블"""
    
    __tablename__ = 'two_stage_announcement_processing'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 기본 정보
    folder_name = Column(String(500), nullable=False, comment="폴더명")
    site_code = Column(String(100), nullable=False, comment="사이트 코드")
    
    # 원본 데이터
    content_md = Column(LONGTEXT, comment="content.md 파일 내용")
    combined_content = Column(LONGTEXT, comment="전체 결합된 내용 (content.md + 첨부파일들)")
    
    # 1단계 Ollama 분석 결과 (간단한 정보 추출)
    stage1_prompt = Column(LONGTEXT, comment="1단계 Ollama 프롬프트")
    stage1_response = Column(KoreanJSON, comment="1단계 Ollama 응답")
    stage1_duration = Column(Integer, comment="1단계 응답 시간 (초)")
    
    # 1단계에서 추출된 간단한 정보
    extracted_title = Column(Text, comment="추출된 제목")
    extracted_target = Column(Text, comment="추출된 지원대상")
    extracted_amount = Column(Text, comment="추출된 지원금액")
    extracted_period = Column(Text, comment="추출된 접수기간")
    extracted_schedule = Column(Text, comment="추출된 모집일정")
    extracted_content = Column(Text, comment="추출된 지원내용")
    extracted_announcement_date = Column(Text, comment="추출된 공고등록일")
    extracted_target_classification = Column(KoreanJSON, comment="추출된 지원대상분류 배열 (개인, 기업, 소상공인)")
    
    # 2단계 Ollama 분석 결과 (정밀한 구조화된 분석)
    stage2_executed = Column(Boolean, default=False, comment="2단계 실행 여부")
    stage2_prompt = Column(LONGTEXT, comment="2단계 Ollama 프롬프트")
    stage2_response = Column(KoreanJSON, comment="2단계 Ollama 정밀 구조화된 응답")
    stage2_duration = Column(Integer, comment="2단계 응답 시간 (초)")
    
    # 메타 정보
    processing_status = Column(String(50), default="completed", comment="처리 상태")
    error_message = Column(Text, comment="오류 메시지")
    total_duration = Column(Integer, comment="전체 처리 시간 (초)")
    created_at = Column(DateTime, default=datetime.utcnow, comment="생성일시")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="수정일시")


class TwoStageDatabaseManager:
    """2단계 공고 데이터베이스 매니저"""
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._initialize_database()
    
    def _initialize_database(self):
        """데이터베이스 연결 초기화"""
        try:
            # 환경변수에서 직접 데이터베이스 정보 가져오기
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = int(os.getenv("DB_PORT", "3306"))
            db_user = os.getenv("DB_USER", "root")
            db_password = os.getenv("DB_PASSWORD", "")
            db_name = os.getenv("DB_NAME", "subvention")
            
            # 데이터베이스 URL 생성
            database_url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}?charset=utf8mb4"
            
            # 엔진 생성
            self.engine = create_engine(
                database_url,
                echo=False,  # SQL 로그 출력
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=3600,
                # JSON 처리를 위한 추가 설정
                json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
            )
            
            # 세션 생성기
            self.SessionLocal = sessionmaker(bind=self.engine)
            
            logger.info("2단계 데이터베이스 연결 초기화 완료")
            
        except Exception as e:
            logger.error(f"2단계 데이터베이스 연결 초기화 실패: {e}")
            raise
    
    def create_tables(self):
        """테이블 생성"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("2단계 데이터베이스 테이블 생성 완료")
        except Exception as e:
            logger.error(f"2단계 테이블 생성 실패: {e}")
            raise
    
    def test_connection(self) -> bool:
        """데이터베이스 연결 테스트"""
        try:
            from sqlalchemy import text
            with self.engine.connect() as connection:
                result = connection.execute(text("SELECT 1 as test"))
                test_value = result.fetchone()[0]
                if test_value == 1:
                    logger.info("2단계 데이터베이스 연결 테스트 성공")
                    return True
                else:
                    logger.error("2단계 데이터베이스 연결 테스트 실패")
                    return False
        except Exception as e:
            logger.error(f"2단계 데이터베이스 연결 테스트 중 오류: {e}")
            return False
    
    def save_processing_result(
        self,
        folder_name: str,
        site_code: str,
        content_md: str,
        combined_content: str,
        stage1_result: Dict[str, Any],
        stage1_prompt: str,
        stage1_duration: float,
        stage2_result: Optional[Dict[str, Any]] = None,
        stage2_prompt: str = "",
        stage2_duration: float = 0.0,
        stage2_executed: bool = False,
        update_if_exists: bool = False
    ) -> Optional[int]:
        """
        2단계 처리 결과를 데이터베이스에 저장합니다.
        
        Args:
            folder_name: 폴더명
            site_code: 사이트 코드
            content_md: content.md 내용
            combined_content: 전체 결합된 내용
            stage1_result: 1단계 분석 결과
            stage1_prompt: 1단계 프롬프트
            stage1_duration: 1단계 소요 시간
            stage2_result: 2단계 분석 결과 (선택적)
            stage2_prompt: 2단계 프롬프트
            stage2_duration: 2단계 소요 시간
            stage2_executed: 2단계 실행 여부
            update_if_exists: 이미 존재하는 경우 업데이트할지 여부
            
        Returns:
            저장된 레코드의 ID 또는 None
        """
        try:
            with self.SessionLocal() as session:
                # 이미 존재하는 레코드 확인
                existing_record = session.query(TwoStageAnnouncementProcessing)\
                    .filter(
                        TwoStageAnnouncementProcessing.folder_name == folder_name,
                        TwoStageAnnouncementProcessing.site_code == site_code
                    ).first()
                
                total_duration = int(stage1_duration + stage2_duration)
                
                if existing_record and update_if_exists:
                    # UPSERT: 기존 레코드 업데이트
                    existing_record.content_md = content_md
                    existing_record.combined_content = combined_content
                    existing_record.stage1_prompt = stage1_prompt
                    existing_record.stage1_response = stage1_result
                    existing_record.stage1_duration = int(stage1_duration)
                    
                    # 1단계 추출 정보 업데이트
                    existing_record.extracted_title = stage1_result.get("제목", "해당없음")
                    existing_record.extracted_target = stage1_result.get("지원대상", "해당없음")
                    existing_record.extracted_amount = stage1_result.get("지원금액", "해당없음")
                    existing_record.extracted_period = stage1_result.get("접수기간", "해당없음")
                    existing_record.extracted_schedule = stage1_result.get("모집일정", "해당없음")
                    existing_record.extracted_content = stage1_result.get("지원내용", "해당없음")
                    existing_record.extracted_announcement_date = stage1_result.get("공고등록일", "해당없음")
                    existing_record.extracted_target_classification = stage1_result.get("지원대상분류", [])
                    
                    # 2단계 정보 업데이트
                    existing_record.stage2_executed = stage2_executed
                    if stage2_executed and stage2_result:
                        existing_record.stage2_prompt = stage2_prompt
                        existing_record.stage2_response = stage2_result
                        existing_record.stage2_duration = int(stage2_duration)
                    
                    existing_record.total_duration = total_duration
                    existing_record.processing_status = "completed"
                    existing_record.error_message = None
                    
                    record_id = existing_record.id
                    logger.info(f"기존 2단계 레코드 업데이트: ID {record_id}")
                    
                elif existing_record and not update_if_exists:
                    # 이미 존재하지만 업데이트 안함
                    logger.warning(f"2단계 레코드가 이미 존재함 (업데이트 안함): {folder_name}")
                    return existing_record.id
                    
                else:
                    # INSERT: 새 레코드 생성
                    new_record = TwoStageAnnouncementProcessing(
                        folder_name=folder_name,
                        site_code=site_code,
                        content_md=content_md,
                        combined_content=combined_content,
                        stage1_prompt=stage1_prompt,
                        stage1_response=stage1_result,
                        stage1_duration=int(stage1_duration),
                        
                        # 1단계 추출 정보
                        extracted_title=stage1_result.get("제목", "해당없음"),
                        extracted_target=stage1_result.get("지원대상", "해당없음"),
                        extracted_amount=stage1_result.get("지원금액", "해당없음"),
                        extracted_period=stage1_result.get("접수기간", "해당없음"),
                        extracted_schedule=stage1_result.get("모집일정", "해당없음"),
                        extracted_content=stage1_result.get("지원내용", "해당없음"),
                        extracted_announcement_date=stage1_result.get("공고등록일", "해당없음"),
                        extracted_target_classification=stage1_result.get("지원대상분류", []),
                        
                        # 2단계 정보
                        stage2_executed=stage2_executed,
                        stage2_prompt=stage2_prompt if stage2_executed else "",
                        stage2_response=stage2_result if stage2_executed else {},
                        stage2_duration=int(stage2_duration) if stage2_executed else 0,
                        
                        total_duration=total_duration,
                        processing_status="completed"
                    )
                    
                    session.add(new_record)
                    session.flush()  # ID 생성을 위해 flush
                    record_id = new_record.id
                    logger.info(f"새 2단계 레코드 생성: ID {record_id}")
                
                session.commit()
                logger.info(f"2단계 처리 결과 저장 완료: ID {record_id}")
                return record_id
                
        except Exception as e:
            logger.error(f"2단계 처리 결과 저장 실패: {e}")
            return None
    
    def create_initial_record(
        self,
        folder_name: str,
        site_code: str,
        content_md: str,
        combined_content: str,
        update_if_exists: bool = False
    ) -> Optional[int]:
        """
        파일 읽기 완료 후 초기 레코드를 생성합니다.
        
        Args:
            folder_name: 폴더명
            site_code: 사이트 코드
            content_md: content.md 내용
            combined_content: 전체 결합된 내용
            update_if_exists: 이미 존재하는 경우 업데이트할지 여부
            
        Returns:
            생성된 레코드의 ID 또는 None
        """
        try:
            with self.SessionLocal() as session:
                # 이미 존재하는 레코드 확인
                existing_record = session.query(TwoStageAnnouncementProcessing)\
                    .filter(
                        TwoStageAnnouncementProcessing.folder_name == folder_name,
                        TwoStageAnnouncementProcessing.site_code == site_code
                    ).first()
                
                if existing_record and update_if_exists:
                    # 기존 레코드 업데이트
                    existing_record.content_md = content_md
                    existing_record.combined_content = combined_content
                    existing_record.processing_status = "processing"
                    existing_record.error_message = None
                    
                    record_id = existing_record.id
                    logger.info(f"기존 초기 레코드 업데이트: ID {record_id}")
                    
                elif existing_record and not update_if_exists:
                    # 이미 존재하지만 업데이트 안함
                    logger.warning(f"초기 레코드가 이미 존재함: {folder_name}")
                    return existing_record.id
                    
                else:
                    # 새 레코드 생성
                    new_record = TwoStageAnnouncementProcessing(
                        folder_name=folder_name,
                        site_code=site_code,
                        content_md=content_md,
                        combined_content=combined_content,
                        processing_status="processing",
                        
                        # 기본값들
                        stage1_prompt="",
                        stage1_response={},
                        stage1_duration=0,
                        extracted_title="해당없음",
                        extracted_target="해당없음",
                        extracted_amount="해당없음",
                        extracted_period="해당없음",
                        extracted_schedule="해당없음",
                        extracted_content="해당없음",
                        extracted_announcement_date="해당없음",
                        extracted_target_classification=[],
                        
                        stage2_executed=False,
                        stage2_prompt="",
                        stage2_response={},
                        stage2_duration=0,
                        total_duration=0
                    )
                    
                    session.add(new_record)
                    session.flush()  # ID 생성을 위해 flush
                    record_id = new_record.id
                    logger.info(f"새 초기 레코드 생성: ID {record_id}")
                
                session.commit()
                return record_id
                
        except Exception as e:
            logger.error(f"초기 레코드 생성 실패: {e}")
            return None
    
    def update_stage1_result(
        self,
        record_id: int,
        stage1_result: Dict[str, Any],
        stage1_prompt: str,
        stage1_duration: float
    ) -> bool:
        """
        1단계 Ollama 결과로 레코드를 업데이트합니다.
        
        Args:
            record_id: 레코드 ID
            stage1_result: 1단계 분석 결과
            stage1_prompt: 1단계 프롬프트
            stage1_duration: 1단계 소요 시간
            
        Returns:
            업데이트 성공 여부
        """
        try:
            with self.SessionLocal() as session:
                record = session.get(TwoStageAnnouncementProcessing, record_id)
                if not record:
                    logger.error(f"레코드를 찾을 수 없음: ID {record_id}")
                    return False
                
                # 1단계 결과 업데이트
                record.stage1_prompt = stage1_prompt
                record.stage1_response = stage1_result
                record.stage1_duration = int(stage1_duration)
                
                # 1단계 추출 정보 업데이트
                record.extracted_title = stage1_result.get("제목", "해당없음")
                record.extracted_target = stage1_result.get("지원대상", "해당없음")
                record.extracted_amount = stage1_result.get("지원금액", "해당없음")
                record.extracted_period = stage1_result.get("접수기간", "해당없음")
                record.extracted_schedule = stage1_result.get("모집일정", "해당없음")
                record.extracted_content = stage1_result.get("지원내용", "해당없음")
                record.extracted_announcement_date = stage1_result.get("공고등록일", "해당없음")
                record.extracted_target_classification = stage1_result.get("지원대상분류", [])
                
                record.total_duration = int(stage1_duration)
                
                session.commit()
                logger.info(f"1단계 결과 업데이트 완료: ID {record_id}")
                return True
                
        except Exception as e:
            logger.error(f"1단계 결과 업데이트 실패: {e}")
            return False
    
    def update_stage2_result(
        self,
        record_id: int,
        stage2_result: Dict[str, Any],
        stage2_prompt: str,
        stage2_duration: float
    ) -> bool:
        """
        2단계 Ollama 결과로 레코드를 업데이트합니다.
        
        Args:
            record_id: 레코드 ID
            stage2_result: 2단계 분석 결과
            stage2_prompt: 2단계 프롬프트
            stage2_duration: 2단계 소요 시간
            
        Returns:
            업데이트 성공 여부
        """
        try:
            with self.SessionLocal() as session:
                record = session.get(TwoStageAnnouncementProcessing, record_id)
                if not record:
                    logger.error(f"레코드를 찾을 수 없음: ID {record_id}")
                    return False
                
                # 2단계 결과 업데이트
                record.stage2_executed = True
                record.stage2_prompt = stage2_prompt
                record.stage2_response = stage2_result
                record.stage2_duration = int(stage2_duration)
                
                # 전체 처리 시간 업데이트
                record.total_duration = record.stage1_duration + int(stage2_duration)
                record.processing_status = "completed"
                
                session.commit()
                logger.info(f"2단계 결과 업데이트 완료: ID {record_id}")
                return True
                
        except Exception as e:
            logger.error(f"2단계 결과 업데이트 실패: {e}")
            return False
    
    def mark_completed_without_stage2(
        self,
        record_id: int
    ) -> bool:
        """
        2단계 없이 완료된 레코드를 마킹합니다.
        
        Args:
            record_id: 레코드 ID
            
        Returns:
            업데이트 성공 여부
        """
        try:
            with self.SessionLocal() as session:
                record = session.get(TwoStageAnnouncementProcessing, record_id)
                if not record:
                    logger.error(f"레코드를 찾을 수 없음: ID {record_id}")
                    return False
                
                record.stage2_executed = False
                record.processing_status = "completed"
                
                session.commit()
                logger.info(f"2단계 없이 완료 처리: ID {record_id}")
                return True
                
        except Exception as e:
            logger.error(f"완료 처리 실패: {e}")
            return False

    def save_processing_error(
        self,
        folder_name: str,
        site_code: str,
        error_message: str,
        content_md: str = None,
        combined_content: str = None
    ) -> Optional[int]:
        """
        처리 실패한 공고 정보를 저장합니다.
        
        Args:
            folder_name: 폴더명
            site_code: 사이트 코드
            error_message: 오류 메시지
            content_md: content.md 내용 (있는 경우)
            combined_content: 결합된 내용 (있는 경우)
            
        Returns:
            저장된 레코드의 ID 또는 None
        """
        try:
            with self.SessionLocal() as session:
                error_record = TwoStageAnnouncementProcessing(
                    folder_name=folder_name,
                    site_code=site_code,
                    content_md=content_md,
                    combined_content=combined_content,
                    processing_status="failed",
                    error_message=error_message,
                    stage1_response={},
                    stage1_prompt="",
                    stage1_duration=0,
                    stage2_executed=False,
                    stage2_response={},
                    stage2_prompt="",
                    stage2_duration=0,
                    total_duration=0
                )
                
                session.add(error_record)
                session.commit()
                
                logger.info(f"2단계 처리 실패 정보 저장 완료: {folder_name}")
                return error_record.id
                
        except Exception as e:
            logger.error(f"2단계 처리 실패 정보 저장 실패: {e}")
            return None
    
    def get_processed_folders(self, site_code: str) -> List[str]:
        """
        이미 처리된 폴더 목록을 가져옵니다.
        
        Args:
            site_code: 사이트 코드
            
        Returns:
            처리된 폴더명 리스트
        """
        try:
            with self.SessionLocal() as session:
                result = session.query(TwoStageAnnouncementProcessing.folder_name)\
                    .filter(TwoStageAnnouncementProcessing.site_code == site_code)\
                    .all()
                
                return [row[0] for row in result]
                
        except Exception as e:
            logger.error(f"2단계 처리된 폴더 목록 조회 실패: {e}")
            return []
    
    def is_already_processed(self, folder_name: str, site_code: str) -> bool:
        """
        특정 폴더가 이미 처리되었는지 확인합니다.
        
        Args:
            folder_name: 폴더명
            site_code: 사이트 코드
            
        Returns:
            처리 여부 (True: 이미 처리됨, False: 미처리)
        """
        try:
            if not self.engine or not self.SessionLocal:
                logger.warning("2단계 데이터베이스 연결이 없어서 처리 상태를 확인할 수 없습니다. 미처리로 간주합니다.")
                return False
                
            with self.SessionLocal() as session:
                result = session.query(TwoStageAnnouncementProcessing)\
                    .filter(
                        TwoStageAnnouncementProcessing.folder_name == folder_name,
                        TwoStageAnnouncementProcessing.site_code == site_code
                    )\
                    .first()
                
                return result is not None
                
        except Exception as e:
            logger.error(f"2단계 폴더 처리 상태 확인 실패: {e}")
            return False  # 에러 시 미처리로 간주하여 다시 처리하도록 함


def create_two_stage_tables():
    """2단계 처리용 테이블을 생성합니다."""
    try:
        db_manager = TwoStageDatabaseManager()
        if db_manager.test_connection():
            db_manager.create_tables()
            logger.info("2단계 처리용 테이블 생성 완료")
            return True
        else:
            logger.error("2단계 데이터베이스 연결 실패로 테이블 생성 불가")
            return False
    except Exception as e:
        logger.error(f"2단계 테이블 생성 중 오류: {e}")
        return False


if __name__ == "__main__":
    # 테스트
    try:
        # 테이블 생성 테스트
        create_two_stage_tables()
        
        # 연결 테스트
        db_manager = TwoStageDatabaseManager()
        if db_manager.test_connection():
            print("2단계 데이터베이스 연결 및 테이블 생성 성공!")
        else:
            print("2단계 데이터베이스 연결 실패")
            
    except Exception as e:
        print(f"2단계 테스트 중 오류: {e}")