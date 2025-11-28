# Node.js 업그레이드 가이드

## 문제 상황

리눅스 서버에서 다음과 같은 에러가 발생하는 경우:

```
ReferenceError: File
webidl.is.File = webidl.util.MakeTypeAssertion(File)
                                               ^
```

이것은 **Node.js 버전이 낮아서** 발생하는 문제입니다.

## 원인

- `undici` v6 패키지가 `File` API를 사용하는데, 이 API는 **Node.js 20 이상**에서만 사용 가능
- 현재 서버의 Node.js 버전이 18.x 또는 19.x일 가능성

## 해결 방법

### 1. 현재 Node.js 버전 확인

```bash
node --version
```

출력 예시:
- ❌ `v18.16.0` - 업그레이드 필요
- ❌ `v19.9.0` - 업그레이드 필요
- ✅ `v20.11.1` - 사용 가능
- ✅ `v22.0.0` - 사용 가능

### 2. Node.js 20+ 설치 방법

#### 방법 A: nvm 사용 (권장)

**nvm이 설치되어 있는 경우:**

```bash
# Node.js 20 LTS 설치
nvm install 20

# Node.js 20 사용
nvm use 20

# 기본 버전으로 설정
nvm alias default 20

# 버전 확인
node --version
```

**nvm이 설치되어 있지 않은 경우:**

```bash
# nvm 설치
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

# 쉘 재시작 또는 환경 변수 로드
source ~/.bashrc  # 또는 source ~/.zshrc

# Node.js 20 설치
nvm install 20
nvm use 20
nvm alias default 20
```

#### 방법 B: 직접 설치 (Ubuntu/Debian)

```bash
# NodeSource 저장소 추가
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -

# Node.js 20 설치
sudo apt-get install -y nodejs

# 버전 확인
node --version
npm --version
```

#### 방법 C: 직접 설치 (CentOS/RHEL)

```bash
# NodeSource 저장소 추가
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -

# Node.js 20 설치
sudo yum install -y nodejs

# 버전 확인
node --version
npm --version
```

### 3. 패키지 재설치

Node.js 버전을 업그레이드한 후, 프로젝트의 node_modules를 다시 설치합니다:

```bash
cd /home/zium/classfy_scraper/node

# 기존 node_modules 삭제
rm -rf node_modules package-lock.json

# 패키지 재설치
npm install

# Playwright 브라우저 재설치
npx playwright install
```

### 4. 테스트

```bash
# 단일 스크래퍼 테스트
node node/scraper/eminwon_scraper.js --region 천안시 --date 20251031 --output /tmp/test

# 전체 배치 테스트
./daily_eminwon.sh
```

## 서버별 PATH 설정

### /home/zium/classfy_scraper/daily_eminwon.sh

스크립트가 자동으로 Node.js 버전을 체크하도록 업데이트되었습니다:

```bash
# Node.js 확인 및 버전 체크
if command -v node >/dev/null 2>&1; then
    NODE_VERSION=$(node --version 2>&1)
    NODE_MAJOR_VERSION=$(echo "$NODE_VERSION" | sed 's/v\([0-9]*\).*/\1/')

    if [ "$NODE_MAJOR_VERSION" -lt 20 ]; then
        echo "✗ ERROR: Node.js 버전이 너무 낮습니다"
        echo "  현재 버전: ${NODE_VERSION}"
        echo "  필요 버전: v20.0.0 이상"
        exit 1
    fi
fi
```

nvm을 사용하는 경우, `.bashrc` 또는 `.zshrc`에 다음을 추가:

```bash
# nvm 설정
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# 기본 Node.js 버전 사용
nvm use default
```

## 문제 해결

### Q: nvm 설치 후 "command not found: nvm" 에러

**A:** 쉘 설정 파일을 다시 로드하거나 터미널을 재시작하세요:

```bash
source ~/.bashrc  # bash 사용 시
source ~/.zshrc   # zsh 사용 시

# 또는 터미널 재시작
exit
# 다시 로그인
```

### Q: npm install 시 권한 에러

**A:** sudo 없이 설치하려면 npm prefix를 변경:

```bash
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

### Q: Playwright 브라우저 설치 실패

**A:** 시스템 의존성 설치:

```bash
# Ubuntu/Debian
sudo apt-get install -y \
    libwoff1 \
    libopus0 \
    libwebp7 \
    libwebpdemux2 \
    libenchant-2-2 \
    libgudev-1.0-0 \
    libsecret-1-0 \
    libhyphen0 \
    libgdk-pixbuf2.0-0 \
    libegl1 \
    libnotify4 \
    libxslt1.1 \
    libevent-2.1-7 \
    libgles2 \
    libxcomposite1 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libepoxy0 \
    libgtk-3-0 \
    libharfbuzz-icu0

# 그 후 다시 설치
npx playwright install
npx playwright install-deps
```

## 참고 자료

- [Node.js 공식 다운로드](https://nodejs.org/en/download/)
- [nvm GitHub](https://github.com/nvm-sh/nvm)
- [NodeSource 설치 가이드](https://github.com/nodesource/distributions)
- [Playwright 시스템 요구사항](https://playwright.dev/docs/intro#system-requirements)

## 연락처

문제가 계속되면 개발팀에 문의하세요:
- 로그 파일: `logs/eminwon_daily_*.log`
- 에러 메시지와 함께 위 로그 파일 전달
