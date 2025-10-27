#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
인코딩 자동 검증 및 복구 유틸리티

Mojibake (한글 인코딩 오류) 자동 감지 및 복구
"""

import re
from typing import Tuple, Optional


class EncodingValidator:
    """인코딩 자동 검증 및 복구"""

    def validate_and_fix(self, text: str) -> Tuple[str, bool, str]:
        """
        텍스트 검증 및 자동 복구

        Args:
            text: 검증할 텍스트

        Returns:
            (fixed_text: str, was_fixed: bool, reason: str)
        """
        if not text:
            return text, False, "빈 텍스트"

        # 1. Mojibake 감지
        if self._has_mojibake(text):
            fixed = self._fix_mojibake(text)
            if self._is_better(fixed, text):
                return fixed, True, "Mojibake 자동 복구"

        # 2. 제어 문자 제거
        if self._has_control_chars(text):
            fixed = self._remove_control_chars(text)
            return fixed, True, "제어 문자 제거"

        # 3. 한글 비율 검증
        korean_ratio = self._get_korean_ratio(text)
        if korean_ratio < 0.01 and len(text) > 100:
            return text, False, f"⚠️ 한글 비율 낮음 ({korean_ratio:.2%})"

        return text, False, "검증 통과"

    def _has_mojibake(self, text: str) -> bool:
        """Mojibake 패턴 감지"""
        # 키릴 문자 존재
        if re.search(r'[А-Яа-яЁё]', text):
            return True

        # 한글 자모만 있고 완성형 없음
        has_jamo = bool(re.search(r'[ㄱ-ㅎㅏ-ㅣ]', text))
        has_syllable = bool(re.search(r'[가-힣]', text))
        if has_jamo and not has_syllable:
            return True

        # Latin-1 특수 문자 패턴 (한글이 깨진 경우)
        if re.search(r'[ìîïòôöùûü]{3,}', text):
            return True

        return False

    def _fix_mojibake(self, text: str) -> str:
        """Mojibake 자동 복구"""
        # 여러 인코딩 조합 시도
        encodings = [
            ('latin1', 'utf-8'),
            ('latin1', 'cp949'),
            ('latin1', 'euc-kr'),
            ('iso-8859-1', 'utf-8'),
            ('cp1252', 'utf-8'),
        ]

        best_result = text
        best_korean_count = len(re.findall(r'[가-힣]', text))

        for encode_as, decode_as in encodings:
            try:
                bytes_data = text.encode(encode_as)
                decoded = bytes_data.decode(decode_as, errors='ignore')
                korean_count = len(re.findall(r'[가-힣]', decoded))

                if korean_count > best_korean_count:
                    best_korean_count = korean_count
                    best_result = decoded
            except Exception:
                continue

        return best_result

    def _has_control_chars(self, text: str) -> bool:
        """제어 문자 존재 확인"""
        return bool(re.search(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', text))

    def _remove_control_chars(self, text: str) -> str:
        """제어 문자 제거 (줄바꿈/탭 제외)"""
        return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

    def _get_korean_ratio(self, text: str) -> float:
        """한글 비율 계산"""
        if not text:
            return 0.0
        korean_count = len(re.findall(r'[가-힣]', text))
        return korean_count / len(text)

    def _is_better(self, fixed: str, original: str) -> bool:
        """복구된 텍스트가 더 나은지 판단"""
        fixed_korean = len(re.findall(r'[가-힣]', fixed))
        original_korean = len(re.findall(r'[가-힣]', original))

        # 한글이 50% 이상 증가하면 복구 성공
        return fixed_korean > original_korean * 1.5


class JSONSanitizer:
    """JSON 이스케이프 자동 수정"""

    def sanitize(self, json_str: str) -> Tuple[str, bool, str]:
        """
        JSON 이스케이프 시퀀스 자동 수정

        Args:
            json_str: JSON 문자열

        Returns:
            (fixed_json: str, was_fixed: bool, reason: str)
        """
        if not json_str:
            return json_str, False, "빈 문자열"

        # 유효하지 않은 이스케이프 패턴 찾기
        invalid_escapes = self._find_invalid_escapes(json_str)

        if not invalid_escapes:
            return json_str, False, "검증 통과"

        # 자동 수정
        fixed = self._fix_invalid_escapes(json_str)

        return fixed, True, f"이스케이프 수정: {', '.join(set(invalid_escapes))}"

    def _find_invalid_escapes(self, text: str) -> list:
        """유효하지 않은 이스케이프 시퀀스 찾기"""
        valid_escapes = set('"\\' + '/bfnrtu')
        invalid = []

        # \x 패턴 찾기
        pattern = r'\\(.)'
        for match in re.finditer(pattern, text):
            escaped_char = match.group(1)
            if escaped_char not in valid_escapes:
                invalid.append(f'\\{escaped_char}')

        return invalid

    def _fix_invalid_escapes(self, text: str) -> str:
        """유효하지 않은 이스케이프 자동 수정"""
        valid_escapes = set('"\\' + '/bfnrtu')

        def fix_escape(match):
            escaped_char = match.group(1)
            if escaped_char in valid_escapes:
                return match.group(0)  # 유효한 건 그대로
            else:
                # 백슬래시를 이스케이프 처리
                return '\\\\' + escaped_char

        return re.sub(r'\\(.)', fix_escape, text)


def test_encoding_validator():
    """EncodingValidator 테스트"""
    validator = EncodingValidator()

    print("=" * 80)
    print("EncodingValidator 테스트")
    print("=" * 80)

    test_cases = [
        ("정상 텍스트입니다. 지원대상자", "정상 케이스"),
        ("вқҚ м§ҖмӣҗлҢҖмғҒ", "키릴 문자 (Mojibake)"),
        ("ì§ìëìì", "Latin-1 문자 (Mojibake)"),
        ("Hello World", "영문 (한글 비율 낮음)"),
    ]

    for text, description in test_cases:
        print(f"\n[{description}]")
        print(f"원본: {text[:50]}")
        fixed, was_fixed, reason = validator.validate_and_fix(text)
        print(f"결과: {'✅ 복구됨' if was_fixed else '⚪ 변경없음'}")
        print(f"이유: {reason}")
        if was_fixed:
            print(f"복구: {fixed[:50]}")


def test_json_sanitizer():
    """JSONSanitizer 테스트"""
    sanitizer = JSONSanitizer()

    print("\n" + "=" * 80)
    print("JSONSanitizer 테스트")
    print("=" * 80)

    test_cases = [
        ('{"test": "normal"}', "정상 JSON"),
        ('{"test": "\\d digit"}', "유효하지 않은 \\d"),
        ('{"test": "\\* asterisk"}', "유효하지 않은 \\*"),
        ('{"test": "\\n newline"}', "유효한 \\n"),
    ]

    for json_str, description in test_cases:
        print(f"\n[{description}]")
        print(f"원본: {json_str}")
        fixed, was_fixed, reason = sanitizer.sanitize(json_str)
        print(f"결과: {'✅ 수정됨' if was_fixed else '⚪ 변경없음'}")
        print(f"이유: {reason}")
        if was_fixed:
            print(f"수정: {fixed}")


if __name__ == '__main__':
    test_encoding_validator()
    test_json_sanitizer()
