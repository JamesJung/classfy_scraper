#!/usr/bin/env python3

import os
import sys
import json
import logging
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import mysql.connector
from typing import Dict, List
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class EminwonDailyBatch:
    def __init__(self, config_file='config/batch_config.json'):
        self.start_time = datetime.now()
        self.today = self.start_time.strftime('%Y-%m-%d')
        
        # Setup logging
        self.setup_logging()
        
        # Load configuration
        self.config = self.load_config(config_file)
        
        # Database configuration
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
        
        # Statistics
        self.stats = {
            'indexing': {'status': 'pending', 'message': ''},
            'crawling': {'status': 'pending', 'message': '', 'new_count': 0},
            'processing': {'status': 'pending', 'message': '', 'processed_count': 0},
            'errors': []
        }
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_dir = Path('logs/batch')
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f'batch_{self.today}.log'
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        self.logger = logging.getLogger(__name__)
    
    def load_config(self, config_file):
        """Load batch configuration"""
        config_path = Path(config_file)
        
        # Default configuration
        default_config = {
            'run_indexing': False,  # Only run once initially
            'max_pages_per_region': 3,
            'parallel_workers': 5,
            'enable_email_notification': False,
            'email_recipients': [],
            'process_announcements': True,
            'cleanup_old_data': True,
            'cleanup_days': 30
        }
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        else:
            # Create default config file
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2)
            self.logger.info(f"Created default config file: {config_path}")
        
        return default_config
    
    def check_database_connection(self):
        """Verify database connection"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            self.logger.info("✓ Database connection verified")
            return True
        except Exception as e:
            self.logger.error(f"✗ Database connection failed: {e}")
            self.stats['errors'].append(f"Database connection error: {e}")
            return False
    
    def run_initial_indexing(self):
        """Run initial indexing if needed"""
        if not self.config['run_indexing']:
            self.logger.info("Skipping initial indexing (disabled in config)")
            self.stats['indexing']['status'] = 'skipped'
            return True
        
        self.logger.info("=" * 80)
        self.logger.info("Step 1: Running Initial Indexing")
        self.logger.info("=" * 80)
        
        try:
            result = subprocess.run(
                ['python', 'index_existing_eminwon.py'],
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )
            
            if result.returncode == 0:
                self.logger.info("✓ Initial indexing completed successfully")
                self.stats['indexing']['status'] = 'success'
                self.stats['indexing']['message'] = 'Indexing completed'
                return True
            else:
                self.logger.error(f"✗ Initial indexing failed: {result.stderr}")
                self.stats['indexing']['status'] = 'failed'
                self.stats['indexing']['message'] = result.stderr
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("✗ Initial indexing timed out")
            self.stats['indexing']['status'] = 'timeout'
            return False
        except Exception as e:
            self.logger.error(f"✗ Error running initial indexing: {e}")
            self.stats['indexing']['status'] = 'error'
            self.stats['errors'].append(f"Indexing error: {e}")
            return False
    
    def run_incremental_crawler(self):
        """Run incremental crawler to collect new announcements"""
        self.logger.info("=" * 80)
        self.logger.info("Step 2: Running Incremental Crawler")
        self.logger.info("=" * 80)
        
        try:
            result = subprocess.run(
                ['python', 'eminwon_incremental_crawler.py'],
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )
            
            if result.returncode == 0:
                # Parse output to get statistics
                output_lines = result.stdout.split('\n')
                for line in output_lines:
                    if 'New announcements found:' in line:
                        count = line.split(':')[1].strip().replace(',', '')
                        self.stats['crawling']['new_count'] = int(count) if count.isdigit() else 0
                
                self.logger.info(f"✓ Incremental crawling completed")
                self.logger.info(f"  New announcements: {self.stats['crawling']['new_count']}")
                self.stats['crawling']['status'] = 'success'
                return True
            else:
                self.logger.error(f"✗ Incremental crawling failed: {result.stderr}")
                self.stats['crawling']['status'] = 'failed'
                self.stats['crawling']['message'] = result.stderr
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("✗ Incremental crawling timed out")
            self.stats['crawling']['status'] = 'timeout'
            return False
        except Exception as e:
            self.logger.error(f"✗ Error running incremental crawler: {e}")
            self.stats['crawling']['status'] = 'error'
            self.stats['errors'].append(f"Crawler error: {e}")
            return False
    
    def process_new_announcements(self):
        """Process newly collected announcements"""
        if not self.config['process_announcements']:
            self.logger.info("Skipping announcement processing (disabled in config)")
            self.stats['processing']['status'] = 'skipped'
            return True
        
        self.logger.info("=" * 80)
        self.logger.info("Step 3: Processing New Announcements")
        self.logger.info("=" * 80)
        
        # Check if there are new announcements to process
        new_data_dir = Path(f'eminwon_data_new/{self.today}')
        if not new_data_dir.exists():
            self.logger.info("No new announcements to process")
            self.stats['processing']['status'] = 'no_data'
            return True
        
        # Count announcements to process
        announcement_count = sum(
            1 for region in new_data_dir.iterdir() if region.is_dir()
            for ann in region.iterdir() if ann.is_dir()
        )
        
        if announcement_count == 0:
            self.logger.info("No new announcements to process")
            self.stats['processing']['status'] = 'no_data'
            return True
        
        self.logger.info(f"Found {announcement_count} announcements to process")
        
        # Process each region's announcements
        try:
            for region_dir in new_data_dir.iterdir():
                if not region_dir.is_dir():
                    continue
                
                region_name = region_dir.name
                self.logger.info(f"Processing {region_name}...")
                
                # Run announcement_pre_processor.py for this region
                result = subprocess.run(
                    ['python', 'announcement_pre_processor.py', 
                     '--data-dir', str(region_dir),
                     '--force'],
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes per region
                )
                
                if result.returncode == 0:
                    self.stats['processing']['processed_count'] += len(list(region_dir.iterdir()))
                else:
                    self.logger.warning(f"Failed to process {region_name}: {result.stderr}")
                    self.stats['errors'].append(f"Processing error for {region_name}")
            
            self.logger.info(f"✓ Processed {self.stats['processing']['processed_count']} announcements")
            self.stats['processing']['status'] = 'success'
            return True
            
        except Exception as e:
            self.logger.error(f"✗ Error processing announcements: {e}")
            self.stats['processing']['status'] = 'error'
            self.stats['errors'].append(f"Processing error: {e}")
            return False
    
    def cleanup_old_data(self):
        """Clean up old data files"""
        if not self.config['cleanup_old_data']:
            self.logger.info("Skipping old data cleanup (disabled in config)")
            return
        
        self.logger.info("=" * 80)
        self.logger.info("Step 4: Cleaning Up Old Data")
        self.logger.info("=" * 80)
        
        cleanup_date = datetime.now() - timedelta(days=self.config['cleanup_days'])
        new_data_dir = Path('eminwon_data_new')
        
        if not new_data_dir.exists():
            return
        
        cleaned_count = 0
        for date_dir in new_data_dir.iterdir():
            if not date_dir.is_dir():
                continue
            
            # Parse directory name as date
            try:
                dir_date = datetime.strptime(date_dir.name, '%Y-%m-%d')
                if dir_date < cleanup_date:
                    # Remove old directory
                    import shutil
                    shutil.rmtree(date_dir)
                    cleaned_count += 1
                    self.logger.info(f"Removed old data: {date_dir.name}")
            except ValueError:
                continue
        
        if cleaned_count > 0:
            self.logger.info(f"✓ Cleaned up {cleaned_count} old directories")
    
    def generate_report(self):
        """Generate batch execution report"""
        elapsed_time = datetime.now() - self.start_time
        
        report = f"""
