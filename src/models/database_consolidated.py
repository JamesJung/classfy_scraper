"""
통합된 APPLICATION_DETAIL 테이블을 위한 SQLAlchemy 모델
마이그레이션 후 사용할 새로운 모델 정의
"""

import json
import sys
from datetime import datetime


def safe_json_loads(x):
    """
    안전한 JSON 역직렬화 함수
    빈 값, null, 잘못된 JSON 등을 처리
    """
    # 이미 리스트나 딕셔너리인 경우 그대로 반환 (배열→문자열 변환 문제 해결)
    if isinstance(x, (list, dict)):
        return x
        
    if not x:
        return None
    
    # 문자열 타입이 아닌 경우 None 반환
    if not isinstance(x, str):
        return None
    
    # 공백 제거 후 빈 문자열이면 None 반환
    x_stripped = x.strip()
    if not x_stripped:
        return None
    
    # 명시적으로 null 문자열인 경우
    if x_stripped.lower() in ('null', 'none', ''):
        return None
    
    try:
        return json.loads(x_stripped)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        # JSON 파싱 실패 시 로그 남기고 None 반환
        from src.config.logConfig import setup_logging
        logger = setup_logging().getChild(__name__)
        logger.warning(f"JSON 역직렬화 실패, None으로 처리: '{x[:200]}{"..." if len(x) > 200 else ""}' - {str(e)}")
        return None

from sqlalchemy import (
    BIGINT,
    DateTime,
    ForeignKey,
    TypeDecorator,
    create_engine,
)
from sqlalchemy.dialects.mysql import INTEGER, JSON, LONGTEXT, VARCHAR
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.sql import func

from src.config.config import ConfigManager
from src.config.logConfig import setup_logging

logger = setup_logging(__name__)


# 한글 지원 JSON 타입 정의
class KoreanJSON(TypeDecorator):
    """한글을 유니코드 이스케이프 없이 저장하는 JSON 타입"""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return value

    def process_result_value(self, value, dialect):
        return value


# 설정 로드
config = ConfigManager().get_config()
db_config = config["database"]

# Database connection URL with UTF-8 charset for Korean support
DATABASE_URL = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['name']}?charset=utf8mb4&autocommit=true&connect_timeout=60&read_timeout=60&write_timeout=60"

# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_timeout=60,
    pool_recycle=1800,
    pool_pre_ping=True,
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
    json_deserializer=safe_json_loads,
    connect_args={
        "autocommit": True
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# SQLAlchemy 2.0 기본 클래스
class Base(DeclarativeBase):
    pass


# 기존 테이블들은 동일하게 유지
class SubventionMasterTable(Base):
    __tablename__ = "SUBVENTION_MASTER"
    __table_args__ = {"comment": "정책지원금기본"}

    SBVT_ID: Mapped[int] = mapped_column(
        INTEGER(20), primary_key=True, autoincrement=True, comment="정책지원금ID"
    )
    ANNC_NO: Mapped[str] = mapped_column(VARCHAR(100), comment="공고번호")
    SBVT_TITLE: Mapped[str] = mapped_column(VARCHAR(300), comment="정책지원금제목")
    RCPT_INST_CD: Mapped[str] = mapped_column(
        VARCHAR(7), default="", comment="소관기관코드"
    )
    RCPT_INST_NM: Mapped[str] = mapped_column(
        VARCHAR(100), default="", comment="소관기관명"
    )
    RCPT_INST_CTGR_CD: Mapped[str] = mapped_column(
        VARCHAR(5), default="ETC06", comment="소관기관유형코드"
    )
    RSPS_DVSN_NM: Mapped[str] = mapped_column(
        VARCHAR(300), default="정보없음", comment="담당부서명"
    )
    RSPS_DVSN_TEL_NO: Mapped[str] = mapped_column(
        VARCHAR(20), default="", comment="담당부서전화번호"
    )
    APL_STRT_DT: Mapped[str | None] = mapped_column(
        VARCHAR(8), nullable=True, comment="신청시작일"
    )
    APL_END_DT: Mapped[str | None] = mapped_column(
        VARCHAR(8), nullable=True, comment="신청종료일"
    )
    APL_DDLN_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="신청기한내용"
    )
    CNTC_DVSN_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="문의처내용"
    )
    BIZ_OVRVW_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="사업개요내용"
    )
    SPOT_TRG_DV_CD: Mapped[list[str]] = mapped_column(
        JSON, default=list, comment="지원대상구분코드(배열)"
    )
    SPOT_TRG_STRTUP_DV_CD: Mapped[list[int]] = mapped_column(
        JSON, default=list, comment="지원대상창업구분코드(배열)"
    )
    SPOT_TRG_AREA_CD: Mapped[list[str]] = mapped_column(
        JSON, default=list, comment="지원대상지역코드(배열)"
    )
    SPOT_TRG_AREA_NM: Mapped[list[str]] = mapped_column(
        KoreanJSON, default=list, comment="지원대상지역명(배열)"
    )
    REQRD_BUDG_AMT: Mapped[int] = mapped_column(
        BIGINT, default=0, comment="소요예산금액"
    )
    SPOT_AMT: Mapped[int] = mapped_column(BIGINT, default=0, comment="지원금액")
    SELCT_SCLE_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="선정규모내용"
    )
    SPOT_CONTS: Mapped[str] = mapped_column(LONGTEXT, default="", comment="지원내용")
    SPOT_TYP_DV_CD: Mapped[list[str]] = mapped_column(
        JSON, default=list, comment="지원분야구분코드(배열)"
    )
    SPOT_QULFT_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="지원자격내용"
    )
    SUBM_DOC_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="제출서류내용"
    )
    SLT_PRSD_EVAL_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="선정절차평가내용"
    )
    NOTE_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="유의사항내용"
    )
    BIZ_REAS_LAW_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="사업근거법령내용"
    )
    ANNC_URL_ADDR: Mapped[str] = mapped_column(
        VARCHAR(300), default="", comment="공고URL주소"
    )
    DETL_PAGE_URL_ADDR: Mapped[str] = mapped_column(
        VARCHAR(300), default="", comment="상세페이지URL주소"
    )
    ANNC_DT: Mapped[str] = mapped_column(VARCHAR(8), default="", comment="공고일자")
    ANNC_HIT_CNT: Mapped[int] = mapped_column(
        INTEGER(11), default=0, comment="공고조회수"
    )
    FST_REG_DT: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), comment="최초등록일시"
    )
    LST_UPD_DT: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), comment="최종변경일시"
    )
    SITE_CODE: Mapped[str] = mapped_column(VARCHAR(200), comment="사이트코드")
    FOLDER_TYPE: Mapped[str] = mapped_column(
        VARCHAR(10),
        default="TITLE",
        comment="폴더타입(TITLE:공고제목, POST_NO:게시물번호)",
    )
    FOLDER_NAME: Mapped[str] = mapped_column(
        VARCHAR(300), default="", comment="원본폴더명"
    )
    EXTRACTED_TEXT: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="추출된텍스트내용"
    )

    # 관계 정의 - 통합된 APPLICATION_DETAIL과 1:1 관계
    subvention_application_detail: Mapped[
        "SubventionApplicationDetailConsolidatedTable"
    ] = relationship(
        back_populates="subvention_master", uselist=False  # 단일 관계로 변경
    )
    subvention_file_lists: Mapped[list["SubventionFileListTable"]] = relationship(
        back_populates="subvention_master"
    )
    subvention_preferential_restriction_details: Mapped[
        list["SubventionPreferentialRestrictionDetailTable"]
    ] = relationship(back_populates="subvention_master")
    subvention_supporting_type_details: Mapped[
        list["SubventionSupportingTypeDetailTable"]
    ] = relationship(back_populates="subvention_master")
    subvention_supporting_industry_details: Mapped[
        list["SubventionSupportingIndustryDetailTable"]
    ] = relationship(back_populates="subvention_master")
    subvention_announcement_no_details: Mapped[
        list["SubventionAnnouncementNoDetailTable"]
    ] = relationship(back_populates="subvention_master")


