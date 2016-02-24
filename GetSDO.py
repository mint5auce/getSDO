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
import datetime

# Feed Config
fdir = '/Users/jonh/Pictures/sdo-feed/'
sdo_rss_root = 'http://feeds.feedburner.com/nasa/'
sdo_rss_views = ['aia_131', 'aia_171', 'aia_193', 'aia_211', 'aia_304', 'aia_335', 'aia_1700'] # Pretty ones only + 1700 for sun spots

# File and date config
today = datetime.date.today().strftime("%Y%m%d")
purgeday = (datetime.date.today() - datetime.timedelta(days=8)).strftime("%Y%m%d")
sdofiles = [f for f in os.listdir(fdir) if os.path.isfile(os.path.join(fdir, f))]
sdofiles.remove('.DS_Store')

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
            if fname not in sdofiles:
                output = open( fout, 'wb' )
                output.write( data )
                output.close()
                print 'File downloaded: ', fname
            else:
                print 'File skipped: ', fname
    except:
            print 'URL error: ', url
            pass
