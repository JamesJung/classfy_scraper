#!/bin/bash

# 공고 처리 프로그램 실행 스크립트
# PYTHONPATH를 설정하여 import 문제 해결

# 스크립트가 있는 디렉토리로 이동
cd "$(dirname "$0")"

# PYTHONPATH 설정
export PYTHONPATH="$(pwd):$PYTHONPATH"

# 프로그램 실행
python3 announcement_processor.py "$@"