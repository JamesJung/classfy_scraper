#!/usr/bin/env python3

import mysql.connector
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Database configuration
db_config = {
    'host': os.environ.get('DB_HOST', '192.168.0.95'),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', 'b3UvSDS232GbdZ42'),
    'database': os.environ.get('DB_NAME', 'subvention'),
    'port': int(os.environ.get('DB_PORT', '3309')),
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}

try:
    # Connect to database
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    
    # Check total count
    cursor.execute("SELECT COUNT(*) FROM eminwon_url_registry")
    total = cursor.fetchone()[0]
    
    print(f"Total indexed URLs: {total:,}")
    
    # Check regions
    cursor.execute("""
        SELECT region, COUNT(*) as count 
        FROM eminwon_url_registry 
        GROUP BY region 
        ORDER BY count DESC
    """)
    
    regions = cursor.fetchall()
    
    print(f"\nIndexed regions ({len(regions)}):")
    print("-" * 40)
    for region, count in regions[:20]:  # Show top 20
        print(f"  {region:20} : {count:6,} announcements")
    
    if len(regions) > 20:
        print(f"  ... and {len(regions) - 20} more regions")
    
    cursor.close()
    conn.close()
    
except mysql.connector.Error as err:
    print(f"Database error: {err}")
except Exception as e:
    print(f"Error: {e}")