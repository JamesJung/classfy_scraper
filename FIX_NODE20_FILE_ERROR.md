# Node.js v20에서 File API 에러 해결 방법

## 문제 상황

서버의 Node.js 버전이 v20.19.5인데도 다음 에러 발생:

```
ReferenceError: File
webidl.is.File = webidl.util.MakeTypeAssertion(File)
                                               ^
```

## 원인

Node.js v20은 File API를 지원하지만, 다음 이유로 에러가 발생할 수 있습니다:

1. **node_modules가 다른 Node.js 버전으로 설치됨**
2. **실행 시점에 다른 Node.js 버전 사용** (PATH 문제)
3. **npm 캐시 문제**
4. **package-lock.json과 node_modules 불일치**

## ✅ 해결 방법 (서버에서 실행)

### 1단계: Node.js 버전 재확인

```bash
# 현재 사용 중인 Node.js 버전 확인
node --version
# 출력: v20.19.5 (또는 v20.x.x)

# which 명령어로 실제 node 경로 확인
which node
# nvm 사용 시: /home/zium/.nvm/versions/node/v20.19.5/bin/node
# 시스템 설치 시: /usr/bin/node

# npm 버전 확인
npm --version
```

**예상 출력:**
- ✅ `v20.19.5` 이상
- ❌ `v18.x.x` 또는 `v19.x.x` → nvm으로 v20 활성화 필요

### 2단계: 코드 업데이트

```bash
cd /home/zium/classfy_scraper
git pull
```

### 3단계: node_modules 완전 삭제 및 재설치

```bash
cd /home/zium/classfy_scraper/node

# 1. 기존 node_modules와 lock 파일 완전 삭제
rm -rf node_modules package-lock.json

# 2. npm 캐시 클리어
npm cache clean --force

# 3. Node.js 버전 재확인 (중요!)
node --version
# 반드시 v20.x.x 확인

# 4. 패키지 재설치
npm install

# 5. undici 버전 확인
npm list undici
# 출력: undici@6.19.8 이어야 함
```

### 4단계: Playwright 브라우저 재설치 (옵션)

```bash
# Playwright 브라우저가 꼬였을 수 있으므로 재설치
npx playwright install

# 시스템 의존성도 설치 (Ubuntu/Debian)
npx playwright install-deps
```

### 5단계: 테스트

```bash
cd /home/zium/classfy_scraper

# 단일 스크래퍼 테스트
node node/scraper/eminwon_scraper.js \
  --region 천안시 \
  --date 20251101 \
  --output /tmp/test_eminwon

# 성공 시 출력:
# === 천안시 이민원 스크래핑 완료 ===
# 처리된 공고 수: X
```

## 🔍 추가 디버깅

### nvm 사용 시 기본 버전 설정

```bash
# 현재 활성화된 Node.js 버전
nvm current

# Node.js 20을 기본값으로 설정
nvm alias default 20

# 쉘 재시작 후에도 v20 사용되는지 확인
nvm use default
node --version
```

### PATH 확인

```bash
# 현재 PATH 확인
echo $PATH

# node가 어느 경로에서 실행되는지 확인
type node
which -a node  # 모든 node 경로 확인
```

### 실행 스크립트에서 Node.js 버전 명시

daily_eminwon.sh의 PATH 설정 확인:

```bash
# ~/.bashrc 또는 ~/.zshrc에 nvm 설정 추가
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# 기본 Node.js 버전 사용
nvm use default
```

## 🐛 여전히 에러가 발생하는 경우

### 옵션 1: Node.js 경로 직접 지정

`daily_eminwon.sh` 또는 Python 스크립트에서 node 경로를 직접 지정:

```bash
# daily_eminwon.sh 수정
NODE_PATH="/home/zium/.nvm/versions/node/v20.19.5/bin/node"

# Python 스크립트에서 사용
subprocess.run([NODE_PATH, "node/scraper/eminwon_scraper.js", ...])
```

### 옵션 2: nvm을 통한 실행

```bash
# nvm 환경에서 스크립트 실행
nvm exec 20 ./daily_eminwon.sh
```

### 옵션 3: 완전히 새로 설치

```bash
# Node.js 완전 재설치
nvm uninstall 20
nvm install 20
nvm use 20
nvm alias default 20

# 프로젝트 패키지 재설치
cd /home/zium/classfy_scraper/node
rm -rf node_modules package-lock.json
npm install
npx playwright install
```

## ✅ 확인 체크리스트

실행 전 다음을 모두 확인:

- [ ] `node --version` → v20.19.5 (또는 v20.x.x)
- [ ] `which node` → nvm 경로 또는 시스템 경로 확인
- [ ] `npm list undici` → undici@6.19.8
- [ ] `node_modules` 완전 삭제 후 재설치
- [ ] `npm cache clean --force` 실행
- [ ] 테스트 스크래퍼 정상 실행

## 📊 버전 정보

| 항목 | 요구사항 | 현재 서버 |
|------|----------|----------|
| **Node.js** | v20.0.0+ | v20.19.5 ✅ |
| **npm** | v9.0.0+ | 확인 필요 |
| **undici** | v6.19.8 | 확인 필요 |

## 📝 로그 확인

에러 발생 시 로그 확인:

```bash
# 최근 에러 로그 확인
tail -100 /home/zium/classfy_scraper/logs/eminwon_daily_*.log | grep -A5 "ReferenceError"

# node_modules 설치 로그
npm install 2>&1 | tee npm-install.log
```

## 💡 예방 방법

향후 이런 문제를 방지하려면:

1. **nvm 사용** - 버전 관리 명확화
2. **기본 버전 설정** - `nvm alias default 20`
3. **CI/CD에서 버전 고정** - `.nvmrc` 파일 사용
4. **package-lock.json 커밋** - 버전 일관성 유지

### .nvmrc 파일 생성

```bash
# 프로젝트 루트에 .nvmrc 생성
echo "20" > /home/zium/classfy_scraper/.nvmrc

# 이후 프로젝트 디렉토리에서
nvm use
# 자동으로 v20 사용
```

---

**최종 업데이트**: 2025-10-31
**적용 대상**: Node.js v20.19.5 서버
**문제**: File API ReferenceError
**해결**: node_modules 재설치
