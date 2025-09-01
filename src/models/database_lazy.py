"""
데이터베이스 지연 로딩 모듈
Database Lazy Loading Module

데이터베이스 연결을 실제 필요한 시점에 생성하여 초기화 시간을 단축합니다.
"""

import threading

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from src.config.config import ConfigManager
from src.config.logConfig import setup_logging

# 로깅 설정
logger = setup_logging(__name__)


class LazyDatabaseConnection:
    """
    지연 로딩 데이터베이스 연결 관리자
    스레드 안전한 싱글톤 패턴으로 구현
    """

    _instance = None
    _lock = threading.Lock()
    _engine: Engine | None = None
    _session_local: sessionmaker | None = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 중복 초기화 방지
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

    def get_engine(self) -> Engine:
        """
        데이터베이스 엔진을 지연 로딩으로 반환

        Returns:
            SQLAlchemy Engine 객체
        """
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    logger.info("데이터베이스 엔진 초기화 시작...")

                    try:
                        # 설정 로드
                        config = ConfigManager().get_config()
                        db_config = config["database"]

                        # Database connection URL
                        database_url = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['name']}"

                        # Create SQLAlchemy engine with connection pooling
                        self._engine = create_engine(
                            database_url,
                            echo=False,
                            pool_size=10,  # 연결 풀 크기
                            max_overflow=20,  # 추가 연결 가능 수
                            pool_timeout=30,  # 연결 대기 시간
                            pool_recycle=3600,  # 연결 재활용 시간 (1시간)
                            pool_pre_ping=True,  # 연결 상태 사전 확인
                        )

                        logger.info("데이터베이스 엔진 초기화 완료")

                    except Exception as e:
                        logger.error(f"데이터베이스 엔진 초기화 실패: {e}")
                        raise

        return self._engine

    def get_session_local(self) -> sessionmaker:
        """
        세션메이커를 지연 로딩으로 반환

        Returns:
            SQLAlchemy SessionLocal 객체
        """
        if self._session_local is None:
            with self._lock:
                if self._session_local is None:
                    logger.info("데이터베이스 세션메이커 초기화...")
                    engine = self.get_engine()  # 엔진이 없으면 자동으로 생성
                    self._session_local = sessionmaker(
                        autocommit=False, autoflush=False, bind=engine
                    )
                    logger.info("데이터베이스 세션메이커 초기화 완료")

        return self._session_local

    def is_initialized(self) -> bool:
        """
        데이터베이스 연결이 초기화되었는지 확인

        Returns:
            초기화 여부
        """
        return self._engine is not None and self._session_local is not None

    def close_connections(self):
        """
        모든 데이터베이스 연결 정리
        """
        if self._engine is not None:
            logger.info("데이터베이스 연결 정리...")
            self._engine.dispose()
            self._engine = None
            self._session_local = None
            logger.info("데이터베이스 연결 정리 완료")


# 전역 지연 로딩 인스턴스
_lazy_db = LazyDatabaseConnection()


def get_lazy_engine() -> Engine:
    """
    지연 로딩 데이터베이스 엔진 반환

    Returns:
        SQLAlchemy Engine 객체
    """
    return _lazy_db.get_engine()


def get_lazy_session_local() -> sessionmaker:
    """
    지연 로딩 세션메이커 반환

    Returns:
        SQLAlchemy SessionLocal 객체
    """
    return _lazy_db.get_session_local()


def is_database_initialized() -> bool:
    """
    데이터베이스가 초기화되었는지 확인

    Returns:
        초기화 여부
    """
    return _lazy_db.is_initialized()


def cleanup_database_connections():
    """
    데이터베이스 연결 정리
    """
    _lazy_db.close_connections()
