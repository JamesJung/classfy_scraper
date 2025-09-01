"""
공고 처리 전용 데이터베이스 모델 - RAG 시스템 통합

ChromaDB를 활용한 RAG(Retrieval-Augmented Generation) 시스템과
기존 MySQL 데이터베이스를 통합한 하이브리드 저장소입니다.

공고 처리 결과를 저장하는 테이블:
- announcement_processing: 공고 처리 결과 저장 (기존 + RAG 컨텍스트)
- attachment_files: 첨부파일 정보 저장
- ChromaDB: 벡터 임베딩 및 유사도 검색
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
    from src.utils.ollamaClientRag import AnnouncementAnalyzerRAG
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


class AnnouncementProcessingRAG(Base):
    """공고 처리 결과를 저장하는 테이블 - RAG 시스템 통합"""
    
    __tablename__ = 'announcement_processing_rag'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 기본 정보
    folder_name = Column(String(500), nullable=False, comment="폴더명")
    site_code = Column(String(100), nullable=False, comment="사이트 코드")
    
    # 원본 데이터
    content_md = Column(LONGTEXT, comment="content.md 파일 내용")
    combined_content = Column(LONGTEXT, comment="전체 결합된 내용 (content.md + 첨부파일들)")
    
    # Ollama 분석 결과
    extracted_title = Column(Text, comment="추출된 제목")
    extracted_target = Column(Text, comment="추출된 지원대상")
    extracted_target_type = Column(Text, comment="추출된 지원대상 분류")
    extracted_amount = Column(Text, comment="추출된 지원금액")
    extracted_period = Column(Text, comment="추출된 접수기간")
    extracted_schedule = Column(Text, comment="추출된 모집일정")
    extracted_content = Column(Text, comment="추출된 지원내용")
    extracted_announcement_date = Column(Text, comment="추출된 등록일(공고일)")
    
    # Ollama 처리 결과
    ollama_prompt = Column(LONGTEXT, comment="Ollama에 전송한 프롬프트")
    ollama_response = Column(LONGTEXT, comment="Ollama 원본 응답")
    formatted_announcement_date = Column(String(10), comment="표준화된 공고일 (YYYY-MM-DD)")
    original_url = Column(Text, comment="원본 URL")
    target_type = Column(String(20), comment="지원대상 유형 (individual/company)")
    is_small_business = Column(Boolean, comment="소상공인 해당여부")
    
    # RAG 시스템 관련 필드
    rag_context = Column(LONGTEXT, comment="RAG 컨텍스트 정보 (JSON)")
    vector_id = Column(String(100), comment="ChromaDB 벡터 ID")
    similar_announcement_count = Column(Integer, default=0, comment="참조된 유사 공고 개수")
    
    # 첨부파일 정보
    attachment_files_list = Column(LONGTEXT, comment="첨부파일 목록 및 정보")
    
    # 메타 정보
    processing_status = Column(String(50), default="processing", comment="처리 상태")
    error_message = Column(Text, comment="오류 메시지")
    created_at = Column(DateTime, default=datetime.utcnow, comment="생성일시")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="수정일시")
    
    # 관계 설정
    attachments = relationship("AttachmentFileRAG", back_populates="announcement", cascade="all, delete-orphan")


class AttachmentFileRAG(Base):
    """첨부파일 정보를 저장하는 테이블 - RAG 시스템 통합"""
    
    __tablename__ = 'attachment_files_rag'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 연관 관계
    announcement_id = Column(Integer, ForeignKey('announcement_processing_rag.id'), nullable=False)
    
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
    announcement = relationship("AnnouncementProcessingRAG", back_populates="attachments")


class AnnouncementDatabaseManagerRAG:
    """공고 데이터베이스 매니저 - RAG 시스템 통합"""
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._initialize_database()
        
        # RAG 시스템 초기화는 필요시에만
        self._rag_analyzer = None
    
    @property
    def rag_analyzer(self):
        """지연 로딩으로 RAG 분석기를 초기화합니다."""
        if self._rag_analyzer is None:
            try:
                from src.utils.ollamaClientRag import AnnouncementAnalyzerRAG
                self._rag_analyzer = AnnouncementAnalyzerRAG()
                logger.info("RAG 분석기 초기화 완료")
            except Exception as e:
                logger.error(f"RAG 분석기 초기화 실패: {e}")
                self._rag_analyzer = None
        return self._rag_analyzer
    
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
            
            logger.info("RAG 데이터베이스 연결 초기화 완료")
            
        except Exception as e:
            logger.error(f"RAG 데이터베이스 연결 초기화 실패: {e}")
            raise
    
    def create_tables(self):
        """테이블 생성"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("RAG 데이터베이스 테이블 생성 완료")
        except Exception as e:
            logger.error(f"RAG 테이블 생성 실패: {e}")
            raise
    
    def _process_announcement_data(self, ollama_response: Dict[str, Any], combined_content: str) -> Dict[str, Any]:
        """
        공고 데이터를 후처리하여 추가 분석 정보를 생성합니다.
        
        Args:
            ollama_response: Ollama 분석 결과
            combined_content: 전체 결합된 내용
            
        Returns:
            처리된 추가 데이터
        """
        processed_data = {}
        
        try:
            # 1. 공고일자 표준화
            raw_date = ollama_response.get("EXTRACTED_ANNOUNCEMENT_DATE", "")
            formatted_date = format_date_to_standard(raw_date)
            processed_data["formatted_announcement_date"] = formatted_date
            
            # 2. 원본 URL 추출
            original_url = extract_url_from_content(combined_content)
            processed_data["original_url"] = original_url
            
            # 3. 지원대상 분석
            target_description = ollama_response.get("EXTRACTED_TARGET", "")
            
            # 프로그램 로직 분석
            logic_target_type, logic_is_small_business = analyze_target_type_and_small_business(target_description)
            
            # 기존 필드들은 프로그램 로직 결과 사용 (하위 호환성)
            processed_data["target_type"] = logic_target_type
            processed_data["is_small_business"] = logic_is_small_business
            
            logger.debug(f"RAG 데이터 후처리 완료: 날짜={formatted_date}, URL={'있음' if original_url else '없음'}, 대상유형={logic_target_type}, 소상공인={logic_is_small_business}")
            
        except Exception as e:
            logger.error(f"RAG 데이터 후처리 중 오류: {e}")
            import traceback
            logger.error(f"전체 스택 트레이스: {traceback.format_exc()}")
            # 오류 발생 시 기본값 사용
            processed_data.update({
                "formatted_announcement_date": None,
                "original_url": None,
                "target_type": None,
                "is_small_business": None
            })
        
        return processed_data

    def test_connection(self) -> bool:
        """데이터베이스 연결 테스트"""
        try:
            from sqlalchemy import text
            with self.engine.connect() as connection:
                result = connection.execute(text("SELECT 1 as test"))
                test_value = result.fetchone()[0]
                if test_value == 1:
                    logger.info("RAG 데이터베이스 연결 테스트 성공")
                    return True
                else:
                    logger.error("RAG 데이터베이스 연결 테스트 실패")
                    return False
        except Exception as e:
            logger.error(f"RAG 데이터베이스 연결 테스트 중 오류: {e}")
            return False
    
    def save_announcement_processing(
        self,
        folder_name: str,
        site_code: str,
        content_md: str,
        combined_content: str,
        ollama_response: Dict[str, Any],
        ollama_prompt: str = None,
        attachment_files: List[Dict[str, Any]] = None,
        rag_context: Dict[str, Any] = None,
        update_if_exists: bool = True,
        processing_status: str = "completed",
        error_message: str = None
    ) -> Optional[int]:
        """
        공고 처리 결과를 RAG 시스템과 함께 데이터베이스에 UPSERT 방식으로 저장합니다.
        MySQL의 INSERT ... ON DUPLICATE KEY UPDATE 구문을 사용합니다.
        
        Args:
            folder_name: 폴더명
            site_code: 사이트 코드
            content_md: content.md 내용
            combined_content: 전체 결합된 내용
            ollama_response: Ollama 분석 결과
            ollama_prompt: Ollama에 보낸 프롬프트
            attachment_files: 첨부파일 정보 리스트
            rag_context: RAG 컨텍스트 정보
            update_if_exists: 이미 존재하는 경우 업데이트할지 여부 (기본값: True)
            processing_status: 처리 상태 (기본값: "completed")
            error_message: 에러 메시지 (선택사항)
            
        Returns:
            저장된 레코드의 ID 또는 None
        """
        try:
            from sqlalchemy import text
            
            # 데이터 후처리
            processed_data = self._process_announcement_data(ollama_response, combined_content)
            
            with self.SessionLocal() as session:
                # JSON 데이터 직렬화
                ollama_response_json = json.dumps(ollama_response, ensure_ascii=False) if ollama_response else None
                attachment_files_json = json.dumps(attachment_files, ensure_ascii=False) if attachment_files else None
                rag_context_json = json.dumps(rag_context, ensure_ascii=False) if rag_context else None
                
                # 벡터 ID 생성
                vector_id = f"{site_code}_{folder_name}_{hash(combined_content[:100])}"
                similar_count = rag_context.get('context_count', 0) if rag_context else 0
                
                # UPSERT SQL 쿼리 (INSERT ... ON DUPLICATE KEY UPDATE)
                upsert_sql = text("""
                    INSERT INTO announcement_processing_rag (
                        folder_name, site_code, content_md, combined_content, 
                        ollama_prompt, ollama_response, 
                        extracted_title, extracted_target, extracted_target_type, 
                        extracted_amount, extracted_period, extracted_schedule, 
                        extracted_content, extracted_announcement_date,
                        formatted_announcement_date, original_url, target_type, 
                        is_small_business, attachment_files_list, processing_status,
                        rag_context, vector_id, similar_announcement_count,
                        created_at, updated_at
                    ) VALUES (
                        :folder_name, :site_code, :content_md, :combined_content,
                        :ollama_prompt, :ollama_response,
                        :extracted_title, :extracted_target, :extracted_target_type,
                        :extracted_amount, :extracted_period, :extracted_schedule,
                        :extracted_content, :extracted_announcement_date,
                        :formatted_announcement_date, :original_url, :target_type,
                        :is_small_business, :attachment_files_list, :processing_status,
                        :rag_context, :vector_id, :similar_announcement_count,
                        NOW(), NOW()
                    ) 
                    ON DUPLICATE KEY UPDATE
                        content_md = VALUES(content_md),
                        combined_content = VALUES(combined_content),
                        ollama_prompt = VALUES(ollama_prompt),
                        ollama_response = VALUES(ollama_response),
                        extracted_title = VALUES(extracted_title),
                        extracted_target = VALUES(extracted_target),
                        extracted_target_type = VALUES(extracted_target_type),
                        extracted_amount = VALUES(extracted_amount),
                        extracted_period = VALUES(extracted_period),
                        extracted_schedule = VALUES(extracted_schedule),
                        extracted_content = VALUES(extracted_content),
                        extracted_announcement_date = VALUES(extracted_announcement_date),
                        formatted_announcement_date = VALUES(formatted_announcement_date),
                        original_url = VALUES(original_url),
                        target_type = VALUES(target_type),
                        is_small_business = VALUES(is_small_business),
                        attachment_files_list = VALUES(attachment_files_list),
                        processing_status = VALUES(processing_status),
                        rag_context = VALUES(rag_context),
                        vector_id = VALUES(vector_id),
                        similar_announcement_count = VALUES(similar_announcement_count),
                        error_message = :error_message,
                        updated_at = NOW()
                """)
                
                # 파라미터 준비
                params = {
                    'folder_name': folder_name,
                    'site_code': site_code,
                    'content_md': content_md,
                    'combined_content': combined_content,
                    'ollama_prompt': ollama_prompt,
                    'ollama_response': ollama_response_json,
                    'extracted_title': ollama_response.get("EXTRACTED_TITLE", "정보 없음"),
                    'extracted_target': ollama_response.get("EXTRACTED_TARGET", "정보 없음"),
                    'extracted_target_type': ollama_response.get("EXTRACTED_TARGET_TYPE", "정보 없음"),
                    'extracted_amount': ollama_response.get("EXTRACTED_AMOUNT", "정보 없음"),
                    'extracted_period': ollama_response.get("EXTRACTED_PERIOD", "정보 없음"),
                    'extracted_schedule': ollama_response.get("EXTRACTED_SCHEDULE", "정보 없음"),
                    'extracted_content': ollama_response.get("EXTRACTED_CONTENT", "정보 없음"),
                    'extracted_announcement_date': ollama_response.get("EXTRACTED_ANNOUNCEMENT_DATE", "정보 없음"),
                    'formatted_announcement_date': processed_data.get("formatted_announcement_date"),
                    'original_url': processed_data.get("original_url"),
                    'target_type': processed_data.get("target_type"),
                    'is_small_business': processed_data.get("is_small_business"),
                    'attachment_files_list': attachment_files_json,
                    'processing_status': processing_status,
                    'rag_context': rag_context_json,
                    'vector_id': vector_id,
                    'similar_announcement_count': similar_count,
                    'error_message': error_message
                }
                
                # UPSERT 실행
                result = session.execute(upsert_sql, params)
                session.commit()
                
                # 저장된 레코드의 ID 가져오기
                if result.lastrowid:
                    # INSERT된 경우
                    announcement_id = result.lastrowid
                    logger.info(f"새 RAG 공고 레코드 생성: ID {announcement_id}")
                else:
                    # UPDATE된 경우
                    existing_record = session.query(AnnouncementProcessingRAG)\
                        .filter(
                            AnnouncementProcessingRAG.folder_name == folder_name,
                            AnnouncementProcessingRAG.site_code == site_code
                        ).first()
                    
                    if existing_record:
                        announcement_id = existing_record.id
                        logger.info(f"기존 RAG 공고 레코드 업데이트: ID {announcement_id}")
                    else:
                        logger.error("RAG UPSERT 후 레코드를 찾을 수 없음")
                        return None
                
                return announcement_id
                
        except Exception as e:
            logger.error(f"RAG 공고 처리 결과 저장 실패: {e}")
            return None
    
    def store_vector_embedding(self, record_id: int, content: str, extracted_data: Dict[str, Any], site_code: str) -> bool:
        """공고 데이터를 ChromaDB 벡터 스토어에 저장합니다."""
        try:
            if self.rag_analyzer:
                doc_id = f"announcement_{record_id}"
                success = self.rag_analyzer.store_announcement_for_rag(
                    doc_id=doc_id,
                    content=content,
                    extracted_data=extracted_data,
                    site_code=site_code
                )
                
                if success:
                    logger.info(f"벡터 임베딩 저장 완료: record_id={record_id}")
                else:
                    logger.error(f"벡터 임베딩 저장 실패: record_id={record_id}")
                    
                return success
            else:
                logger.warning("RAG 분석기가 초기화되지 않았습니다.")
                return False
                
        except Exception as e:
            logger.error(f"벡터 임베딩 저장 중 오류: {e}")
            return False

    def _update_processing_status(self, record_id: int, status: str, error_message: str = None) -> bool:
        """
        레코드의 처리 상태를 업데이트합니다.
        
        Args:
            record_id: 레코드 ID
            status: 처리 상태 (completed, failed, processing)
            error_message: 에러 메시지 (선택사항)
            
        Returns:
            업데이트 성공 여부
        """
        try:
            with self.SessionLocal() as session:
                record = session.get(AnnouncementProcessingRAG, record_id)
                if record:
                    record.processing_status = status
                    if error_message:
                        record.error_message = error_message
                    session.commit()
                    logger.info(f"RAG 처리 상태 업데이트: ID {record_id} → {status}")
                    return True
                else:
                    logger.error(f"RAG 레코드를 찾을 수 없음: ID {record_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"RAG 처리 상태 업데이트 실패: {e}")
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
                announcement = AnnouncementProcessingRAG(
                    folder_name=folder_name,
                    site_code=site_code,
                    content_md=content_md,
                    combined_content=combined_content,
                    processing_status="failed",
                    error_message=error_message
                )
                
                session.add(announcement)
                session.commit()
                
                logger.info(f"RAG 처리 실패 공고 저장 완료: {folder_name}")
                return announcement.id
                
        except Exception as e:
            logger.error(f"RAG 처리 실패 공고 저장 실패: {e}")
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
                result = session.query(AnnouncementProcessingRAG.folder_name)\
                    .filter(AnnouncementProcessingRAG.site_code == site_code)\
                    .all()
                
                return [row[0] for row in result]
                
        except Exception as e:
            logger.error(f"RAG 처리된 폴더 목록 조회 실패: {e}")
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
                logger.warning("RAG 데이터베이스 연결이 없어서 처리 상태를 확인할 수 없습니다. 미처리로 간주합니다.")
                return False
                
            with self.SessionLocal() as session:
                result = session.query(AnnouncementProcessingRAG)\
                    .filter(
                        AnnouncementProcessingRAG.folder_name == folder_name,
                        AnnouncementProcessingRAG.site_code == site_code
                    )\
                    .first()
                
                return result is not None
                
        except Exception as e:
            logger.error(f"RAG 폴더 처리 상태 확인 실패: {e}")
            return False  # 에러 시 미처리로 간주하여 다시 처리하도록 함
    
    def get_rag_statistics(self) -> Dict[str, Any]:
        """RAG 시스템 통계를 가져옵니다."""
        try:
            stats = {}
            
            # MySQL 통계
            with self.SessionLocal() as session:
                total_count = session.query(AnnouncementProcessingRAG).count()
                completed_count = session.query(AnnouncementProcessingRAG)\
                    .filter(AnnouncementProcessingRAG.processing_status == 'completed').count()
                failed_count = session.query(AnnouncementProcessingRAG)\
                    .filter(AnnouncementProcessingRAG.processing_status == 'failed').count()
                
                stats['mysql'] = {
                    'total_announcements': total_count,
                    'completed': completed_count,
                    'failed': failed_count,
                    'success_rate': (completed_count / total_count * 100) if total_count > 0 else 0
                }
            
            # ChromaDB 통계
            if self.rag_analyzer:
                chroma_stats = self.rag_analyzer.ollama_client.chromadb_manager.get_collection_stats()
                stats['chromadb'] = chroma_stats
            else:
                stats['chromadb'] = {'error': 'RAG analyzer not initialized'}
            
            return stats
            
        except Exception as e:
            logger.error(f"RAG 통계 조회 실패: {e}")
            return {'error': str(e)}


def create_announcement_tables():
    """RAG 공고 처리용 테이블을 생성합니다."""
    try:
        db_manager = AnnouncementDatabaseManagerRAG()
        if db_manager.test_connection():
            db_manager.create_tables()
            logger.info("RAG 공고 처리용 테이블 생성 완료")
            return True
        else:
            logger.error("RAG 데이터베이스 연결 실패로 테이블 생성 불가")
            return False
    except Exception as e:
        logger.error(f"RAG 테이블 생성 중 오류: {e}")
        return False


if __name__ == "__main__":
    # 테스트
    try:
        # 테이블 생성 테스트
        create_announcement_tables()
        
        # 연결 테스트
        db_manager = AnnouncementDatabaseManagerRAG()
        if db_manager.test_connection():
            print("RAG 데이터베이스 연결 및 테이블 생성 성공!")
            
            # 통계 출력
            stats = db_manager.get_rag_statistics()
            print(f"RAG 시스템 통계: {json.dumps(stats, ensure_ascii=False, indent=2)}")
        else:
            print("RAG 데이터베이스 연결 실패")
            
    except Exception as e:
        print(f"RAG 테스트 중 오류: {e}")