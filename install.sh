#!/bin/bash

echo "========================================"
echo "공고 첨부파일 처리 프로그램 설치 스크립트"
echo "========================================"

# Python 버전 확인
echo "1. Python 버전 확인..."
python3 --version
if [ $? -ne 0 ]; then
    echo "❌ Python3가 설치되지 않았습니다."
    exit 1
fi

# 가상환경 생성 (선택적)
read -p "가상환경을 생성하시겠습니까? (y/n): " create_venv
if [[ $create_venv == "y" || $create_venv == "Y" ]]; then
    echo "2. 가상환경 생성 중..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✅ 가상환경 생성 및 활성화 완료"
else
    echo "2. 가상환경 생성 건너뜀"
fi

# pip 업그레이드
echo "3. pip 업그레이드..."
pip install --upgrade pip

# 최소 필수 패키지 설치
echo "4. 필수 패키지 설치 중..."
pip install -r requirements_minimal.txt

if [ $? -eq 0 ]; then
    echo "✅ 필수 패키지 설치 완료"
else
    echo "❌ 패키지 설치 실패"
    exit 1
fi

# 추가 패키지 설치 여부 확인
read -p "전체 패키지를 설치하시겠습니까? (더 많은 기능, 더 오래 걸림) (y/n): " install_full
if [[ $install_full == "y" || $install_full == "Y" ]]; then
    echo "5. 전체 패키지 설치 중..."
    pip install -r requirements.txt
    echo "✅ 전체 패키지 설치 완료"
else
    echo "5. 전체 패키지 설치 건너뜀"
fi

echo ""
echo "========================================"
echo "✅ 설치 완료!"
echo "========================================"
echo ""
echo "다음 단계:"
echo "1. .env 파일에서 데이터베이스 및 Ollama 설정 확인"
echo "2. Ollama 서버가 실행 중인지 확인"
echo "3. MySQL 서버가 실행 중인지 확인"
echo ""
echo "사용법:"
echo "python announcement_processor.py --data data.enhanced --site-code acci"
echo ""
echo "도움말:"
echo "python announcement_processor.py --help"
echo ""