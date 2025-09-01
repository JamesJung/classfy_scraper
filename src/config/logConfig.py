import datetime
import json
import logging
import re
import threading
from enum import Enum
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

# 전역 로깅 초기화 상태 추적 (스레드 안전)
_logging_initialized = False
_logging_lock = threading.Lock()


# 표준화된 로그 레벨 정의
class LogLevel(Enum):
    """표준화된 로그 레벨"""

    TRACE = 5  # 매우 상세한 디버깅
    DEBUG = 10  # 디버깅 정보
    INFO = 20  # 일반 정보
    WARNING = 30  # 경고
    ERROR = 40  # 에러
    CRITICAL = 50  # 치명적 에러
    SECURITY = 60  # 보안 이벤트 (커스텀 레벨)


# 보안 이벤트 타입 정의
class SecurityEventType(Enum):
    """보안 이벤트 타입"""

    AUTHENTICATION_FAILURE = "AUTH_FAIL"
    AUTHORIZATION_FAILURE = "AUTHZ_FAIL"
    DATA_ACCESS_VIOLATION = "DATA_VIOLATION"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS"
    SECURITY_SCAN_DETECTED = "SCAN_DETECTED"
    MALICIOUS_INPUT = "MALICIOUS_INPUT"
    PRIVILEGE_ESCALATION = "PRIVILEGE_ESC"
    DATA_BREACH = "DATA_BREACH"
    SYSTEM_COMPROMISE = "SYSTEM_COMPROMISE"
    CONFIGURATION_CHANGE = "CONFIG_CHANGE"


# 커스텀 로그 레벨 추가
logging.addLevelName(LogLevel.TRACE.value, "TRACE")
logging.addLevelName(LogLevel.SECURITY.value, "SECURITY")


# 로그 메시지 형식
class LogMessageFormat:
    # 시스템 관련
    SYSTEM_PREFIX = "[시스템]"

    # 파일 처리 관련
    FILE_PROCESSING_START = "{} 파일 처리 시작"
    FILE_PROCESSING_SUCCESS = "{} 처리 성공"
    FILE_PROCESSING_FAILED = "{} 처리 실패"
    FILE_PROCESSING_ERROR = "{} 처리 중 오류 발생: {}"

    # JSON 생성 관련
    JSON_GENERATION_SUCCESS = "{} JSON 파일 생성 완료: {}"
    JSON_GENERATION_ERROR = "{} JSON 파일 생성 중 오류 발생: {}"

    # 필드 검증 관련
    REQUIRED_FIELD_MISSING = "{} 필수 필드 누락 또는 비어있음: {}"
    FIELD_TYPE_ERROR = "{} 필드 타입 오류 - {}: 문자열이어야 하나 {} 타입임"
    OPTIONAL_FIELD_MISSING = "{} 선택적 필드 '{}' 누락 - 빈 문자열로 설정"

    # 데이터 형식 검증 관련
    DATE_FORMAT_ERROR = "{} 날짜 형식 오류 - {}: {}"
    EMAIL_FORMAT_ERROR = "{} 이메일 형식 오류: {}"
    PHONE_FORMAT_ERROR = "{} 전화번호 형식 오류: {}"

    # 처리 결과 보고서
    REPORT_HEADER = "=" * 50
    REPORT_TITLE = "{} 처리 결과 보고서"
    REPORT_TOTAL_FILES = "전체 파일 수: {}"
    REPORT_SUCCESS_COUNT = "성공: {}"
    REPORT_FAILED_COUNT = "실패: {}"
    REPORT_FAILED_FILES_HEADER = "\n실패한 파일 목록:"
    REPORT_SUCCESS_RATE = "\n성공률: {:.1f}%"

    # DB 처리 관련
    DB_SAVE_FAILED = "{} 데이터베이스 저장 실패: {}"
    DB_SAVE_SUCCESS = "{} 데이터베이스 저장 성공: {}"
    DB_SAVE_ERROR = "{} 데이터베이스 저장 중 오류 발생: {}"
    DB_SAVE_START = "{} 데이터베이스 저장 시작"
    DB_SAVE_END = "{} 데이터베이스 저장 완료"


