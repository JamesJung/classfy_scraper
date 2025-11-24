# 유효하지 않은 ZIP 파일 오류 분석 보고서

**분석 일시**: 2025-11-24
**분석 대상**: logs/app_error.log.20251122의 HWPX ZIP 오류
**담당자**: Claude Code

---

## 📋 Executive Summary

### 문제 요약
- 로그에 "유효하지 않은 ZIP 파일 (HWPX)" 오류가 **12건** 발생
- **6개의 유니크한 HWPX 파일**에서 오류 발생 (각 파일당 2번씩 오류 기록)
- DB 확인 결과 6건 모두 **텍스트 추출 실패** (`combined_content`가 EMPTY)

### 결론
**⚠️ 실제 텍스트 추출 실패**
- 로그의 오류는 실제 문제를 반영
- 6건의 공고에서 첨부파일 내용 추출이 완전히 실패
- Fallback 메커니즘이 제대로 작동하지 않음

---

## 🔍 상세 분석

### 1. 로그 파일 분석

#### 발견된 오류 (총 12건, 유니크 파일 6개)

| 파일명 | 발생 횟수 | 파일 크기 |
|--------|-----------|-----------|
| 입법예고문(부산광역시 건축 조례 일부개정조례안).hwpx | 2회 | 92,672 bytes |
| 입법예고문(부산광역시 공영차고지 관리 및 운영 조례 일부개정조례안).hwpx | 2회 | 45,056 bytes |
| 입법예고문(부산광역시 교통약자의 이동편의 증진 조례 일부개정조례안).hwpx | 2회 | 50,688 bytes |
| 입법예고문(부산광역시 노후계획도시 정비 및 지원에 관한 조례 일부개정조례안).hwpx | 2회 | 41,472 bytes |
| 입법예고문(부산광역시 빈집 및 소규모주택 정비 조례 일부개정조례안).hwpx | 2회 | 42,496 bytes |
| 입법예고문(부산광역시 자전거이용 활성화에 관한 조례 일부개정조례안).hwpx | 2회 | 47,616 bytes |

#### 오류 로그 예시
```
2025-11-23 10:45:33,842 - src.utils.hwp_custom - [hwp_custom.py:115] - ERROR - 유효하지 않은 ZIP 파일 (HWPX): 입법예고문(부산광역시 교통약자의 이동편의 증진 조례 일부개정조례안).hwpx
```

---

### 2. DB 상태 확인

#### announcement_pre_processing 테이블 조회 결과

모든 6건의 공고에서 **텍스트 추출 실패** 확인:

| ID | 사이트 | 제목 | 공고일 | 텍스트 길이 | 텍스트 상태 | 처리 상태 |
|----|--------|------|--------|-------------|-------------|-----------|
| 93369 | prv_busan | 「부산광역시 노후계획도시 정비 및 지원에 관한 조례 일부개정조례안」 입법예고 | 20251114 | **0자** | **EMPTY** | 제외 |
| 93370 | prv_busan | 「부산광역시 빈집 및 소규모주택 정비 조례 일부개정조례안」 입법예고 | 20251114 | **0자** | **EMPTY** | 제외 |
| 93371 | prv_busan | 「부산광역시 건축 조례 일부개정조례안」 입법예고 | 20251114 | **0자** | **EMPTY** | 제외 |
| 93372 | prv_busan | 「부산광역시 자전거이용 활성화에 관한 조례 일부개정조례안」 입법예고 | 20251114 | **0자** | **EMPTY** | 제외 |
| 93373 | prv_busan | 「부산광역시 공영차고지 관리 및 운영 조례 일부개정조례안」 입법예고 | 20251114 | **0자** | **EMPTY** | 제외 |
| 93374 | prv_busan | 「부산광역시 교통약자의 이동편의 증진 조례 일부개정조례안」 입법예고 | 20251114 | **0자** | **EMPTY** | 제외 |

**attachment_files_list 예시**:
```json
[{
  "filename": "입법예고문(부산광역시 교통약자의 이동편의 증진 조례 일부개정조례안).hwpx",
  "file_size": 50688,
  "conversion_success": false,
  "conversion_method": "hwp_markdown",
  "download_url": "https://www.busan.go.kr/nbgosi/download?fileId=F..."
}]
```

---

### 3. 파일 형식 분석

#### 실제 파일 분석 결과

테스트 파일: `tests/입법예고문(부산광역시 교통약자의 이동편의 증진 조례 일부개정조례안).hwpx`

```
파일 크기: 50,688 bytes
매직 넘버: d0cf11e0 (HWP 5.0 OLE 형식)
```

