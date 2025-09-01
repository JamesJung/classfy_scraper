"""
Ollama API 클라이언트 및 공고 데이터 추출 유틸리티

Ollama를 통해 공고 내용을 분석하고 다음 정보를 추출합니다:
- 지원대상
- 지원금액
- 제목
- 접수기간
- 모집일정
- 지원내용
- 소상공인 해당여부
"""

import json
import os
import logging
import requests
from typing import Dict, Optional, Any
from pathlib import Path

try:
    from src.config.config import ConfigManager
    from src.config.logConfig import setup_logging
except ImportError:
    # 절대 import 시도
    import sys
    from pathlib import Path

    # 프로젝트 루트를 path에 추가
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    from src.config.config import ConfigManager
    from src.config.logConfig import setup_logging

# 환경변수에서 로그 레벨 읽기
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO)
logger = setup_logging(__name__, log_level)

# 환경변수에서 직접 읽기
try:
    config = ConfigManager().get_config()
except:
    config = {}


class OllamaClient:
    """Ollama API 클라이언트"""

    def __init__(self):
        # 환경변수에서 직접 읽기
        self.api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api")
        self.model = os.getenv("OLLAMA_MODEL", "llama3.2")
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "600"))  # 기본 10분 타임아웃
        self.max_tokens = int(os.getenv("OLLAMA_MAX_TOKENS", "16384"))  # 환경변수로 제어 가능
        
        # API 헤더 설정
        self.headers = {
            "Content-Type": "application/json"
        }

    def is_available(self) -> bool:
        """Ollama 서버 상태를 확인합니다."""
        try:
            # Ollama health check endpoint
            health_url = f"{self.api_url.replace('/api', '')}/api/tags"
            response = requests.get(health_url, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama 서버 연결 실패: {e}")
            return False

    def generate_response(self, prompt: str, system_prompt: str = None) -> Optional[str]:
        """
        Ollama API를 통해 응답을 생성합니다.

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트

        Returns:
            생성된 응답 또는 None
        """
        try:
            logger.info(f"Ollama API 요청 전송 중... (모델: {self.model})")
            logger.info(f"요청 URL: {self.api_url}")

            # 요청 세부 정보 로그
            logger.debug(f"Ollama API 요청 파라미터:")
            logger.debug(f"  모델: {self.model}")
            if system_prompt:
                logger.debug(f"  시스템 프롬프트 길이: {len(system_prompt)} 문자")
                logger.debug(system_prompt)
                
            else:
                logger.debug(f"  시스템 프롬프트 없음")
                    
            logger.debug(f"  사용자 프롬프트 길이: {len(prompt)} 문자")

            # Ollama API 요청 페이로드
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system_prompt if system_prompt else "",
                "stream": False,
                # "context": [],
                "options": {
                    # "temperature": 0.1,
                    "top_p": 0.9,
                    # "num_predict": self.max_tokens,
                    "num_predict": 2049,
                    # "stop": [ "</final>"],
                    # "repeat_penalty": 1.1
                }
            }

            # Ollama generate API 호출
            generate_url = f"{self.api_url}/generate"
            response = requests.post(
                generate_url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )

            logger.debug(f"Ollama API 응답 수신: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                logger.info(f"result: {result}")

                generated_text = result.get('response', '').strip()
                thinking_text = result.get('thinking', '').strip()
                
                if generated_text:
                    logger.info(f"Ollama API 응답 생성 완료: {len(generated_text)} 문자")
                    return generated_text
                elif thinking_text:
                    logger.warning(f"response 필드는 비어있지만 thinking 필드에 내용 있음: {len(thinking_text)} 문자")
                    logger.info(f"thinking 내용을 응답으로 사용")
                    return thinking_text
                else:
                    logger.error(f"Ollama API 응답이 비어있음!")
                    logger.error(f"전체 응답: {result}")
                    return None
            else:
                logger.error(f"Ollama API 오류: {response.status_code}")
                logger.error(f"응답 내용: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Ollama API 호출 중 오류: {e}")
            if hasattr(e, 'response'):
                logger.error(f"응답 상태코드: {e.response.status_code if e.response else 'None'}")
                logger.error(f"응답 내용: {e.response.text if e.response else 'None'}")
            return None


class AnnouncementAnalyzer:
    """공고 내용 분석 및 데이터 추출"""

    def __init__(self):
        self.ollama_client = OllamaClient()
        self.system_prompt = self._create_system_prompt()

    def _create_system_prompt(self) -> str:
        """분석용 시스템 프롬프트를 생성합니다."""
        try:
            # 템플릿 파일 경로
            template_path = Path(__file__).parent.parent / "config" / "ollama_template.txt"
            
            if template_path.exists():
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_content = f.read()
                
                logger.debug(f"시스템 프롬프트 템플릿 로드 성공: {template_path}")
                return template_content
            else:
                logger.warning(f"템플릿 파일을 찾을 수 없음: {template_path}")
                # 기본 프롬프트 사용
                return self._get_default_system_prompt()
                
        except Exception as e:
            logger.error(f"시스템 프롬프트 템플릿 로드 실패: {e}")
            return self._get_default_system_prompt()
    
    def _get_default_system_prompt(self) -> str:
        """기본 시스템 프롬프트를 반환합니다."""
        return """당신은 정부 및 공공기관의 공고문을 분석하는 전문가입니다.
주어진 공고 내용을 분석하여 다음 정보를 정확히 추출해주세요.

추출할 정보:
1. 지원대상: 누가 지원할 수 있는지 (예: 중소기업, 스타트업, 개인 등)
2. 지원금액: 지원받을 수 있는 금액 (구체적인 수치나 범위)
3. 제목: 공고의 정확한 제목
4. 등록일 : 공고 등록한 일자 (공고일, 등록일)
5. 접수기간: 신청을 받는 기간 (시작일과 마감일)
6. 모집일정: 전체적인 일정 (접수기간, 심사일정, 발표일 등)
7. 지원내용: 구체적으로 어떤 지원을 제공하는지
8. 소상공인_해당여부: 소상공인이 대상에 포함되는지 여부 (true/false)

중요한 규칙:
- 전달된 내용에서 정보를 찾을 수 없으면 "정보 없음"이라고 정확히 기재해주세요.
- 추측하거나 가정하지 마세요. 명확한 정보만 추출해주세요.
- 결과는 반드시 유효한 JSON 형식으로 반환해주세요.
- 날짜는 가능한 한 구체적으로 기재해주세요.

응답 형식:
```json
{
    "지원대상": "추출된 정보 또는 정보 없음",
    "지원금액": "추출된 정보 또는 정보 없음",
    "제목": "추출된 정보 또는 정보 없음",
    "등록일": "추출된 정보 또는 정보 없음",
    "접수기간": "추출된 정보 또는 정보 없음",
    "모집일정": "추출된 정보 또는 정보 없음",
    "지원내용": "추출된 정보 또는 정보 없음",
    "소상공인_해당여부": true/false/null
}
```"""


    def analyze_announcement(self, content: str) -> tuple[Dict[str, Any], str]:
        """
        공고 내용을 분석하여 구조화된 데이터를 추출합니다.

        Args:
            content: 분석할 공고 내용

        Returns:
            (추출된 정보를 담은 딕셔너리, 사용된 프롬프트)
        """
        if not content or not content.strip():
            logger.warning("분석할 내용이 비어있음")
            return self._create_empty_result("내용이 비어있음"), ""

        # Ollama 서버 상태 확인
        if not self.ollama_client.is_available():
            logger.error("Ollama 서버를 사용할 수 없음")
            return self._create_empty_result("Ollama 서버 연결 실패"), ""

        # 내용이 너무 긴 경우 잘라내기 (토큰 제한 고려)
        # max_length = 8000  # 대략적인 토큰 제한
        # if len(content) > max_length:
        #     logger.warning(f"내용이 너무 김 ({len(content)} -> {max_length} 문자로 축소)")
        #     content = content[:max_length] + "\n\n... (내용 축소됨)"

        # 분석 프롬프트 생성
        user_prompt = f"""다음 공고 내용을 분석해주세요:

=== 공고 내용 시작 ===
{content}
=== 공고 내용 끝 ===

위 내용을 분석하여 JSON 형식으로 추출해주세요. 이 때 "반드시" 응답형식에 맞춰서 응답해주세요. JSON에 별도의 키 값을 추가하지 말고 응답형식을 지켜주세요."""

        # 전체 프롬프트 (시스템 프롬프트 + 사용자 프롬프트)
        full_prompt = f"SYSTEM:\n{self.system_prompt}\n\nUSER:\n{user_prompt}"

        try:
            logger.info("공고 내용 분석 시작...")

            # 디버깅을 위한 전체 프롬프트 로그 추가
            logger.info(f"=== Ollama 요청 프롬프트 ===")
            logger.info(f"시스템 프롬프트 길이: {len(self.system_prompt)} 문자")
            logger.info(f"사용자 프롬프트 길이: {len(user_prompt)} 문자")
            logger.info(f"전체 프롬프트 길이: {len(full_prompt)} 문자")
            # logger.info(f"시스템 프롬프트: {self.system_prompt}")
            logger.info(f"사용자 프롬프트: {user_prompt}")
            logger.info("=== Ollama 요청 프롬프트 끝 ===")

            # Ollama를 통해 분석 수행
            response = self.ollama_client.generate_response(
                prompt=user_prompt,
                system_prompt=self.system_prompt
            )

            if not response:
                logger.error("Ollama 응답을 받을 수 없음")
                logger.error(f"응답 타입: {type(response)}")
                logger.error(f"응답 값: {repr(response)}")
                logger.error("Ollama 서버 연결 상태 재확인...")
                if self.ollama_client.is_available():
                    logger.error("Ollama 서버는 사용 가능하지만 응답이 없음")
                else:
                    logger.error("Ollama 서버 연결 불가")
                return self._create_empty_result("AI 분석 실패"), full_prompt

            # 디버깅을 위한 원본 응답 로그 추가
            logger.info(f"=== Ollama 원본 응답 (길이: {len(response)} 문자) ===")
            logger.info(f"응답 내용: {response}")
            logger.info("=== Ollama 원본 응답 끝 ===")

            # JSON 파싱
            parsed_result = self._parse_json_response(response)

            if parsed_result:
                logger.info("공고 분석 완료")
                return parsed_result, full_prompt
            else:
                logger.error("JSON 파싱 실패")
                return self._create_empty_result("응답 파싱 실패"), full_prompt

        except Exception as e:
            logger.error(f"공고 분석 중 오류: {e}")
            return self._create_empty_result(f"분석 오류: {str(e)}"), full_prompt

    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """AI 응답에서 JSON을 파싱합니다."""
        try:
            logger.debug("=== JSON 파싱 시작 ===")
            
            # JSON 코드 블록에서 추출 시도
            if "```json" in response:
                logger.debug("```json 블록 발견")
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                if json_end != -1:
                    json_str = response[json_start:json_end].strip()
                else:
                    json_str = response[json_start:].strip()
            elif "```" in response:
                logger.debug("일반 ``` 블록 발견")
                # 일반 코드 블록에서 추출
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                if json_end != -1:
                    json_str = response[json_start:json_end].strip()
                else:
                    json_str = response[json_start:].strip()
            else:
                logger.debug("코드 블록 없음, 전체 응답 사용")
                # JSON 블록이 없으면 전체 응답에서 JSON 찾기
                json_str = response.strip()

            logger.debug(f"추출된 JSON 문자열 (길이: {len(json_str)}): {json_str[:500]}...")

            # JSON 파싱 시도
            parsed = json.loads(json_str)
            logger.debug(f"JSON 파싱 성공, 키 개수: {len(parsed) if isinstance(parsed, dict) else '딕셔너리가 아님'}")

            # 잘못된 키들을 올바른 키로 매핑 (EXTRACTED_* 형태로 통일)
            key_mapping = {
                # 한글 키 → EXTRACTED_* 키 매핑
                "공고명": "EXTRACTED_TITLE",
                "제목": "EXTRACTED_TITLE",
                "지원대상": "EXTRACTED_TARGET",
                "대상": "EXTRACTED_TARGET",
                "지원 대상": "EXTRACTED_TARGET",
                "지원_대상": "EXTRACTED_TARGET",
                "지원금액": "EXTRACTED_AMOUNT",
                "금액": "EXTRACTED_AMOUNT",
                "지원 금액": "EXTRACTED_AMOUNT",
                "지원_금액": "EXTRACTED_AMOUNT",
                "접수기간": "EXTRACTED_PERIOD",
                "접수 기간": "EXTRACTED_PERIOD",
                "접수기간_원본": "EXTRACTED_PERIOD",
                "모집일정": "EXTRACTED_SCHEDULE",
                "일정": "EXTRACTED_SCHEDULE",
                "모집 일정": "EXTRACTED_SCHEDULE",
                "모집_일정": "EXTRACTED_SCHEDULE",
                "지원내용": "EXTRACTED_CONTENT",
                "내용": "EXTRACTED_CONTENT",
                "지원 내용": "EXTRACTED_CONTENT",
                "지원_내용": "EXTRACTED_CONTENT",
                "공고등록일": "EXTRACTED_ANNOUNCEMENT_DATE",
                "등록일": "EXTRACTED_ANNOUNCEMENT_DATE",
                "공고 등록일": "EXTRACTED_ANNOUNCEMENT_DATE",
                "공고_등록일": "EXTRACTED_ANNOUNCEMENT_DATE",
                # 기존 영문 키들도 대문자로 통일
                "extracted_title": "EXTRACTED_TITLE",
                "extracted_target": "EXTRACTED_TARGET", 
                "extracted_amount": "EXTRACTED_AMOUNT",
                "extracted_period": "EXTRACTED_PERIOD",
                "extracted_schedule": "EXTRACTED_SCHEDULE",
                "extracted_content": "EXTRACTED_CONTENT",
                "extracted_announcement_date": "EXTRACTED_ANNOUNCEMENT_DATE"
            }
            
            # 키 매핑 적용
            normalized_parsed = {}
            for key, value in parsed.items():
                mapped_key = key_mapping.get(key, key)
                normalized_parsed[mapped_key] = value
            
            # 원본 파싱 결과를 정규화된 결과로 교체
            parsed = normalized_parsed
            
            # 필수 키들 확인 및 보완
            required_keys = ["EXTRACTED_TARGET", "EXTRACTED_TARGET_TYPE", "EXTRACTED_AMOUNT", "EXTRACTED_TITLE", "EXTRACTED_PERIOD", 
            "EXTRACTED_SCHEDULE", "EXTRACTED_CONTENT", "EXTRACTED_ANNOUNCEMENT_DATE"]
            for key in required_keys:
                if key not in parsed:
                    parsed[key] = "해당없음"
            logger.info(f"parsed: {parsed}")

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}")
            logger.debug(f"파싱 시도한 문자열: {response[:500]}...")
            return None
        except Exception as e:
            logger.error(f"응답 파싱 중 오류: {e}")
            return None

    def _create_empty_result(self, error_message: str = "분석 실패") -> Dict[str, Any]:
        """빈 결과 딕셔너리를 생성합니다."""
        return {
            "EXTRACTED_TARGET": "정보 없음",
            "EXTRACTED_TARGET_TYPE": "정보 없음",
            "EXTRACTED_AMOUNT": "정보 없음",
            "EXTRACTED_TITLE": "정보 없음",
            "EXTRACTED_PERIOD": "정보 없음",
            "EXTRACTED_SCHEDULE": "정보 없음",
            "EXTRACTED_CONTENT": "정보 없음",
            "EXTRACTED_ANNOUNCEMENT_DATE": "정보 없음",
            "error": error_message
        }



