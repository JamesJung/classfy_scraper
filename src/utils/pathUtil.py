import re
import unicodedata
import hashlib


def sanitize_path_component(text: str) -> str:
    """파일/디렉터리 이름에 사용할 안전한 컴포넌트로 정규화합니다.

    - 유니코드 NFKC 정규화
    - 금지 문자 치환: \\/:*?"<>|
    - 비어있거나 과도한 길이일 경우 해시 대체
    """
    if text is None:
        return hashlib.md5(b"none").hexdigest()[:16]

    original = str(text)
    normalized = unicodedata.normalize("NFKC", original).strip()

    # 금지 문자 치환
    safe = re.sub(r"[\\/:*?\"<>|]+", "_", normalized)

    # 공백만 남는 경우 방지
    if not safe or not safe.strip():
        return hashlib.md5(original.encode("utf-8", errors="ignore")).hexdigest()[:16]

    # 너무 긴 이름 방지 (예: 80자 초과 시 해시 대체)
    if len(safe) > 80:
        return hashlib.md5(safe.encode("utf-8", errors="ignore")).hexdigest()[:16]

    return safe

"""
경로 처리 유틸리티
환경에 독립적인 상대경로 처리를 위한 함수들
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def convert_to_relative_path(
    path: str | Path, base_dir: str = "data.origin"
) -> str:
    """
    절대경로를 프로젝트 기준 상대경로로 변환

    Args:
        path: 변환할 경로 (절대경로 또는 상대경로)
        base_dir: 기준 디렉토리 (기본값: "data.origin")

    Returns:
        상대경로 문자열

    Examples:
        convert_to_relative_path("/mnt/d/.../data.origin/acci/001_test")
        -> "data.origin/acci/001_test"

        convert_to_relative_path("data.origin/acci/001_test")
        -> "data.origin/acci/001_test" (이미 상대경로)
    """
    try:
        path_obj = Path(path)
        path_str = str(path_obj)

        # 이미 상대경로인 경우 (data.origin으로 시작)
        if path_str.startswith(base_dir):
            return path_str

        # 절대경로에서 data.origin 이후 부분 추출
        if base_dir in path_str:
            parts = path_str.split(base_dir)
            if len(parts) >= 2:
                relative_part = parts[-1].lstrip("/")
                result = f"{base_dir}/{relative_part}" if relative_part else base_dir
                logger.debug(f"경로 변환: {path} -> {result}")
                return result

        # data.origin이 없는 경우, Path.relative_to 사용 시도
        try:
            # 현재 작업 디렉토리 기준으로 상대경로 생성
            current_dir = Path.cwd()
            if path_obj.is_absolute() and path_obj.exists():
                relative_path = path_obj.relative_to(current_dir)
                return str(relative_path)
        except ValueError:
            pass

        # 모든 변환 실패 시 원본 경로의 마지막 부분만 사용
        logger.warning(f"경로 변환 실패, 원본 사용: {path}")
        return str(path)

    except Exception as e:
        logger.error(f"경로 변환 중 오류: {e}, 원본 사용: {path}")
        return str(path)


def get_relative_folder_path(folder_path: str | Path) -> str:
    """
    공고 폴더 경로를 DB 저장용 상대경로로 변환하는 편의 함수
    prv 사이트의 [시도]/[시군구]/공고 구조도 지원합니다.

    Args:
        folder_path: 공고 폴더 경로

    Returns:
        사이트코드/폴더명 형태의 상대경로 (data.origin 제외)

    Examples:
        "/mnt/.../data.origin/acci/001_test" -> "acci/001_test"
        "/mnt/.../data.origin/prv/서울/강남구/001_test" -> "prv/서울/강남구/001_test"
    """
    try:
        path_obj = Path(folder_path)
        parts = path_obj.parts

        # data.origin 위치 찾기
        data_origin_idx = next(
            (i for i, part in enumerate(parts) if part == "data.origin"), None
        )

        if data_origin_idx is not None:
            # data.origin 이후 부분만 추출
            remaining_parts = parts[data_origin_idx + 1 :]

            if remaining_parts:
                result = "/".join(remaining_parts).replace("\\", "/")
                logger.debug(f"경로 변환: {folder_path} -> {result}")
                return result

        # data.origin이 없는 경우, 기본 패턴 추출
        if len(parts) >= 2:
            # 마지막 두 부분 (사이트코드/폴더명)
            result = f"{parts[-2]}/{parts[-1]}"
            logger.debug(f"기본 패턴 변환: {folder_path} -> {result}")
            return result
        else:
            # 폴더명만
            result = path_obj.name
            logger.debug(f"폴더명만 변환: {folder_path} -> {result}")
            return result

    except Exception as e:
        logger.error(f"공고 폴더 경로 변환 중 오류: {folder_path} - {e}")
        # 폴백: 폴더명만 반환
        return Path(folder_path).name


def normalize_path_for_db(path: str | Path) -> str:
    """
    DB 저장용 경로 정규화
    - 절대경로를 상대경로로 변환
    - 슬래시 정규화
    - 환경에 독립적인 형태로 변환

    Args:
        path: 정규화할 경로

    Returns:
        정규화된 상대경로
    """
    relative_path = convert_to_relative_path(path)

    # 슬래시 정규화 (항상 forward slash 사용)
    normalized = relative_path.replace("\\", "/")

    return normalized


# 테스트 함수
def test_path_conversion():
    """경로 변환 테스트"""
    test_paths = [
        "/mnt/d/workspace/sources/grant_info-main/data.origin/acci/001_test",
        "data.origin/acci/001_test",
        "/some/other/path/data.origin/bacf/002_test",
        "relative/path/without/data_origin",
    ]

    print("경로 변환 테스트:")
    for test_path in test_paths:
        result = convert_to_relative_path(test_path)
        print(f"  {test_path}")
        print(f"  -> {result}")
        print()


if __name__ == "__main__":
    test_path_conversion()
