#!/bin/bash

# NumPy 버전 충돌 해결 스크립트
# markitdown과 onnxruntime이 NumPy 2.x와 호환되지 않는 문제 해결

echo "=================================================="
echo "NumPy 버전 충돌 해결 스크립트"
echo "=================================================="
echo ""

# 현재 NumPy 버전 확인
echo "현재 NumPy 버전:"
python3 -c "import numpy; print(numpy.__version__)"
echo ""

# 옵션 1: NumPy 다운그레이드 (빠른 해결책)
echo "옵션 1: NumPy를 1.x 버전으로 다운그레이드"
echo "실행할 명령어:"
echo "pip install --user 'numpy<2.0'"
echo ""

# 옵션 2: onnxruntime 재설치
echo "옵션 2: onnxruntime과 markitdown 재설치 (시간이 걸릴 수 있음)"
echo "실행할 명령어:"
echo "pip uninstall -y onnxruntime markitdown"
echo "pip install --user --upgrade onnxruntime markitdown"
echo ""

echo "=================================================="
echo "권장 사항: 옵션 1을 먼저 시도하세요"
echo "=================================================="
echo ""
echo "바로 실행하시겠습니까? (y/n)"
read -r answer

if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    echo "NumPy 다운그레이드 시작..."
    pip install --user 'numpy<2.0'
    
    echo ""
    echo "변경된 NumPy 버전:"
    python3 -c "import numpy; print(numpy.__version__)"
    
    echo ""
    echo "=================================================="
    echo "완료! 이제 다시 테스트해보세요:"
    echo "python3 batch_scraper_to_pre_processor.py --source eminwon --date 2025-09-28"
    echo "=================================================="
else
    echo "수동으로 실행해주세요:"
    echo "pip install --user 'numpy<2.0'"
fi