#!/usr/bin/python3
from google.cloud import texttospeech
from gpiozero import Button
from logging import handlers
from logging.handlers import RotatingFileHandler
from signal import pause
import argparse
import codecs
import feedparser
import logging
import os
import re
import sys
import sys
import threading
import time

urls_news = ["https://www.standaard.be/rss/section/1f2838d4-99ea-49f0-9102-138784c7ea7c","https://www.standaard.be/rss/section/e70ccf13-a2f0-42b0-8bd3-e32d424a0aa0"]
status_koningsoord = "https://klanten.connectingmedia.nl/koningsoord/stream-embed.php"
stream_koningsoord = "http://source.audio.true.nl:8000/abdijkoningsoord"
tune_news = "pips.ogg"
tune_angelus = "angelus.mp3"
db_news = "news.db"

# touch db_news
if not os.path.exists(db_news):
  codecs.open(db_news, 'a', 'utf8').close()

DEBUG = True

#setup logging
logger = logging.getLogger('')
logger.setLevel(logging.DEBUG)
format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(format)
logger.addHandler(ch)
fh = handlers.RotatingFileHandler("get_news.log", maxBytes=(1048576*5), backupCount=7)
fh.setFormatter(format)
logger.addHandler(fh)
logger.info("Starting get_news.py")

# Initiate the command line parser
parser = argparse.ArgumentParser()
parser.add_argument("--silent", "-s", action="store_true", help="Don't play sound, only print out.")
args = parser.parse_args()

# Instantiates a Google TTS client
if not args.silent:
  client = texttospeech.TextToSpeechClient()

# Define the buttons
Button.was_held = False
button_backward = Button(20)
button_forward = Button(26)
switch_news = Button(13)
switch_getijden = Button(19)
button_play = Button(16)
button_mute = Button(21)

broadcast_mute = False
 
# Decorator for threaded functions
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
  switch_getijden.when_pressed = play_getijden
  switch_getijden.when_released = stop_playing_getijden
  button_play.when_released = read_latest_item
  button_play.when_held = read_latest_5_items
  button_mute.when_pressed = kill_playing_broadcasts
  
  # Start polling the news feeds
  news()

  # Start polling getijden
  getijden()

  # Wait for things to happen
  pause()

#
# Button handlers
#

klok_lock = threading.Lock()
pending_calibration = None

def schedule_calibration():
  global pending_calibration
  if pending_calibration: 
    pending_calibration.cancel()
    logger.info("Canceled a pending calibration")
  pending_calibration = threading.Timer(10.0, calibrate)
  pending_calibration.start()
  logger.info("Scheduled a calibration")


def calibrate():
  logger.info("Acquiring the klok_lock...")
  klok_lock.acquire()
  logger.info("Going to calibrate the clock")
  os.system('python /home/pi/Public/klok/klok_calibrate.py')
  klok_lock.release()


@threaded
def one_minute_backward():
  if not button_backward.was_held:
    logger.info("Acquiring the klok_lock...")
    klok_lock.acquire()
    logger.info("[BUTTON] Going one minute backward")
    os.system('python /home/pi/Public/klok/klok_1_minute_hands_backward.py')
    schedule_calibration()
    klok_lock.release()
  button_backward.was_held = False


@threaded
def ten_minutes_backward():
  button_backward.was_held = True
  logger.info("Acquiring the klok_lock...")
  klok_lock.acquire()
  logger.info("[BUTTON] Going ten minutes backward")
  os.system('python /home/pi/Public/klok/klok_10_minutes_hands_backward.py')
  schedule_calibration()
  klok_lock.release()


@threaded
def one_minute_forward():
  if not button_forward.was_held:
    logger.info("Acquiring the klok_lock...")
    klok_lock.acquire()
    logger.info("[BUTTON] Going one minute forward")
    os.system('python /home/pi/Public/klok/klok_1_minute_hands_forward.py')
    schedule_calibration()
    klok_lock.release()
  button_forward.was_held = False


@threaded
def ten_minutes_forward():
  button_forward.was_held = True
  logger.info("Acquiring the klok_lock...")
  klok_lock.acquire()
  logger.info("[BUTTON] Going ten minutes forward")
  os.system('python /home/pi/Public/klok/klok_10_minutes_hands_forward.py')
  schedule_calibration()
  klok_lock.release()


def play_getijden():
  global getijden_playing
  if not getijden_playing:
    logger.info("[BUTTON] Play getijden")
    status = fetch_h1(status_koningsoord)
    if "gestart" in status:
      broadcast([status], tune_angelus)
      broadcast_getijden(stream_koningsoord) 
    else:
      broadcast([status], None)
  else:
    logger.info("[BUTTON] Play getijden, but already playing. Strange...")

