#!/usr/bin/env python3
import os
import sys
import subprocess
import time
import pymysql
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import argparse

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# 이메일 설정
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ALERT_RECIPIENTS = os.getenv("ALERT_RECIPIENTS", "").split(",")
ALERT_SENDER_NAME = os.getenv("ALERT_SENDER_NAME", "Scraper Alert System")
ALERT_ENABLED = os.getenv("ALERT_ENABLED", "true").lower() == "true"

NODE_DIR = Path(__file__).parent / "node"
SCRAPER_DIR = NODE_DIR / "scraper"
BASE_OUTPUT_DIR = Path(__file__).parent / "scraped_incremental_v2"


def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def save_scraper_log(
    site_code,
    status,
    elapsed_time=0,
    error_message=None,
    scraper_file=None,
    from_date=None,
    output_dir=None,
    scraped_count=0,
):
    """스크래퍼 실행 로그를 DB에 저장"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 테이블이 없으면 생성
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scraper_execution_log (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    site_code VARCHAR(50) NOT NULL,
                    execution_date DATE NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    error_message TEXT,
                    elapsed_time FLOAT,
                    scraper_file VARCHAR(255),
                    from_date DATE,
                    to_date DATE,
                    output_dir VARCHAR(500),
                    scraped_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_site_code (site_code),
                    INDEX idx_execution_date (execution_date),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
            )

            # 로그 저장
            cursor.execute(
                """
                INSERT INTO scraper_execution_log 
                (site_code, execution_date, status, error_message, elapsed_time, 
                 scraper_file, from_date, to_date, output_dir, scraped_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    site_code,
                    datetime.now().date(),
                    status,
                    error_message,
                    elapsed_time,
                    scraper_file,
                    from_date,
                    datetime.now().date(),
                    output_dir,
                    scraped_count,
                ),
            )

            log_id = cursor.lastrowid
            conn.commit()
            return log_id
    except Exception as e:
        print(f"로그 저장 실패: {e}")
        return None
    finally:
        conn.close()


