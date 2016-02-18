# GetSDO.py
#
# A Python script to download the latest image from NASA's Solar Dynamics
# Observatory RSS feed.
#
# I use it to set the screensaver image source on my Mac
#
# Requires: Universal Feed Parser (https://github.com/kurtmckee/feedparser
# / https://pythonhosted.org/feedparser/)
#
# Based on BigPicture.py by: Henry Cooke (me@prehensile.co.uk)
# https://gist.github.com/prehensile/675906

import feedparser
import urllib2

import os
import time

# Testing
import pdb


# Config
fdir = '/Users/jonh/Pictures/sdo-feed/'
sdo_rss_root = 'http://feeds.feedburner.com/nasa/'
sdo_rss_views = ['aia_094', 'aia_131', 'aia_171', 'aia_193', 'aia_211', 'aia_304', 'aia_335', 'aia_1600', 'aia_1700', 'COMP094335193', 'COMP211193171', 'COMP304211171', 'COMPHMI171', 'hmib', 'hmibc', 'hmii', 'hmiic'] # hmid & f was offline at time of writing

# Parse RSS

# Get first image from each seperate type

for view in sdo_rss_views:
    sdo_rss = sdo_rss_root + view + '?format=xml'
    feed = feedparser.parse( sdo_rss )
    items = feed[ "items" ]
    url = items[0]['media_content'][0]['url'] # Just get first item

    # Download image
    try:
            data = urllib2.urlopen( url ).read()
            fname = view + '_' + url.split('/')[-1] # Feed images use same name, hence prefix
            fout = fdir+fname
            # @TODO: Don't download again if it exisits
            output = open( fout, 'wb' )
            output.write( data )
            output.close()
            print 'File downloaded: ', fname
    except:
            print 'URL error: ', url
            pass

# @TODO: Remove anything older than one week

# DEPRECATED - I want one a day (not enough changes hourly)
# Get all images from feed - RSS shows last 5 hours or so in 15 min intervals.

# for item in items:
#     # pdb.set_trace() # Test
#     url = item['media_content'][0]['url']
#     # pdb.set_trace() # Test
#
#     # download image
#     try:
#             data = urllib2.urlopen( url ).read()
#             fname = url.split('/')[-1]
#             fout = fdir+fname
#             # @TODO: Don't download again if it exisits
#             output = open( fout, 'wb' )
#             output.write( data )
#             output.close()
#             print 'File downloaded: ', url
#     except:
#             print 'File error: ', url
#             pass
