# domain_key_config와 Excel key_params 불일치 보고서

**생성일시**: 2025-10-28

**총 불일치 건수**: 110개

---

## 1. gtp

**도메인**: `pms.gtp.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['b_idx']`

### 차이점

**DB에만 있음**: `['b_idx']`

### 공고 URL

```
https://pms.gtp.or.kr/web/business/webBusinessList.do
```

---

## 2. dcb

**도메인**: `www.dcb.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
no
```

**파싱된 파라미터 리스트**: `['no']`

### DB 데이터

**key_params**: `['mcode', 'mode', 'no']`

### 차이점

**DB에만 있음**: `['mcode', 'mode']`

### 공고 URL

```
https://www.dcb.or.kr/01_news/?mcode=0401010000
```

---

## 3. sjtp

**도메인**: `sjtp.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
wr_id
```

**파싱된 파라미터 리스트**: `['wr_id']`

### DB 데이터

**key_params**: `['bo_table', 'wr_id']`

### 차이점

**DB에만 있음**: `['bo_table']`

### 공고 URL

```
https://sjtp.or.kr/bbs/board.php?bo_table=business01
```

---

## 4. kiat

**도메인**: `www.kiat.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['MenuId', 'board_id', 'contents_id', 'mode']`

### 차이점

**DB에만 있음**: `['contents_id', 'board_id', 'mode', 'MenuId']`

### 공고 URL

```
https://www.kiat.or.kr/front/board/boardContentsListPage.do?board_id=90&MenuId=b159c9dac684471b87256f1e25404f5e
```

---

## 5. gwjob1

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://www.gwjob.kr/gwjob/support_policy/support_apply
```

---

## 6. gwjob2

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://job.gwd.go.kr/gwjob/support_policy/support_apply/career_discon_women
```

---

## 7. gwjob3

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://job.gwd.go.kr/gwjob/support_policy/support_apply/interview_activity_expense
```

---

## 8. gwjob4

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://job.gwd.go.kr/gwjob/support_policy/startups_policy
```

---

## 9. gwjob5

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://job.gwd.go.kr/gwjob/support_policy/enterprises_policy/growing_support
```

---

## 10. gwjob6

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://job.gwd.go.kr/gwjob/support_policy/enterprises_policy/financial_support
```

---

## 11. gwjob7

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://job.gwd.go.kr/gwjob/support_policy/enterprises_policy/workforce_support
```

---

## 12. mss8

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/gangwon/ex/bbs/List.do?cbIdx=252
```

---

## 13. cceiGangwon

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/gangwon/custom/notice_list.do?
```

---

## 14. mss5

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/gyeonggi/ex/bbs/List.do?cbIdx=247
```

---

## 15. cceiGyeonggi

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/gyeonggi/custom/notice_list.do?&sPtime=all&page=1
```

---

## 16. gcon

**도메인**: `www.gcon.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
pbancSrnm
```

**파싱된 파라미터 리스트**: `['pbancSrnm']`

### DB 데이터

**key_params**: `['menuNo', 'pbancSrnm']`

### 차이점

**DB에만 있음**: `['menuNo']`

### 공고 URL

```
https://www.gcon.or.kr/gcon/business/gconNotice/list.do?menuNo=200061
```

---

## 17. gcaf

**도메인**: `www.gcaf.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
wr_id
```

**파싱된 파라미터 리스트**: `['wr_id']`

### DB 데이터

**key_params**: `['bo_table', 'wr_id']`

### 차이점

**DB에만 있음**: `['bo_table']`

### 공고 URL

```
https://www.gcaf.or.kr/bbs/board.php?bo_table=sub3_7
```

---

## 18. gnsinbo

**도메인**: `www.gnsinbo.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
wr_id
```

**파싱된 파라미터 리스트**: `['wr_id']`

### DB 데이터

**key_params**: `['bo_table', 'wr_id']`

### 차이점

**DB에만 있음**: `['bo_table']`

### 공고 URL

```
https://www.gnsinbo.or.kr/bbs/board.php?bo_table=6_2_1
```

---

## 19. mss11

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/gyeongnam/ex/bbs/List.do?cbIdx=255
```

---

## 20. cceiGyeongnam

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
rnum
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/gyeongnam/allim/allim_list.do?div_code=1
```

---

## 21. gntp_sm

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
https://www.gntp.or.kr/biz/smartFactCont/
```

