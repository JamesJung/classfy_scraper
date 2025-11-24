# 인코딩 자동 복구 시스템 통합 가이드

ftfy를 사용하여 announcement_pre_processing 테이블에 데이터 저장 시 키릴 문자 및 깨진 인코딩을 자동으로 복구하는 시스템입니다.

---

## 📦 설치

### Step 1: ftfy 설치

```bash
pip install ftfy
```

### Step 2: 설치 확인

```bash
python3 -c "import ftfy; print('ftfy version:', ftfy.__version__)"
```

출력 예시:
```
ftfy version: 6.1.3
```

---

## 🔧 통합 방법

### 방법 1: announcement_pre_processor.py 수정 (권장)

`announcement_pre_processor.py`의 DB 저장 부분에 자동 복구 로직 추가

#### 수정 위치 찾기

```bash
grep -n "def.*insert.*db\|INSERT INTO announcement_pre_processing" announcement_pre_processor.py
```

#### 수정 예시

**Before:**
```python
def save_to_database(self, data):
    """DB에 저장"""
    query = """
        INSERT INTO announcement_pre_processing
        (site_code, title, content_md, ...)
        VALUES (%s, %s, %s, ...)
    """

    values = (
        data['site_code'],
        data['title'],  # ← 원본 그대로 저장
        data['content_md'],  # ← 원본 그대로 저장
        ...
    )

    self.cursor.execute(query, values)
```

**After:**
```python
from src.utils.text_encoding_fixer import fix_announcement_data, validate_encoding

def save_to_database(self, data):
    """DB에 저장 (인코딩 자동 복구 포함)"""

    # ✅ 1. 인코딩 자동 복구
    fixed_data = fix_announcement_data(data)

    # ✅ 2. 복구 결과 검증 (선택사항)
    if not validate_encoding(fixed_data.get('title', '')):
        logger.warning(f"제목 인코딩 검증 실패: {fixed_data.get('title', '')[:50]}")

    query = """
        INSERT INTO announcement_pre_processing
        (site_code, title, content_md, ...)
        VALUES (%s, %s, %s, ...)
    """

    values = (
        fixed_data['site_code'],
        fixed_data['title'],  # ← 복구된 텍스트 저장
        fixed_data['content_md'],  # ← 복구된 텍스트 저장
        ...
    )

    self.cursor.execute(query, values)
```

---

### 방법 2: 래퍼 함수 사용 (최소 수정)

기존 코드 수정을 최소화하면서 적용

```python
from src.utils.text_encoding_fixer import auto_fix

def save_to_database(self, data):
    """DB에 저장"""
    query = """
        INSERT INTO announcement_pre_processing
        (site_code, title, content_md, combined_content, ...)
        VALUES (%s, %s, %s, %s, ...)
    """

    values = (
        data['site_code'],
        auto_fix(data.get('title')),  # ← 저장 직전 복구
        auto_fix(data.get('content_md')),  # ← 저장 직전 복구
        auto_fix(data.get('combined_content')),  # ← 저장 직전 복구
        ...
    )

    self.cursor.execute(query, values)
```

---

### 방법 3: UPDATE 쿼리로 기존 데이터 복구

이미 저장된 데이터를 일괄 복구

```python
# fix_existing_data.py

from src.utils.text_encoding_fixer import fix_text_encoding, detect_encoding_issues
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    port=int(os.getenv('DB_PORT')),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)

cursor = conn.cursor(dictionary=True)

# 1. 키릴 문자가 포함된 레코드 찾기
cursor.execute("""
    SELECT id, title, content_md, combined_content
    FROM announcement_pre_processing
    WHERE title REGEXP '[А-Яа-яЁё]'  -- 키릴 문자 패턴
       OR content_md REGEXP '[А-Яа-яЁё]'
    LIMIT 1000
""")

records = cursor.fetchall()
print(f"키릴 문자 포함 레코드: {len(records)}개")

fixed_count = 0

for record in records:
    record_id = record['id']

    # 제목 복구
    original_title = record['title']
    fixed_title = fix_text_encoding(original_title)

    # 내용 복구
    original_content = record['content_md']
    fixed_content = fix_text_encoding(original_content)

    # 변경사항이 있으면 UPDATE
    if fixed_title != original_title or fixed_content != original_content:
        update_query = """
            UPDATE announcement_pre_processing
            SET title = %s,
                content_md = %s,
                combined_content = %s,
                updated_at = NOW()
            WHERE id = %s
        """

        combined = f"{fixed_title}\n\n{fixed_content}" if fixed_content else fixed_title

        cursor.execute(update_query, (
            fixed_title,
            fixed_content,
            combined,
            record_id
        ))

        fixed_count += 1

        print(f"[{record_id}] 복구 완료")
        print(f"  Before: {original_title[:50]}...")
        print(f"  After:  {fixed_title[:50]}...")

conn.commit()
print(f"\n총 {fixed_count}개 레코드 복구 완료")

cursor.close()
conn.close()
```

