# grantProjectNoticeBatcher에 url_key_hash 구현 가이드

**작성일**: 2025-10-30
**목적**: grantProjectNoticeBatcher에서 INSERT 시 url_key, url_key_hash 생성

---

## 📊 현재 상황

### **grantProjectNoticeBatcher의 INSERT 로직**

**파일**: `/mnt/d/workspace/sources/grantProjectNoticeBatcher/src/db/registry.js`

**현재 코드** (line 18-31):
```javascript
const [result] = await pool.execute(
  `INSERT INTO api_url_registry
   (site_code, site_name, scrap_url, announcement_url, announcement_id,
    title, post_date, status, folder_name, has_attachments, attachment_count, retry_count)
   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, 0, 0, 0)
   ON DUPLICATE KEY UPDATE
     title = VALUES(title),
     scrap_url = VALUES(scrap_url),
     announcement_url = VALUES(announcement_url),
     post_date = VALUES(post_date),
     folder_name = VALUES(folder_name),
     update_at = CURRENT_TIMESTAMP`,
  [siteCode, siteName, scrapUrl, announcementUrl, announcementId, title, postDate, folderName]
);
```

**문제점**:
- ❌ url_key 없음
- ❌ url_key_hash 없음
- ❌ announcement_pre_processor.py와 매칭 실패 원인

---

## ✅ 구현 방안

### **1단계: DB 스키마 변경**

```sql
-- api_url_registry 테이블에 컬럼 추가
ALTER TABLE api_url_registry
ADD COLUMN url_key VARCHAR(500) COMMENT '정규화된 URL (domain|path|params)',
ADD COLUMN url_key_hash CHAR(32) AS (MD5(url_key)) STORED COMMENT '자동 생성 해시',
ADD INDEX idx_url_key (url_key),
ADD INDEX idx_url_key_hash (url_key_hash);
```

**실행 방법**:
```bash
python3 -c "
import pymysql
from dotenv import load_dotenv
import os

load_dotenv()

conn = pymysql.connect(
    host=os.getenv('DB_HOST'),
    port=int(os.getenv('DB_PORT', 3306)),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME'),
    charset='utf8mb4'
)

cursor = conn.cursor()

# url_key 컬럼 추가
print('1. url_key 컬럼 추가...')
cursor.execute('''
    ALTER TABLE api_url_registry
    ADD COLUMN url_key VARCHAR(500) COMMENT '정규화된 URL'
''')
conn.commit()
print('✅ url_key 컬럼 추가 완료')

# url_key_hash Generated Column 추가
print('\\n2. url_key_hash Generated Column 추가...')
cursor.execute('''
    ALTER TABLE api_url_registry
    ADD COLUMN url_key_hash CHAR(32) AS (MD5(url_key)) STORED COMMENT '자동 생성 해시',
    ADD INDEX idx_url_key (url_key),
    ADD INDEX idx_url_key_hash (url_key_hash)
''')
conn.commit()
print('✅ url_key_hash Generated Column 추가 완료')

cursor.close()
conn.close()

print('\\n✅ 스키마 변경 완료!')
"
```

---

### **2단계: DomainKeyExtractor 로직을 JavaScript로 포팅**

#### **방안 A: Python 스크립트 호출** (간단, 권장)

**새 파일 생성**: `/mnt/d/workspace/sources/grantProjectNoticeBatcher/src/utils/urlKeyExtractor.js`

```javascript
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// classfy_scraper의 DomainKeyExtractor 사용
const PYTHON_SCRIPT_PATH = path.join(__dirname, '../../../../classfy_scraper/extract_url_key.py');

/**
 * URL을 정규화된 url_key로 변환
 * @param {string} url - 원본 URL
 * @param {string} siteCode - 사이트 코드 (bizInfo, kStartUp, smes24)
 * @returns {Promise<string|null>} - 정규화된 url_key (예: "www.bizinfo.go.kr|/notice|id=123&page=1")
 */
export async function extractUrlKey(url, siteCode) {
  return new Promise((resolve, reject) => {
    const python = spawn('python3', [PYTHON_SCRIPT_PATH, url, siteCode]);

    let output = '';
    let errorOutput = '';

    python.stdout.on('data', (data) => {
      output += data.toString();
    });

    python.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    python.on('close', (code) => {
      if (code !== 0) {
        console.error(`Python script failed: ${errorOutput}`);
        resolve(null);  // 실패 시 null 반환
        return;
      }

      const urlKey = output.trim();
      resolve(urlKey || null);
    });

    python.on('error', (err) => {
      console.error(`Failed to execute Python script: ${err.message}`);
      resolve(null);
    });
  });
}

export default {
  extractUrlKey,
};
```

