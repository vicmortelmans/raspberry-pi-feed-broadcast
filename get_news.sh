#!/bin/sh
cd /home/pi/Public/raspberry-pi-feed-broadcast
export GOOGLE_APPLICATION_CREDENTIALS="/home/pi/joyce-2d487b74673d.json"
python3 get_news.py $@
