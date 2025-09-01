"""
공고 제외 필터링 유틸리티
공고 제목에 제외 키워드가 포함된 경우 필터링
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class AnnouncementFilter:
    """공고 제외 필터링 클래스"""

    def __init__(self):
        self.exclusion_keywords_cache = None
        self.support_content_keywords = None
        self.load_exclusion_keywords()
        self._load_support_content_patterns()

    def load_exclusion_keywords(self):
        """데이터베이스에서 제외 키워드를 로드"""
        try:
            from sqlalchemy import text

            from src.models.database import SessionLocal

            db = SessionLocal()

            result = db.execute(
                text(
                    """
                SELECT EXCLUSION_ID, KEYWORD, DESCRIPTION
                FROM EXCLUSION_KEYWORDS
                WHERE IS_ACTIVE = TRUE
                ORDER BY EXCLUSION_ID
            """
                )
            )

            keywords = result.fetchall()

            self.exclusion_keywords_cache = []
            for exclusion_id, keyword, description in keywords:
                self.exclusion_keywords_cache.append(
                    {"id": exclusion_id, "keyword": keyword, "description": description}
                )

            db.close()
            logger.info(
                f"제외 키워드 로드 완료: {len(self.exclusion_keywords_cache)}개"
            )

        except Exception as e:
            logger.error(f"제외 키워드 로딩 실패: {e}")
            self.exclusion_keywords_cache = []

    def _load_support_content_patterns(self):
        """지원내용 감지를 위한 패턴 로드"""

        # 지원내용 관련 핵심 키워드 (동의어/유의어 포함)
        self.support_content_keywords = {
            "primary": [
                "지원내용",
                "지원사항",
                "지원방법",
                "지원혜택",
                "혜택",
                "지원금",
                "보조금",
                "재정지원",
                "자금지원",
                "컨설팅",
                "교육지원",
                "멘토링",
                "기술지원",
            ],
            "secondary": [
                "지원",
                "지원대상",
                "지원금액",
                "지원기간",
                "사업내용",
                "사업지원",
                "프로그램",
                "서비스",
                "제공",
                "지원분야",
                "지원조건",
            ],
            "amount_patterns": [
                "만원",
                "억원",
                "천만원",
                "원",
                "금액",
                "예산",
                "최대",
                "최소",
                "최고",
                "한도",
                "규모",
            ],
            "service_patterns": [
                "무료",
                "제공",
                "지급",
                "지원",
                "혜택",
                "서비스",
                "프로그램",
                "과정",
                "교육",
                "컨설팅",
                "상담",
            ],
        }

        logger.debug(
            f"지원내용 패턴 로드 완료: {sum(len(v) for v in self.support_content_keywords.values())}개"
        )

    def check_comprehensive_exclusion(
        self, folder_path: Path, site_code: str, extracted_texts: dict[str, str] = None
    ) -> tuple[bool, dict]:
        """
        포괄적 공고 제외 검사 (키워드 + 지원내용 부재)

        Args:
            folder_path: 공고 폴더 경로
            site_code: 사이트 코드
            extracted_texts: 이미 추출된 텍스트 (선택적)

        Returns:
            (should_exclude: bool, exclusion_info: Dict)
        """

        # 1. 기존 키워드 기반 제외 검사 (우선)
        should_exclude_keyword, keyword_exclusion_info = (
            self.check_announcement_exclusion(folder_path, site_code)
        )

        if should_exclude_keyword:
            # 키워드 제외가 우선순위 높음
            return True, keyword_exclusion_info

        # 2. 지원내용 부재 검사
        should_exclude_support, support_exclusion_info = (
            self.check_support_content_exclusion(
                folder_path, site_code, extracted_texts
            )
        )

        if should_exclude_support:
            return True, support_exclusion_info

        # 둘 다 통과한 경우
        return False, support_exclusion_info

    def check_announcement_exclusion(
        self, folder_path: Path, site_code: str
    ) -> tuple[bool, dict]:
        """
        공고 폴더가 제외 대상인지 확인

        Args:
            folder_path: 공고 폴더 경로
            site_code: 사이트 코드

        Returns:
            (should_exclude: bool, exclusion_info: Dict)
        """

        from src.utils.pathUtil import get_relative_folder_path

        exclusion_info = {
            "site_code": site_code,
            "folder_name": folder_path.name,
            "folder_path": get_relative_folder_path(folder_path),
            "announcement_title": self._extract_title_from_folder_name(
                folder_path.name
            ),
            "matched_exclusion_keywords": [],
            "exclusion_reason": "",
            "should_exclude": False,
        }

        if not self.exclusion_keywords_cache:
            return False, exclusion_info

        # 공고 제목에서 제외 키워드 검사
        title = exclusion_info["announcement_title"].lower()

        matched_keywords = []
        for keyword_info in self.exclusion_keywords_cache:
            keyword = keyword_info["keyword"].lower()

            if keyword in title:
                matched_keywords.append(
                    {
                        "keyword_id": keyword_info["id"],
                        "keyword": keyword_info["keyword"],
                        "description": keyword_info["description"],
                        "position": title.find(keyword),
                    }
                )

                logger.debug(
                    f"제외 키워드 매칭: '{keyword_info['keyword']}' in '{exclusion_info['announcement_title']}'"
                )

        if matched_keywords:
            exclusion_info["matched_exclusion_keywords"] = matched_keywords
            exclusion_info["exclusion_reason"] = (
                f"제목에 제외 키워드 포함: {', '.join([kw['keyword'] for kw in matched_keywords])}"
            )
            exclusion_info["should_exclude"] = True

            # 제외 로그 저장
            self._save_exclusion_log(exclusion_info)

            # 키워드별 제외 횟수 업데이트
            self._update_exclusion_counts(matched_keywords)

            return True, exclusion_info

        return False, exclusion_info

    def check_support_content_exclusion(
        self, folder_path: Path, site_code: str, extracted_texts: dict[str, str] = None
    ) -> tuple[bool, dict]:
        """
        첨부파일 텍스트에서 지원내용이 없는 공고 제외 확인

        Args:
            folder_path: 공고 폴더 경로
            site_code: 사이트 코드
            extracted_texts: 이미 추출된 텍스트 (선택적)

        Returns:
            (should_exclude: bool, exclusion_info: Dict)
        """

        from src.utils.pathUtil import get_relative_folder_path

        exclusion_info = {
            "site_code": site_code,
            "folder_name": folder_path.name,
            "folder_path": get_relative_folder_path(folder_path),
            "announcement_title": self._extract_title_from_folder_name(
                folder_path.name
            ),
            "matched_exclusion_keywords": [],
            "exclusion_reason": "",
            "should_exclude": False,
            "support_content_analysis": {
                "primary_matches": 0,
                "secondary_matches": 0,
                "amount_matches": 0,
                "service_matches": 0,
                "total_score": 0,
                "text_length": 0,
            },
        }

        try:
            # 1. 텍스트 추출 (제공되지 않은 경우)
            if not extracted_texts:
                from src.utils.announcementClassifier import AnnouncementClassifier

                classifier = AnnouncementClassifier()
                extracted_texts = classifier.extract_text_from_files(folder_path)

            if not extracted_texts:
                # 텍스트 추출 실패한 경우도 제외 대상
                exclusion_info["exclusion_reason"] = "첨부파일에서 텍스트 추출 실패"
                exclusion_info["should_exclude"] = True
                self._save_exclusion_log(exclusion_info)
                return True, exclusion_info

            # 2. 모든 텍스트 병합
            combined_text = ""
            total_length = 0

            for filename, text in extracted_texts.items():
                if text and text.strip():
                    combined_text += f" {text}"
                    total_length += len(text)

            combined_text = combined_text.strip().lower()
            exclusion_info["support_content_analysis"]["text_length"] = total_length

            if len(combined_text) < 50:  # 텍스트가 너무 짧은 경우
                exclusion_info["exclusion_reason"] = (
                    "추출된 텍스트 내용 부족 (50자 미만)"
                )
                exclusion_info["should_exclude"] = True
                self._save_exclusion_log(exclusion_info)
                return True, exclusion_info

            # 3. 지원내용 관련 키워드 점수 계산
            support_score = self._calculate_support_content_score(
                combined_text, exclusion_info
            )

            # 4. 지원내용 부재 판정 기준
            should_exclude_support = self._should_exclude_for_lack_of_support(
                support_score, total_length
            )

            if should_exclude_support:
                exclusion_info["exclusion_reason"] = (
                    f"지원내용 부재 (점수: {support_score:.1f}, 텍스트: {total_length}자)"
                )
                exclusion_info["should_exclude"] = True

                # 제외 키워드 정보 구성
                exclusion_info["matched_exclusion_keywords"] = [
                    {
                        "keyword_id": "SUPPORT_CONTENT_MISSING",
                        "keyword": "지원내용_부재",
                        "description": "첨부파일에서 구체적인 지원내용을 찾을 수 없음",
                        "position": 0,
                    }
                ]

                # 제외 로그 저장
                self._save_exclusion_log(exclusion_info)

                logger.info(
                    f"지원내용 부재로 제외: {folder_path.name} (점수: {support_score:.1f})"
                )
                return True, exclusion_info

            logger.debug(
                f"지원내용 존재 확인: {folder_path.name} (점수: {support_score:.1f})"
            )
            return False, exclusion_info

        except Exception as e:
            logger.error(f"지원내용 부재 확인 중 오류 ({folder_path}): {e}")
            return False, exclusion_info

    def _extract_title_from_folder_name(self, folder_name: str) -> str:
        """폴더명에서 공고 제목 추출"""
        # 숫자_제목 형태에서 제목 부분만 추출
        match = re.match(r"^(\d+)_(.+)$", folder_name)
        if match:
            return match.group(2)
        return folder_name

    def _save_exclusion_log(self, exclusion_info: dict):
        """제외된 공고를 로그 테이블에 저장"""
        try:
            from sqlalchemy import text

            from src.models.database import SessionLocal

            db = SessionLocal()

            # JSON 직렬화
            matched_keywords_json = json.dumps(
                exclusion_info["matched_exclusion_keywords"], ensure_ascii=False
            )

            sql = """
            INSERT INTO ANNOUNCEMENT_EXCLUSION_LOG
            (SITE_CODE, FOLDER_NAME, FOLDER_PATH, ANNOUNCEMENT_TITLE,
             MATCHED_EXCLUSION_KEYWORDS, EXCLUSION_REASON)
            VALUES (:site_code, :folder_name, :folder_path, :announcement_title,
                    :matched_keywords, :exclusion_reason)
            ON DUPLICATE KEY UPDATE
                FOLDER_PATH = VALUES(FOLDER_PATH),
                ANNOUNCEMENT_TITLE = VALUES(ANNOUNCEMENT_TITLE),
                MATCHED_EXCLUSION_KEYWORDS = VALUES(MATCHED_EXCLUSION_KEYWORDS),
                EXCLUSION_REASON = VALUES(EXCLUSION_REASON)
            """

            db.execute(
                text(sql),
                {
                    "site_code": exclusion_info["site_code"],
                    "folder_name": exclusion_info["folder_name"],
                    "folder_path": exclusion_info["folder_path"],
                    "announcement_title": exclusion_info["announcement_title"],
                    "matched_keywords": matched_keywords_json,
                    "exclusion_reason": exclusion_info["exclusion_reason"],
                },
            )

            db.commit()
            db.close()

            logger.info(f"제외 로그 저장 완료: {exclusion_info['folder_name']}")

        except Exception as e:
            logger.error(f"제외 로그 저장 실패: {e}")
            if "db" in locals():
                db.rollback()
                db.close()

    def _update_exclusion_counts(self, matched_keywords: list[dict]):
        """키워드별 제외 횟수 업데이트"""
        try:
            from sqlalchemy import text

            from src.models.database import SessionLocal

            db = SessionLocal()

            for keyword_info in matched_keywords:
                sql = """
                UPDATE EXCLUSION_KEYWORDS
                SET EXCLUSION_COUNT = EXCLUSION_COUNT + 1,
                    UPDATED_AT = CURRENT_TIMESTAMP
                WHERE EXCLUSION_ID = :keyword_id
                """

                db.execute(text(sql), {"keyword_id": keyword_info["keyword_id"]})

            db.commit()
            db.close()

            logger.debug(f"제외 횟수 업데이트 완료: {len(matched_keywords)}개 키워드")

        except Exception as e:
            logger.error(f"제외 횟수 업데이트 실패: {e}")
            if "db" in locals():
                db.rollback()
                db.close()

    def get_exclusion_statistics(
        self, site_code: str | None = None, days: int = 30
    ) -> dict:
        """제외 통계 조회"""
        try:
            from sqlalchemy import text

            from src.models.database import SessionLocal

            db = SessionLocal()

            # 기본 통계 (키워드별 제외 횟수)
            keyword_stats_sql = """
            SELECT ek.KEYWORD, ek.DESCRIPTION, ek.EXCLUSION_COUNT, ek.IS_ACTIVE,
                   COALESCE(recent.RECENT_COUNT, 0) as RECENT_COUNT
            FROM EXCLUSION_KEYWORDS ek
            LEFT JOIN (
                SELECT
                    JSON_UNQUOTE(JSON_EXTRACT(kw.value, '$.keyword')) as keyword,
                    COUNT(*) as RECENT_COUNT
                FROM ANNOUNCEMENT_EXCLUSION_LOG ael,
                     JSON_TABLE(ael.MATCHED_EXCLUSION_KEYWORDS, '$[*]' COLUMNS (
                         value JSON PATH '$'
                     )) as kw
                WHERE ael.EXCLUDED_AT >= DATE_SUB(NOW(), INTERVAL :days DAY)
                {}
                GROUP BY keyword
            ) recent ON ek.KEYWORD = recent.keyword
            ORDER BY ek.EXCLUSION_COUNT DESC
            """.format(
                "AND ael.SITE_CODE = :site_code" if site_code else ""
            )

            params = {"days": days}
            if site_code:
                params["site_code"] = site_code

            result = db.execute(text(keyword_stats_sql), params)
            keyword_stats = result.fetchall()

            # 사이트별 통계
            site_stats_sql = """
            SELECT SITE_CODE, COUNT(*) as EXCLUSION_COUNT,
                   COUNT(DISTINCT DATE(EXCLUDED_AT)) as ACTIVE_DAYS
            FROM ANNOUNCEMENT_EXCLUSION_LOG
            WHERE EXCLUDED_AT >= DATE_SUB(NOW(), INTERVAL :days DAY)
            {}
            GROUP BY SITE_CODE
            ORDER BY EXCLUSION_COUNT DESC
            """.format(
                "AND SITE_CODE = :site_code" if site_code else ""
            )

            site_result = db.execute(text(site_stats_sql), params)
            site_stats = site_result.fetchall()

            # 최근 제외된 공고 목록
            recent_exclusions_sql = """
            SELECT SITE_CODE, FOLDER_NAME, ANNOUNCEMENT_TITLE,
                   EXCLUSION_REASON, EXCLUDED_AT
            FROM ANNOUNCEMENT_EXCLUSION_LOG
            WHERE EXCLUDED_AT >= DATE_SUB(NOW(), INTERVAL :days DAY)
            {}
            ORDER BY EXCLUDED_AT DESC
            LIMIT 20
            """.format(
                "AND SITE_CODE = :site_code" if site_code else ""
            )

            recent_result = db.execute(text(recent_exclusions_sql), params)
            recent_exclusions = recent_result.fetchall()

            db.close()

            return {
                "keyword_statistics": [
                    {
                        "keyword": row[0],
                        "description": row[1],
                        "total_count": row[2],
                        "is_active": bool(row[3]),
                        "recent_count": row[4],
                    }
                    for row in keyword_stats
                ],
                "site_statistics": [
                    {
                        "site_code": row[0],
                        "exclusion_count": row[1],
                        "active_days": row[2],
                    }
                    for row in site_stats
                ],
                "recent_exclusions": [
                    {
                        "site_code": row[0],
                        "folder_name": row[1],
                        "announcement_title": row[2],
                        "exclusion_reason": row[3],
                        "excluded_at": row[4],
                    }
                    for row in recent_exclusions
                ],
            }

        except Exception as e:
            logger.error(f"제외 통계 조회 실패: {e}")
            return {
                "keyword_statistics": [],
                "site_statistics": [],
                "recent_exclusions": [],
            }

    def _calculate_support_content_score(
        self, text: str, exclusion_info: dict
    ) -> float:
        """지원내용 관련 키워드 점수 계산"""

        if not self.support_content_keywords:
            return 0.0

        analysis = exclusion_info["support_content_analysis"]
        total_score = 0.0

        # 1차 키워드 (핵심 키워드) - 높은 가중치
        for keyword in self.support_content_keywords["primary"]:
            if keyword in text:
                count = text.count(keyword)
                analysis["primary_matches"] += count
                total_score += count * 5.0  # 5점씩 가중치
                logger.debug(f"1차 키워드 매칭: '{keyword}' {count}회")

        # 2차 키워드 (일반 키워드) - 중간 가중치
        for keyword in self.support_content_keywords["secondary"]:
            if keyword in text:
                count = text.count(keyword)
                analysis["secondary_matches"] += count
                total_score += count * 2.0  # 2점씩 가중치
                logger.debug(f"2차 키워드 매칭: '{keyword}' {count}회")

        # 금액 관련 키워드 - 중간 가중치
        for keyword in self.support_content_keywords["amount_patterns"]:
            if keyword in text:
                count = text.count(keyword)
                analysis["amount_matches"] += count
                total_score += count * 3.0  # 3점씩 가중치
                logger.debug(f"금액 키워드 매칭: '{keyword}' {count}회")

        # 서비스 관련 키워드 - 낮은 가중치
        for keyword in self.support_content_keywords["service_patterns"]:
            if keyword in text:
                count = text.count(keyword)
                analysis["service_matches"] += count
                total_score += count * 1.0  # 1점씩 가중치
                logger.debug(f"서비스 키워드 매칭: '{keyword}' {count}회")

        # 텍스트 길이에 따른 보정 (긴 텍스트일수록 키워드가 많을 수 있음)
        text_length_factor = min(1.0, len(text) / 1000)  # 1000자 기준으로 정규화
        adjusted_score = total_score / max(1, text_length_factor)

        analysis["total_score"] = adjusted_score

        logger.debug(
            f"지원내용 점수 계산: {adjusted_score:.1f} (원점수: {total_score:.1f}, 길이보정: {text_length_factor:.2f})"
        )
        return adjusted_score

    def _should_exclude_for_lack_of_support(
        self, support_score: float, text_length: int
    ) -> bool:
        """지원내용 부재 판정 기준"""

        # 텍스트 길이별 차등 기준 적용
        if text_length < 200:
            # 짧은 텍스트 - 엄격한 기준
            threshold = 8.0  # 높은 임계점
        elif text_length < 500:
            # 중간 길이 텍스트 - 보통 기준
            threshold = 6.0
        elif text_length < 1000:
            # 긴 텍스트 - 완화된 기준
            threshold = 4.0
        else:
            # 매우 긴 텍스트 - 가장 완화된 기준
            threshold = 3.0

        should_exclude = support_score < threshold

        logger.debug(
            f"지원내용 부재 판정: 점수={support_score:.1f}, 임계점={threshold}, "
            f"텍스트길이={text_length}, 제외여부={should_exclude}"
        )

        return should_exclude

    def reload_keywords(self):
        """키워드 캐시 재로드"""
        self.load_exclusion_keywords()
        self._load_support_content_patterns()
        logger.info("제외 키워드 캐시 재로드 완료")
