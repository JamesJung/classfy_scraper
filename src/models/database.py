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
        logger = setup_logging().getChild(__name__)
        logger.warning(f"JSON 역직렬화 실패, None으로 처리: '{x[:200]}{'...' if len(x) > 200 else ''}' - {str(e)}")
        return None

from sqlalchemy import (
    JSON as SQLAlchemy_JSON,
)
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    create_engine,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from src.config.config import ConfigManager
from src.config.logConfig import setup_logging

"""
# 테이블 정보
1. SUBVENTION_MASTER (정책지원금기본)
   - PK: SBVT_ID

2. SUBVENTION_APPLICATION_DETAIL (정책지원금신청내역)
   - PK: SBVT_ID (단일키, APL_SNO 제거됨)
   - FK: SBVT_ID -> SUBVENTION_MASTER.SBVT_ID (CASCADE)
   - APL_MTHD_CD는 JSON 배열로 변경됨 (여러 신청방법 코드 저장)

3. SUBVENTION_FILE_LIST (정책지원금첨부파일목록)
   - PK: SBVT_ID, FILE_SNO (복합키)
   - FK: SBVT_ID -> SUBVENTION_MASTER.SBVT_ID (CASCADE)

4. SUBVENTION_PREFERENTIAL_RESTRICTION_DETAIL (정책지원금우대제한내역)
   - PK: SBVT_ID, PRF_RSTR_DV_CD, PRF_RSTR_SNO (복합키)
   - FK: SBVT_ID -> SUBVENTION_MASTER.SBVT_ID (CASCADE)

5. SUBVENTION_SUPPORTING_TYPE_DETAIL (정책지원금지원분야내역)
   - PK: SBVT_ID, SPOT_TYP_SNO (복합키)
   - FK: SBVT_ID -> SUBVENTION_MASTER.SBVT_ID (CASCADE)

6. SUBVENTION_SUPPORTING_INDUSTRY_DETAIL (정책지원금지원업종내역)
   - PK: SBVT_ID, SPOT_INDST_SNO (복합키)
   - FK: SBVT_ID -> SUBVENTION_MASTER.SBVT_ID (CASCADE)

7. SUBVENTION_ANNOUNCEMENT_NO_DETAIL (정책지원금공고번호내역)
   - PK: SBVT_ID, ANNC_SNO (복합키)
   - FK: SBVT_ID -> SUBVENTION_MASTER.SBVT_ID (CASCADE)

8. INSTITUTION_MASTER (소관기관마스터)
   - PK: INST_CD
   - 소관기관코드와 관련 정보를 저장하는 마스터 테이블
"""

# 로깅 설정
logger = setup_logging(__name__)


# 한글 지원 JSON 타입 정의
class KoreanJSON(TypeDecorator):
    """한글을 유니코드 이스케이프 없이 저장하는 JSON 타입"""

    impl = SQLAlchemy_JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        # Python 객체를 그대로 반환하여 SQLAlchemy가 처리하도록 함
        # MySQL JSON 타입이 UTF-8로 저장하므로 한글 유지됨
        return value

    def process_result_value(self, value, dialect):
        # MySQL JSON 타입에서 이미 파싱된 Python 객체를 그대로 반환
        return value


# NULL 처리 JSON 타입 정의
class NullableJSON(TypeDecorator):
    """Python None을 데이터베이스 NULL로 저장하는 JSON 타입"""

    impl = Text  # SQLAlchemy_JSON 대신 Text 사용하여 직접 제어
    cache_ok = True

    def process_bind_param(self, value, dialect):
        # Python None을 데이터베이스 NULL로 저장
        if value is None:
            return None
        # 빈 리스트도 None으로 처리
        if isinstance(value, list) and len(value) == 0:
            return None
        # 리스트를 JSON 문자열로 변환
        if isinstance(value, list):
            import json

            return json.dumps(value, ensure_ascii=False)
        return value

    def process_result_value(self, value, dialect):
        # 데이터베이스 NULL을 Python None으로 반환
        if value is None:
            return None
        # JSON 문자열을 리스트로 변환
        if isinstance(value, str):
            try:
                import json

                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return None
        return value


# Database type compatibility functions
def get_varchar_type(length):
    """MySQL/SQLite 호환 VARCHAR 타입"""
    return String(length)  # SQLite 호환을 위해 String 사용


def get_text_type():
    """MySQL/SQLite 호환 TEXT 타입"""
    return Text


