#!/bin/sh
cd /home/vic/raspberry-pi-feed-broadcast
export GOOGLE_APPLICATION_CREDENTIALS="/home/vic/joyce-2d487b74673d.json"
python3 get_news.py $@