**공고 URL**:
```
https://www.gntp.or.kr/biz/smartFactory
```

---

## 22. cceiGyeongbuk

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/gyeongbuk/custom/notice_list.do?
```

---

## 23. gbtp

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://www.gbtp.or.kr/user/board.do?bbsId=BBSMSTR_000000000021
```

---

## 24. gipa

**도메인**: `www.gipa.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
no
```

**파싱된 파라미터 리스트**: `['no']`

### DB 데이터

**key_params**: `['cate', 'no', 'term']`

### 차이점

**DB에만 있음**: `['term', 'cate']`

### 공고 URL

```
https://www.gipa.or.kr/apply/01.php?cate=1
```

---

## 25. moel

**도메인**: `www.moel.go.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['bbs_seq']`

### 차이점

**DB에만 있음**: `['bbs_seq']`

### 공고 URL

```
https://www.moel.go.kr/news/notice/noticeList.do
```

---

## 26. gwangyangc

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://gwangyangcci.korcham.net/front/board/boardContentsListPage.do?boardId=10836&menuId=2059
```

---

## 27. mss4

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/gwangju/ex/bbs/List.do?cbIdx=251
```

---

## 28. gjep

**도메인**: `www.gjep.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
dk_id
```

**파싱된 파라미터 리스트**: `['dk_id']`

### DB 데이터

**key_params**: `['dk_cms', 'dk_id']`

### 차이점

**DB에만 있음**: `['dk_cms']`

### 공고 URL

```
https://www.gjep.or.kr/cms/bbs/cms.php?dk_cms=comm_01
```

---

## 29. gitct

**도메인**: `www.gicon.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
list_no
```

**파싱된 파라미터 리스트**: `['list_no']`

### DB 데이터

**key_params**: `['bid', 'mid']`

### 차이점

**Excel에만 있음**: `['list_no']`

**DB에만 있음**: `['mid', 'bid']`

### 공고 URL

```
https://www.gicon.or.kr/board.es?mid=a10204000000&bid=0003
```

---

## 30. cceiGwangju

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/gwangju/custom/notice_list.do?
```

---

## 31. gitp

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bsnssId
```

**공고 URL**:
```
https://www.gjtp.or.kr/home/business.cs
```

---

## 32. geri

**도메인**: `geri.re.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
board_idx
```

**파싱된 파라미터 리스트**: `['board_idx']`

### DB 데이터

**key_params**: `['board_id', 'board_idx']`

### 차이점

**DB에만 있음**: `['board_id']`

### 공고 URL

```
https://geri.re.kr/html/board_list.asp?board_id=business
```

---

## 33. bizinfo

**도메인**: `www.bizinfo.go.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['bltSeq', 'pblancId']`

### 차이점

**DB에만 있음**: `['pblancId', 'bltSeq']`

### 공고 URL

```
API연계
```

---

## 34. epis7

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://www.epis.or.kr/board/list?boardManagementNo=7&level=2&menuNo=7&enYn=N
```

---

## 35. mss3

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/daegu/ex/bbs/List.do?cbIdx=253
```

---

## 36. dgmif

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://www.kmedihub.re.kr/index.do?menu_id=00000063
```

---

## 37. cceiDaeGu

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/daegu/custom/notice_list.do?
```

---

## 38. dgtp

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://dgtp.or.kr/bbs/BoardControll.do?bbsId=BBSMSTR_000000000003
```

---

## 39. mss13

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/daejeon/ex/bbs/List.do?cbIdx=248
```

---

## 40. djbaInfo

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
TSK_PBNC_ID
```

**공고 URL**:
```
https://www.djbea.or.kr/pms/an/an_0101/list
```

---

## 41. djbaAnnc

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
BBSCTT_SEQ
```

**공고 URL**:
```
https://www.djbea.or.kr/pms/st/st_0205/list
```

---

## 42. dicia

**도메인**: `www.dicia.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
nttIdx
```

**파싱된 파라미터 리스트**: `['nttIdx']`

### DB 데이터

**key_params**: `['contentSubMode', 'menuIdx', 'nttIdx']`

### 차이점

**DB에만 있음**: `['contentSubMode', 'menuIdx']`

### 공고 URL

