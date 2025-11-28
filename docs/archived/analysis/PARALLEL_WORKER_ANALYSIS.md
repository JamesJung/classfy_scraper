# 병렬 워커(3개) 작업 분할 방식 분석 보고

## 📌 요약

`batch_scraper_to_pre_processor.py`는 **지역(사이트)별로 작업을 분할**하여 3개의 병렬 워커에게 할당합니다.
각 워커는 **하나의 사이트 전체**를 독립적으로 처리하며, 동일 사이트 내의 공고들은 순차적으로 처리됩니다.

---

## 🔍 핵심 발견 사항

### 1. 작업 단위: **지역(사이트) 단위**

```python
# batch_scraper_to_pre_processor.py:113-125
def get_region_folders(self) -> List[Path]:
    """처리할 지역 폴더 목록 반환"""
    if not self.base_dir.exists():
        return []

    # 하위 디렉토리만 추출 (지역 폴더)
    region_folders = [
        d for d in self.base_dir.iterdir()
        if d.is_dir() and not d.name.startswith('.')
    ]

    return sorted(region_folders)
```

**작업 단위**:
- `/home/zium/moabojo/incremental/btp/20251111/` 디렉토리 내의 각 사이트 폴더
- 예: `keiti/`, `cceiGyeonggi/`, `gb/`, `tongyeong/` 등 각 사이트가 하나의 작업 단위

---

### 2. 병렬 처리 방식: **ThreadPoolExecutor**

```python
# batch_scraper_to_pre_processor.py:308-344
with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
    # 작업 제출
    futures = {
        executor.submit(self.process_region, region): region
        for region in region_folders
    }

    # 진행 상황 모니터링
    for future in as_completed(futures):
        region = futures[future]
        result = future.result()
        # 처리 완료...
```

**동작 방식**:
- `ThreadPoolExecutor`가 `max_workers=5` (기본값) 또는 3개의 워커 스레드 생성
- 각 워커는 **하나의 사이트(region) 전체**를 담당
- 사이트 처리가 완료되면 다음 대기 중인 사이트를 할당받음

---

### 3. 각 워커의 처리 과정

```python
# batch_scraper_to_pre_processor.py:151-251
def process_region(self, region_path: Path) -> Dict[str, Any]:
    """단일 지역 처리"""
    region_name = region_path.name
    normalized_site_code = self.normalize_site_code(region_name)

    # 지역 폴더 내 공고 폴더 수 확인
    announcement_folders = [
        d for d in region_path.iterdir()
        if d.is_dir() and not d.name.startswith('.')
    ]

    # announcement_pre_processor.py 실행
    cmd = [
        sys.executable,
        'announcement_pre_processor.py',
        '-d', str(region_path),  # ← 사이트 디렉토리 전체를 전달
        '-s', normalized_site_code,
        '--batch-mode'
    ]

    if self.force:
        cmd.append('--force')
    if self.attach_force:
        cmd.append('--attach-force')

    # 프로세스 실행 (최대 20분 타임아웃)
    process = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=1200
    )
```

**각 워커가 수행하는 작업**:
1. 하나의 사이트 디렉토리(예: `keiti/`)를 받음
2. 해당 사이트 내 모든 공고 폴더 개수를 카운트
3. `announcement_pre_processor.py`를 별도 프로세스로 실행
   - `-d` 파라미터: 사이트 디렉토리 경로
   - `-s` 파라미터: 정규화된 사이트 코드 (끝에 시/군/구 제거)
4. 최대 20분 동안 해당 프로세스가 완료될 때까지 대기
5. 결과를 반환하고 다음 사이트 처리

---

## 📊 작업 분할 시나리오 예시

### 시나리오: 2025-11-11 데이터 처리 (총 50개 사이트)

**초기 상태**:
- 총 50개 사이트 폴더
- 병렬 워커 3개 실행

**처리 과정**:

