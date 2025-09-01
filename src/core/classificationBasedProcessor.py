"""
분류 기반 선별적 LLM 처리 시스템
ANNOUNCEMENT_CLASSIFICATION 테이블의 분류 결과를 기반으로
특정 분류 타입만 LLM 처리 및 DB 저장
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 프로젝트 루트 추가
sys.path.append(str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


class ClassificationBasedProcessor:
    """분류 기반 선별적 처리 클래스"""

    # LLM 처리 대상 분류 타입
    TARGET_CLASSIFICATION_TYPES = {
        "SMALL_BUSINESS": "소상공인",
        "SME": "중소기업",
        "STARTUP": "창업",
        "SOCIAL_ENTERPRISE": "사회적기업",
    }

    def __init__(self):
        self.processed_count = 0
        self.skipped_count = 0
        self.error_count = 0

        # 지연 로딩을 위한 컴포넌트들
        self._llm_parser = None
        self._db_handler = None

        logger.info("분류 기반 선별적 처리 시스템 초기화 완료")

    @property
    def llm_parser(self):
        """LLM 파서 지연 로딩"""
        if self._llm_parser is None:
            try:
                from src.core.llmParserGpt import LLMParserGpt

                self._llm_parser = LLMParserGpt()
                logger.info("LLMParserGpt 지연 로딩 완료")
            except Exception as e:
                logger.error(f"LLMParserGpt 로딩 실패: {e}")
        return self._llm_parser

    @property
    def db_handler(self):
        """DB 핸들러 지연 로딩"""
        if self._db_handler is None:
            try:
                from src.core.dbHandler import DBHandler

                self._db_handler = DBHandler()
                logger.info("DBHandler 지연 로딩 완료")
            except Exception as e:
                logger.error(f"DBHandler 로딩 실패: {e}")
        return self._db_handler

    def should_process_with_llm(
        self, folder_path: Path, site_code: str
    ) -> tuple[bool, dict]:
        """
        폴더가 LLM 처리 대상인지 확인

        Args:
            folder_path: 공고 폴더 경로
            site_code: 사이트 코드

        Returns:
            (should_process: bool, classification_info: Dict)
        """

        try:
            from sqlalchemy import text

            from src.models.database import SessionLocal

            db = SessionLocal()

            # ANNOUNCEMENT_CLASSIFICATION 테이블에서 분류 정보 조회
            query = text(
                """
            SELECT CLASSIFICATION_TYPE, CONFIDENCE_SCORE, MATCHED_KEYWORDS,
                   INDUSTRY_KEYWORDS, CLASSIFICATION_ID, IS_PROCESSED
            FROM ANNOUNCEMENT_CLASSIFICATION
            WHERE SITE_CODE = :site_code
            AND FOLDER_NAME = :folder_name
            ORDER BY CLASSIFICATION_DATE DESC
            LIMIT 1
            """
            )

            folder_name = folder_path.name
            result = db.execute(
                query, {"site_code": site_code, "folder_name": folder_name}
            )

            row = result.fetchone()
            db.close()

            if not row:
                logger.warning(f"분류 정보를 찾을 수 없음: {folder_path}")
                return False, {}

            classification_type = row[0]
            confidence_score = row[1] or 0
            matched_keywords = row[2] or "[]"
            industry_keywords = row[3] or "[]"
            classification_id = row[4]
            is_processed = row[5] or False

            classification_info = {
                "classification_id": classification_id,
                "classification_type": classification_type,
                "confidence_score": confidence_score,
                "matched_keywords": matched_keywords,
                "industry_keywords": industry_keywords,
                "is_processed": is_processed,
                "classification_name": self.TARGET_CLASSIFICATION_TYPES.get(
                    classification_type, "기타"
                ),
            }

            # 대상 분류 타입인지 확인
            should_process = classification_type in self.TARGET_CLASSIFICATION_TYPES

            if should_process:
                logger.info(
                    f"✅ LLM 처리 대상: {folder_name} ({self.TARGET_CLASSIFICATION_TYPES[classification_type]})"
                )
            else:
                logger.info(f"⏭️  LLM 처리 제외: {folder_name} ({classification_type})")

            return should_process, classification_info

        except Exception as e:
            logger.error(f"분류 정보 조회 실패 ({folder_path}): {e}")
            return False, {}

    def process_classified_folder(
        self, folder_path: Path, site_code: str
    ) -> dict[str, Any]:
        """
        분류된 폴더에 대한 선별적 LLM 처리

        Args:
            folder_path: 공고 폴더 경로
            site_code: 사이트 코드

        Returns:
            처리 결과 딕셔너리
        """

        result = {
            "folder_path": str(folder_path),
            "site_code": site_code,
            "processed": False,
            "skipped": False,
            "error": None,
            "classification_info": {},
            "llm_result": None,
            "db_saved": False,
            "sbvt_id": None,
        }

        try:
            # 1. 분류 정보 확인
            should_process, classification_info = self.should_process_with_llm(
                folder_path, site_code
            )
            result["classification_info"] = classification_info

            if not should_process:
                result["skipped"] = True
                self.skipped_count += 1
                logger.info(f"⏭️  LLM 처리 건너뛰기: {folder_path.name}")
                return result

            # 2. 이미 처리된 경우 확인
            if classification_info.get("is_processed", False):
                result["skipped"] = True
                self.skipped_count += 1
                logger.info(f"✅ 이미 처리됨: {folder_path.name}")
                return result

            # 3. LLM 처리 수행
            logger.info(
                f"🤖 LLM 처리 시작: {folder_path.name} ({classification_info.get('classification_name', '알 수 없음')})"
            )

            llm_result = self._perform_llm_processing(
                folder_path, site_code, classification_info
            )

            if not llm_result:
                raise Exception("LLM 처리 실패")

            result["llm_result"] = llm_result

            # 4. DB 저장
            sbvt_id = self._save_to_master_table(
                llm_result, folder_path, site_code, classification_info
            )

            if sbvt_id:
                result["db_saved"] = True
                result["sbvt_id"] = sbvt_id
                result["processed"] = True
                self.processed_count += 1

                # 5. 분류 테이블 처리 상태 업데이트 (검증 결과 포함)
                validation_result = llm_result.get("validation_result")
                self._update_classification_processed_status(
                    classification_info["classification_id"], sbvt_id, validation_result
                )

                logger.info(
                    f"✅ LLM 처리 및 DB 저장 완료: {folder_path.name}, SBVT_ID: {sbvt_id}"
                )
            else:
                raise Exception("DB 저장 실패")

        except Exception as e:
            result["error"] = str(e)
            self.error_count += 1
            logger.error(f"❌ 처리 실패 ({folder_path.name}): {e}")

        return result

    def _perform_llm_processing(
        self, folder_path: Path, site_code: str, classification_info: dict
    ) -> dict | None:
        """LLM 처리 수행"""

        if not self.llm_parser:
            logger.error("LLM 파서가 초기화되지 않음")
            return None

        try:
            # 폴더 내 파일들을 처리하여 텍스트 추출
            extracted_text = self._extract_text_from_folder(folder_path)

            if not extracted_text:
                logger.warning(f"추출할 텍스트가 없음: {folder_path}")
                return None

            # 분류 정보를 컨텍스트로 제공하여 LLM 처리 품질 향상
            enhanced_prompt = self._create_enhanced_prompt(
                extracted_text, classification_info
            )

            # LLM 파싱 수행
            llm_result = self.llm_parser.parse_with_llm(
                enhanced_prompt,
                ".md",  # file_type - dot prefix required
                str(folder_path),  # file_path
            )

            # LLM 결과가 딕셔너리이고 비어있지 않으면 성공으로 간주
            # (LLM 파서는 parsed_data 키가 아닌 딕셔너리 자체를 반환)
            if llm_result and isinstance(llm_result, dict) and len(llm_result) > 0:
                # 분류 검증 및 불일치 감지 수행
                validation_result = self._validate_classification_consistency(
                    classification_info, llm_result
                )
                
                # 분류 정보를 LLM 결과에 추가
                llm_result["classification_info"] = classification_info
                llm_result["processed_timestamp"] = datetime.now().isoformat()

                # DB 저장을 위해 parsed_data 래핑
                final_result = {
                    "parsed_data": llm_result.copy(),
                    "quality_score": llm_result.get("quality_score", 0),
                    "field_completion_rate": llm_result.get("field_completion_rate", 0),
                    "classification_info": classification_info,
                    "validation_result": validation_result,
                    "processed_timestamp": datetime.now().isoformat(),
                }

                # 분류 불일치 로깅
                if validation_result.get("is_mismatch", False):
                    logger.warning(
                        f"⚠️ 분류 불일치 감지: {folder_path.name} - "
                        f"키워드: {validation_result.get('keyword_primary')}, "
                        f"LLM: {validation_result.get('llm_primary')}"
                    )
                else:
                    logger.info(
                        f"✅ 분류 일치 확인: {folder_path.name} - "
                        f"분류: {validation_result.get('keyword_primary')}"
                    )

                logger.info(
                    f"✅ LLM 처리 성공: {folder_path.name} - 품질: {llm_result.get('quality_score', 0):.1f}%"
                )
                return final_result
            else:
                logger.error(
                    f"❌ LLM 파싱 실패: {folder_path.name} - 결과: {type(llm_result)}, 키 개수: {len(llm_result) if llm_result and isinstance(llm_result, dict) else 0}"
                )
                return None

        except Exception as e:
            logger.error(f"LLM 처리 중 오류 ({folder_path}): {e}")
            return None

    def _extract_text_from_folder(self, folder_path: Path) -> str:
        """폴더에서 텍스트 추출"""

        try:
            from src.utils.announcementClassifier import AnnouncementClassifier

            classifier = AnnouncementClassifier()
            extracted_texts = classifier.extract_text_from_files(folder_path)

            if not extracted_texts:
                return ""

            # 품질 우선순위로 텍스트 결합
            combined_text = ""
            for filename, text in extracted_texts.items():
                if filename.endswith((".pdf", ".hwp", ".hwpx")):
                    combined_text = text + "\n" + combined_text  # 높은 품질 파일을 앞에
                else:
                    combined_text += "\n" + text

            return combined_text.strip()

        except Exception as e:
            logger.error(f"텍스트 추출 실패 ({folder_path}): {e}")
            return ""

    def _create_enhanced_prompt(self, text: str, classification_info: dict) -> str:
        """분류 정보를 활용한 향상된 프롬프트 생성"""

        classification_type = classification_info.get("classification_type", "UNKNOWN")
        classification_name = classification_info.get(
            "classification_name", "알 수 없음"
        )
        confidence_score = classification_info.get("confidence_score", 0)

        enhanced_prompt = f"""