```
https://www.dicia.or.kr/sub.do;jsessionid=2A64958CBD7EF4D3110AFE9D2BF94252.tomcat?menuIdx=MENU_000000000000055
```

---

## 43. cceiDaejeon

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/daejeon/custom/notice_list.do?&sPtime=all&page=1
```

---

## 44. kotra

**도메인**: `kotra.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['cpbizYn', 'dtlBizId']`

### 차이점

**DB에만 있음**: `['cpbizYn', 'dtlBizId']`

### 공고 URL

```
https://www.kotra.or.kr/subList/41000022001
```

---

## 45. mcst

**도메인**: `www.mcst.go.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['pSeq']`

### 차이점

**DB에만 있음**: `['pSeq']`

### 공고 URL

```
https://www.mcst.go.kr/kor/s_notice/notice/noticeList.jsp
```

---

## 46. iris

**도메인**: `www.iris.go.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['ancmId']`

### 차이점

**DB에만 있음**: `['ancmId']`

### 공고 URL

```
https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do
```

---

## 47. busan

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
https://www.busan.go.kr/nongup/agricommunity11/
```

**공고 URL**:
```
https://www.busan.go.kr/nongup/agricommunity11
```

---

## 48. bcci

**도메인**: `www.bcci.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
idx
```

**파싱된 파라미터 리스트**: `['idx']`

### DB 데이터

**key_params**: `['idx', 'pCode']`

### 차이점

**DB에만 있음**: `['pCode']`

### 공고 URL

```
https://www.bcci.or.kr/kr/index.php?pCode=notice
```

---

## 49. busanit

**도메인**: `www.busanit.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
bidx
```

**파싱된 파라미터 리스트**: `['bidx']`

### DB 데이터

**key_params**: `['bcode', 'bidx']`

### 차이점

**DB에만 있음**: `['bcode']`

### 공고 URL

```
http://www.busanit.or.kr/board/list.asp?bcode=notice
```

---

## 50. mss2

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/busan/ex/bbs/List.do?cbIdx=256
```

---

## 51. cceiBusan

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/busan/custom/notice_list.do?
```

---

## 52. btp

**도메인**: `www.btp.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
board_seq
```

**파싱된 파라미터 리스트**: `['board_seq']`

### DB 데이터

**key_params**: `['board_seq', 'mCode', 'mgr_seq', 'mode']`

### 차이점

**DB에만 있음**: `['mgr_seq', 'mode', 'mCode']`

### 공고 URL

```
https://www.btp.or.kr/kor/CMS/Board/Board.do?mCode=MN013
```

---

## 53. cceiBitgaram

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/bitgaram/custom/notice_list.do?
```

---

## 54. motiego

**도메인**: `www.motie.go.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['rowPageC', 'schClear', 'searchCondition']`

### 차이점

**DB에만 있음**: `['rowPageC', 'schClear', 'searchCondition']`

### 공고 URL

```
https://www.motie.go.kr/kor/article/ATCL2826a2625
```

---

## 55. motie

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://www.motie.go.kr/ftz/yulchon/notification/notice/bbs/bbsList.do?bbs_cd_n=117
```

---

## 56. seoulsbdc

**도메인**: `www.seoulsbdc.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['infoSeq']`

### 차이점

**DB에만 있음**: `['infoSeq']`

### 공고 URL

```
https://www.seoulsbdc.or.kr/Notice/list.do
```

---

## 57. gbmakers

**도메인**: `gbmakers.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
idx
```

**파싱된 파라미터 리스트**: `['idx']`

### DB 데이터

**key_params**: `['bmode', 'idx', 't']`

### 차이점

**DB에만 있음**: `['t', 'bmode']`

### 공고 URL

```
https://gbmakers.or.kr/notice?category=
```

---

## 58. mss1

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/seoul/ex/bbs/List.do?cbIdx=146
```

---

## 59. cceiseoul

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/seoul/allim/allim_list.do?div_code=1
```

---

## 60. cceiSejong

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/sejong/custom/notice_list.do?
```

---

## 61. yemi

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bbs_data
```

**공고 URL**:
```
https://mybiz.yipa.or.kr/yipa/bbs_list.do?code=sub01b&keyvalue=sub01
```

---

## 62. uepa

**도메인**: `www.ubpi.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
no
```

**파싱된 파라미터 리스트**: `['no']`

### DB 데이터

