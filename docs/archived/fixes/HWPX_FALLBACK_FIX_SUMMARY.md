# HWPX Fallback 로직 수정 완료 보고서

**작업 일시**: 2025-11-24
**수정 파일**:
- `src/utils/convertUtil.py`
- `src/utils/hwp_custom.py`

---

## 📋 문제 요약

### 발견된 문제
1. **OLE 형식 HWPX 파일 처리 실패**
   - 확장자는 `.hwpx`이지만 실제로는 HWP 5.0 (OLE) 형식인 파일들
   - ZIP 기반 HWPX 처리 함수(`gethwp.read_hwpx()`)가 실패
   - Fallback 로직이 작동하지 않아 텍스트 추출 완전 실패

2. **부적절한 에러 로깅**
   - 최종적으로 성공했음에도 ERROR 로그가 남음
   - `app_error.log`에 불필요한 오류 기록

### 영향 범위
- **실패 건수**: 6건 (부산광역시 입법예고 공고)
- **DB 상태**: `combined_content` = EMPTY (0자)
- **처리 상태**: "제외"로 잘못 설정됨

---

## 🔧 수정 내용

### 1. Fallback 로직 구현 (`convertUtil.py:3065-3085`)

#### 수정 전
```python
if hwp_file_path.suffix.lower() == ".hwpx":
    try:
        return convert_hwpx_to_text(hwp_file_path)
    except Exception as e:  # ❌ 예외가 발생하지 않아서 실행 안됨
        logger.error(f"Fallback HWPX 텍스트 추출 실패: {hwp_file_path.name} - {e}")
        return None
```

**문제점**: `convert_hwpx_to_text()`가 예외를 던지지 않고 `None`을 반환하므로 `except` 블록이 실행되지 않음

#### 수정 후
```python
if hwp_file_path.suffix.lower() == ".hwpx":
    result = convert_hwpx_to_text(hwp_file_path)

    # ✅ None 반환 체크로 변경
    if result is None:
        logger.info(f"gethwp.read_hwp()로 재시도 (OLE 형식 HWPX 가능성): {hwp_file_path.name}")
        try:
            import gethwp
            text = gethwp.read_hwp(str(hwp_file_path))
            if text and text.strip():
                cleaned_text = clean_hwp_extracted_text(text)
                if len(cleaned_text) >= 10:
                    logger.info(f"✅ read_hwp()로 HWPX 추출 성공: {hwp_file_path.name} ({len(cleaned_text)}자)")
                    return cleaned_text
        except Exception as e:
            logger.error(f"read_hwp()로도 HWPX 추출 실패: {hwp_file_path.name} - {e}")
    else:
        return result

    return None
```

**개선점**:
- `None` 반환을 체크하여 fallback 로직 실행
- OLE 형식 HWPX도 `gethwp.read_hwp()`로 처리 가능
- 명확한 로깅으로 처리 과정 추적 가능

---

### 2. 로그 레벨 조정

#### (1) `convertUtil.py:2941-2945`

**수정 전**:
```python
except Exception as e:
    logger.error(f"HWPX 파일 '{hwpx_file_path.name}' 텍스트 추출 중 오류 발생: {e}")
    logger.debug(f"HWPX 텍스트 추출 오류 상세: {traceback.format_exc()}")
    return None
```

**수정 후**:
```python
except Exception as e:
    # ZIP 형식이 아닌 경우 fallback으로 처리 가능하므로 WARNING으로 낮춤
    logger.warning(f"HWPX 파일 '{hwpx_file_path.name}' 텍스트 추출 실패 (fallback 시도 예정): {e}")
    logger.debug(f"HWPX 텍스트 추출 오류 상세: {traceback.format_exc()}")
    return None
```

**효과**: ERROR → WARNING으로 변경, fallback 시도 예정임을 명시

#### (2) `hwp_custom.py:114-117`

**수정 전**:
```python
except zipfile.BadZipFile:
    logger.error(f"유효하지 않은 ZIP 파일 (HWPX): {hwpx_file_path.name}")
    raise Exception(f"Invalid HWPX file format: {hwpx_file_path.name}")
```

