"""
Ollama 기반 필드별 정보 추출 유틸리티

LangExtract 대신 Ollama를 직접 사용하여 필드별로 정보를 추출합니다.
각 필드별로 전문화된 프롬프트를 사용하여 정확도를 높입니다.
"""

import os
import json
import requests
import logging
from typing import Dict, Any, Optional

try:
    from src.config.logConfig import setup_logging
except ImportError:
    # 절대 import 시도
    import sys
    from pathlib import Path
    
    # 프로젝트 루트를 path에 추가
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    
    from src.config.logConfig import setup_logging

# 환경변수에서 로그 레벨 읽기
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO)
logger = setup_logging(__name__, log_level)


class OllamaFieldExtractor:
    """Ollama 기반 필드별 정보 추출기"""
    
    def __init__(self):
        # Ollama 설정
        self.model_id = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
        self.api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434").replace("/api", "").rstrip("/")
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "120"))
        
        logger.info(f"Ollama 필드 추출기 초기화 완료 - 모델: {self.model_id}, URL: {self.api_url}")
    
    def extract_all_fields(self, content: str) -> Dict[str, Any]:
        """
        공고 내용에서 모든 필드를 개별적으로 추출합니다.
        
        Args:
            content: 분석할 공고 내용 (content.md + 첨부파일)
            
        Returns:
            추출된 모든 필드 정보
        """
        logger.info("Ollama 필드별 추출 시작")
        
        results = {}
        
        # 각 필드별로 순차 추출
        fields = [
            "지원대상", "시행기관", "제목", "지원내용", 
            "지원금액", "등록일", "접수기간", "모집일정"
        ]
        
        for field in fields:
            try:
                logger.info(f"  📋 {field} 추출 중...")
                
                extracted_value = self._extract_single_field(field, content)
                results[field] = extracted_value
                
                # 결과 로깅
                if extracted_value and extracted_value.strip() and extracted_value != "찾을 수 없음":
                    logger.info(f"  ✓ {field} 추출 성공: {extracted_value[:50]}...")
                else:
                    logger.warning(f"  ⚠ {field} 추출 실패")
                    
            except Exception as e:
                logger.error(f"  ❌ {field} 추출 중 오류: {e}")
                results[field] = "찾을 수 없음"
        
        logger.info("Ollama 필드별 추출 완료")
        return results
    
    def _extract_single_field(self, field_name: str, content: str) -> str:
        """
        특정 필드만 추출합니다.
        
        Args:
            field_name: 추출할 필드명
            content: 분석할 내용
            
        Returns:
            추출된 값 또는 "찾을 수 없음"
        """
        try:
            # 필드별 전용 프롬프트 생성
            system_prompt, user_prompt = self._build_field_prompt(field_name, content)
            
            print(f"    🔍 {field_name} 추출 중...")
            
            # Ollama API 호출
            response = self._call_ollama(system_prompt, user_prompt)
            
            if not response:
                return "찾을 수 없음"
            
            # 결과 정제
            extracted = self._clean_extracted_value(response)
            
            return extracted if extracted else "찾을 수 없음"
            
        except Exception as e:
            print(f"    ❌ {field_name} 추출 오류: {e}")
            logger.error(f"{field_name} 추출 중 오류: {e}")
            return "찾을 수 없음"
    
    def _build_field_prompt(self, field_name: str, content: str) -> tuple[str, str]:
        """필드별 전용 프롬프트를 생성합니다."""
        
        system_prompts = {
            "지원대상": """당신은 공고 문서에서 지원대상을 정확히 찾는 전문가입니다.
공고 내용을 분석하여 누가 이 지원사업에 신청할 수 있는지만 간단명료하게 답변하세요.
예시: 중소기업, 소상공인, 개인사업자, 스타트업, 청년 등
찾을 수 없으면 "찾을 수 없음"이라고 답변하세요.""",
            
            "시행기관": """당신은 공고 문서에서 시행기관(주관기관)을 정확히 찾는 전문가입니다.
공고 내용을 분석하여 어느 기관에서 이 지원사업을 주관하는지만 간단명료하게 답변하세요.
예시: 중소벤처기업부, 서울시, 경기도, 한국산업기술진흥원 등
찾을 수 없으면 "찾을 수 없음"이라고 답변하세요.""",
            
            "제목": """당신은 공고 문서에서 정확한 제목을 찾는 전문가입니다.
공고 내용을 분석하여 공고의 공식 제목이나 사업명만 간단명료하게 답변하세요.
불필요한 기호나 번호는 제외하고 핵심 제목만 추출하세요.
찾을 수 없으면 "찾을 수 없음"이라고 답변하세요.""",
            
            "지원내용": """당신은 공고 문서에서 지원내용을 정확히 찾는 전문가입니다.
공고 내용을 분석하여 구체적으로 어떤 종류의 지원을 제공하는지만 간단명료하게 답변하세요.
예시: 사업비 지원, 교육 지원, 컨설팅 지원, 시설비 지원 등
찾을 수 없으면 "찾을 수 없음"이라고 답변하세요.""",
            
            "지원금액": """당신은 공고 문서에서 지원금액을 정확히 찾는 전문가입니다.
공고 내용을 분석하여 구체적인 지원 금액이나 범위만 간단명료하게 답변하세요.
예시: 최대 5,000만원, 3천만원 이내, 1억원 한도 등
찾을 수 없으면 "찾을 수 없음"이라고 답변하세요.""",
            
            "등록일": """당신은 공고 문서에서 공고 등록일(공고일)을 정확히 찾는 전문가입니다.
공고 내용을 분석하여 언제 이 공고가 등록되었는지만 간단명료하게 답변하세요.
접수기간이나 심사일정이 아닌 공고 자체의 등록일만 추출하세요.
찾을 수 없으면 "찾을 수 없음"이라고 답변하세요.""",
            
            "접수기간": """당신은 공고 문서에서 접수기간을 정확히 찾는 전문가입니다.
공고 내용을 분석하여 신청서를 언제부터 언제까지 받는지만 간단명료하게 답변하세요.
시작일과 종료일을 모두 포함해서 답변하세요.
찾을 수 없으면 "찾을 수 없음"이라고 답변하세요.""",
            
            "모집일정": """당신은 공고 문서에서 전체 모집일정을 정확히 찾는 전문가입니다.
공고 내용을 분석하여 접수기간, 심사일정, 발표일 등 전체적인 일정 정보를 간단명료하게 답변하세요.
찾을 수 없으면 "찾을 수 없음"이라고 답변하세요."""
        }
        
        system_prompt = system_prompts.get(field_name, f"공고 문서에서 {field_name}를 정확히 추출하세요.")
        user_prompt = f"다음 공고 내용에서 {field_name}을(를) 찾아주세요:\n\n{content[:3000]}..."  # 내용이 너무 길면 첫 3000자만 사용
        
        return system_prompt, user_prompt
    
    def _call_ollama(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Ollama API를 직접 호출합니다."""
        try:
            payload = {
                "model": self.model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9
                }
            }
            
            url = f"{self.api_url}/api/chat"
            logger.debug(f"Ollama API 호출: {url}")
            
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("message", {}).get("content", "")
                logger.debug(f"API 응답 성공, 내용 길이: {len(content)}")
                return content
            else:
                logger.error(f"Ollama API 오류 {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Ollama API 호출 중 오류: {e}")
            return None
    
    def _clean_extracted_value(self, raw_response: str) -> str:
        """추출된 값을 정제합니다."""
        if not raw_response:
            return "찾을 수 없음"
        
        # 기본 정제
        cleaned = raw_response.strip()
        
        # 찾을 수 없음 관련 응답들 처리
        if any(phrase in cleaned.lower() for phrase in ["찾을 수 없음", "없음", "해당없음", "정보없음", "찾지 못", "확인할 수 없"]):
            return "찾을 수 없음"
        
        # 너무 긴 응답은 잘라내기 (500자 제한)
        if len(cleaned) > 500:
            cleaned = cleaned[:500] + "..."
        
        return cleaned
    
    def test_ollama_connection(self) -> bool:
        """Ollama 연결 상태를 테스트합니다."""
        try:
            print(f"연결 테스트 시작 - 모델: {self.model_id}, URL: {self.api_url}")
            
            # 간단한 테스트
            response = self._call_ollama(
                "당신은 문서에서 연도를 찾는 전문가입니다.", 
                "다음 문서에서 연도를 찾아주세요: 테스트 문서입니다. 오늘은 2025년입니다."
            )
            
            if response and "2025" in response:
                print("✓ Ollama 연결 테스트 성공")
                return True
            else:
                print(f"❌ 연결은 되었으나 예상과 다른 응답: {response}")
                return False
                
        except Exception as e:
            print(f"❌ Ollama 연결 테스트 실패: {e}")
            return False


def extract_announcement_fields(content: str) -> Dict[str, str]:
    """
    공고 내용에서 모든 필드를 Ollama로 추출하는 편의 함수
    
    Args:
        content: 분석할 공고 내용
        
    Returns:
        필드별 추출 결과
    """
    extractor = OllamaFieldExtractor()
    return extractor.extract_all_fields(content)


if __name__ == "__main__":
    # 테스트용
    test_content = """
    2025년 중소기업 기술개발지원사업 공고
    
    ○ 시행기관: 중소벤처기업부
    ○ 지원대상: 중소기업, 소상공인
    ○ 지원금액: 최대 5,000만원
    ○ 접수기간: 2025년 3월 1일 ~ 2025년 3월 31일
    ○ 지원내용: 기술개발비, 인건비, 장비구입비 지원
    ○ 등록일: 2025년 2월 15일
    """

    # Ollama 연결 테스트
    extractor = OllamaFieldExtractor()
    
    if extractor.test_ollama_connection():
        print("✓ Ollama 연결 성공")
        
        # 필드별 추출 테스트
        print("\n=== 필드별 추출 테스트 ===")
        results = extract_announcement_fields(test_content)
        
        for field, value in results.items():
            status = "✓" if value != "찾을 수 없음" else "✗"
            print(f"{status} {field}: {value}")
            
    else:
        print("❌ Ollama 연결 실패")
        print("다음을 확인해주세요:")
        print("1. Ollama가 실행 중인지 확인")
        print("2. ollama serve 명령으로 서버 시작") 
        print(f"3. 모델이 설치되었는지: ollama pull {extractor.model_id}")
        print(f"4. API URL이 올바른지: {extractor.api_url}")