**key_params**: `['mcode', 'no']`

### 차이점

**DB에만 있음**: `['mcode']`

### 공고 URL

```
https://www.ubpi.or.kr/sub/?mcode=0403010000
```

---

## 63. mss7

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/ulsan/ex/bbs/List.do?cbIdx=254
```

---

## 64. cceiUlsan

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/ulsan/custom/notice_list.do?
```

---

## 65. incheon

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://incheon.korcham.net/front/board/boardContentsListPage.do?boardId=51228&menuId=10130
```

---

## 66. mss6

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/incheon/ex/bbs/List.do?cbIdx=246
```

---

## 67. cceiIncheon

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/incheon/custom/notice_list.do?
```

---

## 68. debc

**도메인**: `www.debc.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
wr_id
```

**파싱된 파라미터 리스트**: `['wr_id']`

### DB 데이터

**key_params**: `['bo_table', 'wr_id']`

### 차이점

**DB에만 있음**: `['bo_table']`

### 공고 URL

```
https://www.debc.or.kr/bbs/board.php?bo_table=s2_2
```

---

## 69. seoulRndb

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
seqNo
```

**공고 URL**:
```
https://seoul.rnbd.kr/client/c030100/c030100_00.jsp
```

---

## 70. cceiJeonnam

**도메인**: `ccei.creativekorea.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
no
```

**파싱된 파라미터 리스트**: `['no']`

### DB 데이터

**key_params**: `['no', 'sPtime']`

### 차이점

**DB에만 있음**: `['sPtime']`

### 공고 URL

```
https://ccei.creativekorea.or.kr/jeonnam/custom/notice_list.do?
```

---

## 71. jntp

**도메인**: `www.jntp.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
announcement
```

**파싱된 파라미터 리스트**: `['announcement']`

### DB 데이터

**key_params**: `['announcement', 'menuLevel', 'menuNo']`

### 차이점

**DB에만 있음**: `['menuLevel', 'menuNo']`

### 공고 URL

```
https://www.jntp.or.kr/base/apiAnnouncement/List?menuLevel=2&menuNo=45
```

---

## 72. jepa

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bs_idx
```

**공고 URL**:
```
https://www.jepa.kr/bbs/?b_id=notice&site=new_jepa&mn=426
```

---

## 73. mss10

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/jeonbuk/ex/bbs/List.do?cbIdx=250
```

---

## 74. cceijeonbuk

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/jeonbuk/custom/notice_list.do?&page=1
```

---

## 75. jbtp

**도메인**: `www.jbtp.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
dataSid
```

**파싱된 파라미터 리스트**: `['dataSid']`

### DB 데이터

**key_params**: `['boardId', 'dataSid', 'menuCd']`

### 차이점

**DB에만 있음**: `['boardId', 'menuCd']`

### 공고 URL

```
https://www.jbtp.or.kr/board/list.jbtp?boardId=BBS_0000006&menuCd=DOM_000000102001000000&contentsSid=9&cpath=
```

---

## 76. jbba

**도메인**: `www.jbba.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
wr_id
```

**파싱된 파라미터 리스트**: `['wr_id']`

### DB 데이터

**key_params**: `['bo_table', 'wr_id']`

### 차이점

**DB에만 있음**: `['bo_table']`

### 공고 URL

```
https://www.jbba.kr/bbs/board.php?bo_table=sub01_09
```

---

## 77. jccia

**도메인**: `www.jcon.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
nttId
```

**파싱된 파라미터 리스트**: `['nttId']`

### DB 데이터

**key_params**: `['bbsId', 'nttId']`

### 차이점

**DB에만 있음**: `['bbsId']`

### 공고 URL

```
https://www.jcon.or.kr/board/list.php?bbsId=BBSMSTR_000000000001&pageId=C000000016
```

---

## 78. jica

**도메인**: `www.jica.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
no
```

**파싱된 파라미터 리스트**: `['no']`

### DB 데이터

**key_params**: `['mode', 'no', 'sMenu']`

### 차이점

**DB에만 있음**: `['mode', 'sMenu']`

### 공고 URL

```
https://www.jica.or.kr/2025/inner.php?sMenu=A1000
```

---

## 79. cceiJeju

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/jeju/custom/notice_list.do?
```

---

## 80. kbiz

**도메인**: `www.kbiz.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
seq
```

