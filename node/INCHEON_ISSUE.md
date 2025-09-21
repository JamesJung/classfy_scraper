# Incheon Scraper Issue

## 문제
Incheon 공고 사이트 (https://announce.incheon.go.kr) 스크래핑이 정상 작동하지 않음

## 원인 분석
1. 사이트가 서버 세션 기반으로 동작
2. GET 요청으로는 검색 폼만 표시되고 실제 데이터는 표시되지 않음
3. POST 요청도 세션 없이는 데이터를 반환하지 않음
4. 세션 초기화를 위해 홈페이지 먼저 방문 후 리스트 페이지 접근 필요

## 시도한 방법
1. ✅ GET 요청으로 직접 접근
   - URL: `?command=searchList&flag=gosiGL&svp=Y&sido=ic&currentPageNo=1`
   - 결과: 검색 폼만 표시, 데이터 없음

2. ✅ POST 폼 제출 방식
   - 동적 폼 생성 후 제출
   - 결과: 데이터 없음

3. ✅ 세션 초기화 후 접근
   - 홈페이지 (https://announce.incheon.go.kr) 방문하여 세션 생성
   - 리스트 페이지로 이동
   - 결과: 부분적 성공, 테이블은 표시되나 실제 공고 데이터는 여전히 없음

## 발견사항
- 홈페이지에서 `/citynet/jsp/vol/VolHome.do?command=home`로 리다이렉트됨
- 세션 생성 후 리스트 페이지 접근 시 테이블 구조는 나타나지만 공고 데이터는 없음
- viewData(sno, gosiGbn) 함수는 존재하지만 데이터가 없어 테스트 불가

## 현재 상태
- 리스트 페이지 접근은 가능하나 실제 공고 데이터를 가져올 수 없음
- 검색 폼을 통한 명시적 검색이 필요할 수 있음
- 서버측에서 추가 검증이나 필수 파라미터를 요구하는 것으로 추정

## 향후 해결 방안
1. 검색 폼에서 검색 버튼 클릭 후 데이터 로딩 확인
2. 개발자 도구에서 실제 데이터 요청 시 전송되는 헤더/쿠키 분석
3. 필요시 검색 조건 입력 후 검색 실행하는 로직 구현
4. AJAX 요청이나 동적 로딩 메커니즘 분석

## 기술 스택
- Playwright
- Node.js
- cwg_scraper 베이스 클래스 상속

## 파일 위치
`/Users/jin/classfy_scraper/node/scraper/incheon_scraper.js`