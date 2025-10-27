#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
실패 케이스 자동 재시도 관리자

LLM 호출 실패 시 복구 전략을 적용하여 자동 재시도
"""

import time
import logging
from typing import Callable, Any, Optional, Tuple, List
from .encodingValidator import EncodingValidator


class RetryManager:
    """실패 케이스 자동 재시도"""

    def __init__(self, max_retries: int = 3, backoff_seconds: int = 5):
        """
        Args:
            max_retries: 최대 재시도 횟수
            backoff_seconds: 재시도 간 대기 시간 (초)
        """
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.logger = logging.getLogger(__name__)

    def retry_with_recovery(
        self,
        func: Callable,
        *args,
        recovery_funcs: Optional[List[Callable]] = None,
        **kwargs
    ) -> Tuple[Any, bool, int, Optional[str]]:
        """
        함수 실행 + 실패 시 복구 전략 적용 후 재시도

        Args:
            func: 실행할 함수
            recovery_funcs: 실패 시 적용할 복구 함수 리스트
            *args, **kwargs: func에 전달할 인자

        Returns:
            (result, success: bool, attempts: int, error: Optional[str])
        """
        recovery_funcs = recovery_funcs or []
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                if attempt > 1:
                    self.logger.info(f"✅ 재시도 성공 (시도: {attempt}회)")
                return result, True, attempt, None

            except Exception as e:
                last_error = e
                self.logger.warning(f"⚠️ 시도 {attempt}/{self.max_retries} 실패: {e}")

                # 복구 전략 적용
                if attempt < self.max_retries and recovery_funcs:
                    recovery_func = recovery_funcs[(attempt - 1) % len(recovery_funcs)]

                    self.logger.info(f"🔧 복구 전략 적용: {recovery_func.__name__}")
                    try:
                        args, kwargs = recovery_func(*args, **kwargs)
                    except Exception as recovery_error:
                        self.logger.error(f"복구 전략 적용 실패: {recovery_error}")

                # 백오프
                if attempt < self.max_retries:
                    wait_time = self.backoff_seconds * attempt
                    self.logger.info(f"⏳ {wait_time}초 후 재시도...")
                    time.sleep(wait_time)

        # 모든 시도 실패
        self.logger.error(f"❌ 모든 재시도 실패 ({self.max_retries}회)")
        return None, False, self.max_retries, str(last_error)


# 복구 전략 함수들

def recovery_fix_encoding(content: str, **kwargs) -> Tuple[tuple, dict]:
    """인코딩 복구 전략"""
    validator = EncodingValidator()
    fixed, was_fixed, reason = validator.validate_and_fix(content)

    if was_fixed:
        logging.info(f"🔧 인코딩 복구: {reason}")

    return (fixed,), kwargs


def recovery_simplify_content(content: str, **kwargs) -> Tuple[tuple, dict]:
    """콘텐츠 단순화 전략 (길이 제한)"""
    max_length = kwargs.get('max_length', 50000)

    if len(content) > max_length:
        simplified = content[:max_length] + "\n\n... (이하 생략)"
        logging.info(f"🔧 콘텐츠 단순화: {len(content)} → {len(simplified)} 문자")
        return (simplified,), kwargs

    return (content,), kwargs


def recovery_remove_special_chars(content: str, **kwargs) -> Tuple[tuple, dict]:
    """특수 문자 제거 전략"""
    import re
    # 한글, 영문, 숫자, 기본 구두점만 남김
    cleaned = re.sub(r'[^\w\s가-힣.,!?()[\]{}<>:;"\'\-]', '', content)

    removed_count = len(content) - len(cleaned)
    if removed_count > 0:
        logging.info(f"🔧 특수 문자 제거: {removed_count}개 문자 제거")

    return (cleaned,), kwargs


def recovery_extract_main_content(content: str, **kwargs) -> Tuple[tuple, dict]:
    """주요 콘텐츠 추출 전략 (앞부분만)"""
    # 앞부분 30%만 추출 (보통 중요한 내용이 앞에 있음)
    extract_ratio = 0.3
    extract_length = int(len(content) * extract_ratio)

    if extract_length < len(content):
        extracted = content[:extract_length] + "\n\n... (요약됨)"
        logging.info(f"🔧 주요 콘텐츠 추출: {len(content)} → {len(extracted)} 문자")
        return (extracted,), kwargs

    return (content,), kwargs


def test_retry_manager():
    """RetryManager 테스트"""
    print("=" * 80)
    print("RetryManager 테스트")
    print("=" * 80)

    # 로깅 설정
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    # 테스트 함수 (처음 2번은 실패, 3번째에 성공)
    attempt_count = [0]

    def flaky_function(text):
        attempt_count[0] += 1
        if attempt_count[0] < 3:
            raise ValueError(f"의도적 실패 (시도 {attempt_count[0]})")
        return f"성공: {text[:20]}..."

    # 재시도 관리자
    retry_manager = RetryManager(max_retries=3, backoff_seconds=1)

    print("\n[테스트 1: 재시도로 성공하는 케이스]")
    result, success, attempts, error = retry_manager.retry_with_recovery(
        flaky_function,
        "테스트 텍스트",
        recovery_funcs=[recovery_fix_encoding, recovery_simplify_content]
    )

    print(f"\n결과: {'✅ 성공' if success else '❌ 실패'}")
    print(f"시도 횟수: {attempts}")
    if success:
        print(f"반환값: {result}")
    else:
        print(f"오류: {error}")

    # 항상 실패하는 함수
    def always_fail(text):
        raise RuntimeError("항상 실패")

    print("\n" + "=" * 80)
    print("[테스트 2: 모든 재시도 실패하는 케이스]")
    retry_manager2 = RetryManager(max_retries=2, backoff_seconds=1)
    result, success, attempts, error = retry_manager2.retry_with_recovery(
        always_fail,
        "테스트 텍스트",
        recovery_funcs=[recovery_fix_encoding]
    )

    print(f"\n결과: {'✅ 성공' if success else '❌ 실패'}")
    print(f"시도 횟수: {attempts}")
    print(f"오류: {error}")


if __name__ == '__main__':
    test_retry_manager()