**Python 스크립트 생성**: `/mnt/d/workspace/sources/classfy_scraper/extract_url_key.py`

```python
#!/usr/bin/env python3
"""
URL을 정규화된 url_key로 변환하는 스크립트
grantProjectNoticeBatcher에서 호출용
"""

import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.domainKeyExtractor import DomainKeyExtractor

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 extract_url_key.py <url> <site_code>", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    site_code = sys.argv[2]

    try:
        extractor = DomainKeyExtractor()
        url_key = extractor.extract_url_key(url, site_code)

        if url_key:
            print(url_key)
        else:
            print("", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
```

**장점**:
- ✅ Python 코드 재사용 (DomainKeyExtractor 그대로 사용)
- ✅ 로직 일치 보장
- ✅ 유지보수 용이 (한 곳만 수정)

**단점**:
- ⚠️ Python 프로세스 생성 오버헤드 (하지만 INSERT는 비교적 드묾)

---

#### **방안 B: JavaScript로 순수 구현** (복잡)

**새 파일 생성**: `/mnt/d/workspace/sources/grantProjectNoticeBatcher/src/utils/urlKeyExtractor.js`

```javascript
import { URL } from 'url';
import crypto from 'crypto';
import mysql from 'mysql2/promise';
import { getPool } from '../db/connection.js';

/**
 * domain_key_config에서 설정 조회
 */
async function getDomainKeyConfig(domain) {
  const pool = getPool();
  const [rows] = await pool.execute(
    'SELECT url_key_1, url_key_2, url_key_3, path_pattern FROM domain_key_config WHERE domain = ?',
    [domain]
  );
  return rows.length > 0 ? rows[0] : null;
}

/**
 * URL을 정규화된 url_key로 변환
 */
export async function extractUrlKey(urlString, siteCode) {
  try {
    const url = new URL(urlString);
    let domain = url.hostname.toLowerCase();

    // www. 제거
    if (domain.startsWith('www.')) {
      domain = domain.substring(4);
    }

    // domain_key_config 조회
    const config = await getDomainKeyConfig(domain);

    if (!config) {
      // fallback: 전체 URL 사용
      return urlString;
    }

    // path 정규화
    let path = url.pathname;

    // path_pattern 적용 (정규식)
    if (config.path_pattern) {
      const match = path.match(new RegExp(config.path_pattern));
      if (match && match[1]) {
        path = match[1];
      }
    }

    // 쿼리 파라미터 정규화
    const params = new URLSearchParams(url.search);
    const sortedParams = [];

    // url_key_1, url_key_2, url_key_3 순서로 추출
    for (const key of [config.url_key_1, config.url_key_2, config.url_key_3]) {
      if (key && params.has(key)) {
        sortedParams.push(`${key}=${params.get(key)}`);
      }
    }

    // url_key 조립
    const urlKey = `${domain}|${path}|${sortedParams.join('&')}`;

    return urlKey;
  } catch (error) {
    console.error(`Failed to extract url_key: ${error.message}`);
    return null;
  }
}

export default {
  extractUrlKey,
};
```

**장점**:
- ✅ Python 의존성 없음
- ✅ Node.js 네이티브 실행

**단점**:
- ⚠️ Python 코드와 동기화 필요 (유지보수 부담)
- ⚠️ 로직 불일치 위험

---

### **권장: 방안 A (Python 스크립트 호출)**

이유:
- ✅ 로직 일치 보장 (DomainKeyExtractor 직접 사용)
- ✅ 유지보수 용이
- ✅ INSERT는 배치 작업이라 성능 영향 적음

---

### **3단계: registry.js 수정**