# 새로운 통합된 APPLICATION_DETAIL 테이블
class SubventionApplicationDetailConsolidatedTable(Base):
    """통합된 정책지원금신청내역 테이블"""

    __tablename__ = "SUBVENTION_APPLICATION_DETAIL"
    __table_args__ = {"comment": "정책지원금신청내역(통합된구조)"}

    # Primary Key는 SBVT_ID만 사용 (APL_SNO 제거)
    SBVT_ID: Mapped[int] = mapped_column(
        INTEGER(20),
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )

    # 신청방법코드를 JSON 배열로 저장
    APL_MTHD_CD: Mapped[list[str]] = mapped_column(
        JSON, default=list, comment='신청방법코드(배열) - 예: ["01", "02"]'
    )

    # 통합된 신청방법내용
    APL_MTHD_CONTS: Mapped[str] = mapped_column(
        LONGTEXT,
        default="",
        comment="신청방법내용(통합) - 여러 방법의 내용을 구조화하여 저장",
    )

    # 통합 메타데이터
    CONSOLIDATED_FROM_ROWS: Mapped[int] = mapped_column(
        INTEGER(3),
        default=1,
        comment="통합된 원본 행 수 - 통합 전 몇 개의 행이었는지 기록",
    )

    # 기본 타임스탬프
    FST_REG_DT: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        comment="최초등록일시 - 통합된 행 중 가장 빠른 등록일시",
    )
    LST_UPD_DT: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), comment="최종변경일시"
    )

    # 관계 설정 - MASTER와 1:1 관계
    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_application_detail"
    )

    # 편의 메서드들
    def get_method_codes_list(self) -> list[str]:
        """신청방법코드 리스트를 반환합니다."""
        if self.APL_MTHD_CD is None:
            return []
        return self.APL_MTHD_CD if isinstance(self.APL_MTHD_CD, list) else []

    def get_method_codes_string(self, separator: str = ", ") -> str:
        """신청방법코드를 문자열로 반환합니다."""
        codes = self.get_method_codes_list()
        return separator.join(codes) if codes else ""

    def has_multiple_methods(self) -> bool:
        """여러 신청방법이 있는지 확인합니다."""
        return len(self.get_method_codes_list()) > 1

    def is_consolidated(self) -> bool:
        """통합된 데이터인지 확인합니다."""
        return self.CONSOLIDATED_FROM_ROWS > 1

    def to_dict(self) -> dict:
        """딕셔너리로 변환합니다."""
        return {
            "SBVT_ID": self.SBVT_ID,
            "APL_MTHD_CD": self.get_method_codes_list(),
            "APL_MTHD_CONTS": self.APL_MTHD_CONTS,
            "CONSOLIDATED_FROM_ROWS": self.CONSOLIDATED_FROM_ROWS,
            "FST_REG_DT": self.FST_REG_DT.isoformat() if self.FST_REG_DT else None,
            "LST_UPD_DT": self.LST_UPD_DT.isoformat() if self.LST_UPD_DT else None,
            "has_multiple_methods": self.has_multiple_methods(),
            "is_consolidated": self.is_consolidated(),
        }


# 기존 테이블들 (변경사항 없음)
class SubventionFileListTable(Base):
    __tablename__ = "SUBVENTION_FILE_LIST"
    __table_args__ = {"comment": "정책지원금첨부파일목록"}

    SBVT_ID: Mapped[int] = mapped_column(
        INTEGER(20),
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )
    FILE_SNO: Mapped[int] = mapped_column(
        INTEGER(3), primary_key=True, comment="파일일련번호"
    )
    FILE_NM: Mapped[str] = mapped_column(VARCHAR(1000), comment="파일명")
    FILE_ADDR: Mapped[str] = mapped_column(VARCHAR(2048), comment="파일주소")
    FST_REG_DT: Mapped[datetime] = mapped_column(DateTime, comment="최초등록일시")
    LST_UPD_DT: Mapped[datetime] = mapped_column(DateTime, comment="최종변경일시")

    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_file_lists"
    )


class SubventionPreferentialRestrictionDetailTable(Base):
    __tablename__ = "SUBVENTION_PREFERENTIAL_RESTRICTION_DETAIL"
    __table_args__ = {"comment": "정책지원금우대제한내역"}

    SBVT_ID: Mapped[int] = mapped_column(
        INTEGER(20),
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )
    PRF_RSTR_DV_CD: Mapped[str] = mapped_column(
        VARCHAR(1), primary_key=True, comment="우대제한구분코드"
    )
    PRF_RSTR_SNO: Mapped[int] = mapped_column(
        INTEGER(3), primary_key=True, comment="우대제한일련번호"
    )
    PRF_RSTR_CONTS: Mapped[str] = mapped_column(LONGTEXT, comment="우대제한내용")
    FST_REG_DT: Mapped[datetime] = mapped_column(DateTime, comment="최초등록일시")
    LST_UPD_DT: Mapped[datetime] = mapped_column(DateTime, comment="최종변경일시")

    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_preferential_restriction_details"
    )


