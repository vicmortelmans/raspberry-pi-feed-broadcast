#!/bin/sh
export GOOGLE_APPLICATION_CREDENTIALS="~/joyce-2d487b74673d.json"
python get_news.py $@
