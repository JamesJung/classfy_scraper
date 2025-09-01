"""
통합된 APPLICATION_DETAIL을 위한 Pydantic 스키마
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, validator


# 통합된 APPLICATION_DETAIL 스키마
class SubventionApplicationDetailConsolidatedSchema(BaseModel):
    """통합된 정책지원금신청내역 스키마"""

    SBVT_ID: int = Field(..., description="정책지원금ID")
    APL_MTHD_CD: list[str] | None = Field(
        default=[], description="신청방법코드(배열) - 예: ['01', '02']"
    )
    APL_MTHD_CONTS: str | None = Field(
        default="",
        description="신청방법내용(통합) - 여러 방법의 내용을 구조화하여 저장",
    )
    CONSOLIDATED_FROM_ROWS: int | None = Field(
        default=1, description="통합된 원본 행 수 - 통합 전 몇 개의 행이었는지 기록"
    )
    FST_REG_DT: datetime | None = Field(
        default=None, description="최초등록일시 - 통합된 행 중 가장 빠른 등록일시"
    )
    LST_UPD_DT: datetime | None = Field(default=None, description="최종변경일시")

    model_config = ConfigDict(from_attributes=True)

    @validator("APL_MTHD_CD", pre=True, always=True)
    def validate_method_codes(cls, v):
        """신청방법코드 유효성 검증"""
        if v is None:
            return []
        if isinstance(v, str):
            # 단일 문자열인 경우 리스트로 변환
            return [v] if v.strip() else []
        if isinstance(v, list):
            # 빈 문자열이나 None 제거
            return [str(code).strip() for code in v if code and str(code).strip()]
        return []

    @validator("APL_MTHD_CONTS", pre=True, always=True)
    def validate_method_contents(cls, v):
        """신청방법내용 유효성 검증"""
        if v is None:
            return ""
        return str(v).strip()

    @validator("CONSOLIDATED_FROM_ROWS", pre=True, always=True)
    def validate_consolidated_rows(cls, v):
        """통합된 행 수 유효성 검증"""
        if v is None or v < 1:
            return 1
        return int(v)

    def get_method_codes_string(self, separator: str = ", ") -> str:
        """신청방법코드를 문자열로 반환"""
        if not self.APL_MTHD_CD:
            return ""
        return separator.join(self.APL_MTHD_CD)

    def has_multiple_methods(self) -> bool:
        """여러 신청방법이 있는지 확인"""
        return len(self.APL_MTHD_CD or []) > 1

    def is_consolidated(self) -> bool:
        """통합된 데이터인지 확인"""
        return (self.CONSOLIDATED_FROM_ROWS or 1) > 1

    def get_content_preview(self, max_length: int = 200) -> str:
        """내용 미리보기"""
        content = self.APL_MTHD_CONTS or ""
        if len(content) <= max_length:
            return content
        return content[:max_length] + "..."


# 기존 스키마들 (변경사항 없음)
class SubventionFileListSchema(BaseModel):
    SBVT_ID: int
    FILE_SNO: int | None = None
    FILE_NM: str | None = None
    FILE_ADDR: str | None = None
    FST_REG_DT: datetime | None = None
    LST_UPD_DT: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SubventionPreferentialRestrictionDetailSchema(BaseModel):
    SBVT_ID: int
    PRF_RSTR_DV_CD: str | None = None
    PRF_RSTR_SNO: int | None = None
    PRF_RSTR_CONTS: str | None = None
    FST_REG_DT: datetime | None = None
    LST_UPD_DT: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SubventionSupportingTypeDetailSchema(BaseModel):
    SBVT_ID: int
    SPOT_TYP_SNO: int | None = None
    SPOT_TYP_DV_CD: str | None = None
    SPOT_CONTS: str | None = None
    FST_REG_DT: datetime | None = None
    LST_UPD_DT: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SubventionSupportingIndustryDetailSchema(BaseModel):
    SBVT_ID: int
    SPOT_INDST_SNO: int | None = None
    INDST_CD: str | None = None
    FST_REG_DT: datetime | None = None
    LST_UPD_DT: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SubventionAnnouncementNoDetailSchema(BaseModel):
    SBVT_ID: int
    ANNC_SNO: int | None = None
    RCPT_INST_CD: str | None = None
    RCPT_INST_NM: str | None = None
    ANNC_NO: str | None = None
    FST_REG_DT: datetime | None = None
    LST_UPD_DT: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# 통합된 마스터 스키마 (APPLICATION_DETAIL 관계 업데이트)
class SubventionMasterConsolidatedSchema(BaseModel):
    """통합된 구조를 위한 정책지원금 마스터 스키마"""

    SBVT_ID: int
    ANNC_NO: str | None = None
    SBVT_TITLE: str | None = None
    RCPT_INST_CD: str | None = None
    RCPT_INST_NM: str | None = None
    RCPT_INST_CTGR_CD: str | None = None
    RSPS_DVSN_NM: str | None = None
    RSPS_DVSN_TEL_NO: str | None = None
    APL_STRT_DT: str | None = None
    APL_END_DT: str | None = None
    APL_DDLN_CONTS: str | None = None
    CNTC_DVSN_CONTS: str | None = None
    BIZ_OVRVW_CONTS: str | None = None
    SPOT_TRG_DV_CD: list[str] | None = None
    SPOT_TRG_STRTUP_DV_CD: list[str] | None = None
    SPOT_TRG_AREA_CD: list[str] | None = None
    SPOT_TRG_AREA_NM: list[str] | None = None
    REQRD_BUDG_AMT: int | None = None
    SPOT_AMT: int | None = None
    SELCT_SCLE_CONTS: str | None = None
    SPOT_CONTS: str | None = None
    SPOT_TYP_DV_CD: list[str] | None = None
    SPOT_QULFT_CONTS: str | None = None
    SUBM_DOC_CONTS: str | None = None
    SLT_PRSD_EVAL_CONTS: str | None = None
    NOTE_CONTS: str | None = None
    BIZ_REAS_LAW_CONTS: str | None = None
    ANNC_URL_ADDR: str | None = None
    DETL_PAGE_URL_ADDR: str | None = None
    ANNC_DT: str | None = None
    ANNC_HIT_CNT: int | None = None
    FST_REG_DT: datetime | None = None
    LST_UPD_DT: datetime | None = None
    SITE_CODE: str | None = None
    FOLDER_TYPE: str | None = None
    FOLDER_NAME: str | None = None
    EXTRACTED_TEXT: str | None = None

    # 통합된 APPLICATION_DETAIL (단일 관계)
    application_detail: SubventionApplicationDetailConsolidatedSchema | None = None

    model_config = ConfigDict(from_attributes=True)


# 통합 결과를 위한 스키마
class ConsolidationPreviewSchema(BaseModel):
    """통합 미리보기 결과 스키마"""

    sbvt_id: int
    success: bool
    error_message: str | None = None

    original_data: dict = Field(
        description="원본 데이터 정보 (행 수, 방법코드, 내용 길이 등)"
    )
    consolidated_data: dict = Field(
        description="통합된 데이터 정보 (방법코드, 내용 길이, 미리보기 등)"
    )
    metadata: dict = Field(description="통합 메타데이터 (처리 시간, 통계 등)")

    model_config = ConfigDict(from_attributes=True)


class ConsolidationStatisticsSchema(BaseModel):
    """통합 통계 스키마"""

    total_rows: int = Field(description="전체 행 수")
    unique_sbvt_ids: int = Field(description="고유 SBVT_ID 수")
    average_rows_per_sbvt: float = Field(description="SBVT_ID당 평균 행 수")
    max_rows_per_sbvt: int = Field(description="SBVT_ID당 최대 행 수")
    multi_row_sbvt_ids: int = Field(description="통합이 필요한 SBVT_ID 수")
    consolidation_needed: bool = Field(description="통합이 필요한지 여부")
    method_code_distribution: list[dict] = Field(description="신청방법코드 분포")

    model_config = ConfigDict(from_attributes=True)


# API 응답을 위한 스키마들
class ApplicationDetailConsolidationResponse(BaseModel):
    """APPLICATION_DETAIL 통합 API 응답 스키마"""

    success: bool
    message: str
    data: dict | None = None
    statistics: ConsolidationStatisticsSchema | None = None
    preview: list[ConsolidationPreviewSchema] | None = None

    model_config = ConfigDict(from_attributes=True)


class MigrationStatusSchema(BaseModel):
    """마이그레이션 상태 스키마"""

    migration_id: str
    status: str = Field(description="PENDING, RUNNING, COMPLETED, FAILED, ROLLED_BACK")
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_records: int | None = None
    processed_records: int | None = None
    success_count: int | None = None
    error_count: int | None = None
    errors: list[str] | None = None
    backup_table_name: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @property
    def progress_percentage(self) -> float:
        """진행률 계산"""
        if not self.total_records or self.total_records == 0:
            return 0.0
        if not self.processed_records:
            return 0.0
        return min(100.0, (self.processed_records / self.total_records) * 100.0)

    @property
    def is_completed(self) -> bool:
        """완료 여부"""
        return self.status == "COMPLETED"

    @property
    def is_failed(self) -> bool:
        """실패 여부"""
        return self.status == "FAILED"

    @property
    def has_errors(self) -> bool:
        """오류 존재 여부"""
        return self.error_count is not None and self.error_count > 0
