# 긴급 수정: undici 다운그레이드로 Node.js 18 지원

## ⚡ 빠른 해결 방법 (서버에서 실행)

서버의 Node.js 버전이 18.x인 경우, 다음 명령어로 즉시 해결할 수 있습니다:

```bash
# 1. 프로젝트 디렉토리로 이동
cd /home/zium/classfy_scraper

# 2. 최신 코드 가져오기
git pull

# 3. node 디렉토리로 이동
cd node

# 4. 기존 패키지 삭제 및 재설치
rm -rf node_modules package-lock.json
npm install

# 5. 완료 - 버전 확인
npm list undici
```

예상 출력:
```
└── undici@5.28.4
```

## 📋 변경 사항

### package.json 수정 내역

**변경 전:**
```json
{
  "engines": {
    "node": ">=20.0.0"
  },
  "dependencies": {
    "undici": "^6.19.8"
  }
}
```

**변경 후:**
```json
{
  "engines": {
    "node": ">=18.0.0"
  },
  "dependencies": {
    "undici": "^5.28.4"
  }
}
```

### 왜 undici를 다운그레이드했나?

- **undici v6.x**: Node.js 20+ 필요 (File API 사용)
- **undici v5.x**: Node.js 18+ 지원
- 현재 서버가 Node.js 18.x를 사용 중이므로 v5로 다운그레이드

## 🧪 테스트

### 1. 단일 스크래퍼 테스트

```bash
cd /home/zium/classfy_scraper

# Eminwon 스크래퍼 테스트
node node/scraper/eminwon_scraper.js \
  --region 천안시 \
  --date 20251031 \
  --output /tmp/test_eminwon

# Homepage 스크래퍼 테스트
node node/scraper/cs_scraper.js \
  --site cs \
  --date 2025-10-31 \
  --output /tmp/test_homepage
```

### 2. 전체 배치 테스트

```bash
# Eminwon 배치
./daily_eminwon.sh

# Homepage 배치 (만약 있다면)
python3 homepage_daily_orchestrator.py --test
```

## 📊 버전 호환성

| Node.js 버전 | undici v5.28.4 | undici v6.19.8 |
|-------------|----------------|----------------|
| v16.x       | ⚠️ 부분 지원     | ❌ 미지원        |
| v18.x       | ✅ 완전 지원     | ❌ 미지원        |
| v20.x       | ✅ 완전 지원     | ✅ 완전 지원     |
| v22.x       | ✅ 완전 지원     | ✅ 완전 지원     |

## 🔄 장기 해결책

이것은 **임시 해결책**입니다. 더 나은 성능과 최신 기능을 위해 Node.js 20+로 업그레이드를 권장합니다.

### Node.js 20 업그레이드 방법

```bash
# nvm 사용 (권장)
nvm install 20
nvm use 20
nvm alias default 20

# 패키지 재설치 (undici v6로 복구)
cd /home/zium/classfy_scraper/node
rm -rf node_modules package-lock.json

# package.json을 v6 버전으로 수정 후
npm install
```

상세한 업그레이드 가이드는 `NODEJS_UPGRADE_GUIDE.md` 참조.

## ⚠️ 알려진 제한사항

### undici v5.28.4의 제한

1. **최신 fetch API 기능 부족**: 일부 최신 기능 미지원
2. **성능**: v6에 비해 약간 느릴 수 있음
3. **보안 패치**: v6이 더 최신 보안 패치 포함

### 권장 사항

- ✅ **즉시**: undici v5로 다운그레이드 (문제 해결)
- ⚡ **단기**: Node.js 18.x 유지 (안정적)
- 🚀 **장기**: Node.js 20+ 업그레이드 (권장)

## 🐛 문제 해결

### Q: npm install 후에도 에러가 계속됨

**A:** node_modules를 완전히 삭제했는지 확인:

```bash
cd /home/zium/classfy_scraper/node
rm -rf node_modules package-lock.json
npm cache clean --force
npm install
```

### Q: "Cannot find module 'undici'" 에러

**A:** 패키지가 제대로 설치되지 않았습니다:

```bash
npm install undici@5.28.4 --save
```

### Q: 여전히 File API 에러 발생

**A:** 다음을 확인하세요:

```bash
# 1. undici 버전 확인
npm list undici
# 출력: undici@5.28.4 이어야 함

# 2. Node.js 버전 확인
node --version
# v18.x 이상이어야 함

# 3. 캐시 문제일 수 있으므로 서버 재시작
sudo systemctl restart your-service-name
```

## 📞 추가 지원

문제가 지속되면 다음 정보와 함께 연락:

1. **Node.js 버전**
   ```bash
   node --version
   ```

2. **undici 버전**
   ```bash
   npm list undici
   ```

3. **전체 에러 메시지**
   ```bash
   # 에러가 발생한 전체 로그
   tail -100 logs/eminwon_daily_*.log
   ```

4. **package.json 확인**
   ```bash
   cat node/package.json | grep -A2 '"undici"'
   ```

---

**최종 업데이트**: 2025-10-31
**적용 버전**: undici v5.28.4
**Node.js 요구사항**: v18.0.0+
