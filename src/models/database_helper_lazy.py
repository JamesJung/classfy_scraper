"""
지연 로딩 데이터베이스 헬퍼 모듈
Lazy Loading Database Helper Module

데이터베이스 세션 관리를 지연 로딩으로 처리합니다.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.config.logConfig import setup_logging
from src.models.database_lazy import get_lazy_session_local

# 로깅 설정
logger = setup_logging(__name__)


@contextmanager
def get_lazy_db_session() -> Generator[Session, None, None]:
    """
    지연 로딩 데이터베이스 세션을 제공하는 컨텍스트 매니저

    Yields:
        SQLAlchemy Session 객체

    Raises:
        SQLAlchemyError: 데이터베이스 관련 오류 발생시
    """
    # 실제 사용 시점에 세션 생성
    session_local = get_lazy_session_local()
    session = session_local()

    try:
        logger.debug("데이터베이스 세션 생성")
        yield session
        session.commit()
        logger.debug("데이터베이스 세션 커밋 완료")

    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"데이터베이스 세션 오류: {e}")
        raise

    except Exception as e:
        session.rollback()
        logger.error(f"예상치 못한 데이터베이스 오류: {e}")
        raise

    finally:
        session.close()
        logger.debug("데이터베이스 세션 종료")


def test_lazy_database_connection() -> bool:
    """
    지연 로딩 데이터베이스 연결 테스트

    Returns:
        연결 성공 여부
    """
    try:
        with get_lazy_db_session() as session:
            result = session.execute(text("SELECT 1")).scalar()
            return result == 1
    except Exception as e:
        logger.error(f"데이터베이스 연결 테스트 실패: {e}")
        return False