**파싱된 파라미터 리스트**: `['seq']`

### DB 데이터

**key_params**: `['mnSeq', 'seq']`

### 차이점

**DB에만 있음**: `['mnSeq']`

### 공고 URL

```
https://www.kbiz.or.kr/ko/contents/bbs/list.do?mnSeq=211&schFld=whle&schTxt=%EC%82%AC%EC%97%85%EA%B3%B5%EA%B3%A0
```

---

## 81. sme

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
API연계
```

---

## 82. mss0

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/smba/ex/bbs/List.do?cbIdx=310
```

---

## 83. ripc

**도메인**: `pms.ripc.org`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
selectedBoardSeq
```

**파싱된 파라미터 리스트**: `['selectedBoardSeq']`

### DB 데이터

**key_params**: `['boardCategoryCode', 'selectedBoardSeq']`

### 차이점

**DB에만 있음**: `['boardCategoryCode']`

### 공고 URL

```
https://pms.ripc.org/www/portal/notice/boardList.do?boardCategoryCode=BD40000
```

---

## 84. kstartup

**도메인**: `www.k-startup.go.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['pbancSn']`

### 차이점

**DB에만 있음**: `['pbancSn']`

### 공고 URL

```
API연계
```

---

## 85. changwon

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://www.changwon.go.kr/cwportal/10310/10429/10430.web
```

---

## 86. cheongjucci

**도메인**: `cheongjucci.korcham.net`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['boardId', 'contId', 'menuId']`

### 차이점

**DB에만 있음**: `['menuId', 'boardId', 'contId']`

### 공고 URL

```
https://cheongjucci.korcham.net/front/board/boardContentsListPage.do?boardId=10701&menuId=1561
```

---

## 87. cnsinbo

**도메인**: `www.cnsinbo.co.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
boardSeq
```

**파싱된 파라미터 리스트**: `['boardSeq']`

### DB 데이터

**key_params**: `['boardID', 'boardSeq', 'lev', 's']`

### 차이점

**DB에만 있음**: `['lev', 's', 'boardID']`

### 공고 URL

```
https://www.cnsinbo.co.kr/boardCnts/list.do?boardID=134&m=030101&s=cnsinbo
```

---

## 88. mss12

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/chungnam/ex/bbs/List.do?cbIdx=315
```

---

## 89. cceiChungnam

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/chungnam/custom/notice_list.do?&sPtime=all&page=1
```

---

## 90. cbist

**도메인**: `www.cbist.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
no
```

**파싱된 파라미터 리스트**: `['no']`

### DB 데이터

**key_params**: `['mncd', 'mode', 'no']`

### 차이점

**DB에만 있음**: `['mode', 'mncd']`

### 공고 URL

```
http://www.cbist.or.kr/home/sub.do?mncd=1131
```

---

## 91. mss9

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
bcIdx
parentSeq
```

**공고 URL**:
```
https://www.mss.go.kr/site/chungbuk/ex/bbs/List.do?cbIdx=249
```

---

## 92. cceiChungbuk

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/chungbuk/custom/notice_list.do?
```

---

## 93. cbtp

**도메인**: `www.cbtp.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
no
```

**파싱된 파라미터 리스트**: `['no']`

### DB 데이터

**key_params**: `['board_id', 'no']`

### 차이점

**DB에만 있음**: `['board_id']`

### 공고 URL

```
https://www.cbtp.or.kr/index.php?control=bbs&board_id=saup_notice&lm_uid=387
```

---

## 94. cba

**도메인**: `www.cba.ne.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
no
```

**파싱된 파라미터 리스트**: `['no']`

### DB 데이터

**key_params**: `['menukey', 'mod', 'no']`

### 차이점

**DB에만 있음**: `['mod', 'menukey']`

### 공고 URL

```
https://www.cba.ne.kr/home/sub.php?menukey=172
```

---

## 95. cceiPohang

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
no
```

**공고 URL**:
```
https://ccei.creativekorea.or.kr/pohang/custom/notice_list.do?&sPtime=my&page=1
```

---