def announce_getijden():
  broadcast([], tune_angelus)

def stop_playing_getijden():
  global getijden_playing
  if getijden_playing:
    logger.info("[BUTTON] Stop getijden")
    os.system('killall omxplayer.bin')
  else:
    logger.info("[BUTTON] Stop getijden, but not playing, so doing nothing")


def read_latest_item():
  if not button_play.was_held:
    # it's been noticed in the logs that the broadcasting thread got stuck somehow and the
    # lock wouldn't be released. Let's assume that the user doesn't push this button during
    # a broadcast, and just release the lock to be safe.
#    broadcast_lock.release()
#    logger.info("Broadcasting lock released by pushing READ button")
    # processing request
    logger.info("[BUTTON] Going to read")
    logger.info("Going to read news")
    lines = get_first_lines_from_db(db_news, 1)
    broadcast(lines, tune_news)
  button_play.was_held = False


def read_latest_5_items():
  button_play.was_held = True
  # it's been noticed in the logs that the broadcasting thread got stuck somehow and the
  # lock wouldn't be released. Let's assume that the user doesn't push this button during
  # a broadcast, and just release the lock to be safe.
  broadcast_lock.release()
  logger.info("Broadcasting lock released by pushing READ button")
  # processing request
  logger.info("[BUTTON] Going to read a lot")
  logger.info("Going to read a lot of news")
  lines = get_first_lines_from_db(db_news, 5)
  broadcast(lines, tune_news)


def kill_playing_broadcasts():
  global broadcast_mute
  logger.info("[BUTTON] Stop reading")
  logger.info("Set broadcast_mute to True")
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

getijden_playing = False
getijden_annouced = False

def getijden():

  global getijden_playing
  global getijden_announced

  # This function runs in the background every five minutes. It reads the status_koningsoord.
  # If they're streaming AND the switch is enabled, it starts an omxplayer with the stream
  # In the meanwhile, it keeps polling, because if the streaming ends, the omxplayer must
  # be killed.

  logger.info("Polling getijden started")

  status = fetch_h1(status_koningsoord)
  if getijden_playing:
    if "gestart" in status:
      logger.info("Getijden are playing and still live... just go on playing")
      pass  # continue playing
    else:  
      logger.info("Getijden are playing but no longer live... stop playing")
      stop_playing_getijden()
      getijden_announced = False
  else: # not getijden_playing
    if "gestart" in status:
      if switch_getijden.is_pressed:
        logger.info("Getijden are going live and switch is on... start playing")
        start_playing_getijden()
      else:
        if getijden_announced:
          logger.info("Getijden are going live but switch is off and already announced...")
        else:
          announce_getijden()
          getijden_announced = True
    else:
      logger.info("Getijden are not live.")
      getijden_announced = False

  # set a timer to run news() again in 5 minutes
  if DEBUG:
    interval = 30.0
  else:
    interval = 300.0
  threading.Timer(interval, getijden).start()


def news():

  # This function runs in the background every five minutes. It reads a number of 
  # feeds (urls_news). All items from the feeds are stored into a single list of items. 
  # This list is converted to a list of lines. This list is filtered, keeping the lines 
  # that are not in the datase (db_news). The database lines are filtered, keeping the
  # lines that are still in the feeds.
  # The database is rewritten with new lines first and then the old lines.
  # New lines are broadcasted.

  logger.info("Fetching news started")

  items = []
  for url in urls_news:
    feed = feedparser.parse(url)
    items.extend(feed.entries)
    
  lines = extract_titles_and_descriptions(items)

  logger.info("Fetched lines: " + str(len(lines)) + "")

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
      logger.info("Slightly updated line that will be ignored: " + line + "")
      old_lines.append(line)

  logger.info("Fetched new lines: " + str(len(new_lines)) + "")

  if len(new_lines):

      for db_line in db_lines:
        if db_line in lines:
          old_lines.append(db_line)

      logger.info("Kept old lines: " + str(len(old_lines)) + "")

      # add all the posts to the database (new posts first)
      f = codecs.open(db_news, 'w', 'utf8')
      for line in new_lines + old_lines:
        f.write(line + "\n")
      f.close
          
      # output all of the new posts
      if switch_news.is_pressed:
        logger.info("Going to read new lines: " + str(len(new_lines)) + "")
        broadcast(new_lines, tune_news)
      else:
        logger.info("News reading switch is disabled")

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