#### **insertRegistry() 함수 수정**

**파일**: `/mnt/d/workspace/sources/grantProjectNoticeBatcher/src/db/registry.js`

```javascript
import { getPool } from './connection.js';
import logger from '../utils/logger.js';
import { extractUrlKey } from '../utils/urlKeyExtractor.js';  // 🆕 추가

export async function insertRegistry(data) {
  const pool = getPool();
  const {
    siteCode,
    siteName,
    scrapUrl,
    announcementUrl,
    announcementId,
    title,
    postDate,
    folderName,
  } = data;

  try {
    // 🆕 url_key 생성
    let urlKey = null;
    const targetUrl = siteCode === 'kStartUp' ? scrapUrl : announcementUrl;

    if (targetUrl) {
      urlKey = await extractUrlKey(targetUrl, siteCode);

      if (urlKey) {
        logger.verbose(`URL key extracted: ${siteCode}/${announcementId}`, {
          url: targetUrl.substring(0, 50),
          urlKey: urlKey.substring(0, 50),
        });
      } else {
        logger.warn(`Failed to extract URL key: ${siteCode}/${announcementId}`, {
          url: targetUrl.substring(0, 50),
        });
      }
    }

    // 🆕 SQL 수정: url_key 컬럼 추가 (url_key_hash는 Generated Column이라 자동 생성)
    const [result] = await pool.execute(
      `INSERT INTO api_url_registry
       (site_code, site_name, scrap_url, announcement_url, announcement_id,
        title, post_date, status, folder_name, url_key, has_attachments, attachment_count, retry_count)
       VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, 0, 0, 0)
       ON DUPLICATE KEY UPDATE
         title = VALUES(title),
         scrap_url = VALUES(scrap_url),
         announcement_url = VALUES(announcement_url),
         post_date = VALUES(post_date),
         folder_name = VALUES(folder_name),
         url_key = VALUES(url_key),
         update_at = CURRENT_TIMESTAMP`,
      [siteCode, siteName, scrapUrl, announcementUrl, announcementId, title, postDate, folderName, urlKey]
    );

    logger.verbose(`Registry inserted/updated: ${siteCode}/${announcementId}`, {
      insertId: result.insertId,
      affectedRows: result.affectedRows,
      urlKey: urlKey ? urlKey.substring(0, 30) : null,
    });

    return result.insertId || (await getRegistryId(siteCode, announcementId));
  } catch (error) {
    logger.error(`Failed to insert registry: ${siteCode}/${announcementId}`, error);
    throw error;
  }
}
```

**변경 사항**:
1. ✅ `extractUrlKey` import
2. ✅ url_key 생성 (kStartUp은 scrapUrl, 나머지는 announcementUrl)
3. ✅ INSERT 쿼리에 `url_key` 컬럼 추가
4. ✅ ON DUPLICATE KEY UPDATE에도 `url_key = VALUES(url_key)` 추가
5. ✅ url_key_hash는 Generated Column이라 자동 생성 (신경 안 써도 됨)

---

#### **bulkInsertRegistry() 함수 수정** (선택)

**파일**: `/mnt/d/workspace/sources/grantProjectNoticeBatcher/src/db/registry.js`

