#!/usr/bin/python

import feedparser
import time
import sys
from google.cloud import texttospeech
import os
import argparse
from gpiozero import Button
from signal import pause
import threading
import re
from HTMLParser import HTMLParser
import codecs
from fuzzywuzzy import fuzz
import sys
reload(sys)
sys.setdefaultencoding('utf8')

urls_news = ["https://www.standaard.be/rss/section/1f2838d4-99ea-49f0-9102-138784c7ea7c","https://www.standaard.be/rss/section/e70ccf13-a2f0-42b0-8bd3-e32d424a0aa0", "https://data.buienradar.nl/1.0/feed/xml/rssbuienradar" ]
url_angelus = "https://www.bijbelcitaat.be/feed/"
tune_news = "pips.ogg"
tune_angelus = "angelus.mp3"
db_news = "news.db"
if not os.path.exists(db_news):
  codecs.open(db_news, 'a', 'utf8').close()

DEBUG = True

# Initiate the parser
parser = argparse.ArgumentParser()

# Add long and short argument
parser.add_argument("--silent", "-s", action="store_true", help="Don't play sound, only print out.")

# Read arguments from the command line
args = parser.parse_args()

# Instantiates a client
if not args.silent:
  client = texttospeech.TextToSpeechClient()

# Define the buttons
Button.was_held = False
button_backward = Button(20)
button_forward = Button(26)
switch_news = Button(13)
switch_play_news_or_angelus = Button(19)
button_play = Button(16)
button_mute = Button(21)

broadcast_mute = False
 

def threaded(fn):
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread
    return wrapper


def main():
  # Configure event handlers
  button_backward.when_released = one_minute_backward
  button_backward.when_held = ten_minutes_backward
  button_forward.when_released = one_minute_forward
  button_forward.when_held = ten_minutes_forward
  button_play.when_released = read_latest_item
  button_play.when_held = read_latest_5_items
  button_mute.when_pressed = kill_playing_broadcasts
  
  # Start polling the news feeds
  news()

  # Wait for things to happen
  pause()

#
# Button handlers
#

klok_lock = threading.Lock()
pending_calibration = None

def schedule_calibration():
  global pending_calibration
#  import pdb; pdb.set_trace()
  if pending_calibration: 
    pending_calibration.cancel()
    if DEBUG: sys.stderr.write("Canceled a pending calibration\n")
  pending_calibration = threading.Timer(10.0, calibrate)
  pending_calibration.start()
  if DEBUG: sys.stderr.write("Scheduled a calibration\n")


def calibrate():
  klok_lock.acquire()
  if DEBUG: sys.stderr.write("Going to calibrate the clock\n")
  os.system('python /home/pi/Public/klok/klok_calibrate.py')
  klok_lock.release()


@threaded
def one_minute_backward():
  if not button_backward.was_held:
    klok_lock.acquire()
    if DEBUG: sys.stderr.write("Going one minute backward\n")
    os.system('python /home/pi/Public/klok/klok_1_minute_hands_backward.py')
    schedule_calibration()
    klok_lock.release()
  button_backward.was_held = False


@threaded
def ten_minutes_backward():
  button_backward.was_held = True
  klok_lock.acquire()
  if DEBUG: sys.stderr.write("Going ten minutes backward\n")
  os.system('python /home/pi/Public/klok/klok_10_minutes_hands_backward.py')
  schedule_calibration()
  klok_lock.release()


@threaded
def one_minute_forward():
  if not button_forward.was_held:
    klok_lock.acquire()
    if DEBUG: sys.stderr.write("Going one minute forward\n")
    os.system('python /home/pi/Public/klok/klok_1_minute_hands_forward.py')
    schedule_calibration()
    klok_lock.release()
  button_forward.was_held = False


@threaded
def ten_minutes_forward():
  button_forward.was_held = True
  klok_lock.acquire()
  if DEBUG: sys.stderr.write("Going ten minutes forward\n")
  os.system('python /home/pi/Public/klok/klok_10_minutes_hands_forward.py')
  schedule_calibration()
  klok_lock.release()


def read_latest_item():
  if not button_play.was_held:
      if DEBUG: sys.stderr.write("Going to read\n")
      if not switch_play_news_or_angelus.is_pressed: 
        if DEBUG: sys.stderr.write("Going to read angelus\n")
        items = get_first_items_from_live_feed(url_angelus, 2)
        lines = extract_titles_and_contents(items)
        broadcast(lines, tune_angelus)
      else:
        if DEBUG: sys.stderr.write("Going to read news\n")
        lines = get_first_lines_from_db(db_news, 1)
        broadcast(lines, tune_news)
  button_play.was_held = False


def read_latest_5_items():
  button_play.was_held = True
  if DEBUG: sys.stderr.write("Going to read a lot\n")
  if not switch_play_news_or_angelus.is_pressed: 
    if DEBUG: sys.stderr.write("Going to read angelus\n")
    items = get_first_items_from_live_feed(url_angelus, 2)
    lines = extract_tiles_and_contents(items)
    broadcast(lines, tune_angelus)
  else:
    if DEBUG: sys.stderr.write("Going to read a lot of news\n")
    lines = get_first_lines_from_db(db_news, 5)
    broadcast(lines, tune_news)


