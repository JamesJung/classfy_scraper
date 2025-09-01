import time

from src.config.logConfig import setup_logging

# 로깅 설정
logger = setup_logging(__name__)


# Timer 유틸리티 사용법 및 옵션 설명
#
# [기본 사용법]
#   with Timer("LLM API 요청"):
#     # 실행할 코드
#
# [누적 시간 측정]
#   with Timer("LLM API 요청", totalTimeChk=True):
#     # 실행할 코드
#
# [옵션 설명]
#   totalTimeChk=True  : 여러 번 Timer를 사용할 때, 실행 시간을 누적하여 합산합니다.
#                        (예: 여러 LLM API 호출의 총 소요시간 측정)
#   totalTimeChk=False : 해당 with 블록의 실행 시간만 측정합니다. (기본값)
#
# [누적 시간 활용]
#   Timer.total_time  # 지금까지 누적된 총 소요시간(초)
#   Timer.count       # 누적 측정된 Timer 사용 횟수
#
# [누적 시간 리셋]
#   Timer.total_time = 0.0
#   Timer.count = 0
#
# [로그 예시]
#   [LLM API 요청] 시작
#   [LLM API 요청] 종료 - 소요시간: 1.23초
#
# [참고]
#   main.py 등에서 Timer.total_time, Timer.count를 활용해 전체 처리 시간을 출력할 수 있습니다.
class Timer:
    total_time = 0.0
    count = 0

    def __init__(self, name, totalTimeChk=False):
        self.name = name
        self.start = None
        self.totalTimeChk = totalTimeChk

    def __enter__(self):
        self.start = time.time()
        logger.info(f"[{self.name}] 시작")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        elapsed = time.time() - self.start
        if self.totalTimeChk:
            Timer.total_time += elapsed
            Timer.count += 1
        logger.info(f"[{self.name}] 종료 - 소요시간: {elapsed:.2f}초")
        return False  # 예외를 상위로 전파