---

## 📋 실제 통합 코드 예시

### announcement_pre_processor.py에 추가할 코드

```python
# 파일 상단에 import 추가
from src.utils.text_encoding_fixer import (
    fix_announcement_data,
    fix_text_encoding,
    validate_encoding,
    detect_encoding_issues
)

class AnnouncementPreProcessor:

    # ... 기존 코드 ...

    def process_directory_with_custom_name(
        self, directory: Path, site_code: str, folder_name: str, force: bool = False
    ) -> bool:
        """
        개별 공고 디렉토리 처리 (사용자 정의 폴더명 사용)
        """

        # ... 기존 처리 로직 ...

        # 데이터 수집
        announcement_data = {
            'folder_name': folder_name,
            'site_type': self.site_type,
            'site_code': site_code,
            'title': title,
            'content_md': content_md,
            'combined_content': combined_content,
            'attachment_filenames': attachment_filenames,
            'attachment_files_list': json.dumps(attachment_files_list, ensure_ascii=False),
            'announcement_date': announcement_date,
            'origin_url': origin_url,
            'url_key': url_key,
        }

        # ✅ 인코딩 문제 감지 및 자동 복구
        stats = detect_encoding_issues(announcement_data.get('title', ''))
        if stats['cyrillic'] > 0.01 or stats['broken_chars'] > 0.01:
            logger.warning(
                f"인코딩 문제 감지 [{folder_name}] - "
                f"키릴: {stats['cyrillic']:.2%}, "
                f"깨진문자: {stats['broken_chars']:.2%}"
            )

            # 자동 복구 시도
            announcement_data = fix_announcement_data(announcement_data)

            # 복구 후 재검증
            new_stats = detect_encoding_issues(announcement_data.get('title', ''))
            logger.info(
                f"복구 후 상태 [{folder_name}] - "
                f"키릴: {new_stats['cyrillic']:.2%}, "
                f"한글: {new_stats['korean']:.2%}"
            )

        # ✅ DB 저장 전 최종 검증
        if not validate_encoding(announcement_data.get('title', '')):
            logger.error(f"제목 인코딩 복구 실패: {folder_name}")
            # 복구 실패 시 어떻게 할지 결정
            # - 그대로 저장할지
            # - 에러로 처리할지
            # - 별도 테이블에 저장할지

        # DB 저장
        try:
            self.save_announcement(announcement_data)
            return True
        except Exception as e:
            logger.error(f"DB 저장 실패: {e}")
            return False
```

---

## 🔍 테스트 방법

### 1. 단위 테스트

```python
# test_encoding_fixer.py

from src.utils.text_encoding_fixer import (
    fix_text_encoding,
    detect_encoding_issues,
    validate_encoding
)

# 테스트 케이스 1: 키릴 문자 복구
cyrillic_text = "лҸ…мқј көӯм ң"  # 깨진 한글
fixed = fix_text_encoding(cyrillic_text)
print(f"복구 전: {cyrillic_text}")
print(f"복구 후: {fixed}")

# 테스트 케이스 2: 인코딩 문제 감지
text = "정상적인 한글 텍스트"
stats = detect_encoding_issues(text)
print(f"한글: {stats['korean']:.2%}")
print(f"키릴: {stats['cyrillic']:.2%}")

# 테스트 케이스 3: 검증
is_valid = validate_encoding(text)
print(f"검증 결과: {is_valid}")
```

### 2. 통합 테스트

```bash
# keiti 사이트의 녹색금융 공고 재처리 (테스트)
python3 announcement_pre_processor.py \
  -d /home/zium/moabojo/incremental/btp/20251111 \
  --site-code keiti \
  --force

# 로그에서 인코딩 복구 메시지 확인
tail -100 logs/app.log.* | grep "인코딩"
```

### 3. DB 확인

```sql
-- 복구된 데이터 확인
SELECT
    id,
    site_code,
    title,
    CHAR_LENGTH(title) as title_len,
    created_at
FROM announcement_pre_processing
WHERE site_code = 'keiti'
    AND DATE(created_at) = CURDATE()
ORDER BY created_at DESC
LIMIT 10;

-- 키릴 문자 검색 (복구 전)
SELECT
    id,
    site_code,
    title
FROM announcement_pre_processing
WHERE title REGEXP '[А-Яа-яЁё]'  -- 키릴 문자
LIMIT 10;
```

