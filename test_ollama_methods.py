#!/usr/bin/env python3
"""
OllamaClient의 사용 가능한 메서드 확인 스크립트
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.ollamaClient import OllamaClient

def inspect_ollama_client():
    """OllamaClient의 메서드들을 확인합니다."""
    print("🔬 OllamaClient 메서드 확인")
    
    try:
        client = OllamaClient()
        print("✅ OllamaClient 초기화 완료")
        
        # 클라이언트의 모든 메서드 출력
        methods = [method for method in dir(client) if not method.startswith('_')]
        print(f"\n📋 사용 가능한 메서드들: {len(methods)}개")
        for method in methods:
            print(f"  - {method}")
            
        # analyze로 시작하는 메서드만 필터링
        analyze_methods = [method for method in methods if 'analyze' in method.lower()]
        print(f"\n🔍 분석 관련 메서드들: {len(analyze_methods)}개")
        for method in analyze_methods:
            print(f"  - {method}")
            
        # 각 메서드가 실제로 호출 가능한지 확인
        test_content = "테스트 내용"
        
        for method in analyze_methods:
            try:
                func = getattr(client, method)
                if callable(func):
                    print(f"\n✅ {method} - 호출 가능")
                    # 시그니처 확인
                    import inspect
                    sig = inspect.signature(func)
                    print(f"  시그니처: {method}{sig}")
                else:
                    print(f"\n❌ {method} - 호출 불가능")
            except Exception as e:
                print(f"\n❌ {method} - 에러: {e}")
        
    except Exception as e:
        print(f"❌ 오류: {e}")

if __name__ == "__main__":
    inspect_ollama_client()