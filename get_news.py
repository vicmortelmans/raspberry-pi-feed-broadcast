#!/usr/bin/python

import feedparser
import time
import sys
from google.cloud import texttospeech
import os
import argparse
from gpiozero import Button
import threading

urls_news = ["https://www.standaard.be/rss/section/1f2838d4-99ea-49f0-9102-138784c7ea7c","https://www.standaard.be/rss/section/e70ccf13-a2f0-42b0-8bd3-e32d424a0aa0"]
url_angelus = "https://www.bijbelcitaat.be/feed/"
tune_news = "pips.ogg"
tune_angelus = "angelus.mp3"
db_news = "news.db"
if not os.path.exists(db_news):
  open(db_news, 'a').close()

DEBUG = False

# Initiate the parser
parser = argparse.ArgumentParser()

# Add long and short argument
parser.add_argument("--silent", "-s", action="store_true", help="Don't play sound, only print out.")

# Read arguments from the command line
args = parser.parse_args()

# Define the buttons
button_backward = Button(20)
button_forward = Button(26)
switch_news = Button(13)
switch_play_news_or_angelus = Button(19)
button_play = Button(16)
button_mute = Button(21)

broadcast_mute = False
  
def main():
  # Configure event handlers
  button_backward.when_released = one_minute_backward
  button_backward.when_held = ten_minutes_backward
  button_forward.when_released = one_minute_forward
  button_forward.when_held = ten_minutes_forward
  button_play.when_released = read_latest_item
  button_news.when_held = read_latest_5_items
  button_mute.when_pressed = kill_playing_broadcasts
  
  # Instantiates a client
  if not args.silent:
      client = texttospeech.TextToSpeechClient()

  # Start polling the news feeds
  news(urls_news, db_news)

  # Wait for things to happen
  pause()

#
# Button handlers
#

def one_minute_backward():
  os.system('python /home/vicmortelmans/Public/klok/klok_1_minute_hands_backward.py')


def ten_minutes_backward():
  os.system('python /home/vicmortelmans/Public/klok/klok_10_minutes_hands_backward.py')


def one_minute_forward():
  os.system('python /home/vicmortelmans/Public/klok/klok_1_minute_hands_forward.py')


def ten_minutes_forward():
  os.system('python /home/vicmortelmans/Public/klok/klok_10_minutes_hands_forward.py')


def read_latest_item():
  if switch_play_news_or_angelus.ispressed: 
    items = get_first_items_from_live_feed(url_angelus, 2)
    lines = extract_descriptions(items)
    broadcast(lines, tune_angelus)
  else:
    lines = get first_lines_from_db(db_news, 1)
    broadcast(lines, tune_news)


def read_latest_5_items():
  if switch_play_news_or_angelus.ispressed: 
    items = get_first_items_from_live_feed(url_angelus, 2)
    lines = extract_descriptions(items)
    broadcast(lines, tune_angelus)
  else:
    lines = get first_items_from_db(db_news, 5)
    broadcast(lines, tune_news)


def kill_playing_broadcasts():
  broadcast_mute = True
  os.system('killall omxplayer')

#
# Functions
#

def get_first_items_from_live_feed(url, count):
  feed = feedparser.parse(url)
  return feed.entries[0:count]

def get_first_lines_from_db(db, count):
  lines = []
  with open(db, 'r') as database:
    for line in database:
      if length(lines) < count:
        lines += line
      else 
        break 

def extract_desriptions(items):
  lines = []
  for item in items:
    lines += item.description.replace("\n","").encode('utf8','replace')
    
def extract_titles_and_desriptions(items):
  lines = []
  for item in items:
    lines += (item.title + ' ' + item.description).replace("\n","").encode('utf8','replace')
    
#
# Background functions
#

def news():

  # This function runs in the background every five minutes. It reads a number of 
  # feeds (urls_news). All items from the feeds are stored into a single list of items. 
  # This list is converted to a list of lines. Out of this list, two lists are made,
  # one with the lines that were not in the datase (db_news) and one with the items that were.
  # The database is rewritten with new lines first and then the old lines.
  # New lines are broadcasted.

  items = []
  for url in urls_news:
    feed = feedparser.parse(url)
    items += feed.entries
    
  lines = extract_tiles_and_descriptions(items)

  db_lines = []
  with open(db_news, 'r') as database:
    for db_line in database:
      db_lines += db_line 

  new_lines = []
  old_lines = []
  for line in lines:
    if line in db_lines:
      old_lines += line
    else:
      new_lines += line

  # add all the posts to the database (new posts first)
  f = open(db, 'w')
  for line in new_lines + old_lines:
    f.write(line + "\n")
  f.close
      
  # output all of the new posts
  if switch_news.is_pressed():
    broadcast(new_lines, tune_news)

  # set a timer to run news() again in 5 minutes
  threading.Timer(300.0, news).start()


#
# Audio
#

lock = threading.Lock()

def broadcast(lines, tune):

  lock.acquire()

  if length(posts) and not args.silent and not broadcast_mute:
    # Play the announcement tune
    if args.tune:
      os.system("omxplayer " + tune)

  for line in lines:
    print(line + "\n")

    if length(posts) and not args.silent and not broadcast_mute:
      # Set the text input to be synthesized
      synthesis_input = texttospeech.types.SynthesisInput(text=line)

      # Build the voice request, select the language code ("en-US") and the ssml
      # voice gender ("neutral")
      voice = texttospeech.types.VoiceSelectionParams(
        language_code='nl-NL',
        ssml_gender=texttospeech.enums.SsmlVoiceGender.MALE)

      # Select the type of audio file you want returned
      audio_config = texttospeech.types.AudioConfig(
        audio_encoding=texttospeech.enums.AudioEncoding.MP3)

      # Perform the text-to-speech request on the text input with the selected
      # voice parameters and audio file type
      response = client.synthesize_speech(synthesis_input, voice, audio_config)

      # The response's audio_content is binary.
      with open('output.mp3', 'wb') as out:
        # Write the response to the output file.
        out.write(response.audio_content)
        print('Audio content written to file "output.mp3"')
      
      # Play the audio file
      os.system("omxplayer output.mp3")

  broadcast_mute = False
  lock.release()

#
# Generic functions
#

def slugify(value):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters
    (except dot, to  make sure the file extension is kept),
    and converts spaces to hyphens.
    """
    import unicodedata
    import re
    value = unicode(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
    value = unicode(re.sub('[^\w\s.-]', '', value).strip().lower())
    value = unicode(re.sub('[-\s]+', '-', value))
    return value


if __name__ == '__main__':
    main()
