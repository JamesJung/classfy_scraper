const mysql = require('mysql2/promise');
const csv = require('csv-parser');
const createCsvWriter = require('csv-writer').createObjectCsvWriter;
const fs = require('fs');
const axios = require('axios');
const cheerio = require('cheerio');
const { URL } = require('url');
const { chromium } = require('playwright');

// Database configuration
const dbConfig = {
  host: '192.168.0.95',
  user: 'root',
  password: 'b3UvSDS232GbdZ42',
  port: 3309,
  database: 'naver_submission_20250908'
};

class NaverUrlScraper {
  constructor() {
    this.connection = null;
    this.csvData = [];
    this.results = [];
    this.browser = null;
    this.context = null;
    this.csvWriter = null;
    this.csvInitialized = false;
  }

  async init() {
    try {
      // Connect to database
      this.connection = await mysql.createConnection(dbConfig);
      console.log('Database connected successfully');

      // Initialize browser
      this.browser = await chromium.launch({
        headless: true,
        timeout: 60000
      });
      this.context = await this.browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
      });
      console.log('Browser initialized successfully');

      // Initialize CSV Writer
      this.csvWriter = createCsvWriter({
        path: 'scraping_results.csv',
        header: [
          { id: 'siteName', title: 'Site Name' },
          { id: 'originalUrl', title: 'Original URL' },
          { id: 'hostName', title: 'Host Name' },
          { id: 'currentDetailUrl', title: 'Current Detail URL' },
          { id: 'foundUrl', title: 'Found URL' },
          { id: 'urlType', title: 'URL Type' },
          { id: 'linkText', title: 'Link Text' }
        ]
      });

