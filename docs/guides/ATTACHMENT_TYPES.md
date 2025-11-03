# 첨부파일 다운로드 방식 3가지 타입

## 개요
각 사이트의 첨부파일 다운로드 방식은 크게 3가지로 구분됩니다. 
사이트마다 이 타입에 맞는 다운로드 로직을 적용해야 합니다.

---

## 타입 1: URL href 타입 (직접 링크)

### 특징
- 가장 일반적인 방식
- `<a href="https://example.com/files/document.pdf">다운로드</a>`
- href 속성에 직접 다운로드 URL이 있음

### 처리 방법
```javascript
// axios 또는 fetch로 직접 다운로드
const response = await axios.get(attachment.url, {
    responseType: 'stream',
    timeout: 30000
});

const writer = fs.createWriteStream(savePath);
response.data.pipe(writer);

await new Promise((resolve, reject) => {
    writer.on('finish', resolve);
    writer.on('error', reject);
});
```

### 예시 사이트
- 대부분의 일반 사이트
- 정적 파일 제공 서버

---

## 타입 2: onclick 이벤트 타입

### 특징
- `<a onclick="downloadFile('123', 'abc')" href="#">다운로드</a>`
- onclick 속성에 JavaScript 함수 호출
- href는 `#` 또는 `javascript:void(0)`

### 처리 방법
```javascript
// onclick에서 함수명과 파라미터 추출
const onclickMatch = attachment.onclick.match(/downloadFile\('([^']+)',\s*'([^']+)'\)/);
if (onclickMatch) {
    const [, param1, param2] = onclickMatch;
    
    // 브라우저에서 해당 함수 실행
    await page.evaluate((p1, p2) => {
        downloadFile(p1, p2);
    }, param1, param2);
    
    // 다운로드 이벤트 대기
    const download = await page.waitForEvent('download', { timeout: 30000 });
    await download.saveAs(savePath);
}
```

### 예시 사이트
- 동적 파일 생성 사이트
- 세션 기반 다운로드

---

## 타입 3: href="javascript:" 타입 (안동 방식)

### 특징
- `<a href="javascript:goDownload('file.pdf', 'sys123', '/path')">다운로드</a>`
- href 속성 자체가 `javascript:` 코드
- 주로 POST 방식으로 폼 제출하여 다운로드

### 처리 방법 ⭐ **현재 homepage_gosi_detail_downloader.js에 구현됨**
```javascript
// 1. goDownload 패턴에서 파라미터 추출
const goDownloadRegex = /goDownload\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)/;
const matches = url.match(goDownloadRegex);
const [, userFileNm, sysFileNm, filePath] = matches;

// 2. CDP로 다운로드 설정
await setupDownloadBehavior(page, attachDir);

// 3. 다운로드 이벤트 리스너 등록
const downloadPromise = new Promise((resolve, reject) => {
    const downloadHandler = async (download) => {
        const savePath = path.join(attachDir, download.suggestedFilename());
        await download.saveAs(savePath);
        resolve({ success: true, savedPath });
    };
    page.on('download', downloadHandler);
});

// 4. 브라우저에서 폼 제출 실행
await page.evaluate((params) => {
    // fn_egov_downFile 함수가 있으면 사용
    if (typeof fn_egov_downFile === 'function') {
        fn_egov_downFile(params.userFileNm, params.sysFileNm, params.filePath);
    } else {
        // 수동 폼 제출
        const form = document.createElement('form');
        form.method = 'post';
        form.action = 'https://eminwon.site.go.kr/emwp/jsp/ofr/FileDownNew.jsp';
        
        // hidden input 추가
        ['user_file_nm', 'sys_file_nm', 'file_path'].forEach((name, i) => {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            input.value = [params.userFileNm, params.sysFileNm, params.filePath][i];
            form.appendChild(input);
        });
        
        document.body.appendChild(form);
        form.submit();
    }
}, { userFileNm, sysFileNm, filePath });

// 5. 다운로드 완료 대기
const result = await downloadPromise;
```

### 예시 사이트
- **안동시** (andong) - 현재 구현됨
- 전자민원 시스템 사용 사이트
- eminwon.*.go.kr 도메인 사용 사이트

### 주의사항
- ⚠️ 143바이트 오류 HTML 응답 가능 (구버전 방식에서만)
- ✅ Playwright download 이벤트 방식은 실제 파일만 다운로드
- 파라미터 URL 디코딩 필수

---

## 각 타입별 config.json 설정

### 타입 1: URL href
```json
{
    "selectors": {
        "detail": {
            "attachments": {
                "selector": "a.download-link",
                "type": "direct",
                "downloadFunction": null
            }
        }
    }
}
```

### 타입 2: onclick 이벤트
```json
{
    "selectors": {
        "detail": {
            "attachments": {
                "selector": "a[onclick*='downloadFile']",
                "type": "onclick",
                "downloadFunction": "downloadFile"
            }
        }
    }
}
```

### 타입 3: javascript: href (안동 방식)
```json
{
    "selectors": {
        "detail": {
            "attachments": {
                "selector": "a[href*='goDownload'], a[onclick*='goDownload']",
                "type": "javascript",
                "downloadFunction": "goDownload"
            }
        }
    }
}
```

---

## 사이트별 다운로드 타입 매핑

### 타입 3 (javascript:) 확인된 사이트
- ✅ **andong** (안동시) - 구현 완료

### 타입별 추가 조사 필요
- 각 사이트 확인 후 여기에 추가

---

## 구현 위치

### homepage_gosi_detail_downloader.js
```
downloadSingleAttachment()  → 타입 판별 및 분기
  ↓
  ├─ downloadViaGoDownload()     → 타입 3 (javascript:)
  ├─ downloadViaOnclick()         → 타입 2 (onclick) - TODO
  └─ downloadViaDirectLink()      → 타입 1 (href) - TODO
```

### andong_scraperjs.js (참조용)
```
downloadSingleAttachment()
  ↓
  └─ downloadViaEgovPost()  → 타입 3 구현 (참조용)
```

---

## 다음 작업

1. **타입별 메서드 분리**
   - [ ] downloadViaDirectLink() 구현 (타입 1)
   - [ ] downloadViaOnclick() 구현 (타입 2)
   - [x] downloadViaGoDownload() 구현 (타입 3) ✅

2. **config 기반 자동 판별**
   - [ ] config.selectors.detail.attachments.type 읽기
   - [ ] 타입에 맞는 메서드 자동 호출

3. **사이트별 타입 조사**
   - [ ] 136개 사이트 각각 확인
   - [ ] 타입별 분류 문서화

---

## 참고 파일
- `node/homepage_gosi_detail_downloader.js` - 메인 다운로더 (타입 3 구현됨)
- `node/scraper/andong_scraperjs.js` - 타입 3 참조 구현
- `node/configs/{site_code}.json` - 각 사이트 설정
- `node/fix_andong_content_md.js` - content.md 파일 수정 스크립트 (JavaScript URL → 실제 URL)

## 기존 content.md 파일 수정

기존에 생성된 content.md 파일에 JavaScript URL이 있는 경우, 다음 스크립트로 일괄 수정 가능:

```bash
node node/fix_andong_content_md.js
```

**결과:**
- 326개 중 324개 파일 수정 완료
- JavaScript URL → 실제 eminwon 다운로드 URL로 변경