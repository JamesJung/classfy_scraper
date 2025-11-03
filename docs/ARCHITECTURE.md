# Claude Code 작업 히스토리

이 문서는 Claude Code와 함께 진행한 공고 처리 시스템 개발 및 최적화 작업을 기록합니다.

## 📋 목차

1. [프로젝트 개요](#프로젝트-개요)
2. [주요 작업 내역](#주요-작업-내역)
3. [성능 최적화](#성능-최적화)
4. [파일 구조](#파일-구조)
5. [사용법](#사용법)
6. [성능 테스트 결과](#성능-테스트-결과)
7. [향후 개선사항](#향후-개선사항)

## 🎯 프로젝트 개요

공고 처리 및 분석 시스템의 성능 개선을 위한 병렬 처리 구현 프로젝트입니다.

### 주요 목표
- Ollama 서버 성능 테스트 및 최적화
- 기존 순차 처리를 병렬 처리로 전환
- 2.48배 성능 향상 달성
- 스레드 안전성 보장

## 🚀 주요 작업 내역

### 1. 한글 텍스트 정규화 (2025-09-08)
- **문제**: Windows에서 한글 문자가 자음/모음 분리되어 표시 (NFD vs NFC)
- **해결**: `unicodedata.normalize('NFC')` 적용
- **적용 파일**: `announcement_prv_processor.py`
- **결과**: 392개 PRV 레코드, 269개 일반 레코드 정규화

### 2. 데이터베이스 최적화 (2025-09-08)
- **문제**: `max_allowed_packet` 용량 부족
- **해결**: 16MB → 64MB 증설
- **설정 파일**: `/etc/mysql/mysql.conf.d/mysqld.cnf`

### 3. 2단계 처리 구조 구현 (2025-09-08)
- **기존**: 순차적 전체 처리
- **개선**: content.md 우선 → 지원사업 판별 → 필요시 첨부파일 처리
- **효과**: 불필요한 첨부파일 처리 생략

### 4. 제목 기반 조기 종료 최적화 (2025-09-08)
- **로직**: 제목에 "지원" 키워드 포함시 Ollama 분석 생략
- **효과**: 지원사업 공고 처리 시간 대폭 단축
- **적용**: PRV 및 일반 공고 처리 모두

### 5. Ollama 성능 테스트 및 분석 (2025-09-08)
- **테스트 파일**:
  - `ollama_performance_tester.py`: 개별 성능 측정
  - `resource_monitor.py`: 서버 리소스 모니터링
  - `ollama_concurrent_test.py`: 동시 요청 성능 테스트

### 6. 병렬 처리 구현 (2025-09-08)
- **최적 워커 수**: 2개 (실험으로 검증)
- **성능 향상**: 2.48배 speedup
- **구현 파일**:
  - `announcement_prv_processor_parallel.py`
  - `announcement_processor_parallel.py`

## ⚡ 성능 최적화

### Ollama 동시 요청 성능 테스트 결과

| 워커 수 | 평균 응답 시간 | 성공률 | 성능 향상 | 효율성 |
|--------|-------------|--------|----------|--------|
| 1 (순차) | 9.67초 | 100% | 1.00x | - |
| 2 (병렬) | 3.90초 | 100% | **2.48x** | 124% |
| 4 (병렬) | 15.00초 | 100% | 0.64x | 16% |
| 6 (병렬) | 21.84초 | 100% | 0.44x | 7% |

### 최적화 기법

1. **2개 워커 병렬 처리**: 실험적으로 검증된 최적값
2. **제목 키워드 조기 종료**: Ollama API 호출 생략
3. **2단계 처리**: content.md 우선 분석 후 필요시 첨부파일 처리
4. **스레드별 인스턴스**: ThreadLocal로 스레드 안전성 보장

## 📁 파일 구조

### 핵심 처리 파일
```
classfy_scraper/
├── announcement_prv_processor.py              # PRV 순차 처리 (원본)
├── announcement_prv_processor_parallel.py     # PRV 병렬 처리 (신규)
├── announcement_processor.py                  # 일반 순차 처리 (원본)
├── announcement_processor_parallel.py         # 일반 병렬 처리 (신규)
└── CLAUDE.md                                 # 이 문서
```

### 성능 테스트 파일
```
classfy_scraper/
├── ollama_performance_tester.py              # 개별 성능 측정
├── resource_monitor.py                       # 서버 리소스 모니터링
├── ollama_concurrent_test.py                 # 동시 요청 테스트
└── ollama_concurrent_test_results_20250908_112213.csv  # 테스트 결과
```

### 유틸리티 파일
```
classfy_scraper/
├── normalize_korean_in_db.py                 # 기존 DB 한글 정규화
├── title_support_reprocessor.py              # 제목 기반 지원사업 재처리
└── cleanup_attachments_md.py                 # 첨부파일 정리
```

## 💻 사용법

### PRV 공고 병렬 처리
```bash
# 기본 사용 (2개 워커)
python announcement_prv_processor_parallel.py --data prv

# 워커 수 조정
python announcement_prv_processor_parallel.py --data prv --workers 2

# 강제 재처리
python announcement_prv_processor_parallel.py --data prv --force --attach-force
```

### 일반 공고 병렬 처리
```bash
# 기본 사용
python announcement_processor_parallel.py --site-code acci --data data

# 워커 수 조정
python announcement_processor_parallel.py --site-code cbt --workers 2

# 재귀적 처리
python announcement_processor_parallel.py --site-code acci -r --force
```

### 성능 테스트
```bash
# Ollama 동시 요청 성능 테스트
python ollama_concurrent_test.py

# 개별 성능 측정
python ollama_performance_tester.py
```

### DB 유지보수
```bash
# 한글 텍스트 정규화
python normalize_korean_in_db.py

# 제목 기반 지원사업 재처리
python title_support_reprocessor.py
```

## 📊 성능 테스트 결과

### 실험 환경
- **Ollama 모델**: llama3.1:8b
- **테스트 날짜**: 2025-09-08
- **서버 환경**: Local Ollama server

### 주요 발견사항
1. **2개 워커가 최적**: 2.48배 성능 향상
2. **4개 이상 워커**: 성능 저하 (서버 과부하)
3. **품질 저하 없음**: 모든 테스트에서 응답 품질 유지
4. **안정적 성공률**: 모든 동시성 레벨에서 100% 성공률

### 최적화 효과
- **처리 시간**: 9.67초 → 3.90초 (59.7% 단축)
- **처리량**: 0.10 RPS → 0.26 RPS (160% 증가)
- **CPU/메모리**: 효율적 자원 활용
- **품질**: 동일한 분석 품질 유지

## 🔧 주요 기능

### 병렬 처리 특징
- **ThreadPoolExecutor**: 2개 워커 풀
- **ThreadLocal 인스턴스**: 스레드별 독립적 인스턴스
- **스레드 안전 DB 연결**: 각 스레드별 DB 세션
- **실시간 진행상황**: 병렬 처리 진행률 표시

### 최적화 로직
- **제목 키워드 검사**: "지원" 포함시 조기 종료
- **2단계 처리**: content.md → 지원사업 판별 → 첨부파일
- **캐싱**: 변환된 첨부파일 .md 캐싱
- **필터링**: 양식/신청서 등 불필요 파일 제외

### 모니터링 기능
- **실시간 통계**: 성공/실패/건너뜀 카운트
- **처리 시간**: 개별 항목별 처리 시간 추적
- **성능 추정**: 순차 처리 대비 성능 향상 계산
- **오류 추적**: 상세한 오류 로깅

## 🔄 데이터베이스 스키마

### PRV 처리 테이블
```sql
CREATE TABLE announcement_prv_processing (
    id INT PRIMARY KEY AUTO_INCREMENT,
    folder_name VARCHAR(255) UNIQUE,
    site_code VARCHAR(50),
    content_md LONGTEXT,
    combined_content LONGTEXT,
    processing_status VARCHAR(50),
    is_support_program BOOLEAN,
    support_program_reason TEXT,
    -- ... 기타 추출 필드들
);
```

### 일반 처리 테이블
```sql
CREATE TABLE announcement_processing (
    id INT PRIMARY KEY AUTO_INCREMENT,
    folder_name VARCHAR(255) UNIQUE,
    site_code VARCHAR(50),
    content_md LONGTEXT,
    combined_content LONGTEXT,
    processing_status VARCHAR(50),
    -- ... 기타 추출 필드들
);
```

## 🧪 테스트 결과 상세

### 동시성 테스트 데이터
```
concurrent_2_1757298072: 2.48x 성능 향상 ✅
concurrent_4_1757298078: 0.64x 성능 저하 ❌ 
concurrent_6_1757298101: 0.44x 성능 저하 ❌
```

### 품질 점수
- **모든 테스트**: 0.7/1.0 동일한 품질
- **품질 저하**: 0% (품질 손실 없음)
- **성공률**: 100% (모든 요청 성공)

## 🎯 향후 개선사항

### 단기 계획
- [ ] GPU 가속 Ollama 서버 테스트
- [ ] 더 큰 모델(70B)에서의 동시성 테스트
- [ ] 배치 처리 API 활용 검토

### 중기 계획
- [ ] 클러스터 환경에서의 분산 처리
- [ ] Redis 캐싱 레이어 추가
- [ ] 실시간 대시보드 구현

### 장기 계획
- [ ] AI 모델 직접 최적화
- [ ] 전용 하드웨어 구성
- [ ] Auto-scaling 구현

## 📈 성과 요약

### 정량적 성과
- **처리 속도**: 2.48배 향상
- **처리 시간**: 59.7% 단축
- **처리량**: 160% 증가
- **품질**: 100% 유지

### 정성적 성과
- **시스템 안정성**: 스레드 안전성 보장
- **유지보수성**: 명확한 코드 구조
- **확장성**: 워커 수 조정 가능
- **모니터링**: 상세한 진행상황 추적

## 🔍 기술적 세부사항

### 스레드 안전성
```python
class ParallelAnnouncementProcessor:
    def __init__(self):
        # 스레드별 인스턴스 저장소
        self._local = threading.local()
        
        # 통계 추적용 락
        self._stats_lock = threading.Lock()
    
    def _get_local_instances(self):
        if not hasattr(self._local, 'initialized'):
            # 각 스레드별 독립 인스턴스
            self._local.attachment_processor = AttachmentProcessor()
            self._local.announcement_analyzer = AnnouncementAnalyzer()
            # ...
```

### 성능 측정
```python
@dataclass
class ProcessingResult:
    task_id: str
    folder_name: str
    success: bool
    error_message: Optional[str] = None
    processing_time: float = 0.0
```

### 조기 종료 최적화
```python
def _process_directory_core(self, task):
    # ... DB 저장 후
    
    # 제목에서 "지원" 키워드 확인
    if content_md.strip():
        extracted_title = self._extract_title_from_content(content_md)
        if "지원" in extracted_title:
            # Ollama 분석 생략하고 즉시 성공 처리
            return self._update_processing_result_simple(
                record_id, status="성공", 
                error_message="제목에 지원이라는 글자 있음"
            )
```

## 📞 문의 및 지원

이 시스템에 대한 문의사항이나 개선 제안이 있으시면 다음을 통해 연락주세요:

- **개발**: Claude Code 시스템
- **최적화**: 병렬 처리 및 성능 튜닝
- **테스트**: Ollama 서버 동시성 검증

---

**마지막 업데이트**: 2025-09-08  
**버전**: 2.0 (병렬 처리)  
**상태**: 운영 준비 완료 ✅