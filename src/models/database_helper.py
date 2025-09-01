from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from src.config.logConfig import setup_logging

from .database import SessionLocal

logger = setup_logging(__name__)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    DB 세션을 안전하게 관리하는 컨텍스트 매니저

    Yields:
        Session: SQLAlchemy 세션 객체
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"데이터베이스 세션 오류: {str(e)}")
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    DB 세션을 반환하는 제너레이터 (기존 호환성 유지)

    Yields:
        Session: SQLAlchemy 세션 객체
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
