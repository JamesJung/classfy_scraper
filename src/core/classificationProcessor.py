"""
공고 분류 처리를 위한 핵심 프로세서
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ClassificationProcessor:
    """공고 분류 처리 클래스"""

    def __init__(self):
        self.classifier = None
        self.filter = None
        self._initialize_classifier()
        self._initialize_filter()

    def _initialize_classifier(self):
        """분류기 초기화"""
        try:
            from src.utils.announcementClassifier import AnnouncementClassifier

            self.classifier = AnnouncementClassifier()
            logger.info("공고 분류기 초기화 완료")
        except Exception as e:
            logger.error(f"분류기 초기화 실패: {e}")

    def _initialize_filter(self):
        """필터 초기화"""
        try:
            from src.utils.announcementFilter import AnnouncementFilter

            self.filter = AnnouncementFilter()
            logger.info("공고 필터 초기화 완료")
        except Exception as e:
            logger.error(f"공고 필터 초기화 실패: {e}")

    def process_announcement_folder(self, folder_path: Path, site_code: str) -> dict:
        """공고 폴더 처리 및 분류"""

        logger.info(f"공고 폴더 처리 시작: {folder_path}")
        logger.info(f"분류기: {self.classifier}")
        logger.info(f"필터: {self.filter}")
        
        if not self.classifier or not self.filter:
            logger.error("분류기 또는 필터가 초기화되지 않음")
            return None

        try:
            # 1. 제외 키워드 검사 (먼저 수행)
            should_exclude, exclusion_info = self.filter.check_announcement_exclusion(
                folder_path, site_code
            )

            if should_exclude:
                logger.info(
                    f"공고 제외됨: {folder_path.name} - {exclusion_info['exclusion_reason']}"
                )
                # 제외된 공고는 분류하지 않고 제외 정보만 반환
                return {
                    "excluded": True,
                    "exclusion_info": exclusion_info,
                    "classification_type": "EXCLUDED",
                    "processed": False,
                }

            # 2. 공고 분류 분석 (제외되지 않은 경우만)
            analysis_result = self.classifier.analyze_announcement(
                folder_path, site_code
            )

            # 3. DB에 저장
            classification_id = self.save_classification_result(analysis_result)

            if classification_id:
                analysis_result["classification_id"] = classification_id
                logger.info(
                    f"공고 분류 완료: {folder_path.name} -> {analysis_result['classification_type']}"
                )

            analysis_result["excluded"] = False
            analysis_result["processed"] = True

            return analysis_result

        except Exception as e:
            logger.error(f"공고 분류 처리 실패 ({folder_path}): {e}")
            return None

    def save_classification_result(self, analysis_result: dict, sbvt_id: int = None) -> int | None:
        """분류 결과를 DB에 저장"""

        try:
            from sqlalchemy import text

            from src.models.database import SessionLocal

            db = SessionLocal()

            # UPSERT 로직 (기존 레코드가 있으면 업데이트, 없으면 삽입)
            upsert_sql = """
            INSERT INTO ANNOUNCEMENT_CLASSIFICATION (
                SITE_CODE, FOLDER_NAME, FOLDER_PATH, ANNOUNCEMENT_TITLE,
                MATCHED_KEYWORDS, KEYWORD_COUNT, CLASSIFICATION_TYPE,
                INDUSTRY_KEYWORDS, INDUSTRY_COUNT, CONFIDENCE_SCORE,
                SOURCE_FILES, EXTRACTED_TEXT_PREVIEW, IS_PROCESSED, SBVT_ID
            ) VALUES (
                :site_code, :folder_name, :folder_path, :announcement_title,
                :matched_keywords, :keyword_count, :classification_type,
                :industry_keywords, :industry_count, :confidence_score,
                :source_files, :extracted_text_preview, :is_processed, :sbvt_id
            ) ON DUPLICATE KEY UPDATE
                ANNOUNCEMENT_TITLE = VALUES(ANNOUNCEMENT_TITLE),
                MATCHED_KEYWORDS = VALUES(MATCHED_KEYWORDS),
                KEYWORD_COUNT = VALUES(KEYWORD_COUNT),
                CLASSIFICATION_TYPE = VALUES(CLASSIFICATION_TYPE),
                INDUSTRY_KEYWORDS = VALUES(INDUSTRY_KEYWORDS),
                INDUSTRY_COUNT = VALUES(INDUSTRY_COUNT),
                CONFIDENCE_SCORE = VALUES(CONFIDENCE_SCORE),
                SOURCE_FILES = VALUES(SOURCE_FILES),
                EXTRACTED_TEXT_PREVIEW = VALUES(EXTRACTED_TEXT_PREVIEW),
                IS_PROCESSED = VALUES(IS_PROCESSED),
                SBVT_ID = VALUES(SBVT_ID),
                LAST_UPDATED = CURRENT_TIMESTAMP
            """

            # JSON 직렬화
            matched_keywords_json = json.dumps(
                analysis_result["matched_keywords"], ensure_ascii=False
            )
            industry_keywords_json = json.dumps(
                analysis_result["industry_keywords"], ensure_ascii=False
            )
            source_files_json = json.dumps(
                analysis_result["source_files"], ensure_ascii=False
            )

            params = {
                "site_code": analysis_result["site_code"],
                "folder_name": analysis_result["folder_name"],
                "folder_path": analysis_result["folder_path"],
                "announcement_title": analysis_result["announcement_title"],
                "matched_keywords": matched_keywords_json,
                "keyword_count": len(analysis_result["matched_keywords"]),
                "classification_type": analysis_result["classification_type"],
                "industry_keywords": industry_keywords_json,
                "sbvt_id": sbvt_id,
                "industry_count": len(analysis_result["industry_keywords"]),
                "confidence_score": analysis_result["confidence_score"],
                "source_files": source_files_json,
                "extracted_text_preview": analysis_result["extracted_text_preview"],
                "is_processed": True,
            }

            result = db.execute(text(upsert_sql), params)

            # 삽입된 또는 업데이트된 레코드의 ID 가져오기
            classification_id = result.lastrowid
            if not classification_id:
                # UPDATE된 경우 ID 조회
                select_sql = """
                SELECT CLASSIFICATION_ID FROM ANNOUNCEMENT_CLASSIFICATION
                WHERE SITE_CODE = :site_code AND FOLDER_NAME = :folder_name
                """
                id_result = db.execute(
                    text(select_sql),
                    {
                        "site_code": analysis_result["site_code"],
                        "folder_name": analysis_result["folder_name"],
                    },
                )
                row = id_result.fetchone()
                classification_id = row[0] if row else None

            db.commit()
            db.close()

            return classification_id

        except Exception as e:
            logger.error(f"분류 결과 저장 실패: {e}")
            if "db" in locals():
                db.rollback()
                db.close()
            return None

    def get_classification_statistics(self, site_code: str | None = None) -> dict:
        """분류 통계 조회"""

        try:
            from sqlalchemy import text

            from src.models.database import SessionLocal

            db = SessionLocal()

            where_clause = "WHERE SITE_CODE = :site_code" if site_code else ""
            params = {"site_code": site_code} if site_code else {}

            # 분류 타입별 통계
            stats_sql = f"""
            SELECT
                CLASSIFICATION_TYPE,
                COUNT(*) as count,
                AVG(CONFIDENCE_SCORE) as avg_confidence,
                COUNT(CASE WHEN CONFIDENCE_SCORE >= 20 THEN 1 END) as high_confidence,
                COUNT(CASE WHEN CONFIDENCE_SCORE >= 10 AND CONFIDENCE_SCORE < 20 THEN 1 END) as medium_confidence,
                COUNT(CASE WHEN CONFIDENCE_SCORE < 10 THEN 1 END) as low_confidence
            FROM ANNOUNCEMENT_CLASSIFICATION
            {where_clause}
            GROUP BY CLASSIFICATION_TYPE
            """

            result = db.execute(text(stats_sql), params)
            stats = result.fetchall()

            # 업종별 통계
            industry_sql = f"""
            SELECT
                JSON_UNQUOTE(JSON_EXTRACT(ik.value, '$.industry_category')) as industry_category,
                COUNT(*) as count
            FROM ANNOUNCEMENT_CLASSIFICATION ac,
                 JSON_TABLE(ac.INDUSTRY_KEYWORDS, '$[*]' COLUMNS (
                     value JSON PATH '$'
                 )) as ik
            {where_clause}
            GROUP BY industry_category
            HAVING industry_category IS NOT NULL
            """

            industry_result = db.execute(text(industry_sql), params)
            industry_stats = industry_result.fetchall()

            db.close()

            return {
                "classification_stats": [
                    {
                        "type": row[0],
                        "count": row[1],
                        "avg_confidence": float(row[2]) if row[2] else 0,
                        "high_confidence": row[3],
                        "medium_confidence": row[4],
                        "low_confidence": row[5],
                    }
                    for row in stats
                ],
                "industry_stats": [
                    {"category": row[0], "count": row[1]} for row in industry_stats
                ],
            }

        except Exception as e:
            logger.error(f"분류 통계 조회 실패: {e}")
            return {"classification_stats": [], "industry_stats": []}

    def bulk_classify_announcements(
        self, data_origin_path: Path, site_codes: list[str] | None = None
    ) -> dict:
        """대량 공고 분류 처리"""

        results = {
            "total_processed": 0,
            "successful_classifications": 0,
            "failed_classifications": 0,
            "by_site": {},
            "by_classification_type": {},
        }

        try:
            logger.info(f"대량 분류 시작: {data_origin_path}")

            # 사이트별 폴더 순회
            for site_dir in data_origin_path.iterdir():
                if not site_dir.is_dir():
                    continue

                site_code = site_dir.name

                # 특정 사이트만 처리하는 경우
                if site_codes and site_code not in site_codes:
                    continue

                logger.info(f"사이트 처리 중: {site_code}")

                site_results = {
                    "processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "by_type": {},
                }

                # 공고 폴더 순회
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

                    results["total_processed"] += 1
                    site_results["processed"] += 1

                    # 공고 분류 처리
                    classification_result = self.process_announcement_folder(
                        announcement_dir, site_code
                    )

                    if classification_result:
                        results["successful_classifications"] += 1
                        site_results["successful"] += 1

                        # 분류 타입별 집계
                        classification_type = classification_result[
                            "classification_type"
                        ]

                        results["by_classification_type"][classification_type] = (
                            results["by_classification_type"].get(
                                classification_type, 0
                            )
                            + 1
                        )

                        site_results["by_type"][classification_type] = (
                            site_results["by_type"].get(classification_type, 0) + 1
                        )
                    else:
                        results["failed_classifications"] += 1
                        site_results["failed"] += 1

                results["by_site"][site_code] = site_results
                logger.info(
                    f"사이트 {site_code} 완료: {site_results['successful']}/{site_results['processed']}"
                )

            logger.info(
                f"대량 분류 완료: {results['successful_classifications']}/{results['total_processed']}"
            )

        except Exception as e:
            logger.error(f"대량 분류 처리 실패: {e}")

        return results
