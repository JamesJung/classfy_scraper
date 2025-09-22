#!/usr/bin/env node

/**
 * site_naver_url.csv 파일을 파싱하여 eminwon.json 생성
 * C열(최하위 기관명)을 키로, F열의 eminwon 호스트를 값으로 매핑
 */

const fs = require('fs');
const path = require('path');

function parseCSVToEminwon() {
    try {
        // CSV 파일 읽기
        const csvPath = path.join(__dirname, '../site_naver_url.csv');
        const csvContent = fs.readFileSync(csvPath, 'utf-8');
        
        const lines = csvContent.split('\n');
        const eminwonMapping = {};
        
        console.log('CSV 파일 파싱 시작...');
        console.log(`총 ${lines.length}개 라인 처리`);
        
        // 1단계: 모든 데이터 수집 및 중복 키 확인
        const dataRows = [];
        const keyCount = {};
        
        // 여러 줄에 걸친 CSV 항목 처리
        let currentRecord = '';
        let inQuotedField = false;
        
        for (let i = 1; i < lines.length; i++) {
            const line = lines[i];
            
            if (!inQuotedField && !line.trim()) continue;
            
            // 따옴표 개수 확인으로 여러 줄 필드 감지
            const quoteCount = (line.match(/"/g) || []).length;
            
            if (!inQuotedField) {
                // 새 레코드 시작
                currentRecord = line;
                if (quoteCount % 2 === 1) {
                    inQuotedField = true;
                } else {
                    // 단일 라인 레코드 처리
                    processRecord(currentRecord);
                }
            } else {
                // 여러 줄 필드 계속
                currentRecord += '\\n' + line;
                if (quoteCount % 2 === 1) {
                    inQuotedField = false;
                    processRecord(currentRecord);
                }
            }
        }
        
        function processRecord(record) {
            const columns = parseCSVLine(record);
            if (columns.length < 6) return;
            
            const fullRegionName = columns[1]; // B열: 전체 기관명
            const regionName = columns[2]; // C열: 최하위 기관명
            const siteData = columns[5]; // F열: 고시공고 사이트 주소
            
            if (!regionName || !siteData) return;
            
            const eminwonHosts = extractEminwonHosts(siteData);
            if (eminwonHosts.length > 0) {
                // 메인 데이터 추가
                dataRows.push({
                    fullRegionName,
                    regionName,
                    primaryHost: eminwonHosts[0],
                    additionalHosts: eminwonHosts.slice(1)
                });
                
                keyCount[regionName] = (keyCount[regionName] || 0) + 1;
                
                // 광역시인 경우, 산하 구청 eminwon 호스트들도 개별 항목으로 추가
                if (fullRegionName.includes('광역시') && eminwonHosts.length > 1) {
                    for (const host of eminwonHosts) {
                        const districtInfo = extractDistrictFromHost(host, fullRegionName);
                        if (districtInfo) {
                            dataRows.push({
                                fullRegionName: districtInfo.fullName,
                                regionName: districtInfo.district,
                                primaryHost: host,
                                additionalHosts: []
                            });
                            
                            keyCount[districtInfo.district] = (keyCount[districtInfo.district] || 0) + 1;
                        }
                    }
                }
            }
        }
        
        console.log('중복 키 분석 완료:');
        const duplicateKeys = Object.keys(keyCount).filter(key => keyCount[key] > 1);
        console.log('중복되는 키들:', duplicateKeys);
        
        // 2단계: 키 중복을 해결하면서 매핑 생성
        for (const row of dataRows) {
            let finalKey = row.regionName;
            
            // 중복되는 키인 경우 축약 키 생성
            if (keyCount[row.regionName] > 1) {
                finalKey = createAbbreviatedKey(row.fullRegionName, row.regionName);
                console.log(`중복 키 해결: ${row.regionName} -> ${finalKey} (${row.fullRegionName})`);
            }
            
            eminwonMapping[finalKey] = row.primaryHost;
            console.log(`${finalKey}: ${row.primaryHost}`);
            
            if (row.additionalHosts.length > 0) {
                console.log(`  추가 호스트: ${row.additionalHosts.join(', ')}`);
            }
        }
        
        // 광역시/도 및 누락 지역 수동 추가
        console.log('\n광역시/도 및 누락 지역 수동 추가:');
        const manualMappings = {
            '서울특별시': 'eminwon.gangseo.seoul.kr',
            '부산광역시': 'eminwon.bsgangseo.go.kr', 
            '인천광역시': 'eminwon.icjg.go.kr',
            '광주광역시': 'eminwon.bukgu.gwangju.kr',
            '대전광역시': 'eminwon.seogu.go.kr',
            '울산광역시': 'eminwon.ulsannamgu.go.kr'
        };
        
        for (const [region, host] of Object.entries(manualMappings)) {
            if (!eminwonMapping[region]) {
                eminwonMapping[region] = host;
                console.log(`${region}: ${host} (수동 추가)`);
            }
        }
        
        // JSON 파일로 저장
        const outputPath = path.join(__dirname, 'eminwon.json');
        fs.writeFileSync(outputPath, JSON.stringify(eminwonMapping, null, 4), 'utf-8');
        
        console.log(`\n완료! ${Object.keys(eminwonMapping).length}개 지역의 eminwon 호스트 정보를 eminwon.json에 저장했습니다.`);
        console.log(`출력 파일: ${outputPath}`);
        
        return eminwonMapping;
        
    } catch (error) {
        console.error('CSV 파싱 중 오류:', error.message);
        throw error;
    }
}

/**
 * CSV 라인을 파싱 (따옴표 처리 포함)
 */
function parseCSVLine(line) {
    const result = [];
    let current = '';
    let inQuotes = false;
    
    for (let i = 0; i < line.length; i++) {
        const char = line[i];
        
        if (char === '"') {
            inQuotes = !inQuotes;
        } else if (char === ',' && !inQuotes) {
            result.push(current.trim());
            current = '';
        } else {
            current += char;
        }
    }
    
    // 마지막 컬럼 추가
    result.push(current.trim());
    
    return result;
}

/**
 * 호스트에서 구청 정보 추출
 * 예: "eminwon.seogu.go.kr" + "대전광역시" -> {district: "서구", fullName: "대전광역시 서구"}
 */
function extractDistrictFromHost(host, cityName) {
    const hostPatterns = {
        'seogu': '서구',
        'donggu': '동구', 
        'junggu': '중구',
        'djjunggu': '중구',
        'bsjunggu': '중구',
        'jung': '중구',
        'namgu': '남구',
        'bsnamgu': '남구',
        'nam': '남구',
        'bukgu': '북구',
        'bsbukgu': '북구',
        'buk': '북구',
        'bsdonggu': '동구',
        'dong': '동구',
        'bsseogu': '서구',
        'bsgangseo': '강서구',
        'gangseo': '강서구',
        'daedeok': '대덕구',
        'yuseong': '유성구',
        'dalseong': '달성군',
        'dalseo': '달서구',
        'haeundae': '해운대구',
        'sasang': '사상구',
        'busanjin': '부산진구',
        'yeongdo': '영도구',
        'geumjeong': '금정구'
    };
    
    for (const [pattern, districtName] of Object.entries(hostPatterns)) {
        if (host.includes(pattern)) {
            return {
                district: districtName,
                fullName: `${cityName} ${districtName}`
            };
        }
    }
    
    return null;
}

/**
 * B열 정보를 사용하여 축약된 키 생성
 * 예: "인천광역시 동구" -> "인천동구"
 */
function createAbbreviatedKey(fullRegionName, regionName) {
    if (!fullRegionName) return regionName;
    
    // 광역시/도 정보 추출
    const regionPrefixes = [
        '서울특별시', '부산광역시', '대구광역시', '인천광역시', 
        '광주광역시', '대전광역시', '울산광역시', '세종특별자치시',
        '경기도', '강원특별자치도', '충청북도', '충청남도', 
        '전북특별자치도', '전라남도', '경상북도', '경상남도', '제주특별자치도'
    ];
    
    for (const prefix of regionPrefixes) {
        if (fullRegionName.includes(prefix)) {
            // "인천광역시 동구" -> "인천동구"
            let abbreviated = prefix.replace(/(특별시|광역시|특별자치시|특별자치도|도)$/, '');
            return abbreviated + regionName;
        }
    }
    
    // 매칭되지 않는 경우 전체 이름 사용
    return fullRegionName.replace(/\s+/g, '');
}

/**
 * 사이트 데이터에서 eminwon 호스트들 추출
 */
function extractEminwonHosts(siteData) {
    const eminwonHosts = [];
    
    if (!siteData) return eminwonHosts;
    
    // 개행 문자나 탭으로 분리된 항목들을 처리
    const items = siteData.split(/[\n\t]+/);
    
    for (const item of items) {
        const trimmed = item.trim();
        
        // 숫자 + 호스트 형태 (예: "37	eminwon.gangseo.seoul.kr")에서 호스트만 추출
        const hostMatch = trimmed.match(/^\d+\s+(.+)$/);
        let host = hostMatch ? hostMatch[1].trim() : trimmed;
        
        // eminwon이 포함된 호스트만 선택
        if (host.includes('eminwon')) {
            // http:// 또는 https:// 제거
            host = host.replace(/^https?:\/\//, '');
            // 경로 제거 (호스트명만 남기기)
            host = host.split('/')[0];
            // 불필요한 부가 정보 제거 (줄바꿈, 숫자 등)
            host = host.replace(/\\n.*$/, '').trim();
            
            if (host && !eminwonHosts.includes(host)) {
                eminwonHosts.push(host);
            }
        }
    }
    
    return eminwonHosts;
}

// 스크립트가 직접 실행될 때만 함수 호출
if (require.main === module) {
    parseCSVToEminwon();
}

module.exports = { parseCSVToEminwon };