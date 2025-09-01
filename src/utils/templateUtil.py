import json
import traceback
from pathlib import Path
from typing import Any

from src.config.logConfig import setup_logging

logger = setup_logging(__name__)

# 템플릿 디렉토리 경로
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

# 템플릿 파일 경로들
TEMPLATE_PATHS = {
    "main_prompt_path": TEMPLATE_DIR / "main_prompt_template.txt",
    "md_prompt_path": TEMPLATE_DIR / "md_prompt_template.txt",
    "json_api_prompt_path": TEMPLATE_DIR / "json_api_prompt_template.txt",
    "classification_prompt_path": TEMPLATE_DIR / "classification_prompt_template.txt",
    "synonym_path": TEMPLATE_DIR / "synonyms_template_lite.json",
    "json_path": TEMPLATE_DIR / "json_template.json",
    "example_path": TEMPLATE_DIR / "example_template.json",
    "api_path": TEMPLATE_DIR / "api_template.json",
}

# 캐시된 템플릿 데이터
_template_cache: dict[str, Any] = {}
_section_cache: dict[str, dict[str, str]] = {}


def get_template_path(template_type: str) -> Path:
    """
    템플릿 파일의 경로를 반환합니다.

    Args:
        template_type: 템플릿 타입 ("main_prompt_path", "synonym_path", "json_path", "example_path", "api_path")

    Returns:
        템플릿 파일 경로
    """
    return TEMPLATE_PATHS[template_type]


def extract_section(content: str, section_name: str) -> str | None:
    """
    템플릿에서 특정 섹션을 추출합니다.

    Args:
        content: 전체 템플릿 내용
        section_name: 추출할 섹션 이름

    Returns:
        추출된 섹션 내용 또는 None
    """
    start_marker = f"[{section_name}]"
    end_marker = f"[/{section_name}]"

    start = content.find(start_marker)
    end = content.find(end_marker)

    if start != -1 and end != -1:
        return content[start + len(start_marker) : end].strip()
    return None


def load_template_sections(template_path: Path) -> dict[str, str]:
    """
    템플릿 파일에서 모든 섹션을 로드하고 캐시합니다.

    Args:
        template_path: 템플릿 파일 경로

    Returns:
        섹션 이름과 내용을 매핑한 딕셔너리
    """
    cache_key = str(template_path)
    if cache_key in _section_cache:
        return _section_cache[cache_key]

    try:
        # 파일 존재성 및 읽기 권한 확인
        if not template_path.exists():
            logger.error(f"템플릿 파일이 존재하지 않습니다: {template_path}")
            return {}
        
        if not template_path.is_file():
            logger.error(f"템플릿 경로가 파일이 아닙니다: {template_path}")
            return {}

        with open(template_path, encoding="utf-8") as f:
            content = f.read()
            sections = {}

            # 파일 내용에서 모든 섹션 찾기
            lines = content.split("\n")
            current_section = None
            current_content = []

            for line in lines:
                if (
                    line.startswith("[")
                    and line.endswith("]")
                    and not line.startswith("[/")
                ):
                    # 새로운 섹션 시작
                    if current_section:
                        sections[current_section] = "\n".join(current_content).strip()
                    current_section = line[1:-1]
                    current_content = []
                elif line.startswith(f"[/{current_section}]"):
                    # 현재 섹션 종료
                    sections[current_section] = "\n".join(current_content).strip()
                    current_section = None
                    current_content = []
                elif current_section:
                    # 현재 섹션에 내용 추가
                    current_content.append(line)

            # 마지막 섹션 처리
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()

            _section_cache[cache_key] = sections
            logger.info(f"템플릿 섹션 로드 완료: {template_path}")
            return sections

    except Exception as e:
        logger.error(f"템플릿 섹션 로드 실패: {e}")
        raise


def get_template_section(section_name: str, template_path: Path) -> str:
    """
    특정 섹션의 내용을 반환합니다.

    Args:
        section_name: 가져올 섹션 이름
        template_path: 템플릿 파일 경로

    Returns:
        섹션 내용 문자열
    """
    sections = load_template_sections(template_path)
    return sections.get(section_name, "")