**핵심 발견**:
- 파일 확장자는 `.hwpx`이지만 실제로는 **HWP 5.0 (OLE) 형식**
- HWPX는 일반적으로 ZIP 기반이지만, 이 파일들은 **구 버전 OLE 형식**
- 파일명과 실제 형식이 불일치

#### 파일 형식 비교

| 형식 | 매직 넘버 | 구조 | 확장자 |
|------|-----------|------|--------|
| **HWPX (진짜)** | `50 4B 03 04` (PK..) | ZIP 기반 | .hwpx |
| **HWP 5.0 (실제)** | `d0 cf 11 e0` | OLE 복합 문서 | .hwp |
| **이번 케이스** | `d0 cf 11 e0` | OLE 복합 문서 | **.hwpx** ⚠️ |

---

### 4. 코드 흐름 분석

#### 현재 처리 흐름

1. **attachmentProcessor.py** → `_process_single_hwp()`
   ```python
   elif file_extension in [".hwp", ".hwpx"]:
       return self._process_single_hwp(file_path)
   ```

2. **convertUtil.py** → `convert_hwp_to_markdown()` 시도
   - hwp_markdown 사용 (실패)

3. **convertUtil.py** → `process_hwp_with_fallback()` 호출
   ```python
   # HWPX 파일인 경우 직접 처리
   if hwp_file_path.suffix.lower() == ".hwpx":
       try:
           return convert_hwpx_to_text(hwpx_file_path)  # ❌ 여기서 실패
       except Exception as e:
           logger.error(f"Fallback HWPX 텍스트 추출 실패: {hwp_file_path.name} - {e}")
           return None  # ❌ None 반환 후 종료
   ```

4. **convertUtil.py** → `convert_hwpx_to_text()`
   ```python
   # gethwp.read_hwpx() 호출
   extracted_text = gethwp.read_hwpx(str(hwpx_file_path))
   # ❌ ZIP 오류 발생 - BadZipFile: File is not a zip file
   ```

#### 문제점 발견

**Fallback 로직의 맹점**:
- `.hwpx` 확장자만 보고 `convert_hwpx_to_text()` 호출
- `gethwp.read_hwpx()`는 ZIP 기반 HWPX만 처리 가능
- OLE 형식인 경우 처리 불가
- **하지만 `gethwp.read_hwp()`는 OLE 형식 처리 가능!**

---

### 5. 실제 테스트 결과

#### gethwp 라이브러리 테스트

```python
# ❌ read_hwpx() 실패
gethwp.read_hwpx(test_file)
# BadZipFile: File is not a zip file

# ✅ read_hwp() 성공!
text = gethwp.read_hwp(test_file)
# 추출된 텍스트 길이: 6,182자
```

**추출된 텍스트 샘플**:
```
부산광역시의회 공고 제2025-278호
부산광역시 교통약자의 이동편의 증진 조례 일부개정조례안 입법예고
 「부산광역시 교통약자의 이동편의 증진 조례」를 개정함에 있어 그 내용과 취지를 미리 알려 시민 여러분의 의견을 듣고자 다음과 같이 공고합니다.
...
```

---

## 🐛 근본 원인 (Root Cause)

### 1차 원인: 파일 형식 불일치
- 부산광역시에서 제공하는 파일이 `.hwpx` 확장자를 가지지만 실제로는 HWP 5.0 (OLE) 형식
- 웹사이트에서 잘못된 확장자로 파일 제공

### 2차 원인: Fallback 로직 미비
- `convertUtil.py:process_hwp_with_fallback()`에서 확장자만 보고 처리 방법 결정
- `.hwpx` 확장자 파일에 대해 `gethwp.read_hwpx()`만 시도
- 실패 시 `gethwp.read_hwp()` 시도 없이 None 반환

### 코드 위치
```python
# src/utils/convertUtil.py, Line ~420
def extract_hwp_text_fallback(hwp_file_path: Path) -> str | None:
    """HWP 파일에서 텍스트 추출을 위한 대체 방법"""

    # HWPX 파일인 경우 직접 처리
    if hwp_file_path.suffix.lower() == ".hwpx":
        try:
            return convert_hwpx_to_text(hwpx_file_path)
        except Exception as e:
            logger.error(f"Fallback HWPX 텍스트 추출 실패: {hwp_file_path.name} - {e}")
            return None  # ❌ 여기서 종료 - read_hwp() 시도 안함!

    # 아래 read_hwp() 코드는 .hwp 파일에만 실행됨
    try:
        import gethwp
        if hwp_file_path.suffix.lower() == ".hwp":  # ❌ .hwpx는 여기 안옴
            extracted_text = gethwp.read_hwp(str(hwp_file_path))
            ...
```

---

## 💡 해결 방안

### 방안 1: 파일 매직 넘버 기반 자동 감지 (권장)