def get_json_type():
    """MySQL/SQLite 호환 JSON 타입"""
    return SQLAlchemy_JSON


# 설정 로드

config = ConfigManager().get_config()
db_config = config["database"]

# SQLite Database connection (fallback when MySQL is not available)
import os

db_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "subvention.db"
)
DATABASE_URL = f"sqlite:///{db_path}"

# Try MySQL first, fallback to SQLite
try:
    mysql_url = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['name']}?charset=utf8mb4&autocommit=true&connect_timeout=60&read_timeout=60&write_timeout=60"
    engine = create_engine(
        mysql_url,
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
    logger.info("MySQL 엔진 생성 성공")
except Exception as e:
    logger.warning(f"MySQL 연결 실패, SQLite로 전환: {e}")
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
        json_deserializer=safe_json_loads,
    )

# CREATE DATABASE subvention
#   DEFAULT CHARACTER SET utf8mb4
#   DEFAULT COLLATE utf8mb4_unicode_ci;

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# SQLAlchemy 2.0 기본 클래스
class Base(DeclarativeBase):
    pass


# 테이블 모델 정의
class SubventionMasterTable(Base):
    __tablename__ = "SUBVENTION_MASTER"
    __table_args__ = {"comment": "정책지원금기본"}

    SBVT_ID: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="정책지원금ID"
    )
    ANNC_NO: Mapped[str] = mapped_column(String(100), comment="공고번호")
    SBVT_TITLE: Mapped[str] = mapped_column(String(300), comment="정책지원금제목")
    RCPT_INST_CD: Mapped[str] = mapped_column(
        String(7), default="UNKN01", comment="소관기관코드"
    )
    RCPT_INST_NM: Mapped[str] = mapped_column(
        String(100), default="", comment="소관기관명"
    )
    RCPT_INST_CTGR_CD: Mapped[str] = mapped_column(
        String(5), default="ETC06", comment="소관기관유형코드"
    )
    RSPS_DVSN_NM: Mapped[str] = mapped_column(
        String(300), default="정보없음", comment="담당부서명"
    )
    RSPS_DVSN_TEL_NO: Mapped[str] = mapped_column(
        String(20), default="", comment="담당부서전화번호"
    )
    APL_STRT_DT: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="신청시작일"
    )
    APL_END_DT: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="신청종료일"
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
        SQLAlchemy_JSON, default=list, comment="지원대상구분코드(배열)"
    )
    SPOT_TRG_STRTUP_DV_CD: Mapped[list[int]] = mapped_column(
        SQLAlchemy_JSON, default=list, comment="지원대상창업구분코드(배열)"
    )
    SPOT_TRG_AREA_CD: Mapped[list[str]] = mapped_column(
        SQLAlchemy_JSON, default=list, comment="지원대상지역코드(배열)"
    )
    SPOT_TRG_AREA_NM: Mapped[list[str]] = mapped_column(
        SQLAlchemy_JSON, default=list, comment="지원대상지역명(배열)"
    )
    REQRD_BUDG_AMT: Mapped[int] = mapped_column(
        Integer, default=0, comment="소요예산금액"
    )
    SPOT_AMT: Mapped[int] = mapped_column(Integer, default=0, comment="지원금액")
    SELCT_SCLE_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="선정규모내용"
    )
    SPOT_CONTS: Mapped[str] = mapped_column(LONGTEXT, default="", comment="지원내용")
    SPOT_TYP_DV_CD: Mapped[list[str]] = mapped_column(
        SQLAlchemy_JSON, default=list, comment="지원분야구분코드(배열)"
    )
    SPOT_QULFT_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="지원자격내용"
    )
    PRF_DTL_DV_CD: Mapped[list[str] | None] = mapped_column(
        NullableJSON, nullable=True, comment="우대제한세부구분코드(배열)"
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
        String(300), default="", comment="공고URL주소"
    )
    DETL_PAGE_URL_ADDR: Mapped[str] = mapped_column(
        String(300), default="", comment="상세페이지URL주소"
    )
    ANNC_DT: Mapped[str] = mapped_column(String(8), default="", comment="공고일자")
    ANNC_HIT_CNT: Mapped[int] = mapped_column(Integer, default=0, comment="공고조회수")
    FST_REG_DT: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="최초등록일시"
    )
    LST_UPD_DT: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="최종변경일시"
    )
    SITE_CODE: Mapped[str] = mapped_column(String(50), comment="사이트코드")
    FOLDER_TYPE: Mapped[str] = mapped_column(
        String(10),
        default="TITLE",
        comment="폴더타입(TITLE:공고제목, POST_NO:게시물번호)",
    )
    FOLDER_NAME: Mapped[str] = mapped_column(
        String(300), default="", comment="원본폴더명"
    )
    EXTRACTED_TEXT: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="추출된텍스트내용"
    )
    
    # 비활성화 관련 컬럼들
    IS_ACTIVE: Mapped[bool] = mapped_column(
        default=True, comment="활성화 여부"
    )
    DEACTIVATION_REASON: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="비활성화 사유"
    )
    DEACTIVATED_AT: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="비활성화 일시"
    )
    DEACTIVATED_BY: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="비활성화 담당자"
    )

    # 관계 정의
    subvention_application_detail: Mapped["SubventionApplicationDetailTable"] = (
        relationship(back_populates="subvention_master", uselist=False)
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


class SubventionApplicationDetailTable(Base):
    __tablename__ = "SUBVENTION_APPLICATION_DETAIL"
    __table_args__ = {"comment": "정책지원금신청내역"}

    SBVT_ID: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )
    APL_MTHD_CD: Mapped[list[str]] = mapped_column(
        SQLAlchemy_JSON, default=list, comment="신청방법코드(JSON배열)"
    )
    APL_MTHD_CONTS: Mapped[str] = mapped_column(
        LONGTEXT, default="", comment="신청방법내용(통합)"
    )
    FST_REG_DT: Mapped[datetime] = mapped_column(DateTime, comment="최초등록일시")
    LST_UPD_DT: Mapped[datetime] = mapped_column(DateTime, comment="최종변경일시")

    # 관계 설정
    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_application_detail"
    )