========================================
Eminwon Daily Batch Report
========================================
Date: {self.today}
Execution Time: {elapsed_time}

1. Initial Indexing: {self.stats['indexing']['status']}
   {self.stats['indexing']['message']}

2. Incremental Crawling: {self.stats['crawling']['status']}
   New Announcements: {self.stats['crawling']['new_count']}
   {self.stats['crawling']['message']}

3. Announcement Processing: {self.stats['processing']['status']}
   Processed Count: {self.stats['processing']['processed_count']}
   {self.stats['processing']['message']}

Errors: {len(self.stats['errors'])}
"""
        
        if self.stats['errors']:
            report += "\nError Details:\n"
            for error in self.stats['errors']:
                report += f"  - {error}\n"
        
        report += "\n========================================\n"
        
        # Save report to file
        report_dir = Path('reports')
        report_dir.mkdir(exist_ok=True)
        report_file = report_dir / f'batch_report_{self.today}.txt'
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        self.logger.info(f"Report saved to: {report_file}")
        
        return report
    
    def send_email_notification(self, report):
        """Send email notification with batch results"""
        if not self.config['enable_email_notification']:
            return
        
        # Email configuration (update with your SMTP settings)
        smtp_config = {
            'host': 'smtp.gmail.com',
            'port': 587,
            'user': 'your-email@gmail.com',
            'password': 'your-app-password'
        }
        
        try:
            msg = MIMEMultipart()
            msg['From'] = smtp_config['user']
            msg['To'] = ', '.join(self.config['email_recipients'])
            msg['Subject'] = f'Eminwon Batch Report - {self.today}'
            
            msg.attach(MIMEText(report, 'plain'))
            
            with smtplib.SMTP(smtp_config['host'], smtp_config['port']) as server:
                server.starttls()
                server.login(smtp_config['user'], smtp_config['password'])
                server.send_message(msg)
            
            self.logger.info("✓ Email notification sent")
            
        except Exception as e:
            self.logger.error(f"Failed to send email: {e}")
    
    def run(self):
        """Main batch execution"""
        self.logger.info("=" * 80)
        self.logger.info("Starting Eminwon Daily Batch")
        self.logger.info(f"Date: {self.today}")
        self.logger.info("=" * 80)
        
        # Check database connection
        if not self.check_database_connection():
            self.logger.error("Batch aborted due to database connection error")
            return False
        
        # Step 1: Initial indexing (if enabled)
        self.run_initial_indexing()
        
        # Step 2: Incremental crawling
        if not self.run_incremental_crawler():
            self.logger.warning("Crawling failed, but continuing with existing data")
        
        # Step 3: Process new announcements
        if self.stats['crawling']['new_count'] > 0:
            self.process_new_announcements()
        
        # Step 4: Cleanup old data
        self.cleanup_old_data()
        
        # Generate and send report
        report = self.generate_report()
        self.logger.info(report)
        
        # Send email notification
        self.send_email_notification(report)
        
        self.logger.info("=" * 80)
        self.logger.info("Batch execution completed")
        self.logger.info("=" * 80)
        
        return True

def main():
    parser = argparse.ArgumentParser(description='Eminwon Daily Batch')
    parser.add_argument('--config', default='config/batch_config.json', 
                       help='Configuration file path')
    parser.add_argument('--index', action='store_true',
                       help='Force run initial indexing')
    parser.add_argument('--no-process', action='store_true',
                       help='Skip announcement processing')
    parser.add_argument('--no-cleanup', action='store_true',
                       help='Skip old data cleanup')
    
    args = parser.parse_args()
    
    batch = EminwonDailyBatch(config_file=args.config)
    
    # Override config with command line arguments
    if args.index:
        batch.config['run_indexing'] = True
    if args.no_process:
        batch.config['process_announcements'] = False
    if args.no_cleanup:
        batch.config['cleanup_old_data'] = False
    
    # Run batch
    success = batch.run()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()