from datetime import datetime

from pydantic import BaseModel, ConfigDict

# 정책지원금 기본 스키마들


class SubventionApplicationDetailSchema(BaseModel):
    SBVT_ID: int
    APL_SNO: int | None = None
    APL_MTHD_CD: str | None = None
    APL_MTHD_CONTS: str | None = None
    FST_REG_DT: datetime | None = None
    LST_UPD_DT: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


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
    PRF_DTL_DV_CD: list[str] | None = None
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
    INDST_CD: list[str] | None = None
    BIZ_TYPE_CD: list[str] | None = None
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


class SubventionMasterSchema(BaseModel):
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
    SPOT_QULFT_CONTS: str | None = None
    PRF_DTL_DV_CD: list[str] | None = None
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

    model_config = ConfigDict(from_attributes=True)
