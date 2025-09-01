"""
데이터베이스 연결 풀 관리자
성능 최적화를 위한 연결 풀링 시스템
"""

import logging
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """데이터베이스 연결 풀 관리자"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """싱글톤 패턴 구현"""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: dict[str, Any] = None):
        """연결 풀 초기화"""
        if hasattr(self, "_initialized"):
            return

        self.config = config or {}
        self.engine = None
        self.SessionFactory = None
        self.scoped_session_factory = None

        # 풀 설정
        self.pool_size = self.config.get("pool_size", 10)
        self.max_overflow = self.config.get("max_overflow", 20)
        self.pool_timeout = self.config.get("pool_timeout", 30)
        self.pool_recycle = self.config.get("pool_recycle", 3600)  # 1시간
        self.pool_pre_ping = self.config.get("pool_pre_ping", True)

        # 통계
        self.stats = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0,
            "pool_overflows": 0,
            "last_reset": datetime.now(),
        }

        self._initialized = True
        logger.info("DatabaseConnectionPool 초기화 완료")

    def initialize_pool(self, database_url: str):
        """연결 풀 초기화"""
        try:
            # 엔진 생성 (연결 풀 설정 포함)
            self.engine = create_engine(
                database_url,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,
                pool_recycle=self.pool_recycle,
                pool_pre_ping=self.pool_pre_ping,
                echo=False,  # SQL 로깅 비활성화 (성능)
                future=True,
                connect_args={
                    "charset": "utf8mb4",
                    "collation": "utf8mb4_unicode_ci",
                    "autocommit": False,
                    "connect_timeout": 10,
                    "read_timeout": 30,
                    "write_timeout": 30,
                },
            )

            # 세션 팩토리 생성
            self.SessionFactory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )

            # 스코프드 세션 (스레드 안전)
            self.scoped_session_factory = scoped_session(self.SessionFactory)

            # 연결 풀 이벤트 리스너 등록
            self._register_pool_events()

            # 연결 테스트
            self._test_connection()

            logger.info(
                f"✅ DB 연결 풀 초기화 완료 - "
                f"Pool Size: {self.pool_size}, Max Overflow: {self.max_overflow}"
            )

        except Exception as e:
            logger.error(f"❌ DB 연결 풀 초기화 실패: {e}")
            raise

    def _register_pool_events(self):
        """연결 풀 이벤트 리스너 등록"""

        @event.listens_for(self.engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            """연결 생성 시"""
            self.stats["total_connections"] += 1
            self.stats["active_connections"] += 1
            logger.debug(
                f"🔗 새 DB 연결 생성 - 활성 연결: {self.stats['active_connections']}"
            )

        @event.listens_for(self.engine, "checkout")
        def on_checkout(dbapi_connection, connection_record, connection_proxy):
            """연결 체크아웃 시"""
            logger.debug("📤 DB 연결 체크아웃")

        @event.listens_for(self.engine, "checkin")
        def on_checkin(dbapi_connection, connection_record):
            """연결 체크인 시"""
            logger.debug("📥 DB 연결 체크인")

        @event.listens_for(self.engine, "close")
        def on_close(dbapi_connection, connection_record):
            """연결 종료 시"""
            self.stats["active_connections"] = max(
                0, self.stats["active_connections"] - 1
            )
            logger.debug(
                f"❌ DB 연결 종료 - 활성 연결: {self.stats['active_connections']}"
            )

        # SQLAlchemy 버전별 이벤트 이름 차이 대응
        try:

            @event.listens_for(self.engine, "invalidate")
            def on_invalidate(dbapi_connection, connection_record, exception):
                """연결 무효화 시 (SQLAlchemy 2.x)"""
                self.stats["failed_connections"] += 1
                logger.warning(f"⚠️ DB 연결 무효화: {exception}")

        except Exception:
            try:

                @event.listens_for(self.engine, "invalid")
                def on_invalid(dbapi_connection, connection_record, exception):
                    """연결 무효화 시 (SQLAlchemy 1.x)"""
                    self.stats["failed_connections"] += 1
                    logger.warning(f"⚠️ DB 연결 무효화: {exception}")

            except Exception:
                logger.warning(
                    "⚠️ 연결 무효화 이벤트 리스너 등록 실패 (버전 호환성 문제)"
                )

    def _test_connection(self):
        """연결 테스트"""
        try:
            with self.get_session() as session:
                result = session.execute(text("SELECT 1")).scalar()
                if result != 1:
                    raise Exception("연결 테스트 실패")
            logger.info("✅ DB 연결 테스트 성공")
        except Exception as e:
            logger.error(f"❌ DB 연결 테스트 실패: {e}")
            raise

    @contextmanager
    def get_session(self):
        """컨텍스트 매니저로 세션 제공"""
        if not self.scoped_session_factory:
            raise RuntimeError("연결 풀이 초기화되지 않았습니다")

        session = self.scoped_session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"DB 세션 오류: {e}")
            raise
        finally:
            session.close()
            self.scoped_session_factory.remove()

    @contextmanager
    def get_batch_session(self, autocommit_interval: int = 1000):
        """배치 처리용 세션 (대량 INSERT용)"""
        if not self.scoped_session_factory:
            raise RuntimeError("연결 풀이 초기화되지 않았습니다")

        session = self.scoped_session_factory()
        try:
            session.autoflush = False  # 자동 플러시 비활성화
            batch_count = 0

            def batch_commit():
                nonlocal batch_count
                batch_count += 1
                if batch_count % autocommit_interval == 0:
                    session.commit()
                    logger.debug(f"배치 커밋 #{batch_count // autocommit_interval}")

            # 배치 커밋 함수를 세션에 추가
            session.batch_commit = batch_commit

            yield session

            # 남은 작업 커밋
            if batch_count % autocommit_interval != 0:
                session.commit()
                logger.debug("최종 배치 커밋")

        except Exception as e:
            session.rollback()
            logger.error(f"배치 세션 오류: {e}")
            raise
        finally:
            session.close()
            self.scoped_session_factory.remove()

    def get_pool_status(self) -> dict[str, Any]:
        """연결 풀 상태 조회"""
        if not self.engine:
            return {"status": "not_initialized"}

        pool = self.engine.pool

        return {
            "status": "active",
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "stats": self.stats.copy(),
            "uptime_seconds": (
                datetime.now() - self.stats["last_reset"]
            ).total_seconds(),
        }

    def reset_stats(self):
        """통계 초기화"""
        self.stats = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0,
            "pool_overflows": 0,
            "last_reset": datetime.now(),
        }
        logger.info("📊 연결 풀 통계 초기화")

    def close_all_connections(self):
        """모든 연결 종료"""
        if self.engine:
            self.engine.dispose()
            logger.info("🔚 모든 DB 연결 종료")

    def health_check(self) -> bool:
        """헬스체크"""
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"DB 헬스체크 실패: {e}")
            return False


# 전역 연결 풀 인스턴스
_db_pool = None


def get_database_pool(config: dict[str, Any] = None) -> DatabaseConnectionPool:
    """데이터베이스 연결 풀 인스턴스 반환"""
    global _db_pool
    if _db_pool is None:
        _db_pool = DatabaseConnectionPool(config)
    return _db_pool


def initialize_database_pool(database_url: str, config: dict[str, Any] = None):
    """데이터베이스 연결 풀 초기화"""
    pool = get_database_pool(config)
    pool.initialize_pool(database_url)
    return pool
