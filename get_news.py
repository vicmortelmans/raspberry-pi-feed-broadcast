#!/usr/bin/python

import feedparser
import time
import sys
#from espeak import espeak
from google.cloud import texttospeech
import os
import argparse

DEBUG = False

def main():

    # Initiate the parser
    parser = argparse.ArgumentParser()

    # Add long and short argument
    parser.add_argument("--silent", "-s", action="store_true", help="Don't play sound, only print out.")
    parser.add_argument("--url", "-u", required=True, help="URL of the RSS feed.")
    parser.add_argument("--tune", "-t", help="Filename of the announcement tune.")

    # Read arguments from the command line
    args = parser.parse_args()

    # Instantiates a client
    if not args.silent:
        client = texttospeech.TextToSpeechClient()

    url = 'https://www.vrt.be/vrtnws/nl.rss.articles.xml'

    db = './' + slugify(url) + '.db'

    #
    # get the feed data from the url
    #
    feed = feedparser.parse(url)

    #
    # figure out which posts to print
    #
    posts_to_print = []
    posts_to_skip = []

    for post in feed.entries:
        # if post is already in the database, skip it
        title = post.title.replace("\n","").encode('utf8','replace')
        if post_is_in_db(title, db):
            posts_to_skip.append(title)
            if DEBUG: sys.stderr.write("posts to skip: " + str(len(posts_to_skip)) + "\n")
        else:
            posts_to_print.append(title)
            if DEBUG: sys.stderr.write("posts to print: " + str(len(posts_to_print)) + "\n")
        
    #
    # add all the posts we're going to print to the database with the current timestamp
    #
    f = open(db, 'w')
    for title in posts_to_skip + posts_to_print:
        f.write(title + "\n")
    f.close
        
    #
    # output all of the new posts
    #
    for title in posts_to_print:
        print(title + "\n")

        if not args.silent:
            # Play the announcement tune
            if args.tune:
                os.system("omxplayer " + args.tune)

            # Set the text input to be synthesized
            synthesis_input = texttospeech.types.SynthesisInput(text=title)

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

def post_is_in_db(title, db):
    if not os.path.exists(db):
        open(db, 'a').close()
    with open(db, 'r') as database:
        for line in database:
            if title in line:
                if DEBUG: sys.stderr.write("post found in db: " + title + "\n")
                return True
    if DEBUG: sys.stderr.write("post not found in db: " + title + "\n")
    return False


if __name__ == '__main__':
    main()