```
[초기]
Worker 1: keiti 폴더 처리 시작 (10개 공고)
Worker 2: cceiGyeonggi 폴더 처리 시작 (25개 공고)
Worker 3: tongyeong 폴더 처리 시작 (50개 공고)

대기 중: gb, pohang, gijang, ... (47개 사이트)

[10초 후 - Worker 1 완료]
Worker 1: keiti 완료 → gb 폴더 처리 시작
Worker 2: cceiGyeonggi 처리 중...
Worker 3: tongyeong 처리 중...

대기 중: pohang, gijang, ... (46개 사이트)

[30초 후 - Worker 2 완료]
Worker 1: gb 처리 중...
Worker 2: cceiGyeonggi 완료 → pohang 폴더 처리 시작
Worker 3: tongyeong 처리 중... (공고가 많아서 오래 걸림)

대기 중: gijang, ... (45개 사이트)

[계속...]
```

**특징**:
- ✅ 공고가 적은 사이트는 빨리 완료되어 워커가 다음 사이트 처리
- ⚠️ 공고가 많은 사이트는 해당 워커가 오래 점유
- ⚠️ 작업 부하가 불균등할 수 있음 (사이트별 공고 수 차이)

---

## 🔑 핵심 포인트

### ✅ 작업 분할 방식

**분할 단위**: **사이트 단위**
- 각 사이트의 모든 공고를 하나의 워커가 처리
- 동일 사이트 내 공고들은 순차적으로 처리됨

**분할되지 않는 것**: **사이트 내부의 공고들**
- 예: `keiti` 사이트에 10개 공고가 있으면, 1개 워커가 10개를 모두 처리
- 10개 공고를 3개 워커가 나눠서 처리하지 않음

---

### ⚙️ 병렬 처리 설정

```python
# batch_scraper_to_pre_processor.py:24-32
def __init__(self, data_source: str = 'eminwon', date_str: Optional[str] = None,
             max_workers: int = 5, force: bool = False, attach_force: bool = False):
    """
    Args:
        max_workers: 병렬 처리 워커 수 (기본값: 5)
    """
    self.max_workers = max_workers
```

**기본값**: 5개 워커
**실제 사용**: 사용자가 3개로 설정 가능 (`--workers 3`)

**명령어 예시**:
```bash
python3 batch_scraper_to_pre_processor.py \
    --source scraper \
    --date 2025-11-11 \
    --workers 3  # ← 워커 수 지정
```

---

### 📈 성능 특성

**장점**:
- ✅ 사이트별로 독립적 처리 → 오류 격리 (한 사이트 실패가 다른 사이트에 영향 없음)
- ✅ 간단한 구현 (복잡한 동기화 불필요)
- ✅ ThreadPoolExecutor의 자동 작업 분배

**단점**:
- ⚠️ 사이트별 공고 수 차이로 인한 불균등 부하
  - 예: tongyeong 50개 vs keiti 2개
  - tongyeong을 처리하는 워커는 오래 걸리고, keiti 처리 워커는 금방 완료
- ⚠️ 대용량 사이트가 병목이 될 수 있음

**실제 로그 예시** (batch_scraper_to_pre_processor.py:336-341):
```
[  5.2%] ✅ keiti               (  2개 공고,  12.3초)
[  7.8%] ✅ gb                  (  5개 공고,  25.1초)
[ 13.5%] ✅ cceiGyeonggi        ( 15개 공고,  78.4초)
[ 15.2%] ✅ tongyeong           ( 50개 공고, 302.1초)  ← 오래 걸림
```

---

## 🧪 실제 처리 흐름 검증

### announcement_pre_processor.py에서의 처리

`batch_scraper_to_pre_processor.py`가 전달하는 것:
- `-d /home/zium/moabojo/incremental/btp/20251111/keiti`
- `-s keiti`
- `--batch-mode`

`announcement_pre_processor.py`가 수행하는 것:
1. `keiti` 폴더 내 모든 하위 폴더를 순회
2. 각 공고 폴더를 순차적으로 처리:
   - `001_공고1/` 처리
   - `002_공고2/` 처리
   - `003_공고3/` 처리
   - ...
3. 모든 공고 처리 완료 후 종료

**병렬 처리 수준**: ❌ 없음
- `announcement_pre_processor.py`는 **순차 처리**만 수행
- 병렬 처리는 오직 `batch_scraper_to_pre_processor.py` 레벨에서만 발생

---

## 💡 개선 가능성 분석

### 현재 방식의 문제점

**시나리오**: 100개 사이트, 공고 수 분포
- 95개 사이트: 각 1~5개 공고 (총 200개)
- 5개 사이트: 각 100개 공고 (총 500개)

