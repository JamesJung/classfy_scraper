#!/usr/bin/env python3

import os
import re
import json
import time
import requests
import mysql.connector
from pathlib import Path
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import hashlib
import argparse

class EminwonIncrementalCrawler:
    def __init__(self, test_mode=False, specific_regions=None):
        import os
        # Load .env file if exists
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
            
        self.db_config = {
            'host': os.environ.get('DB_HOST', '192.168.0.95'),
            'user': os.environ.get('DB_USER', 'root'),
            'password': os.environ.get('DB_PASSWORD', 'b3UvSDS232GbdZ42'),
            'database': os.environ.get('DB_NAME', 'subvention'),
            'port': int(os.environ.get('DB_PORT', '3309')),
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci'
        }
        
        # Load eminwon.json configuration
        with open('node/scraper/eminwon.json', 'r', encoding='utf-8') as f:
            self.eminwon_config = json.load(f)
        
        # Set up directories
        today = datetime.now().strftime('%Y-%m-%d')
        self.output_dir = Path(f'eminwon_data_new/{today}')
        
        # Statistics
        self.stats = {
            'total_checked': 0,
            'new_found': 0,
            'downloaded': 0,
            'errors': 0,
            'duplicates': 0
        }
        
        self.test_mode = test_mode
        self.specific_regions = specific_regions
        
        # Session for connection reuse
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def check_url_exists(self, url):
        """Check if URL already exists in database"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id FROM eminwon_url_registry 
            WHERE announcement_url = %s
        """, (url,))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return result is not None
    
    def save_to_database(self, region, folder_name, url, announcement_id, title, post_date, content_hash):
        """Save new announcement URL to database"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            insert_sql = """
            INSERT INTO eminwon_url_registry 
            (region, folder_name, announcement_url, announcement_id, title, post_date, content_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            last_checked_date = CURRENT_TIMESTAMP
            """
            
            cursor.execute(insert_sql, (
                region, folder_name, url, announcement_id, 
                title, post_date, content_hash
            ))
            
            conn.commit()
            return True
            
        except Exception as e:
            print(f"Database error: {e}")
            return False
            
        finally:
            cursor.close()
            conn.close()
    
    def parse_list_page(self, html_content, base_url):
        """Parse announcement list page and extract announcement URLs"""
        soup = BeautifulSoup(html_content, 'html.parser')
        announcements = []
        
        # Find announcement list table
        # eminwon sites typically have announcements in table rows
        rows = soup.select('tr[onclick]')
        
        for row in rows:
            onclick = row.get('onclick', '')
            
            # Extract URL from onclick attribute
            # Pattern: jf_view('params')
            match = re.search(r"jf_view\('([^']+)'\)", onclick)
            if match:
                params = match.group(1)
                # Construct full URL
                view_url = f"https://{base_url}/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do"
                view_url += f"?jndinm=OfrNotAncmtEJB&context=NTIS&method=selectOfrNotAncmt"
                view_url += f"&methodnm=selectOfrNotAncmtRegst&{params}"
                
                # Extract announcement ID
                id_match = re.search(r'not_ancmt_mgt_no=(\d+)', params)
                if id_match:
                    ann_id = id_match.group(1)
                else:
                    continue
                
                # Extract title
                title_cell = row.select_one('td.title')
                if title_cell:
                    title = title_cell.get_text(strip=True)
                else:
                    title = ""
                
                # Extract date
                date_cells = row.select('td')
                post_date = None
                for cell in date_cells:
                    text = cell.get_text(strip=True)
                    if re.match(r'\d{4}-\d{2}-\d{2}', text):
                        post_date = text
                        break
                
                announcements.append({
                    'url': view_url,
                    'id': ann_id,
                    'title': title,
                    'date': post_date
                })
        
        # Alternative parsing for different table structures
        if not announcements:
            links = soup.select('a[href*="not_ancmt_mgt_no"]')
            for link in links:
                href = link.get('href', '')
                id_match = re.search(r'not_ancmt_mgt_no=(\d+)', href)
                if id_match:
                    ann_id = id_match.group(1)
                    full_url = urljoin(f"https://{base_url}/", href)
                    title = link.get_text(strip=True)
                    
                    announcements.append({
                        'url': full_url,
                        'id': ann_id,
                        'title': title,
                        'date': None
                    })
        
        return announcements
    
    def fetch_list_page(self, domain, page=1):
        """Fetch announcement list page from eminwon site"""
        try:
            # Construct list URL
            list_url = f"https://{domain}/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do"
            
            params = {
                'jndinm': 'OfrNotAncmtEJB',
                'context': 'NTIS',
                'method': 'selectList',
                'methodnm': 'selectListOfrNotAncmt',
                'homepage_pbs_yn': 'Y',
                'subCheck': 'Y',
                'ofr_pageSize': '10',
                'not_ancmt_se_code': '01,02,03,04,05',
                'title': '고시공고',
                'initValue': 'Y',
                'countYn': 'Y',
                'list_gubun': 'A',
                'pageIndex': str(page)
            }
            
            response = self.session.get(list_url, params=params, timeout=30)
            response.raise_for_status()
            
            return response.text
            
        except Exception as e:
            print(f"Error fetching list page from {domain}: {e}")
            return None
    
    def download_announcement(self, url, region, announcement_id, title):
        """Download announcement content and save as content.md"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract content
            content_div = soup.select_one('.view_content')
            if not content_div:
                content_div = soup.select_one('#content')
            
            if content_div:
                content_text = content_div.get_text(strip=True)
            else:
                content_text = soup.get_text(strip=True)
            
            # Extract date
            date_match = re.search(r'(\d{4}[-년]\s?\d{1,2}[-월]\s?\d{1,2})', response.text)
            if date_match:
                post_date = date_match.group(1)
                # Normalize date format
                post_date = re.sub(r'[년월]', '-', post_date).replace(' ', '')
                if post_date.endswith('-'):
                    post_date = post_date[:-1]
            else:
                post_date = datetime.now().strftime('%Y-%m-%d')
            
            # Create content.md format
            content_md = f"""**제목**: {title}

**원본 URL**: {url}

**작성일**: {post_date}

**내용**:

{content_text}
"""
            
            # Generate content hash
            content_hash = hashlib.sha256(content_md.encode('utf-8')).hexdigest()
            
            # Create folder name
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', title[:100])
            folder_name = f"{announcement_id}_{safe_title}"
            
            # Save to file system
            region_dir = self.output_dir / region
            region_dir.mkdir(parents=True, exist_ok=True)
            
            ann_dir = region_dir / folder_name
            ann_dir.mkdir(exist_ok=True)
            
            content_path = ann_dir / 'content.md'
            with open(content_path, 'w', encoding='utf-8') as f:
                f.write(content_md)
            
            # Save to database
            self.save_to_database(
                region, folder_name, url, announcement_id,
                title, post_date, content_hash
            )
            
            return True
            
        except Exception as e:
            print(f"Error downloading announcement {announcement_id}: {e}")
            return False
    
    def process_region(self, region_name, domain):
        """Process a single region - check for new announcements"""
        region_stats = {
            'checked': 0,
            'new': 0,
            'downloaded': 0,
            'duplicates': 0
        }
        
        # Fetch recent pages (1-3 pages)
        max_pages = 1 if self.test_mode else 3
        
        for page in range(1, max_pages + 1):
            html = self.fetch_list_page(domain, page)
            if not html:
                continue
            
            announcements = self.parse_list_page(html, domain)
            
            for ann in announcements:
                region_stats['checked'] += 1
                
                # Check if URL exists in database
                if self.check_url_exists(ann['url']):
                    region_stats['duplicates'] += 1
                    continue
                
                # New announcement found
                region_stats['new'] += 1
                
                # Download announcement
                if self.download_announcement(
                    ann['url'], region_name, ann['id'], ann['title']
                ):
                    region_stats['downloaded'] += 1
                
                # In test mode, limit downloads
                if self.test_mode and region_stats['downloaded'] >= 2:
                    break
            
            # In test mode, process only first page
            if self.test_mode:
                break
            
            # Small delay between pages
            time.sleep(1)
        
        return region_stats
    
    def run_incremental_collection(self):
        """Main incremental collection process"""
        print("=" * 80)
        print("Starting Eminwon Incremental Collection")
        print(f"Output directory: {self.output_dir}")
        print("=" * 80)
        
        # Filter regions if specified
        if self.specific_regions:
            regions_to_process = {
                k: v for k, v in self.eminwon_config.items() 
                if k in self.specific_regions
            }
        else:
            regions_to_process = self.eminwon_config
        
        print(f"Processing {len(regions_to_process)} regions...")
        print("-" * 80)
        
        # Process regions with thread pool
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {}
            
            for region_name, domain in regions_to_process.items():
                future = executor.submit(self.process_region, region_name, domain)
                futures[future] = region_name
            
            # Process results with progress bar
            for future in tqdm(as_completed(futures), total=len(futures), desc="Processing regions"):
                region_name = futures[future]
                
                try:
                    stats = future.result(timeout=60)
                    
                    self.stats['total_checked'] += stats['checked']
                    self.stats['new_found'] += stats['new']
                    self.stats['downloaded'] += stats['downloaded']
                    self.stats['duplicates'] += stats['duplicates']
                    
                    if stats['new'] > 0:
                        tqdm.write(f"✓ {region_name:15} - New: {stats['new']:3}, Downloaded: {stats['downloaded']:3}")
                        
                except Exception as e:
                    self.stats['errors'] += 1
                    tqdm.write(f"✗ {region_name:15} - Error: {e}")
        
        # Print summary
        print("=" * 80)
        print("Collection Summary:")
        print("=" * 80)
        print(f"Total announcements checked: {self.stats['total_checked']:,}")
        print(f"New announcements found: {self.stats['new_found']:,}")
        print(f"Successfully downloaded: {self.stats['downloaded']:,}")
        print(f"Duplicates (already in DB): {self.stats['duplicates']:,}")
        print(f"Errors: {self.stats['errors']:,}")
        print("=" * 80)
        
        # Save statistics to file
        stats_file = self.output_dir / 'collection_stats.json'
        stats_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'stats': self.stats,
                'regions_processed': len(regions_to_process)
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ Collection complete! Statistics saved to {stats_file}")

def main():
    parser = argparse.ArgumentParser(description='Eminwon Incremental Crawler')
    parser.add_argument('--test', action='store_true', help='Run in test mode (limited crawling)')
    parser.add_argument('--regions', nargs='+', help='Specific regions to process')
    
    args = parser.parse_args()
    
    crawler = EminwonIncrementalCrawler(
        test_mode=args.test,
        specific_regions=args.regions
    )
    
    crawler.run_incremental_collection()

if __name__ == "__main__":
    main()