@echo off
echo ========================================
echo 공고 첨부파일 처리 프로그램 설치 스크립트
echo ========================================

REM Python 버전 확인
echo 1. Python 버전 확인...
python --version
if errorlevel 1 (
    echo ❌ Python이 설치되지 않았습니다.
    pause
    exit /b 1
)

REM 가상환경 생성 여부 확인
set /p create_venv=가상환경을 생성하시겠습니까? (y/n): 
if /i "%create_venv%"=="y" (
    echo 2. 가상환경 생성 중...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo ✅ 가상환경 생성 및 활성화 완료
) else (
    echo 2. 가상환경 생성 건너뜀
)

REM pip 업그레이드
echo 3. pip 업그레이드...
python -m pip install --upgrade pip

REM 최소 필수 패키지 설치
echo 4. 필수 패키지 설치 중...
pip install -r requirements_minimal.txt

if errorlevel 1 (
    echo ❌ 패키지 설치 실패
    pause
    exit /b 1
) else (
    echo ✅ 필수 패키지 설치 완료
)

REM 추가 패키지 설치 여부 확인
set /p install_full=전체 패키지를 설치하시겠습니까? (더 많은 기능, 더 오래 걸림) (y/n): 
if /i "%install_full%"=="y" (
    echo 5. 전체 패키지 설치 중...
    pip install -r requirements.txt
    echo ✅ 전체 패키지 설치 완료
) else (
    echo 5. 전체 패키지 설치 건너뜀
)

echo.
echo ========================================
echo ✅ 설치 완료!
echo ========================================
echo.
echo 다음 단계:
echo 1. .env 파일에서 데이터베이스 및 Ollama 설정 확인
echo 2. Ollama 서버가 실행 중인지 확인
echo 3. MySQL 서버가 실행 중인지 확인
echo.
echo 사용법:
echo python announcement_processor.py --data data.enhanced --site-code acci
echo.
echo 도움말:
echo python announcement_processor.py --help
echo.
pause