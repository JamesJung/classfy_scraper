#!/usr/bin/env python3
"""
Ollama 서버 동시 처리 성능 종합 테스트 프로그램

동시 요청 개수를 점진적으로 증가시키며 성능과 리소스 사용량을 측정합니다.
"""

import asyncio
import time
import json
import csv
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import sys
import argparse

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.logConfig import setup_logging
from ollama_performance_tester import OllamaPerformanceTester, PerformanceMetric, BatchMetric
from resource_monitor import RemoteResourceMonitor, MonitoringSession

logger = setup_logging(__name__)


@dataclass
class ExperimentResult:
    """실험 결과"""
    experiment_id: str
    concurrent_requests: int
    baseline_avg_response_time: float
    baseline_success_rate: float
    
    # 배치 성능
    batch_total_time: float
    batch_success_rate: float
    batch_average_response_time: float
    batch_throughput_rps: float
    batch_first_response_time: float
    batch_last_response_time: float
    
    # 리소스 사용량
    avg_cpu_percent: float
    max_cpu_percent: float
    avg_memory_percent: float
    max_memory_percent: float
    avg_gpu_utilization: float
    max_gpu_utilization: float
    avg_gpu_memory_percent: float
    max_gpu_memory_percent: float
    
    # 성능 비교
    speedup_ratio: float  # 기준선 대비 성능 향상 비율
    efficiency: float     # 리소스 효율성 (throughput / cpu_usage)
    
    # 품질 점수
    avg_quality_score: float
    quality_degradation: float  # 기준선 대비 품질 저하


