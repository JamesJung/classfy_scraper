
from pydantic import BaseModel, Field


class ReceptionInstitute(BaseModel):
    RCPT_INST_CD: str | None = Field(
        description="공고를 소관, 접수, 관리하는 기관의 코드 (varchar(7))", default=None
    )
    RCPT_INST_NM: str | None = Field(
        description="공고를 소관, 접수, 관리하는 기관의 이름 (varchar(100))",
        default=None,
    )


class SpotDetail(BaseModel):
    SPOT_TYP_DV_CD: str | None = Field(
        description="사업 지원분야 구분코드 (varchar(2))", default=None
    )
    SPOT_CONTS: str | None = Field(
        description="사업 대상에게 지원되는 내용 (longtext)", default=None
    )


class ApplicationMethod(BaseModel):
    APL_MTHD_CD: str | None = Field(
        description="사업 신청방법 코드 (varchar(2))", default=None
    )
    APL_MTHD_CONTS: str | None = Field(
        description="사업 신청방법 내용 (longtext)", default=None
    )


class AttachedFile(BaseModel):
    FILE_NM: str | None = Field(
        description="공고 첨부 파일명 (varchar(1000))", default=None
    )
    FILE_ADDR: str | None = Field(
        description="공고 첨부파일 주소 (varchar(2048))", default=None
    )


class PreferenceRestriction(BaseModel):
    PRF_RSTR_DV_CD: str | None = Field(
        description="심사시 우대되거나 제한되는 대상의 구분코드 (varchar(1))",
        default=None,
    )
    PRF_RSTR_CONTS: str | None = Field(
        description="심사시 우대되거나 제한되는 대상의 내용 (longtext)", default=None
    )


class JsonExtractionFormat(BaseModel):
    ANNC_NO: str | None = Field(description="공고번호 (varchar(100))", default=None)
    SBVT_TITLE: str | None = Field(
        description="정책지원금 사업 공고의 제목 (varchar(300))", default=None
    )
    RCPT_INST: list[ReceptionInstitute] | None = Field(
        description="접수기관 정보 (각 항목: RCPT_INST_CD(varchar(7)), RCPT_INST_NM(varchar(100)))",
        default=None,
    )
    RCPT_INST_CTGR_CD: str | None = Field(
        description="공고 소관기관의 유형코드 (varchar(5))", default=None
    )
    RSPS_DVSN_NM: str | None = Field(
        description="공고 소관기관의 담당부서명 (varchar(300))", default=None
    )
    RSPS_DVSN_TEL_NO: str | None = Field(
        description="공고 소관기관의 담당부서 전화번호 (varchar(20))", default=None
    )
    APL_STRT_DT: str | None = Field(
        description="공고 접수가 시작되는 날짜 (varchar(8))", default=None
    )
    APL_END_DT: str | None = Field(
        description="공고 접수가 종료되는 날짜 (varchar(8))", default=None
    )
    APL_DDLN_CONTS: str | None = Field(
        description="공고 기한(시작시기와 종료시기 중 하나가 없음) + 조건적 예외 규정 포함 (longtext)",
        default=None,
    )
    CNTC_DVSN_CONTS: str | None = Field(
        description="담당 문의처 관련 내용 (longtext)", default=None
    )
    BIZ_OVRVW_CONTS: str | None = Field(
        description="사업개요내용 (longtext)", default=None
    )
    SPOT_TRG_DV_CD: list[str] | None = Field(
        description="지원 대상에 대한 구분코드 배열 (각 항목: varchar(2))", default=None
    )
    SPOT_TRG_STRTUP_DV_CD: list[int] | None = Field(
        description="지원 대상의 사업 주기별 창업구분코드 배열 (각 항목: int)",
        default=None,
    )
    SPOT_TRG_AREA_CD: list[str] | None = Field(
        description="지원 대상의 지역코드 배열 (각 항목: varchar(5))", default=None
    )
    SPOT_TRG_AREA_NM: list[str] | None = Field(
        description="지원 대상의 지역명 배열 (각 항목: varchar(100))", default=None
    )
    REQRD_BUDG_AMT: str | None = Field(
        description="사업에 소요되는 예산금액(지원금액의 총계) (bigint(20))",
        default=None,
    )
    SPOT_AMT: str | None = Field(
        description="개별 업체에 지원되는 금액 중 최대 금액 (bigint(20))", default=None
    )
    SPOT_CONTS: str | None = Field(
        description="지원내용 - 정부가 제공하는 모든 지원사항 (longtext)", default=None
    )
    SELCT_SCLE_CONTS: str | None = Field(
        description="선정규모내용(선정 수량, 유형 배분, 비율 등) (varchar(500))",
        default=None,
    )
    SPOT_QULFT_CONTS: str | None = Field(
        description="지원자격내용 (longtext)", default=None
    )
    SUBM_DOC_CONTS: str | None = Field(
        description="신청에 필요한 제출서류의 내용 (longtext)", default=None
    )
    SLT_PRSD_EVAL_CONTS: str | None = Field(
        description="지원 선정 절차와 각 절차의 심사, 평가 내용 (longtext)",
        default=None,
    )
    NOTE_CONTS: str | None = Field(
        description="유의사항내용 (longtext)", default=None
    )
    BIZ_REAS_LAW_CONTS: str | None = Field(
        description="사업근거법내용 (longtext)", default=None
    )
    ANNC_URL_ADDR: list[str] | None = Field(
        description="공고의 URL주소 (각 항목: varchar(300))", default=None
    )
    DETL_PAGE_URL_ADDR: list[str] | None = Field(
        description="공고와 연결되는 상세페이지의 URL주소 (각 항목: varchar(300))",
        default=None,
    )
    ANNC_DT: str | None = Field(
        description="공고 고시 일자 (varchar(8))", default=None
    )
    ANNC_HIT_CNT: str | None = Field(
        description="공고 조회수 (int(11))", default=None
    )
    FST_REG_DT: str | None = Field(
        description="공고 최초등록일시 (datetime)", default=None
    )
    LST_UPD_DT: str | None = Field(
        description="공고 최종수정일시 (datetime)", default=None
    )
    APL_METHODS: list[ApplicationMethod] | None = Field(
        description="사업 신청방법 상세 (각 항목: APL_MTHD_CD(varchar(2)), APL_MTHD_CONTS(longtext))",
        default=None,
    )
    FILES: list[AttachedFile] | None = Field(
        description="공고 첨부파일 목록 (각 항목: FILE_NM(varchar(1000)), FILE_ADDR(varchar(2048)))",
        default=None,
    )
    PRF_RSTR_DETAILS: list[PreferenceRestriction] | None = Field(
        description="우대 또는 제한 상세 (각 항목: PRF_RSTR_DV_CD(varchar(1)), PRF_RSTR_CONTS(longtext))",
        default=None,
    )
    PRF_DTL_DV_CD: list[str] | None = Field(
        description="우대제한세부구분코드 배열 (각 항목: varchar(2))", default=None
    )
    INDST_CD: list[str] | None = Field(
        description="사업이나 산업을 구분하기 위한 국세청 업종코드 (각 항목: varchar(2))",
        default=None,
    )


class ClassificationInfo(BaseModel):
    primary_classification: str | None = Field(
        description="주요 분류 (소상공인, 중소기업, 창업, 사회적기업, 농촌, 여성, 기타)", 
        default=None
    )
    classification_types: list[str] | None = Field(
        description="해당하는 모든 분류 목록", 
        default=None
    )
    detected_keywords: list[str] | None = Field(
        description="분류 결정에 사용된 지원대상, 모집분야, 지원내용 관련 핵심 키워드들", 
        default=None
    )