      // Read CSV file
      await this.readCsvFile();

    } catch (error) {
      console.error('Initialization error:', error);
      throw error;
    }
  }

  async readCsvFile() {
    const csvFile = 'naver_prv_url.csv'; // Will check for this file

    try {
      // Check if naver_prv_url.csv exists, if not use sitelist_orgin.csv as fallback
      const fileExists = fs.existsSync(csvFile);
      const fileToRead = fileExists ? csvFile : 'sitelist_orgin.csv';

      console.log(`Reading CSV file: ${fileToRead}`);

      return new Promise((resolve, reject) => {
        this.csvData = [];
        fs.createReadStream(fileToRead)
          .pipe(csv())
          .on('data', (row) => {
            // For naver_prv_url.csv: B열 = site name, C열 = URL
            // For sitelist_orgin.csv: site_name, start_url
            const siteName = row.site_name || row.B || Object.values(row)[1];
            const url = row.start_url || row.C || Object.values(row)[2];

            if (siteName && url) {
              this.csvData.push({
                siteName: siteName.trim(),
                url: url.trim()
              });
            }
          })
          .on('end', () => {
            console.log(`CSV file read successfully. Found ${this.csvData.length} entries`);
            resolve();
          })
          .on('error', reject);
      });
    } catch (error) {
      console.error('Error reading CSV file:', error);
      throw error;
    }
  }

  async executeQuery(siteName, hostName) {
    const query = `
      SELECT reception_institution_name, title_name, url_address, 
             SUBSTRING_INDEX(SUBSTRING_INDEX(url_address, '//', -1), '/', 1) as host_name 
      FROM sme_subvention ss, sme_subvention_detail ssd  
      WHERE ss.sme_subvention_id = ssd.sme_subvention_id 
        AND ss.sme_subvention_id LIKE 'prv%'
        AND reception_institution_name LIKE ?
        AND SUBSTRING_INDEX(SUBSTRING_INDEX(url_address, '//', -1), '/', 1) = ?
        order by notice_date  desc
        limit 1

    `;

    try {
      const [rows] = await this.connection.execute(query, [`%${siteName}%`, hostName]);
      console.log(`Found ${rows.length} URLs for ${siteName} (${hostName})`);
      return rows;
    } catch (error) {
      console.error(`Query error for ${siteName}:`, error);
      return [];
    }
  }

  async extractHostName(url) {
    console.log("extractHostName : URL", url)
    try {
      // 1. URL에 프로토콜이 없을 경우, HTTPS를 먼저 붙여서 시도
      let correctedUrl = url.includes('://') ? url : `https://${url}`;
      const response = await fetch(correctedUrl);

      // 성공하면 호스트명 반환
      return new URL(response.url).hostname;

    } catch (httpsError) {
      // 2. HTTPS 시도에 실패하면, HTTP로 재시도
      try {
        const httpUrl = `http://${url}`;
        const response = await fetch(httpUrl);

        // 성공하면 호스트명 반환
        return new URL(response.url).hostname;
      } catch (httpError) {
        // HTTP 시도도 실패하면 에러를 반환
        console.error(`Error fetching URL: ${url}`);
        return null;
      }
    }
  }

  async findAnnouncementBoard(hostName) {
    try {
      const baseUrl = `https://${hostName}`;
      console.log(`Exploring ${baseUrl} for announcement boards...`);

      const response = await axios.get(baseUrl, {
        timeout: 10000,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
      });

      const $ = cheerio.load(response.data);
      const announcementUrls = [];

      // Search for common announcement board keywords
      const keywords = ['공고', '고시', '게시판', 'notice', 'announcement', 'board'];

      $('a').each((i, element) => {
        const href = $(element).attr('href');
        const text = $(element).text().trim();

        if (href && text) {
          for (const keyword of keywords) {
            if (text.includes(keyword)) {
              let fullUrl = href;
              if (href.startsWith('/')) {
                fullUrl = baseUrl + href;
              } else if (!href.startsWith('http')) {
                fullUrl = baseUrl + '/' + href;
              }

              announcementUrls.push({
                text: text,
                url: fullUrl
              });
              break;
            }
          }
        }
      });

      console.log(`Found ${announcementUrls.length} potential announcement board URLs`);
      return announcementUrls;

    } catch (error) {
      console.error(`Error exploring ${hostName}:`, error.message);
      return [];
    }
  }

  async analyzeUrlForListButton(url) {
    const page = await this.context.newPage();

    try {
      console.log("#############analyzeUrlForListButton (Playwright)#####################");
      console.log(`Analyzing ${url} for list buttons...`);

      // Ensure URL has protocol
      let validUrl = url;
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        validUrl = `https://${url}`;
        console.log(`Added HTTPS protocol: ${validUrl}`);
      }


      console.log("validUrl================", validUrl)
      // Navigate to the page
      try {
        await page.goto(validUrl, {
          waitUntil: 'networkidle',
          timeout: 30000
        });
      } catch (httpsError) {
        // If HTTPS fails, try HTTP
        if (validUrl.startsWith('https://')) {
          const httpUrl = validUrl.replace('https://', 'http://');
          console.log(`HTTPS failed, trying HTTP: ${httpUrl}`);
          await page.goto(httpUrl, {
            waitUntil: 'networkidle',
            timeout: 30000
          });
          validUrl = httpUrl;
        } else {
          throw httpsError;
        }
      }

      // Wait for content to load
      await page.waitForTimeout(3000);

      const listUrls = [];

      // Find all clickable elements with list keywords
      const elements = await page.evaluate(() => {
        const results = [];
        const clickableElements = document.querySelectorAll('a, button, [onclick], [role="button"]');

        // 정확한 매칭을 위한 함수 (브라우저 내부에서 실행)
        const isExactListMatch = (text) => {
          const trimmedText = text.trim();
          const listKeywords = ['목록', 'list', '리스트', '전체보기', 'more', '목록보기'];

          // 정확히 일치하는 경우
          if (listKeywords.includes(trimmedText)) return true;

          // "목록"의 경우 단독으로 존재하는지 확인 (앞뒤 공백이나 괄호 포함 가능)
          const listPattern = /^[\s\[\(]*목록[\s\]\)]*$/;
          if (listPattern.test(trimmedText)) return true;

          // "list"의 경우도 마찬가지
          const listEnPattern = /^[\s\[\(]*list[\s\]\)]*$/i;
          if (listEnPattern.test(trimmedText)) return true;

          return false;
        };

        clickableElements.forEach((element, index) => {
          const text = element.textContent.trim();
          const href = element.href;
          const onclick = element.getAttribute('onclick');

          if (text && isExactListMatch(text)) {
            results.push({
              index,
              text,
              href,
              onclick,
              tagName: element.tagName,
              className: element.className
            });
          }
        });

        return results;
      });

      console.log(`Found ${elements.length} potential list buttons`);

      // Click each element and capture the resulting URL
      for (const element of elements) {
        try {
          console.log(`Attempting to click: "${element.text}" (${element.tagName})`);

          // Get current URL before click
          const beforeUrl = page.url();

          // Click the element using various methods
          let clicked = false;

          try {
            // Method 1: Direct click by text
            await page.click(`text=${element.text}`, { timeout: 5000 });
            clicked = true;
          } catch (e1) {
            try {
              // Method 2: Click by selector if we can find it
              const selector = `${element.tagName.toLowerCase()}:has-text("${element.text}")`;
              await page.click(selector, { timeout: 5000 });
              clicked = true;
            } catch (e2) {
              try {
                // Method 3: Evaluate onclick if available
                if (element.onclick) {
                  await page.evaluate((onclick) => {
                    eval(onclick);
                  }, element.onclick);
                  clicked = true;
                }
              } catch (e3) {
                console.log(`Failed to click "${element.text}":`, e3.message);
              }
            }
          }

          if (clicked) {
            // Wait for navigation or content change
            await page.waitForTimeout(3000);

            const afterUrl = page.url();
            console.log("afterUrl", afterUrl)
            if (afterUrl !== beforeUrl) {
              console.log(`✅ Click successful: ${element.text} -> ${afterUrl}`);
              listUrls.push({
                text: element.text,
                url: afterUrl,
                originalUrl: url,
                clickMethod: 'playwright'
              });

              // Go back to original page for next test
              await page.goto(url, { waitUntil: 'networkidle' });
              await page.waitForTimeout(2000);
            } else {
              console.log(`❌ Click did not change URL: ${element.text}`);
            }
          }

        } catch (clickError) {
          console.log(`Error clicking "${element.text}":`, clickError.message);
        }
      }

      console.log(`Successfully extracted ${listUrls.length} list URLs via clicking`);
      console.log(listUrls);

      return listUrls;

    } catch (error) {
      console.error(`Error analyzing ${url}:`, error.message);
      return [];
    } finally {
      await page.close();
    }
  }

  async saveResultsToCSV(result) {
    const csvData = [];

    // Add list button URLs (only if found)
    for (const listUrl of result.listUrls) {
      csvData.push({
        siteName: result.siteName,
        originalUrl: result.originalUrl,
        hostName: result.hostName,
        currentDetailUrl: listUrl.originalUrl, // 현재 상세 URL 추가
        foundUrl: listUrl.url,
        urlType: 'List Button',
        linkText: listUrl.text
      });
    }

    // Add database URLs with empty foundUrl if no list found
    for (const dbResult of result.dbResults) {
      // Check if this dbResult has corresponding list URLs
      const hasListUrl = result.listUrls.some(listUrl =>
        listUrl.originalUrl === dbResult.url_address
      );

      if (!hasListUrl) {
        // No list URL found for this database result
        csvData.push({
          siteName: result.siteName,
          originalUrl: result.originalUrl,
          hostName: result.hostName,
          currentDetailUrl: dbResult.url_address, // 현재 상세 URL 추가
          foundUrl: '', // 목록 URL을 찾지 못한 경우 빈 문자열
          urlType: 'No List Found',
          linkText: dbResult.title_name
        });
      }
    }

    // If no results at all, add a record showing no list found
    if (result.listUrls.length === 0 && result.dbResults.length === 0) {
      csvData.push({
        siteName: result.siteName,
        originalUrl: result.originalUrl,
        hostName: result.hostName,
        currentDetailUrl: result.originalUrl,
        foundUrl: '', // 목록 URL을 찾지 못한 경우 빈 문자열
        urlType: 'No List Found',
        linkText: 'No content analyzed'
      });
    }

    if (csvData.length > 0) {
      try {
        await this.csvWriter.writeRecords(csvData);
        console.log(`✅ Saved ${csvData.length} records to CSV for ${result.siteName}`);
      } catch (error) {
        console.error(`❌ Error saving CSV for ${result.siteName}:`, error);
      }
    }
  }

  async processSite(siteData) {
    const { siteName, url } = siteData;
    const hostName = await this.extractHostName(url);

    if (!hostName) {
      console.log(`Skipping ${siteName} - invalid URL: ${url}`);
      return;
    }

    console.log(`\n=== Processing ${siteName} (${hostName}) ===`);

    try {
      // Step 1: Execute database query
      const dbResults = await this.executeQuery(siteName, hostName);

      // Step 2: Find announcement boards on homepage
      // const announcementBoards = await this.findAnnouncementBoard(hostName);
      // console.log("announcementBoards", announcementBoards)
      // Step 3: Analyze each URL_ADDRESS for list buttons
      const allListUrls = [];

      // Analyze database URLs
      for (const dbResult of dbResults) {

        const listUrls = await this.analyzeUrlForListButton(dbResult.url_address);
        console.log(listUrls)
        allListUrls.push(...listUrls);
      }

      // Analyze original URL
      const originalListUrls = await this.analyzeUrlForListButton(url);
      allListUrls.push(...originalListUrls);

      // Store results
      const currentResult = {
        siteName,
        originalUrl: url,
        hostName,
        dbResults,
        listUrls: allListUrls
      };

      this.results.push(currentResult);

      // Save to CSV immediately after processing each site
      await this.saveResultsToCSV(currentResult);

      console.log(`Results saved for ${siteName}`)

    } catch (error) {
      console.error(`Error processing ${siteName}:`, error);
    }
  }


  async run() {
    try {
      await this.init();

      console.log(`Starting to process ${this.csvData.length} sites...`);

      for (const siteData of this.csvData) {
        await this.processSite(siteData);
        // Add delay to be respectful to servers
        await new Promise(resolve => setTimeout(resolve, 2000));
      }

      console.log('\nScraping completed successfully!');

    } catch (error) {
      console.error('Error during execution:', error);
    } finally {
      if (this.connection) {
        await this.connection.end();
      }
      if (this.browser) {
        await this.browser.close();
      }
    }
  }
}

// Run the scraper
const scraper = new NaverUrlScraper();
scraper.run().catch(console.error);