class SubventionFileListTable(Base):
    __tablename__ = "SUBVENTION_FILE_LIST"
    __table_args__ = {"comment": "정책지원금첨부파일목록"}

    SBVT_ID: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )
    FILE_SNO: Mapped[int] = mapped_column(
        Integer, primary_key=True, comment="파일일련번호"
    )
    FILE_NM: Mapped[str] = mapped_column(String(1000), comment="파일명")
    FILE_ADDR: Mapped[str] = mapped_column(String(2048), comment="파일주소")
    FST_REG_DT: Mapped[datetime] = mapped_column(DateTime, comment="최초등록일시")
    LST_UPD_DT: Mapped[datetime] = mapped_column(DateTime, comment="최종변경일시")

    # 관계 설정
    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_file_lists"
    )


class SubventionPreferentialRestrictionDetailTable(Base):
    __tablename__ = "SUBVENTION_PREFERENTIAL_RESTRICTION_DETAIL"
    __table_args__ = {"comment": "정책지원금우대제한내역"}

    SBVT_ID: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )
    PRF_RSTR_DV_CD: Mapped[str] = mapped_column(
        String(1), primary_key=True, comment="우대제한구분코드"
    )
    PRF_RSTR_SNO: Mapped[int] = mapped_column(
        Integer, primary_key=True, comment="우대제한일련번호"
    )
    PRF_RSTR_CONTS: Mapped[str] = mapped_column(LONGTEXT, comment="우대제한내용")
    PRF_DTL_DV_CD: Mapped[list[str] | None] = mapped_column(
        NullableJSON, nullable=True, comment="우대제한세부구분코드(배열)"
    )
    FST_REG_DT: Mapped[datetime] = mapped_column(DateTime, comment="최초등록일시")
    LST_UPD_DT: Mapped[datetime] = mapped_column(DateTime, comment="최종변경일시")

    # 관계 설정
    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_preferential_restriction_details"
    )


class SubventionSupportingTypeDetailTable(Base):
    __tablename__ = "SUBVENTION_SUPPORTING_TYPE_DETAIL"
    __table_args__ = {"comment": "정책지원금지원분야내역"}

    SBVT_ID: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )
    SPOT_TYP_SNO: Mapped[int] = mapped_column(
        Integer, primary_key=True, comment="지원분야일련번호"
    )
    SPOT_TYP_DV_CD: Mapped[str] = mapped_column(String(2), comment="지원분야구분코드")
    SPOT_CONTS: Mapped[str] = mapped_column(LONGTEXT, comment="지원내용")
    FST_REG_DT: Mapped[datetime] = mapped_column(DateTime, comment="최초등록일시")
    LST_UPD_DT: Mapped[datetime] = mapped_column(DateTime, comment="최종변경일시")

    # 관계 설정
    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_supporting_type_details"
    )


