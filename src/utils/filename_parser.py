"""
파일명 스마트 파싱 유틸리티

DB의 attachment_filenames 필드를 안전하게 파싱합니다.
파일명에 쉼표가 포함된 경우에도 올바르게 처리합니다.
"""

import re
from typing import List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


# 지원 확장자 목록
SUPPORTED_EXTENSIONS = [
    'hwp', 'hwpx', 'pdf', 'docx', 'pptx', 'xlsx', 'xls',
    'md', 'txt',
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp',
    'zip', '7z', 'rar'
]


def smart_parse_filenames(filenames_str: str) -> List[str]:
    """
    파일명 문자열을 스마트 파싱합니다.

    1차: 확장자 기반 스마트 파싱 시도
    2차: 실패 시 단순 쉼표 구분자 사용

    Args:
        filenames_str: 쉼표로 구분된 파일명 문자열

    Returns:
        List[str]: 파싱된 파일명 리스트

    Examples:
        >>> smart_parse_filenames("파일1.hwp, 파일2.pdf")
        ['파일1.hwp', '파일2.pdf']

        >>> smart_parse_filenames("입주호실(405호, 15평).jpg, 공고.hwp")
        ['입주호실(405호, 15평).jpg', '공고.hwp']
    """
    if not filenames_str or not filenames_str.strip():
        return []

    try:
        # 1차 시도: 스마트 파싱 (확장자 기반)
        filenames = _smart_parse_by_extension(filenames_str)

        # 검증: 모든 파일명에 확장자가 있는지 확인
        invalid_count = sum(1 for f in filenames if not _has_valid_extension(f))

        if invalid_count == 0 and len(filenames) > 0:
            logger.debug(f"✓ 스마트 파싱 성공: {len(filenames)}개 파일")
            return filenames
        else:
            logger.warning(f"⚠️ 스마트 파싱 결과 불완전 (확장자 없는 파일: {invalid_count}개)")
            raise ValueError("스마트 파싱 실패")

    except Exception as e:
        # 2차 시도: 단순 쉼표 구분자
        logger.info(f"스마트 파싱 실패, 단순 구분자 사용: {e}")
        filenames = _simple_parse_by_comma(filenames_str)

        logger.debug(f"✓ 단순 파싱 완료: {len(filenames)}개 파일")
        return filenames


def _smart_parse_by_extension(filenames_str: str) -> List[str]:
    """
    확장자 패턴을 기준으로 파일명을 추출합니다.

    작동 원리:
    1. 확장자 패턴을 역방향으로 찾음
    2. 확장자를 찾으면 그 앞쪽으로 파일명 시작점을 찾음
       - 이전 확장자의 끝 또는
       - 문자열 시작 또는
       - 쉼표+공백 직후
    3. 시작점 ~ 확장자 끝까지를 하나의 파일명으로 추출

    Args:
        filenames_str: 파일명 문자열

    Returns:
        List[str]: 파싱된 파일명 리스트
    """
    # 확장자 패턴: .확장자
    ext_list = '|'.join(SUPPORTED_EXTENSIONS)
    # 패턴 설명:
    # \.                      - 점(.)
    # (hwp|pdf|...)           - 확장자
    pattern = rf'\.({ext_list})\s*'

    # 모든 확장자 위치 찾기
    matches = list(re.finditer(pattern, filenames_str, re.IGNORECASE))

    if not matches:
        raise ValueError("확장자 패턴을 찾을 수 없음")

    filenames = []

    # 각 확장자 매치에 대해 파일명 시작점 찾기
    for i, match in enumerate(matches):
        ext_end = match.end()  # 확장자 끝 위치

        # 파일명 시작점 찾기
        if i == 0:
            # 첫 번째 파일: 문자열 시작부터
            start = 0
        else:
            # 이후 파일: 이전 확장자 끝부터
            prev_ext_end = matches[i-1].end()

            # 이전 확장자 끝 ~ 현재 확장자 시작 사이에서
            # 쉼표로 구분된 부분 찾기
            between = filenames_str[prev_ext_end:match.start()]

            # 쉼표가 있으면 그 다음부터 시작
            comma_pos = between.find(',')
            if comma_pos >= 0:
                start = prev_ext_end + comma_pos + 1
            else:
                # 쉼표 없으면 이전 확장자 바로 다음부터
                # (이 경우는 비정상이지만 허용)
                start = prev_ext_end

        # 확장자 끝 직후의 쉼표까지 또는 다음 파일명 시작 전까지
        if i < len(matches) - 1:
            # 다음 확장자가 있으면, 현재 끝 ~ 다음 시작 사이에서 쉼표 찾기
            next_start = matches[i+1].start()
            between = filenames_str[ext_end:next_start]
            comma_pos = between.find(',')
            if comma_pos >= 0:
                end = ext_end + comma_pos
            else:
                end = ext_end
        else:
            # 마지막 파일: 문자열 끝까지
            end = len(filenames_str)

        filename = filenames_str[start:end].strip(' ,')

        if filename:
            filenames.append(filename)

    return filenames