def save_alert_history(log_id, site_code, alert_type, alert_message, recipients):
    """알림 발송 기록을 DB에 저장"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 테이블이 없으면 생성
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scraper_alert_history (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    log_id INT,
                    site_code VARCHAR(50) NOT NULL,
                    alert_type VARCHAR(20) NOT NULL,
                    alert_message TEXT,
                    recipients TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_site_code (site_code),
                    INDEX idx_alert_type (alert_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
            )

            cursor.execute(
                """
                INSERT INTO scraper_alert_history 
                (log_id, site_code, alert_type, alert_message, recipients)
                VALUES (%s, %s, %s, %s, %s)
            """,
                (log_id, site_code, alert_type, alert_message, json.dumps(recipients)),
            )
            conn.commit()
    except Exception as e:
        print(f"알림 기록 저장 실패: {e}")
    finally:
        conn.close()


def send_summary_email(results, total_elapsed):
    """실행 완료 후 문제가 있었던 사이트들에 대한 종합 보고서 이메일 발송"""
    if not ALERT_ENABLED or not SMTP_USER or not SMTP_PASSWORD:
        return False

    if not ALERT_RECIPIENTS or ALERT_RECIPIENTS == [""]:
        return False

    try:
        # 문제가 있었던 사이트들 정리
        problems = []

        for item in results.get("timeout", []):
            problems.append(
                {
                    "site": item["site_code"],
                    "status": "TIMEOUT",
                    "error": item.get("error", "15분 타임아웃 초과"),
                    "time": item.get("elapsed_time", 0),
                }
            )

        for item in results.get("error", []):
            problems.append(
                {
                    "site": item["site_code"],
                    "status": "ERROR",
                    "error": item.get("error", "알 수 없는 오류"),
                    "time": item.get("elapsed_time", 0),
                }
            )

        for item in results.get("failed", []):
            problems.append(
                {
                    "site": item["site_code"],
                    "status": "FAILED",
                    "error": item.get("error", "실행 실패"),
                    "time": item.get("elapsed_time", 0),
                }
            )

        if not problems:
            return False

        # HTML 테이블 생성
        problem_rows = ""
        for p in problems:
            problem_rows += f"""
            <tr>
                <td>{p['site']}</td>
                <td style="color: {'red' if p['status'] == 'TIMEOUT' else 'orange'};">{p['status']}</td>
                <td>{p['error'][:100]}...</td>
                <td>{p['time']:.1f}초</td>
            </tr>
            """

        subject = f"[스크래퍼 일일 보고서] {datetime.now().strftime('%Y-%m-%d')} - 문제 발생 {len(problems)}건"

        html_body = f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .summary-box {{
                        background-color: #f0f0f0;
                        padding: 15px;
                        margin: 10px 0;
                        border-radius: 5px;
                    }}
                    .problem-table {{
                        border-collapse: collapse;
                        width: 100%;
                        margin-top: 20px;
                    }}
                    .problem-table th {{
                        background-color: #333;
                        color: white;
                        padding: 10px;
                        text-align: left;
                    }}
                    .problem-table td {{
                        padding: 8px;
                        border-bottom: 1px solid #ddd;
                    }}
                    .stats-grid {{
                        display: grid;
                        grid-template-columns: repeat(3, 1fr);
                        gap: 10px;
                        margin: 20px 0;
                    }}
                    .stat-card {{
                        background: white;
                        border: 1px solid #ddd;
                        padding: 10px;
                        text-align: center;
                        border-radius: 5px;
                    }}
                    .stat-number {{
                        font-size: 24px;
                        font-weight: bold;
                        color: #333;
                    }}
                    .stat-label {{
                        color: #666;
                        font-size: 12px;
                        margin-top: 5px;
                    }}
                </style>
            </head>
            <body>
                <h2>📊 스크래퍼 일일 실행 보고서</h2>
                
                <div class="summary-box">
                    <h3>실행 요약</h3>
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-number">{len(results.get('success', []))}</div>
                            <div class="stat-label">성공</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number" style="color: orange;">{len(results.get('failed', []))}</div>
                            <div class="stat-label">실패</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number" style="color: red;">{len(results.get('timeout', []))}</div>
                            <div class="stat-label">타임아웃</div>
                        </div>
                    </div>
                    <p>
                        <strong>실행 시간:</strong> {total_elapsed:.1f}초 ({total_elapsed/60:.1f}분)<br>
                        <strong>완료 시각:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    </p>
                </div>
                
                <h3>⚠️ 문제 발생 사이트 ({len(problems)}건)</h3>
                <table class="problem-table">
                    <thead>
                        <tr>
                            <th>사이트 코드</th>
                            <th>상태</th>
                            <th>오류 메시지</th>
                            <th>실행 시간</th>
                        </tr>
                    </thead>
                    <tbody>
                        {problem_rows}
                    </tbody>
                </table>
                
                <p style="margin-top: 30px; color: #666; font-size: 12px;">
                    이 메일은 자동으로 발송되었습니다. 문의사항은 시스템 관리자에게 연락주세요.
                </p>
            </body>
        </html>
        """

        # 이메일 객체 생성
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{ALERT_SENDER_NAME} <{SMTP_USER}>"
        msg["To"] = ", ".join(
            [email.strip() for email in ALERT_RECIPIENTS if email.strip()]
        )

        # HTML 파트 추가
        html_part = MIMEText(html_body, "html")
        msg.attach(html_part)

        # SMTP 서버 연결 및 발송
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"\n📧 일일 종합 보고서 발송 완료: {', '.join(ALERT_RECIPIENTS)}")
        return True

    except Exception as e:
        print(f"\n❌ 종합 보고서 발송 실패: {e}")
        return False


