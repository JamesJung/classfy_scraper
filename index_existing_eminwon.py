#!/usr/bin/env python3

import os
import re
import json
import mysql.connector
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
import hashlib


class EminwonIndexer:
    def __init__(self):
        # Try to get database config from environment or use defaults
        import os

        # Load .env file if exists
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        self.db_config = {
            "host": os.environ.get("DB_HOST"),
            "user": os.environ.get("DB_USER"),
            "password": os.environ.get("DB_PASSWORD"),
            "database": os.environ.get("DB_NAME"),
            "port": int(os.environ.get("DB_PORT")),
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
        }
        self.data_dir = Path("eminwon_data")
        self.indexed_count = 0
        self.error_count = 0
        self.duplicate_count = 0

    def create_database_table(self):
        """Create the eminwon_url_registry table if not exists"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()

        create_table_sql = """
        CREATE TABLE IF NOT EXISTS eminwon_url_registry (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            region VARCHAR(50),
            folder_name VARCHAR(500),
            announcement_url VARCHAR(1000) UNIQUE,
            announcement_id VARCHAR(100),
            title VARCHAR(500),
            post_date DATE,
            content_hash VARCHAR(64),
            first_seen_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_checked_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_region_date (region, post_date),
            INDEX idx_announcement_id (announcement_id),
            INDEX idx_url (announcement_url)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """

        cursor.execute(create_table_sql)
        conn.commit()
        print("✓ Database table 'eminwon_url_registry' created/verified")

        cursor.close()
        conn.close()

    def extract_metadata_from_content(self, content_path):
        """Extract metadata from content.md file"""
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                content = f.read()

            metadata = {}

            # Extract title
            title_match = re.search(r"\*\*제목\*\*:\s*(.+)", content)
            if title_match:
                metadata["title"] = title_match.group(1).strip()
            else:
                # Try alternative format
                title_match = re.search(r"^#\s*(.+)", content, re.MULTILINE)
                if title_match:
                    metadata["title"] = title_match.group(1).strip()

            # Extract URL (handle various formats)
            # Pattern 1: **원본 URL**: 
            # Pattern 2: **원본 URL:**
            # Pattern 3: **원본 URL**:
            url_match = re.search(r"\*\*원본 URL:?\*\*:?\s*(.+)", content)
            if url_match:
                metadata["url"] = url_match.group(1).strip()

            # Extract announcement ID from URL
            if "url" in metadata:
                id_match = re.search(r"not_ancmt_mgt_no=(\d+)", metadata["url"])
                if id_match:
                    metadata["announcement_id"] = id_match.group(1)

            # Extract date
            date_match = re.search(r"\*\*작성일\*\*:\s*(\d{4}-\d{2}-\d{2})", content)
            if date_match:
                metadata["post_date"] = date_match.group(1)

            # Generate content hash
            metadata["content_hash"] = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()

            return metadata

        except Exception as e:
            print(f"Error reading {content_path}: {e}")
            return None

    def index_region(self, region_name, region_path):
        """Index all announcements in a region directory"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()

        region_count = 0
        region_errors = 0
        region_duplicates = 0

        # Get all subdirectories (announcement folders)
        announcement_dirs = [d for d in region_path.iterdir() if d.is_dir()]

        for ann_dir in announcement_dirs:
            content_md_path = ann_dir / "content.md"

            if not content_md_path.exists():
                continue

            metadata = self.extract_metadata_from_content(content_md_path)

            if not metadata or "url" not in metadata:
                region_errors += 1
                self.error_count += 1
                continue

            try:
                # Normalize all text to NFC (standard Korean form)
                import unicodedata

                insert_sql = """
                INSERT INTO eminwon_url_registry 
                (region, folder_name, announcement_url, announcement_id, title, post_date, content_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                last_checked_date = CURRENT_TIMESTAMP,
                content_hash = VALUES(content_hash)
                """

                values = (
                    unicodedata.normalize("NFC", region_name),
                    unicodedata.normalize("NFC", ann_dir.name),
                    metadata.get("url"),
                    metadata.get("announcement_id"),
                    unicodedata.normalize("NFC", metadata.get("title", "")),
                    metadata.get("post_date"),
                    metadata.get("content_hash"),
                )

                cursor.execute(insert_sql, values)

                if cursor.rowcount == 1:
                    region_count += 1
                    self.indexed_count += 1
                else:
                    region_duplicates += 1
                    self.duplicate_count += 1

            except mysql.connector.IntegrityError as e:
                if "Duplicate entry" in str(e):
                    region_duplicates += 1
                    self.duplicate_count += 1
                else:
                    print(f"Database error for {ann_dir.name}: {e}")
                    region_errors += 1
                    self.error_count += 1
            except Exception as e:
                print(f"Error processing {ann_dir.name}: {e}")
                region_errors += 1
                self.error_count += 1

        conn.commit()
        cursor.close()
        conn.close()

        return region_count, region_duplicates, region_errors

    def delete_existing_data(self, specific_regions=None):
        """Delete existing indexed data for force re-indexing"""
        import unicodedata
        
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()

        if specific_regions:
            # Normalize regions to NFC (standard Korean form)
            nfc_regions = [unicodedata.normalize("NFC", r) for r in specific_regions]
            
            # Delete specific regions
            placeholders = ", ".join(["%s"] * len(nfc_regions))
            delete_sql = (
                f"DELETE FROM eminwon_url_registry WHERE region IN ({placeholders})"
            )
            cursor.execute(delete_sql, nfc_regions)
            deleted = cursor.rowcount
            print(
                f"Deleted {deleted} records for regions: {', '.join(specific_regions)}"
            )
        else:
            # Delete all data
            cursor.execute("DELETE FROM eminwon_url_registry")
            deleted = cursor.rowcount
            print(f"Deleted all {deleted} records from database")

        conn.commit()
        cursor.close()
        conn.close()

    def run_indexing(self, specific_regions=None):
        """Main indexing process"""
        print("=" * 80)
        if specific_regions:
            print(f"Starting eminwon data indexing for: {', '.join(specific_regions)}")
        else:
            print("Starting eminwon data indexing...")
        print("=" * 80)

        # Create table if not exists
        self.create_database_table()

        # Get region directories to process
        if specific_regions:
            # Process only specified regions
            region_dirs = []
            for region_name in specific_regions:
                region_path = self.data_dir / region_name
                if region_path.exists() and region_path.is_dir():
                    region_dirs.append(region_path)
                else:
                    print(
                        f"⚠️  Warning: Region '{region_name}' not found in {self.data_dir}"
                    )

            if not region_dirs:
                print("No valid regions found to index")
                return
        else:
            # Process all regions
            region_dirs = [d for d in self.data_dir.iterdir() if d.is_dir()]

        print(f"Found {len(region_dirs)} regions to index")
        print("-" * 80)

        # Process each region with progress bar
        for region_dir in tqdm(region_dirs, desc="Indexing regions"):
            region_name = region_dir.name

            count, duplicates, errors = self.index_region(region_name, region_dir)

            if count > 0 or duplicates > 0 or errors > 0:
                tqdm.write(
                    f"✓ {region_name:15} - New: {count:4}, Duplicates: {duplicates:4}, Errors: {errors:4}"
                )

        print("=" * 80)
        print("Indexing completed!")
        print(f"Total indexed: {self.indexed_count:,}")
        print(f"Total duplicates: {self.duplicate_count:,}")
        print(f"Total errors: {self.error_count:,}")
        print("=" * 80)

        # Show statistics
        if specific_regions:
            self.show_statistics(specific_regions)
        else:
            self.show_statistics()

    def show_statistics(self, specific_regions=None):
        """Show indexed data statistics"""
        import unicodedata
        
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()

        if specific_regions:
            # Normalize regions to NFC (standard Korean form)
            nfc_regions = [unicodedata.normalize("NFC", r) for r in specific_regions]
            
            # Stats for specific regions
            placeholders = ", ".join(["%s"] * len(nfc_regions))

            # Total count for specific regions
            cursor.execute(
                f"SELECT COUNT(*) FROM eminwon_url_registry WHERE region IN ({placeholders})",
                nfc_regions,
            )
            total = cursor.fetchone()[0]

            # Count by region for specific regions
            cursor.execute(
                f"""
                SELECT region, COUNT(*) as count 
                FROM eminwon_url_registry 
                WHERE region IN ({placeholders})
                GROUP BY region 
                ORDER BY count DESC
            """,
                nfc_regions,
            )
            regions_data = cursor.fetchall()

            print("\n" + "=" * 80)
            print(f"Database Statistics for: {', '.join(specific_regions)}")
            print("=" * 80)
            print(f"Total indexed URLs: {total:,}")
            print("\nRegion announcement counts:")
            print("-" * 40)
            for region, count in regions_data:
                print(f"  {region:20} : {count:6,} announcements")

            # Date range for specific regions
            cursor.execute(
                f"""
                SELECT MIN(post_date), MAX(post_date) 
                FROM eminwon_url_registry 
                WHERE post_date IS NOT NULL AND region IN ({placeholders})
            """,
                nfc_regions,
            )
        else:
            # Total count
            cursor.execute("SELECT COUNT(*) FROM eminwon_url_registry")
            total = cursor.fetchone()[0]

            # Count by region
            cursor.execute(
                """
                SELECT region, COUNT(*) as count 
                FROM eminwon_url_registry 
                GROUP BY region 
                ORDER BY count DESC 
                LIMIT 10
            """
            )
            top_regions = cursor.fetchall()

            print("\n" + "=" * 80)
            print("Database Statistics:")
            print("=" * 80)
            print(f"Total indexed URLs: {total:,}")
            print("\nTop 10 regions by announcement count:")
            print("-" * 40)
            for region, count in top_regions:
                print(f"  {region:20} : {count:6,} announcements")

            # Date range
            cursor.execute(
                """
                SELECT MIN(post_date), MAX(post_date) 
                FROM eminwon_url_registry 
                WHERE post_date IS NOT NULL
            """
            )

        min_date, max_date = cursor.fetchone()

        if min_date and max_date:
            print(f"\nDate range: {min_date} ~ {max_date}")

        cursor.close()
        conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Index existing eminwon data to database"
    )
    parser.add_argument(
        "-r",
        "--regions",
        nargs="+",
        help="Specific regions to index (e.g., -r 청주 수원)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-indexing by deleting existing data",
    )
    parser.add_argument(
        "--list", action="store_true", help="List available regions and exit"
    )

    args = parser.parse_args()

    indexer = EminwonIndexer()

    # Check if eminwon_data directory exists
    if not indexer.data_dir.exists():
        print(f"Error: Directory '{indexer.data_dir}' not found!")
        return

    # List regions if requested
    if args.list:
        print("Available regions:")
        print("-" * 40)
        regions = [d.name for d in indexer.data_dir.iterdir() if d.is_dir()]
        for region in sorted(regions):
            print(f"  {region}")
        print(f"\nTotal: {len(regions)} regions")
        return

    # Handle force option
    if args.force:
        if args.regions:
            print(f"Force re-indexing for regions: {', '.join(args.regions)}")
            response = input(
                "This will delete existing data for these regions. Continue? (y/n): "
            )
        else:
            print("Force re-indexing ALL regions")
            response = input(
                "This will delete ALL existing indexed data. Continue? (y/n): "
            )

        if response.lower() != "y":
            print("Cancelled")
            return

        indexer.delete_existing_data(args.regions)

    # Run indexing
    indexer.run_indexing(specific_regions=args.regions)

    print("\n✅ Indexing complete! The database is ready for incremental collection.")
    print(
        "Run 'python eminwon_incremental_crawler.py' to start collecting new announcements."
    )


if __name__ == "__main__":
    main()
