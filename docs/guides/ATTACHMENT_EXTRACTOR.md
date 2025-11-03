# 첨부파일 Extractor 관리 가이드

## 📋 개요

첨부파일 추출 로직을 외부 파일(`attachment_extractors.js`)로 분리하여 관리합니다.

## 🎯 장점

1. **유지보수 용이**: 각 사이트별 로직이 함수로 분리되어 있어 수정이 쉬움
2. **확장성**: 새로운 사이트 추가시 extractor 함수만 추가하면 됨
3. **재사용성**: 동일한 구조의 다른 사이트에서 extractor 재사용 가능
4. **가독성**: 하드코딩된 if-else 대신 명확한 함수명으로 구분

---

## 📂 파일 구조

```
node/
├── homepage_gosi_detail_downloader.js  # 메인 다운로더
├── attachment_extractors.js            # Extractor 함수 모음 (NEW!)
└── configs/
    ├── anyang.json                     # anyang 설정
    ├── boeun.json                      # boeun 설정
    └── ...
```

---

## 🔧 사용법

### 1. Config JSON 설정

#### Type 1: Custom Extractor (복잡한 DOM 조작)
```json
{
  "selectors": {
    "detail": {
      "attachments": {
        "type": "custom",
        "extractorName": "anyang_complex",
        "selector": "td ul li"
      }
    }
  }
}
```

#### Type 2: JavaScript 함수 호출
```json
{
  "selectors": {
    "detail": {
      "attachments": {
        "type": "javascript",
        "selector": "a[href*='goDownload']",
        "downloadFunction": "goDownload"
      }
    }
  }
}
```

#### Type 3: Direct URL
```json
{
  "selectors": {
    "detail": {
      "attachments": {
        "selector": "a.download-link"
      }
    }
  }
}
```

### 2. Extractor 함수 작성

`node/attachment_extractors.js`에 새로운 함수 추가:

```javascript
const attachmentExtractors = {
    // 기존 extractors...
    
    /**
     * 새로운 사이트: 설명
     */
    new_site_name: (document, config) => {
        const attachments = [];
        
        // 여기에 추출 로직 작성
        const links = document.querySelectorAll(config.attachments.selector);
        links.forEach(link => {
            const fileName = link.textContent.trim();
            const url = link.href;
            
            attachments.push({
                name: fileName,
                url: url
            });
        });
        
        return attachments;
    }
};
```

---

## 📝 기존 Extractor 목록

### 1. `anyang_complex`
- **용도**: 아이콘 span 제거 후 파일명 추출
- **DOM 구조**: `td ul li > a`
- **특징**: 
  - `.p-icon` 제거
  - preview 버튼 제외
  - 텍스트 클리닝

```javascript
anyang_complex: (document, config) => {
    const attachments = [];
    const fileLinks = document.querySelectorAll(config.attachments.selector);
    
    fileLinks.forEach(link => {
        const downloadLink = link.querySelector('a:not(.p-attach__preview p-button)');
        if (!downloadLink) return;
        
        const clonedAnchor = downloadLink.cloneNode(true);
        const iconSpan = clonedAnchor.querySelector('.p-icon');
        if (iconSpan) {
            iconSpan.remove();
        }
        const fileName = clonedAnchor.textContent.trim();
        const downloadUrl = downloadLink.href;
        
        if (fileName && downloadUrl) {
            attachments.push({
                name: fileName,
                url: downloadUrl
            });
        }
    });
    
    return attachments;
}
```

### 2. `boeun`
- **용도**: 파일명에서 괄호 제거 (파일 크기 표시)
- **DOM 구조**: `.p-attach li > a.p-attach__link`
- **특징**:
  - 파일명 정규화 (`file.pdf (123KB)` → `file.pdf`)
  - 중복 제거

```javascript
boeun: (document, config) => {
    const attachments = [];
    const attachmentItems = document.querySelectorAll('.p-attach li');
    
    attachmentItems.forEach(item => {
        const downloadLinkElement = item.querySelector('a.p-attach__link');
        const fileNameElement = item.querySelector('.p-attach__link span:last-child');

        if (fileNameElement && downloadLinkElement) {
            const fileName = fileNameElement.textContent.trim();
            const href = downloadLinkElement.href;

            const regex = /(\.[a-z0-9]+)\s*\([^)]*\)$/i;
            const cleanedFileName = fileName.replace(regex, '$1');

            const isDuplicate = attachments.some(att => att.name === cleanedFileName);
            if (!isDuplicate) {
                attachments.push({
                    url: href,
                    name: cleanedFileName
                });
            }
        }
    });
    
    return attachments;
}
```

### 3. `javascript_function`
- **용도**: JavaScript 함수 호출 방식 (goDownload 등)
- **특징**:
  - `onclick` 또는 `href`에서 함수 탐지
  - 중복 제거
  - "다운로드", "바로보기" 텍스트 제외

### 4. `direct_url`
- **용도**: 일반 href 링크
- **특징**: 가장 단순한 형태

---

## 🚀 새 사이트 추가 예시

### 예시 1: 테이블 구조 첨부파일