class SubventionSupportingTypeDetailTable(Base):
    __tablename__ = "SUBVENTION_SUPPORTING_TYPE_DETAIL"
    __table_args__ = {"comment": "정책지원금지원분야내역"}

    SBVT_ID: Mapped[int] = mapped_column(
        INTEGER(20),
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )
    SPOT_TYP_SNO: Mapped[int] = mapped_column(
        INTEGER(3), primary_key=True, comment="지원분야일련번호"
    )
    SPOT_TYP_DV_CD: Mapped[str] = mapped_column(VARCHAR(2), comment="지원분야구분코드")
    SPOT_CONTS: Mapped[str] = mapped_column(LONGTEXT, comment="지원내용")
    FST_REG_DT: Mapped[datetime] = mapped_column(DateTime, comment="최초등록일시")
    LST_UPD_DT: Mapped[datetime] = mapped_column(DateTime, comment="최종변경일시")

    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_supporting_type_details"
    )


class SubventionSupportingIndustryDetailTable(Base):
    __tablename__ = "SUBVENTION_SUPPORTING_INDUSTRY_DETAIL"
    __table_args__ = {"comment": "정책지원금지원업종내역"}

    SBVT_ID: Mapped[int] = mapped_column(
        INTEGER(20),
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )
    SPOT_INDST_SNO: Mapped[int] = mapped_column(
        INTEGER(3), primary_key=True, comment="지원업종일련번호"
    )
    INDST_CD: Mapped[str] = mapped_column(VARCHAR(2), comment="업종코드")
    FST_REG_DT: Mapped[datetime] = mapped_column(DateTime, comment="최초등록일시")
    LST_UPD_DT: Mapped[datetime] = mapped_column(DateTime, comment="최종변경일시")

    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_supporting_industry_details"
    )


class SubventionAnnouncementNoDetailTable(Base):
    __tablename__ = "SUBVENTION_ANNOUNCEMENT_NO_DETAIL"
    __table_args__ = {"comment": "정책지원금공고번호내역"}

    SBVT_ID: Mapped[int] = mapped_column(
        INTEGER(20),
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )
    ANNC_SNO: Mapped[int] = mapped_column(
        INTEGER(3), primary_key=True, comment="공고일련번호"
    )
    RCPT_INST_CD: Mapped[str] = mapped_column(VARCHAR(7), comment="소관기관코드")
    RCPT_INST_NM: Mapped[str] = mapped_column(VARCHAR(100), comment="소관기관명")
    ANNC_NO: Mapped[str] = mapped_column(VARCHAR(100), comment="공고번호")
    FST_REG_DT: Mapped[datetime] = mapped_column(DateTime, comment="최초등록일시")
    LST_UPD_DT: Mapped[datetime] = mapped_column(DateTime, comment="최종변경일시")

    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_announcement_no_details"
    )


class FileProcessingStatusTable(Base):
    __tablename__ = "FILE_PROCESSING_STATUS"
    __table_args__ = {"comment": "파일 처리 상태 관리"}

    PROC_ID: Mapped[int] = mapped_column(
        BIGINT, primary_key=True, autoincrement=True, comment="처리 ID (자동 증가)"
    )
    FILE_PATH: Mapped[str] = mapped_column(
        VARCHAR(1000), nullable=False, comment="파일 전체 경로 (재처리용)"
    )
    FILE_NAME: Mapped[str] = mapped_column(
        VARCHAR(255), nullable=False, comment="파일명"
    )
    SITE_CODE: Mapped[str] = mapped_column(
        VARCHAR(50), nullable=False, comment="사이트 코드"
    )
    PROCESS_STATUS: Mapped[str] = mapped_column(
        VARCHAR(20),
        nullable=False,
        default="PENDING",
        comment="처리 상태 (PENDING/PROCESSING/SUCCESS/FAILED)",
    )
    DB_SAVE_SUCCESS: Mapped[str] = mapped_column(
        VARCHAR(1), nullable=False, default="N", comment="DB 저장 성공 여부 (Y/N)"
    )
    SBVT_ID: Mapped[int] = mapped_column(
        BIGINT, nullable=True, comment="저장된 지원금 ID (성공시)"
    )
    FAILURE_REASON: Mapped[str] = mapped_column(
        LONGTEXT, nullable=True, comment="DB 저장 실패 사유 상세"
    )
    FAILURE_CATEGORY: Mapped[str] = mapped_column(
        VARCHAR(100),
        nullable=True,
        comment="실패 카테고리 (PARSING_ERROR, DB_ERROR, VALIDATION_ERROR 등)",
    )
    ERROR_STACK: Mapped[str] = mapped_column(
        LONGTEXT, nullable=True, comment="오류 스택 트레이스"
    )
    PROCESS_START_TIME: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, comment="처리 시작 시간"
    )
    PROCESS_END_TIME: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, comment="처리 완료 시간"
    )
    PROCESS_DURATION_SEC: Mapped[int] = mapped_column(
        INTEGER, nullable=True, comment="처리 소요 시간(초)"
    )
    FILE_SIZE: Mapped[int] = mapped_column(
        BIGINT, nullable=True, comment="파일 크기(바이트)"
    )
    FILE_MODIFIED_TIME: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, comment="파일 수정 시간"
    )
    RETRY_COUNT: Mapped[int] = mapped_column(
        INTEGER, nullable=False, default=0, comment="재처리 횟수"
    )
    LAST_RETRY_TIME: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, comment="마지막 재처리 시간"
    )
    FST_REG_DT: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="최초 등록일시"
    )
    LST_UPD_DT: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="최종 수정일시",
    )


