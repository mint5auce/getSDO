# GetSDO.py
#
# A Python script to download the latest image from NASA's Solar Dynamics
# Observatory RSS feed.
# I use it from a launchd job to set the wallpaper on my Mac ;)
#
# Requires (pip install -r requirements.txt)
#
# Growl removed. Caused issues and I don't require notification
#
# Universal Feed Parser (https://github.com/kurtmckee/feedparser
# / https://pythonhosted.org/feedparser/)
#       for RSS fetch & parse
# BeautifulSoup (http://www.crummy.com/software/BeautifulSoup/)
#       for parsing HTML in the RSS feed
#
# Based on BigPicture.py by: Henry Cooke (me@prehensile.co.uk)
# https://gist.github.com/prehensile/675906

import feedparser
import urllib2
from BeautifulSoup import BeautifulSoup

import os
import time

import pdb


# config
fout = '/Users/jonh/Pictures/sdo-feed/sdo.jpeg'
bp_rss = 'http://feeds.feedburner.com/nasa/aia_193?format=xml'

# check age of existing file
# @TODO: I want all form last 24 hours. Not 1 for each 24 hours. Or do I...
# @TODO: Or .... match date to today / last 24 hours from XML
if( os.access( fout, os.F_OK ) ):
        stats = os.stat( fout )
        mtime = stats.st_mtime
        now = time.time()
        if( now - mtime < (60 * 60 * 24) ):
                exit( "Existing file is newer than a day old" );

# Parse rss
feed = feedparser.parse( bp_rss )
items = feed[ "items" ]
url = items[0]['media_content'][0]['url']

# Gonna want a for loop eventually, to get all images
# pdb.set_trace()



# It's all RSS, so pretty sure I don't need Soup, only FeedParser.
# leading_item = items[ 0 ]
# soup = BeautifulSoup( leading_item[ "description" ] )
# Class no longer exists
# img = soup.find( "img", { "class" : "bpImage" } )
# img = soup.find( "img" )
# url = img[ "src" ]

# download image
try:
        data = urllib2.urlopen( url ).read()
        output = open( fout, 'wb' )
        output.write( data )
        output.close()
except:
        pass