**DOM 구조:**
```html
<table class="attach-table">
  <tr>
    <td><a href="/download/file1.pdf">문서1.pdf</a></td>
  </tr>
</table>
```

**1. Config 설정 (`configs/mysite.json`)**
```json
{
  "selectors": {
    "detail": {
      "attachments": {
        "type": "custom",
        "extractorName": "mysite_table",
        "selector": "table.attach-table td a"
      }
    }
  }
}
```

**2. Extractor 함수 추가 (`attachment_extractors.js`)**
```javascript
mysite_table: (document, config) => {
    const attachments = [];
    const links = document.querySelectorAll(config.attachments.selector);
    
    links.forEach(link => {
        attachments.push({
            name: link.textContent.trim(),
            url: link.href
        });
    });
    
    return attachments;
}
```

### 예시 2: 복잡한 중첩 구조

**DOM 구조:**
```html
<div class="file-list">
  <div class="file-item">
    <span class="icon">📄</span>
    <a href="/download?id=123">
      <strong>파일명:</strong> 문서.pdf
    </a>
  </div>
</div>
```

**Extractor 함수:**
```javascript
mysite_nested: (document, config) => {
    const attachments = [];
    const items = document.querySelectorAll('.file-item');
    
    items.forEach(item => {
        const link = item.querySelector('a');
        if (!link) return;
        
        // <strong> 태그 제거하고 파일명만 추출
        const cloned = link.cloneNode(true);
        const strong = cloned.querySelector('strong');
        if (strong) strong.remove();
        
        const fileName = cloned.textContent.trim();
        
        attachments.push({
            name: fileName,
            url: link.href
        });
    });
    
    return attachments;
}
```

---

## 🔍 동작 원리

1. **파일 읽기**: `homepage_gosi_detail_downloader.js`가 `attachment_extractors.js` 파일을 읽음
2. **코드 주입**: `page.evaluate()` 내부에서 `eval(extractorsCode)` 실행
3. **함수 호출**: `window.attachmentExtractors[extractorName](document, config)` 호출
4. **결과 반환**: 추출된 attachments 배열 반환

```javascript
// Node.js (homepage_gosi_detail_downloader.js)
const extractorsPath = path.join(__dirname, 'attachment_extractors.js');
const extractorsCode = fs.readFileSync(extractorsPath, 'utf8');

const content = await page.evaluate((config, extractorsCode) => {
    // 브라우저 컨텍스트에서 실행
    eval(extractorsCode);  // window.attachmentExtractors 정의됨
    
    if (config.attachments.type === 'custom') {
        const extractorName = config.attachments.extractorName;
        data.attachments = window.attachmentExtractors[extractorName](document, config);
    }
    
    return data;
}, config, extractorsCode);
```

---

## ✅ 체크리스트: 새 사이트 추가시

1. [ ] 사이트의 첨부파일 DOM 구조 분석
2. [ ] 적절한 타입 선택 (custom/javascript/direct)
3. [ ] `configs/{site}.json`에 설정 추가
4. [ ] 필요시 `attachment_extractors.js`에 함수 추가
5. [ ] 테스트 실행
   ```bash
   node node/homepage_gosi_detail_downloader.js {site_code} --limit 1
   ```
6. [ ] content.md 파일 확인하여 첨부파일 정상 추출 확인

---

## 🐛 디버깅

### Extractor 함수가 호출되지 않을 때

**증상:**
```
Extractor not found: my_extractor
```

**해결:**
1. `attachment_extractors.js`에 함수가 정의되어 있는지 확인
2. 함수명이 config의 `extractorName`과 일치하는지 확인
3. 파일 저장 후 다시 실행

#**첨부파일**:이 비어있을 때

**디버깅 방법:**
```javascript
// attachment_extractors.js의 함수 내부에 console.log 추가
mysite: (document, config) => {
    console.log('Selector:', config.attachments.selector);
    const links = document.querySelectorAll(config.attachments.selector);
    console.log('Found links:', links.length);
    
    // ...
}
```

---

## 📚 참고

- **ATTACHMENT_DOWNLOAD_TYPES.md**: 다운로드 방식 3가지 타입 설명
- **node/attachment_extractors.js**: 모든 extractor 함수 정의
- **node/homepage_gosi_detail_downloader.js**: 메인 다운로더 로직

---

## 🎓 요약

### Before (하드코딩)
```javascript
// extractContent 내부에 모든 로직 하드코딩
if (extractorName === 'anyang_complex') {
    // 50줄 코드...
} else if (extractorName === 'boeun') {
    // 40줄 코드...
} else if (extractorName === 'site3') {
    // 60줄 코드...
}
```

### After (함수 분리)
```javascript
// attachment_extractors.js에 함수로 분리
const attachmentExtractors = {
    anyang_complex: (document, config) => { /* ... */ },
    boeun: (document, config) => { /* ... */ },
    site3: (document, config) => { /* ... */ }
};

// extractContent에서는 단순 호출
data.attachments = window.attachmentExtractors[extractorName](document, config);
```

**결과:**
- ✅ 코드 중복 제거
- ✅ 유지보수 간편
- ✅ 가독성 향상
- ✅ 확장 용이