**3개 워커로 처리 시**:
1. Worker 1, 2, 3이 처음 95개 사이트를 빠르게 처리 (10분 소요)
2. 마지막 5개 대용량 사이트는 3개 워커가 처리
3. 2개 워커는 처리 완료 후 대기 (idle)
4. 1개 워커만 마지막 사이트 처리 중 → **병렬화 효율 저하**

---

### 개선 방안 (참고용)

#### 옵션 1: 공고 단위 병렬 처리 (근본적 개선)

```python
# 사이트별로 공고 목록을 먼저 수집
all_announcements = []
for site in sites:
    for announcement in site.announcements:
        all_announcements.append((site, announcement))

# 공고 단위로 병렬 처리
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = {
        executor.submit(process_announcement, site, announcement): (site, announcement)
        for site, announcement in all_announcements
    }
```

**장점**:
- ✅ 작업 부하가 균등하게 분배
- ✅ 대용량 사이트도 여러 워커가 분담 처리

**단점**:
- ⚠️ DB 동시성 제어 필요 (중복 처리 방지)
- ⚠️ 구현 복잡도 증가

---

#### 옵션 2: 사이트 크기 기반 우선순위 처리

```python
# 사이트를 공고 수 기준으로 정렬 (큰 것부터)
region_folders = sorted(
    region_folders,
    key=lambda r: count_announcements(r),
    reverse=True
)

# 큰 사이트를 먼저 처리하여 병렬화 효율 향상
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = {
        executor.submit(process_region, region): region
        for region in region_folders
    }
```

**장점**:
- ✅ 코드 변경 최소
- ✅ 큰 사이트를 먼저 처리하여 후반 idle 시간 감소

**단점**:
- ⚠️ 여전히 근본적 해결은 아님

---

#### 옵션 3: 워커 수 증가

```bash
# 현재: 3개 워커
python3 batch_scraper_to_pre_processor.py --workers 3

# 개선: 5개 또는 10개 워커
python3 batch_scraper_to_pre_processor.py --workers 10
```

**장점**:
- ✅ 설정만 변경 (코드 수정 불필요)
- ✅ 더 많은 사이트 동시 처리

**단점**:
- ⚠️ DB 부하 증가
- ⚠️ CPU/메모리 제약
- ⚠️ 근본적 문제(불균등 부하)는 해결 안 됨

---

## 🎯 결론

### 현재 방식 요약

1. **작업 단위**: 사이트(지역) 단위로 분할
2. **병렬 수준**: 3개 워커가 사이트별로 독립 처리
3. **워커 할당**: `ThreadPoolExecutor`가 자동으로 다음 사이트 할당
4. **사이트 내부**: 순차 처리 (병렬 처리 없음)

### 질문에 대한 답변

**"병렬 워커(3개)가 동시에 대용량 파일 처리하는 부분 처리할 항목을 나눠서 하는건지"**

**답변**:
- ✅ **사이트 단위**로는 나눠서 처리함 (각 워커가 다른 사이트 처리)
- ❌ **동일 사이트의 공고들**은 나눠서 처리하지 않음 (1개 워커가 모두 처리)
- ❌ **대용량 파일 자체**를 나눠서 처리하지 않음 (파일은 announcement_pre_processor.py에서 순차 처리)

### 실무적 관점

**현재 방식은 합리적인가?**
- ✅ **대부분의 경우 효율적**: 사이트 수가 많고 공고 수가 비슷하면 잘 작동
- ⚠️ **일부 비효율 존재**: 공고 수 편차가 크면 워커 idle 시간 발생
- ✅ **안정성 우수**: 사이트별 격리로 오류 전파 방지

**개선 필요성**:
- 현재 방식으로 큰 문제가 없다면 유지
- 처리 시간이 문제라면 워커 수 증가가 가장 간단한 해결책
- 근본적 개선이 필요하면 공고 단위 병렬 처리 검토

---

**작성일**: 2025-11-18
**분석 파일**: `batch_scraper_to_pre_processor.py`
**핵심 라인**: 23-32 (초기화), 113-125 (작업 분할), 151-251 (워커 처리), 308-344 (병렬 실행)