class SubventionSupportingIndustryDetailTable(Base):
    __tablename__ = "SUBVENTION_SUPPORTING_INDUSTRY_DETAIL"
    __table_args__ = {"comment": "정책지원금지원업종내역"}

    SBVT_ID: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )
    SPOT_INDST_SNO: Mapped[int] = mapped_column(
        Integer, primary_key=True, comment="지원업종일련번호"
    )
    INDST_CD: Mapped[list[str] | None] = mapped_column(
        SQLAlchemy_JSON, nullable=True, default=None, comment="업종코드(JSON배열)"
    )
    BIZ_TYPE_CD: Mapped[list[str] | None] = mapped_column(
        SQLAlchemy_JSON, nullable=True, default=None, comment="사업유형코드(JSON배열)"
    )
    FST_REG_DT: Mapped[datetime] = mapped_column(DateTime, comment="최초등록일시")
    LST_UPD_DT: Mapped[datetime] = mapped_column(DateTime, comment="최종변경일시")

    # 관계 설정
    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_supporting_industry_details"
    )


class SubventionAnnouncementNoDetailTable(Base):
    __tablename__ = "SUBVENTION_ANNOUNCEMENT_NO_DETAIL"
    __table_args__ = {"comment": "정책지원금공고번호내역"}

    SBVT_ID: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("SUBVENTION_MASTER.SBVT_ID", ondelete="CASCADE"),
        primary_key=True,
        comment="정책지원금ID",
    )
    ANNC_SNO: Mapped[int] = mapped_column(
        Integer, primary_key=True, comment="공고일련번호"
    )
    RCPT_INST_CD: Mapped[str] = mapped_column(String(20), comment="소관기관코드")
    RCPT_INST_NM: Mapped[str] = mapped_column(String(200), comment="소관기관명")
    ANNC_NO: Mapped[str] = mapped_column(String(100), comment="공고번호")
    FST_REG_DT: Mapped[datetime] = mapped_column(DateTime, comment="최초등록일시")
    LST_UPD_DT: Mapped[datetime] = mapped_column(DateTime, comment="최종변경일시")

    # 관계 설정
    subvention_master: Mapped["SubventionMasterTable"] = relationship(
        back_populates="subvention_announcement_no_details"
    )


class FileProcessingStatusTable(Base):
    __tablename__ = "FILE_PROCESSING_STATUS"
    __table_args__ = {"comment": "파일 처리 상태 관리"}

    # 기본 키
    PROC_ID: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="처리 ID (자동 증가)"
    )

    # 파일 정보
    FILE_PATH: Mapped[str] = mapped_column(
        String(1000), nullable=False, comment="파일 전체 경로 (재처리용)"
    )
    FILE_NAME: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="파일명"
    )
    SITE_CODE: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="사이트 코드"
    )

    # 처리 상태
    PROCESS_STATUS: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        comment="처리 상태 (PENDING/PROCESSING/SUCCESS/FAILED)",
    )

    # 처리 결과
    DB_SAVE_SUCCESS: Mapped[str] = mapped_column(
        String(1), nullable=False, default="N", comment="DB 저장 성공 여부 (Y/N)"
    )
    SBVT_ID: Mapped[int] = mapped_column(
        Integer, nullable=True, comment="저장된 지원금 ID (성공시)"
    )

    # 실패 정보
    FAILURE_REASON: Mapped[str] = mapped_column(
        LONGTEXT, nullable=True, comment="DB 저장 실패 사유 상세"
    )
    FAILURE_CATEGORY: Mapped[str] = mapped_column(
        String(100),
        nullable=True,
        comment="실패 카테고리 (PARSING_ERROR, DB_ERROR, VALIDATION_ERROR 등)",
    )
    ERROR_STACK: Mapped[str] = mapped_column(
        LONGTEXT, nullable=True, comment="오류 스택 트레이스"
    )

    # 처리 시간
    PROCESS_START_TIME: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, comment="처리 시작 시간"
    )
    PROCESS_END_TIME: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, comment="처리 완료 시간"
    )
    PROCESS_DURATION_SEC: Mapped[int] = mapped_column(
        Integer, nullable=True, comment="처리 소요 시간(초)"
    )

    # 파일 메타데이터
    FILE_SIZE: Mapped[int] = mapped_column(
        Integer, nullable=True, comment="파일 크기(바이트)"
    )
    FILE_MODIFIED_TIME: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, comment="파일 수정 시간"
    )

    # 재처리 정보
    RETRY_COUNT: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="재처리 횟수"
    )
    LAST_RETRY_TIME: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, comment="마지막 재처리 시간"
    )

    # 시스템 정보
    FST_REG_DT: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, comment="최초 등록일시"
    )
    LST_UPD_DT: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        comment="최종 수정일시",
    )


