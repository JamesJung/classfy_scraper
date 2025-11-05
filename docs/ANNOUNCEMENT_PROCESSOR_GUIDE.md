# 공고 첨부파일 처리 프로그램

공고 디렉토리에서 첨부파일들을 텍스트로 변환하고, Ollama를 통해 구조화된 정보를 추출하여 MySQL 데이터베이스에 저장하는 프로그램입니다.

## 기능

1. **디렉토리 구조 처리**: 지정된 사이트코드의 공고 디렉토리들을 순차 처리
2. **첨부파일 변환**: PDF, HWP, 이미지 파일을 텍스트로 변환
3. **AI 분석**: Ollama를 통해 공고 정보 추출
4. **데이터베이스 저장**: 처리 결과를 MySQL에 저장

## 디렉토리 구조

```
{base_directory}/
└── {site_code}/
    ├── 001_공고제목1/
    │   ├── content.md
    │   └── attachments/
    │       ├── file1.pdf
    │       ├── file2.hwp
    │       └── image.png
    ├── 002_공고제목2/
    │   └── content.md
    └── ...
```

## 설치 및 설정

### 1. 자동 설치 (권장)

**Linux/macOS:**
```bash
./install.sh
```

**Windows:**
```cmd
install.bat
```

### 2. 수동 설치

**Python 가상환경 생성 (선택적):**
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 또는
venv\Scripts\activate.bat  # Windows
```

**필수 패키지 설치:**
```bash
pip install -r requirements_minimal.txt
```

**전체 패키지 설치 (더 많은 기능):**
```bash
pip install -r requirements.txt
```

### 3. 환경 설정

`.env` 파일을 확인하고 필요한 설정을 변경하세요:

```env
# 디렉토리 설정
DEFAULT_DIR=data
ROOT_DIR=/Users/jin/classfy_scraper/
INPUT_DIR=${ROOT_DIR}data.enhanced

# MySQL 데이터베이스 설정
DB_HOST=192.168.0.95
DB_PORT=3309
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=subvention

# Ollama API 설정
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

### 4. 필수 요구사항

1. **Python 3.8+**: Python 3.8 이상 버전이 필요합니다
2. **Ollama 설치 및 실행**:
   ```bash
   # Ollama 설치 (macOS)
   brew install ollama
   
   # Ollama 서비스 시작
   ollama serve
   
   # 모델 다운로드 (새 터미널에서)
   ollama pull llama3
   ```
3. **MySQL 서버**: 설정된 주소에 MySQL이 실행 중이어야 함

### 3. 데이터베이스 테이블 생성

프로그램 실행 시 자동으로 테이블이 생성되지만, 수동으로 생성하려면:

```bash
python -c "from src.models.announcementDatabase import create_announcement_tables; create_announcement_tables()"
```

## 사용법

### 기본 사용법

```bash
# 기본 사용법
python announcement_processor.py --data [디렉토리명] --site-code [사이트코드]

# 예시들
python announcement_processor.py --data data.enhanced --site-code acci
python announcement_processor.py --data data.origin --site-code cbt
python announcement_processor.py --data data.custom --site-code mysite
```

### 옵션

- `--data`: 데이터 디렉토리명 (생략 시 환경변수 DEFAULT_DIR 또는 'data' 사용)
- `--site-code`: 사이트 코드 (필수)
- `-r, --recursive`: 하위 디렉토리를 재귀적으로 처리
- `--skip-processed`: 이미 처리된 항목 건너뛰기 (기본 동작)
- `--force`: 이미 처리된 항목도 다시 처리
- `--help`: 도움말 표시

### 환경변수 사용

`--data` 옵션을 지정하지 않으면 환경변수 `DEFAULT_DIR` 또는 기본값 `data`를 사용합니다:

```bash
# 환경변수 설정
export DEFAULT_DIR=data.enhanced

# --data 옵션 생략 가능
python announcement_processor.py --site-code acci

# 재귀적 처리로 모든 하위 디렉토리 탐색
python announcement_processor.py --site-code acci -r
```

### 재귀적 처리 (`-r` 옵션)

`-r` 또는 `--recursive` 옵션을 사용하면 지정된 사이트코드 디렉토리의 모든 하위 디렉토리를 재귀적으로 탐색합니다.

**디렉토리 구조 예시:**
```
data.enhanced/
└── mysite/
    ├── AAA/
    │   └── BBB/
    │       ├── CCC/
    │       │   ├── content.md
    │       │   └── attachments/
    │       └── CC1/
    │           └── content.md
    └── AAB/
        └── AAA/
            ├── CCC/
            │   └── content.md  
            └── CCA/
                └── attachments/
```

**기본 처리 (재귀 없음):**
```bash
python announcement_processor.py --data data.enhanced --site-code mysite
# 처리 대상: AAA, AAB 디렉토리만
```

**재귀적 처리:**
```bash
python announcement_processor.py --data data.enhanced --site-code mysite -r
# 처리 대상: AAA_BBB_CCC, AAA_BBB_CC1, AAB_AAA_CCC, AAB_AAA_CCA
# (content.md나 attachments가 있는 모든 하위 디렉토리)
```

재귀적 처리 시:
- `content.md` 파일이 있거나 `attachments` 폴더가 있는 모든 하위 디렉토리를 찾습니다
- 디렉토리 경로는 언더스코어(`_`)로 연결하여 데이터베이스에 저장됩니다
- 예: `AAA/BBB/CCC` → `AAA_BBB_CCC`

