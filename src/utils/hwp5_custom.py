"""
hwp5 라이브러리 커스텀 패치
Custom patches for hwp5 library

hwp5 라이브러리의 UnderlineStyle Enum에 누락된 값들을 추가합니다.
Adds missing values to hwp5 library's UnderlineStyle Enum.

문제:
- hwp5 라이브러리의 UnderlineStyle은 0-10까지만 정의됨
- 최신 HWP 파일은 15 등의 값을 사용
- 정의되지 않은 값을 만나면 무한 루프 발생

해결:
- UnderlineStyle에 값 11-20을 추가하여 미래 호환성 확보
- 한글과컴퓨터에서 추가한 새로운 밑줄 스타일 지원
"""

import logging
from hwp5.dataio import Enum

logger = logging.getLogger(__name__)


def patch_underline_style():
    """
    hwp5 라이브러리의 CharShape.UnderlineStyle에 누락된 값들을 추가합니다.

    원본 정의 (0-10):
        SOLID=0, DASHED=1, DOTTED=2, DASH_DOT=3, DASH_DOT_DOT=4,
        LONG_DASHED=5, LARGE_DOTTED=6, DOUBLE=7, LOWER_WEIGHTED=8,
        UPPER_WEIGHTED=9, MIDDLE_WEIGHTED=10

    추가 정의 (11-20):
        한글과컴퓨터에서 추가한 새로운 스타일들
        정확한 스타일 이름은 불명확하므로 UNKNOWN_XX로 정의
    """
    try:
        from hwp5.binmodel.tagid21_char_shape import CharShape

        # 현재 UnderlineStyle 확인
        original_style = CharShape.UnderlineStyle

        # 이미 패치되었는지 확인
        if hasattr(original_style, 'UNKNOWN_15'):
            logger.debug("UnderlineStyle 이미 패치됨")
            return True

        logger.info("UnderlineStyle 패치 시작...")

        # 새로운 UnderlineStyle 생성 (원본 + 추가 값)
        # 원본 값들
        original_values = {
            'SOLID': 0,
            'DASHED': 1,
            'DOTTED': 2,
            'DASH_DOT': 3,
            'DASH_DOT_DOT': 4,
            'LONG_DASHED': 5,
            'LARGE_DOTTED': 6,
            'DOUBLE': 7,
            'LOWER_WEIGHTED': 8,
            'UPPER_WEIGHTED': 9,
            'MIDDLE_WEIGHTED': 10,
        }

        # 누락된 값들 추가 (11-20)
        # 실제 스타일 이름은 한글과컴퓨터 문서 참조 필요
        extended_values = {
            'UNKNOWN_11': 11,
            'UNKNOWN_12': 12,
            'UNKNOWN_13': 13,
            'UNKNOWN_14': 14,
            'UNKNOWN_15': 15,  # 문제가 된 값
            'UNKNOWN_16': 16,
            'UNKNOWN_17': 17,
            'UNKNOWN_18': 18,
            'UNKNOWN_19': 19,
            'UNKNOWN_20': 20,
        }

        # 모든 값 병합
        all_values = {**original_values, **extended_values}

        # 새로운 Enum 생성
        # Enum() 함수는 *items (위치 인자)와 **moreitems (키워드 인자)를 받음
        # moreitems만 사용하여 모든 값을 지정
        patched_style = Enum(**all_values)

        # CharShape 클래스에 패치된 UnderlineStyle 적용
        CharShape.UnderlineStyle = patched_style

        # Flags도 업데이트해야 함 (UnderlineStyle을 참조하므로)
        from hwp5.dataio import Flags, UINT32

        CharShape.Flags = Flags(
            UINT32,
            0, 'italic',
            1, 'bold',
            2, 3, CharShape.Underline, 'underline',
            4, 7, patched_style, 'underline_style',  # 패치된 UnderlineStyle 사용
            8, 10, 'outline',
            11, 13, 'shadow'
        )

        logger.info(f"UnderlineStyle 패치 완료: {len(all_values)}개 값 정의됨")
        logger.debug(f"정의된 값: {list(all_values.keys())}")

        return True

    except Exception as e:
        logger.error(f"UnderlineStyle 패치 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def apply_all_patches():
    """
    모든 hwp5 라이브러리 패치를 적용합니다.

    Returns:
        bool: 모든 패치 성공 여부
    """
    logger.info("hwp5 라이브러리 커스텀 패치 적용 중...")

    success = True

    # UnderlineStyle 패치
    if not patch_underline_style():
        logger.warning("UnderlineStyle 패치 실패")
        success = False

    if success:
        logger.info("모든 hwp5 패치 적용 완료")
    else:
        logger.warning("일부 hwp5 패치 적용 실패")

    return success


# 모듈 import 시 자동으로 패치 적용
# convertUtil에서 이 모듈을 import하면 자동으로 패치됨
if __name__ != '__main__':
    # 라이브러리로 사용될 때만 자동 패치
    try:
        apply_all_patches()
    except Exception as e:
        logger.error(f"자동 패치 적용 실패: {e}")


# 테스트 실행
if __name__ == '__main__':
    # 직접 실행 시 테스트
    print("=== hwp5_custom.py 테스트 ===")
    print()

    # 패치 적용
    result = apply_all_patches()
    print(f"패치 결과: {'성공' if result else '실패'}")
    print()

    # 검증
    try:
        from hwp5.binmodel.tagid21_char_shape import CharShape

        print("UnderlineStyle 확인:")
        print(f"  타입: {type(CharShape.UnderlineStyle)}")

        # 원본 값 확인
        print("  원본 값:")
        for name in ['SOLID', 'DASHED', 'MIDDLE_WEIGHTED']:
            if hasattr(CharShape.UnderlineStyle, name):
                value = getattr(CharShape.UnderlineStyle, name)
                print(f"    {name} = {value}")

        # 추가된 값 확인
        print("  추가된 값:")
        for name in ['UNKNOWN_11', 'UNKNOWN_15', 'UNKNOWN_20']:
            if hasattr(CharShape.UnderlineStyle, name):
                value = getattr(CharShape.UnderlineStyle, name)
                print(f"    {name} = {value}")
            else:
                print(f"    {name} = 정의되지 않음 (패치 실패)")

        print()
        print("  값 15 생성 테스트:")
        try:
            style_15 = CharShape.UnderlineStyle(15)
            print(f"    CharShape.UnderlineStyle(15) = {style_15}")
            print(f"    이름: {style_15.name if hasattr(style_15, 'name') else 'N/A'}")
            print(f"    ✅ 값 15 처리 성공")
        except Exception as e:
            print(f"    ❌ 값 15 처리 실패: {e}")

    except Exception as e:
        print(f"검증 실패: {e}")
        import traceback
        traceback.print_exc()
