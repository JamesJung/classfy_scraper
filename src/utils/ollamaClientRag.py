"""
Ollama API 클라이언트 및 공고 데이터 추출 유틸리티 - RAG 시스템 통합

ChromaDB를 활용한 RAG(Retrieval-Augmented Generation) 시스템으로
기존 공고 데이터를 참조하여 더 정확한 분석을 수행합니다.

주요 기능:
- ChromaDB 벡터 스토어 통합
- 유사 공고 검색 및 컨텍스트 제공
- RAG 기반 Ollama 분석
- 벡터 임베딩 생성 및 저장
"""

import json
import os
import logging
import requests
import chromadb
from typing import Dict, Optional, Any, List, Tuple
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
import hashlib

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


class ChromaDBManager:
    """ChromaDB 벡터 스토어 매니저"""
    
    def __init__(self):
        # ChromaDB 설정
        self.chroma_host = os.getenv("CHROMA_HOST", "localhost")
        self.chroma_port = int(os.getenv("CHROMA_PORT", "8000"))
        self.chroma_collection = os.getenv("CHROMA_COLLECTION", "announcements")
        
        # 임베딩 모델 초기화
        self.embedding_model_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        logger.info(f"임베딩 모델 로딩 중: {self.embedding_model_name}")
        self.embedding_model = SentenceTransformer(self.embedding_model_name)
        
        # ChromaDB 클라이언트 초기화
        try:
            # 로컬 ChromaDB 사용 (HTTP 클라이언트 대신)
            self.chroma_client = chromadb.PersistentClient(
                path=os.getenv("CHROMA_PERSIST_DIRECTORY", "./chromadb_data")
            )
            logger.info("ChromaDB 클라이언트 초기화 성공")
        except Exception as e:
            logger.warning(f"ChromaDB 클라이언트 초기화 실패, 메모리 클라이언트로 대체: {e}")
            self.chroma_client = chromadb.Client()
        
        # 컬렉션 생성 또는 가져오기
        self.collection = self._get_or_create_collection()
    
    def _get_or_create_collection(self):
        """컬렉션을 가져오거나 생성합니다."""
        try:
            # 기존 컬렉션 가져오기 시도
            collection = self.chroma_client.get_collection(name=self.chroma_collection)
            logger.info(f"기존 ChromaDB 컬렉션 로드: {self.chroma_collection}")
        except:
            # 컬렉션이 없으면 새로 생성
            collection = self.chroma_client.create_collection(
                name=self.chroma_collection,
                metadata={"description": "공고 데이터 벡터 스토어"}
            )
            logger.info(f"새 ChromaDB 컬렉션 생성: {self.chroma_collection}")
        
        return collection
    
    def generate_embedding(self, text: str) -> List[float]:
        """텍스트에 대한 임베딩을 생성합니다."""
        try:
            # 텍스트가 너무 긴 경우 잘라내기
            max_length = 512  # SentenceTransformer 모델의 최대 토큰 길이
            if len(text.split()) > max_length:
                text = ' '.join(text.split()[:max_length])
            
            embedding = self.embedding_model.encode(text)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"임베딩 생성 실패: {e}")
            # 기본 임베딩 반환 (모든 0)
            return [0.0] * 384  # MiniLM 모델의 기본 차원
    
    def store_document(self, doc_id: str, content: str, metadata: Dict[str, Any]):
        """문서를 벡터 스토어에 저장합니다."""
        try:
            # 임베딩 생성
            embedding = self.generate_embedding(content)
            
            # ChromaDB에 저장
            self.collection.add(
                documents=[content],
                metadatas=[metadata],
                embeddings=[embedding],
                ids=[doc_id]
            )
            
            logger.debug(f"문서 저장 완료: {doc_id}")
            return True
            
        except Exception as e:
            logger.error(f"문서 저장 실패 ({doc_id}): {e}")
            return False
    
    def search_similar_documents(self, query: str, site_code: str = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """유사한 문서들을 검색합니다."""
        try:
            # 쿼리 임베딩 생성
            query_embedding = self.generate_embedding(query)
            
            # 검색 필터 설정
            where_filter = {}
            if site_code:
                where_filter["site_code"] = site_code
            
            # 유사 문서 검색
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter if where_filter else None,
                include=["documents", "metadatas", "distances"]
            )
            
            # 결과 정리
            similar_docs = []
            if results and results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i] if results['metadatas'] and results['metadatas'][0] else {}
                    distance = results['distances'][0][i] if results['distances'] and results['distances'][0] else 1.0
                    
                    similar_docs.append({
                        "content": doc,
                        "metadata": metadata,
                        "similarity": 1.0 - distance,  # 유사도로 변환
                        "distance": distance
                    })
            
            logger.debug(f"유사 문서 검색 완료: {len(similar_docs)}개")
            return similar_docs
            
        except Exception as e:
            logger.error(f"유사 문서 검색 실패: {e}")
            return []
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """컬렉션 통계를 가져옵니다."""
        try:
            count = self.collection.count()
            return {"total_documents": count}
        except Exception as e:
            logger.error(f"컬렉션 통계 조회 실패: {e}")
            return {"total_documents": 0}