class OllamaConcurrentTester:
    """Ollama 동시 처리 종합 테스터"""
    
    def __init__(self, 
                 ollama_url: str = "http://192.168.0.40:11434/api",
                 model: str = "gpt-oss:20b",
                 server_host: str = "192.168.0.40"):
        """
        Args:
            ollama_url: Ollama API URL
            model: 사용할 모델명  
            server_host: 리소스 모니터링할 서버 호스트
        """
        self.ollama_url = ollama_url
        self.model = model
        self.server_host = server_host
        
        self.performance_tester = None
        self.resource_monitor = None
        self.results: List[ExperimentResult] = []
    
    async def __aenter__(self):
        """비동기 컨텍스트 매니저 시작"""
        self.performance_tester = await OllamaPerformanceTester(
            ollama_url=self.ollama_url, 
            model=self.model
        ).__aenter__()
        
        self.resource_monitor = RemoteResourceMonitor(server_host=self.server_host)
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        if self.performance_tester:
            await self.performance_tester.__aexit__(exc_type, exc_val, exc_tb)
    
    def _get_sample_content_batch(self, batch_size: int) -> List[str]:
        """테스트용 샘플 콘텐츠 배치 생성"""
        contents = []
        sample_types = ["short", "medium", "long"]
        
        for i in range(batch_size):
            sample_type = sample_types[i % len(sample_types)]
            content = self.performance_tester.sample_texts[sample_type]
            contents.append(content)
        
        return contents
    
    async def _measure_baseline_performance(self, iterations: int = 5) -> Tuple[float, float, float]:
        """기준선 성능 측정 (순차 처리)"""
        logger.info(f"기준선 성능 측정 시작: {iterations}회")
        
        baseline_metrics = await self.performance_tester.baseline_performance(iterations)
        successful_metrics = [m for m in baseline_metrics if m.success]
        
        if not successful_metrics:
            return 0.0, 0.0, 0.0
        
        avg_response_time = sum(m.response_time for m in successful_metrics) / len(successful_metrics)
        success_rate = len(successful_metrics) / len(baseline_metrics)
        avg_quality_score = sum(m.response_quality_score for m in successful_metrics) / len(successful_metrics)
        
        logger.info(f"기준선 성능: 평균응답 {avg_response_time:.2f}초, 성공률 {success_rate:.2%}, 품질 {avg_quality_score:.3f}")
        return avg_response_time, success_rate, avg_quality_score
    
    async def _run_concurrent_experiment(self, 
                                       concurrent_count: int,
                                       baseline_avg_time: float,
                                       baseline_quality: float) -> ExperimentResult:
        """개별 동시 처리 실험 실행"""
        experiment_id = f"concurrent_{concurrent_count}_{int(time.time())}"
        logger.info(f"실험 시작: {concurrent_count}개 동시 요청")
        
        # 테스트 콘텐츠 준비
        contents = self._get_sample_content_batch(concurrent_count)
        
        # 리소스 모니터링 시작
        self.resource_monitor.start_monitoring()
        
        try:
            # 동시 요청 실행
            batch_result = await self.performance_tester.concurrent_requests(
                contents, batch_id=experiment_id
            )
            
            # 리소스 모니터링 중지
            monitoring_session = self.resource_monitor.stop_monitoring()
            
            # 성능 지표 계산
            speedup_ratio = baseline_avg_time / batch_result.average_response_time if batch_result.average_response_time > 0 else 0.0
            theoretical_max_speedup = concurrent_count
            efficiency = speedup_ratio / theoretical_max_speedup if theoretical_max_speedup > 0 else 0.0
            
            # 품질 점수 계산
            successful_metrics = [m for m in batch_result.individual_metrics if m.success]
            avg_quality_score = sum(m.response_quality_score for m in successful_metrics) / len(successful_metrics) if successful_metrics else 0.0
            quality_degradation = baseline_quality - avg_quality_score
            
            # CPU 효율성 계산 (throughput per CPU usage)
            cpu_efficiency = batch_result.throughput_rps / monitoring_session.avg_cpu_percent if monitoring_session and monitoring_session.avg_cpu_percent > 0 else 0.0
            
            result = ExperimentResult(
                experiment_id=experiment_id,
                concurrent_requests=concurrent_count,
                baseline_avg_response_time=baseline_avg_time,
                baseline_success_rate=1.0,  # 기준선은 항상 성공으로 가정
                
                batch_total_time=batch_result.total_time,
                batch_success_rate=batch_result.success_count / batch_result.concurrent_requests,
                batch_average_response_time=batch_result.average_response_time,
                batch_throughput_rps=batch_result.throughput_rps,
                batch_first_response_time=batch_result.first_response_time,
                batch_last_response_time=batch_result.last_response_time,
                
                avg_cpu_percent=monitoring_session.avg_cpu_percent if monitoring_session else 0.0,
                max_cpu_percent=monitoring_session.max_cpu_percent if monitoring_session else 0.0,
                avg_memory_percent=monitoring_session.avg_memory_percent if monitoring_session else 0.0,
                max_memory_percent=monitoring_session.max_memory_percent if monitoring_session else 0.0,
                avg_gpu_utilization=monitoring_session.avg_gpu_utilization if monitoring_session else 0.0,
                max_gpu_utilization=monitoring_session.max_gpu_utilization if monitoring_session else 0.0,
                avg_gpu_memory_percent=monitoring_session.avg_gpu_memory_percent if monitoring_session else 0.0,
                max_gpu_memory_percent=monitoring_session.max_gpu_memory_percent if monitoring_session else 0.0,
                
                speedup_ratio=speedup_ratio,
                efficiency=cpu_efficiency,
                
                avg_quality_score=avg_quality_score,
                quality_degradation=quality_degradation
            )
            
            logger.info(f"실험 완료: {concurrent_count}개 동시요청, 성능향상 {speedup_ratio:.2f}배")
            return result
            
        except Exception as e:
            logger.error(f"실험 실행 중 오류 ({concurrent_count}개): {e}")
            # 모니터링 중지
            try:
                self.resource_monitor.stop_monitoring()
            except:
                pass
            raise
    
    async def run_full_experiment(self, 
                                max_concurrent: int = 8,
                                baseline_iterations: int = 5,
                                step_size: int = 2) -> List[ExperimentResult]:
        """전체 실험 실행"""
        logger.info(f"Ollama 동시 처리 성능 실험 시작 (최대 {max_concurrent}개)")
        
        print("🧪 Ollama 서버 동시 처리 성능 실험")
        print(f"{'='*60}")
        print(f"서버: {self.server_host}")
        print(f"모델: {self.model}")
        print(f"최대 동시 요청: {max_concurrent}개")
        print(f"{'='*60}")
        
        # Phase 1: 기준선 성능 측정
        print(f"\n1️⃣ 기준선 성능 측정 ({baseline_iterations}회 순차 처리)")
        baseline_avg_time, baseline_success_rate, baseline_quality = await self._measure_baseline_performance(baseline_iterations)
        
        if baseline_avg_time == 0:
            print("❌ 기준선 성능 측정 실패")
            return []
        
        print(f"✅ 기준선 성능: 평균 {baseline_avg_time:.2f}초, 성공률 {baseline_success_rate:.1%}")
        
        # Phase 2: 동시 처리 실험
        print(f"\n2️⃣ 동시 처리 성능 실험")
        concurrent_counts = list(range(2, max_concurrent + 1, step_size))
        if max_concurrent not in concurrent_counts:
            concurrent_counts.append(max_concurrent)
        
        results = []
        
        for i, concurrent_count in enumerate(concurrent_counts, 1):
            print(f"\n[{i}/{len(concurrent_counts)}] {concurrent_count}개 동시 요청 테스트...")
            
            try:
                result = await self._run_concurrent_experiment(
                    concurrent_count, baseline_avg_time, baseline_quality
                )
                results.append(result)
                
                # 실시간 결과 출력
                print(f"  ✅ 완료: {result.batch_success_rate:.1%} 성공")
                print(f"     총 소요: {result.batch_total_time:.1f}초")
                print(f"     처리량: {result.batch_throughput_rps:.2f} RPS")
                print(f"     성능향상: {result.speedup_ratio:.2f}배")
                print(f"     CPU 사용: {result.avg_cpu_percent:.1f}%")
                
                # 성능 저하 감지
                if result.speedup_ratio < 1.0:
                    print(f"  ⚠️ 성능 저하 감지: {result.speedup_ratio:.2f}배")
                
                # 실패율 높음 감지
                if result.batch_success_rate < 0.8:
                    print(f"  ⚠️ 높은 실패율: {result.batch_success_rate:.1%}")
                
            except Exception as e:
                print(f"  ❌ 실험 실패: {e}")
                logger.error(f"동시 요청 {concurrent_count}개 실험 실패: {e}")
        
        self.results = results
        return results
    
    def analyze_results(self) -> Dict[str, Any]:
        """실험 결과 분석"""
        if not self.results:
            return {}
        
        # 최적 성능 지점 찾기
        best_speedup = max(self.results, key=lambda r: r.speedup_ratio)
        best_throughput = max(self.results, key=lambda r: r.batch_throughput_rps)
        best_efficiency = max(self.results, key=lambda r: r.efficiency)
        
        # 안정성 기준 (성공률 95% 이상)
        stable_results = [r for r in self.results if r.batch_success_rate >= 0.95]
        best_stable = max(stable_results, key=lambda r: r.speedup_ratio) if stable_results else None
        
        analysis = {
            "total_experiments": len(self.results),
            "best_speedup": {
                "concurrent_count": best_speedup.concurrent_requests,
                "speedup_ratio": best_speedup.speedup_ratio,
                "success_rate": best_speedup.batch_success_rate
            },
            "best_throughput": {
                "concurrent_count": best_throughput.concurrent_requests,
                "throughput_rps": best_throughput.batch_throughput_rps,
                "success_rate": best_throughput.batch_success_rate
            },
            "best_efficiency": {
                "concurrent_count": best_efficiency.concurrent_requests,
                "efficiency": best_efficiency.efficiency,
                "cpu_usage": best_efficiency.avg_cpu_percent
            },
            "recommended_stable": {
                "concurrent_count": best_stable.concurrent_requests if best_stable else None,
                "speedup_ratio": best_stable.speedup_ratio if best_stable else None,
                "success_rate": best_stable.batch_success_rate if best_stable else None
            } if best_stable else None
        }
        
        return analysis
    
    def print_summary_report(self):
        """실험 결과 요약 보고서 출력"""
        if not self.results:
            print("❌ 실험 결과가 없습니다")
            return
        
        analysis = self.analyze_results()
        
        print(f"\n📊 Ollama 동시 처리 성능 실험 결과 요약")
        print(f"{'='*60}")
        print(f"총 실험 횟수: {analysis['total_experiments']}개")
        
        # 최고 성능 지점
        print(f"\n🏆 최고 성능 향상:")
        best = analysis['best_speedup']
        print(f"   동시 요청 수: {best['concurrent_count']}개")
        print(f"   성능 향상: {best['speedup_ratio']:.2f}배")
        print(f"   성공률: {best['success_rate']:.1%}")
        
        # 최고 처리량
        print(f"\n⚡ 최고 처리량:")
        throughput = analysis['best_throughput']
        print(f"   동시 요청 수: {throughput['concurrent_count']}개")
        print(f"   처리량: {throughput['throughput_rps']:.2f} RPS")
        print(f"   성공률: {throughput['success_rate']:.1%}")
        
        # 권장 설정
        recommended = analysis.get('recommended_stable')
        if recommended:
            print(f"\n✅ 권장 설정 (안정성 우선):")
            print(f"   동시 요청 수: {recommended['concurrent_count']}개")
            print(f"   성능 향상: {recommended['speedup_ratio']:.2f}배")
            print(f"   성공률: {recommended['success_rate']:.1%}")
        else:
            print(f"\n⚠️ 안정적인 설정을 찾지 못함 (성공률 95% 이상 없음)")
        
        # 상세 결과 테이블
        print(f"\n📋 상세 실험 결과:")
        print(f"{'동시요청':<8} {'성능향상':<8} {'처리량':<8} {'성공률':<8} {'CPU':<8} {'GPU':<8}")
        print(f"{'-'*50}")
        
        for result in sorted(self.results, key=lambda r: r.concurrent_requests):
            print(f"{result.concurrent_requests:<8} "
                  f"{result.speedup_ratio:<8.2f} "
                  f"{result.batch_throughput_rps:<8.2f} "
                  f"{result.batch_success_rate:<8.1%} "
                  f"{result.avg_cpu_percent:<8.1f} "
                  f"{result.avg_gpu_utilization:<8.1f}")
    
    def save_detailed_results(self, filepath: str = None):
        """상세 결과를 CSV 파일로 저장"""
        if not self.results:
            return
        
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"ollama_concurrent_test_results_{timestamp}.csv"
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=list(asdict(self.results[0]).keys()))
                writer.writeheader()
                
                for result in self.results:
                    writer.writerow(asdict(result))
            
            print(f"💾 상세 결과 저장됨: {filepath}")
            logger.info(f"실험 결과 저장: {filepath}")
            
        except Exception as e:
            print(f"❌ 결과 저장 실패: {e}")
            logger.error(f"결과 저장 실패: {e}")


async def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description='Ollama 동시 처리 성능 테스트')
    parser.add_argument('--max-concurrent', type=int, default=8, help='최대 동시 요청 수')
    parser.add_argument('--baseline-iterations', type=int, default=5, help='기준선 측정 반복 횟수')
    parser.add_argument('--step-size', type=int, default=2, help='동시 요청 수 증가 단위')
    parser.add_argument('--quick', action='store_true', help='빠른 테스트 (2, 4개만)')
    parser.add_argument('--output', type=str, help='결과 저장 파일명')
    
    args = parser.parse_args()
    
    if args.quick:
        args.max_concurrent = 4
        args.baseline_iterations = 3
    
    async with OllamaConcurrentTester() as tester:
        results = await tester.run_full_experiment(
            max_concurrent=args.max_concurrent,
            baseline_iterations=args.baseline_iterations,
            step_size=args.step_size
        )
        
        # 결과 분석 및 출력
        tester.print_summary_report()
        
        # 결과 저장
        tester.save_detailed_results(args.output)
        
        print(f"\n🎉 실험 완료! 총 {len(results)}개 실험 수행됨")


if __name__ == "__main__":
    asyncio.run(main())