def load_json_template(json_path: Path) -> str:
    """
    JSON 템플릿을 로드하고 문자열로 반환합니다.

    Args:
        json_path: JSON 템플릿 파일 경로

    Returns:
        JSON 문자열
    """
    cache_key = str(json_path)
    if cache_key in _template_cache:
        return _template_cache[cache_key]

    try:
        with open(json_path, encoding="utf-8") as f:
            template = json.load(f)
            json_str = json.dumps(template, ensure_ascii=False, indent=2)
            _template_cache[cache_key] = json_str
            return json_str
    except Exception as e:
        logger.error(f"JSON 템플릿 로드 실패: {e}")
        raise


def load_synonym(synonym_path: Path) -> str:
    """
    동의어/유사어 템플릿을 로드하고 문자열로 반환합니다.

    Args:
        synonyms_path: 동의어/유사어 템플릿 파일 경로

    Returns:
        JSON 문자열
    """
    cache_key = str(synonym_path)
    if cache_key in _template_cache:
        return _template_cache[cache_key]

    try:
        if synonym_path.exists():
            with open(synonym_path, encoding="utf-8") as f:
                synonyms = json.load(f)
                json_str = json.dumps(synonyms, ensure_ascii=False, indent=2)
                _template_cache[cache_key] = json_str
                return json_str
        else:
            raise FileNotFoundError("동의어/유사어 템플릿 파일이 없습니다")
    except Exception as e:
        logger.error(f"동의어/유사어 템플릿 로드 실패: {e}")
        raise


def load_api_data(api_data_path: Path) -> str:
    """
    API 데이터 템플릿을 로드하고 문자열로 반환합니다.

    Args:
        api_data_path: API 데이터 템플릿 파일 경로

    Returns:
        JSON 문자열
    """
    cache_key = str(api_data_path)
    if cache_key in _template_cache:
        return _template_cache[cache_key]

    try:
        if api_data_path.exists():
            with open(api_data_path, encoding="utf-8") as f:
                api_data = json.load(f)
                json_str = json.dumps(api_data, ensure_ascii=False, indent=2)
                _template_cache[cache_key] = json_str
                return json_str
        else:
            raise FileNotFoundError("API 데이터 템플릿 파일이 없습니다")
    except Exception as e:
        logger.error(f"API 데이터 템플릿 로드 실패: {e}")
        raise


def load_examples(examples_path: Path) -> str:
    """
    Few-Shot 예시를 로드하고 문자열로 반환합니다.

    Args:
        examples_path: 예시 파일 경로

    Returns:
        예시 문자열
    """
    cache_key = str(examples_path)
    if cache_key in _template_cache:
        return _template_cache[cache_key]

    try:
        with open(examples_path, encoding="utf-8") as f:
            examples_data = json.load(f)

        # 출력 데이터를 문자열로 변환
        for example in examples_data["examples"]:
            if isinstance(example["output"], dict):
                example["output"] = json.dumps(
                    example["output"], ensure_ascii=False, indent=2
                )

        # 예시 문자열 생성
        examples_str = "\n".join(
            [
                f"## 예시\n입력:\n{example['input']}\n\n출력:\n{example['output']}"
                for example in examples_data["examples"]
            ]
        )

        _template_cache[cache_key] = examples_str
        return examples_str

    except Exception as e:
        logger.error(f"Few-Shot 예시 파일 로드 실패: {e}")
        raise


def generate_json_file(data: dict[str, Any], output_json_path: Path) -> bool:
    """
    JSON 파일을 생성합니다.

    Args:
        data: 생성할 JSON 데이터
        output_json_path: 출력할 JSON 파일 경로

    Returns:
        성공 여부 (True/False)
    """
    try:
        # 디렉토리 생성
        output_json_path.parent.mkdir(parents=True, exist_ok=True)

        with open(TEMPLATE_PATHS["json_path"], encoding="utf-8") as f:
            json_template = json.load(f)
            for key, value in data.items():
                if key in json_template:
                    json_template[key] = value

            # 병합된 결과 저장
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(json_template, f, ensure_ascii=False, indent=2)
                logger.info(f"JSON 파일 생성 완료: {output_json_path}")
        return True

    except Exception as e:
        logger.error(f"JSON 파일 생성 실패: {e}\n{traceback.format_exc()}")
        return False
