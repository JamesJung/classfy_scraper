# 스크래퍼 제목 비교 로직 분석 보고서

생성 시간: 2025-09-30 22:18:17

## 요약
- 총 스크래퍼 수: 153개
- 제목 비교 로직 있음: 151개
- 제목 비교 로직 없음: 2개
- 날짜 비교 로직 있음: 143개

## 제목 비교 로직이 있는 스크래퍼

### andong
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### announcement
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### anseong
- 로직 유형: includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### anyang
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### boeun
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### boseong
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### buan
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### busan
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### changwon
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### cheongdo
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### cheongju
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### cheongyang
- 로직 유형: duplicate_check
- 예시:
  - duplicate_check: ['processedTitles']

### chilgok
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### chungbuk
- 로직 유형: exact_title_match, includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### chungju
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### chungnam
- 로직 유형: exact_title_match, includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### cng
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### cs
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### cwg
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### daegu
- 로직 유형: startsWith_endsWith, break_on_condition
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - break_on_condition: ['if (!titleLink) return']

### daejeon
- 로직 유형: startsWith_endsWith, break_on_condition
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - break_on_condition: ['if (!titleLink) return']

### ddc
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### djjunggu
- 로직 유형: includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### eminwon_detail
- 로직 유형: exact_title_match, break_on_condition
- 예시:
  - exact_title_match: ['title === ']
  - break_on_condition: ['if (result.title) break']

### eminwon
- 로직 유형: exact_title_match, duplicate_check
- 예시:
  - exact_title_match: ['Title === ']
  - duplicate_check: ['processedTitles', 'existingTitles']

### ep
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### eumseong
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gangbuk
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### ganghwa
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gangjin
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gangnam
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gb
- 로직 유형: exact_title_match, includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gbgs
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gbmg
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gc
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gccity
- 로직 유형: startsWith_endsWith
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]

### geochang
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### geoje
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### geumjeong
- 로직 유형: startsWith_endsWith, break_on_condition, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - break_on_condition: ['if (!titleElement || !dateElement) return']
  - duplicate_check: ['processedTitles']

### geumsan
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gg
- 로직 유형: exact_title_match, includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gimhae
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gimje
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gimpo
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gjcity
- 로직 유형: startsWith_endsWith
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]

### gm
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gn
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gochang
- 로직 유형: exact_title_match, includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gokseong
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### goryeong
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### goseong
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gp
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gumi
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gunwi
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### guri
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### guro
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gurye
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gwanak
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gwangjin
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gwangsan
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gwangyang
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gwd
- 로직 유형: exact_title_match, includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gwgs
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gyeongju
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### gyeongnam
- 로직 유형: exact_title_match, includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gyeryong
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### gyeyang
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### hadong
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### haenam
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### haman
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### hampyeong
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### hc
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### hongcheon
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### hongseong
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### hsg
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### icbp
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### icdonggu
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### icheon
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### inje
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### jangheung
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### jangseong
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### jecheon
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### jeju
- 로직 유형: startsWith_endsWith, regex_title, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - regex_title: ['title && noticeNo.match(']
  - duplicate_check: ['processedTitles', 'existingTitles']

### jeonbuk
- 로직 유형: exact_title_match, includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### jeonnam
- 로직 유형: exact_title_match, includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### jindo
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### jongno
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### jp
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### junggu
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### jungnang
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### mapo
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### michuhol
- 로직 유형: includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### mokpo
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### muan
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### naju
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### namdong
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### namhae
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### namwon
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### nowon
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### nyj
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### oc
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### ongjin
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### osan
- 로직 유형: startsWith_endsWith
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]

### paju
- 로직 유형: startsWith_endsWith
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]

### pocheon
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### pohang
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### pyeongtaek
- 로직 유형: startsWith_endsWith
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]

### sacheon
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['TITLE===', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### samcheok
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### sancheong
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['TITLE===', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### sb
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### sd
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### sdm
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### sejong
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### seo
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### seogu
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### seosan
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### seoul
- 로직 유형: includes_title, indexOf_title, break_on_condition
- 예시:
  - includes_title: ['title && fullText.includes(']
  - indexOf_title: ['titleIndex = fullText.indexOf(', 'Title.indexOf(']
  - break_on_condition: ['if (!titleLink) return']

### shinan
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### siheung
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### sj
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### songpa
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### suncheon
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### taebaek
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### tongyeong
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### ui4u
- 로직 유형: startsWith_endsWith
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]

### uiryung
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['TITLE===', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### uljin
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### ulju
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### ulleung
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### ulsan
- 로직 유형: exact_title_match, includes_title, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - includes_title: ['title && link.title.includes(']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### unified_detail
- 로직 유형: startsWith_endsWith
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]

### usc
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### wando
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### wonju
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### yangcheon
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### yanggu
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### yangsan
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### yc
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### yd21
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### yd
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### ydp
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### yeoju
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### yeongam
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### yeongdo
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### yeongju
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### yeonje
- 로직 유형: exact_title_match, startsWith_endsWith, duplicate_check
- 예시:
  - exact_title_match: ['Title === ', 'Title === ']
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles', 'existingTitles']

### yeosu
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### yongsan
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### yp21
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

### yyg
- 로직 유형: startsWith_endsWith, duplicate_check
- 예시:
  - startsWith_endsWith: [".startsWith('", ".startsWith('"]
  - duplicate_check: ['processedTitles']

## 제목 비교 로직이 없는 스크래퍼

- gwangju, incheon

## 날짜 비교 로직이 있는 스크래퍼

- andong, announcement, anseong, anyang, boeun, boseong, buan, busan, changwon, cheongdo
- cheongju, cheongyang, chilgok, chungbuk, chungju, chungnam, cng, cs, cwg, ddc
- djjunggu, eminwon, ep, eumseong, gangbuk, ganghwa, gangjin, gangnam, gb, gbgs
- gbmg, gc, gccity, geochang, geoje, geumjeong, geumsan, gg, gimhae, gimje
- gimpo, gjcity, gm, gn, gochang, gokseong, goryeong, goseong, gp, gumi
- gunwi, guri, guro, gurye, gwanak, gwangjin, gwangsan, gwangyang, gwd, gwgs
- gyeongju, gyeongnam, gyeryong, gyeyang, hadong, haenam, haman, hampyeong, hc, hongcheon
- hongseong, hsg, icbp, icdonggu, inje, jangheung, jangseong, jecheon, jeju, jeonbuk
- jeonnam, jindo, jongno, jp, junggu, jungnang, mapo, michuhol, mokpo, muan
- naju, namdong, namhae, namwon, nowon, oc, ongjin, osan, paju, pocheon
- pohang, pyeongtaek, sacheon, samcheok, sancheong, sb, sd, sdm, sejong, seo
- seogu, seosan, shinan, siheung, sj, suncheon, taebaek, tongyeong, ui4u, uiryung
- uljin, ulju, ulleung, ulsan, usc, wando, wonju, yangcheon, yanggu, yangsan
- yc, yd21, yd, ydp, yeoju, yeongam, yeongdo, yeongju, yeonje, yeosu
- yongsan, yp21, yyg
