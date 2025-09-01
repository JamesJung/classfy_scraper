"""
2단계 Ollama 처리 클라이언트

1단계: 간단한 정보 추출 (지원대상, 지원금액, 제목, 접수기간 등)
2단계: 개인이 아닌 경우 정밀한 구조화된 데이터 추출
"""

import json
import os
import time
import logging
from typing import Dict, Optional, Any, Tuple
from pathlib import Path

try:
    from src.utils.ollamaClient import OllamaClient
    from src.config.logConfig import setup_logging
except ImportError:
    # 절대 import 시도
    import sys
    from pathlib import Path
    
    # 프로젝트 루트를 path에 추가
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    
    from src.utils.ollamaClient import OllamaClient
    from src.config.logConfig import setup_logging

# 환경변수에서 로그 레벨 읽기
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO)
logger = setup_logging(__name__, log_level)


class TwoStageOllamaClient:
    """2단계 Ollama 처리 클라이언트"""
    
    def __init__(self):
        self.ollama_client = OllamaClient()
        self.simple_prompt_template = self._load_simple_template()
        self.format_prompt_template = self._load_format_template()
    
    def _load_simple_template(self) -> str:
        """간단한 정보 추출용 템플릿을 로드합니다."""
        try:
            template_path = Path(__file__).parent.parent / "config" / "ollama_simple_template.txt"
            
            if template_path.exists():
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                logger.debug(f"간단 템플릿 로드 성공: {template_path}")
                return content
            else:
                logger.warning(f"간단 템플릿 파일 없음: {template_path}")
                return self._get_default_simple_template()
                
        except Exception as e:
            logger.error(f"간단 템플릿 로드 실패: {e}")
            return self._get_default_simple_template()
    
    def _load_format_template(self) -> str:
        """정밀한 구조화된 분석용 템플릿을 로드합니다."""
        try:
            template_path = Path(__file__).parent.parent / "config" / "ollama_format_template.txt"
            
            if template_path.exists():
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                logger.debug(f"정밀 템플릿 로드 성공: {template_path}")
                return content
            else:
                logger.warning(f"정밀 템플릿 파일 없음: {template_path}")
                return self._get_default_format_template()
                
        except Exception as e:
            logger.error(f"정밀 템플릿 로드 실패: {e}")
            return self._get_default_format_template()
    
    def _get_default_simple_template(self) -> str:
        """기본 간단 템플릿을 반환합니다."""
        return """당신은 정부 및 공공기관의 공고문을 분석하는 전문가입니다.
주어진 공고 내용을 분석하여 다음 정보를 정확히 추출해주세요.

추출할 정보:
1. 지원대상: 누가 지원할 수 있는지
2. 지원금액: 지원받을 수 있는 금액
3. 제목: 공고의 정확한 제목
4. 공고등록일: 공고 등록한 일자
5. 접수기간: 신청을 받는 기간
6. 모집일정: 전체적인 일정
7. 지원내용: 구체적으로 어떤 지원을 제공하는지
8. 지원대상분류: 개인, 기업, 소상공인인지 분류 (복수 선택 가능)

응답 형식:
```json
{
    "지원대상": "추출된 정보 또는 해당없음",
    "지원금액": "추출된 정보 또는 해당없음",
    "제목": "추출된 정보 또는 해당없음",
    "공고등록일": "추출된 정보 또는 해당없음",
    "접수기간": "추출된 정보 또는 해당없음",
    "모집일정": "추출된 정보 또는 해당없음",
    "지원내용": "추출된 정보 또는 해당없음",
    "지원대상분류": ["개인", "기업", "소상공인"]
}
```"""
    
    def _get_default_format_template(self) -> str:
        """기본 정밀 템플릿을 반환합니다."""
        return """당신은 한국 정부 공고 문서에서 필드별 원문 데이터를 정확히 추출하는 AI입니다.
주어진 공고 내용을 분석하여 구조화된 JSON 형식으로 모든 필드를 추출해주세요.
문서에 없는 정보는 생성하지 말고, 불확실하면 빈 값으로 두세요."""
    
    def stage1_simple_analysis(self, content: str) -> Tuple[Dict[str, Any], str, float]:
        """
        1단계: 간단한 정보 추출
        
        Args:
            content: 분석할 공고 내용
            
        Returns:
            (추출된 간단 정보, 사용된 프롬프트, 소요 시간)
        """
        logger.info("=== 1단계: 간단한 정보 추출 시작 ===")
        
        if not content or not content.strip():
            logger.warning("분석할 내용이 비어있음")
            return self._create_empty_simple_result("내용이 비어있음"), "", 0.0
        
        # Ollama 서버 상태 확인
        if not self.ollama_client.is_available():
            logger.error("Ollama 서버를 사용할 수 없음")
            return self._create_empty_simple_result("Ollama 서버 연결 실패"), "", 0.0
        
        # 분석 프롬프트 생성
        user_prompt = f"""다음 공고 내용을 분석해주세요:

=== 공고 내용 시작 ===
{content}
=== 공고 내용 끝 ===

위 내용을 분석하여 요청된 간단한 정보를 JSON 형식으로 추출해주세요."""

        # 전체 프롬프트
        full_prompt = f"SYSTEM:\\n{self.simple_prompt_template}\\n\\nUSER:\\n{user_prompt}"
        
        try:
            start_time = time.time()
            
            logger.info("1단계 Ollama 요청 전송...")
            logger.debug(f"1단계 시스템 프롬프트 길이: {len(self.simple_prompt_template)} 문자")
            logger.debug(f"1단계 사용자 프롬프트 길이: {len(user_prompt)} 문자")
            
            # Ollama를 통해 분석 수행
            response = self.ollama_client.generate_response(
                prompt=user_prompt,
                system_prompt=self.simple_prompt_template
            )
            
            duration = time.time() - start_time
            
            if not response:
                logger.error("1단계 Ollama 응답을 받을 수 없음")
                return self._create_empty_simple_result("1단계 AI 분석 실패"), full_prompt, duration
            
            logger.info(f"1단계 Ollama 응답 받음 (길이: {len(response)} 문자, 소요시간: {duration:.2f}초)")
            logger.debug(f"1단계 원본 응답: {response}")
            
            # JSON 파싱
            parsed_result = self._parse_simple_json_response(response)
            
            if parsed_result:
                logger.info("1단계 간단 분석 완료")
                return parsed_result, full_prompt, duration
            else:
                logger.error("1단계 JSON 파싱 실패")
                return self._create_empty_simple_result("1단계 응답 파싱 실패"), full_prompt, duration
                
        except Exception as e:
            duration = time.time() - start_time if 'start_time' in locals() else 0.0
            logger.error(f"1단계 공고 분석 중 오류: {e}")
            return self._create_empty_simple_result(f"1단계 분석 오류: {str(e)}"), full_prompt, duration
    
    def stage2_format_analysis(self, content: str) -> Tuple[Dict[str, Any], str, float]:
        """
        2단계: 정밀한 구조화된 데이터 추출
        
        Args:
            content: 분석할 공고 내용
            
        Returns:
            (추출된 구조화된 정보, 사용된 프롬프트, 소요 시간)
        """
        logger.info("=== 2단계: 정밀한 구조화된 분석 시작 ===")
        
        if not content or not content.strip():
            logger.warning("2단계 분석할 내용이 비어있음")
            return self._create_empty_format_result("내용이 비어있음"), "", 0.0
        
        # Ollama 서버 상태 확인
        if not self.ollama_client.is_available():
            logger.error("2단계 Ollama 서버를 사용할 수 없음")
            return self._create_empty_format_result("Ollama 서버 연결 실패"), "", 0.0
        
        # 분석 프롬프트 생성
        user_prompt = f"""다음 공고 내용을 정밀하게 분석해주세요:

=== 공고 내용 시작 ===
{content}
=== 공고 내용 끝 ===

위 내용을 분석하여 요청된 모든 구조화된 필드를 JSON 형식으로 추출해주세요."""

        # 전체 프롬프트
        full_prompt = f"SYSTEM:\\n{self.format_prompt_template}\\n\\nUSER:\\n{user_prompt}"
        
        try:
            start_time = time.time()
            
            logger.info("2단계 Ollama 요청 전송...")
            logger.debug(f"2단계 시스템 프롬프트 길이: {len(self.format_prompt_template)} 문자")
            logger.debug(f"2단계 사용자 프롬프트 길이: {len(user_prompt)} 문자")
            
            # Ollama를 통해 분석 수행
            response = self.ollama_client.generate_response(
                prompt=user_prompt,
                system_prompt=self.format_prompt_template
            )
            
            duration = time.time() - start_time
            
            if not response:
                logger.error("2단계 Ollama 응답을 받을 수 없음")
                return self._create_empty_format_result("2단계 AI 분석 실패"), full_prompt, duration
            
            logger.info(f"2단계 Ollama 응답 받음 (길이: {len(response)} 문자, 소요시간: {duration:.2f}초)")
            logger.debug(f"2단계 원본 응답: {response}")
            
            # JSON 파싱
            parsed_result = self._parse_format_json_response(response)
            
            if parsed_result:
                logger.info("2단계 정밀 분석 완료")
                return parsed_result, full_prompt, duration
            else:
                logger.error("2단계 JSON 파싱 실패")
                return self._create_empty_format_result("2단계 응답 파싱 실패"), full_prompt, duration
                
        except Exception as e:
            duration = time.time() - start_time if 'start_time' in locals() else 0.0
            logger.error(f"2단계 공고 분석 중 오류: {e}")
            return self._create_empty_format_result(f"2단계 분석 오류: {str(e)}"), full_prompt, duration
    
    def process_announcement(self, content: str) -> Dict[str, Any]:
        """
        2단계 공고 처리 전체 프로세스
        
        Args:
            content: 분석할 공고 내용
            
        Returns:
            전체 처리 결과
        """
        logger.info("=== 2단계 Ollama 처리 시작 ===")
        
        result = {
            "stage1_result": None,
            "stage1_prompt": "",
            "stage1_duration": 0.0,
            "stage2_result": None,
            "stage2_prompt": "",
            "stage2_duration": 0.0,
            "stage2_executed": False
        }
        
        # 1단계: 간단한 정보 추출
        stage1_result, stage1_prompt, stage1_duration = self.stage1_simple_analysis(content)
        result["stage1_result"] = stage1_result
        result["stage1_prompt"] = stage1_prompt
        result["stage1_duration"] = stage1_duration
        
        # 지원대상분류가 개인이 아닌 경우만 2단계 실행
        target_classification = stage1_result.get("지원대상분류", [])
        if not target_classification:
            target_classification = []
        
        # "개인"만 있는 경우가 아니면 2단계 실행
        should_run_stage2 = not (len(target_classification) == 1 and "개인" in target_classification)
        
        if should_run_stage2:
            logger.info("지원대상이 개인이 아니므로 2단계 정밀 분석 실행")
            stage2_result, stage2_prompt, stage2_duration = self.stage2_format_analysis(content)
            result["stage2_result"] = stage2_result
            result["stage2_prompt"] = stage2_prompt
            result["stage2_duration"] = stage2_duration
            result["stage2_executed"] = True
        else:
            logger.info("지원대상이 개인만 해당되므로 2단계 분석 건너뜀")
        
        total_duration = stage1_duration + (result["stage2_duration"] if result["stage2_executed"] else 0)
        logger.info(f"2단계 처리 완료 - 총 소요시간: {total_duration:.2f}초")
        
        return result
    
    def _parse_simple_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """1단계 응답에서 JSON을 파싱합니다."""
        try:
            # JSON 코드 블록에서 추출 시도
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                if json_end != -1:
                    json_str = response[json_start:json_end].strip()
                else:
                    json_str = response[json_start:].strip()
            elif "```" in response:
                # 일반 코드 블록에서 추출
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                if json_end != -1:
                    json_str = response[json_start:json_end].strip()
                else:
                    json_str = response[json_start:].strip()
            else:
                # JSON 블록이 없으면 전체 응답에서 JSON 찾기
                json_str = response.strip()

            # JSON 파싱 시도
            parsed = json.loads(json_str)

            # 필수 키들 확인 및 보완
            required_keys = ["지원대상", "지원금액", "제목", "공고등록일", "접수기간", "모집일정", "지원내용", "지원대상분류"]
            for key in required_keys:
                if key not in parsed:
                    if key == "지원대상분류":
                        parsed[key] = []
                    else:
                        parsed[key] = "해당없음"

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"1단계 JSON 파싱 오류: {e}")
            logger.debug(f"파싱 시도한 문자열: {response[:500]}...")
            return None
        except Exception as e:
            logger.error(f"1단계 응답 파싱 중 오류: {e}")
            return None
    
    def _parse_format_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """2단계 응답에서 JSON을 파싱합니다."""
        try:
            # JSON 코드 블록에서 추출 시도
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                if json_end != -1:
                    json_str = response[json_start:json_end].strip()
                else:
                    json_str = response[json_start:].strip()
            elif "```" in response:
                # 일반 코드 블록에서 추출
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                if json_end != -1:
                    json_str = response[json_start:json_end].strip()
                else:
                    json_str = response[json_start:].strip()
            else:
                # JSON 블록이 없으면 전체 응답에서 JSON 찾기
                json_str = response.strip()

            # JSON 파싱 시도
            parsed = json.loads(json_str)
            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"2단계 JSON 파싱 오류: {e}")
            logger.debug(f"파싱 시도한 문자열: {response[:500]}...")
            return None
        except Exception as e:
            logger.error(f"2단계 응답 파싱 중 오류: {e}")
            return None
    
    def _create_empty_simple_result(self, error_message: str = "1단계 분석 실패") -> Dict[str, Any]:
        """빈 1단계 결과 딕셔너리를 생성합니다."""
        return {
            "지원대상": "해당없음",
            "지원금액": "해당없음",
            "제목": "해당없음",
            "공고등록일": "해당없음",
            "접수기간": "해당없음",
            "모집일정": "해당없음",
            "지원내용": "해당없음",
            "지원대상분류": [],
            "오류": error_message
        }
    
    def _create_empty_format_result(self, error_message: str = "2단계 분석 실패") -> Dict[str, Any]:
        """빈 2단계 결과 딕셔너리를 생성합니다."""
        return {
            "오류": error_message
        }


def analyze_announcement_two_stage(content: str) -> Dict[str, Any]:
    """
    2단계 공고 분석 편의 함수
    
    Args:
        content: 분석할 공고 내용
        
    Returns:
        분석 결과
    """
    client = TwoStageOllamaClient()
    return client.process_announcement(content)


if __name__ == "__main__":
    # 테스트용
    test_content = """
    2025년 중소기업 기술개발지원사업 공고

    1. 지원대상: 중소기업, 소상공인
    2. 지원금액: 최대 5,000만원
    3. 접수기간: 2025년 3월 1일 ~ 2025년 3월 31일
    4. 지원내용: 기술개발비, 인건비, 장비구입비 지원
    """

    # 2단계 분석 테스트
    result = analyze_announcement_two_stage(test_content)
    print("\\n=== 2단계 분석 결과 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))