def _simple_parse_by_comma(filenames_str: str) -> List[str]:
    """
    단순 쉼표 구분자로 파싱합니다.

    Args:
        filenames_str: 파일명 문자열

    Returns:
        List[str]: 파싱된 파일명 리스트
    """
    filenames = [f.strip() for f in filenames_str.split(',') if f.strip()]
    return filenames


def _has_valid_extension(filename: str) -> bool:
    """
    파일명에 유효한 확장자가 있는지 확인합니다.

    Args:
        filename: 파일명

    Returns:
        bool: 유효한 확장자가 있으면 True
    """
    suffix = Path(filename).suffix.lower().lstrip('.')
    return suffix in SUPPORTED_EXTENSIONS


def test_smart_parse():
    """스마트 파싱 테스트"""
    test_cases = [
        # 정상 케이스
        ("파일1.hwp, 파일2.pdf", ["파일1.hwp", "파일2.pdf"]),

        # 파일명에 쉼표 포함
        ("입주호실(405호, 15평).jpg, 입주호실(311호, 15평).zip",
         ["입주호실(405호, 15평).jpg", "입주호실(311호, 15평).zip"]),

        ("[공고] 2026 디노랩 통합 모집 (강남,부산,경남)_F.hwp, [포스터] 2026 디노랩 통합 모집 (강남,부산,경남)_F.jpg",
         ["[공고] 2026 디노랩 통합 모집 (강남,부산,경남)_F.hwp", "[포스터] 2026 디노랩 통합 모집 (강남,부산,경남)_F.jpg"]),

        ("2025년 임대형 스마트팜 청년농 추가모집(4-3동, 딸기) 공고문.hwp",
         ["2025년 임대형 스마트팜 청년농 추가모집(4-3동, 딸기) 공고문.hwp"]),

        ("[첨부2] 개인정보 이용동의 및 중복지원 금지,지원조건 이행 확약서.hwp",
         ["[첨부2] 개인정보 이용동의 및 중복지원 금지,지원조건 이행 확약서.hwp"]),

        # 여러 파일
        ("공고문.hwp, 신청서.pdf, 안내문.docx",
         ["공고문.hwp", "신청서.pdf", "안내문.docx"]),

        # 공백 처리
        ("파일1.hwp  ,  파일2.pdf  ,  파일3.jpg",
         ["파일1.hwp", "파일2.pdf", "파일3.jpg"]),
    ]

    print("\n" + "="*80)
    print("스마트 파싱 테스트")
    print("="*80 + "\n")

    passed = 0
    failed = 0

    for idx, (input_str, expected) in enumerate(test_cases, 1):
        result = smart_parse_filenames(input_str)

        if result == expected:
            print(f"✅ 테스트 #{idx} 통과")
            print(f"   입력: {input_str[:60]}{'...' if len(input_str) > 60 else ''}")
            print(f"   결과: {result}")
            passed += 1
        else:
            print(f"❌ 테스트 #{idx} 실패")
            print(f"   입력: {input_str[:60]}{'...' if len(input_str) > 60 else ''}")
            print(f"   예상: {expected}")
            print(f"   결과: {result}")
            failed += 1
        print()

    print("-"*80)
    print(f"결과: {passed}개 통과, {failed}개 실패")
    print("="*80)


if __name__ == "__main__":
    # 테스트 실행
    test_smart_parse()
