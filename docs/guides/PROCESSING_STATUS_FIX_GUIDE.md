# Processing Status 수정 가이드

## 개요
announcement_pre_processing 테이블의 processing_status 필드에 잘못된 'success' 값이 입력되어 있는 문제를 수정하는 가이드입니다.

## 문제 상황
- **현재**: processing_status = 'success' (영문)
- **정상**: processing_status = '성공' (한글)

## 수정 내용

### 1. 코드 수정 완료 ✓

#### reprocess_with_exclusion_keywords.py
```python
# Before
WHERE processing_status = 'success'

# After
WHERE processing_status = '성공'
```

**수정 라인**: 73, 77번째 줄

### 2. 데이터베이스 수정 필요

#### 방법 1: SQL 스크립트 실행 (권장)

```bash
# 로컬 DB
mysql -u root -P 3306 subvention_local < fix_processing_status_success_to_korean.sql

# 운영 DB (주의!)
source .env
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD -P $DB_PORT $DB_NAME < fix_processing_status_success_to_korean.sql
```

#### 방법 2: Python 스크립트로 실행

스크립트를 만들어 실행할 수도 있습니다:

```python
#!/usr/bin/env python3
"""
Processing Status 'success' → '성공' 변경 스크립트
"""
import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

conn = pymysql.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", 3306)),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    charset="utf8mb4"
)

try:
    with conn.cursor() as cursor:
        # 현재 상태 확인
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM announcement_pre_processing
            WHERE processing_status = 'success'
        """)
        count = cursor.fetchone()[0]
        print(f"변경 대상: {count:,}개")

        if count > 0:
            # 업데이트 실행
            cursor.execute("""
                UPDATE announcement_pre_processing
                SET processing_status = '성공',
                    updated_at = NOW()
                WHERE processing_status = 'success'
            """)
            conn.commit()
            print(f"✓ {cursor.rowcount:,}개 레코드 업데이트 완료")
        else:
            print("✓ 변경할 레코드가 없습니다.")

        # 검증
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM announcement_pre_processing
            WHERE processing_status = 'success'
        """)
        remaining = cursor.fetchone()[0]

        if remaining == 0:
            print("✓ 모든 'success' 값이 '성공'으로 변경되었습니다.")
        else:
            print(f"⚠️ {remaining}개의 'success' 값이 남아있습니다.")

finally:
    conn.close()
```

#### 방법 3: 직접 SQL 실행

최소한의 SQL 명령만 실행하려면:

```sql
-- 1. 현재 상태 확인
SELECT processing_status, COUNT(*) as count
FROM announcement_pre_processing
GROUP BY processing_status;

-- 2. 'success' 개수 확인
SELECT COUNT(*) FROM announcement_pre_processing WHERE processing_status = 'success';

-- 3. 업데이트 실행
UPDATE announcement_pre_processing
SET processing_status = '성공', updated_at = NOW()
WHERE processing_status = 'success';

-- 4. 검증
SELECT COUNT(*) FROM announcement_pre_processing WHERE processing_status = 'success';
-- 결과가 0이어야 함
```

## 실행 순서

### STEP 1: 백업 (선택사항, 권장)
```sql
CREATE TABLE announcement_pre_processing_backup_20251105
SELECT * FROM announcement_pre_processing
WHERE processing_status = 'success';
```

### STEP 2: SQL 스크립트 실행
```bash
mysql -u root -P 3306 subvention_local < fix_processing_status_success_to_korean.sql
```

### STEP 3: 검증
```sql
-- 'success' 값이 남아있는지 확인
SELECT COUNT(*) FROM announcement_pre_processing WHERE processing_status = 'success';
-- 결과: 0

-- 전체 분포 확인
SELECT processing_status, COUNT(*) as count
FROM announcement_pre_processing
GROUP BY processing_status
ORDER BY count DESC;
```

### STEP 4: 테스트
```bash
# reprocess_with_exclusion_keywords.py 실행 테스트
python3 reprocess_with_exclusion_keywords.py
```

## 예상 결과

### 수정 전
```
processing_status  | count
-------------------|-------
success            | 12,345
제외               | 5,678
error              | 1,234
```

### 수정 후
```
processing_status  | count
-------------------|-------
성공               | 12,345
제외               | 5,678
error              | 1,234
```

## 주의사항

1. **운영 DB 수정 시 주의**
   - 반드시 백업 수행
   - 점검 시간에 실행 권장
   - 롤백 계획 수립

2. **다른 테이블은 변경 안 함**
   - `scraper_execution_log.status`는 'success' 사용 (정상)
   - `api_url_processing_log.processing_status`는 영문 사용 (정상)

3. **코드 변경사항 배포**
   - reprocess_with_exclusion_keywords.py 배포 필요
   - 운영 서버에 적용 필요

## 재발 방지

### 향후 개선사항
1. **상수 정의 사용 권장**
   ```python
   # constants.py
   class ProcessingStatus:
       SUCCESS = "성공"
       EXCLUDED = "제외"
       ERROR = "error"
   ```

2. **타입 체크 추가**
   ```python
   ALLOWED_PROCESSING_STATUS = ["성공", "제외", "error"]

   def validate_processing_status(status: str):
       if status not in ALLOWED_PROCESSING_STATUS:
           raise ValueError(f"Invalid processing_status: {status}")
   ```

3. **데이터베이스 제약조건**
   ```sql
   ALTER TABLE announcement_pre_processing
   ADD CONSTRAINT chk_processing_status
   CHECK (processing_status IN ('성공', '제외', 'error'));
   ```

## 관련 문서
- PROCESSING_STATUS_SUCCESS_ANALYSIS.md: 상세 분석 보고서
- fix_processing_status_success_to_korean.sql: 실행 SQL 스크립트

## 문의
문제 발생 시 개발팀에 문의하세요.
