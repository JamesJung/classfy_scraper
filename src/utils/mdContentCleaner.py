#!/usr/bin/env python3
"""
MD 파일 내용 정리 유틸리티
웹사이트 네비게이션, 헤더, 푸터 등 불필요한 내용을 제거하여 EXTRACTED_TEXT 품질을 향상시킵니다.
"""

import re

from src.config.logConfig import setup_logging

# 로깅 설정
logger = setup_logging(__name__)


class MDContentCleaner:
    """MD 파일 내용 정리 클래스"""

    def __init__(self):
        self.setup_cleaning_patterns()

    def setup_cleaning_patterns(self):
        """정리 패턴 설정"""

        # 헤더 메타데이터 패턴 (작성자, 작성일, 상태 등)
        self.header_patterns = [
            r"\*\*작성자\*\*:.*",
            r"\*\*작성일\*\*:.*",
            r"\*\*접수기간\*\*:.*",
            r"\*\*상태\*\*:.*",
            r"---\s*$",  # 헤더 구분선
        ]

        # PRV 사이트 전용: URL 메타데이터는 보존
        self.prv_preserved_patterns = [
            r"\*\*원본 URL\*\*:.*",
            r"\*\*정부24 URL\*\*:.*",
        ]

        # 네비게이션 메뉴 패턴
        self.navigation_patterns = [
            r"검색어를 입력하세요.*",
            r"\[로그인\].*",
            r"\[회원가입\].*",
            r"전체메뉴.*",
            r"## 전체메뉴",
            r"전체메뉴열기",
            r"전체메뉴닫기",
            r".*\[.*\]\(.*mCode.*\)",  # 메뉴 링크
            r".*\[.*\]\(.*CMS.*\)",  # CMS 링크
        ]

        # 푸터 패턴
        self.footer_patterns = [
            r"### 부산테크노파크 서비스메뉴",
            r"전국테크노파크",
            r"전국테크노파크 바로가기.*",
            r"BTP플랫폼",
            r"BTP플랫폼 바로가기.*",
            r"TOP\s*$",
            r".*바로가기 닫기",
        ]

        # UI 요소 패턴
        self.ui_patterns = [
            r"!\[.*\]\(.*logo.*\)",  # 로고 이미지
            r"!\[.*\]\(.*Icon.*\)",  # 아이콘 이미지
            r"!\[.*\]\(.*ico_.*\)",  # 아이콘 파일
            r"!\[.*\]\(/resources.*\)",  # 리소스 이미지
            r"!\[.*\]\(/attach.*\)",  # 첨부 이미지
        ]

        # 불필요한 링크 패턴
        self.link_patterns = [
            r"\[.*\]\(.*새창열림.*\)",
            r"\[.*\]\(.*새창내려받기.*\)",
            r"\[.*\]\(/kor/.*\)",
            r"\[.*\]\(http.*테크노파크.*\)",
        ]

        # 첨부파일 섹션 패턴
        self.attachment_patterns = [
            r"첨부파일\s*$",
            r"  \* \[ !\[.*첨부 파일.*\].*\].*",
        ]

        # 이전/다음 네비게이션 패턴
        self.navigation_link_patterns = [
            r"  \* \[ 이전글.*\].*",
            r"  \* \[ 다음글.*\].*",
            r"\[ 목록 \].*",
        ]

    def clean_md_content(self, content: str, site_code: str = None) -> str:
        """
        MD 파일 내용에서 불필요한 부분을 제거합니다.

        Args:
            content: 원본 MD 파일 내용
            site_code: 사이트 코드 (prv인 경우 URL 보존)

        Returns:
            정리된 MD 파일 내용
        """
        try:
            if not content or not content.strip():
                return content

            # PRV 사이트 전용 처리 또는 일반 처리
            if site_code and site_code.lower() == "prv":
                cleaned_content = self._conservative_clean_prv(content)
            else:
                cleaned_content = self._conservative_clean(content)

            # 유효성 검사
            if len(cleaned_content.strip()) < 100:
                logger.warning("MD 정리 결과가 너무 짧습니다. 원본 내용을 반환합니다.")
                return content

            # 정리 통계 로그
            original_lines = len(content.split("\n"))
            cleaned_lines_count = len(cleaned_content.split("\n"))
            reduction_ratio = (
                (original_lines - cleaned_lines_count) / original_lines * 100
            )

            logger.info(
                f"MD 내용 정리 완료: {original_lines}줄 → {cleaned_lines_count}줄 ({reduction_ratio:.1f}% 감소)"
            )

            return cleaned_content

        except Exception as e:
            logger.error(f"MD 내용 정리 중 오류: {e}")
            return content

    def _should_remove_line(self, line: str) -> bool:
        """라인을 제거해야 하는지 판단"""
        line_stripped = line.strip()

        # 빈 줄은 유지
        if not line_stripped:
            return False

        # 헤더 메타데이터 패턴 검사
        for pattern in self.header_patterns:
            if re.match(pattern, line_stripped):
                return True

        # 네비게이션 패턴 검사
        for pattern in self.navigation_patterns:
            if re.match(pattern, line_stripped):
                return True

        # 푸터 패턴 검사
        for pattern in self.footer_patterns:
            if re.match(pattern, line_stripped):
                return True

        # UI 요소 패턴 검사
        for pattern in self.ui_patterns:
            if re.search(pattern, line_stripped):
                return True

        # 링크 패턴 검사
        for pattern in self.link_patterns:
            if re.search(pattern, line_stripped):
                return True

        # 첨부파일 패턴 검사
        for pattern in self.attachment_patterns:
            if re.search(pattern, line_stripped):
                return True

        # 네비게이션 링크 패턴 검사
        for pattern in self.navigation_link_patterns:
            if re.search(pattern, line_stripped):
                return True

        return False

    def _is_prv_preserved_line(self, line: str) -> bool:
        """PRV 사이트에서 보존해야 하는 라인인지 판단"""
        line_stripped = line.strip()

        for pattern in self.prv_preserved_patterns:
            if re.match(pattern, line_stripped):
                return True
        return False

    def _conservative_clean_prv(self, content: str) -> str:
        """
        PRV 사이트 전용 보수적인 정리: URL 메타데이터 보존
        """
        lines = content.split("\n")
        cleaned_lines = []

        skip_until_content = False
        content_found = False
        url_metadata_lines = []

        for line in lines:
            line_stripped = line.strip()

            # PRV 전용: URL 메타데이터 라인 보존
            if self._is_prv_preserved_line(line):
                url_metadata_lines.append(line)
                continue

            # 기타 메타데이터 섹션 건너뛰기
            if line_stripped.startswith("**작성자**") or line_stripped.startswith(
                "**작성일**"
            ):
                skip_until_content = True
                continue

            # 대규모 네비게이션 블록 시작 감지
            if (
                ("로그인" in line_stripped and "회원가입" in line_stripped)
                or "전체메뉴" in line_stripped
                or line_stripped.startswith("  * [ 공고")
                or line_stripped.startswith("  * [ 기업지원")
            ):
                skip_until_content = True
                continue

            # 실제 내용 시작 감지
            if skip_until_content:
                if (
                    re.search(r"공고.*제.*\d{4}-\d+호", line_stripped)
                    or "지원분야" in line_stripped
                    or "산업분야" in line_stripped
                    or "게시일" in line_stripped
                ):
                    skip_until_content = False
                    content_found = True
                elif line_stripped.startswith("###") and any(
                    keyword in line_stripped
                    for keyword in ["공고", "사업", "지원", "모집"]
                ):
                    skip_until_content = False
                    content_found = True
                else:
                    continue

            # 내용 시작 후 바닥글 제거
            if content_found:
                if any(
                    keyword in line_stripped
                    for keyword in [
                        "부산테크노파크 서비스메뉴",
                        "전국테크노파크",
                        "BTP플랫폼",
                    ]
                ):
                    break
                if (
                    "이전글" in line_stripped
                    or "다음글" in line_stripped
                    or "목록" in line_stripped
                ):
                    break

            # 유효한 라인 추가
            if not skip_until_content:
                cleaned_lines.append(line)

        # PRV 전용: URL 메타데이터를 헤더에 추가
        if url_metadata_lines and cleaned_lines:
            # 첫 번째 제목 라인 다음에 URL 정보 삽입
            title_inserted = False
            final_lines = []

            for line in cleaned_lines:
                final_lines.append(line)

                # 첫 번째 제목(#) 라인 다음에 URL 메타데이터 삽입
                if not title_inserted and line.strip().startswith("#"):
                    final_lines.append("")  # 빈 줄
                    final_lines.extend(url_metadata_lines)
                    final_lines.append("")  # 빈 줄
                    title_inserted = True

            return "\n".join(final_lines)

        return "\n".join(cleaned_lines)

    def _conservative_clean(self, content: str) -> str:
        """
        보수적인 정리: 명확한 네비게이션 블록만 제거
        """
        lines = content.split("\n")
        cleaned_lines = []

        skip_until_content = False
        content_found = False

        for line in lines:
            line_stripped = line.strip()

            # 메타데이터 섹션 건너뛰기
            if line_stripped.startswith("**작성자**") or line_stripped.startswith(
                "**작성일**"
            ):
                skip_until_content = True
                continue

            # 대규모 네비게이션 블록 시작 감지
            if (
                ("로그인" in line_stripped and "회원가입" in line_stripped)
                or "전체메뉴" in line_stripped
                or line_stripped.startswith("  * [ 공고")
                or line_stripped.startswith("  * [ 기업지원")
            ):
                skip_until_content = True
                continue

            # 실제 내용 시작 감지
            if skip_until_content:
                # 공고 번호나 지원분야 등 실제 내용
                if (
                    re.search(r"공고.*제.*\d{4}-\d+호", line_stripped)
                    or "지원분야" in line_stripped
                    or "산업분야" in line_stripped
                    or "게시일" in line_stripped
                ):
                    skip_until_content = False
                    content_found = True
                elif line_stripped.startswith("###") and any(
                    keyword in line_stripped
                    for keyword in ["공고", "사업", "지원", "모집"]
                ):
                    skip_until_content = False
                    content_found = True
                else:
                    continue

            # 내용 시작 후 바닥글 제거
            if content_found:
                # 푸터 섹션 감지
                if any(
                    keyword in line_stripped
                    for keyword in [
                        "부산테크노파크 서비스메뉴",
                        "전국테크노파크",
                        "BTP플랫폼",
                    ]
                ):
                    break
                # 이전/다음글 링크
                if (
                    "이전글" in line_stripped
                    or "다음글" in line_stripped
                    or "목록" in line_stripped
                ):
                    break

            # 유효한 라인 추가
            if not skip_until_content:
                cleaned_lines.append(line)

        return "\n".join(cleaned_lines)

    def _remove_blocks(self, content: str) -> str:
        """블록 단위로 불필요한 내용 제거"""

        # 대규모 네비게이션 블록 제거
        # 예: "  * [ 공고˙안내 ]" 로 시작하는 긴 메뉴 블록
        content = re.sub(
            r"  \* \[ 공고˙안내 \].*?(?=\n\n|\n  \* \[ 이전글|\n첨부파일|\n2025\.\d{2}\.\d{2}|\Z)",
            "",
            content,
            flags=re.DOTALL,
        )

        # 전국테크노파크 블록 제거
        content = re.sub(
            r"전국테크노파크\s*.*?전국테크노파크 바로가기 닫기",
            "",
            content,
            flags=re.DOTALL,
        )

        # BTP플랫폼 블록 제거
        content = re.sub(
            r"BTP플랫폼\s*.*?BTP플랫폼 바로가기 닫기", "", content, flags=re.DOTALL
        )

        # 이미지 블록 제거 (로고 등)
        content = re.sub(r"#  \[ !\[재단법인.*?\].*?\]", "", content, flags=re.DOTALL)

        return content

    def _final_cleanup(self, content: str) -> str:
        """최종 정리 작업"""

        # 연속된 빈 줄 제거 (3개 이상)
        content = re.sub(r"\n\n\n+", "\n\n", content)

        # 시작과 끝의 빈 줄 제거
        content = content.strip()

        # 특수 문자 정리
        content = re.sub(
            r"[^\w\s가-힣ㄱ-ㅎㅏ-ㅣ\.\,\(\)\[\]\-\+\*\~\!\@\#\$\%\^\&\=\:\;\"\'\?\/\n]",
            "",
            content,
        )

        return content

    def extract_valuable_content(self, content: str) -> str:
        """
        가치 있는 내용만 추출 (더 공격적인 정리)

        Args:
            content: 원본 MD 파일 내용

        Returns:
            가치 있는 내용만 추출된 텍스트
        """
        try:
            lines = content.split("\n")
            valuable_lines = []

            # 제목 찾기
            title_found = False
            content_started = False
            skip_navigation = False

            for i, line in enumerate(lines):
                line_stripped = line.strip()

                # 제목 라인 (첫 번째 #으로 시작하는 라인)
                if line_stripped.startswith("#") and not title_found:
                    # 중복된 제목 정리
                    if "공고" in line_stripped:
                        title_parts = line_stripped.split("공고")
                        if len(title_parts) > 1:
                            clean_title = title_parts[0] + "공고"
                            valuable_lines.append(clean_title)
                        else:
                            valuable_lines.append(line_stripped)
                    else:
                        valuable_lines.append(line_stripped)
                    title_found = True
                    continue

                # 메타데이터 섹션 건너뛰기
                if not content_started and (
                    "**" in line_stripped or "---" in line_stripped
                ):
                    continue

                # 네비게이션 섹션 건너뛰기 시작 감지
                if (
                    "공고안내" in line_stripped
                    or "전체메뉴" in line_stripped
                    or "로그인" in line_stripped
                ):
                    skip_navigation = True
                    continue

                # 실제 내용 시작 감지 (공고 번호나 중요한 내용)
                if not content_started and line_stripped:
                    # 공고 번호 패턴 감지
                    if re.search(r"공고.*제.*\d{4}-\d+호", line_stripped):
                        content_started = True
                        skip_navigation = False
                    # 게시일 패턴
                    elif "게시일" in line_stripped and re.search(
                        r"\d{4}\.\d{2}\.\d{2}", line_stripped
                    ):
                        content_started = True
                        skip_navigation = False
                    # 지원분야 패턴
                    elif "지원분야" in line_stripped or "산업분야" in line_stripped:
                        content_started = True
                        skip_navigation = False
                    # 사업 제목 패턴 (### 으로 시작)
                    elif line_stripped.startswith("###") and any(
                        keyword in line_stripped
                        for keyword in ["공고", "사업", "지원", "모집"]
                    ):
                        content_started = True
                        skip_navigation = False
                    # 중요한 내용 키워드
                    elif any(
                        keyword in line_stripped
                        for keyword in [
                            "지원대상",
                            "지원내용",
                            "신청방법",
                            "접수기간",
                            "문의처",
                        ]
                    ):
                        content_started = True
                        skip_navigation = False

                # 네비게이션 섹션 건너뛰기
                if skip_navigation:
                    continue

                # 내용 시작 후 처리
                if content_started:
                    # 불필요한 라인 건너뛰기
                    if self._is_valuable_line(line_stripped):
                        valuable_lines.append(line)
                    elif not line_stripped:  # 빈 줄 유지
                        valuable_lines.append(line)

            result = "\n".join(valuable_lines)
            return self._final_cleanup(result)

        except Exception as e:
            logger.error(f"가치 있는 내용 추출 중 오류: {e}")
            return content

    def _is_valuable_line(self, line: str) -> bool:
        """라인이 가치 있는 내용인지 판단"""

        # 빈 줄
        if not line:
            return True

        # 가치 있는 키워드 포함
        valuable_keywords = [
            "지원",
            "신청",
            "접수",
            "모집",
            "공고",
            "기간",
            "대상",
            "내용",
            "방법",
            "문의",
            "첨부",
            "제출",
            "서류",
            "기업",
            "사업",
            "프로그램",
            "지원금",
            "보조금",
            "기술",
            "연구",
            "개발",
            "혁신",
            "창업",
            "벤처",
            "스타트업",
        ]

        if any(keyword in line for keyword in valuable_keywords):
            return True

        # 불필요한 키워드 포함
        unwanted_keywords = [
            "mCode",
            "CMS",
            "새창열림",
            "새창내려받기",
            "logo",
            "Icon",
            "ico_",
            "전체메뉴",
            "서비스메뉴",
            "테크노파크",
            "플랫폼",
            "바로가기",
        ]

        if any(keyword in line for keyword in unwanted_keywords):
            return False

        # 날짜 패턴 (중요한 정보)
        if re.search(r"\d{4}\.\d{2}\.\d{2}", line):
            return True

        # 연락처 패턴
        if re.search(r"\d{3}-\d{3,4}-\d{4}", line):
            return True

        # 이메일 패턴
        if re.search(r"\w+@\w+\.\w+", line):
            return True

        # 일반 텍스트 (너무 짧지 않은)
        if len(line) > 5 and not line.startswith("[") and not line.startswith("*"):
            return True

        return False


# 전역 인스턴스
_md_cleaner = None


def get_md_cleaner() -> MDContentCleaner:
    """MDContentCleaner 싱글톤 인스턴스 반환"""
    global _md_cleaner
    if _md_cleaner is None:
        _md_cleaner = MDContentCleaner()
    return _md_cleaner


def clean_md_content(content: str, site_code: str = None) -> str:
    """
    MD 내용 정리 헬퍼 함수

    Args:
        content: 원본 MD 파일 내용
        site_code: 사이트 코드 (prv인 경우 URL 보존)

    Returns:
        정리된 MD 파일 내용
    """
    cleaner = get_md_cleaner()
    return cleaner.clean_md_content(content, site_code)


def extract_valuable_md_content(content: str) -> str:
    """
    가치 있는 MD 내용만 추출하는 헬퍼 함수

    Args:
        content: 원본 MD 파일 내용

    Returns:
        가치 있는 내용만 추출된 텍스트
    """
    cleaner = get_md_cleaner()
    return cleaner.extract_valuable_content(content)