```javascript
export async function bulkInsertRegistry(items) {
  const pool = getPool();

  if (!items || items.length === 0) {
    return [];
  }

  try {
    // 🆕 모든 item에 대해 url_key 생성
    const itemsWithUrlKey = await Promise.all(
      items.map(async (item) => {
        const targetUrl = item.siteCode === 'kStartUp' ? item.scrapUrl : item.announcementUrl;
        const urlKey = targetUrl ? await extractUrlKey(targetUrl, item.siteCode) : null;

        return {
          ...item,
          urlKey,
        };
      })
    );

    const values = [];
    const params = [];

    for (const item of itemsWithUrlKey) {
      values.push('(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)');  // url_key 자리 추가
      params.push(
        item.siteCode,
        item.siteName,
        item.scrapUrl,
        item.announcementUrl,
        item.announcementId,
        item.title,
        item.postDate,
        'pending',
        item.folderName,
        item.urlKey  // 🆕 추가
      );
    }

    const sql = `INSERT INTO api_url_registry
      (site_code, site_name, scrap_url, announcement_url, announcement_id,
       title, post_date, status, folder_name, url_key, has_attachments, attachment_count, retry_count)
      VALUES ${values.join(', ')}
      ON DUPLICATE KEY UPDATE
        title = VALUES(title),
        scrap_url = VALUES(scrap_url),
        announcement_url = VALUES(announcement_url),
        post_date = VALUES(post_date),
        folder_name = VALUES(folder_name),
        url_key = VALUES(url_key),
        update_at = CURRENT_TIMESTAMP`;

    const [result] = await pool.execute(sql, params);

    logger.info(`Bulk inserted ${items.length} items with url_key`, {
      insertedRows: result.affectedRows,
    });

    const insertedIds = [];
    for (const item of items) {
      const id = await getRegistryId(item.siteCode, item.announcementId);
      if (id) {
        insertedIds.push({ announcementId: item.announcementId, id });
      }
    }

    return insertedIds;
  } catch (error) {
    logger.error('Failed to bulk insert registry', error);
    throw error;
  }
}
```

---

## 🧪 테스트 방법

### **1. Python 스크립트 단독 테스트**

```bash
cd /mnt/d/workspace/sources/classfy_scraper

# bizInfo 테스트
python3 extract_url_key.py "https://www.bizinfo.go.kr/notice?page=1&id=123" "bizInfo"
# 예상 출력: www.bizinfo.go.kr|/notice|id=123&page=1

# kStartUp 테스트
python3 extract_url_key.py "https://www.k-startup.go.kr/web/contents/bizNotice_view.do?schM=view&pbancSn=999" "kStartUp"
# 예상 출력: www.k-startup.go.kr|/web/contents/bizNotice_view.do|pbancSn=999
```

---

### **2. Node.js에서 호출 테스트**

```javascript
// test.js
import { extractUrlKey } from './src/utils/urlKeyExtractor.js';

(async () => {
  const urlKey1 = await extractUrlKey(
    'https://www.bizinfo.go.kr/notice?page=1&id=123',
    'bizInfo'
  );
  console.log('bizInfo url_key:', urlKey1);

  const urlKey2 = await extractUrlKey(
    'https://www.k-startup.go.kr/web/contents/bizNotice_view.do?schM=view&pbancSn=999',
    'kStartUp'
  );
  console.log('kStartUp url_key:', urlKey2);
})();
```

```bash
cd /mnt/d/workspace/sources/grantProjectNoticeBatcher
node test.js
```

---

### **3. 실제 INSERT 테스트**

```javascript
// test-insert.js
import { insertRegistry } from './src/db/registry.js';

(async () => {
  const result = await insertRegistry({
    siteCode: 'bizInfo',
    siteName: '중소벤처기업부',
    scrapUrl: null,
    announcementUrl: 'https://www.bizinfo.go.kr/notice?id=TEST123&page=1',
    announcementId: 'TEST123',
    title: '테스트 공고',
    postDate: '2025-10-30',
    folderName: 'test_folder',
  });

  console.log('Insert result:', result);
})();
```

```bash
node test-insert.js
```

---

### **4. DB 확인**

```sql
-- INSERT 후 url_key, url_key_hash 확인
SELECT
    id,
    site_code,
    announcement_id,
    LEFT(announcement_url, 50) as url,
    LEFT(url_key, 50) as url_key,
    url_key_hash
FROM api_url_registry
WHERE announcement_id = 'TEST123';
```

**예상 결과**:
```
id  | site_code | announcement_id | url                                             | url_key                                         | url_key_hash
----|-----------|-----------------|------------------------------------------------|------------------------------------------------|------------------
123 | bizInfo   | TEST123         | https://www.bizinfo.go.kr/notice?id=TEST123... | bizinfo.go.kr|/notice|id=TEST123&page=1       | a1b2c3d4e5f6...
```

**url_key_hash는 자동 생성됨!** (Generated Column)

---

## 📊 예상 효과

### **Before (현재)**

