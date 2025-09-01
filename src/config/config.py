import configparser
import os
import re
from pathlib import Path
from typing import Any

from src.config.logConfig import setup_logging

logger = setup_logging()

# .env 파일 로드를 시도합니다.
try:
    from dotenv import load_dotenv

    load_dotenv()
    logger.info(".env 파일을 로드했습니다.")
except ImportError:
    logger.warning(
        "python-dotenv가 설치되지 않았습니다. .env 파일을 사용하지 않습니다."
    )


class ConfigManager:
    """
    설정 파일을 파싱하고 관리합니다.
    환경 변수를 통해 설정을 동적으로 오버라이드할 수 있습니다.
    """

    _instance = None
    _config_cache: dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized") or not self._initialized:
            self._config_file_path = Path(__file__).parent / "config.ini"
            self._type_conversion_map = self._build_type_conversion_map()
            self._load_config()
            self._initialized = True

    def _build_type_conversion_map(self) -> dict[str, dict[str, Any]]:
        """타입 변환이 필요한 필드를 미리 정의합니다."""
        return {
            "database": {"port": int},
            "llm_api": {
                "max_tokens": int,
                "temperature": float,
                "retry_attempts": int,
                "retry_delay": int,
            },
            "ollama_api": {
                "url": str,
                "model": str,
            },
            "async_processing": {
                "enabled": bool,
                "max_workers": int,
                "max_memory_mb": int,
                "queue_size": int,
                "file_processing_timeout": int,
                "progress_report_interval": int,
            },
            "md_field_merge": {
                "enabled": bool,
                "log_level": int,
                "min_merge_threshold": int,
                "priority_fields_only": bool,
            },
            "duplicate_check": {
                "enabled": bool,
                "enable_cache": bool,
                "cache_ttl_hours": int,
                "batch_size": int,
                "title_similarity_threshold": float,
                "skip_on_duplicate": bool,
            },
            "exclusion_filter": {
                "enabled": bool,
                "log_exclusions": bool,
                "db_logging": bool,
            },
            "logging": {
                "console_output": bool,
                "file_output": bool,
                "backup_count": int,
            },
        }

    def _substitute_env_vars(self, value: str) -> str:
        """
        환경 변수를 치환합니다. ${VAR_NAME} 또는 ${VAR_NAME:default_value} 형식을 지원합니다.
        production_config.py에서 가져온 향상된 버전입니다.
        """
        if not isinstance(value, str):
            return value

        def replace_var(match):
            var_spec = match.group(1)
            if ":" in var_spec:
                var_name, default_value = var_spec.split(":", 1)
            else:
                var_name, default_value = var_spec, None

            env_value = os.getenv(var_name.strip())

            if env_value is not None:
                return env_value
            if default_value is not None:
                return default_value.strip()

            logger.warning(
                f"환경 변수 '{var_name}'이(가) 설정되지 않았고 기본값도 없습니다."
            )
            return ""  # 빈 문자열로 대체

        return re.sub(r"\$\{([^}]+)\}", replace_var, value)

    def _convert_value(self, value: str) -> Any:
        """문자열 값을 적절한 타입으로 변환합니다."""
        value_lower = value.lower()
        if value_lower in ("true", "yes", "on"):
            return True
        if value_lower in ("false", "no", "off"):
            return False
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def _load_config(self):
        """설정 파일을 읽고 파싱하여 캐시에 저장합니다."""
        if ConfigManager._config_cache:
            return

        parser = configparser.ConfigParser()
        try:
            parser.read(self._config_file_path, encoding="utf-8")
        except FileNotFoundError:
            logger.error(f"설정 파일을 찾을 수 없습니다: {self._config_file_path}")
            raise

        config: dict[str, Any] = {}
        for section in parser.sections():
            config[section] = {}
            for key, value in parser.items(section):
                # 1. 환경 변수 치환
                processed_value = self._substitute_env_vars(value)

                # 2. 타입 변환
                converter = self._type_conversion_map.get(section, {}).get(key)
                if converter:
                    try:
                        if converter is bool:
                            processed_value = processed_value.lower() in (
                                "true",
                                "1",
                                "yes",
                                "on",
                            )
                        else:
                            processed_value = converter(processed_value)
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"[{section}]{key}의 값 '{processed_value}'를 {converter.__name__}으로 변환하지 못했습니다: {e}"
                        )
                # 3. 필드(리스트) 처리
                elif section == "fields" and key in ["required", "optional"]:
                    processed_value = [
                        item.strip()
                        for item in processed_value.split(",")
                        if item.strip()
                    ]

                config[section][key] = processed_value

        ConfigManager._config_cache = config
        logger.info("설정 파일을 성공적으로 로드하고 캐시했습니다.")

    def get_config(self) -> dict[str, Any]:
        """캐시된 전체 설정을 반환합니다."""
        return ConfigManager._config_cache

    def get_section(self, section: str) -> dict[str, Any]:
        """특정 섹션의 설정을 반환합니다."""
        return ConfigManager._config_cache.get(section, {})

    def get_value(self, section: str, key: str, default: Any = None) -> Any:
        """특정 설정 값을 반환합니다."""
        return ConfigManager._config_cache.get(section, {}).get(key, default)


# 전역 인스턴스 생성
config_manager = ConfigManager()


def get_config() -> dict[str, Any]:
    """전체 설정 객체를 가져오는 헬퍼 함수."""
    return config_manager.get_config()
