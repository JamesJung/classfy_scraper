# 프로덕션 환경 Node.js 버전 문제 해결 가이드

## 🔍 문제 상황

```
프로덕션 서버:
- which node: /home/zium/.nvm/versions/node/v20.19.5/bin/node
- 실제 실행 시: Node.js v12.22.9 사용 ❌
- 에러: "Playwright requires Node.js 18 or higher"
```

## 🎯 원인

**비대화형 셸에서 nvm 환경이 로드되지 않음**

- cron, systemd, 수동 스크립트 실행 시 `~/.bashrc` 실행 안됨
- nvm 환경변수 미설정 → 시스템 기본 node (v12.22.9) 사용
- 대화형 셸에서는 정상 (v20.19.5 사용)

## 💡 해결 방법

### ✅ 방법 1: run_scrapers_batch.sh 수정 (권장)

기존 `/home/zium/classfy_scraper/run_scrapers_batch.sh`를 다음과 같이 수정:

```bash
#!/bin/bash

SCRIPT_DIR="/home/zium/classfy_scraper"
LOG_DIR="$SCRIPT_DIR/logs"
PYTHON_PATH="/usr/bin/python3"

# ========== NVM 환경 로드 추가 ==========
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
[ -s "/home/zium/.nvm/nvm.sh" ] && source "/home/zium/.nvm/nvm.sh"

# Node.js 버전 활성화
if command -v nvm &> /dev/null; then
    nvm use 20 &> /dev/null || nvm use default &> /dev/null
fi

# Node.js 버전 확인
NODE_VERSION=$(node --version 2>/dev/null)
NODE_MAJOR=$(echo $NODE_VERSION | sed -E 's/v([0-9]+)\..*/\1/')
if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "❌ Node.js 버전 부족: $NODE_VERSION"
    exit 1
fi
echo "✅ Node.js: $NODE_VERSION"
# ========================================

mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/scraper_batch_$TIMESTAMP.log"

cd "$SCRIPT_DIR"

echo "========================================" >> "$LOG_FILE"
echo "스크래퍼 배치 실행 시작: $(date)" >> "$LOG_FILE"
echo "Node.js: $(node --version)" >> "$LOG_FILE"  # ✅ 버전 로깅 추가
echo "========================================" >> "$LOG_FILE"

$PYTHON_PATH run_incremental_scrapers_v2.py 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}
if [ $EXIT_CODE -eq 0 ]; then
    echo "스크래퍼 실행 성공: $(date)" >> "$LOG_FILE"
else
    echo "스크래퍼 실행 실패: $(date)" >> "$LOG_FILE"
    echo "오류 코드: $EXIT_CODE" >> "$LOG_FILE"
fi

echo "========================================" >> "$LOG_FILE"
echo "스크래퍼 배치 종료: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

find "$LOG_DIR" -name "scraper_batch_*.log" -mtime +30 -delete

exit $EXIT_CODE
```

### ✅ 방법 2: run_incremental_scrapers_v2.py 수정

`run_incremental_scrapers_v2.py` line 695 수정:

```python
# 현재
cmd = [
    "node",
    str(scraper_path),
    ...
]

# 수정
cmd = [
    "/home/zium/.nvm/versions/node/v20.19.5/bin/node",  # ✅ 절대 경로
    str(scraper_path),
    ...
]

# 또는 환경변수로 제어
NODE_EXECUTABLE = os.getenv("NODE_EXECUTABLE", "node")
cmd = [
    NODE_EXECUTABLE,
    str(scraper_path),
    ...
]
```

### ✅ 방법 3: ~/.bashrc 수정 (비대화형에서도 nvm 로드)

`/home/zium/.bashrc` 파일에 다음 추가:

```bash
# 파일 맨 위에 추가 (비대화형 셸 체크 전에)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && source "$NVM_DIR/bash_completion"
```

### ✅ 방법 4: 시스템 레벨 심볼릭 링크 생성

