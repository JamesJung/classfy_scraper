"""
공고 분류를 위한 키워드 매칭 및 분류 유틸리티
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class AnnouncementClassifier:
    """공고 분류를 위한 키워드 분석 클래스"""

    def __init__(self):
        self.keywords_cache = None
        self.load_keywords()

    def load_keywords(self):
        """데이터베이스에서 키워드를 로드"""
        try:
            from sqlalchemy import text

            from src.models.database import SessionLocal

            db = SessionLocal()

            result = db.execute(
                text(
                    """
                SELECT KEYWORD, KEYWORD_TYPE, INDUSTRY_CATEGORY, SYNONYMS, WEIGHT
                FROM CLASSIFICATION_KEYWORDS
                WHERE IS_ACTIVE = TRUE
            """
                )
            )

            keywords = result.fetchall()

            self.keywords_cache = {
                "SMALL_BUSINESS": [],
                "SME": [],
                "STARTUP": [],
                "SOCIAL_ENTERPRISE": [],
                "INDUSTRY": [],
            }

            for keyword, kw_type, industry_cat, synonyms_json, weight in keywords:
                try:
                    synonyms = json.loads(synonyms_json) if synonyms_json else [keyword]
                except json.JSONDecodeError:
                    synonyms = [keyword]

                keyword_info = {
                    "keyword": keyword,
                    "synonyms": synonyms,
                    "weight": weight,
                    "industry_category": industry_cat,
                }

                if kw_type in self.keywords_cache:
                    self.keywords_cache[kw_type].append(keyword_info)

            db.close()
            logger.info(
                f"키워드 로드 완료: {sum(len(v) for v in self.keywords_cache.values())}개"
            )

        except Exception as e:
            logger.error(f"키워드 로딩 실패: {e}")
            self.keywords_cache = {
                "SMALL_BUSINESS": [],
                "SME": [],
                "STARTUP": [],
                "SOCIAL_ENTERPRISE": [],
                "INDUSTRY": [],
            }

    def extract_text_from_files(self, folder_path: Path) -> dict[str, str]:
        """폴더에서 모든 파일의 텍스트 추출 - 품질 최적화"""

        extracted_texts = {}

        try:
            # content.md 파일 (processManager와 동일한 로직 사용)
            content_file = folder_path / "content.md"
            if content_file.exists():
                from src.utils.convertUtil import read_md_file

                loaded_content = read_md_file(content_file)
                if loaded_content and loaded_content.strip():
                    cleaned_content = self._clean_markdown_content(loaded_content)
                    extracted_texts["content.md"] = cleaned_content

            # attachments 폴더의 파일들 (우선순위 기반 처리)
            attachments_dir = folder_path / "attachments"
            if attachments_dir.exists():
                # 파일 우선순위 정렬 (PDF, HWP > 기타)
                files_by_priority = self._sort_files_by_priority(
                    list(attachments_dir.iterdir())
                )

                for file_path in files_by_priority:
                    if file_path.is_file():
                        try:
                            text = self._extract_text_from_file(file_path)
                            if text and len(text.strip()) > 10:  # 최소 텍스트 길이 검증
                                quality_score = self._calculate_text_quality(text)
                                logger.debug(
                                    f"파일 {file_path.name} 품질 점수: {quality_score:.3f}"
                                )

                                # 품질 임계값을 0.2로 낮춤 (더 많은 파일 포함)
                                if quality_score > 0.2:
                                    cleaned_text = self._clean_extracted_text(text)
                                    extracted_texts[file_path.name] = cleaned_text
                                    logger.debug(
                                        f"파일 {file_path.name} 추가됨 (길이: {len(cleaned_text)}자)"
                                    )
                                else:
                                    logger.debug(
                                        f"파일 {file_path.name} 품질 임계값 미달 (점수: {quality_score:.3f})"
                                    )
                            else:
                                logger.debug(
                                    f"파일 {file_path.name} 텍스트 추출 실패 또는 너무 짧음"
                                )
                        except Exception as e:
                            logger.warning(f"파일 {file_path.name} 처리 중 오류: {e}")
                            continue

        except Exception as e:
            logger.warning(f"텍스트 추출 중 오류 ({folder_path}): {e}")

        return extracted_texts

    def _clean_markdown_content(self, content: str) -> str:
        """마크다운 콘텐츠 정제 - processManager와 동일한 로직 사용"""
        # processManager에서 사용하는 mdContentCleaner를 사용
        from src.utils.mdContentCleaner import clean_md_content

        return clean_md_content(content)

    def _sort_files_by_priority(self, files: list[Path]) -> list[Path]:
        """파일 우선순위 정렬"""

        priority_order = {
            ".pdf": 1,
            ".hwp": 2,
            ".hwpx": 3,
            ".doc": 4,
            ".docx": 5,
            ".txt": 6,
        }

        def get_priority(file_path: Path) -> int:
            return priority_order.get(file_path.suffix.lower(), 10)

        return sorted([f for f in files if f.is_file()], key=get_priority)

    def _calculate_text_quality(self, text: str) -> float:
        """추출된 텍스트 품질 점수 계산 - 개선된 로직"""

        if not text or len(text.strip()) < 10:
            return 0.0

        quality_score = 0.3  # 기본 점수를 더 관대하게 설정

        # 한글 비율 (한국 공고이므로 한글이 많을수록 품질 높음)
        korean_chars = len([c for c in text if "가" <= c <= "힣"])
        korean_ratio = korean_chars / len(text) if text else 0
        quality_score += korean_ratio * 0.4  # 가중치 증가

        # 의미있는 단어 포함 여부 (더 많은 키워드 추가)
        meaningful_words = [
            "지원",
            "신청",
            "모집",
            "대상",
            "자격",
            "선정",
            "사업",
            "기업",
            "공고",
            "안내",
            "계획",
            "예산",
            "접수",
            "제출",
            "마감",
            "일정",
            "요건",
            "조건",
            "절차",
            "방법",
            "문의",
            "담당",
        ]
        word_count = sum(1 for word in meaningful_words if word in text)
        quality_score += (word_count / len(meaningful_words)) * 0.2

        # 텍스트 길이 기준 완화
        text_length = len(text.strip())
        if text_length >= 50:  # 최소 50자 이상이면 가점
            quality_score += 0.1
        if text_length >= 200:  # 200자 이상이면 추가 가점
            quality_score += 0.1

        # 숫자와 특수문자 비율이 너무 높으면 감점 (OCR 오류 등)
        non_korean_chars = len(
            [c for c in text if not ("가" <= c <= "힣" or c.isspace())]
        )
        if non_korean_chars / len(text) > 0.7:  # 70% 이상이 비한글이면
            quality_score -= 0.2

        return min(1.0, max(0.0, quality_score))

    def _clean_extracted_text(self, text: str) -> str:
        """추출된 텍스트 정제"""
        import re

        # 특수문자 정리
        text = re.sub(r"[^\w\s가-힣]", " ", text)

        # 연속된 공백 정리
        text = re.sub(r"\s+", " ", text)

        # 의미없는 반복 문자 제거
        text = re.sub(r"(.)\1{5,}", r"\1", text)

        return text.strip()

    def _extract_text_from_file(self, file_path: Path) -> str | None:
        """개별 파일에서 텍스트 추출"""

        try:
            file_ext = file_path.suffix.lower()

            if file_ext == ".md":
                with open(file_path, encoding="utf-8") as f:
                    return f.read()

            elif file_ext == ".pdf":
                return self._extract_from_pdf(file_path)

            elif file_ext == ".hwp":
                return self._extract_from_hwp(file_path)

            elif file_ext == ".hwpx":
                return self._extract_from_hwpx(file_path)

            elif file_ext in [".txt"]:
                with open(file_path, encoding="utf-8") as f:
                    return f.read()

            # 이미지 파일은 OCR 필요 (나중에 구현)
            elif file_ext in [".jpg", ".jpeg", ".png", ".gif"]:
                return None  # OCR 구현 예정

        except Exception as e:
            logger.warning(f"파일 텍스트 추출 실패 ({file_path}): {e}")

        return None

    def _extract_from_pdf(self, file_path: Path) -> str | None:
        """PDF 파일에서 텍스트 추출 - processManager 로직 사용"""
        try:
            import os
            from tempfile import NamedTemporaryFile

            from src.utils.convertUtil import convert_pdf_to_text_simple

            # 임시 파일에 텍스트 추출
            with NamedTemporaryFile(
                mode="w+", suffix=".txt", encoding="utf-8", delete=False
            ) as temp_file:
                temp_path = temp_file.name

            try:
                success = convert_pdf_to_text_simple(str(file_path), temp_path)

                if success and os.path.exists(temp_path):
                    with open(temp_path, encoding="utf-8") as f:
                        text_content = f.read()

                    # 텍스트를 마크다운 형식으로 정리 (processManager와 동일)
                    from src.utils.mdContentCleaner import clean_md_content

                    cleaned_content = clean_md_content(text_content)

                    return cleaned_content.strip() if cleaned_content else None
                else:
                    return None

            finally:
                # 임시 파일 삭제
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        except Exception as e:
            logger.warning(f"PDF 텍스트 추출 실패 ({file_path}): {e}")
            return None

    def _extract_from_hwp(self, file_path: Path) -> str | None:
        """HWP 파일에서 텍스트 추출 - processManager 로직 사용"""
        try:
            from tempfile import TemporaryDirectory

            from src.utils.convertUtil import process_hwp_with_fallback

            # 임시 디렉토리 생성
            with TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)

                # HWP/HWPX → 텍스트 변환 (processManager와 동일한 로직)
                text_content = process_hwp_with_fallback(file_path, temp_dir_path)

                if text_content and text_content.strip():
                    # 텍스트를 마크다운 형식으로 정리 (processManager와 동일)
                    from src.utils.mdContentCleaner import clean_md_content

                    cleaned_content = clean_md_content(text_content)
                    return cleaned_content.strip() if cleaned_content else None
                else:
                    logger.warning(f"HWP 변환 실패: {file_path}")
                    return None

        except Exception as e:
            logger.warning(f"HWP 텍스트 추출 실패 ({file_path}): {e}")
            return None

    def _extract_from_hwpx(self, file_path: Path) -> str | None:
        """HWPX 파일에서 텍스트 추출 - processManager 로직 사용"""
        try:
            from src.utils.convertUtil import convert_hwpx_to_text

            # HWPX → 텍스트 변환 (processManager와 동일한 로직)
            text_content = convert_hwpx_to_text(file_path)

            if text_content and text_content.strip():
                # 텍스트를 마크다운 형식으로 정리 (processManager와 동일)
                from src.utils.mdContentCleaner import clean_md_content

                cleaned_content = clean_md_content(text_content)
                return cleaned_content.strip() if cleaned_content else None
            else:
                logger.warning(f"HWPX 변환 실패: {file_path}")
                return None

        except Exception as e:
            logger.warning(f"HWPX 텍스트 추출 실패 ({file_path}): {e}")
            return None

    def analyze_announcement(self, folder_path: Path, site_code: str) -> dict:
        """사이트별 구조에 맞는 공고 폴더 분석 및 분류"""
        
        # API 사이트 (bizInfo, kStartUp, sme) 2단계 키워드 분류
        if site_code.lower() in ["bizinfo", "kstartup", "sme"]:
            return self._analyze_api_sites_dual_classification(folder_path, site_code)
        else:
            # 일반 사이트 키워드 분류 (gtp 등)
            return self._analyze_general_announcement(folder_path, site_code)

    def _analyze_general_announcement(self, folder_path: Path, site_code: str) -> dict:
        """기존 일반 사이트 공고 분석 (gtp 등)"""

        from src.utils.pathUtil import get_relative_folder_path

        result = {
            "site_code": site_code,
            "folder_name": folder_path.name,
            "folder_path": get_relative_folder_path(folder_path),
            "announcement_title": self._extract_title_from_folder_name(
                folder_path.name
            ),
            "matched_keywords": [],
            "industry_keywords": [],
            "classification_type": "UNCLASSIFIED",
            "confidence_score": 0,
            "source_files": [],
            "extracted_text_preview": "",
        }

        # 1. 파일에서 텍스트 추출
        extracted_texts = self.extract_text_from_files(folder_path)

        if not extracted_texts:
            logger.warning(f"텍스트 추출 실패: {folder_path}")
            return result

        # 2. 전체 텍스트 병합 (우선순위: PDF/HWP > MD)
        combined_text = ""
        priority_files = []

        for filename, text in extracted_texts.items():
            if filename.endswith((".pdf", ".hwp", ".hwpx")):
                combined_text = text + "\n" + combined_text  # 앞에 추가 (높은 우선순위)
                priority_files.insert(0, filename)
            else:
                combined_text = combined_text + "\n" + text  # 뒤에 추가
                priority_files.append(filename)

        result["source_files"] = priority_files
        result["extracted_text_preview"] = combined_text


        
        logger.info(f"combined_text: {combined_text}")  
        #result["extracted_text_preview"] = combined_text
        
        # 3. 키워드 매칭 분석
        keyword_analysis = self._analyze_keywords(combined_text)

        result["matched_keywords"] = keyword_analysis["matched_keywords"]
        result["industry_keywords"] = keyword_analysis["industry_keywords"]
        result["classification_type"] = keyword_analysis["classification_type"]
        result["confidence_score"] = keyword_analysis["confidence_score"]

        return result

    def _analyze_api_sites_dual_classification(self, folder_path: Path, site_code: str) -> dict:
        """API 사이트 2단계 키워드 분류 (JSON 필드 1차 + 첨부파일 2차)"""
        
        from src.utils.pathUtil import get_relative_folder_path
        
        result = {
            "site_code": site_code,
            "folder_name": folder_path.name,
            "folder_path": get_relative_folder_path(folder_path),
            "announcement_title": folder_path.name,  # PBLN_* 형태
            "matched_keywords": [],
            "industry_keywords": [],
            "classification_type": "UNCLASSIFIED",
            "confidence_score": 0,
            "source_files": [],
            "extracted_text_preview": ""
        }
        
        # API 사이트 JSON 파일 경로 (상위 디렉토리에 위치)
        json_file = folder_path.parent / f"{folder_path.name}.json"
        
        if not json_file.exists():
            logger.warning(f"API 사이트 JSON 파일 없음: {json_file}")
            # JSON 파일이 없으면 일반 첨부파일 분류로 fallback
            return self._analyze_general_announcement(folder_path, site_code)
        
        try:
            logger.info(f"API 사이트 2단계 키워드 분류 시작: {folder_path.name}")
            
            # 1차 분류: JSON supportQualificationSummary/Contents 키워드 매칭
            json_classification = self._classify_from_qualification_fields(json_file)
            
            # 2차 분류: 첨부파일 텍스트 키워드 매칭
            attachment_classification = self._classify_from_attachments(folder_path)
            
            # 점수 병합 및 대표/서브 분류 결정
            merged_result = self._merge_dual_classifications(
                json_classification, attachment_classification, folder_path.name
            )
            
            # 결과 업데이트
            result.update(merged_result)
            result["source_files"] = [json_file.name] + merged_result.get("attachment_files", [])
            
            logger.info(f"✅ API 사이트 2단계 분류 완료: {folder_path.name} → {result.get('classification_type')} (점수: {result.get('confidence_score')})")
            return result
            
        except Exception as e:
            logger.error(f"❌ API 사이트 분류 실패 {json_file}: {e}")
            # 실패 시 일반 분류로 fallback
            return self._analyze_general_announcement(folder_path, site_code)

    def _classify_from_qualification_fields(self, json_file: Path) -> dict:
        """JSON supportQualificationSummary/Contents 필드에서 키워드 분류 (1차)"""
        
        classification_scores = {
            "SMALL_BUSINESS": 0,
            "SME": 0,
            "STARTUP": 0,
            "SOCIAL_ENTERPRISE": 0,
        }
        
        try:
            import json
            
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
            
            # 분석 대상 필드들 추출
            qualification_texts = []
            
            if data.get("supportQualificationSummary"):
                qualification_texts.append(data["supportQualificationSummary"])
            
            if data.get("supportQualificationContents"):
                qualification_texts.append(data["supportQualificationContents"])
                
            if not qualification_texts:
                logger.warning(f"JSON 자격 필드 없음: {json_file.name}")
                return {
                    "classification_scores": classification_scores,
                    "matched_keywords": [],
                    "source": "JSON_FIELDS"
                }
            
            # 전체 자격 텍스트 결합
            combined_qualification_text = " ".join(qualification_texts)
            
            # 키워드 분석 수행
            keyword_analysis = self._analyze_keywords(combined_qualification_text)
            
            # 점수 추출 (JSON 필드는 1.2배 가중치 적용)
            for kw_info in keyword_analysis.get("matched_keywords", []):
                kw_type = self._get_keyword_type_from_cache(kw_info["keyword"])
                if kw_type and kw_type in classification_scores:
                    classification_scores[kw_type] += kw_info["weight"] * 1.2  # JSON 필드 가중치
            
            logger.info(f"JSON 자격 필드 분류 완료: {json_file.name} → 점수: {classification_scores}")
            
            return {
                "classification_scores": classification_scores,
                "matched_keywords": keyword_analysis.get("matched_keywords", []),
                "industry_keywords": keyword_analysis.get("industry_keywords", []),
                "source": "JSON_FIELDS"
            }
            
        except Exception as e:
            logger.error(f"JSON 자격 필드 분류 실패 {json_file}: {e}")
            return {
                "classification_scores": classification_scores,
                "matched_keywords": [],
                "source": "JSON_FIELDS"
            }

    def _classify_from_attachments(self, folder_path: Path) -> dict:
        """첨부파일 텍스트에서 키워드 분류 (2차)"""
        
        classification_scores = {
            "SMALL_BUSINESS": 0,
            "SME": 0,
            "STARTUP": 0,
            "SOCIAL_ENTERPRISE": 0,
        }
        
        attachment_files = []
        
        try:
            # 첨부파일에서 텍스트 추출
            extracted_texts = self.extract_text_from_files(folder_path)
            
            # Fallback: attachments/ 미존재 또는 비어 있을 때, 폴더 최상위 주요 첨부파일 보조 스캔(API 사이트 구조 대응)
            if not extracted_texts:
                logger.info(
                    f"attachments 폴더 비어있음/없음으로 보조 스캔 시도: {folder_path.name}"
                )
                fallback_texts = {}
                try:
                    allowed_exts = {".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".txt"}
                    for file_path in sorted(folder_path.iterdir()):
                        if file_path.is_file() and file_path.suffix.lower() in allowed_exts:
                            try:
                                text = self._extract_text_from_file(file_path)
                                if text and len(text.strip()) > 10:
                                    quality_score = self._calculate_text_quality(text)
                                    if quality_score > 0.2:
                                        cleaned_text = self._clean_extracted_text(text)
                                        fallback_texts[file_path.name] = cleaned_text
                            except Exception as e:
                                logger.debug(f"보조 스캔 파일 처리 실패 {file_path.name}: {e}")
                                continue
                    # zip 존재 시 현재는 무시 (리소스 고려). 필요시 확장 가능
                except Exception as e:
                    logger.debug(f"보조 스캔 중 오류: {e}")

                extracted_texts = fallback_texts
            if not extracted_texts:
                logger.warning(f"첨부파일 텍스트 추출 실패: {folder_path.name}")
                return {
                    "classification_scores": classification_scores,
                    "matched_keywords": [],
                    "attachment_files": [],
                    "source": "ATTACHMENTS"
                }
            
            # 모든 첨부파일 텍스트 결합
            combined_text = ""
            for filename, text in extracted_texts.items():
                if text and text.strip():
                    combined_text += f" {text}"
                    attachment_files.append(filename)
            
            # 키워드 분석 수행
            keyword_analysis = self._analyze_keywords(combined_text)
            
            # 점수 추출 (첨부파일은 기본 가중치)
            for kw_info in keyword_analysis.get("matched_keywords", []):
                kw_type = self._get_keyword_type_from_cache(kw_info["keyword"])
                if kw_type and kw_type in classification_scores:
                    classification_scores[kw_type] += kw_info["weight"]
            
            logger.info(f"첨부파일 분류 완료: {folder_path.name} → 점수: {classification_scores}")
            
            return {
                "classification_scores": classification_scores,
                "matched_keywords": keyword_analysis.get("matched_keywords", []),
                "industry_keywords": keyword_analysis.get("industry_keywords", []),
                "attachment_files": attachment_files,
                "source": "ATTACHMENTS"
            }
            
        except Exception as e:
            logger.error(f"첨부파일 분류 실패 {folder_path}: {e}")
            return {
                "classification_scores": classification_scores,
                "matched_keywords": [],
                "attachment_files": [],
                "source": "ATTACHMENTS"
            }

    def _merge_dual_classifications(self, json_classification: dict, attachment_classification: dict, folder_name: str) -> dict:
        """1차(JSON) + 2차(첨부파일) 분류 점수 병합 및 대표/서브 분류 결정"""
        
        # 점수 병합: JSON 70%, 첨부파일 30%
        combined_scores = {}
        json_scores = json_classification.get("classification_scores", {})
        attachment_scores = attachment_classification.get("classification_scores", {})
        
        for classification_type in ["SMALL_BUSINESS", "SME", "STARTUP", "SOCIAL_ENTERPRISE"]:
            json_score = json_scores.get(classification_type, 0)
            attachment_score = attachment_scores.get(classification_type, 0)
            combined_scores[classification_type] = (json_score * 0.7) + (attachment_score * 0.3)
        
        # 대표 분류 + 서브 분류 결정
        classification_result = self._determine_primary_and_sub_classifications(combined_scores)
        
        # 키워드 정보 병합
        all_matched_keywords = (
            json_classification.get("matched_keywords", []) + 
            attachment_classification.get("matched_keywords", [])
        )
        
        all_industry_keywords = (
            json_classification.get("industry_keywords", []) +
            attachment_classification.get("industry_keywords", [])
        )
        
        # 결과 구성
        merged_result = {
            "classification_type": classification_result["primary_classification"],
            "classification_types": classification_result["sub_classifications"],
            "classification_scores": combined_scores,
            "confidence_score": classification_result["primary_score"],
            "matched_keywords": all_matched_keywords,
            "industry_keywords": all_industry_keywords,
            "attachment_files": attachment_classification.get("attachment_files", []),
            "classification_details": {
                "json_scores": json_scores,
                "attachment_scores": attachment_scores,
                "combined_scores": combined_scores,
                "merge_weights": {"json": 0.7, "attachments": 0.3}
            }
        }
        
        logger.info(f"분류 점수 병합 완료: {folder_name}")
        logger.info(f"  JSON 분류: {max(json_scores.items(), key=lambda x: x[1]) if json_scores else 'None'}")
        logger.info(f"  첨부파일 분류: {max(attachment_scores.items(), key=lambda x: x[1]) if attachment_scores else 'None'}")
        logger.info(f"  최종 대표 분류: {merged_result['classification_type']} ({merged_result['confidence_score']:.1f}점)")
        
        return merged_result

    def _determine_primary_and_sub_classifications(self, type_scores: dict) -> dict:
        """최고 매칭률 = 대표 분류, 임계값 이상 = 서브 분류"""
        
        # 임계값 설정 (30점 이상만 유효한 분류로 인정)
        threshold = 30
        qualified_classifications = {k: v for k, v in type_scores.items() if v >= threshold}
        
        if not qualified_classifications:
            return {
                "primary_classification": "UNCLASSIFIED",
                "sub_classifications": [],
                "primary_score": 0,
                "qualified_count": 0
            }
        
        # 최고 점수 = 대표 분류
        primary_type = max(qualified_classifications.keys(), key=qualified_classifications.get)
        primary_score = qualified_classifications[primary_type]
        
        # 서브 분류 = 임계값 이상 모든 분류 (점수 순 정렬)
        sub_types = sorted(qualified_classifications.keys(), 
                          key=lambda k: qualified_classifications[k], reverse=True)
        
        return {
            "primary_classification": primary_type,
            "sub_classifications": sub_types,
            "primary_score": primary_score,
            "qualified_count": len(qualified_classifications)
        }

    def _get_keyword_type_from_cache(self, keyword: str) -> str:
        """캐시에서 키워드의 분류 타입 찾기"""
        
        if not self.keywords_cache:
            return None
            
        for kw_type, keywords in self.keywords_cache.items():
            for keyword_info in keywords:
                if keyword_info["keyword"] == keyword:
                    return kw_type
        
        return None

    def _extract_text_from_bizinfo_files(self, folder_path: Path) -> dict[str, str]:
        """bizInfo 폴더에서 첨부파일 텍스트 추출 (기존 processed_data 활용 + 신규 추출)"""
        
        extracted_texts = {}
        
        try:
            # 1. 기존 processed_data 폴더에서 추출된 텍스트 확인
            processed_dirs = [d for d in folder_path.iterdir() if d.is_dir() and d.name.startswith("processed_data_")]
            
            for processed_dir in processed_dirs:
                extract_file = processed_dir / "extracted_text.txt"
                if extract_file.exists():
                    try:
                        with open(extract_file, encoding="utf-8") as f:
                            content = f.read()
                        if content and content.strip():
                            # processed_data 파일명에서 원본 파일명 추출
                            original_name = processed_dir.name.replace("processed_data_", "") + ".pdf"  # 대부분 PDF
                            extracted_texts[original_name] = content
                            logger.info(f"bizInfo 기존 추출 텍스트 활용: {original_name} ({len(content)} chars)")
                    except Exception as e:
                        logger.warning(f"기존 추출 텍스트 읽기 실패 {extract_file}: {e}")
            
            # 2. 기존 추출이 없는 파일들은 신규 처리
            files = [f for f in folder_path.iterdir() if f.is_file()]
            target_files = [f for f in files if f.suffix.lower() in ['.pdf', '.hwp', '.hwpx', '.docx']]
            
            for file_path in target_files:
                if file_path.name not in extracted_texts:
                    try:
                        # 신규 파일 텍스트 추출 시도
                        extracted_text = self._extract_single_file_text(file_path)
                        
                        if extracted_text and extracted_text.strip():
                            extracted_texts[file_path.name] = extracted_text
                            logger.info(f"bizInfo 신규 첨부파일 추출: {file_path.name} ({len(extracted_text)} chars)")
                        
                    except Exception as e:
                        logger.warning(f"bizInfo 신규 첨부파일 추출 실패 {file_path.name}: {e}")
                        continue
            
            logger.info(f"bizInfo 첨부파일 추출 완료: {len(extracted_texts)}개 파일")
            return extracted_texts
            
        except Exception as e:
            logger.error(f"bizInfo 첨부파일 추출 오류: {e}")
            return {}
    
    #현재 사용하지 않는 것으로 판단된다.
    def _extract_single_file_text(self, file_path: Path) -> str:
        """단일 파일에서 텍스트 추출"""
        
        try:
            from src.utils.convertUtil import convert_file_to_text
            
            # 파일 변환
            text = convert_file_to_text(file_path)
            
            if text and text.strip():
                return self._clean_extracted_text(text)
            else:
                logger.warning(f"텍스트 추출 결과 없음: {file_path.name}")
                return ""
                
        except Exception as e:
            logger.error(f"파일 텍스트 추출 실패 {file_path.name}: {e}")
            return ""
    
    def _clean_extracted_text(self, text: str) -> str:
        """추출된 텍스트 정리"""
        
        # 기본적인 텍스트 정리
        text = text.strip()
        
        # 과도한 공백 제거
        import re
        text = re.sub(r'\n\s*\n', '\n\n', text)  # 연속된 빈 줄을 하나로
        text = re.sub(r' +', ' ', text)  # 연속된 공백을 하나로
        
        return text

    def _classify_bizinfo_json_with_llm(self, json_content: str) -> dict:
        """bizInfo JSON → create_prompt_classification → LLM 분류"""
        
        try:
            from src.core.llmParserGpt import LLMParserGPT
            from src.core.promptManager import create_prompt_classification
            
            # 분류 전용 프롬프트 생성 (새로운 classification_prompt_template.txt 사용)
            full_prompt = create_prompt_classification(json_content)
            
            # LLM 호출
            llm_parser = LLMParserGPT()
            response = llm_parser._call_openai_api(
                prompt=full_prompt,
                max_tokens=800,
                temperature=0.2
            )
            
            # 분류 결과 파싱 (classification template 형식)
            return self._parse_classification_llm_response(response)
            
        except Exception as e:
            logger.error(f"bizInfo JSON LLM 분류 실패: {e}")
            return {
                "classification_type": "UNCLASSIFIED",
                "confidence_score": 0,
                "matched_keywords": [],
                "industry_keywords": []
            }

    def _parse_classification_llm_response(self, response: str) -> dict:
        """분류 전용 LLM 응답 파싱 (classification_prompt_template.txt 출력 형식)"""
        
        try:
            import json
            import re
            
            # JSON 부분 추출 (```json 블록 또는 일반 JSON)
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if not json_match:
                json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1) if '```json' in response else json_match.group()
                result = json.loads(json_str)
            else:
                # JSON 형식이 아닌 경우 텍스트에서 분류 타입 추출
                if "SMALL_BUSINESS" in response.upper():
                    return {"classification_type": "SMALL_BUSINESS", "confidence_score": 70, "matched_keywords": ["소상공인"], "industry_keywords": []}
                elif "SME" in response.upper() or "중소기업" in response:
                    return {"classification_type": "SME", "confidence_score": 70, "matched_keywords": ["중소기업"], "industry_keywords": []}
                elif "STARTUP" in response.upper() or "창업" in response:
                    return {"classification_type": "STARTUP", "confidence_score": 70, "matched_keywords": ["창업"], "industry_keywords": []}
                else:
                    return {"classification_type": "UNCLASSIFIED", "confidence_score": 0, "matched_keywords": [], "industry_keywords": []}
            
            # 새로운 classification template 출력 형식 처리
            parsed_result = {
                "classification_type": result.get("primary_classification", result.get("classification_type", "UNCLASSIFIED")),
                "confidence_score": max(0, min(100, int(result.get("confidence_score", 0)))),
                "matched_keywords": result.get("detected_keywords", result.get("matched_keywords", [])),
                "industry_keywords": result.get("industry_keywords", [])
            }
            
            # secondary_classifications가 있으면 industry_keywords로 활용
            if result.get("secondary_classifications"):
                parsed_result["industry_keywords"] = result["secondary_classifications"]
            
            # 분류 타입 검증
            valid_types = ["SMALL_BUSINESS", "SME", "STARTUP", "SOCIAL_ENTERPRISE", 
                          "INDUSTRY", "MIXED", "UNCLASSIFIED"]
            if parsed_result["classification_type"] not in valid_types:
                parsed_result["classification_type"] = "UNCLASSIFIED"
                parsed_result["confidence_score"] = 0
            
            return parsed_result
            
        except Exception as e:
            logger.error(f"분류 응답 파싱 실패: {e}")
            return {
                "classification_type": "UNCLASSIFIED",
                "confidence_score": 0,
                "matched_keywords": [],
                "industry_keywords": []
            }

    def _classify_from_json_content_directly(self, json_content: str) -> dict:
        """JSON 내용에서 직접 키워드 분석하여 분류 (LLM 실패시 fallback)"""
        
        try:
            import json
            
            # JSON 파싱
            data = json.loads(json_content)
            
            # 분석할 텍스트 필드들 추출
            analysis_texts = []
            
            # 핵심 필드들 수집 (우선순위 순서)
            if data.get("supportBusinessTitle"):
                analysis_texts.append(data["supportBusinessTitle"])
            
            if data.get("supportQualificationSummary"):
                analysis_texts.append(data["supportQualificationSummary"])
            
            if data.get("supportQualificationContents"):
                analysis_texts.append(data["supportQualificationContents"])
            
            if data.get("businessOverviewContents"):
                analysis_texts.append(data["businessOverviewContents"])
            
            if data.get("hashtags"):
                analysis_texts.append(data["hashtags"])
            
            # 전체 분석 텍스트 생성
            full_text = " ".join(analysis_texts).lower()
            
            # 키워드 기반 분류
            classification_result = self._classify_by_keywords_direct(full_text)
            
            logger.info(f"JSON 직접 분류 결과: {classification_result['classification_type']} ({classification_result['confidence_score']}%)")
            logger.info(f"분석 필드들: {[field for field in ['supportBusinessTitle', 'supportQualificationSummary', 'supportQualificationContents', 'businessOverviewContents', 'hashtags'] if data.get(field)]}")
            
            return classification_result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {e}")
            return {"classification_type": "UNCLASSIFIED", "confidence_score": 0, "matched_keywords": [], "industry_keywords": []}
        except Exception as e:
            logger.error(f"JSON 직접 분류 실패: {e}")
            return {"classification_type": "UNCLASSIFIED", "confidence_score": 0, "matched_keywords": [], "industry_keywords": []}
    
    def _classify_by_keywords_direct(self, text: str) -> dict:
        """키워드 직접 매칭 분류 (간단한 fallback 분류기)"""
        
        # 기본 키워드 매핑
        keyword_mapping = {
            "SME": ["중소기업", "중소벤처기업", "중견기업", "벤처기업", "벤처", "sme", "서울 중소기업", "서울소재 중소기업"],
            "SMALL_BUSINESS": ["소상공인", "소기업", "자영업", "개인사업자", "소상공인", "small business"],
            "STARTUP": ["창업", "예비창업", "창업기업", "스타트업", "startup", "창업자", "창업기업", "창업지원"],
            "SOCIAL_ENTERPRISE": ["사회적기업", "협동조합", "사회적경제", "소셜벤처", "social enterprise"],
            "INDUSTRY": ["제조업", "서비스업", "it", "바이오", "헬스케어", "농업", "관광", "문화콘텐츠"]
        }
        
        matched_keywords = []
        classification_scores = {}
        
        # 각 분류별 키워드 매칭
        for category, keywords in keyword_mapping.items():
            score = 0
            category_keywords = []
            
            for keyword in keywords:
                if keyword in text:
                    score += 1
                    category_keywords.append(keyword)
                    matched_keywords.append(keyword)
            
            if score > 0:
                classification_scores[category] = {
                    "score": score,
                    "keywords": category_keywords
                }
        
        # 최고 점수 분류 선택
        if not classification_scores:
            return {
                "classification_type": "UNCLASSIFIED",
                "confidence_score": 0,
                "matched_keywords": [],
                "industry_keywords": []
            }
        
        best_category = max(classification_scores.keys(), key=lambda k: classification_scores[k]["score"])
        best_score = classification_scores[best_category]["score"]
        
        # 신뢰도 점수 계산 (키워드 매칭 수 기반)
        confidence = min(100, best_score * 30)  # 키워드 1개당 30점, 최대 100점
        
        return {
            "classification_type": best_category,
            "confidence_score": confidence,
            "matched_keywords": classification_scores[best_category]["keywords"],
            "industry_keywords": classification_scores.get("INDUSTRY", {}).get("keywords", [])
        }

    def _extract_title_from_folder_name(self, folder_name: str) -> str:
        """폴더명에서 공고 제목 추출"""
        # 숫자_제목 형태에서 제목 부분만 추출
        match = re.match(r"^(\d+)_(.+)$", folder_name)
        if match:
            return match.group(2)
        return folder_name

    def _analyze_keywords(self, text: str) -> dict:
        """텍스트에서 키워드 분석"""

        analysis_result = {
            "matched_keywords": [],
            "industry_keywords": [],
            "classification_type": "UNCLASSIFIED",
            "confidence_score": 0,
        }

        if not self.keywords_cache:
            return analysis_result

        # 텍스트 전처리
        text = text.lower().replace(" ", "").replace("\n", " ")

        # 각 키워드 타입별 매칭
        type_scores = {
            "SMALL_BUSINESS": 0,
            "SME": 0,
            "STARTUP": 0,
            "SOCIAL_ENTERPRISE": 0,
        }

        # 1. 일반 키워드 매칭
        for kw_type, keywords in self.keywords_cache.items():
            if kw_type == "INDUSTRY":
                continue  # 업종 키워드는 별도 처리

            for keyword_info in keywords:
                match_info = self._match_keyword_in_text(text, keyword_info)
                if match_info:
                    analysis_result["matched_keywords"].append(match_info)
                    type_scores[kw_type] += match_info["weight"]

        # 2. 업종 키워드 매칭
        for keyword_info in self.keywords_cache.get("INDUSTRY", []):
            match_info = self._match_keyword_in_text(text, keyword_info)
            if match_info:
                match_info["industry_category"] = keyword_info.get("industry_category")
                analysis_result["industry_keywords"].append(match_info)
                type_scores["SMALL_BUSINESS"] += match_info[
                    "weight"
                ]  # 업종 키워드는 소상공인으로 분류

        # 3. 분류 타입 결정
        analysis_result["classification_type"] = self._determine_classification_type(
            type_scores, analysis_result
        )
        analysis_result["confidence_score"] = max(type_scores.values())

        return analysis_result

    def _match_keyword_in_text(self, text: str, keyword_info: dict) -> dict | None:
        """텍스트에서 맥락 기반 키워드 매칭"""

        keyword = keyword_info["keyword"].lower()
        synonyms = [s.lower() for s in keyword_info.get("synonyms", [keyword])]

        for synonym in synonyms:
            if synonym in text:
                # 매칭 위치와 맥락 확인
                position = text.find(synonym)
                context = text[max(0, position - 30) : position + len(synonym) + 30]

                # 맥락 기반 검증 - 네거티브 키워드 체크
                if self._is_negative_context(synonym, context):
                    continue

                # 맥락 기반 가중치 조정
                adjusted_weight = self._adjust_weight_by_context(
                    synonym, context, keyword_info["weight"]
                )

                return {
                    "keyword": keyword_info["keyword"],
                    "matched_synonym": synonym,
                    "weight": adjusted_weight,
                    "position": position,
                    "context": context.strip(),
                    "context_score": self._calculate_context_score(synonym, context),
                }

        return None

    def _analyze_keywords_per_file(self, filename_to_text: dict[str, str]) -> dict:
        """파일별 키워드 분석 결과 집계(파일 상관관계 보강)

        Returns:
            {
              'matched_keywords': [ { ... , 'file_name': str }, ... ],
              'industry_keywords': [ { ... , 'file_name': str }, ... ]
            }
        """
        aggregated_matches: list[dict] = []
        aggregated_industry: list[dict] = []

        if not filename_to_text:
            return {"matched_keywords": [], "industry_keywords": []}

        for file_name, file_text in filename_to_text.items():
            # 개별 파일 텍스트에 대해 기존 분석 수행
            file_analysis = self._analyze_keywords(file_text)
            for m in file_analysis.get("matched_keywords", []) or []:
                m_with_file = dict(m)
                m_with_file["file_name"] = file_name
                aggregated_matches.append(m_with_file)
            for im in file_analysis.get("industry_keywords", []) or []:
                im_with_file = dict(im)
                im_with_file["file_name"] = file_name
                aggregated_industry.append(im_with_file)

        return {
            "matched_keywords": aggregated_matches,
            "industry_keywords": aggregated_industry,
        }

    def _is_negative_context(self, keyword: str, context: str) -> bool:
        """네거티브 맥락 확인 - 키워드가 부정적 맥락에서 사용되었는지 검사"""

        # 키워드별 네거티브 패턴 정의
        negative_patterns = {
            "소상공인": ["지원센터", "진흥원", "청", "단체", "협회", "기관"],
            "중소기업": ["지원센터", "진흥원", "청", "단체", "협회", "기관", "연합회"],
            "스타트업": ["센터", "인큐베이터", "액셀러레이터", "지원기관"],
            "사회적기업": ["진흥원", "센터", "협의회"],
        }

        if keyword in negative_patterns:
            for negative_word in negative_patterns[keyword]:
                if negative_word in context:
                    logger.debug(
                        f"네거티브 맥락 감지: '{keyword}' + '{negative_word}' in '{context}'"
                    )
                    return True

        return False

    def _adjust_weight_by_context(
        self, keyword: str, context: str, original_weight: int
    ) -> int:
        """맥락에 따른 가중치 조정"""

        # 긍정적 맥락 키워드 (가중치 증가)
        positive_keywords = ["지원", "대상", "신청", "모집", "선정", "선발", "참여"]

        # 부정적 맥락 키워드 (가중치 감소)
        negative_keywords = ["제외", "해당없음", "불가", "제한"]

        adjusted_weight = original_weight

        for pos_word in positive_keywords:
            if pos_word in context:
                adjusted_weight += 2
                break

        for neg_word in negative_keywords:
            if neg_word in context:
                adjusted_weight = max(1, adjusted_weight - 3)
                break

        return adjusted_weight

    def _calculate_context_score(self, keyword: str, context: str) -> float:
        """맥락 점수 계산"""

        # 맥락의 품질을 평가하는 키워드들
        high_quality_words = [
            "지원대상",
            "모집대상",
            "신청자격",
            "지원자격",
            "참여대상",
        ]
        medium_quality_words = ["지원", "모집", "신청", "대상", "자격"]

        score = 0.5  # 기본 점수

        for word in high_quality_words:
            if word in context:
                score += 0.3

        for word in medium_quality_words:
            if word in context:
                score += 0.1

        return min(1.0, score)

    def _determine_classification_type(
        self, type_scores: dict, analysis_result: dict
    ) -> str:
        """키워드 점수 기반 분류 타입 결정"""

        # 최고 점수 타입 선택
        max_score = max(type_scores.values())

        if max_score == 0:
            return "UNCLASSIFIED"

        # 높은 점수를 가진 타입들
        high_score_types = [t for t, s in type_scores.items() if s >= max_score]

        # 소상공인 + 업종 키워드가 매칭되면 소상공인으로 확정
        if (
            type_scores["SMALL_BUSINESS"] > 0
            and len(analysis_result["industry_keywords"]) > 0
        ):
            return "SMALL_BUSINESS"

        # 복합 타입 판단
        if len(high_score_types) > 1:
            return "MIXED"

        # 단일 타입
        for t, s in type_scores.items():
            if s == max_score:
                return t

        return "UNCLASSIFIED"

    def get_classification_summary(self, analysis_result: dict) -> str:
        """분류 결과 요약"""

        summary_parts = []

        # 분류 타입
        summary_parts.append(f"분류: {analysis_result['classification_type']}")

        # 신뢰도
        summary_parts.append(f"신뢰도: {analysis_result['confidence_score']}")

        # 매칭된 키워드 수
        keyword_count = len(analysis_result["matched_keywords"])
        industry_count = len(analysis_result["industry_keywords"])
        summary_parts.append(f"키워드: {keyword_count}개")

        if industry_count > 0:
            summary_parts.append(f"업종: {industry_count}개")

        return " | ".join(summary_parts)
