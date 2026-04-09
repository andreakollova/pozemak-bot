#!/bin/bash
# Run all hockey scrapers and immediately trigger the Discord bot
LOG_DIR="/Users/antik/pozemak_bot/logs"
mkdir -p "$LOG_DIR"

PYTHON=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
SCRAPER_DIR=/Users/antik/hockey_scraper
BOT_DIR=/Users/antik/pozemak_bot
TRIGGER=/tmp/pozemak_poll_now

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting scraper run" >> "$LOG_DIR/cron.log"

# Articles
cd "$SCRAPER_DIR"
$PYTHON scraper.py >> "$LOG_DIR/cron.log" 2>&1
$PYTHON gb_scraper.py >> "$LOG_DIR/cron.log" 2>&1
$PYTHON multi_scraper.py >> "$LOG_DIR/cron.log" 2>&1

# Videos
$PYTHON fih_video_scraper.py >> "$LOG_DIR/cron.log" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scrapers done — triggering bot poll" >> "$LOG_DIR/cron.log"
touch "$TRIGGER"