# Create all tables
def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("데이터베이스 테이블이 생성되었습니다.")
    except DBAPIError as e:
        logger.error(f"데이터베이스 테이블 생성 중 오류 발생: {str(e)}")
        sys.exit(1)
    except SQLAlchemyError as e:
        logger.error(f"데이터베이스 테이블 생성 중 오류 발생: {str(e)}")
        sys.exit(1)
        raise


class InstitutionMaster(Base):
    """소관기관마스터 테이블"""

    __tablename__ = "INSTITUTION_MASTER"

    INST_CD: Mapped[str] = mapped_column(
        String(20), primary_key=True, comment="소관기관코드"
    )
    INST_NM: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="소관기관명"
    )
    INST_CTGR_CD: Mapped[str] = mapped_column(
        String(10), nullable=True, comment="소관기관유형코드"
    )
    INST_CTGR_NM: Mapped[str] = mapped_column(
        String(100), nullable=True, comment="소관기관유형명"
    )
    USE_YN: Mapped[str] = mapped_column(String(1), default="Y", comment="사용여부")
    REG_DT: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="등록일시"
    )
    UPD_DT: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="수정일시"
    )


class AnnouncementClassificationTable(Base):
    """공고 분류 정보 테이블"""
    
    __tablename__ = "ANNOUNCEMENT_CLASSIFICATION"
    
    CLASSIFICATION_ID: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="분류ID"
    )
    SITE_CODE: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="사이트코드"
    )
    FOLDER_NAME: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="폴더명"
    )
    CLASSIFICATION_TYPE: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="분류타입"
    )
    CLASSIFICATION_TYPES: Mapped[list[str] | None] = mapped_column(
        SQLAlchemy_JSON, nullable=True, comment="전체 분류 목록(서브 분류들)"
    )
    CLASSIFICATION_SCORES: Mapped[dict | None] = mapped_column(
        SQLAlchemy_JSON, nullable=True, comment="각 분류별 점수"
    )
    CLASSIFICATION_DETAILS: Mapped[dict | None] = mapped_column(
        SQLAlchemy_JSON, nullable=True, comment="분류별 상세 정보"
    )
    CONFIDENCE_SCORE: Mapped[int] = mapped_column(
        Integer, default=0, comment="신뢰도 점수"
    )
    MATCHED_KEYWORDS: Mapped[str] = mapped_column(
        Text, default="", comment="매칭된 키워드"
    )
    INDUSTRY_KEYWORDS: Mapped[str] = mapped_column(
        Text, default="", comment="업종 키워드"
    )
    
    # LLM 분류 정보 컬럼들
    LLM_CLASSIFICATION_TYPE: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="LLM 대표 분류"
    )
    LLM_CLASSIFICATION_TYPES: Mapped[list[str] | None] = mapped_column(
        SQLAlchemy_JSON, nullable=True, comment="LLM 전체 분류 목록"
    )
    LLM_CLASSIFICATION_SCORES: Mapped[dict | None] = mapped_column(
        SQLAlchemy_JSON, nullable=True, comment="LLM 각 분류별 점수"
    )
    LLM_DETECTED_KEYWORDS: Mapped[list[str] | None] = mapped_column(
        SQLAlchemy_JSON, nullable=True, comment="LLM 감지 키워드"
    )
    
    # 분류 검증 및 상태 관리 컬럼들
    CLASSIFICATION_VALIDATION_STATUS: Mapped[str] = mapped_column(
        String(20), default="KEYWORD_ONLY", comment="분류 검증 상태"
    )
    IS_CLASSIFICATION_MISMATCH: Mapped[bool] = mapped_column(
        default=False, comment="키워드-LLM 분류 불일치 여부"
    )
    MISMATCH_DETAILS: Mapped[dict | None] = mapped_column(
        SQLAlchemy_JSON, nullable=True, comment="불일치 상세 정보"
    )
    
    IS_PROCESSED: Mapped[bool] = mapped_column(
        default=False, comment="처리 여부"
    )
    SBVT_ID: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="SubventionMaster SBVT_ID"
    )
    CREATED_AT: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="생성일시"
    )
    LAST_UPDATED: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="최종 수정일시"
    )