확장자가 아닌 실제 파일 형식을 감지하여 처리:

```python
def extract_hwp_text_fallback(hwp_file_path: Path) -> str | None:
    """HWP 파일에서 텍스트 추출을 위한 대체 방법 (파일 형식 자동 감지)"""

    logger.info(f"Fallback HWP 텍스트 추출 시작: {hwp_file_path.name}")

    # 파일 매직 넘버로 실제 형식 감지
    with open(hwp_file_path, 'rb') as f:
        magic = f.read(4)

    is_zip_based = (magic == b'PK\x03\x04')  # ZIP 기반 HWPX
    is_ole_based = (magic == b'\xd0\xcf\x11\xe0')  # OLE 기반 HWP 5.0

    import gethwp

    # ZIP 기반 HWPX 시도
    if is_zip_based or hwp_file_path.suffix.lower() == ".hwpx":
        try:
            text = gethwp.read_hwpx(str(hwp_file_path))
            if text and text.strip():
                return text.strip()
        except Exception as e:
            logger.warning(f"read_hwpx 실패, read_hwp 시도: {e}")

    # OLE 기반 HWP 5.0 시도 (fallback)
    try:
        text = gethwp.read_hwp(str(hwp_file_path))
        if text and text.strip():
            cleaned_text = clean_hwp_extracted_text(text)
            if len(cleaned_text) >= 10:
                logger.info(f"read_hwp로 텍스트 추출 성공: {hwp_file_path.name} ({len(cleaned_text)}자)")
                return cleaned_text
    except Exception as e:
        logger.error(f"read_hwp 실패: {e}")

    return None
```

### 방안 2: .hwpx에 대한 Fallback 강화

현재 코드에 read_hwp() 시도 추가:

```python
def extract_hwp_text_fallback(hwp_file_path: Path) -> str | None:
    # HWPX 파일인 경우 직접 처리
    if hwp_file_path.suffix.lower() == ".hwpx":
        try:
            return convert_hwpx_to_text(hwpx_file_path)
        except Exception as e:
            logger.error(f"Fallback HWPX 텍스트 추출 실패: {hwp_file_path.name} - {e}")
            # ✅ 실패 시 read_hwp() 시도
            logger.info(f"read_hwp()로 재시도: {hwp_file_path.name}")
            try:
                import gethwp
                text = gethwp.read_hwp(str(hwp_file_path))
                if text and text.strip():
                    cleaned_text = clean_hwp_extracted_text(text)
                    if len(cleaned_text) >= 10:
                        logger.info(f"read_hwp로 추출 성공: {len(cleaned_text)}자")
                        return cleaned_text
            except Exception as e2:
                logger.error(f"read_hwp도 실패: {e2}")
            return None
```

---

## 📊 영향 분석

### 현재 영향
- **6건의 공고**가 텍스트 없이 저장됨
- 모두 **부산광역시 입법예고** 공고
- 처리 상태가 "제외"로 설정됨 (텍스트 없어서 제외 키워드 검사 불가)

### 잠재적 영향
- 부산광역시에서 계속 이런 형식으로 파일 제공 시 지속적 실패 가능
- 다른 지자체에서도 유사한 파일 형식 사용 가능성

---

## ✅ 권장 조치사항

### 즉시 조치 (High Priority)
1. **convertUtil.py 수정**: 방안 1 또는 방안 2 적용
2. **실패한 6건 재처리**: 수정 후 해당 공고 다시 처리

### 중기 조치 (Medium Priority)
1. **파일 형식 감지 로직 개선**: 매직 넘버 기반 자동 감지
2. **모니터링 강화**: HWPX 변환 실패 케이스 별도 알림

### 장기 조치 (Low Priority)
1. **hwp_custom.py 개선**: OLE 형식 HWPX도 처리 가능하도록
2. **부산광역시 담당자 컨택**: 올바른 확장자 사용 요청

---

## 📈 통계 요약

| 항목 | 값 |
|------|-----|
| 총 오류 발생 | 12건 |
| 유니크 파일 수 | 6개 |
| 텍스트 추출 실패 | 6건 (100%) |
| 영향받은 사이트 | prv_busan |
| 공고 날짜 | 2025-11-14 |
| 실패 원인 | 파일 형식 불일치 + Fallback 미비 |

---

## 🔗 관련 파일

- **로그 파일**: `logs/app_error.log.20251122`
- **DB 테이블**: `announcement_pre_processing` (ID: 93369-93374)
- **코드 파일**: `src/utils/convertUtil.py` (Line ~420)
- **테스트 파일**: `tests/입법예고문(부산광역시 교통약자의 이동편의 증진 조례 일부개정조례안).hwpx`

---

**보고서 작성**: 2025-11-24
**작성자**: Claude Code