@threaded
def broadcast(lines, tune):
  global broadcast_mute

  logger.info("Broadcasting started")

  logger.info("Broadcasting waiting for lock...")
  broadcast_lock.acquire()
  logger.info("Broadcasting lock acquired")

  if not args.silent:

    for num, line in enumerate(lines):
      line_to_numbered_audio(line, num)
      
    # run through all audio for this session; not that it's important to 
    # keep checking broadcast_mute, as it can be set by an event outside of this loop!

    # Play the announcement tune
    if tune and not broadcast_mute:
      logger.info("Playing tune: " + tune + "")
      os.system("omxplayer --no-keys --no-osd " + tune)

    for num, line in enumerate(lines):
      # Play the audio file
      if not broadcast_mute:
        logger.info("Playing audio for line: " + line + " from output" + str(num) + ".mp3")
        os.system("omxplayer --no-keys --no-osd output" + str(num) + ".mp3")
      else:
        logger.info("broadcast_mute is True - not Playing audio for line: " + line + " from output" + str(num) + ".mp3")

  else:  # args.silent requested

    if DEBUG:
      for line in lines:
        if not broadcast_mute:
          os.system('echo "'+ line + '" | pv -L 20 -q')

  if broadcast_mute:
    broadcast_mute = False
    logger.info("Set broadcast_mute to False")

  broadcast_lock.release()
  logger.info("Broadcasting lock released")

  logger.info("Broadcasting done")

  return


@threaded
def broadcast_getijden(stream):
  global getijden_playing

  getijden_playing = True
  logger.info("Broadcasting getijden started")

  logger.info("Broadcasting getijden waiting for lock...")
  broadcast_lock.acquire()
  logger.info("Broadcasting lock acquired for getijden")

  if not args.silent:
  
      logger.info("Playing stream: " + stream + "")
      os.system("omxplayer --no-keys --no-osd --live " + stream)

  broadcast_lock.release()
  logger.info("Broadcasting lock released for getijden")

  getijden_playing = False
  logger.info("Broadcasting getijden done")

  return


def line_to_numbered_audio(line, num):
  # Set the text input to be synthesized
  ssml = line_to_ssml(line)
#      import pdb; pdb.set_trace()
  logger.info("SSML formatted line: " + ssml + "")
  logger.info("Going to SynthesisInput")
  synthesis_input = texttospeech.types.SynthesisInput(ssml=ssml)

  # Build the voice request, select the language code ("en-US") and the ssml
  # voice gender ("neutral")
  logger.info("Going to VoiceSelectionParams")
  voice = texttospeech.types.VoiceSelectionParams(
    language_code='nl-NL',
    name='nl-NL-Wavenet-C',
    ssml_gender=texttospeech.enums.SsmlVoiceGender.MALE)

  # Select the type of audio file you want returned
  logger.info("Going to AudioConfig")
  audio_config = texttospeech.types.AudioConfig(
    audio_encoding=texttospeech.enums.AudioEncoding.MP3,
    volume_gain_db=-1.0)

  # Perform the text-to-speech request on the text input with the selected
  # voice parameters and audio file type
  logger.info("Going to synthesize_speech")
  response = client.synthesize_speech(synthesis_input, voice, audio_config)

  # The response's audio_content is binary.
  logger.info("Going to write audio content to file")
  with open('output' + str(num) + '.mp3', 'wb') as out:
    # Write the response to the output file.
    out.write(response.audio_content)
    print('Audio content written to file output' + str(num) + '.mp3')


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
  value = value
  value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
  value = re.sub('[^\w\s.-]', '', value).strip().lower()
  value = re.sub('[-\s]+', '-', value)
  return value


def clean_string(s):
  import html
  return html.unescape(re.sub('<[^<]+?>', ' ', re.sub('</p>', '. ', s.replace("\n"," "))))


def line_to_ssml(s):
  import nltk.data
  from lxml import etree
  sent_detector = nltk.data.load('tokenizers/punkt/dutch.pickle')
  sentences = sent_detector.tokenize(s.strip())
  speak = etree.Element('speak')
  for sentence in sentences:
    s = etree.Element('s')
    s.text = sentence
    speak.append(s)
  return etree.tostring(speak, encoding='unicode', method='xml')


def line_in_list_fuzzy_ratio(line,list_of_lines):
  from fuzzywuzzy import fuzz
  m = 0
  for l in list_of_lines:
    m = max(m, fuzz.ratio(line.lower(), l.lower()))
  return m


def fetch_h1(url):
  from urllib.request import urlopen
  from bs4 import BeautifulSoup
  html = urlopen(url)
  bsh = BeautifulSoup(html.read(), 'html.parser')
  return bsh.h1.text


if __name__ == '__main__':
    main()
