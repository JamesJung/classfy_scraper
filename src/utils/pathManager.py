"""
환경 독립적 파일 경로 관리자
프로덕션 환경과 개발 환경 간의 파일 경로 차이를 해결하기 위한 유틸리티
"""

import os
from pathlib import Path

from src.core.baseManager import SingletonManager


class PathManager(SingletonManager):
    """
    파일 경로를 환경 독립적으로 관리하는 클래스

    - DB 저장: 상대 경로 (data.origin 기준)
    - 파일 접근: 절대 경로 (환경별 base_dir + 상대 경로)
    - 기존 절대 경로 데이터 호환성 보장
    """

    _instance = None

    def __new__(cls):
        """싱글톤 패턴으로 인스턴스 생성"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """PathManager 초기화"""
        super().__init__("PathManager")
        if not self.is_initialized:
            self._load_config()
            if self.initialize():
                self.logger.info("PathManager 초기화 완료")

    def _load_config(self):
        """설정 파일에서 경로 정보 로드"""
        try:
            # 환경 변수를 먼저 확인 (프로덕션 환경 우선)
            env_input_dir = (
                os.environ.get("INPUT_DIR")
                or os.environ.get("DATA_ORIGIN_PATH")
                or os.environ.get("GRANT_INFO_DATA_DIR")
            )

            if env_input_dir:
                self.input_dir = os.path.abspath(env_input_dir)
                self.logger.info(
                    f"PathManager using environment variable: {self.input_dir}"
                )
            else:
                # 환경 변수가 없으면 설정 파일 사용
                config = self.config
                self.input_dir = config.get("directories", "input_dir")
                self.input_dir = os.path.abspath(self.input_dir)
                self.logger.info(f"PathManager using config file: {self.input_dir}")

            self.data_origin_marker = "data.origin"

        except Exception as e:
            # 모든 설정 로드 실패시 기본값 사용
            self.logger.error(f"Config load failed, using fallback: {e}")
            self.input_dir = str(Path(__file__).parent.parent / "data.origin")
            self.data_origin_marker = "data.origin"

    def initialize(self) -> bool:
        """PathManager 초기화 완료"""
        try:
            # input_dir 유효성 검증
            if not os.path.exists(self.input_dir):
                self.logger.warning(
                    f"입력 디렉토리가 존재하지 않습니다: {self.input_dir}"
                )
                return False

            self._initialized = True
            return True
        except Exception as e:
            self.logger.error(f"PathManager 초기화 실패: {e}")
            return False

    def store_file_path(self, absolute_path: str | Path) -> str:
        """
        파일의 절대 경로를 DB 저장용 상대 경로로 변환

        Args:
            absolute_path: 파일의 절대 경로

        Returns:
            str: data.origin 기준 상대 경로 (예: "btp/003_공고/attachments/파일.hwp")

        Examples:
            >>> pm = PathManager()
            >>> absolute = "/mnt/d/workspace/sources/grant_info-main/data.origin/btp/001_공고/file.pdf"
            >>> pm.store_file_path(absolute)
            "btp/001_공고/file.pdf"
        """
        try:
            absolute_path = str(absolute_path)

            # 이미 상대 경로인 경우 그대로 반환
            if not absolute_path.startswith("/"):
                return absolute_path

            # input_dir 기준으로 상대 경로 계산
            path_obj = Path(absolute_path)
            input_path_obj = Path(self.input_dir)

            # 상대 경로 계산
            try:
                relative_path = path_obj.relative_to(input_path_obj)
                result = str(relative_path).replace("\\", "/")  # Windows 호환성

                self.logger.debug(f"Path converted: {absolute_path} -> {result}")
                return result

            except ValueError:
                # input_dir 기준으로 계산할 수 없는 경우
                # data.origin 마커를 찾아서 그 이후 부분 추출
                if self.data_origin_marker in absolute_path:
                    marker_index = absolute_path.find(self.data_origin_marker)
                    marker_end = (
                        marker_index + len(self.data_origin_marker) + 1
                    )  # +1 for '/'
                    if marker_end < len(absolute_path):
                        result = absolute_path[marker_end:]
                        self.logger.debug(
                            f"Path extracted by marker: {absolute_path} -> {result}"
                        )
                        return result

                # 모든 방법이 실패한 경우 원본 경로 반환 (하위 호환성)
                self.logger.warning(f"Cannot convert to relative path: {absolute_path}")
                return absolute_path

        except Exception as e:
            self.logger.error(f"Error in store_file_path: {e}")
            return str(absolute_path)

    def resolve_file_path(self, stored_path: str) -> str:
        """
        DB에 저장된 경로를 실제 파일 시스템 경로로 복원

        Args:
            stored_path: DB에 저장된 경로 (상대 경로 또는 절대 경로)

        Returns:
            str: 실제 파일 시스템 절대 경로

        Examples:
            >>> pm = PathManager()
            >>> stored = "btp/001_공고/file.pdf"
            >>> pm.resolve_file_path(stored)
            "/app/grant_info/data.origin/btp/001_공고/file.pdf"
        """
        try:
            if not stored_path:
                return ""

            # 절대 경로인 경우 (기존 데이터 호환성)
            if stored_path.startswith("/"):
                resolved = self._resolve_legacy_path(stored_path)
                self.logger.debug(f"Legacy path resolved: {stored_path} -> {resolved}")
                return resolved

            # 상대 경로인 경우 (새로운 방식)
            resolved = os.path.join(self.input_dir, stored_path)
            resolved = os.path.abspath(resolved)

            self.logger.debug(f"Relative path resolved: {stored_path} -> {resolved}")
            return resolved

        except Exception as e:
            self.logger.error(f"Error in resolve_file_path: {e}")
            return stored_path

    def _resolve_legacy_path(self, legacy_path: str) -> str:
        """
        기존 절대 경로 데이터를 현재 환경에 맞게 변환

        Args:
            legacy_path: 기존 절대 경로

        Returns:
            str: 현재 환경에 맞는 절대 경로
        """
        try:
            # 알려진 개발 환경 경로들을 현재 환경으로 변환
            legacy_prefixes = [
                "/mnt/d/workspace/sources/grant_info-main/data.origin/",
                "/home/jwj/grant_info/data/",
                "/app/grant_info/data.origin/",  # 이미 프로덕션 경로인 경우
            ]

            for prefix in legacy_prefixes:
                if legacy_path.startswith(prefix):
                    # 상대 경로 부분 추출
                    relative_part = legacy_path[len(prefix) :]
                    # 현재 환경 경로로 결합
                    resolved = os.path.join(self.input_dir, relative_part)
                    return os.path.abspath(resolved)

            # 매칭되는 prefix가 없는 경우 원본 반환
            return legacy_path

        except Exception as e:
            self.logger.error(f"Error in _resolve_legacy_path: {e}")
            return legacy_path

    def file_exists(self, stored_path: str) -> bool:
        """
        저장된 경로의 파일 존재 여부 확인

        Args:
            stored_path: DB에 저장된 경로

        Returns:
            bool: 파일 존재 여부
        """
        try:
            actual_path = self.resolve_file_path(stored_path)
            exists = os.path.exists(actual_path)

            if not exists:
                self.logger.debug(f"File not found: {stored_path} -> {actual_path}")

            return exists

        except Exception as e:
            self.logger.error(f"Error checking file existence: {e}")
            return False

    def get_file_info(self, stored_path: str) -> dict:
        """
        파일 정보 반환 (존재 여부, 크기, 수정 시간 등)

        Args:
            stored_path: DB에 저장된 경로

        Returns:
            dict: 파일 정보
        """
        try:
            actual_path = self.resolve_file_path(stored_path)

            if not os.path.exists(actual_path):
                return {
                    "exists": False,
                    "stored_path": stored_path,
                    "resolved_path": actual_path,
                    "error": "File not found",
                }

            stat = os.stat(actual_path)
            return {
                "exists": True,
                "stored_path": stored_path,
                "resolved_path": actual_path,
                "size": stat.st_size,
                "modified_time": stat.st_mtime,
                "is_file": os.path.isfile(actual_path),
                "is_directory": os.path.isdir(actual_path),
            }

        except Exception as e:
            return {
                "exists": False,
                "stored_path": stored_path,
                "resolved_path": "",
                "error": str(e),
            }

    def validate_config(self) -> dict:
        """
        PathManager 설정 검증

        Returns:
            dict: 검증 결과
        """
        try:
            validation = {
                "input_dir_exists": os.path.exists(self.input_dir),
                "input_dir_readable": os.access(self.input_dir, os.R_OK),
                "input_dir_path": self.input_dir,
                "config_loaded": hasattr(self, "input_dir"),
                "warnings": [],
            }

            if not validation["input_dir_exists"]:
                validation["warnings"].append(
                    f"Input directory does not exist: {self.input_dir}"
                )

            if not validation["input_dir_readable"]:
                validation["warnings"].append(
                    f"Input directory is not readable: {self.input_dir}"
                )

            return validation

        except Exception as e:
            return {"error": str(e), "config_loaded": False}


# 전역 인스턴스 (싱글톤)
_path_manager_instance = None


def get_path_manager() -> PathManager:
    """PathManager 싱글톤 인스턴스 반환"""
    global _path_manager_instance
    if _path_manager_instance is None:
        _path_manager_instance = PathManager()
    return _path_manager_instance


def reset_path_manager():
    """PathManager 싱글톤 인스턴스 재설정 (환경 변수 변경 시 사용)"""
    global _path_manager_instance
    _path_manager_instance = None
    # 클래스 레벨 싱글톤도 재설정
    PathManager._instance = None
