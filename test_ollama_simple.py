#!/usr/bin/env python3
"""
Ollama 연결 테스트 스크립트
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.logConfig import setup_logging
from src.utils.ollamaClient import OllamaClient

logger = setup_logging(__name__)

def test_ollama():
    """Ollama 클라이언트 테스트"""
    print("🔬 Ollama 클라이언트 테스트 시작")
    
    try:
        client = OllamaClient()
        print("✅ OllamaClient 초기화 완료")
        
        test_content = """# 2025년 중소기업 창업 지원사업 공고

## 사업개요
- 사업기간: 2025.1.1 ~ 2025.12.31
- 지원대상: 창업 3년 이내 중소기업
- 지원내용: 사업비의 70% 지원 (최대 5천만원)

## 신청방법
- 접수기간: 2025.1.15 ~ 2025.2.15
- 제출처: 중소벤처기업부

## 문의처
- 담당자: 홍길동 (02-1234-5678)
"""
        
        print("📋 테스트 내용 분석 중...")
        response, prompt = client.analyze_announcement(test_content)
        
        if response:
            print("✅ 분석 성공!")
            print(f"IS_SUPPORT_PROGRAM: {response.get('IS_SUPPORT_PROGRAM')}")
            print(f"EXTRACTED_TARGET: {response.get('EXTRACTED_TARGET', 'N/A')}")
            print(f"EXTRACTED_AMOUNT: {response.get('EXTRACTED_AMOUNT', 'N/A')}")
        else:
            print("❌ 분석 실패 - 응답 없음")
            print(f"프롬프트 길이: {len(prompt) if prompt else 0}")
        
    except Exception as e:
        print(f"❌ 테스트 중 오류: {e}")
        logger.error(f"Ollama 테스트 실패: {e}")

if __name__ == "__main__":
    test_ollama()