```
[grantProjectNoticeBatcher]
  INSERT INTO api_url_registry (
    announcement_url = "https://www.bizinfo.go.kr/notice?id=123&page=1",
    url_key = NULL,
    url_key_hash = NULL
  )

[announcement_pre_processor.py]
  origin_url = "https://www.bizinfo.go.kr/notice?page=1&id=123"  # 파라미터 순서 다름
  url_key_hash = "abc123..."

  WHERE url_key_hash = "abc123..."  # ← NULL이라 매칭 실패
  WHERE announcement_url = origin_url  # ← 파라미터 순서 달라 매칭 실패

  → preprocessing_id 업데이트 실패 ❌
```

---

### **After (개선 후)**

```
[grantProjectNoticeBatcher]
  url_key = extractUrlKey("https://www.bizinfo.go.kr/notice?id=123&page=1")
           → "www.bizinfo.go.kr|/notice|id=123&page=1"

  INSERT INTO api_url_registry (
    announcement_url = "https://www.bizinfo.go.kr/notice?id=123&page=1",
    url_key = "www.bizinfo.go.kr|/notice|id=123&page=1",
    url_key_hash = "abc123..."  # Generated Column이 자동 생성
  )

[announcement_pre_processor.py]
  origin_url = "https://www.bizinfo.go.kr/notice?page=1&id=123"  # 파라미터 순서 다름
  url_key = extractUrlKey(origin_url)
          → "www.bizinfo.go.kr|/notice|id=123&page=1"  # 정규화되어 동일!
  url_key_hash = MD5(url_key)
               → "abc123..."  # 동일한 해시!

  WHERE url_key_hash = "abc123..."  # ✅ 매칭 성공!
  SET preprocessing_id = 12345

  → preprocessing_id 업데이트 성공 ✅
```

**매칭률**: 60-70% → **90-95%** (+20-30%p 향상 예상)

---

## ✅ 구현 체크리스트

### **필수 작업**

- [ ] **1. DB 스키마 변경**
  ```sql
  ALTER TABLE api_url_registry
  ADD COLUMN url_key VARCHAR(500),
  ADD COLUMN url_key_hash CHAR(32) AS (MD5(url_key)) STORED,
  ADD INDEX idx_url_key (url_key),
  ADD INDEX idx_url_key_hash (url_key_hash);
  ```

- [ ] **2. Python 스크립트 생성**
  - `/mnt/d/workspace/sources/classfy_scraper/extract_url_key.py`

- [ ] **3. JavaScript 유틸 생성**
  - `/mnt/d/workspace/sources/grantProjectNoticeBatcher/src/utils/urlKeyExtractor.js`

- [ ] **4. registry.js 수정**
  - `insertRegistry()` 함수 수정
  - `bulkInsertRegistry()` 함수 수정 (선택)

- [ ] **5. 테스트**
  - Python 스크립트 단독 테스트
  - Node.js 호출 테스트
  - INSERT 테스트
  - DB 확인

### **선택 작업**

- [ ] **6. 기존 데이터 마이그레이션**
  ```sql
  -- 기존 19,526개 레코드의 url_key 채우기
  -- (announcement_pre_processor.py가 채워줄 수도 있지만, 한 번에 처리 가능)
  ```

- [ ] **7. 모니터링 추가**
  - url_key 생성 성공/실패 로그
  - url_key_hash 매칭률 추적

---

## 🎯 최종 정리

### **변경 사항 요약**

| 컴포넌트 | 변경 내용 | 목적 |
|---------|----------|------|
| **api_url_registry 테이블** | url_key, url_key_hash 컬럼 추가 | 정규화된 URL 저장 |
| **extract_url_key.py** | Python 스크립트 생성 | DomainKeyExtractor 재사용 |
| **urlKeyExtractor.js** | Node.js 유틸 생성 | Python 스크립트 호출 |
| **registry.js** | insertRegistry 수정 | url_key 생성 및 INSERT |

### **효과**

- ✅ INSERT 시점부터 url_key_hash 생성
- ✅ announcement_pre_processor.py 즉시 매칭 성공
- ✅ 매칭률 60-70% → 90-95% 향상
- ✅ preprocessing_id 업데이트 성공률 대폭 증가

---

**다음 단계: 위 체크리스트 순서대로 구현**