class OllamaClientRAG:
    """Ollama API 클라이언트 - RAG 기능 추가"""

    def __init__(self):
        # 기본 Ollama 설정
        self.api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api")
        self.model = os.getenv("OLLAMA_MODEL", "llama3.2")
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "600"))  # 기본 10분 타임아웃
        self.max_tokens = int(os.getenv("OLLAMA_MAX_TOKENS", "16384"))  # 환경변수로 제어 가능
        
        # API 헤더 설정
        self.headers = {
            "Content-Type": "application/json"
        }
        
        # ChromaDB 매니저 초기화
        self.chromadb_manager = ChromaDBManager()

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

    def generate_response_with_context(self, prompt: str, context: str = "", system_prompt: str = None) -> Optional[str]:
        """
        컨텍스트를 포함하여 Ollama API를 통해 응답을 생성합니다.

        Args:
            prompt: 사용자 프롬프트
            context: RAG로 검색된 컨텍스트 정보
            system_prompt: 시스템 프롬프트

        Returns:
            생성된 응답 또는 None
        """
        try:
            # 컨텍스트가 있으면 프롬프트에 추가
            enhanced_prompt = prompt
            if context:
                enhanced_prompt = f"""관련 정보:
{context}

---

위의 관련 정보를 참고하여 다음 질문에 답변해주세요:
{prompt}"""

            logger.info(f"Ollama API 요청 전송 중... (모델: {self.model})")
            logger.info(f"요청 URL: {self.api_url}")

            # 요청 세부 정보 로그
            logger.debug(f"Ollama API 요청 파라미터:")
            logger.debug(f"  모델: {self.model}")
            if system_prompt:
                logger.debug(f"  시스템 프롬프트 길이: {len(system_prompt)} 문자")
            else:
                logger.debug(f"  시스템 프롬프트 없음")
                    
            logger.debug(f"  사용자 프롬프트 길이: {len(enhanced_prompt)} 문자")
            if context:
                logger.debug(f"  컨텍스트 길이: {len(context)} 문자")

            # Ollama API 요청 페이로드
            payload = {
                "model": self.model,
                "prompt": enhanced_prompt,
                "system": system_prompt if system_prompt else "",
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "num_predict": self.max_tokens,
                    "stop": ["</final>"],
                    "repeat_penalty": 1.1
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
    
    def store_announcement_vector(self, doc_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        """공고 문서를 벡터 스토어에 저장합니다."""
        return self.chromadb_manager.store_document(doc_id, content, metadata)
    
    def search_similar_announcements(self, query: str, site_code: str = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """유사한 공고들을 검색합니다."""
        return self.chromadb_manager.search_similar_documents(query, site_code, top_k)


class AnnouncementAnalyzerRAG:
    """공고 내용 분석 및 데이터 추출 - RAG 시스템 통합"""

    def __init__(self):
        self.ollama_client = OllamaClientRAG()
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
8. 지원대상분류: 개인/기업/소상공인 등의 분류
9. 소상공인_해당여부: 소상공인이 대상에 포함되는지 여부 (true/false)

중요한 규칙:
- 전달된 내용에서 정보를 찾을 수 없으면 "정보 없음"이라고 정확히 기재해주세요.
- 추측하거나 가정하지 마세요. 명확한 정보만 추출해주세요.
- 결과는 반드시 유효한 JSON 형식으로 반환해주세요.
- 날짜는 가능한 한 구체적으로 기재해주세요.
- 관련 정보가 제공된 경우 이를 참고하되, 현재 분석하는 공고의 내용을 우선시하세요.

응답 형식:
```json
{
    "EXTRACTED_TARGET": "추출된 정보 또는 정보 없음",
    "EXTRACTED_TARGET_TYPE": "추출된 정보 또는 정보 없음",
    "EXTRACTED_AMOUNT": "추출된 정보 또는 정보 없음",
    "EXTRACTED_TITLE": "추출된 정보 또는 정보 없음",
    "EXTRACTED_ANNOUNCEMENT_DATE": "추출된 정보 또는 정보 없음",
    "EXTRACTED_PERIOD": "추출된 정보 또는 정보 없음",
    "EXTRACTED_SCHEDULE": "추출된 정보 또는 정보 없음",
    "EXTRACTED_CONTENT": "추출된 정보 또는 정보 없음"
}
```"""

    def analyze_announcement_with_rag(self, content: str, site_code: str = None) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
        """
        RAG 시스템을 활용하여 공고 내용을 분석합니다.

        Args:
            content: 분석할 공고 내용
            site_code: 사이트 코드 (유사 공고 검색용)

        Returns:
            (추출된 정보를 담은 딕셔너리, 사용된 프롬프트, RAG 컨텍스트)
        """
        if not content or not content.strip():
            logger.warning("분석할 내용이 비어있음")
            return self._create_empty_result("내용이 비어있음"), "", {}

        # Ollama 서버 상태 확인
        if not self.ollama_client.is_available():
            logger.error("Ollama 서버를 사용할 수 없음")
            return self._create_empty_result("Ollama 서버 연결 실패"), "", {}

        # RAG 컨텍스트 수집
        rag_context = self._collect_rag_context(content, site_code)
        
        # 분석 프롬프트 생성
        user_prompt = f"""다음 공고 내용을 분석해주세요:

=== 공고 내용 시작 ===
{content}
=== 공고 내용 끝 ===

위 내용을 분석하여 요청된 정보를 JSON 형식으로 추출해주세요."""

        try:
            logger.info("RAG 기반 공고 내용 분석 시작...")

            # 디버깅을 위한 전체 프롬프트 로그 추가
            logger.info(f"=== RAG Ollama 요청 프롬프트 ===")
            logger.info(f"시스템 프롬프트 길이: {len(self.system_prompt)} 문자")
            logger.info(f"사용자 프롬프트 길이: {len(user_prompt)} 문자")
            logger.info(f"RAG 컨텍스트 길이: {len(rag_context.get('context_text', ''))} 문자")
            logger.info("=== RAG Ollama 요청 프롬프트 끝 ===")

            # Ollama를 통해 RAG 기반 분석 수행
            response = self.ollama_client.generate_response_with_context(
                prompt=user_prompt,
                context=rag_context.get("context_text", ""),
                system_prompt=self.system_prompt
            )

            if not response:
                logger.error("RAG Ollama 응답을 받을 수 없음")
                logger.error(f"응답 타입: {type(response)}")
                logger.error(f"응답 값: {repr(response)}")
                return self._create_empty_result("RAG AI 분석 실패"), user_prompt, rag_context

            # 디버깅을 위한 원본 응답 로그 추가
            logger.info(f"=== RAG Ollama 원본 응답 (길이: {len(response)} 문자) ===")
            logger.info(f"응답 내용: {response}")
            logger.info("=== RAG Ollama 원본 응답 끝 ===")

            # JSON 파싱
            parsed_result = self._parse_json_response(response)

            if parsed_result:
                logger.info("RAG 기반 공고 분석 완료")
                return parsed_result, user_prompt, rag_context
            else:
                logger.error("RAG JSON 파싱 실패")
                return self._create_empty_result("RAG 응답 파싱 실패"), user_prompt, rag_context

        except Exception as e:
            logger.error(f"RAG 기반 공고 분석 중 오류: {e}")
            return self._create_empty_result(f"RAG 분석 오류: {str(e)}"), user_prompt, rag_context

    def _collect_rag_context(self, content: str, site_code: str = None) -> Dict[str, Any]:
        """RAG 컨텍스트를 수집합니다."""
        try:
            # 유사 공고 검색
            similar_announcements = self.ollama_client.search_similar_announcements(
                query=content[:1000],  # 처음 1000자만 사용해서 검색
                site_code=site_code,
                top_k=3  # 상위 3개만 사용
            )
            
            # 컨텍스트 텍스트 생성
            context_text = ""
            if similar_announcements:
                context_text = "=== 참고할 유사 공고들 ===\n"
                for i, doc in enumerate(similar_announcements, 1):
                    similarity = doc.get("similarity", 0)
                    if similarity > 0.7:  # 유사도 70% 이상만 사용
                        metadata = doc.get("metadata", {})
                        title = metadata.get("title", "제목 없음")
                        target = metadata.get("target", "대상 없음")
                        amount = metadata.get("amount", "금액 없음")
                        
                        context_text += f"\n[유사 공고 {i}] (유사도: {similarity:.2f})\n"
                        context_text += f"제목: {title}\n"
                        context_text += f"지원대상: {target}\n"
                        context_text += f"지원금액: {amount}\n"
                        context_text += f"내용 요약: {doc['content'][:200]}...\n"
                
                context_text += "\n=== 유사 공고 참고 정보 끝 ===\n"
            
            logger.info(f"RAG 컨텍스트 수집 완료: {len(similar_announcements)}개 유사 공고")
            
            return {
                "similar_announcements": similar_announcements,
                "context_text": context_text,
                "context_count": len(similar_announcements)
            }
            
        except Exception as e:
            logger.error(f"RAG 컨텍스트 수집 실패: {e}")
            return {"similar_announcements": [], "context_text": "", "context_count": 0}

    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """AI 응답에서 JSON을 파싱합니다."""
        try:
            logger.debug("=== RAG JSON 파싱 시작 ===")
            
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

            # 키 매핑 적용 (기존 로직과 동일)
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
                "지원대상분류": "EXTRACTED_TARGET_TYPE",
                # 기존 영문 키들도 대문자로 통일
                "extracted_title": "EXTRACTED_TITLE",
                "extracted_target": "EXTRACTED_TARGET", 
                "extracted_amount": "EXTRACTED_AMOUNT",
                "extracted_period": "EXTRACTED_PERIOD",
                "extracted_schedule": "EXTRACTED_SCHEDULE",
                "extracted_content": "EXTRACTED_CONTENT",
                "extracted_announcement_date": "EXTRACTED_ANNOUNCEMENT_DATE",
                "extracted_target_type": "EXTRACTED_TARGET_TYPE"
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
            logger.info(f"RAG parsed: {parsed}")

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"RAG JSON 파싱 오류: {e}")
            logger.debug(f"파싱 시도한 문자열: {response[:500]}...")
            return None
        except Exception as e:
            logger.error(f"RAG 응답 파싱 중 오류: {e}")
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

    def store_announcement_for_rag(self, doc_id: str, content: str, extracted_data: Dict[str, Any], site_code: str) -> bool:
        """분석된 공고를 RAG 시스템에 저장합니다."""
        try:
            # 메타데이터 구성
            metadata = {
                "doc_id": doc_id,
                "site_code": site_code,
                "title": extracted_data.get("EXTRACTED_TITLE", "제목 없음"),
                "target": extracted_data.get("EXTRACTED_TARGET", "대상 없음"),
                "amount": extracted_data.get("EXTRACTED_AMOUNT", "금액 없음"),
                "target_type": extracted_data.get("EXTRACTED_TARGET_TYPE", "분류 없음"),
                "announcement_date": extracted_data.get("EXTRACTED_ANNOUNCEMENT_DATE", "날짜 없음")
            }
            
            # 벡터 스토어에 저장
            success = self.ollama_client.store_announcement_vector(doc_id, content, metadata)
            
            if success:
                logger.info(f"RAG 시스템에 공고 저장 완료: {doc_id}")
            else:
                logger.error(f"RAG 시스템에 공고 저장 실패: {doc_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"RAG 시스템 공고 저장 중 오류: {e}")
            return False


def analyze_announcement_content_with_rag(content: str, site_code: str = None) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    """
    RAG 시스템을 활용한 공고 내용 분석 편의 함수

    Args:
        content: 분석할 공고 내용
        site_code: 사이트 코드

    Returns:
        (분석 결과 딕셔너리, 프롬프트, RAG 컨텍스트)
    """
    analyzer = AnnouncementAnalyzerRAG()
    return analyzer.analyze_announcement_with_rag(content, site_code)


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
    client = OllamaClientRAG()
    if client.is_available():
        print("Ollama 서버 연결 성공")

        # RAG 분석 테스트
        result, prompt, rag_context = analyze_announcement_content_with_rag(test_content, "test")
        print("\nRAG 분석 결과:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\nRAG 컨텍스트: {rag_context.get('context_count', 0)}개 유사 공고 참조")
    else:
        print("Ollama 서버에 연결할 수 없습니다.")
        print("다음을 확인해주세요:")
        print("1. Ollama가 실행 중인지 확인")
        print("2. 인터넷 연결이 정상인지")
        print(f"3. API URL이 올바른지: {client.api_url}")
        print(f"4. 모델이 설치되었는지: {client.model}")
        print("5. 'ollama list' 명령으로 설치된 모델을 확인해보세요")