# 로그 파일 경로 설정 - 날짜별 저장을 위한 디렉토리 구조
# classfy_scraper 프로젝트 루트의 logs 폴더 사용
project_root = Path(__file__).parent.parent.parent  # src/config에서 프로젝트 루트로
log_dir = project_root / "logs"
# WSL 환경에서 logs 디렉토리 생성 이슈 해결


def ensure_log_directory():
    """로그 디렉토리가 존재하는지 확인하고 없으면 생성"""
    global log_dir
    try:
        # 1. 절대 경로로 변환
        log_dir = log_dir.resolve()

        # 2. 부모 디렉토리부터 차례로 생성
        log_dir.parent.mkdir(parents=True, exist_ok=True)

        # 3. 로그 디렉토리가 파일로 존재하는 경우 삭제
        if log_dir.exists() and not log_dir.is_dir():
            try:
                log_dir.unlink()  # 파일 삭제
            except (OSError, PermissionError):
                log_dir = Path.cwd() / "temp_logs"  # 임시 디렉토리 사용

        # 4. 디렉토리 생성
        log_dir.mkdir(mode=0o755, parents=True, exist_ok=True)

        # 5. 기본 로그 파일들 생성
        for log_file in [
            "app.log",
            "app_error.log",
            "sql_queries.log",
            "security_events.log",
        ]:
            log_path = log_dir / log_file
            if not log_path.exists():
                log_path.touch(mode=0o666)

    except Exception:
        # 최후의 수단: 임시 디렉토리 사용
        import tempfile

        temp_dir = Path(tempfile.gettempdir()) / "grant_info_logs"
        temp_dir.mkdir(parents=True, exist_ok=True)
        log_dir = temp_dir

        # 기본 로그 파일들 생성
        for log_file in [
            "app.log",
            "app_error.log",
            "sql_queries.log",
            "security_events.log",
        ]:
            (log_dir / log_file).touch(exist_ok=True)


# 로그 디렉토리 확실하게 생성
ensure_log_directory()


# 날짜별 로그 파일명 생성 함수
def get_date_log_filename(prefix: str) -> str:
    """날짜별 로그 파일명 생성"""
    today = datetime.datetime.now().strftime("%Y%m%d")
    return str(log_dir / f"{prefix}_{today}.log")


# 현재 날짜 기준 로그 파일명
log_file = get_date_log_filename("app")
error_log_file = get_date_log_filename("app_error")

# 로그 포맷 설정 (파일명과 라인 번호 추가)
LOG_FORMAT = (
    "%(asctime)s - %(name)s - [%(filename)s:%(lineno)d] - %(levelname)s - %(message)s"
)


