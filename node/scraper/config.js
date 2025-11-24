/**
 * Node.js 스크래핑 시스템 설정 파일
 */

module.exports = {
    // 브라우저 설정
    browser: {
        // 헤드리스 모드 (안정성을 위해 "new" 권장)
        headless: "new",
        
        // 디버깅을 위한 헤드리스 모드 해제
        devMode: false,
        
        // Puppeteer 실행 옵션
        launchOptions: {
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage'
            ],
            timeout: 60000,
            ignoreHTTPSErrors: true
        },
        
        // 타임아웃 설정 (밀리초)
        timeouts: {
            navigation: 30000,
            default: 30000,
            waitFor: 10000
        }
    },
    
    // 재시도 설정
    retry: {
        maxRetries: 3,
        baseDelay: 2000,
        maxConsecutiveErrors: 5
    },
    
    // 요청 간격 설정
    delays: {
        betweenPages: 1000,
        betweenRequests: 500,
        afterError: 2000
    },
    
    // 기본 선택자
    selectors: {
        list: 'table tr',
        title: 'td:nth-child(2) a',
        date: 'td:last-child',
        
        // 상세 페이지 컨텐츠
        content: [
            '.content', 
            '.main', 
            '.article', 
            '.post',
            '#content', 
            '#main', 
            '#article', 
            '#post',
            '.board-content', 
            '.view-content'
        ],
        
        // 제거할 요소들
        exclude: [
            'header', 
            'nav', 
            'aside', 
            'footer',
            '.header', 
            '.nav', 
            '.sidebar', 
            '.footer',
            '.menu', 
            '.navigation', 
            '.breadcrumb',
            '.advertisement',
            '.ad',
            '.banner'
        ],
        
        // 날짜 선택자
        dateElements: [
            '.date', 
            '.reg-date', 
            '.write-date', 
            '.post-date',
            '[class*="date"]', 
            '[id*="date"]'
        ],
        
        // 첨부파일 선택자
        attachments: [
            'a[href*="download"]',
            'a[href*="file"]', 
            'a[href*="attach"]',
            'a[href*="upload"]',
            '.file-link',
            '.attachment'
        ]
    },
    
    // 날짜 형식들
    dateFormats: [
        'YYYY-MM-DD',
        'YYYY.MM.DD',
        'YYYY/MM/DD',
        'MM-DD-YYYY',
        'MM.DD.YYYY',
        'MM/DD/YYYY',
        'YYYY년 MM월 DD일',
        'YY-MM-DD',
        'YY.MM.DD'
    ],
    
    // 파일 확장자 필터
    fileExtensions: {
        allowed: ['.pdf', '.hwp', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.zip', '.rar'],
        blocked: ['.exe', '.bat', '.cmd', '.scr', '.com']
    },
    
    // 로그 설정
    logging: {
        level: 'info', // debug, info, warn, error
        saveToFile: false,
        filename: 'scraper.log'
    },
    
    // 사이트별 기본 설정
    siteConfigs: {
        // 안산상공회의소
        acci: {
            baseUrl: 'https://www.acci.or.kr',
            listPath: '/board/list',
            selectors: {
                list: '.board-list tbody tr',
                title: '.subject a',
                date: '.date'
            },
            encoding: 'utf-8'
        },
        
        // 중소기업기술혁신협회
        cbt: {
            baseUrl: 'https://www.cbt.or.kr',
            listPath: '/board/notice',
            selectors: {
                list: 'table.board-table tbody tr',
                title: 'td.title a',
                date: 'td.date'
            },
            encoding: 'utf-8'
        },
        
        // 일반적인 게시판 구조
        default: {
            selectors: {
                list: 'tbody tr',
                title: 'td:nth-child(2) a',
                date: 'td:last-child'
            },
            encoding: 'utf-8'
        }
    },
    
    // 성능 설정
    performance: {
        maxConcurrent: 1, // 동시 브라우저 인스턴스 수
        memoryThreshold: 1024 * 1024 * 500, // 500MB
        maxPageSize: 10 * 1024 * 1024, // 10MB
    },
    
    // 보안 설정
    security: {
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        respectRobots: true,
        maxRedirects: 5
    },

    // 데이터베이스 설정 (환경 변수에서 로드)
    database: {
        host: process.env.DB_HOST || 'localhost',
        port: parseInt(process.env.DB_PORT) || 3306,
        user: process.env.DB_USER || 'root',
        password: process.env.DB_PASSWORD || '',
        database: process.env.DB_NAME || 'subvention'
    }
};