**수정 후**:
```python
except zipfile.BadZipFile:
    # ZIP 형식이 아닌 HWPX는 OLE 형식일 수 있으므로 DEBUG로 기록
    logger.debug(f"ZIP 형식이 아닌 HWPX (OLE 형식 가능성): {hwpx_file_path.name}")
    raise Exception(f"Invalid HWPX file format: {hwpx_file_path.name}")
```

**효과**: ERROR → DEBUG으로 변경, `app_error.log`에 기록 안됨

---

## ✅ 테스트 결과

### 테스트 파일
```
tests/입법예고문(부산광역시 교통약자의 이동편의 증진 조례 일부개정조례안).hwpx
파일 크기: 50,688 bytes
파일 형식: HWP 5.0 (OLE), 매직 넘버 = d0cf11e0
```

### 실행 결과
```
✅ 텍스트 추출 성공!
추출된 텍스트 길이: 5,244자
```

### 로그 출력
```
2025-11-24 10:28:13,048 - WARNING - HWPX 파일 '...' 텍스트 추출 실패 (fallback 시도 예정): Invalid HWPX file format
2025-11-24 10:28:13,077 - INFO - gethwp.read_hwp()로 재시도 (OLE 형식 HWPX 가능성): ...
2025-11-24 10:28:13,111 - INFO - ✅ read_hwp()로 HWPX 추출 성공: ... (5244자)
```

### Error Log 확인
✅ **최종 성공 시 `app_error.log`에 새로운 ERROR 기록 없음**

---

## 📊 처리 흐름

### 수정 전
```
.hwpx 파일 발견
  ↓
gethwp.read_hwpx() 시도
  ↓
❌ BadZipFile 예외 (OLE 형식)
  ↓
convert_hwpx_to_text() → None 반환
  ↓
extract_hwp_text_fallback() → None 반환
  ↓
❌ 텍스트 추출 실패
```

### 수정 후
```
.hwpx 파일 발견
  ↓
gethwp.read_hwpx() 시도
  ↓
⚠️ BadZipFile 예외 (OLE 형식) - DEBUG 로그
  ↓
convert_hwpx_to_text() → None 반환 - WARNING 로그
  ↓
extract_hwp_text_fallback()에서 None 감지
  ↓
✅ gethwp.read_hwp() 재시도 - INFO 로그
  ↓
✅ 텍스트 추출 성공 (5,244자) - INFO 로그
```

---

## 🎯 개선 효과

### 1. 기능 개선
- ✅ OLE 형식 HWPX 파일 정상 처리
- ✅ Fallback 메커니즘 정상 작동
- ✅ 텍스트 추출 성공률 향상

### 2. 로그 품질 개선
- ✅ 최종 성공 시 ERROR 로그 제거
- ✅ 처리 과정 명확하게 추적 가능
- ✅ 불필요한 알림 감소

### 3. 운영 효율성
- ✅ 실제 문제와 임시 실패 구분 가능
- ✅ `app_error.log` 노이즈 감소
- ✅ 모니터링 정확도 향상

---

## 📝 향후 조치사항

### 즉시 조치
- [ ] 실패한 6건의 부산광역시 공고 재처리
- [ ] DB 업데이트 확인 (combined_content, processing_status)

### 모니터링
- [ ] 향후 HWPX 파일 처리 성공률 모니터링
- [ ] 다른 지자체에서 유사한 파일 형식 발생 여부 확인

### 장기 개선
- [ ] 파일 매직 넘버 기반 자동 형식 감지 구현 고려
- [ ] HWPX 변환 성공/실패 통계 수집

---

## 📌 관련 파일

- **수정 파일**:
  - `src/utils/convertUtil.py` (Line 2941-2945, 3065-3085)
  - `src/utils/hwp_custom.py` (Line 114-117)

- **테스트 파일**:
  - `test_fixed_hwpx.py`
  - `test_hwpx_conversion.py`
  - `test_gethwp_hwpx.py`

- **분석 보고서**:
  - `ZIP_ERROR_ANALYSIS_REPORT.md`
  - `analyze_zip_errors.py`

---

**작성자**: Claude Code
**작성일**: 2025-11-24
**상태**: ✅ 수정 완료 및 테스트 검증 완료
