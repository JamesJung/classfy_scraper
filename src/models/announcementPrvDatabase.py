"""
공고 PRV 처리 전용 데이터베이스 모델

공고 PRV 처리 결과를 저장하는 테이블:
- announcement_prv_processing: 공고 PRV 처리 결과 저장
- attachment_prv_files: 첨부파일 정보 저장
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
    ForeignKey,
    TypeDecorator
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.mysql import LONGTEXT

try:
    from src.config.config import ConfigManager
    from src.config.logConfig import setup_logging
    from src.utils.dataProcessor import format_date_to_standard, extract_url_from_content, analyze_target_type_and_small_business
except ImportError:
    # 절대 import 시도
    import sys
    from pathlib import Path
    
    # 프로젝트 루트를 path에 추가
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    
    from src.config.config import ConfigManager
    from src.config.logConfig import setup_logging
    from src.utils.dataProcessor import format_date_to_standard, extract_url_from_content, analyze_target_type_and_small_business

logger = setup_logging(__name__)
config = ConfigManager().get_config()

# Base 모델
Base = declarative_base()


def serialize_json_korean(data: Any) -> Any:
    """
    JSON 데이터를 한글이 읽을 수 있는 형태로 직렬화합니다.
    
    Args:
        data: 직렬화할 데이터
        
    Returns:
        한글이 보존된 JSON 데이터
    """
    if data is None:
        return None
    
    try:
        # ensure_ascii=False로 한글을 유니코드 이스케이프하지 않도록 설정
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        # 다시 파싱해서 dict/list로 반환 (SQLAlchemy JSON 타입 호환)
        return json.loads(json_str)
    except Exception as e:
        logger.warning(f"JSON 직렬화 중 오류: {e}, 원본 데이터 사용")
        return data


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


class AnnouncementPrvProcessing(Base):
    """공고 PRV 처리 결과를 저장하는 테이블"""
    
    __tablename__ = 'announcement_prv_processing'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 기본 정보
    folder_name = Column(String(500), nullable=False, comment="폴더명")
    site_code = Column(String(100), nullable=False, comment="사이트 코드")
    
    # 원본 데이터
    content_md = Column(LONGTEXT, comment="content.md 파일 내용")
    combined_content = Column(LONGTEXT, comment="첨부파일들 결합된 내용")
    
    # Ollama 분석 결과
    extracted_title = Column(Text, comment="추출된 제목")
    extracted_target = Column(Text, comment="추출된 지원대상")
    extracted_target_type = Column(Text, comment="추출된 지원대상 분류")
    extracted_amount = Column(Text, comment="추출된 지원금액")
    extracted_period = Column(Text, comment="추출된 접수기간")
    extracted_schedule = Column(Text, comment="추출된 모집일정")
    extracted_content = Column(Text, comment="추출된 지원내용")
    extracted_announcement_date = Column(Text, comment="추출된 등록일(공고일)")
    
    # 추가 PRV 분석 결과
    extracted_gov24_url = Column(Text, comment="정부24 원본 URL")
    extracted_origin_url = Column(Text, comment="원본 URL")
    is_support_program = Column(Boolean, comment="지원사업 여부")
    support_program_reason = Column(Text, comment="지원사업 판단 근거")
    
    # Ollama 처리 결과
    ollama_first_response = Column(LONGTEXT, comment="첫번째 Ollama 응답 (content_md 기반)")
    ollama_response = Column(LONGTEXT, comment="최종 Ollama 응답")
    ollama_prompt = Column(LONGTEXT, comment="Ollama에 전송한 프롬프트")
    formatted_announcement_date = Column(String(10), comment="표준화된 공고일 (YYYY-MM-DD)")
    original_url = Column(Text, comment="원본 URL")
    target_type = Column(String(20), comment="지원대상 유형 (individual/company)")
    is_small_business = Column(Boolean, comment="소상공인 해당여부")
    
    # 첨부파일 정보
    attachment_files_list = Column(LONGTEXT, comment="첨부파일 목록 및 정보")
    attachment_filenames = Column(Text, comment="첨부파일명 목록 (PDF 포함)")
    
    # 제외 키워드 정보
    exclusion_keyword = Column(Text, comment="매칭된 제외 키워드")
    exclusion_reason = Column(Text, comment="제외 사유")
    
    # 메타 정보 (상태: 제외/ollama/성공/completed)
    processing_status = Column(String(50), default="ollama", comment="처리 상태 (제외/ollama/성공/completed)")
    error_message = Column(Text, comment="오류 메시지")
    created_at = Column(DateTime, default=datetime.utcnow, comment="생성일시")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="수정일시")
    
    # 관계 설정
    attachments = relationship("AttachmentPrvFile", back_populates="announcement", cascade="all, delete-orphan")


class AttachmentPrvFile(Base):
    """첨부파일 정보를 저장하는 테이블"""
    
    __tablename__ = 'attachment_prv_files'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 연관 관계
    announcement_id = Column(Integer, ForeignKey('announcement_prv_processing.id'), nullable=False)
    
    # 파일 정보
    filename = Column(String(255), nullable=False, comment="첨부파일명 (확장자 제외)")
    file_extension = Column(String(10), comment="파일 확장자")
    file_path = Column(String(1000), comment="원본 파일 경로")
    file_size = Column(Integer, comment="파일 크기 (bytes)")
    
    # 변환 결과
    converted_content = Column(LONGTEXT, comment="변환된 텍스트 내용")
    conversion_method = Column(String(50), comment="변환 방법 (pdf_docling, hwp_markdown, ocr 등)")
    conversion_success = Column(Boolean, default=False, comment="변환 성공 여부")
    conversion_error = Column(Text, comment="변환 오류 메시지")
    
    # 메타 정보
    created_at = Column(DateTime, default=datetime.utcnow, comment="생성일시")
    
    # 관계 설정
    announcement = relationship("AnnouncementPrvProcessing", back_populates="attachments")


class AnnouncementPrvDatabaseManager:
    """공고 PRV 데이터베이스 매니저"""
    
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
            
            logger.info("PRV 데이터베이스 연결 초기화 완료")
            
        except Exception as e:
            logger.error(f"PRV 데이터베이스 연결 초기화 실패: {e}")
            raise
    
    def create_tables(self):
        """테이블 생성"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("PRV 데이터베이스 테이블 생성 완료")
        except Exception as e:
            logger.error(f"PRV 테이블 생성 실패: {e}")
            raise

    def test_connection(self) -> bool:
        """데이터베이스 연결 테스트"""
        try:
            from sqlalchemy import text
            with self.engine.connect() as connection:
                result = connection.execute(text("SELECT 1 as test"))
                test_value = result.fetchone()[0]
                if test_value == 1:
                    logger.info("PRV 데이터베이스 연결 테스트 성공")
                    return True
                else:
                    logger.error("PRV 데이터베이스 연결 테스트 실패")
                    return False
        except Exception as e:
            logger.error(f"PRV 데이터베이스 연결 테스트 중 오류: {e}")
            return False
    
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
                result = session.query(AnnouncementPrvProcessing.folder_name)\
                    .filter(AnnouncementPrvProcessing.site_code == site_code)\
                    .all()
                
                return [row[0] for row in result]
                
        except Exception as e:
            logger.error(f"PRV 처리된 폴더 목록 조회 실패: {e}")
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
                logger.warning("PRV 데이터베이스 연결이 없어서 처리 상태를 확인할 수 없습니다. 미처리로 간주합니다.")
                return False
                
            with self.SessionLocal() as session:
                result = session.query(AnnouncementPrvProcessing)\
                    .filter(
                        AnnouncementPrvProcessing.folder_name == folder_name,
                        AnnouncementPrvProcessing.site_code == site_code
                    )\
                    .first()
                
                return result is not None
                
        except Exception as e:
            logger.error(f"PRV 폴더 처리 상태 확인 실패: {e}")
            return False  # 에러 시 미처리로 간주하여 다시 처리하도록 함


def create_announcement_prv_tables():
    """공고 PRV 처리용 테이블을 생성합니다."""
    try:
        db_manager = AnnouncementPrvDatabaseManager()
        if db_manager.test_connection():
            db_manager.create_tables()
            logger.info("공고 PRV 처리용 테이블 생성 완료")
            return True
        else:
            logger.error("PRV 데이터베이스 연결 실패로 테이블 생성 불가")
            return False
    except Exception as e:
        logger.error(f"PRV 테이블 생성 중 오류: {e}")
        return False


if __name__ == "__main__":
    # 테스트
    try:
        # 테이블 생성 테스트
        create_announcement_prv_tables()
        
        # 연결 테스트
        db_manager = AnnouncementPrvDatabaseManager()
        if db_manager.test_connection():
            print("PRV 데이터베이스 연결 및 테이블 생성 성공!")
        else:
            print("PRV 데이터베이스 연결 실패")
            
    except Exception as e:
        print(f"PRV 테스트 중 오류: {e}")