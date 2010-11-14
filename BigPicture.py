# BigPicture.py
#
# A Python script to download the latest image from Boston Big Picture's RSS.
# I use it from a launchd job to set the wallpaper on my Mac ;) 
#
# Requires:
# Universal Feed Parser (http://www.feedparser.org/)
# 	for RSS fetch & parse
# BeautifulSoup (http://www.crummy.com/software/BeautifulSoup/)
#	for parsing HTML in the RSS feed
# GrowlPython (http://growl.info/documentation/developer/python-support.php)
#	for notifying the user of a new download
#	(easy enough to remove on non-Jobs platfroms)
#
# Author:
#	Henry Cooke (me@prehensile.co.uk)

import feedparser
import urllib2
from BeautifulSoup import BeautifulSoup
import Growl
import os
import time


# config
fout = '/Users/henry/Pictures/wallpaper*/BigPicture.jpeg'
bp_rss = 'http://feeds.boston.com/boston/bigpicture/index';

# check age of existing file
if( os.access( fout, os.F_OK ) ):
	stats = os.stat( fout )
	mtime = stats.st_mtime
	now = time.time()
	if( now - mtime < (60 * 60 * 24) ):
		exit( "Existing file is newer than a day old" );

# parse rss
feed = feedparser.parse( bp_rss )
items = feed[ "items" ]
leading_item = items[ 0 ]
soup = BeautifulSoup( leading_item[ "description" ] )
img = soup.find( "img", { "class" : "bpImage" } )
url = img[ "src" ]

# download image
try:
	data = urllib2.urlopen( url ).read()
	output = open( fout, 'wb' )
	output.write( data )
	output.close()
except:
	pass
	
# notify bearded user
gn = Growl.GrowlNotifier( "BigPictureAgent", ["Download completed"] )
gn.register()
gn.notify( "Download completed", "Download complete", "BigPictureAgent downloaded a new picture for %s." % leading_item["title"] )