def kill_playing_broadcasts():
  global broadcast_mute
  if DEBUG: sys.stderr.write("Stop reading\n")
  broadcast_mute = True
  os.system('killall omxplayer.bin')
  if DEBUG: 
    os.system('killall pv')

#
# Functions
#

def get_first_items_from_live_feed(url, count):
  feed = feedparser.parse(url)
  return feed.entries[0:count]


def get_first_lines_from_db(db, count):
  lines = []

  with codecs.open(db, 'r', 'utf8') as database:
    for line in database:
      if len(lines) < count:
        lines.append(line)
      else: 
        break 
  return lines


def extract_descriptions(items):
  lines = []
  for item in items:
    lines.append(clean_string(item.description))
  return lines
    

def extract_titles_and_descriptions(items):
  lines = []
  for item in items:
    lines.append(clean_string(item.title + '. ' + item.description))
  return lines
    

def extract_titles_and_contents(items):
  lines = []
  for item in items:
    lines.append(clean_string(item.title + '. ' + item.content[0].value))
  return lines
    
#
# Background functions
#

def news():

  # This function runs in the background every five minutes. It reads a number of 
  # feeds (urls_news). All items from the feeds are stored into a single list of items. 
  # This list is converted to a list of lines. This list is filtered, keeping the lines 
  # that are not in the datase (db_news). The database lines are filtered, keeping the
  # lines that are still in the feeds.
  # The database is rewritten with new lines first and then the old lines.
  # New lines are broadcasted.

  if DEBUG: sys.stderr.write("Fetching news started\n")

  items = []
  for url in urls_news:
    feed = feedparser.parse(url)
    items.extend(feed.entries)
    
  lines = extract_titles_and_descriptions(items)

  if DEBUG: sys.stderr.write("Fetched lines: " + str(len(lines)) + "\n")

  db_lines = []
  with codecs.open(db_news, 'r', 'utf8') as database:
    for db_line in database:
      db_lines.append(db_line.replace("\n","")) 

  new_lines = []
  old_lines = []

  for line in lines:
    fuzzy_ratio = line_in_list_fuzzy_ratio(line, db_lines)
    if fuzzy_ratio < 90:
      new_lines.append(line)
    elif fuzzy_ratio < 100:
      if DEBUG: sys.stderr.write("Updated line: " + line + "\n")
      old_lines.append(line)

  if DEBUG: sys.stderr.write("Fetched new lines: " + str(len(new_lines)) + "\n")

  if len(new_lines):

      for db_line in db_lines:
        if db_line in lines:
          old_lines.append(db_line)

      if DEBUG: sys.stderr.write("Kept old lines: " + str(len(old_lines)) + "\n")

      # add all the posts to the database (new posts first)
      f = codecs.open(db_news, 'w', 'utf8')
      for line in new_lines + old_lines:
        f.write(unicode(line) + "\n")
      f.close
          
      # output all of the new posts
      if switch_news.is_pressed:
        if DEBUG: sys.stderr.write("Going to read new lines: " + str(len(new_lines)) + "\n")
        broadcast(new_lines, tune_news)

  # set a timer to run news() again in 5 minutes
  if DEBUG:
    interval = 30.0
  else:
    interval = 300.0
  threading.Timer(interval, news).start()


#
# Audio
#

broadcast_lock = threading.Lock()

def broadcast(lines, tune):
  thread = threading.Thread(target = broadcast_thread, args = (lines, tune))
  thread.start()
  return


def broadcast_thread(lines, tune):
  global broadcast_mute

  if DEBUG: sys.stderr.write("Broadcasting started\n")

  broadcast_lock.acquire()

  for num, line in enumerate(lines):
    print(line + "\n")

    if len(lines) and not args.silent:
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
      with open('output' + str(num) + '.mp3', 'wb') as out:
        # Write the response to the output file.
        out.write(response.audio_content)
        print('Audio content written to file "output' + str(num) + '.mp3"')
      
  if len(lines):
    if not args.silent:
      # Play the announcement tune
      if tune and not broadcast_mute:
        if DEBUG: sys.stderr.write("Playing tune: " + tune + "\n")
        os.system("omxplayer " + tune)

      for num, line in enumerate(lines):
        # Play the audio file
        if not broadcast_mute:
          if DEBUG: sys.stderr.write("Playing audio for line: " + line + "\n")
          os.system("omxplayer output" + str(num) + ".mp3")
    else:
      if DEBUG:
        for line in lines:
          if not broadcast_mute:
            os.system('echo "'+ line + '" | pv -L 20 -q')

  broadcast_mute = False
  broadcast_lock.release()

  if DEBUG: sys.stderr.write("Broadcasting done\n")

  return

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


def clean_string(s):
    return HTMLParser().unescape(re.sub('<[^<]+?>', '', s.replace("\n"," ").encode('utf8','replace')))


def line_in_list_fuzzy_ratio(line,list_of_lines):
    m = 0
    for l in list_of_lines:
        m = max(m, fuzz.ratio(line.lower(), l.lower()))
    return m


if __name__ == '__main__':
    main()
