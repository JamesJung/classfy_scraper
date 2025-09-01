"""
LangExtract + Ollama를 이용한 필드별 정보 추출 유틸리티

각 필드별로 전문화된 추출을 수행하여 정확도를 높입니다:
- 지원대상, 시행기관, 제목, 지원내용, 지원금액, 등록일, 접수기간, 모집일정
"""

import os
import logging
import langextract as lx
import requests
import json
from typing import Dict, Any, Optional, List
from pathlib import Path

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


class LangExtractFieldAnalyzer:
    """LangExtract를 이용한 필드별 정보 추출기"""
    
    def __init__(self):
        # Ollama 설정 - 환경변수가 없으면 gemma2:latest 사용 (LangExtract 호환성)
        self.model_id = os.getenv("OLLAMA_MODEL", "gemma2:latest")
        self.model_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434").rstrip("/").rstrip("/api")
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "300"))
        
        # gpt-oss 모델의 thinking 필드 문제로 인해 gemma2 사용 권장
        if "gpt-oss" in self.model_id:
            logger.warning(f"gpt-oss 모델은 LangExtract와 호환성 문제가 있을 수 있습니다. gemma2:latest 사용을 권장합니다.")
            print(f"⚠️  {self.model_id} 모델 사용 중 - LangExtract 호환성 문제 가능")
        
        # LangExtract Ollama 설정 - 모델명을 명시적으로 포함
        self.language_model_params = {
            "model_url": f"{self.model_url}/api",
            "model_name": self.model_id,
            "timeout": self.timeout,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9
            }
        }
        
        logger.info(f"LangExtract 초기화 완료 - 모델: {self.model_id}, URL: {self.model_url}")
    
    def extract_all_fields(self, content: str) -> Dict[str, Any]:
        """
        공고 내용에서 모든 필드를 개별적으로 추출합니다.
        
        Args:
            content: 분석할 공고 내용 (content.md + 첨부파일)
            
        Returns:
            추출된 모든 필드 정보
        """
        logger.info("LangExtract 필드별 추출 시작")
        
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
        
        logger.info("LangExtract 필드별 추출 완료")
        return results
    
    def _extract_with_ollama_direct(self, field_name: str, content: str) -> str:
        """
        Ollama를 직접 호출하여 특정 필드를 추출합니다.
        """
        try:
            prompt = self._build_extraction_prompt(field_name, content)
            
            response = requests.post(
                f"{self.model_url}/api/chat",
                json={
                    "model": self.model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "num_predict": 256
                    }
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                extracted = result.get("message", {}).get("content", "").strip()
                
                if not extracted or extracted.lower() in ["없음", "해당없음", "정보없음", "찾을 수 없음", ""]:
                    return "찾을 수 없음"
                    
                return extracted
            else:
                logger.error(f"Ollama API 오류: {response.status_code}")
                return "찾을 수 없음"
                
        except Exception as e:
            logger.error(f"Ollama 직접 호출 오류: {e}")
            return "찾을 수 없음"
    
    def _build_extraction_prompt(self, field_name: str, content: str) -> str:
        """필드별 추출을 위한 프롬프트를 구성합니다."""
        field_description = self._get_field_prompt(field_name)
        
        prompt = f"""다음 공고 내용에서 {field_name}를 정확히 찾아서 추출해주세요.

{field_description}

공고 내용:
{content}

{field_name}를 찾을 수 없다면 "찾을 수 없음"이라고 답하세요.
답변은 추출한 내용만 간단히 작성해주세요."""

        return prompt
    

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
            print(f"    🔍 {field_name} 추출 중...")
            
            # 필드별 전용 프롬프트와 예시 생성
            prompt_description = self._get_field_prompt(field_name)
            examples = self._get_field_examples(field_name)
            
            # LangExtract로 추출 수행 - Ollama 전용 설정
            result = lx.extract(
                text_or_documents=content,
                prompt_description=prompt_description,
                examples=examples[:1],  # 예시를 1개로 제한
                model_id=self.model_id,
                model_url=self.model_url,
                fence_output=False,  # Ollama용 설정
                use_schema_constraints=False  # Ollama용 설정
            )
            
            # 결과 처리
            if result and hasattr(result, 'extractions') and result.extractions:
                first_extraction = result.extractions[0]
                
                if hasattr(first_extraction, 'extraction_text'):
                    extracted = first_extraction.extraction_text.strip()
                elif hasattr(first_extraction, 'text'):
                    extracted = first_extraction.text.strip()
                else:
                    extracted = str(first_extraction).strip()
                    
                if extracted and extracted != "찾을 수 없음":
                    return extracted
                    
            return "찾을 수 없음"
            
        except Exception as e:
            print(f"    ❌ {field_name} 추출 오류: {e}")
            logger.error(f"{field_name} 추출 중 오류: {e}")
            return "찾을 수 없음"
    
    def _get_field_prompt(self, field_name: str) -> str:
        """필드별 전용 프롬프트를 반환합니다."""
        
        prompts = {
            "지원대상": """공고 문서에서 지원 대상을 정확히 추출하세요. 
누가 이 지원사업에 신청할 수 있는지만 찾아서 반환하세요.
예: 중소기업, 소상공인, 개인사업자, 스타트업, 청년 등""",
            
            "시행기관": """공고 문서에서 시행기관(주관기관)을 정확히 추출하세요.
어느 기관에서 이 지원사업을 주관하는지만 찾아서 반환하세요.
예: 중소벤처기업부, 서울시, 경기도, 한국산업기술진흥원 등""",
            
            "제목": """공고 문서에서 정확한 제목을 추출하세요.
공고의 공식 제목이나 사업명만 찾아서 반환하세요.
불필요한 기호나 번호는 제외하고 핵심 제목만 추출하세요.""",
            
            "지원내용": """공고 문서에서 지원 내용을 정확히 추출하세요.
구체적으로 어떤 종류의 지원을 제공하는지만 찾아서 반환하세요.
예: 사업비 지원, 교육 지원, 컨설팅 지원, 시설비 지원 등""",
            
            "지원금액": """공고 문서에서 지원 금액을 정확히 추출하세요.
구체적인 지원 금액이나 범위만 찾아서 반환하세요.
예: 최대 5,000만원, 3천만원 이내, 1억원 한도 등""",
            
            "등록일": """공고 문서에서 공고 등록일(공고일)을 정확히 추출하세요.
언제 이 공고가 등록되었는지만 찾아서 반환하세요.
접수기간이나 심사일정이 아닌 공고 자체의 등록일만 추출하세요.""",
            
            "접수기간": """공고 문서에서 접수 기간을 정확히 추출하세요.
신청서를 언제부터 언제까지 받는지만 찾아서 반환하세요.
시작일과 종료일을 모두 포함해서 반환하세요.""",
            
            "모집일정": """공고 문서에서 전체 모집 일정을 정확히 추출하세요.
접수기간, 심사일정, 발표일 등 전체적인 일정 정보를 찾아서 반환하세요."""
        }
        
        return prompts.get(field_name, f"{field_name}를 정확히 추출하세요.")
    
    def _get_field_examples(self, field_name: str) -> List[lx.data.ExampleData]:
        """필드별 추출 예시를 반환합니다."""
        
        examples = {
            "지원대상": [
                lx.data.ExampleData(
                    text="지원대상: 중소기업 및 소상공인",
                    extractions=[lx.data.Extraction(extraction_class="지원대상", extraction_text="중소기업, 소상공인")]
                ),
                lx.data.ExampleData(
                    text="신청자격: 개인사업자, 예비창업자", 
                    extractions=[lx.data.Extraction(extraction_class="지원대상", extraction_text="개인사업자, 예비창업자")]
                ),
                lx.data.ExampleData(
                    text="○ 대상 : 스타트업, 벤처기업",
                    extractions=[lx.data.Extraction(extraction_class="지원대상", extraction_text="스타트업, 벤처기업")]
                )
            ],
            
            "시행기관": [
                lx.data.ExampleData(
                    text="주관: 중소벤처기업부",
                    extractions=[lx.data.Extraction(extraction_class="시행기관", extraction_text="중소벤처기업부")]
                ),
                lx.data.ExampleData(
                    text="시행기관: 서울특별시",
                    extractions=[lx.data.Extraction(extraction_class="시행기관", extraction_text="서울특별시")]
                ),
                lx.data.ExampleData(
                    text="주최: 한국산업기술진흥원",
                    extractions=[lx.data.Extraction(extraction_class="시행기관", extraction_text="한국산업기술진흥원")]
                )
            ],
            
            "제목": [
                lx.data.ExampleData(
                    text="2024년 중소기업 기술개발지원사업 공고",
                    extractions=[lx.data.Extraction(extraction_class="제목", extraction_text="2024년 중소기업 기술개발지원사업")]
                ),
                lx.data.ExampleData(
                    text="□ 소상공인 창업지원 프로그램 안내",
                    extractions=[lx.data.Extraction(extraction_class="제목", extraction_text="소상공인 창업지원 프로그램")]
                )
            ],
            
            "지원내용": [
                lx.data.ExampleData(
                    text="지원내용: 기술개발비, 인건비, 장비구입비 지원",
                    extractions=[lx.data.Extraction(extraction_class="지원내용", extraction_text="기술개발비, 인건비, 장비구입비 지원")]
                ),
                lx.data.ExampleData(
                    text="○ 지원사항: 사업비 지원, 교육 및 컨설팅",
                    extractions=[lx.data.Extraction(extraction_class="지원내용", extraction_text="사업비 지원, 교육 및 컨설팅")]
                )
            ],
            
            "지원금액": [
                lx.data.ExampleData(
                    text="지원금액: 최대 5,000만원",
                    extractions=[lx.data.Extraction(extraction_class="지원금액", extraction_text="최대 5,000만원")]
                ),
                lx.data.ExampleData(
                    text="○ 지원규모: 3천만원 이내",
                    extractions=[lx.data.Extraction(extraction_class="지원금액", extraction_text="3천만원 이내")]
                )
            ],
            
            "등록일": [
                lx.data.ExampleData(
                    text="공고일: 2024년 3월 15일",
                    extractions=[lx.data.Extraction(extraction_class="등록일", extraction_text="2024년 3월 15일")]
                ),
                lx.data.ExampleData(
                    text="작성일: 2025.05.30",
                    extractions=[lx.data.Extraction(extraction_class="등록일", extraction_text="2025.05.30")]
                )
            ],
            
            "접수기간": [
                lx.data.ExampleData(
                    text="접수기간: 2025년 3월 1일 ~ 2025년 3월 31일",
                    extractions=[lx.data.Extraction(extraction_class="접수기간", extraction_text="2025년 3월 1일 ~ 2025년 3월 31일")]
                ),
                lx.data.ExampleData(
                    text="○ 신청기한: 2024.12.01 ~ 2024.12.31",
                    extractions=[lx.data.Extraction(extraction_class="접수기간", extraction_text="2024.12.01 ~ 2024.12.31")]
                )
            ],
            
            "모집일정": [
                lx.data.ExampleData(
                    text="모집일정: 접수(3.1~3.31), 심사(4.1~4.15), 발표(4.30)",
                    extractions=[lx.data.Extraction(extraction_class="모집일정", extraction_text="접수(3.1~3.31), 심사(4.1~4.15), 발표(4.30)")]
                ),
                lx.data.ExampleData(
                    text="일정안내: 신청접수 12월, 서류심사 1월, 최종발표 2월",
                    extractions=[lx.data.Extraction(extraction_class="모집일정", extraction_text="신청접수 12월, 서류심사 1월, 최종발표 2월")]
                )
            ],
            
            "지원내용": [
                lx.data.ExampleData(
                    text="지원내용: 기술개발비, 인건비, 장비구입비 지원",
                    extractions=[lx.data.Extraction(extraction_class="지원내용", extraction_text="기술개발비, 인건비, 장비구입비 지원")]
                ),
                lx.data.ExampleData(
                    text="○ 지원형태: 컨설팅 및 교육 지원",
                    extractions=[lx.data.Extraction(extraction_class="지원내용", extraction_text="컨설팅 및 교육 지원")]
                )
            ],
            
            "지원금액": [
                lx.data.ExampleData(
                    text="지원금액: 최대 5,000만원",
                    extractions=[lx.data.Extraction(extraction_class="지원금액", extraction_text="최대 5,000만원")]
                ),
                lx.data.ExampleData(
                    text="○ 지원한도: 3천만원 이내",
                    extractions=[lx.data.Extraction(extraction_class="지원금액", extraction_text="3천만원 이내")]
                )
            ],
            
            "접수기간": [
                lx.data.ExampleData(
                    text="접수기간: 2025년 3월 1일 ~ 2025년 3월 31일",
                    extractions=[lx.data.Extraction(extraction_class="접수기간", extraction_text="2025년 3월 1일 ~ 2025년 3월 31일")]
                ),
                lx.data.ExampleData(
                    text="신청일정: 2025.06.01 ~ 2025.06.30",
                    extractions=[lx.data.Extraction(extraction_class="접수기간", extraction_text="2025.06.01 ~ 2025.06.30")]
                )
            ],
            
            "모집일정": [
                lx.data.ExampleData(
                    text="모집일정: 접수(3.1~3.31) → 심사(4.1~4.15) → 발표(4.20)",
                    extractions=[lx.data.Extraction(extraction_class="모집일정", extraction_text="접수(3.1~3.31) → 심사(4.1~4.15) → 발표(4.20)")]
                ),
                lx.data.ExampleData(
                    text="전체일정: 모집공고(5월) - 접수(6월) - 선정평가(7월) - 최종발표(8월)",
                    extractions=[lx.data.Extraction(extraction_class="모집일정", extraction_text="모집공고(5월) - 접수(6월) - 선정평가(7월) - 최종발표(8월)")]
                )
            ]
        }
        
        return examples.get(field_name, [])
    
    def test_ollama_connection(self) -> bool:
        """Ollama 연결 상태를 테스트합니다."""
        try:
            print(f"연결 테스트 시작 - 모델: {self.model_id}, URL: {self.model_url}")
            
            # LangExtract + Ollama 테스트
            try:
                test_result = lx.extract(
                    text_or_documents="테스트 문서입니다. 오늘은 2025년입니다.",
                    prompt_description="이 문서에서 연도를 찾아서 반환하세요.",
                    examples=[
                        lx.data.ExampleData(
                            text="2024년 사업안내",
                            extractions=[lx.data.Extraction(extraction_class="연도", extraction_text="2024년")]
                        )
                    ],
                    model_id=self.model_id,
                    model_url=self.model_url,
                    fence_output=False,  # Ollama용 설정
                    use_schema_constraints=False  # Ollama용 설정
                )
                
                print(f"LangExtract 테스트 결과: {test_result}")
                print("✓ LangExtract + Ollama 연결 테스트 성공")
                return True
                
            except Exception as e:
                print(f"❌ LangExtract 테스트 실패: {e}")
                logger.error(f"LangExtract 연결 테스트 실패: {e}")
                return False
            
        except Exception as e:
            print(f"❌ 모든 연결 테스트 실패: {e}")
            return False


def extract_announcement_fields(content: str) -> Dict[str, str]:
    """
    공고 내용에서 모든 필드를 LangExtract로 추출하는 편의 함수
    
    Args:
        content: 분석할 공고 내용
        
    Returns:
        필드별 추출 결과
    """
    analyzer = LangExtractFieldAnalyzer()
    return analyzer.extract_all_fields(content)


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

    # LangExtract + Ollama 연결 테스트
    analyzer = LangExtractFieldAnalyzer()
    
    if analyzer.test_ollama_connection():
        print("✓ LangExtract + Ollama 연결 성공")
        
        # 필드별 추출 테스트
        print("\n=== 필드별 추출 테스트 ===")
        results = extract_announcement_fields(test_content)
        
        for field, value in results.items():
            status = "✓" if value != "찾을 수 없음" else "✗"
            print(f"{status} {field}: {value}")
            
    else:
        print("❌ LangExtract + Ollama 연결 실패")
        print("다음을 확인해주세요:")
        print("1. Ollama가 실행 중인지 확인")
        print("2. ollama serve 명령으로 서버 시작")
        print(f"3. 모델이 설치되었는지: ollama pull {analyzer.model_id}")
        print(f"4. API URL이 올바른지: {analyzer.model_url}")