class InstitutionMaster(Base):
    """소관기관마스터 테이블"""

    __tablename__ = "INSTITUTION_MASTER"

    INST_CD: Mapped[str] = mapped_column(
        VARCHAR(20), primary_key=True, comment="소관기관코드"
    )
    INST_NM: Mapped[str] = mapped_column(
        VARCHAR(200), nullable=False, comment="소관기관명"
    )
    INST_CTGR_CD: Mapped[str] = mapped_column(
        VARCHAR(10), nullable=True, comment="소관기관유형코드"
    )
    INST_CTGR_NM: Mapped[str] = mapped_column(
        VARCHAR(100), nullable=True, comment="소관기관유형명"
    )
    USE_YN: Mapped[str] = mapped_column(VARCHAR(1), default="Y", comment="사용여부")
    REG_DT: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), comment="등록일시"
    )
    UPD_DT: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), comment="수정일시"
    )


# Create all tables
def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("통합된 데이터베이스 테이블이 생성되었습니다.")
    except DBAPIError as e:
        logger.error(f"데이터베이스 테이블 생성 중 오류 발생: {str(e)}")
        sys.exit(1)
    except SQLAlchemyError as e:
        logger.error(f"데이터베이스 테이블 생성 중 오류 발생: {str(e)}")
        sys.exit(1)
        raise


# 편의 함수들
def get_application_detail_with_master(sbvt_id: int) -> dict:
    """MASTER와 APPLICATION_DETAIL 정보를 함께 조회합니다."""
    with SessionLocal() as session:
        try:
            master = (
                session.query(SubventionMasterTable)
                .filter(SubventionMasterTable.SBVT_ID == sbvt_id)
                .first()
            )

            if not master:
                return None

            detail = master.subvention_application_detail

            return {
                "master": {
                    "SBVT_ID": master.SBVT_ID,
                    "SBVT_TITLE": master.SBVT_TITLE,
                    "ANNC_NO": master.ANNC_NO,
                    "RCPT_INST_NM": master.RCPT_INST_NM,
                },
                "application_detail": detail.to_dict() if detail else None,
            }

        except Exception as e:
            logger.error(f"SBVT_ID {sbvt_id} 조회 중 오류: {str(e)}")
            return None


def get_consolidated_statistics() -> dict:
    """통합된 APPLICATION_DETAIL 테이블의 통계를 반환합니다."""
    with SessionLocal() as session:
        try:
            total_count = session.query(
                SubventionApplicationDetailConsolidatedTable
            ).count()
            consolidated_count = (
                session.query(SubventionApplicationDetailConsolidatedTable)
                .filter(
                    SubventionApplicationDetailConsolidatedTable.CONSOLIDATED_FROM_ROWS
                    > 1
                )
                .count()
            )
            multiple_methods_count = (
                session.query(SubventionApplicationDetailConsolidatedTable)
                .filter(
                    func.json_length(
                        SubventionApplicationDetailConsolidatedTable.APL_MTHD_CD
                    )
                    > 1
                )
                .count()
            )

            return {
                "total_application_details": total_count,
                "consolidated_entries": consolidated_count,
                "entries_with_multiple_methods": multiple_methods_count,
                "consolidation_ratio": (
                    (consolidated_count / total_count * 100) if total_count > 0 else 0
                ),
            }

        except Exception as e:
            logger.error(f"통합 통계 조회 중 오류: {str(e)}")
            return {}