def send_alert_email(site_code, status, error_message, elapsed_time, from_date):
    """타임아웃 또는 오류 발생시 이메일 알림 발송"""
    if not ALERT_ENABLED or not SMTP_USER or not SMTP_PASSWORD:
        print("이메일 알림이 비활성화되어 있거나 설정이 없습니다.")
        return False

    if not ALERT_RECIPIENTS or ALERT_RECIPIENTS == [""]:
        print("수신자 이메일이 설정되지 않았습니다.")
        return False

    try:
        # 이메일 내용 구성
        subject = f"[스크래퍼 알림] {site_code} - {status}"

        html_body = f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .alert-box {{ 
                        border: 2px solid #ff0000;
                        padding: 15px;
                        margin: 10px 0;
                        background-color: #fff5f5;
                    }}
                    .info-table {{
                        border-collapse: collapse;
                        width: 100%;
                        margin-top: 10px;
                    }}
                    .info-table td {{
                        padding: 8px;
                        border: 1px solid #ddd;
                    }}
                    .info-table td:first-child {{
                        font-weight: bold;
                        background-color: #f2f2f2;
                        width: 30%;
                    }}
                </style>
            </head>
            <body>
                <h2>스크래퍼 실행 알림</h2>
                <div class="alert-box">
                    <h3>⚠️ {status.upper()} 발생</h3>
                    <table class="info-table">
                        <tr>
                            <td>사이트 코드</td>
                            <td>{site_code}</td>
                        </tr>
                        <tr>
                            <td>상태</td>
                            <td>{status}</td>
                        </tr>
                        <tr>
                            <td>시작 날짜</td>
                            <td>{from_date}</td>
                        </tr>
                        <tr>
                            <td>실행 시간</td>
                            <td>{elapsed_time:.1f}초</td>
                        </tr>
                        <tr>
                            <td>오류 메시지</td>
                            <td><pre>{error_message or 'N/A'}</pre></td>
                        </tr>
                        <tr>
                            <td>발생 시각</td>
                            <td>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td>
                        </tr>
                    </table>
                </div>
                <p>이 메일은 자동으로 발송되었습니다.</p>
            </body>
        </html>
        """

        # 이메일 객체 생성
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{ALERT_SENDER_NAME} <{SMTP_USER}>"
        msg["To"] = ", ".join(
            [email.strip() for email in ALERT_RECIPIENTS if email.strip()]
        )

        # HTML 파트 추가
        html_part = MIMEText(html_body, "html")
        msg.attach(html_part)

        # SMTP 서버 연결 및 발송
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"  📧 알림 이메일 발송 완료: {', '.join(ALERT_RECIPIENTS)}")
        return True

    except Exception as e:
        print(f"  ❌ 이메일 발송 실패: {e}")
        return False


def get_sites_to_scrape(site_code=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if site_code:
                # 특정 사이트만 조회
                cursor.execute(
                    """
                    SELECT 
                        site_code,
                        latest_announcement_date
                    FROM homepage_site_announcement_date
                    WHERE site_code = %s
                    """,
                    (site_code,)
                )
            else:
                # 모든 사이트 조회
                cursor.execute(
                    """
                    SELECT 
                        site_code,
                        latest_announcement_date
                    FROM homepage_site_announcement_date
                    ORDER BY site_code
                    """
                )
            return cursor.fetchall()
    finally:
        conn.close()


def get_latest_date_from_scraped_files(site_code, output_dir):
    """스크래핑된 파일에서 최신 날짜를 가져옵니다."""
    from pathlib import Path
    import re

    output_path = Path(output_dir)
    if not output_path.exists():
        return None

    # 001_로 시작하는 첫 번째 폴더 찾기
    first_dir = None
    for item_dir in sorted(output_path.iterdir()):
        if item_dir.is_dir() and item_dir.name.startswith("001_"):
            first_dir = item_dir
            break

    if not first_dir:
        # 001_로 시작하는 폴더가 없으면 첫 번째 디렉토리 사용
        dirs = [d for d in output_path.iterdir() if d.is_dir()]
        if dirs:
            first_dir = sorted(dirs)[0]
        else:
            return None

    # content.md 파일 읽기
    content_md_path = first_dir / "content.md"
    if not content_md_path.exists():
        print(f"  ⚠️ content.md 파일 없음: {first_dir.name}")
        return None

    try:
        with open(content_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 날짜 추출 패턴 (우선순위 순서)
        date_patterns = [
            r"\*\*작성일\*\*[:\s]*(.+?)(?:\n|$)",
            r"\*\*등록일\*\*[:\s]*(.+?)(?:\n|$)",
            r"\*\*공고일\*\*[:\s]*(.+?)(?:\n|$)",
            r"작성일[:\s]*(.+?)(?:\n|$)",
            r"등록일[:\s]*(.+?)(?:\n|$)",
            r"공고일[:\s]*(.+?)(?:\n|$)",
            r"날짜\s*[:\s]*(.+?)(?:\n|$)",  # 날짜: 형식 추가
            r"^\d{4}[-.년]\d{1,2}[-.월]\d{1,2}[일]?$",  # 날짜만 있는 라인
        ]

        announcement_date = None
        for pattern in date_patterns:
            date_match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if date_match:
                # 패턴에 그룹이 있는 경우
                if date_match.groups():
                    announcement_date = date_match.group(1).strip()
                else:
                    announcement_date = date_match.group(0).strip()
                break

        if announcement_date:
            print(
                f"  📄 파일에서 추출한 최신 날짜: {announcement_date} (from {first_dir.name})"
            )
            return announcement_date
        else:
            print(f"  ⚠️ 날짜 정보를 찾을 수 없음: {first_dir.name}")
            return None

    except Exception as e:
        print(f"  ❌ 파일 읽기 오류: {e}")
        return None


def update_latest_announcement_date(site_code, output_dir=None):
    """스크래핑 완료 후 해당 사이트의 최신 공고 날짜를 업데이트합니다."""

    # 스크래핑된 파일에서 최신 날짜 가져오기
    latest_date_str = None
    if output_dir:
        latest_date_str = get_latest_date_from_scraped_files(site_code, output_dir)

    if not latest_date_str:
        print(f"  ⚠️ 날짜 정보를 찾을 수 없어 DB 업데이트 스킵")
        return False

    # 날짜 형식 변환 (YYYY-MM-DD 형식으로)
    from datetime import datetime
    import re

    try:
        # 다양한 날짜 형식 처리
        date_obj = None

        # HH:MM:SS 형식 (시간만 있는 경우 - 오늘 날짜로 처리)
        if re.match(r"^\d{1,2}:\d{2}:\d{2}$", latest_date_str):
            print(f"  ⚠️ 시간만 있음 ({latest_date_str}), 오늘 날짜로 설정")
            date_obj = datetime.now()
        # YYYY-MM-DD 형식
        elif re.match(r"^\d{4}-\d{2}-\d{2}$", latest_date_str):
            date_obj = datetime.strptime(latest_date_str, "%Y-%m-%d")
        # YYYY.MM.DD 형식
        elif re.match(r"^\d{4}\.\d{2}\.\d{2}$", latest_date_str):
            date_obj = datetime.strptime(latest_date_str, "%Y.%m.%d")
        # YYYYMMDD 형식
        elif re.match(r"^\d{8}$", latest_date_str):
            date_obj = datetime.strptime(latest_date_str, "%Y%m%d")
        # YYYY년 MM월 DD일 형식 (시간 포함 가능)
        elif re.match(r"^\d{4}년\s*\d{1,2}월\s*\d{1,2}일", latest_date_str):
            # 시간 부분 제거하고 날짜만 추출
            match = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", latest_date_str)
            if match:
                year, month, day = match.groups()
                formatted_date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                date_obj = datetime.strptime(formatted_date_str, "%Y-%m-%d")
        else:
            print(f"  ⚠️ 알 수 없는 날짜 형식: {latest_date_str}")
            return False

        # YYYY-MM-DD 형식으로 변환
        formatted_date = date_obj.strftime("%Y-%m-%d")

        # DB 업데이트
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE homepage_site_announcement_date
                    SET latest_announcement_date = %s
                    WHERE site_code = %s
                """,
                    (formatted_date, site_code),
                )

                conn.commit()
                print(f"  📅 DB 업데이트 성공: {site_code} → {formatted_date}")
                return True
        finally:
            conn.close()

    except Exception as e:
        print(f"  ❌ DB 업데이트 오류: {site_code} - {e}")
        return False