---

## 📊 모니터링

### 인코딩 복구 통계 로그

```python
# announcement_pre_processor.py 끝에 추가

def print_encoding_stats(self):
    """처리 완료 후 인코딩 복구 통계 출력"""
    if hasattr(self, 'encoding_fix_count'):
        print(f"\n{'='*60}")
        print(f"인코딩 복구 통계")
        print(f"{'='*60}")
        print(f"  총 복구 시도: {self.encoding_fix_count}건")
        print(f"  복구 성공: {self.encoding_fix_success}건")
        print(f"  복구 실패: {self.encoding_fix_failed}건")
        print(f"{'='*60}")
```

### 로그 파일 분석

```bash
# 인코딩 복구 관련 로그 추출
grep "인코딩" logs/app.log.* | tail -50

# 키릴 복구 성공 카운트
grep "키릴->한글 복구 성공" logs/app.log.* | wc -l

# ftfy 복구 성공 카운트
grep "ftfy 복구 성공" logs/app.log.* | wc -l
```

---

## ⚠️ 주의사항

### 1. 성능 영향

인코딩 복구는 추가 처리 시간이 필요합니다.

```python
# 선택적 복구: 문제가 감지된 경우에만 복구
stats = detect_encoding_issues(text)
if stats['cyrillic'] > 0.01 or stats['broken_chars'] > 0.01:
    text = fix_text_encoding(text)
```

### 2. 과도한 복구 방지

정상 텍스트를 잘못 복구하는 것을 방지:

```python
# 복구 전후 비교
before_stats = detect_encoding_issues(original)
fixed = fix_text_encoding(original)
after_stats = detect_encoding_issues(fixed)

# 한글이 증가한 경우에만 적용
if after_stats['korean'] > before_stats['korean']:
    return fixed
else:
    return original
```

### 3. 로깅 레벨 조정

대량 처리 시 로그가 너무 많을 수 있음:

```python
import logging

# 개발 환경: DEBUG
logging.basicConfig(level=logging.DEBUG)

# 프로덕션: INFO
logging.basicConfig(level=logging.INFO)

# 로그 최소화: WARNING
logging.basicConfig(level=logging.WARNING)
```

---

## 🚀 배포 가이드

### 1. 개발 환경 테스트

```bash
# ftfy 설치
pip install ftfy

# 테스트 실행
python3 test_encoding_fixer.py

# 단일 사이트 재처리
python3 announcement_pre_processor.py \
  -d /home/zium/moabojo/incremental/btp/20251111 \
  --site-code keiti \
  --force
```

### 2. 프로덕션 배포

```bash
# 1. 원격 서버에 ftfy 설치
ssh zium@server
pip install ftfy

# 2. 코드 배포
git pull origin main

# 3. 테스트 실행
python3 announcement_pre_processor.py \
  -d /home/zium/moabojo/incremental/btp/20251111 \
  --site-code keiti \
  --force

# 4. 로그 확인
tail -100 logs/app.log.* | grep "인코딩\|키릴\|ftfy"

# 5. DB 확인
mysql -h 192.168.0.95 -u root -p -P3309 subvention -e "
SELECT title FROM announcement_pre_processing
WHERE site_code = 'keiti'
AND DATE(created_at) = CURDATE()
LIMIT 5;
"
```

### 3. 기존 데이터 일괄 복구

```bash
# fix_existing_data.py 실행
python3 fix_existing_data.py

# 진행 상황 모니터링
tail -f logs/encoding_fix.log
```

---

## 📝 체크리스트

### 배포 전

- [ ] ftfy 설치 확인
- [ ] text_encoding_fixer.py 배포
- [ ] announcement_pre_processor.py 수정
- [ ] 단위 테스트 통과
- [ ] 통합 테스트 통과

### 배포 후

- [ ] 인코딩 복구 로그 확인
- [ ] DB 데이터 샘플 확인
- [ ] 성능 영향 모니터링
- [ ] 에러 로그 확인

---

## 🎯 예상 결과

### Before (복구 전)

```
title: "лҸ…мқј көӯм ң көҮҮ..."  (키릴 문자)
content: "м�мҹү�Ү�ѕөӯ..."  (깨진 문자)
```

### After (복구 후)

```
title: "독일 조명 및 공연장 전문가 초청..."  (정상 한글)
content: "2025년 글로벌 녹색금융 컨퍼런스..."  (정상 한글)
```

---

**작성일**: 2025-11-18
**버전**: 1.0
**필요 패키지**: `ftfy>=6.0.0`
