#!/bin/bash
cd /mnt/playground/workspace/workspace-data-engineering/projects/real-estate-scraper || exit 1
python3 src/daily_pipeline.py "${1:-1000}" >> /tmp/realestate-cron.log 2>&1