def setup_logging(
    name: str | None = None, level: int = logging.INFO
) -> logging.Logger:
    """애플리케이션 전체의 로깅 설정 - 날짜별 로그 파일 저장 (충돌 방지 강화)

    Args:
        name: 로거 이름 (None인 경우 호출한 모듈의 이름 사용)
        level: 로깅 레벨 (기본값: INFO)

    Returns:
        설정된 로거 인스턴스
    """
    global _logging_initialized
    
    # 🔒 전역 로깅 초기화 (한 번만 실행)
    with _logging_lock:
        if not _logging_initialized:
            # basicConfig 차단 및 루트 로거 정리
            _secure_logging_initialization()
            _logging_initialized = True
    
    # 로그 디렉토리 재확인
    ensure_log_directory()

    # 애플리케이션 로거 설정 (이미 설정된 로거는 반환)
    logger = logging.getLogger(name if name else __name__)
    
    # 🔒 강화된 중복 방지: 핸들러 존재 확인 + 핸들러 초기화 추적
    if hasattr(logger, '_handlers_initialized') and logger._handlers_initialized:
        return logger
    
    # 기존 핸들러 제거 (확실한 초기화)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    logger.setLevel(level)
    
    try:
        # 날짜별 일반 로그 파일 핸들러 (매일 자정에 새 파일 생성)
        app_handler = TimedRotatingFileHandler(
            filename=str(log_dir / "app.log"),
            when="midnight",  # 매일 자정에 로테이션
            interval=1,  # 1일마다
            backupCount=30,  # 30일간 보관
            encoding="utf-8",
        )
        app_handler.suffix = "%Y%m%d"
    except (OSError, PermissionError) as e:
        # 파일 핸들러 생성 실패 시 콘솔만 사용
        app_handler = logging.StreamHandler()
        print(f"Warning: 로그 파일 생성 실패, 콘솔 출력만 사용: {e}")
    app_handler.setLevel(level)
    app_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(app_handler)

    # 날짜별 에러 로그 파일 핸들러 (ERROR 레벨 이상만)
    try:
        error_handler = TimedRotatingFileHandler(
            filename=str(log_dir / "app_error.log"),
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        error_handler.suffix = "%Y%m%d"
    except (OSError, PermissionError):
        # 에러 핸들러 생성 실패 시 스트림 핸들러 사용
        error_handler = logging.StreamHandler()
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(error_handler)

    # propagate를 False로 설정하여 상위 로거로 전파 방지 (중복 출력 방지)
    logger.propagate = False

    # 🔒 핸들러 초기화 완료 표시 (중복 방지용)
    logger._handlers_initialized = True

    # hwp5 라이브러리의 로깅 레벨 설정 (ERROR 이상만 표시)
    hwp_loggers = [
        logging.getLogger("hwp5"),
        logging.getLogger("hwp5.bintype"),
        logging.getLogger("hwp5.filestructure"),
        logging.getLogger("hwp5.recordstream"),
        logging.getLogger("hwp5.xmlmodel"),
        logging.getLogger("hwp5.dataio"),
    ]
    for hwp_logger in hwp_loggers:
        hwp_logger.setLevel(logging.ERROR)
        hwp_logger.propagate = False

    # unstructured 라이브러리의 로깅 레벨 설정 (ERROR 이상만 표시)
    unstructured_logger = logging.getLogger("unstructured")
    unstructured_logger.setLevel(logging.ERROR)
    unstructured_logger.propagate = False

    # SQLAlchemy 로거 설정 (중복 방지 강화)
    sql_logger = logging.getLogger("sqlalchemy.engine.Engine")
    if not hasattr(sql_logger, '_handlers_initialized') or not sql_logger._handlers_initialized:
        sql_logger.setLevel(level)
        sql_formatter = SQLAlchemySQLFormatter()

        # SQL 전용 날짜별 핸들러
        try:
            sql_handler = TimedRotatingFileHandler(
                filename=str(log_dir / "sql_queries.log"),
                when="midnight",
                interval=1,
                backupCount=30,
                encoding="utf-8",
            )
            sql_handler.suffix = "%Y%m%d"
        except (OSError, PermissionError):
            sql_handler = logging.StreamHandler()

        sql_handler.setFormatter(sql_formatter)
        sql_logger.addHandler(sql_handler)
        sql_logger.propagate = False
        sql_logger._handlers_initialized = True

    # 보안 이벤트 전용 로거 설정 (중복 방지 강화)
    security_logger = logging.getLogger("security")
    if not hasattr(security_logger, '_handlers_initialized') or not security_logger._handlers_initialized:
        security_logger.setLevel(LogLevel.SECURITY.value)

        # 보안 이벤트 전용 핸들러
        try:
            security_handler = TimedRotatingFileHandler(
                filename=str(log_dir / "security_events.log"),
                when="midnight",
                interval=1,
                backupCount=90,  # 보안 로그는 더 오래 보관
                encoding="utf-8",
            )
            security_handler.suffix = "%Y%m%d"
        except (OSError, PermissionError):
            security_handler = logging.StreamHandler()

        security_formatter = SecurityEventFormatter()
        security_handler.setFormatter(security_formatter)
        security_logger.addHandler(security_handler)

        # 보안 이벤트는 별도 콘솔에도 출력
        security_console = logging.StreamHandler()
        security_console.setLevel(LogLevel.SECURITY.value)
        security_console.setFormatter(SecurityEventFormatter())
        security_logger.addHandler(security_console)
        security_logger.propagate = False
        security_logger._handlers_initialized = True

    # 🔒 루트 로거 중복 방지 및 전파 차단 강화
    root_logger = logging.getLogger()
    if not hasattr(root_logger, '_root_configured') or not root_logger._root_configured:
        # 루트 로거의 핸들러도 정리
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger._root_configured = True

    return logger


def _secure_logging_initialization():
    """로깅 충돌 방지를 위한 보안 초기화 (내부 함수)"""
    try:
        # 1. 루트 로거 완전 정리
        root_logger = logging.getLogger()
        
        # 기존 핸들러 모두 제거
        for handler in root_logger.handlers[:]:
            try:
                handler.close()
            except Exception:
                pass
            root_logger.removeHandler(handler)
        
        # 2. 루트 로거 레벨 설정 (WARNING 이상만 허용)
        root_logger.setLevel(logging.WARNING)
        
        # 3. basicConfig 호출 방지를 위한 더미 핸들러 추가
        # (이렇게 하면 다른 모듈에서 basicConfig를 호출해도 무시됨)
        dummy_handler = logging.NullHandler()
        root_logger.addHandler(dummy_handler)
        
        # 4. 문제가 되는 외부 라이브러리 로거들 사전 설정
        problematic_loggers = [
            'hwp5', 'hwp5.bintype', 'hwp5.filestructure', 'hwp5.recordstream',
            'hwp5.xmlmodel', 'hwp5.dataio', 'hwp5.importhelper',
            'unstructured', 'unstructured.partition',
            'urllib3', 'urllib3.connectionpool', 'requests', 'requests.packages.urllib3',
            'matplotlib', 'PIL', 'transformers', 'torch',
            'mysql', 'mysql.connector', 'mysql.connector.pooling', 
            'mysql.connector.network', 'mysql.connector.cursor',
            'pymysql', 'pymysql.cursors', 'pymysql.connections'
        ]
        
        for logger_name in problematic_loggers:
            ext_logger = logging.getLogger(logger_name)
            ext_logger.setLevel(logging.ERROR)
            ext_logger.propagate = False
            # 기존 핸들러 제거
            for handler in ext_logger.handlers[:]:
                ext_logger.removeHandler(handler)
            # NullHandler 추가하여 로그 차단
            ext_logger.addHandler(logging.NullHandler())
        
        # 5. Python warnings 모듈 필터링 (hwp5 pkg_resources 경고 차단)
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning, module="hwp5.importhelper")
        warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")
        
        # 5. logging 모듈의 _handlers_lock 확인 (가능한 경우)
        # Python의 내부 로킹 메커니즘과 충돌 방지
        
    except Exception as e:
        # 초기화 실패해도 계속 진행 (로깅 초기화는 중단되지 않아야 함)
        pass


