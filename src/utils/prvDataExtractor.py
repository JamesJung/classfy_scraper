#!/usr/bin/env python3
"""
PRV 사이트 전용 데이터 추출기
PRV 사이트의 특수 요구사항을 처리하는 전용 클래스

주요 기능:
1. content.md에서 "원본 URL"과 "정부24 URL" 분리 추출
2. LLM 추출 소관기관명을 INSTITUTION_MASTER와 매칭
3. SITE_MASTER 기관정보 사용 금지 (prv 전용)
"""

import re
from pathlib import Path

from src.config.logConfig import setup_logging
from src.utils.institutionUtil import InstitutionService

# 로깅 설정
logger = setup_logging(__name__)


class PrvDataExtractor:
    """PRV 사이트 전용 데이터 추출 클래스"""

    def __init__(self):
        self.institution_service = InstitutionService()
        logger.info("PRV 데이터 추출기 초기화 완료")

    def extract_prv_urls_from_content_md(self, content_md_path: Path) -> dict[str, str]:
        """
        PRV 사이트의 content.md에서 URL 정보를 추출합니다.

        Args:
            content_md_path: content.md 파일 경로

        Returns:
            {
                'ANNC_URL_ADDR': '원본 URL',
                'DETL_PAGE_URL_ADDR': '정부24 URL'
            }
        """
        result = {"ANNC_URL_ADDR": "", "DETL_PAGE_URL_ADDR": ""}

        try:
            if not content_md_path.exists():
                logger.warning(f"content.md 파일이 존재하지 않음: {content_md_path}")
                return result

            with open(content_md_path, encoding="utf-8") as f:
                content = f.read()

            # 원본 URL 추출
            original_url_pattern = r"\*\*원본 URL\*\*:\s*(.+)"
            original_match = re.search(original_url_pattern, content)
            if original_match:
                result["ANNC_URL_ADDR"] = original_match.group(1).strip()
                logger.debug(f"원본 URL 추출: {result['ANNC_URL_ADDR']}")

            # 정부24 URL 추출
            gov24_url_pattern = r"\*\*정부24 URL\*\*:\s*(.+)"
            gov24_match = re.search(gov24_url_pattern, content)
            if gov24_match:
                result["DETL_PAGE_URL_ADDR"] = gov24_match.group(1).strip()
                logger.debug(f"정부24 URL 추출: {result['DETL_PAGE_URL_ADDR']}")

            if not result["ANNC_URL_ADDR"] and not result["DETL_PAGE_URL_ADDR"]:
                logger.warning(f"URL 정보를 찾을 수 없음: {content_md_path}")

        except Exception as e:
            logger.error(f"content.md URL 추출 실패 ({content_md_path}): {e}")

        return result

    def extract_institution_from_llm_response(
        self, llm_response: dict
    ) -> dict[str, str]:
        """
        LLM 응답에서 소관기관명을 추출하고 INSTITUTION_MASTER와 매칭합니다.

        Args:
            llm_response: LLM 파싱 결과 딕셔너리

        Returns:
            {
                'RCPT_INST_CD': '매칭된 소관기관코드',
                'RCPT_INST_NM': '매칭된 소관기관명'
            }
        """
        result = {"RCPT_INST_CD": "", "RCPT_INST_NM": ""}

        try:
            # LLM 응답에서 소관기관명 후보들 수집
            institution_candidates = []

            # 1. RCPT_INST_NM 필드에서 직접 추출
            if llm_response.get("RCPT_INST_NM"):
                institution_candidates.append(llm_response["RCPT_INST_NM"])

            # 2. 기타 기관 관련 필드에서 추출
            institution_fields = [
                "CONTACT_INSTITUTION",
                "MANAGE_INSTITUTION",
                "HOST_INSTITUTION",
                "ORGANIZER",
                "CONTACT_DEPT",
                "MANAGEMENT_DEPT",
            ]

            for field in institution_fields:
                if llm_response.get(field):
                    institution_candidates.append(llm_response[field])

            # 3. 텍스트 분석을 통한 기관명 추출
            text_fields = [
                "BIZ_OVRVW_CONTS",
                "SPOT_CONTS",
                "SUBM_DOC_CONTS",
                "NOTE_CONTS",
            ]
            for field in text_fields:
                if llm_response.get(field):
                    extracted_institutions = self._extract_institutions_from_text(
                        llm_response[field]
                    )
                    institution_candidates.extend(extracted_institutions)

            # 4. 후보들 중 INSTITUTION_MASTER와 가장 잘 매칭되는 것 선택
            best_match = self._find_best_institution_match(institution_candidates)

            if best_match:
                result["RCPT_INST_CD"] = best_match["code"]
                result["RCPT_INST_NM"] = best_match["name"]
                logger.info(
                    f"PRV 소관기관 매칭 성공: '{best_match['name']}' -> '{best_match['code']}'"
                )
            else:
                logger.warning(
                    f"PRV 소관기관 매칭 실패. 후보: {institution_candidates}"
                )
                # 후보가 있으면 첫 번째를 기관명으로 사용
                if institution_candidates:
                    result["RCPT_INST_NM"] = institution_candidates[0]

        except Exception as e:
            logger.error(f"PRV 소관기관 추출 실패: {e}")

        return result

    def _extract_institutions_from_text(self, text: str) -> list[str]:
        """
        텍스트에서 기관명 패턴을 추출합니다.

        Args:
            text: 분석할 텍스트

        Returns:
            추출된 기관명 리스트
        """
        if not text:
            return []

        institutions = []

        # 일반적인 기관명 패턴들
        institution_patterns = [
            # 기본 패턴: OO구, OO시, OO도, OO청, OO원, OO공단, OO진흥원 등
            r"([가-힣]+(?:구|시|도|청|원|공단|진흥원|센터|재단|공사|협회|조합))",
            # 문의처 패턴: "문의: 강남구청 경제진흥과"
            r"문의.*?:\s*([가-힣]+(?:구|시|도|청|원|공단|진흥원|센터|재단|공사|협회|조합))",
            # 주관 패턴: "주관: 서울특별시 강남구"
            r"주관.*?:\s*([가-힣\s]+(?:구|시|도|청|원|공단|진흥원|센터|재단|공사|협회|조합))",
            # 접수처 패턴
            r"접수.*?:\s*([가-힣\s]+(?:구|시|도|청|원|공단|진흥원|센터|재단|공사|협회|조합))",
        ]

        for pattern in institution_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # 정리된 기관명 추가
                clean_name = match.strip()
                if clean_name and len(clean_name) >= 2:  # 최소 2글자 이상
                    institutions.append(clean_name)

        # 중복 제거하면서 순서 유지
        unique_institutions = []
        seen = set()
        for inst in institutions:
            if inst not in seen:
                unique_institutions.append(inst)
                seen.add(inst)

        logger.debug(f"텍스트에서 추출된 기관명: {unique_institutions}")
        return unique_institutions

    def _find_best_institution_match(self, candidates: list[str]) -> dict | None:
        """
        후보 기관명들 중 INSTITUTION_MASTER와 가장 잘 매칭되는 것을 찾습니다.

        Args:
            candidates: 후보 기관명 리스트

        Returns:
            매칭된 기관 정보 또는 None
        """
        if not candidates:
            return None

        # 후보별 매칭 점수 계산
        best_match = None
        best_score = 0

        for candidate in candidates:
            if not candidate or not candidate.strip():
                continue

            clean_candidate = candidate.strip()

            # INSTITUTION_MASTER에서 매칭 시도
            institution_info = self.institution_service.get_institution_info(
                clean_candidate
            )

            if institution_info:
                # 정확한 매칭인 경우 최고 점수
                score = 100
                logger.debug(
                    f"정확한 기관 매칭: '{clean_candidate}' -> '{institution_info['name']}'"
                )
            else:
                # 부분 매칭 시도
                partial_match, score = self._try_partial_institution_match(
                    clean_candidate
                )
                institution_info = partial_match

            if institution_info and score > best_score:
                best_match = institution_info
                best_score = score

        return best_match

    def _try_partial_institution_match(
        self, institution_name: str
    ) -> tuple[dict | None, int]:
        """
        부분 매칭을 통한 기관명 검색을 시도합니다.

        Args:
            institution_name: 검색할 기관명

        Returns:
            (매칭된 기관 정보, 매칭 점수)
        """
        try:
            # 기관명에서 핵심 키워드 추출
            keywords = self._extract_institution_keywords(institution_name)

            if not keywords:
                return None, 0

            # 각 키워드로 INSTITUTION_MASTER 검색
            for keyword in keywords:
                # 키워드가 포함된 기관명 검색
                institution_info = self._search_institution_by_keyword(keyword)
                if institution_info:
                    score = len(keyword) * 10  # 키워드 길이에 비례한 점수
                    logger.debug(
                        f"부분 매칭 성공: '{institution_name}' -> '{institution_info['name']}' (키워드: '{keyword}')"
                    )
                    return institution_info, score

            return None, 0

        except Exception as e:
            logger.error(f"부분 매칭 시도 실패: {e}")
            return None, 0

    def _extract_institution_keywords(self, institution_name: str) -> list[str]:
        """
        기관명에서 검색 키워드를 추출합니다.

        Args:
            institution_name: 원본 기관명

        Returns:
            추출된 키워드 리스트 (길이순으로 정렬)
        """
        keywords = []

        # 일반적인 기관 접미사들
        suffixes = [
            "구",
            "시",
            "도",
            "청",
            "원",
            "공단",
            "진흥원",
            "센터",
            "재단",
            "공사",
            "협회",
            "조합",
        ]

        # 접미사를 포함한 키워드 추출
        for suffix in suffixes:
            if suffix in institution_name:
                # "OO구" 형태의 키워드 추출
                pattern = f"([가-힣]+{suffix})"
                matches = re.findall(pattern, institution_name)
                keywords.extend(matches)

        # 핵심 단어 추출 (3글자 이상)
        words = re.findall(r"[가-힣]{3,}", institution_name)
        keywords.extend(words)

        # 중복 제거하고 길이순으로 정렬 (긴 것부터)
        unique_keywords = list(set(keywords))
        unique_keywords.sort(key=len, reverse=True)

        return unique_keywords[:5]  # 상위 5개만 사용

    def _search_institution_by_keyword(self, keyword: str) -> dict | None:
        """
        키워드로 INSTITUTION_MASTER에서 기관을 검색합니다.

        Args:
            keyword: 검색 키워드

        Returns:
            매칭된 기관 정보 또는 None
        """
        try:
            # InstitutionService의 캐시를 활용한 검색
            self.institution_service._load_cache()

            for inst_name, inst_info in self.institution_service._cache.items():
                if keyword in inst_name:
                    return inst_info

            return None

        except Exception as e:
            logger.error(f"키워드 기관 검색 실패: {e}")
            return None

    def process_prv_announcement_data(
        self, folder_path: Path, llm_response: dict
    ) -> dict:
        """
        PRV 공고 데이터를 종합적으로 처리합니다.

        Args:
            folder_path: 공고 폴더 경로
            llm_response: LLM 파싱 결과

        Returns:
            PRV 전용 처리가 완료된 데이터 딕셔너리
        """
        processed_data = llm_response.copy()

        try:
            # 1. content.md에서 URL 추출
            content_md_path = folder_path / "content.md"
            url_data = self.extract_prv_urls_from_content_md(content_md_path)
            processed_data.update(url_data)

            # 2. LLM 응답에서 소관기관 추출 및 매칭
            institution_data = self.extract_institution_from_llm_response(llm_response)
            processed_data.update(institution_data)

            # 3. PRV 처리 플래그 추가
            processed_data["PRV_PROCESSED"] = True
            processed_data["PRV_PROCESSING_TIMESTAMP"] = "datetime.now().isoformat()"

            # 로그 출력
            logger.info(f"PRV 데이터 처리 완료: {folder_path.name}")
            logger.info(f"  - 원본 URL: {processed_data.get('ANNC_URL_ADDR', 'N/A')}")
            logger.info(
                f"  - 정부24 URL: {processed_data.get('DETL_PAGE_URL_ADDR', 'N/A')}"
            )
            logger.info(
                f"  - 소관기관: {processed_data.get('RCPT_INST_NM', 'N/A')} ({processed_data.get('RCPT_INST_CD', 'N/A')})"
            )

        except Exception as e:
            logger.error(f"PRV 데이터 처리 실패 ({folder_path}): {e}")
            processed_data["PRV_PROCESSING_ERROR"] = str(e)

        return processed_data


# 전역 인스턴스
_prv_extractor = None


def get_prv_extractor() -> PrvDataExtractor:
    """PrvDataExtractor 싱글톤 인스턴스 반환"""
    global _prv_extractor
    if _prv_extractor is None:
        _prv_extractor = PrvDataExtractor()
    return _prv_extractor


def process_prv_data(folder_path: Path, llm_response: dict) -> dict:
    """
    PRV 사이트 데이터 처리 헬퍼 함수

    Args:
        folder_path: 공고 폴더 경로
        llm_response: LLM 파싱 결과

    Returns:
        PRV 전용 처리된 데이터
    """
    extractor = get_prv_extractor()
    return extractor.process_prv_announcement_data(folder_path, llm_response)
