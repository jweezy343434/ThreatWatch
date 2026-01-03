#!/usr/bin/env python3
import feedparser
import anthropic
import yaml
import os
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import time

FEEDS_CONFIG = 'config/feeds.yaml'
CONTENT_DIR = 'content/posts'
CACHE_FILE = '.feed_cache.txt'
MAX_ARTICLES = 10

def load_feeds():
    with open(FEEDS_CONFIG, 'r') as f:
        config = yaml.safe_load(f)
    return config['feeds']

def get_cached_urls():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return set(f.read().splitlines())
    return set()

def save_to_cache(url):
    with open(CACHE_FILE, 'a') as f:
        f.write(f"{url}\n")

def fetch_entries(feeds):
    cached_urls = get_cached_urls()
    new_entries = []
    
    for feed in feeds:
        try:
            print(f"Fetching: {feed['name']}")
            parsed = feedparser.parse(feed['url'])
            
            for entry in parsed.entries[:3]:
                if entry.link in cached_urls:
                    continue
                
                pub_date = datetime.now()
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6])
                
                new_entries.append({
                    'title': entry.title,
                    'link': entry.link,
                    'published': pub_date,
                    'source': feed['name'],
                    'summary': entry.get('summary', '')[:500],
                    'category': feed.get('category', 'general'),
                    'priority': feed.get('priority', 3)
                })
        except Exception as e:
            print(f"Error: {e}")
            continue
    
    new_entries.sort(key=lambda x: x['priority'])
    return new_entries[:MAX_ARTICLES]

def generate_analysis(entry):
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    
    prompt = f"""Analyze this cybersecurity threat:

Title: {entry['title']}
Source: {entry['source']}

Provide 3 concise paragraphs:

**What Happened**
Technical summary

**Impact**
Why this matters

**Actions**
What to do

Keep under 250 words."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        return f"Analysis unavailable: {e}"

def create_hugo_post(entry, analysis):
    slug = entry['title'].lower()
    slug = ''.join(c if c.isalnum() or c in ' -' else '' for c in slug)
    slug = '-'.join(slug.split())[:50]
    
    date_str = entry['published'].strftime('%Y-%m-%d')
    url_hash = hashlib.md5(entry['link'].encode()).hexdigest()[:8]
    filename = f"{date_str}-{slug}-{url_hash}.md"
    filepath = Path(CONTENT_DIR) / filename
    
    frontmatter = f"""---
title: "{entry['title']}"
date: {entry['published'].isoformat()}
source: "{entry['source']}"
source_url: "{entry['link']}"
category: "{entry['category']}"
draft: false
---

{analysis}

---
[Read full article at {entry['source']}]({entry['link']})
"""
    
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(frontmatter)
    
    return filepath

def main():
    print("ThreatWatch Feed Aggregator")
    print("="*60)
    
    feeds = load_feeds()
    print(f"Loaded {len(feeds)} feeds")
    
    entries = fetch_entries(feeds)
    print(f"Found {len(entries)} new articles\n")
    
    if not entries:
        print("No new content")
        return
    
    for i, entry in enumerate(entries, 1):
        print(f"[{i}/{len(entries)}] {entry['title'][:60]}...")
        analysis = generate_analysis(entry)
        filepath = create_hugo_post(entry, analysis)
        save_to_cache(entry['link'])
        print(f"  Created: {filepath.name}\n")
        time.sleep(1)
    
    print(f"✓ Processed {len(entries)} articles")

if __name__ == '__main__':
    main()
