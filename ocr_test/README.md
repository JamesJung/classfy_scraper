# OCR Performance Testing

이 디렉토리는 다양한 OCR 엔진의 성능을 테스트하고 비교하기 위한 테스트 파일들을 포함합니다.

## 테스트 대상 OCR 엔진

1. **docTR** - Deep Learning based OCR from Mindee
2. **Tesseract** - Google's traditional OCR engine
3. **EasyOCR** - Deep Learning based OCR with multi-language support
4. **PaddleOCR** - Baidu's high-performance OCR engine

## 설치 방법

각 OCR 엔진을 테스트하기 위해서는 해당 라이브러리를 설치해야 합니다:

```bash
# docTR
pip install python-doctr

# Tesseract
pip install pytesseract pillow
# 추가로 시스템에 tesseract-ocr 설치 필요
# Ubuntu/Debian: sudo apt-get install tesseract-ocr tesseract-ocr-kor
# macOS: brew install tesseract tesseract-lang
# Windows: https://github.com/UB-Mannheim/tesseract/wiki

# EasyOCR
pip install easyocr

# PaddleOCR
pip install paddleocr paddlepaddle
# GPU 지원: pip install paddlepaddle-gpu
```

## 사용 방법

각 테스트 파일을 개별적으로 실행:

```bash
# docTR 테스트
python test_doctr.py

# Tesseract 테스트
python test_tesseract.py

# EasyOCR 테스트
python test_easyocr.py

# PaddleOCR 테스트
python test_paddleocr.py
```

## 테스트 이미지

- **파일명**: `test_image.jpg`
- **출처**: https://www.bcci.or.kr
- **용도**: 한글/영문 혼합 문서 OCR 성능 테스트

## 출력 파일

각 테스트는 다음 파일들을 생성합니다:

- `{engine}_output.txt`: 추출된 텍스트
- `{engine}_detailed.txt`: 상세 결과 (신뢰도, 좌표 등)

## 성능 메트릭

각 테스트는 다음 성능 지표를 측정합니다:

- **초기화/모델 로딩 시간**: OCR 엔진 초기화 시간
- **이미지 로딩 시간**: 이미지 파일 읽기 시간
- **OCR 처리 시간**: 실제 텍스트 추출 시간
- **총 처리 시간**: 전체 소요 시간
- **추출된 문자 수**: 인식된 전체 문자 개수
- **추출된 라인 수**: 인식된 텍스트 라인 개수
- **평균 신뢰도**: 인식 결과의 평균 신뢰도 (지원하는 엔진만)

## 비교 분석

모든 테스트를 실행한 후, 다음 기준으로 엔진들을 비교할 수 있습니다:

1. **속도**: 총 처리 시간 비교
2. **정확도**: 추출된 텍스트의 품질과 신뢰도
3. **한글 지원**: 한글 인식 정확도
4. **설치 용이성**: 의존성 및 설치 복잡도
5. **GPU 지원**: GPU 가속 가능 여부