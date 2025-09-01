"""
커스텀 HWP/HWPX 처리 모듈
Custom HWP/HWPX Processing Module

gethwp 라이브러리의 read_hwpx 함수를 개선된 로직으로 오버라이드합니다.
Overrides gethwp library's read_hwpx function with improved logic.
"""

import io
import traceback
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from src.config.logConfig import setup_logging

# 로깅 설정
logger = setup_logging(__name__)


def read_hwpx(hwpx_file_path):
    """
    개선된 HWPX 파일 텍스트 추출 함수

    원본 gethwp.read_hwpx를 대체하는 개선된 구현:
    - 메모리 효율적인 ZIP 파일 처리
    - 네임스페이스 인식 XML 파싱
    - 더 정확한 텍스트 추출

    Args:
        hwpx_file_path: HWPX 파일 경로 (str 또는 Path)

    Returns:
        str: 추출된 텍스트 내용

    Raises:
        Exception: 파일 읽기 또는 파싱 실패시
    """
    # Path 객체로 변환 (문자열인 경우)
    if isinstance(hwpx_file_path, str):
        hwpx_file_path = Path(hwpx_file_path)

    logger.debug(f"커스텀 HWPX 텍스트 추출 시작: {hwpx_file_path.name}")

    try:
        # 메모리 상에서 ZIP 파일 읽기
        with open(hwpx_file_path, "rb") as f:
            hwpx_file_bytes = f.read()

        text_parts = []
        with io.BytesIO(hwpx_file_bytes) as bytes_io:
            with zipfile.ZipFile(bytes_io, "r") as zip_ref:
                xml_files_found = 0

                for file_info in zip_ref.infolist():
                    if file_info.filename.startswith(
                        "Contents/"
                    ) and file_info.filename.endswith(".xml"):
                        xml_files_found += 1
                        logger.debug(f"XML 파일 처리 중: {file_info.filename}")

                        try:
                            with zip_ref.open(file_info) as file:
                                # XML 파일 읽고 파싱하기
                                tree = ET.parse(file)
                                root = tree.getroot()

                                # <hp:t> 태그 내의 모든 텍스트를 추출
                                text_elements_found = 0
                                for elem in root.iter():
                                    # HWPX XML은 네임스페이스를 사용하므로, 태그 이름을 정확히 비교해야 합니다.
                                    # 'hp:t' 태그는 일반적으로 '{http://www.hancom.co.kr/hwpml/2011/hpml}t'와 같습니다.
                                    # endswith('}t')를 사용하면 네임스페이스 접두사가 바뀌어도 유연하게 대응할 수 있습니다.
                                    if (
                                        elem.tag.endswith("}t") or elem.tag == "t"
                                    ):  # <hp:t> 태그를 찾음
                                        full_text = "".join(elem.itertext())
                                        if full_text.strip():
                                            text_parts.append(full_text.strip())
                                            text_elements_found += 1

                                logger.debug(
                                    f"{file_info.filename}에서 {text_elements_found}개 텍스트 요소 추출"
                                )

                        except ET.ParseError as e:
                            logger.warning(
                                f"XML 파싱 오류 (건너뜀): {file_info.filename} - {e}"
                            )
                            continue
                        except Exception as e:
                            logger.warning(
                                f"XML 파일 처리 오류 (건너뜀): {file_info.filename} - {e}"
                            )
                            continue

                logger.debug(
                    f"총 {xml_files_found}개 XML 파일 처리, {len(text_parts)}개 텍스트 부분 추출"
                )

        result_text = "\n".join(text_parts)

        if result_text.strip():
            logger.info(
                f"커스텀 HWPX 텍스트 추출 성공: {hwpx_file_path.name} ({len(result_text)}자)"
            )
        else:
            logger.warning(
                f"커스텀 HWPX 텍스트 추출 결과가 비어있음: {hwpx_file_path.name}"
            )

        return result_text

    except zipfile.BadZipFile:
        logger.error(f"유효하지 않은 ZIP 파일 (HWPX): {hwpx_file_path.name}")
        raise Exception(f"Invalid HWPX file format: {hwpx_file_path.name}")

    except FileNotFoundError:
        logger.error(f"HWPX 파일을 찾을 수 없음: {hwpx_file_path}")
        raise Exception(f"HWPX file not found: {hwpx_file_path}")

    except Exception as e:
        logger.error(f"커스텀 HWPX 텍스트 추출 중 오류: {hwpx_file_path.name} - {e}")
        logger.debug(f"커스텀 HWPX 오류 상세:\n{traceback.format_exc()}")
        raise Exception(f"Failed to extract text from HWPX: {e}")


def read_hwp(hwp_file_path):
    """
    HWP 파일 읽기 - 원본 gethwp 함수로 위임

    이 함수는 기존 gethwp.read_hwp 함수를 그대로 사용합니다.
    필요시 나중에 커스텀 구현으로 대체할 수 있습니다.

    Args:
        hwp_file_path: HWP 파일 경로

    Returns:
        str: 추출된 텍스트 내용
    """
    try:
        # 원본 gethwp 라이브러리 import 및 호출
        import gethwp

        return gethwp.read_hwp(hwp_file_path)
    except Exception as e:
        logger.error(f"HWP 파일 읽기 실패: {hwp_file_path} - {e}")
        raise


# 호환성을 위한 다른 gethwp 함수들 (필요시 추가)
def get_hwp_version(hwp_file_path):
    """HWP 파일 버전 정보 조회 - 원본 gethwp 함수로 위임"""
    try:
        import gethwp

        return gethwp.get_hwp_version(hwp_file_path)
    except Exception as e:
        logger.warning(f"HWP 버전 조회 실패: {hwp_file_path} - {e}")
        return None


# 모듈이 직접 실행될 때 테스트 코드
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        print(f"Testing custom HWPX reader with: {test_file}")
        try:
            result = read_hwpx(test_file)
            print(f"Extracted {len(result)} characters")
            print("First 500 characters:")
            print(result[:500])
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("Usage: python hwp_custom.py <hwpx_file_path>")