def analyze_announcement_content(content: str) -> Dict[str, Any]:
    """
    공고 내용을 분석하는 편의 함수

    Args:
        content: 분석할 공고 내용

    Returns:
        분석 결과 딕셔너리
    """
    analyzer = AnnouncementAnalyzer()
    return analyzer.analyze_announcement(content)


if __name__ == "__main__":
    # 테스트용
    test_content = """
    2025년 중소기업 기술개발지원사업 공고

    1. 지원대상: 중소기업, 소상공인
    2. 지원금액: 최대 5,000만원
    3. 접수기간: 2025년 3월 1일 ~ 2025년 3월 31일
    4. 지원내용: 기술개발비, 인건비, 장비구입비 지원
    """

    # Ollama 서버 상태 확인
    client = OllamaClient()
    if client.is_available():
        print("Ollama 서버 연결 성공")

        # 분석 테스트
        result = analyze_announcement_content(test_content)
        print("\n분석 결과:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Ollama 서버에 연결할 수 없습니다.")
        print("다음을 확인해주세요:")
        print("1. Ollama가 실행 중인지 확인")
        print("2. 인터넷 연결이 정상인지")
        print(f"3. API URL이 올바른지: {client.api_url}")
        print(f"4. 모델이 설치되었는지: {client.model}")
        print("5. 'ollama list' 명령으로 설치된 모델을 확인해보세요")