def check_scraper_exists(site_code):
    scraper_path = SCRAPER_DIR / f"{site_code}_scraper.js"
    return scraper_path.exists(), scraper_path


def run_scraper(site_code, from_date):
    start_time = time.time()

    exists, scraper_path = check_scraper_exists(site_code)

    if not exists:
        return {
            "site_code": site_code,
            "status": "skipped",
            "reason": f"스크래퍼 파일 없음: {scraper_path}",
            "elapsed_time": time.time() - start_time,
        }

    target_year = from_date.year
    from_date_str = from_date.strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 스크래퍼가 내부적으로 site_code를 추가하므로, 여기서는 날짜 디렉토리까지만 생성
    base_dir_for_date = BASE_OUTPUT_DIR / today_str
    base_dir_for_date.mkdir(parents=True, exist_ok=True)

    # 실제 output_dir는 스크래퍼가 생성할 것이므로 여기서는 base_dir만 전달
    expected_output_dir = base_dir_for_date / site_code  # 예상 출력 디렉토리 (로깅용)

    # 이미 스크래핑된 파일이 있는지 확인
    if expected_output_dir.exists():
        print(f"  📁 기존 스크래핑 파일 발견: {expected_output_dir}")

        # 첫 번째 폴더의 content.md에서 날짜 확인
        latest_scraped_date = get_latest_date_from_scraped_files(
            site_code, expected_output_dir
        )

        if latest_scraped_date:
            # DB의 날짜와 비교
            db_date_str = from_date_str

            # 날짜 형식 통일하여 비교
            try:
                # 스크래핑된 날짜를 YYYY-MM-DD 형식으로 변환
                import re

                scraped_date_normalized = None

                if re.match(r"^\d{4}-\d{2}-\d{2}$", latest_scraped_date):
                    scraped_date_normalized = latest_scraped_date
                elif re.match(r"^\d{4}\.\d{2}\.\d{2}$", latest_scraped_date):
                    scraped_date_normalized = latest_scraped_date.replace(".", "-")
                elif re.match(r"^\d{8}$", latest_scraped_date):
                    scraped_date_normalized = f"{latest_scraped_date[:4]}-{latest_scraped_date[4:6]}-{latest_scraped_date[6:8]}"

                if scraped_date_normalized and scraped_date_normalized == db_date_str:
                    print(
                        f"  ⊙ 이미 최신 데이터: DB 날짜({db_date_str}) = 스크래핑 날짜({scraped_date_normalized})"
                    )
                    return {
                        "site_code": site_code,
                        "status": "skipped",
                        "reason": f"이미 최신 데이터 보유 (날짜: {db_date_str})",
                        "elapsed_time": time.time() - start_time,
                    }
                else:
                    print(
                        f"  📅 날짜 차이 발견: DB({db_date_str}) != 스크래핑({scraped_date_normalized or latest_scraped_date})"
                    )
            except Exception as e:
                print(f"  ⚠️ 날짜 비교 중 오류: {e}")
    else:
        print(f"  📂 신규 스크래핑 (출력 디렉토리 없음)")

    try:
        # 스크래퍼에 전달할 arguments (named arguments 형식)
        cmd = [
            "node",
            str(scraper_path),
            "--output",
            str(base_dir_for_date),  # 날짜 디렉토리까지만 전달
            "--date",
            from_date_str,  # 시작 날짜
            # "--site",
            # site_code,  # 사이트 코드
            # "--force",  # 기존 폴더 덮어쓰기
        ]

        print(f"\n[{site_code}] 스크래퍼 실행")
        print(f"  스크래퍼 파일: {scraper_path}")
        print(f"  시작일: {from_date_str}")
        print(f"  종료일: {today_str}")
        print(f"  기본 출력 디렉토리: {base_dir_for_date}")
        # print(f"  예상 최종 디렉토리: {expected_output_dir}")
        # print(f"  작업 디렉토리: {NODE_DIR}")
        print(f"  명령: {' '.join(cmd)}")

        # 환경변수 설정 (필요시)
        env = os.environ.copy()
        env["NODE_ENV"] = "production"

        # 실시간 출력을 위해 subprocess.Popen 사용
        process = subprocess.Popen(
            cmd,
            cwd=str(NODE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # stderr를 stdout으로 합침
            text=True,
            bufsize=1,  # 라인 버퍼링
            env=env,
        )
        
        # 실시간 로그 출력
        stdout_lines = []
        for line in iter(process.stdout.readline, ''):
            if line:
                line = line.rstrip()
                print(f"  [{site_code}] {line}")  # 실시간 출력
                stdout_lines.append(line)
        
        process.stdout.close()
        return_code = process.wait(timeout=1200)  # 최대 20분 대기
        
        # subprocess.run과 유사한 결과 객체 생성
        result = type('Result', (), {
            'returncode': return_code,
            'stdout': '\n'.join(stdout_lines),
            'stderr': ''  # stderr는 stdout으로 합쳤음
        })()

        if result.returncode == 0:
            # stdout이 없어도 성공으로 처리할 수 있도록 체크
            scraped_count = 0
            if "scraped" in result.stdout.lower():
                # stdout에서 스크래핑 개수 추출 시도
                import re

                match = re.search(
                    r"(\d+)\s*(?:items?|announcements?|공고)", result.stdout
                )
                if match:
                    scraped_count = int(match.group(1))

            elapsed_time = time.time() - start_time
            return {
                "site_code": site_code,
                "status": "success",
                "output_dir": str(expected_output_dir),
                "scraped_count": scraped_count,
                "elapsed_time": elapsed_time,
                "stdout": (
                    result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
                ),
            }
        else:
            elapsed_time = time.time() - start_time
            return {
                "site_code": site_code,
                "status": "failed",
                "returncode": result.returncode,
                "error": result.stderr if result.stderr else result.stdout,
                "elapsed_time": elapsed_time,
                "stdout": (
                    result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
                ),
            }

    except subprocess.TimeoutExpired:
        elapsed_time = time.time() - start_time
        return {
            "site_code": site_code,
            "status": "timeout",
            "error": "15분 타임아웃 초과",
            "elapsed_time": elapsed_time,
        }
    except Exception as e:
        elapsed_time = time.time() - start_time
        return {
            "site_code": site_code,
            "status": "error",
            "error": str(e),
            "elapsed_time": elapsed_time,
        }


def retry_failed_scrapers(failed_results, from_dates_map, max_retry=2):
    """
    실패한 스크래퍼를 재시도합니다.

    Args:
        failed_results: 실패한 결과 리스트 (failed, timeout, error 상태)
        from_dates_map: {site_code: from_date} 매핑
        max_retry: 최대 재시도 횟수 (기본값: 2)

    Returns:
        dict: {"success": [], "failed": []} 형태의 재시도 결과
    """
    if not failed_results:
        return {"success": [], "failed": []}

    print("\n" + "=" * 80)
    print("실패한 스크래퍼 재시도 시작")
    print(f"대상: {len(failed_results)}개")
    print("=" * 80)

    retry_results = {"success": [], "failed": []}

    for idx, failed_item in enumerate(failed_results, 1):
        site_code = failed_item["site_code"]
        from_date = from_dates_map.get(site_code)

        if not from_date:
            print(f"\n[재시도 {idx}/{len(failed_results)}] {site_code} - from_date 없음, 스킵")
            retry_results["failed"].append(failed_item)
            continue

        print(f"\n{'='*80}")
        print(f"[재시도 {idx}/{len(failed_results)}] {site_code}")
        print(f"원래 상태: {failed_item['status']}")
        print(f"{'='*80}")

        success = False
        last_result = None

        # 최대 max_retry번 재시도
        for retry_attempt in range(1, max_retry + 1):
            # 지수 백오프: 30초, 60초
            wait_time = 30 * retry_attempt

            print(f"\n  재시도 {retry_attempt}/{max_retry} - {wait_time}초 대기 중...")
            time.sleep(wait_time)

            print(f"  재시도 {retry_attempt}/{max_retry} 실행 중...")
            result = run_scraper(site_code, from_date)
            last_result = result

            if result["status"] == "success":
                print(f"  ✓ 재시도 성공! (시도 횟수: {retry_attempt})")

                # DB에 성공 로그 저장 (재시도 성공임을 표시)
                elapsed = result.get("elapsed_time", 0)
                save_scraper_log(
                    site_code=site_code,
                    status=f"success_retry_{retry_attempt}",
                    elapsed_time=elapsed,
                    error_message=f"재시도 {retry_attempt}회 만에 성공",
                    scraper_file=f"{site_code}_scraper.js",
                    from_date=from_date,
                    output_dir=result.get("output_dir"),
                    scraped_count=result.get("scraped_count", 0),
                )

                # DB 업데이트
                update_latest_announcement_date(site_code, result["output_dir"])

                retry_results["success"].append({
                    **result,
                    "retry_attempt": retry_attempt,
                    "original_status": failed_item["status"]
                })
                success = True
                break
            else:
                print(f"  ✗ 재시도 {retry_attempt} 실패: {result['status']} - {result.get('error', 'N/A')[:100]}")

                # 재시도 실패 로그 저장
                elapsed = result.get("elapsed_time", 0)
                save_scraper_log(
                    site_code=site_code,
                    status=f"retry_{retry_attempt}_failed",
                    elapsed_time=elapsed,
                    error_message=result.get("error"),
                    scraper_file=f"{site_code}_scraper.js",
                    from_date=from_date,
                )

        # 모든 재시도 실패
        if not success:
            print(f"\n  ✗ 모든 재시도 실패 ({max_retry}회)")
            retry_results["failed"].append({
                **last_result,
                "retry_attempts": max_retry,
                "original_status": failed_item["status"]
            })

    print("\n" + "=" * 80)
    print("재시도 결과 요약")
    print("=" * 80)
    print(f"재시도 성공: {len(retry_results['success'])}개")
    print(f"재시도 실패: {len(retry_results['failed'])}개")
    print("=" * 80)

    return retry_results


def main():
    # 커맨드라인 인자 파싱
    parser = argparse.ArgumentParser(description='홈페이지 고시/공고 점진적 스크래핑 v2')
    parser.add_argument('--site-code', type=str, help='특정 사이트 코드만 처리 (예: --site-code acci)')
    args = parser.parse_args()
    
    total_start_time = time.time()

    print("=" * 80)
    print("홈페이지 고시/공고 점진적 스크래핑 v2")
    print(f"실행 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.site_code:
        print(f"대상 사이트: {args.site_code}")
    print("=" * 80)

    sites = get_sites_to_scrape(args.site_code)
    
    if not sites:
        if args.site_code:
            print(f"\n❌ 사이트 코드 '{args.site_code}'를 찾을 수 없습니다.")
        else:
            print("\n❌ 처리할 사이트가 없습니다.")
        return
    
    print(f"\n총 {len(sites)}개 사이트 대상")

    BASE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {"success": [], "failed": [], "skipped": [], "timeout": [], "error": []}
    from_dates_map = {}  # 재시도를 위한 from_date 매핑

    for idx, site in enumerate(sites, 1):
        site_code = site["site_code"]
        from_date = site["latest_announcement_date"]
        from_dates_map[site_code] = from_date  # from_date 저장

        print(f"\n{'='*80}")
        print(f"[{idx}/{len(sites)}] {site_code}")
        print(f"{'='*80}")

        result = run_scraper(site_code, from_date)
        status = result["status"]
        results[status].append(result)

        elapsed = result.get("elapsed_time", 0)

        # 모든 상태에 대해 로그 저장
        scraper_file = f"{site_code}_scraper.js"

        if status == "success":
            print(f"  ✓ 성공: {result['output_dir']} (소요시간: {elapsed:.1f}초)")
            # 스크래핑 성공 시 DB 업데이트
            update_latest_announcement_date(site_code, result["output_dir"])
            # 성공 로그 저장
            save_scraper_log(
                site_code=site_code,
                status="success",
                elapsed_time=elapsed,
                scraper_file=scraper_file,
                from_date=from_date,
                output_dir=result.get("output_dir"),
                scraped_count=result.get("scraped_count", 0),
            )
        elif status == "skipped":
            print(f"  ⊘ 스킵: {result['reason']} (소요시간: {elapsed:.1f}초)")
            # 스킵 로그 저장 (선택적)
            save_scraper_log(
                site_code=site_code,
                status="skipped",
                elapsed_time=elapsed,
                error_message=result.get("reason"),
                scraper_file=scraper_file,
                from_date=from_date,
            )
        elif status == "failed":
            print(f"  ✗ 실패: {result['error'][:200]} (소요시간: {elapsed:.1f}초)")
            # 실패 로그 저장
            log_id = save_scraper_log(
                site_code=site_code,
                status="failed",
                elapsed_time=elapsed,
                error_message=result.get("error"),
                scraper_file=scraper_file,
                from_date=from_date,
            )
            # 이메일 알림 발송 (선택적)
            if ALERT_ENABLED:
                if send_alert_email(
                    site_code, "failed", result.get("error"), elapsed, from_date
                ):
                    save_alert_history(
                        log_id,
                        site_code,
                        "failure",
                        result.get("error"),
                        ALERT_RECIPIENTS,
                    )
        elif status == "timeout":
            print(f"  ⏱ 타임아웃: {result['error']} (소요시간: {elapsed:.1f}초)")
            # 타임아웃 로그 저장
            log_id = save_scraper_log(
                site_code=site_code,
                status="timeout",
                elapsed_time=elapsed,
                error_message=result.get("error"),
                scraper_file=scraper_file,
                from_date=from_date,
            )
            # 타임아웃은 항상 이메일 알림 발송
            if send_alert_email(
                site_code, "timeout", result.get("error"), elapsed, from_date
            ):
                save_alert_history(
                    log_id, site_code, "timeout", result.get("error"), ALERT_RECIPIENTS
                )
        elif status == "error":
            print(f"  ⚠ 오류: {result['error'][:200]} (소요시간: {elapsed:.1f}초)")
            # 오류 로그 저장
            log_id = save_scraper_log(
                site_code=site_code,
                status="error",
                elapsed_time=elapsed,
                error_message=result.get("error"),
                scraper_file=scraper_file,
                from_date=from_date,
            )
            # 오류도 이메일 알림 발송
            if send_alert_email(
                site_code, "error", result.get("error"), elapsed, from_date
            ):
                save_alert_history(
                    log_id, site_code, "error", result.get("error"), ALERT_RECIPIENTS
                )

    # ====================================================================
    # 재시도 로직: 실패/타임아웃/오류 사이트 재시도
    # ====================================================================
    failed_to_retry = results["failed"] + results["timeout"] + results["error"]

    if failed_to_retry:
        retry_results = retry_failed_scrapers(failed_to_retry, from_dates_map, max_retry=2)

        # 재시도 성공한 항목을 success로 이동
        results["success"].extend(retry_results["success"])

        # 원래 실패 리스트에서 재시도 성공한 항목 제거
        retry_success_site_codes = {r["site_code"] for r in retry_results["success"]}
        results["failed"] = [r for r in results["failed"] if r["site_code"] not in retry_success_site_codes]
        results["timeout"] = [r for r in results["timeout"] if r["site_code"] not in retry_success_site_codes]
        results["error"] = [r for r in results["error"] if r["site_code"] not in retry_success_site_codes]

    total_elapsed = time.time() - total_start_time

    print("\n" + "=" * 80)
    print("최종 처리 결과 요약")
    print("=" * 80)
    print(f"성공: {len(results['success'])}개")
    print(f"실패: {len(results['failed'])}개")
    print(f"스킵: {len(results['skipped'])}개")
    print(f"타임아웃: {len(results['timeout'])}개")
    print(f"오류: {len(results['error'])}개")

    if results["skipped"]:
        print(f"\n스킵된 사이트 ({len(results['skipped'])}개):")
        for r in results["skipped"][:10]:
            print(f"  - {r['site_code']}")
        if len(results["skipped"]) > 10:
            print(f"  ... 외 {len(results['skipped']) - 10}개")

    print("\n" + "=" * 80)
    print(f"총 실행 시간: {total_elapsed:.1f}초 ({total_elapsed/60:.1f}분)")
    print(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 타임아웃이나 오류가 있었다면 종합 보고서 이메일 발송
    if (results["timeout"] or results["error"] or results["failed"]) and ALERT_ENABLED:
        send_summary_email(results, total_elapsed)


if __name__ == "__main__":
    main()