[분류 정보]
- 대상 분류: {classification_name} ({classification_type})
- 신뢰도: {confidence_score}점
- 분류 근거: 이 공고는 {classification_name} 대상으로 분류되었습니다.

[원본 텍스트]
{text}

[처리 지침]
위 분류 정보를 참고하여 {classification_name} 관련 필드들을 중점적으로 추출하고 분석해주세요.
특히 지원 대상, 지원 자격, 지원 내용 등을 상세히 파악해주세요.
"""

        return enhanced_prompt

    def _save_to_master_table(
        self,
        llm_result: dict,
        folder_path: Path,
        site_code: str,
        classification_info: dict,
    ) -> int | None:
        """SubventionMasterTable에 저장"""

        if not self.db_handler:
            logger.error("DB 핸들러가 초기화되지 않음")
            return None

        try:
            # PRV 사이트 전용 데이터 처리 (선택사항 - 모듈이 있으면 사용)
            if site_code.lower() == "prv":
                try:
                    from src.utils.prvDataExtractor import process_prv_data

                    llm_result = process_prv_data(folder_path, llm_result)
                    logger.info(f"PRV 사이트 전용 데이터 처리 완료: {folder_path.name}")
                except ImportError:
                    logger.debug(
                        f"PRV 전용 데이터 처리 모듈을 찾을 수 없음 - 기본 처리로 진행: {folder_path.name}"
                    )
                except Exception as e:
                    logger.warning(f"PRV 전용 데이터 처리 실패, 기본 처리로 진행: {e}")

            # LLM 결과 데이터에 분류 정보 추가
            final_data = llm_result.get("parsed_data", {}).copy()

            # 분류 관련 필드 추가
            final_data.update(
                {
                    "CLASSIFICATION_TYPE": classification_info.get(
                        "classification_type"
                    ),
                    "CLASSIFICATION_CONFIDENCE": classification_info.get(
                        "confidence_score", 0
                    ),
                    "CLASSIFICATION_PROCESSED": True,
                    "CLASSIFICATION_TIMESTAMP": datetime.now(),
                    "MATCHED_KEYWORDS": classification_info.get(
                        "matched_keywords", "[]"
                    ),
                    "INDUSTRY_KEYWORDS": classification_info.get(
                        "industry_keywords", "[]"
                    ),
                    "FOLDER_NAME": folder_path.name,
                    "SITE_CODE": site_code,
                }
            )

            # 텍스트 추출
            extracted_text = self._extract_text_from_folder(folder_path)

            # 처리된 파일 정보 구성 (UNIQUE 제약조건 오류 방지를 위한 folder_name 추가)
            processed_files = {
                "best_file": {"exists": True, "path": str(folder_path)},
                "announcement_folder": str(folder_path),
                "classification_based_processing": True,
                "output_json": str(
                    folder_path / "processed_data.json"
                ),  # DB 핸들러에서 필요한 키
                "pdf": [],
                "hwp": [],
                "folder_name": folder_path.name  # 실제 공고 폴더명 명시적 추가
            }

            # DB 저장
            sbvt_id = self.db_handler.save_to_db(
                final_data, folder_path, processed_files, site_code, extracted_text
            )

            logger.debug(f"DB 저장 결과: SBVT_ID={sbvt_id} (타입: {type(sbvt_id)})")

            return sbvt_id

        except Exception as e:
            logger.error(f"마스터 테이블 저장 실패 ({folder_path}): {e}")
            import traceback

            traceback.print_exc()
            return None

    def _update_classification_processed_status(
        self, classification_id: int, sbvt_id: int, validation_result: dict = None
    ):
        """분류 테이블의 처리 상태 및 LLM 분류 정보 업데이트"""

        try:
            from sqlalchemy import text
            import json

            from src.models.database import SessionLocal

            db = SessionLocal()
            
            # LLM 분류 정보 추출
            llm_classification = None
            llm_classification_types = None
            llm_classification_scores = None
            llm_detected_keywords = None
            classification_validation_status = "LLM_COMPLETED"
            is_classification_mismatch = False
            mismatch_details = None
            
            if validation_result:
                llm_classification = validation_result.get("llm_primary")
                llm_types = validation_result.get("llm_types", [])
                llm_keywords = validation_result.get("llm_detected_keywords", [])
                llm_confidence = validation_result.get("llm_confidence", 0)
                
                if llm_types:
                    llm_classification_types = json.dumps(llm_types, ensure_ascii=False)
                if llm_keywords:
                    llm_detected_keywords = json.dumps(llm_keywords, ensure_ascii=False)
                if llm_confidence > 0:
                    llm_classification_scores = json.dumps({llm_classification: llm_confidence}, ensure_ascii=False)
                
                is_classification_mismatch = validation_result.get("is_mismatch", False)
                if is_classification_mismatch:
                    classification_validation_status = "MISMATCH"
                    mismatch_details = json.dumps(validation_result.get("mismatch_details", {}), ensure_ascii=False)
                else:
                    classification_validation_status = "VALIDATED"

            update_query = text(
                """
            UPDATE ANNOUNCEMENT_CLASSIFICATION
            SET IS_PROCESSED = TRUE,
                SBVT_ID = :sbvt_id,
                LLM_CLASSIFICATION_TYPE = :llm_classification_type,
                LLM_CLASSIFICATION_TYPES = :llm_classification_types,
                LLM_CLASSIFICATION_SCORES = :llm_classification_scores,
                LLM_DETECTED_KEYWORDS = :llm_detected_keywords,
                CLASSIFICATION_VALIDATION_STATUS = :classification_validation_status,
                IS_CLASSIFICATION_MISMATCH = :is_classification_mismatch,
                MISMATCH_DETAILS = :mismatch_details,
                LAST_UPDATED = NOW()
            WHERE CLASSIFICATION_ID = :classification_id
            """
            )

            db.execute(
                update_query,
                {
                    "classification_id": classification_id,
                    "sbvt_id": sbvt_id,
                    "llm_classification_type": llm_classification,
                    "llm_classification_types": llm_classification_types,
                    "llm_classification_scores": llm_classification_scores,
                    "llm_detected_keywords": llm_detected_keywords,
                    "classification_validation_status": classification_validation_status,
                    "is_classification_mismatch": is_classification_mismatch,
                    "mismatch_details": mismatch_details,
                },
            )

            db.commit()
            db.close()

            status_msg = "일치" if not is_classification_mismatch else "불일치"
            logger.info(
                f"분류 테이블 업데이트 완료: {classification_id} -> SBVT_ID: {sbvt_id}, "
                f"LLM 분류: {llm_classification}, 검증: {status_msg}"
            )

        except Exception as e:
            logger.error(f"분류 테이블 상태 업데이트 실패: {e}")

    def process_site_folders(
        self, data_origin_path: Path, site_codes: list[str] | None = None
    ) -> dict[str, Any]:
        """사이트별 폴더 일괄 처리"""

        results = {
            "total_folders": 0,
            "processed_folders": 0,
            "skipped_folders": 0,
            "error_folders": 0,
            "by_site": {},
            "by_classification_type": {},
            "processing_time": 0,
        }

        start_time = datetime.now()

        try:
            logger.info(f"🚀 분류 기반 선별적 처리 시작: {data_origin_path}")

            # 사이트별 폴더 순회
            for site_dir in data_origin_path.iterdir():
                if not site_dir.is_dir():
                    continue

                site_code = site_dir.name

                # 특정 사이트만 처리하는 경우
                if site_codes and site_code not in site_codes:
                    continue

                logger.info(f"📁 사이트 처리 중: {site_code}")

                site_results = {
                    "total": 0,
                    "processed": 0,
                    "skipped": 0,
                    "errors": 0,
                    "by_type": {},
                }

                # prv 사이트 특수 처리 ([시도]/[시군구]/공고 구조)
                if site_code.lower() == "prv":
                    from src.utils.folderUtil import get_prv_announcement_folders

                    prv_folders = get_prv_announcement_folders(site_dir)

                    for (
                        announcement_dir,
                        sido_name,
                        sigungu_name,
                        announcement_name,
                    ) in prv_folders:
                        results["total_folders"] += 1
                        site_results["total"] += 1

                        # prv 사이트 전용 처리 수행
                        folder_result = self.process_classified_folder(
                            announcement_dir, site_code
                        )

                        # 결과 집계
                        self._aggregate_classification_results(
                            folder_result, results, site_results
                        )

                        logger.debug(
                            f"prv 공고 처리 완료: {sido_name}/{sigungu_name}/{announcement_name}"
                        )
                else:
                    # 일반 사이트 처리 (기존 로직)
                    for announcement_dir in site_dir.iterdir():
                        if not announcement_dir.is_dir():
                            continue

                        # 메타데이터 폴더 제외
                        if (
                            announcement_dir.name.startswith("processed_")
                            or announcement_dir.name.startswith("backup_")
                            or announcement_dir.name.startswith("temp_")
                        ):
                            continue

                        results["total_folders"] += 1
                        site_results["total"] += 1

                        # 개별 폴더 처리
                        folder_result = self.process_classified_folder(
                            announcement_dir, site_code
                        )

                        # 결과 집계
                        self._aggregate_classification_results(
                            folder_result, results, site_results
                        )

                results["by_site"][site_code] = site_results
                logger.info(
                    f"✅ 사이트 {site_code} 완료: 처리 {site_results['processed']}, 건너뜀 {site_results['skipped']}, 오류 {site_results['errors']}"
                )

            end_time = datetime.now()
            results["processing_time"] = (end_time - start_time).total_seconds()

            logger.info("🎉 분류 기반 선별적 처리 완료:")
            logger.info(f"  - 총 폴더: {results['total_folders']}개")
            logger.info(f"  - 처리됨: {results['processed_folders']}개")
            logger.info(f"  - 건너뜀: {results['skipped_folders']}개")
            logger.info(f"  - 오류: {results['error_folders']}개")
            logger.info(f"  - 처리 시간: {results['processing_time']:.1f}초")

        except Exception as e:
            logger.error(f"일괄 처리 중 오류 발생: {e}")
            import traceback

            traceback.print_exc()

        return results

    def _aggregate_classification_results(
        self, folder_result: dict, results: dict, site_results: dict
    ):
        """분류 처리 결과를 집계합니다."""

        if folder_result["processed"]:
            results["processed_folders"] += 1
            site_results["processed"] += 1

            # 분류 타입별 집계
            classification_type = folder_result["classification_info"].get(
                "classification_type", "UNKNOWN"
            )
            results["by_classification_type"][classification_type] = (
                results["by_classification_type"].get(classification_type, 0) + 1
            )
            site_results["by_type"][classification_type] = (
                site_results["by_type"].get(classification_type, 0) + 1
            )

        elif folder_result["skipped"]:
            results["skipped_folders"] += 1
            site_results["skipped"] += 1
        else:
            results["error_folders"] += 1
            site_results["errors"] += 1

    def get_processing_statistics(self) -> dict[str, Any]:
        """처리 통계 반환"""

        return {
            "target_classification_types": self.TARGET_CLASSIFICATION_TYPES,
            "processed_count": self.processed_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "total_count": self.processed_count + self.skipped_count + self.error_count,
            "success_rate": (
                self.processed_count / max(1, self.processed_count + self.error_count)
            )
            * 100,
        }

    def _validate_classification_consistency(
        self, classification_info: dict, llm_result: dict
    ) -> dict:
        """
        키워드 기반 분류와 LLM 기반 분류의 일치성 검증
        
        Args:
            classification_info: 키워드 기반 분류 정보
            llm_result: LLM 처리 결과 (CLASSIFICATION_INFO 포함)
            
        Returns:
            dict: 검증 결과 정보
        """
        try:
            # 키워드 기반 분류 정보 추출
            keyword_primary = classification_info.get("classification_type", "")
            keyword_name = self.TARGET_CLASSIFICATION_TYPES.get(keyword_primary, "")
            keyword_confidence = classification_info.get("confidence_score", 0)
            
            # LLM 기반 분류 정보 추출
            llm_classification = llm_result.get("CLASSIFICATION_INFO", {})
            llm_primary = llm_classification.get("primary_classification", "")
            llm_types = llm_classification.get("classification_types", [])
            llm_confidence = llm_classification.get("confidence_score", 0)
            llm_keywords = llm_classification.get("detected_keywords", [])
            llm_reasoning = llm_classification.get("reasoning", "")
            
            # 분류 매핑 (한글 -> 영어 코드)
            classification_mapping = {v: k for k, v in self.TARGET_CLASSIFICATION_TYPES.items()}
            llm_primary_code = classification_mapping.get(llm_primary, "")
            
            # 불일치 여부 판단
            is_mismatch = False
            mismatch_details = {}
            
            if keyword_primary != llm_primary_code and llm_primary_code:
                is_mismatch = True
                confidence_diff = abs(keyword_confidence - llm_confidence)
                
                mismatch_details = {
                    "keyword_primary": keyword_name,
                    "llm_primary": llm_primary,
                    "keyword_code": keyword_primary,
                    "llm_primary_code": llm_primary_code,
                    "confidence_diff": confidence_diff,
                    "keyword_confidence": keyword_confidence,
                    "llm_confidence": llm_confidence,
                    "review_needed": confidence_diff > 20,  # 20점 이상 차이면 리뷰 필요
                    "llm_reasoning": llm_reasoning
                }
                
                logger.info(f"분류 불일치 감지: {keyword_name} -> {llm_primary} (신뢰도 차이: {confidence_diff}점)")
            else:
                logger.debug(f"분류 일치 확인: {keyword_name}")
            
            # 검증 결과 구성
            validation_result = {
                "is_mismatch": is_mismatch,
                "keyword_primary": keyword_name,
                "keyword_code": keyword_primary,
                "llm_primary": llm_primary,
                "llm_primary_code": llm_primary_code,
                "llm_types": llm_types,
                "llm_detected_keywords": llm_keywords,
                "llm_confidence": llm_confidence,
                "keyword_confidence": keyword_confidence,
                "mismatch_details": mismatch_details,
                "validation_status": "MISMATCH" if is_mismatch else "VALIDATED",
                "validation_timestamp": datetime.now().isoformat()
            }
            
            return validation_result
            
        except Exception as e:
            logger.error(f"분류 검증 중 오류 발생: {e}")
            return {
                "is_mismatch": False,
                "validation_status": "ERROR",
                "error_message": str(e),
                "validation_timestamp": datetime.now().isoformat()
            }
