#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
품질 모니터링 및 알림

처리 통계를 추적하고 임계값 초과 시 알림 발송
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional


class QualityMonitor:
    """품질 모니터링 및 알림"""

    def __init__(
        self,
        mojibake_threshold: float = 0.05,
        json_error_threshold: float = 0.05,
        success_threshold: float = 0.95
    ):
        """
        Args:
            mojibake_threshold: Mojibake 발생률 임계값 (기본 5%)
            json_error_threshold: JSON 오류율 임계값 (기본 5%)
            success_threshold: 최소 성공률 임계값 (기본 95%)
        """
        self.logger = logging.getLogger(__name__)
        self.alert_threshold = {
            'mojibake_rate': mojibake_threshold,
            'json_error_rate': json_error_threshold,
            'success_rate': success_threshold
        }

    def check_and_alert(self, stats: Dict[str, int]) -> List[str]:
        """
        통계 확인 및 알림

        Args:
            stats: 처리 통계
                {
                    'total': int,
                    'encoding_fixed': int,
                    'json_fixed': int,
                    'failed': int
                }

        Returns:
            발생한 알림 리스트
        """
        total = stats.get('total', 0)
        if total == 0:
            return []

        # 비율 계산
        mojibake_rate = stats.get('encoding_fixed', 0) / total
        json_error_rate = stats.get('json_fixed', 0) / total
        success_rate = (total - stats.get('failed', 0)) / total

        alerts = []

        # 임계값 확인
        if mojibake_rate > self.alert_threshold['mojibake_rate']:
            alerts.append(
                f"⚠️ Mojibake 발생률 높음: {mojibake_rate:.2%} "
                f"(임계값: {self.alert_threshold['mojibake_rate']:.2%})"
            )

        if json_error_rate > self.alert_threshold['json_error_rate']:
            alerts.append(
                f"⚠️ JSON 오류율 높음: {json_error_rate:.2%} "
                f"(임계값: {self.alert_threshold['json_error_rate']:.2%})"
            )

        if success_rate < self.alert_threshold['success_rate']:
            alerts.append(
                f"⚠️ 성공률 낮음: {success_rate:.2%} "
                f"(임계값: {self.alert_threshold['success_rate']:.2%})"
            )

        # 알림 발송
        if alerts:
            self._send_alert(alerts, stats)

        return alerts

    def _send_alert(self, alerts: List[str], stats: Dict[str, int]):
        """알림 발송 (로그 기록)"""
        message = f"""
{'=' * 80}
[LLM 배치 품질 알림]
시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{chr(10).join(alerts)}

상세 통계:
- 총 처리: {stats.get('total', 0):,}건
- 인코딩 복구: {stats.get('encoding_fixed', 0):,}건
- JSON 복구: {stats.get('json_fixed', 0):,}건
- 실패: {stats.get('failed', 0):,}건
{'=' * 80}
"""

        # 로그 기록
        self.logger.warning(message)

        # 콘솔 출력
        print(message)

    def print_summary(self, stats: Dict[str, int]):
        """통계 요약 출력"""
        total = stats.get('total', 0)
        if total == 0:
            print("처리된 항목이 없습니다.")
            return

        encoding_fixed = stats.get('encoding_fixed', 0)
        json_fixed = stats.get('json_fixed', 0)
        failed = stats.get('failed', 0)
        succeeded = total - failed

        # 비율 계산
        success_rate = (succeeded / total) * 100
        encoding_rate = (encoding_fixed / total) * 100
        json_rate = (json_fixed / total) * 100
        failure_rate = (failed / total) * 100

        print("\n" + "=" * 80)
        print("📊 처리 통계 요약")
        print("=" * 80)
        print(f"총 처리:        {total:,}건")
        print(f"성공:           {succeeded:,}건 ({success_rate:.2f}%)")
        print(f"실패:           {failed:,}건 ({failure_rate:.2f}%)")
        print()
        print(f"인코딩 자동복구: {encoding_fixed:,}건 ({encoding_rate:.2f}%)")
        print(f"JSON 자동복구:   {json_fixed:,}건 ({json_rate:.2f}%)")
        print()

        # 자동 복구 성공률
        auto_recovery_attempts = encoding_fixed + json_fixed
        if auto_recovery_attempts > 0:
            # 복구 시도 중 실패하지 않은 것들이 복구 성공
            auto_recovery_success = auto_recovery_attempts - failed
            auto_recovery_rate = (auto_recovery_success / auto_recovery_attempts) * 100
            print(f"자동 복구 성공률: {auto_recovery_rate:.2f}% "
                  f"({auto_recovery_success}/{auto_recovery_attempts})")

        print("=" * 80)


def test_quality_monitor():
    """QualityMonitor 테스트"""
    print("=" * 80)
    print("QualityMonitor 테스트")
    print("=" * 80)

    # 로깅 설정
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    monitor = QualityMonitor(
        mojibake_threshold=0.05,
        json_error_threshold=0.05,
        success_threshold=0.95
    )

    # 테스트 케이스 1: 정상 (알림 없음)
    print("\n[테스트 1: 정상 통계 (알림 없음)]")
    stats1 = {
        'total': 1000,
        'encoding_fixed': 10,  # 1%
        'json_fixed': 5,        # 0.5%
        'failed': 2             # 0.2%
    }
    alerts1 = monitor.check_and_alert(stats1)
    print(f"발생한 알림: {len(alerts1)}개")
    monitor.print_summary(stats1)

    # 테스트 케이스 2: 높은 오류율 (알림 발생)
    print("\n" + "=" * 80)
    print("[테스트 2: 높은 오류율 (알림 발생)]")
    stats2 = {
        'total': 100,
        'encoding_fixed': 10,  # 10% (임계값 5% 초과)
        'json_fixed': 8,       # 8% (임계값 5% 초과)
        'failed': 15           # 15% (성공률 85%, 임계값 95% 미달)
    }
    alerts2 = monitor.check_and_alert(stats2)
    print(f"발생한 알림: {len(alerts2)}개")
    for alert in alerts2:
        print(f"  - {alert}")
    monitor.print_summary(stats2)


if __name__ == '__main__':
    test_quality_monitor()
