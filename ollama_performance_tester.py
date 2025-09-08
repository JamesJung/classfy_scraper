#!/usr/bin/env python3
"""
Ollama 서버 개별 성능 측정 모듈

단일 요청 및 동시 요청 성능을 측정하고 응답 품질을 검증합니다.
"""

import asyncio
import aiohttp
import time
import json
import statistics
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path
import sys

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.logConfig import setup_logging

logger = setup_logging(__name__)


@dataclass
class PerformanceMetric:
    """개별 요청 성능 메트릭"""
    request_id: str
    start_time: float
    end_time: float
    response_time: float
    success: bool
    error_message: str = ""
    response_size: int = 0
    http_status: int = 0
    content_length: int = 0
    response_quality_score: float = 0.0


@dataclass
class BatchMetric:
    """배치 처리 성능 메트릭"""
    batch_id: str
    concurrent_requests: int
    start_time: float
    end_time: float
    total_time: float
    first_response_time: float  # TTFR (Time To First Response)
    last_response_time: float   # TTL (Time To Last Response)
    individual_metrics: List[PerformanceMetric]
    success_count: int
    failure_count: int
    average_response_time: float
    median_response_time: float
    std_dev_response_time: float
    throughput_rps: float  # Requests Per Second


class OllamaPerformanceTester:
    """Ollama 서버 성능 테스터"""
    
    def __init__(self, 
                 ollama_url: str = "http://192.168.0.40:11434/api",
                 model: str = "gpt-oss:20b",
                 timeout: int = 120):
        """
        Args:
            ollama_url: Ollama API URL
            model: 사용할 모델명
            timeout: 요청 타임아웃 (초)
        """
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = timeout
        self.session = None
        
        # 테스트용 샘플 텍스트들 (다양한 길이)
        self.sample_texts = {
            "short": """2025년 중소기업 창업 지원사업 공고
지원대상: 창업 3년 이내 중소기업
지원금액: 최대 5천만원""",
            
            "medium": """2025년 중소기업 창업 지원사업 공고

## 사업개요
- 사업기간: 2025.1.1 ~ 2025.12.31
- 지원대상: 창업 3년 이내 중소기업
- 지원내용: 사업비의 70% 지원 (최대 5천만원)

## 신청방법
- 접수기간: 2025.1.15 ~ 2025.2.15
- 제출처: 중소벤처기업부

## 문의처
- 담당자: 홍길동 (02-1234-5678)""",
            
            "long": """2025년 중소기업 창업 지원사업 공고

## 1. 사업개요
- 사업명: 2025년 중소기업 창업 지원사업
- 사업기간: 2025.1.1 ~ 2025.12.31
- 사업예산: 총 100억원
- 지원대상: 창업 3년 이내 중소기업 (제조업, IT서비스업 우선)
- 지원내용: 사업비의 70% 지원 (최대 5천만원)

## 2. 지원 분야
### 2.1 제조업 분야
- 스마트 제조 기술
- 친환경 기술
- 바이오 기술
- 신소재 기술

### 2.2 IT서비스업 분야  
- 인공지능/빅데이터
- 사물인터넷(IoT)
- 클라우드 서비스
- 핀테크

## 3. 신청자격
- 사업자등록증을 보유한 중소기업
- 창업일로부터 3년 이내 기업
- 최근 3년간 국세 및 지방세 완납 기업
- 고용보험 가입 기업

## 4. 신청방법
- 접수기간: 2025.1.15 ~ 2025.2.15 (18:00까지)
- 접수방법: 온라인 접수 (www.smes.go.kr)
- 제출서류: 사업계획서, 재무제표, 사업자등록증 등

## 5. 선정절차
1차: 서류심사 (정량평가)
2차: 발표심사 (정성평가)
3차: 현장실사

## 6. 문의처
- 담당부서: 중소벤처기업부 창업지원과
- 담당자: 홍길동 과장
- 연락처: 02-1234-5678
- 이메일: startup@smes.go.kr"""
        }
        
    async def __aenter__(self):
        """비동기 컨텍스트 매니저 시작"""
        connector = aiohttp.TCPConnector(limit=50, limit_per_host=20)
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        self.session = aiohttp.ClientSession(
            connector=connector, 
            timeout=timeout,
            headers={'Content-Type': 'application/json'}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        if self.session:
            await self.session.close()
    
    def _create_ollama_payload(self, content: str) -> Dict[str, Any]:
        """Ollama API 요청 페이로드 생성"""
        system_prompt = """당신은 정부 및 공공기관의 공고문을 분석하는 전문가입니다.
주어진 공고 내용을 분석하여 다음 정보를 정확히 추출해주세요.

추출할 정보:
1. 지원대상: 누가 지원할 수 있는지
2. 지원금액: 지원받을 수 있는 금액
3. 제목: 공고의 제목
4. 지원사업 여부: 재정적 지원을 제공하는지 여부

JSON 형식으로 응답해주세요."""

        user_prompt = f"""다음 공고 내용을 분석해주세요:

{content}

=== 공고 내용 끝 ===

위 내용을 분석하여 JSON 형식으로 추출해주세요."""

        return {
            "model": self.model,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "top_p": 0.9,
                "num_predict": 2049,
            }
        }
    
    def _evaluate_response_quality(self, response_data: Dict[str, Any]) -> float:
        """응답 품질 점수 계산 (0.0 - 1.0)"""
        if not response_data or 'response' not in response_data:
            return 0.0
        
        response_text = response_data.get('response', '')
        score = 0.0
        
        # 1. 응답 길이 적절성 (0.2점)
        if 50 <= len(response_text) <= 2000:
            score += 0.2
        
        # 2. JSON 형식 여부 (0.3점)
        try:
            parsed = json.loads(response_text)
            if isinstance(parsed, dict):
                score += 0.3
        except:
            pass
        
        # 3. 필수 키워드 포함 여부 (0.3점)
        required_keywords = ['지원', '대상', '금액', '제목']
        keyword_count = sum(1 for keyword in required_keywords if keyword in response_text)
        score += (keyword_count / len(required_keywords)) * 0.3
        
        # 4. 응답 완료성 (0.2점)
        if not response_data.get('done', True):
            score -= 0.2
        else:
            score += 0.2
            
        return min(1.0, max(0.0, score))
    
    async def single_request(self, 
                           content: str, 
                           request_id: str = "single") -> PerformanceMetric:
        """단일 요청 성능 측정"""
        start_time = time.time()
        
        try:
            payload = self._create_ollama_payload(content)
            
            async with self.session.post(
                f"{self.ollama_url}/generate",
                json=payload
            ) as response:
                end_time = time.time()
                response_time = end_time - start_time
                
                if response.status == 200:
                    response_data = await response.json()
                    quality_score = self._evaluate_response_quality(response_data)
                    
                    return PerformanceMetric(
                        request_id=request_id,
                        start_time=start_time,
                        end_time=end_time,
                        response_time=response_time,
                        success=True,
                        response_size=len(str(response_data)),
                        http_status=response.status,
                        content_length=len(content),
                        response_quality_score=quality_score
                    )
                else:
                    error_text = await response.text()
                    return PerformanceMetric(
                        request_id=request_id,
                        start_time=start_time,
                        end_time=end_time,
                        response_time=response_time,
                        success=False,
                        error_message=f"HTTP {response.status}: {error_text}",
                        http_status=response.status,
                        content_length=len(content)
                    )
                    
        except asyncio.TimeoutError:
            end_time = time.time()
            return PerformanceMetric(
                request_id=request_id,
                start_time=start_time,
                end_time=end_time,
                response_time=end_time - start_time,
                success=False,
                error_message="Timeout",
                content_length=len(content)
            )
        except Exception as e:
            end_time = time.time()
            return PerformanceMetric(
                request_id=request_id,
                start_time=start_time,
                end_time=end_time,
                response_time=end_time - start_time,
                success=False,
                error_message=str(e),
                content_length=len(content)
            )
    
    async def concurrent_requests(self, 
                                contents: List[str], 
                                batch_id: str = "batch") -> BatchMetric:
        """동시 요청 성능 측정"""
        batch_start_time = time.time()
        
        # 비동기 태스크 생성
        tasks = []
        for i, content in enumerate(contents):
            request_id = f"{batch_id}_req_{i+1}"
            task = asyncio.create_task(self.single_request(content, request_id))
            tasks.append(task)
        
        # 모든 요청 실행 및 완료 대기
        results = await asyncio.gather(*tasks, return_exceptions=True)
        batch_end_time = time.time()
        
        # 결과 처리
        individual_metrics = []
        first_response_time = None
        last_response_time = None
        
        for result in results:
            if isinstance(result, Exception):
                # 예외 발생한 요청 처리
                metric = PerformanceMetric(
                    request_id="error",
                    start_time=batch_start_time,
                    end_time=batch_end_time,
                    response_time=batch_end_time - batch_start_time,
                    success=False,
                    error_message=str(result)
                )
            else:
                metric = result
            
            individual_metrics.append(metric)
            
            # 첫 번째/마지막 응답 시간 추적
            if metric.success:
                if first_response_time is None or metric.end_time < first_response_time:
                    first_response_time = metric.end_time
                if last_response_time is None or metric.end_time > last_response_time:
                    last_response_time = metric.end_time
        
        # 통계 계산
        success_metrics = [m for m in individual_metrics if m.success]
        success_count = len(success_metrics)
        failure_count = len(individual_metrics) - success_count
        
        if success_metrics:
            response_times = [m.response_time for m in success_metrics]
            average_response_time = statistics.mean(response_times)
            median_response_time = statistics.median(response_times)
            std_dev_response_time = statistics.stdev(response_times) if len(response_times) > 1 else 0.0
        else:
            average_response_time = 0.0
            median_response_time = 0.0
            std_dev_response_time = 0.0
        
        total_time = batch_end_time - batch_start_time
        throughput_rps = len(contents) / total_time if total_time > 0 else 0.0
        
        return BatchMetric(
            batch_id=batch_id,
            concurrent_requests=len(contents),
            start_time=batch_start_time,
            end_time=batch_end_time,
            total_time=total_time,
            first_response_time=(first_response_time - batch_start_time) if first_response_time else 0.0,
            last_response_time=(last_response_time - batch_start_time) if last_response_time else 0.0,
            individual_metrics=individual_metrics,
            success_count=success_count,
            failure_count=failure_count,
            average_response_time=average_response_time,
            median_response_time=median_response_time,
            std_dev_response_time=std_dev_response_time,
            throughput_rps=throughput_rps
        )
    
    async def baseline_performance(self, iterations: int = 10) -> List[PerformanceMetric]:
        """기준선 성능 측정 (단일 요청 반복)"""
        logger.info(f"기준선 성능 측정 시작: {iterations}회 반복")
        
        results = []
        for i in range(iterations):
            content = self.sample_texts["medium"]  # 중간 길이 텍스트 사용
            metric = await self.single_request(content, f"baseline_{i+1}")
            results.append(metric)
            
            # 진행상황 출력
            if (i + 1) % 5 == 0:
                success_count = sum(1 for r in results if r.success)
                avg_time = statistics.mean([r.response_time for r in results if r.success])
                logger.info(f"진행: {i+1}/{iterations}, 성공: {success_count}, 평균응답: {avg_time:.2f}초")
        
        return results
    
    def print_baseline_summary(self, results: List[PerformanceMetric]):
        """기준선 성능 결과 요약 출력"""
        success_results = [r for r in results if r.success]
        
        if not success_results:
            print("❌ 모든 요청 실패")
            return
        
        response_times = [r.response_time for r in success_results]
        quality_scores = [r.response_quality_score for r in success_results]
        
        print(f"\n📊 기준선 성능 측정 결과 ({len(results)}회 요청)")
        print(f"{'='*50}")
        print(f"성공률: {len(success_results)}/{len(results)} ({len(success_results)/len(results)*100:.1f}%)")
        print(f"평균 응답시간: {statistics.mean(response_times):.2f}초")
        print(f"중간값 응답시간: {statistics.median(response_times):.2f}초")
        print(f"표준편차: {statistics.stdev(response_times):.2f}초" if len(response_times) > 1 else "표준편차: N/A")
        print(f"최소 응답시간: {min(response_times):.2f}초")
        print(f"최대 응답시간: {max(response_times):.2f}초")
        print(f"평균 품질점수: {statistics.mean(quality_scores):.3f}")
        
        # 실패한 요청 정보
        failed_results = [r for r in results if not r.success]
        if failed_results:
            print(f"\n❌ 실패한 요청 ({len(failed_results)}개):")
            for i, r in enumerate(failed_results[:3], 1):  # 처음 3개만 표시
                print(f"  {i}. {r.error_message}")
    
    def print_batch_summary(self, result: BatchMetric):
        """배치 처리 결과 요약 출력"""
        print(f"\n📊 동시 요청 성능 측정 결과")
        print(f"{'='*50}")
        print(f"동시 요청 수: {result.concurrent_requests}개")
        print(f"총 소요시간: {result.total_time:.2f}초")
        print(f"성공률: {result.success_count}/{result.concurrent_requests} ({result.success_count/result.concurrent_requests*100:.1f}%)")
        print(f"처리량: {result.throughput_rps:.2f} RPS")
        print(f"첫 번째 응답: {result.first_response_time:.2f}초")
        print(f"마지막 응답: {result.last_response_time:.2f}초")
        
        if result.success_count > 0:
            print(f"평균 응답시간: {result.average_response_time:.2f}초")
            print(f"중간값 응답시간: {result.median_response_time:.2f}초")
            print(f"표준편차: {result.std_dev_response_time:.2f}초")
        
        # 실패한 요청 정보
        if result.failure_count > 0:
            print(f"\n❌ 실패한 요청 ({result.failure_count}개):")
            failed_metrics = [m for m in result.individual_metrics if not m.success]
            for i, m in enumerate(failed_metrics[:3], 1):  # 처음 3개만 표시
                print(f"  {i}. {m.request_id}: {m.error_message}")


async def main():
    """테스트 실행 예제"""
    async with OllamaPerformanceTester() as tester:
        print("🧪 Ollama 성능 테스트 시작")
        
        # 1. 기준선 성능 측정
        print("\n1️⃣ 기준선 성능 측정 (단일 요청 5회)")
        baseline_results = await tester.baseline_performance(5)
        tester.print_baseline_summary(baseline_results)
        
        # 2. 동시 요청 테스트
        print("\n2️⃣ 동시 요청 테스트 (2개)")
        contents = [tester.sample_texts["medium"], tester.sample_texts["short"]]
        batch_result = await tester.concurrent_requests(contents, "concurrent_2")
        tester.print_batch_summary(batch_result)


if __name__ == "__main__":
    asyncio.run(main())