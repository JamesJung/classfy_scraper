#!/usr/bin/env python3

import os
import re
import json
import glob

def extract_config_from_scraper(filepath):
    """Extract configuration from a single scraper file"""
    
    site_code = os.path.basename(filepath).replace('_scraper.js', '')
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract configuration patterns
    config = {
        'baseUrl': None,
        'listUrl': None,
        'listSelector': None,
        'titleSelector': None,
        'dateSelector': None,
        'dateFormat': 'YYYY-MM-DD',
        'detailType': 'url'  # default
    }
    
    # Extract baseUrl
    base_url_patterns = [
        r"baseUrl[:\s]*['\"]([^'\"]+)['\"]",
        r"baseUrl\s*=\s*['\"]([^'\"]+)['\"]",
        r"this\.baseUrl\s*=\s*['\"]([^'\"]+)['\"]"
    ]
    for pattern in base_url_patterns:
        match = re.search(pattern, content)
        if match:
            config['baseUrl'] = match.group(1)
            break
    
    # Extract listUrl
    list_url_patterns = [
        r"listUrl[:\s]*['\"]([^'\"]+)['\"]",
        r"const listUrl\s*=\s*['\"]([^'\"]+)['\"]"
    ]
    for pattern in list_url_patterns:
        match = re.search(pattern, content)
        if match:
            config['listUrl'] = match.group(1)
            break
    
    # Extract selectors
    selector_patterns = {
        'listSelector': [
            r"listSelector[:\s]*['\"]([^'\"]+)['\"]",
            r"argv\.listSelector\s*\|\|\s*['\"]([^'\"]+)['\"]",
            r"default:\s*['\"]([^'\"]+)['\"].*list-selector"
        ],
        'titleSelector': [
            r"titleSelector[:\s]*['\"]([^'\"]+)['\"]",
            r"argv\.titleSelector\s*\|\|\s*['\"]([^'\"]+)['\"]"
        ],
        'dateSelector': [
            r"dateSelector[:\s]*['\"]([^'\"]+)['\"]",
            r"argv\.dateSelector\s*\|\|\s*['\"]([^'\"]+)['\"]"
        ]
    }
    
    for key, patterns in selector_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
            if match:
                config[key] = match.group(1)
                break
    
    # Check for special detail handling
    if 'javascript:' in content or 'goView' in content:
        config['detailType'] = 'javascript'
    elif 'POST' in content and 'detailPost' in content:
        config['detailType'] = 'post'
    
    # Extract date format if specified
    date_format_match = re.search(r"dateFormat[:\s]*['\"]([^'\"]+)['\"]", content)
    if date_format_match:
        config['dateFormat'] = date_format_match.group(1)
    
    return site_code, config

def main():
    scrapers_config = {}
    
    # Get all scraper files
    scraper_files = glob.glob('node/scraper/*_scraper.js')
    
    # Exclude certain files
    exclude_patterns = ['announcement_scraper.js', 'eminwon_scraper.js', 'eminwon_detail_scraper.js']
    scraper_files = [f for f in scraper_files if not any(ex in f for ex in exclude_patterns)]
    
    print(f"Found {len(scraper_files)} scraper files to process")
    
    # Process each scraper
    for filepath in sorted(scraper_files)[:20]:  # Start with first 20
        try:
            site_code, config = extract_config_from_scraper(filepath)
            scrapers_config[site_code] = config
            print(f"Processed: {site_code}")
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
    
    # Save to JSON file
    output_file = 'scrapers_config.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(scrapers_config, f, indent=2, ensure_ascii=False)
    
    print(f"\nConfiguration extracted to {output_file}")
    print(f"Total sites configured: {len(scrapers_config)}")
    
    # Display sample
    sample = list(scrapers_config.items())[:3]
    print("\nSample configuration:")
    for site, config in sample:
        print(f"\n{site}:")
        print(json.dumps(config, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()