```bash
# 프로덕션 서버에서 실행 (root 권한 필요)
sudo ln -sf /home/zium/.nvm/versions/node/v20.19.5/bin/node /usr/local/bin/node
sudo ln -sf /home/zium/.nvm/versions/node/v20.19.5/bin/npm /usr/local/bin/npm

# 확인
/usr/local/bin/node --version  # v20.19.5 출력되어야 함
```

## 🧪 테스트 방법

### 1. 비대화형 셸 테스트

```bash
# SSH로 접속한 후
bash -c 'echo "Node version: $(node --version)"'
# 출력: v20.19.5 (정상) 또는 v12.22.9 (문제)

# 수정 후 다시 테스트
bash -c 'source ~/.nvm/nvm.sh && nvm use 20 && echo "Node: $(node --version)"'
# 출력: v20.19.5
```

### 2. 스크립트 직접 실행 테스트

```bash
# 프로덕션 서버에서
cd /home/zium/classfy_scraper
bash run_scrapers_batch.sh

# 또는 수정된 버전
bash run_scrapers_batch_fixed.sh

# 로그 확인
tail -f logs/scraper_batch_*.log
```

### 3. cron 환경 시뮬레이션

```bash
# cron과 동일한 환경에서 실행
env -i HOME=/home/zium SHELL=/bin/bash bash --noprofile --norc /home/zium/classfy_scraper/run_scrapers_batch.sh
```

## 📋 체크리스트

프로덕션 서버에서 다음 순서로 진행:

- [ ] 1. 현재 상태 확인
  ```bash
  which node
  node --version
  bash -c 'echo $(node --version)'
  ```

- [ ] 2. nvm 설치 확인
  ```bash
  ls -la ~/.nvm/nvm.sh
  source ~/.nvm/nvm.sh && nvm --version
  ```

- [ ] 3. run_scrapers_batch.sh 백업
  ```bash
  cp /home/zium/classfy_scraper/run_scrapers_batch.sh /home/zium/classfy_scraper/run_scrapers_batch.sh.backup
  ```

- [ ] 4. 스크립트 수정 적용
  ```bash
  # run_scrapers_batch_fixed.sh를 업로드하거나
  # 기존 파일을 직접 수정
  ```

- [ ] 5. 테스트 실행
  ```bash
  bash /home/zium/classfy_scraper/run_scrapers_batch.sh --site-code andong
  ```

- [ ] 6. 로그 확인
  ```bash
  tail -100 /home/zium/classfy_scraper/logs/scraper_batch_*.log | grep -E "Node|node|버전"
  ```

- [ ] 7. cron 작업 확인 (있다면)
  ```bash
  crontab -l
  # cron 작업이 있으면 환경변수 설정 추가
  ```

## 🔧 cron 설정 예시

```bash
# crontab -e

# nvm 환경변수 설정 (cron에서)
SHELL=/bin/bash
NVM_DIR=/home/zium/.nvm

# 매일 새벽 2시 실행
0 2 * * * source $NVM_DIR/nvm.sh && cd /home/zium/classfy_scraper && bash run_scrapers_batch.sh >> /home/zium/classfy_scraper/logs/cron.log 2>&1
```

## 🎯 권장 해결책 요약

**최고 우선순위 (둘 다 적용 권장):**
1. ✅ **run_scrapers_batch.sh 수정** - nvm 환경 로드 추가
2. ✅ **Node.js 버전 검증 로직** - 18 미만이면 즉시 중단

**추가 권장:**
3. ✅ **로그에 버전 정보 기록** - 문제 추적 용이
4. ✅ **cron 환경변수 설정** - cron 실행 시에도 nvm 로드

## 📞 문제 발생 시 확인사항

1. **로그 파일 확인**
   ```bash
   cat /home/zium/classfy_scraper/logs/scraper_batch_*.log | grep -i "node"
   ```

2. **환경변수 확인**
   ```bash
   env | grep -E "NVM|NODE|PATH"
   ```

3. **실행 권한 확인**
   ```bash
   ls -la /home/zium/classfy_scraper/*.sh
   ```

4. **Node.js 프로세스 확인**
   ```bash
   ps aux | grep node
   ```