## 처리 흐름

1. **디렉토리 스캔**: 지정된 사이트코드 디렉토리의 하위 폴더들을 발견
2. **중복 처리 방지**: 이미 처리된 폴더는 건너뜀 (`--force` 옵션으로 재처리 가능)
3. **content.md 읽기**: 기본 공고 내용 로드
4. **첨부파일 처리**:
   - PDF → 텍스트 변환 (docling, markitdown 사용)
   - HWP → 텍스트 변환 (기존 convertUtil 사용)
   - 이미지 → OCR 텍스트 추출 (EasyOCR 사용)
5. **내용 결합**: content.md + 모든 첨부파일 텍스트를 결합
6. **AI 분석**: Ollama를 통해 구조화된 정보 추출:
   - 지원대상
   - 지원금액
   - 제목
   - 접수기간
   - 모집일정
   - 지원내용
   - 소상공인 해당여부
7. **데이터베이스 저장**: 모든 결과를 MySQL에 저장

## 데이터베이스 스키마

### announcement_processing 테이블

| 필드명 | 타입 | 설명 |
|--------|------|------|
| id | INT(자동증가) | 기본키 |
| folder_name | VARCHAR(500) | 폴더명 |
| site_code | VARCHAR(100) | 사이트 코드 |
| content_md | LONGTEXT | content.md 내용 |
| combined_content | LONGTEXT | 전체 결합 내용 |
| ollama_response | JSON | Ollama 원본 응답 |
| extracted_title | TEXT | 추출된 제목 |
| extracted_target | TEXT | 추출된 지원대상 |
| extracted_amount | TEXT | 추출된 지원금액 |
| extracted_period | TEXT | 추출된 접수기간 |
| extracted_schedule | TEXT | 추출된 모집일정 |
| extracted_content | TEXT | 추출된 지원내용 |
| is_small_business | BOOLEAN | 소상공인 해당여부 |
| processing_status | VARCHAR(50) | 처리 상태 |
| error_message | TEXT | 오류 메시지 |
| created_at | DATETIME | 생성일시 |
| updated_at | DATETIME | 수정일시 |

### attachment_files 테이블

| 필드명 | 타입 | 설명 |
|--------|------|------|
| id | INT(자동증가) | 기본키 |
| announcement_id | INT | 공고 처리 ID (외래키) |
| filename | VARCHAR(255) | 파일명 |
| file_extension | VARCHAR(10) | 파일 확장자 |
| file_path | VARCHAR(1000) | 원본 파일 경로 |
| file_size | INT | 파일 크기 |
| converted_content | LONGTEXT | 변환된 텍스트 |
| conversion_method | VARCHAR(50) | 변환 방법 |
| conversion_success | BOOLEAN | 변환 성공 여부 |
| conversion_error | TEXT | 변환 오류 메시지 |
| created_at | DATETIME | 생성일시 |

## 로그 및 모니터링

로그는 `logs/` 디렉토리에 저장됩니다:
- 일반 로그: `logs/app.log`
- 오류 로그: `logs/app_error.log`

## 문제 해결

### 1. Ollama 연결 오류
```bash
# Ollama 상태 확인
curl http://localhost:11434/api/tags

# Ollama 서비스 재시작
pkill ollama
ollama serve
```

### 2. MySQL 연결 오류
- `.env` 파일의 데이터베이스 설정 확인
- MySQL 서버 상태 확인
- 방화벽 및 포트 설정 확인

### 3. 첨부파일 변환 오류
- PDF: `pip install markitdown docling` 확인
- HWP: 기존 HWP 변환 라이브러리 설치 상태 확인
- 이미지: `pip install easyocr` 확인

## 성능 최적화 팁

1. **배치 처리**: 여러 사이트코드를 순차적으로 처리
2. **메모리 관리**: 큰 파일 처리 시 메모리 사용량 모니터링
3. **병렬 처리**: 향후 멀티프로세싱 지원 고려
4. **Ollama 모델**: 처리 속도와 정확도에 따라 모델 변경 가능

## 예제

### 기본 실행
```bash
python announcement_processor.py --data data.enhanced --site-code acci
```

### 재귀적 처리
```bash
python announcement_processor.py --data data.enhanced --site-code acci -r
```

### 강제 재처리
```bash
python announcement_processor.py --data data.enhanced --site-code acci --force
```

### 재귀적 + 강제 재처리
```bash
python announcement_processor.py --data data.enhanced --site-code acci -r --force
```

### 여러 사이트 배치 처리
```bash
#!/bin/bash
for site in acci andongcci ansancci anseongcci; do
    echo "Processing site: $site"
    python announcement_processor.py --data data.enhanced --site-code $site -r
done
```

## 추가 기능 아이디어

요청하신 기능들이 모두 구현되었습니다. 추가로 고려할 수 있는 개선사항:

1. **웹 인터페이스**: 처리 상태를 모니터링할 수 있는 대시보드
2. **API 서버**: REST API로 처리 결과 조회
3. **스케줄링**: cron 등을 통한 자동 처리
4. **알림 기능**: 처리 완료 시 이메일/슬랙 알림
5. **데이터 검증**: 추출된 정보의 품질 검증
6. **통계 리포트**: 처리 결과 통계 및 분석

## 라이센스

기존 프로젝트의 라이센스를 따릅니다.