## 96. fact

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
https://www.koat.or.kr/board/business/
```

**공고 URL**:
```
https://www.koat.or.kr/board/business/list.do
```

---

## 97. kca

**도메인**: `www.kca.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
seq
```

**파싱된 파라미터 리스트**: `['seq']`

### DB 데이터

**key_params**: `['boardId', 'movePage', 'seq']`

### 차이점

**DB에만 있음**: `['movePage', 'boardId']`

### 공고 URL

```
https://www.kca.kr/boardList.do?boardId=NOTICE&pageId=www47
```

---

## 98. bokji1

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://www.bokji.net/not/biz/01.bokji
```

---

## 99. kicox

**도메인**: `www.kicox.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
q_bbscttSn
```

**파싱된 파라미터 리스트**: `['q_bbscttSn']`

### DB 데이터

**key_params**: `['q_bbsCode', 'q_bbscttSn']`

### 차이점

**DB에만 있음**: `['q_bbsCode']`

### 공고 URL

```
https://www.kicox.or.kr/user/bbs/BD_selectBbsList.do?q_bbsCode=1016
```

---

## 100. kitech

**도메인**: `www.kitech.re.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['idx']`

### 차이점

**DB에만 있음**: `['idx']`

### 공고 URL

```
https://www.kitech.re.kr/research/page1-1.php
```

---

## 101. energy

**도메인**: `www.energy.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['boardMngNo', 'boardNo']`

### 차이점

**DB에만 있음**: `['boardNo', 'boardMngNo']`

### 공고 URL

```
https://www.energy.or.kr/front/board/List2.do
```

---

## 102. kofpi1

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://www.kofpi.or.kr/notice/notice_01.do
```

---

## 103. kofpi2

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```

```

**공고 URL**:
```
https://www.kofpi.or.kr/notice/notice_02.do
```

---

## 104. keti

**도메인**: `www.keti.re.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
idx
```

**파싱된 파라미터 리스트**: `['idx']`

### DB 데이터

**key_params**: `['at', 'idx', 'sp']`

### 차이점

**DB에만 있음**: `['sp', 'at']`

### 공고 URL

```
https://www.keti.re.kr/notice/notice.php
```

---

## 105. kocca

**도메인**: `www.kocca.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
intcNo
```

**파싱된 파라미터 리스트**: `['intcNo']`

### DB 데이터

**key_params**: `['intcNo', 'menuNo']`

### 차이점

**DB에만 있음**: `['menuNo']`

### 공고 URL

```
https://www.kocca.kr/kocca/pims/list.do?menuNo=204104
```

---

## 106. ttp

**문제**: DB에 존재하지 않음

**Excel URL 파라미터**:
```
http://www.technopark.kr/businessboard/
```

**공고 URL**:
```
http://www.technopark.kr/businessboard
```

---

## 107. fintech

**도메인**: `fintech.or.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['board_id', 'contents_id']`

### 차이점

**DB에만 있음**: `['board_id', 'contents_id']`

### 공고 URL

```
https://fintech.or.kr/web/board/boardContentsListPage.do?board_id=3&menu_id=6300&miv_pageNo=
```

---

## 108. keiti

**도메인**: `keiti.re.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
bcIdx
```

**파싱된 파라미터 리스트**: `['bcIdx']`

### DB 데이터

**key_params**: `['bcIdx', 'cbIdx']`

### 차이점

**DB에만 있음**: `['cbIdx']`

### 공고 URL

```
https://www.keiti.re.kr/site/keiti/ex/board/List.do?cbIdx=277&searchExt1=24000100
```

---

## 109. mof

**도메인**: `www.mof.go.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```
docSeq
```

**파싱된 파라미터 리스트**: `['docSeq']`

### DB 데이터

**key_params**: `['bbsSeq', 'docSeq', 'menuSeq']`

### 차이점

**DB에만 있음**: `['menuSeq', 'bbsSeq']`

### 공고 URL

```
https://www.mof.go.kr/doc/ko/selectDocList.do?menuSeq=375&bbsSeq=9&listUpdtDt=2025-04-07++10%3A00
```

---

## 110. me

**도메인**: `www.me.go.kr`

**문제**: key_params 불일치

### Excel 데이터

**원본 URL 파라미터**:
```

```

**파싱된 파라미터 리스트**: `[]`

### DB 데이터

**key_params**: `['boardId', 'menuId']`

### 차이점

**DB에만 있음**: `['menuId', 'boardId']`

### 공고 URL

```
https://www.me.go.kr/home/web/board/list.do?menuId=10524&boardMasterId=39&boardCategoryId=55
```

---