def prevent_basicconfig_conflicts():
    """basicConfig 충돌 방지를 위한 추가 보안 조치"""
    # logging 모듈의 basicConfig를 안전한 버전으로 오버라이드
    original_basic_config = logging.basicConfig
    
    def safe_basic_config(*args, **kwargs):
        """안전한 basicConfig - 이미 초기화된 경우 무시"""
        if _logging_initialized:
            # 이미 우리의 로깅 시스템이 초기화되었으면 무시
            pass
        else:
            # 초기화되지 않은 경우에만 원본 호출
            original_basic_config(*args, **kwargs)
    
    # 원본 함수를 안전한 버전으로 교체
    logging.basicConfig = safe_basic_config


# 모듈 import 시점에 보안 조치 적용
prevent_basicconfig_conflicts()


class SQLAlchemySQLFormatter(logging.Formatter):
    """SQL 쿼리 로그 포맷터

    쿼리 실행 정보를 상세하게 포맷팅합니다:
    - 쿼리 종류 (SELECT/INSERT/UPDATE/DELETE)
    - 실제 실행되는 SQL문
    - 바인딩된 파라미터
    - 실행 시간
    """

    # SQL 키워드 목록 (대문자로 변환할 키워드)
    SQL_KEYWORDS = [
        "SELECT",
        "FROM",
        "WHERE",
        "INSERT",
        "INTO",
        "VALUES",
        "UPDATE",
        "SET",
        "DELETE",
        "JOIN",
        "LEFT",
        "RIGHT",
        "INNER",
        "OUTER",
        "FULL",
        "GROUP",
        "ORDER",
        "BY",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "UNION",
        "ALL",
        "INTERSECT",
        "EXCEPT",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "AND",
        "OR",
        "NOT",
        "EXISTS",
        "IN",
        "LIKE",
        "BETWEEN",
        "IS",
        "NULL",
        "ON",
        "AS",
        "DISTINCT",
        "CREATE",
        "TABLE",
        "ALTER",
        "DROP",
        "INDEX",
        "VIEW",
        "TRIGGER",
        "FUNCTION",
        "PROCEDURE",
        "UNIQUE",
        "PRIMARY",
        "KEY",
        "FOREIGN",
        "REFERENCES",
        "CONSTRAINT",
    ]

    def format(self, record):
        try:
            # 기본 메시지 가져오기
            message = record.getMessage()

            # 쿼리 종류 확인
            query_type = "QUERY"
            upper_message = message.upper()
            if "SELECT" in upper_message:
                query_type = "SELECT"
            elif "INSERT" in upper_message:
                query_type = "INSERT"
            elif "UPDATE" in upper_message:
                query_type = "UPDATE"
            elif "DELETE" in upper_message:
                query_type = "DELETE"

            # 타임스탬프 포맷팅
            timestamp = self.formatTime(record)

            # 향상된 SQL 포맷팅 적용
            formatted_sql = self.format_sql(message)

            # 최종 포맷팅
            output = (
                f"\n{'='*80}\n"
                f"[{timestamp}] {query_type} 쿼리 실행\n"
                f"{'-'*80}\n"
                f"SQL문:\n"
                f"{formatted_sql}\n"
                f"{'='*80}"
            )

            return output

        except Exception as e:
            return f"로그 포맷팅 중 오류 발생: {str(e)}\n원본 메시지: {record.getMessage()}"

    def format_sql(self, sql):
        """향상된 SQL 포맷팅 함수 (sqlparse 없이 구현)

        모든 SQL 타입(SELECT, INSERT, UPDATE, DELETE)에 대해 일관된 포맷팅 제공
        """
        # 기본 정리
        sql = sql.strip()

        # 시작 쿼리 타입 확인
        sql_type = self._get_sql_type(sql)

        # 키워드 대문자화
        sql = self._capitalize_keywords(sql)

        # 쿼리 타입별 처리
        if sql_type == "SELECT":
            sql = self._format_select_query(sql)
        elif sql_type == "INSERT":
            sql = self._format_insert_query(sql)
        elif sql_type == "UPDATE":
            sql = self._format_update_query(sql)
        elif sql_type == "DELETE":
            sql = self._format_delete_query(sql)

        # 괄호 내용 포맷팅
        sql = self._format_parentheses_content(sql)

        # AND/OR 조건 들여쓰기
        sql = re.sub(r"(?i)(\s)AND\s+", r"\1AND\n        ", sql)
        sql = re.sub(r"(?i)(\s)OR\s+", r"\1OR\n        ", sql)

        return sql

    def _get_sql_type(self, sql):
        """SQL 쿼리 타입 확인"""
        sql_upper = sql.upper().strip()
        if sql_upper.startswith("SELECT"):
            return "SELECT"
        elif sql_upper.startswith("INSERT"):
            return "INSERT"
        elif sql_upper.startswith("UPDATE"):
            return "UPDATE"
        elif sql_upper.startswith("DELETE"):
            return "DELETE"
        return "UNKNOWN"

    def _capitalize_keywords(self, sql):
        """SQL 키워드를 대문자로 변환"""
        # 모든 단어 기준으로 키워드 확인
        re.findall(r"\b\w+\b", sql)

        # 키워드만 대문자로 변환 (중복 처리 방지를 위해 큰 문자열부터 처리)
        for keyword in sorted(self.SQL_KEYWORDS, key=len, reverse=True):
            pattern = re.compile(r"\b" + keyword + r"\b", re.IGNORECASE)
            sql = pattern.sub(keyword, sql)

        return sql

    def _format_select_query(self, sql):
        """SELECT 쿼리 포맷팅"""
        # 주요 절 앞에 줄바꿈 추가
        for clause in ["FROM", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT"]:
            pattern = re.compile(r"\b" + clause + r"\b", re.IGNORECASE)
            sql = pattern.sub(f"\n{clause}", sql)

        # JOIN 절 앞에 줄바꿈 추가
        for join_type in [
            "JOIN",
            "LEFT JOIN",
            "RIGHT JOIN",
            "INNER JOIN",
            "OUTER JOIN",
        ]:
            pattern = re.compile(r"\b" + join_type + r"\b", re.IGNORECASE)
            sql = pattern.sub(f"\n{join_type}", sql)

        # SELECT 다음에 컬럼 들여쓰기
        sql = re.sub(r"(?i)SELECT\s+", "SELECT\n    ", sql)

        # 쉼표로 구분된 컬럼 줄바꿈 처리
        def replace_columns(match):
            columns = match.group(1).split(",")
            formatted = ",\n    ".join([col.strip() for col in columns])
            return f"\n    {formatted}"

        # SELECT 절의 컬럼 처리 (FROM 앞까지)
        select_pattern = r"(?i)SELECT\n\s+(.*?)(?=\nFROM)"
        sql = re.sub(
            select_pattern,
            lambda m: f"SELECT{replace_columns(m)}",
            sql,
            flags=re.DOTALL,
        )

        return sql

    def _format_insert_query(self, sql):
        """INSERT 쿼리 포맷팅"""
        # INSERT INTO와 VALUES 사이에 들여쓰기 추가
        sql = re.sub(
            r"(?i)(INSERT\s+INTO\s+\w+)\s*(\(.*?\))\s*VALUES",
            r"\1\n\2\nVALUES",
            sql,
            flags=re.DOTALL,
        )

        return sql

    def _format_update_query(self, sql):
        """UPDATE 쿼리 포맷팅"""
        # SET과 WHERE 앞에 줄바꿈 추가
        sql = re.sub(r"(?i)\b(SET|WHERE)\b", r"\n\1", sql)

        return sql

    def _format_delete_query(self, sql):
        """DELETE 쿼리 포맷팅"""
        # FROM과 WHERE 앞에 줄바꿈 추가
        sql = re.sub(r"(?i)\b(FROM|WHERE)\b", r"\n\1", sql)

        return sql

    def _format_parentheses_content(self, sql):
        """괄호 내용 들여쓰기 개선"""

        # 괄호 안의 쉼표로 구분된 목록 처리
        def replace_paren_content(match):
            # 괄호 내용
            content = match.group(1)

            # 괄호 안이 비어있거나 단일 항목인 경우 원래대로 반환
            if not content.strip() or "," not in content:
                return f"({content})"

            # 쉼표로 구분된 내용 들여쓰기
            items = [item.strip() for item in content.split(",")]
            formatted = "\n        " + ",\n        ".join(items)
            return f"(\n{formatted}\n    )"

        # 괄호 내용 처리 (중첩 괄호 처리는 복잡해서 단순한 정규식 사용)
        sql = re.sub(r"\(\s*([^)(]+?)\s*\)", replace_paren_content, sql)

        return sql


class SecurityEventFormatter(logging.Formatter):
    """보안 이벤트 전용 포맷터

    보안 이벤트를 JSON 형태로 구조화하여 로깅합니다.
    SIEM(Security Information and Event Management) 시스템과의 연동을 고려한 형태입니다.
    """

    def format(self, record):
        try:
            # 타임스탬프
            timestamp = self.formatTime(record)

            # 보안 이벤트 데이터 파싱
            event_data = self._parse_security_event(record.getMessage())

            # 표준 보안 이벤트 형식
            security_event = {
                "timestamp": timestamp,
                "level": record.levelname,
                "event_type": event_data.get("event_type", "UNKNOWN"),
                "severity": self._get_severity(event_data.get("event_type")),
                "source": {
                    "module": record.name,
                    "filename": record.filename,
                    "lineno": record.lineno,
                    "function": getattr(record, "funcName", "unknown"),
                },
                "event_details": event_data.get("details", {}),
                "user_id": event_data.get("user_id"),
                "session_id": event_data.get("session_id"),
                "ip_address": event_data.get("ip_address"),
                "user_agent": event_data.get("user_agent"),
                "action": event_data.get("action"),
                "resource": event_data.get("resource"),
                "outcome": event_data.get("outcome", "UNKNOWN"),
                "risk_score": self._calculate_risk_score(event_data),
            }

            # JSON 형태로 출력 (한 줄로 압축하여 파싱 용이)
            return json.dumps(security_event, ensure_ascii=False, separators=(",", ":"))

        except Exception as e:
            # 포맷팅 실패 시 기본 형태로 출력
            return f"SECURITY_EVENT_FORMAT_ERROR: {str(e)} | ORIGINAL: {record.getMessage()}"

    def _parse_security_event(self, message: str) -> dict[str, Any]:
        """보안 이벤트 메시지에서 구조화된 데이터 추출"""
        try:
            # "SECURITY_EVENT: {json_data}" 형태로 전달된 경우 파싱
            if message.startswith("SECURITY_EVENT: "):
                json_part = message[16:]  # "SECURITY_EVENT: " 제거
                return json.loads(json_part)
            else:
                # 기본 형태로 파싱
                return {"details": {"message": message}}
        except (json.JSONDecodeError, Exception):
            return {"details": {"message": message, "parse_error": True}}

    def _get_severity(self, event_type: str) -> str:
        """이벤트 타입별 심각도 결정"""
        high_severity = {"DATA_BREACH", "SYSTEM_COMPROMISE", "PRIVILEGE_ESC"}
        medium_severity = {
            "AUTH_FAIL",
            "AUTHZ_FAIL",
            "DATA_VIOLATION",
            "MALICIOUS_INPUT",
        }

        if event_type in high_severity:
            return "HIGH"
        elif event_type in medium_severity:
            return "MEDIUM"
        else:
            return "LOW"

    def _calculate_risk_score(self, event_data: dict[str, Any]) -> int:
        """위험 점수 계산 (0-100)"""
        base_score = 30  # 기본 점수

        # 이벤트 타입별 가중치
        event_type = event_data.get("event_type", "")
        if "BREACH" in event_type or "COMPROMISE" in event_type:
            base_score += 50
        elif "FAIL" in event_type or "VIOLATION" in event_type:
            base_score += 30
        elif "SUSPICIOUS" in event_type:
            base_score += 20

        # 최대값 제한
        return min(base_score, 100)


# 보안 이벤트 로깅을 위한 유틸리티 함수들
def log_security_event(
    event_type: SecurityEventType,
    details: dict[str, Any] = None,
    user_id: str = None,
    session_id: str = None,
    ip_address: str = None,
    action: str = None,
    resource: str = None,
    outcome: str = "UNKNOWN",
):
    """
    보안 이벤트 로깅 유틸리티 함수

    Args:
        event_type: 보안 이벤트 타입
        details: 상세 정보
        user_id: 사용자 ID
        session_id: 세션 ID
        ip_address: IP 주소
        action: 수행 동작
        resource: 대상 리소스
        outcome: 결과 (SUCCESS/FAILURE/UNKNOWN)
    """
    security_logger = logging.getLogger("security")

    event_data = {
        "event_type": event_type.value,
        "details": details or {},
        "user_id": user_id,
        "session_id": session_id,
        "ip_address": ip_address,
        "action": action,
        "resource": resource,
        "outcome": outcome,
    }

    # JSON 형태로 직렬화하여 로깅
    message = f"SECURITY_EVENT: {json.dumps(event_data, ensure_ascii=False)}"
    security_logger.log(LogLevel.SECURITY.value, message)


def trace(logger: logging.Logger, message: str):
    """TRACE 레벨 로깅"""
    logger.log(LogLevel.TRACE.value, message)


def get_standardized_logger(
    name: str, level: LogLevel = LogLevel.INFO
) -> logging.Logger:
    """
    표준화된 로거 생성

    Args:
        name: 로거 이름
        level: 로그 레벨

    Returns:
        표준화된 로거 인스턴스
    """
    logger = setup_logging(name, level.value)

    # 커스텀 메서드 추가
    def log_trace(message: str):
        logger.log(LogLevel.TRACE.value, message)

    def log_security(
        event_type: SecurityEventType, details: dict[str, Any] = None, **kwargs
    ):
        log_security_event(event_type, details, **kwargs)

    # 로거에 커스텀 메서드 추가
    logger.trace = log_trace
    logger.security = log_security

    return logger
