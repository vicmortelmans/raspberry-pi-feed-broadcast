#!/bin/bash -l
exec 1> >(logger -s -t $(basename $0)) 2>&1
cd /home/vic/raspberry-pi-feed-broadcast
export GOOGLE_APPLICATION_CREDENTIALS="/home/vic/joyce-2d487b74673d.json"
export DISPLAY=:0.0
source env/bin/activate
python get_news.py $@
