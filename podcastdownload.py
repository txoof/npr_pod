#!/usr/bin/env python
# Copyright 2016 Aaron ciuffo

version = '''NPR Podcast Downloader V5.1

by Aaron Ciuffo (txoof.com)
released without warranty under GPLV3:
http://www.gnu.org/licenses/gpl-3.0.html
Please don't sue me.
'''

programName = 'podcastdownload'

# Imports
from datetime import datetime # for time stuff
import pytz
import logging # logging library
#from urllib2 import urlopen # standard library for interfacing with web resources
import urllib2 # standard library for interfacing with web resources 
from urllib2 import URLError
import re # regular expressions
import json # handle JSON objects
import os # Opperating System interface 
import sys # internal opperations including a list of imported modules
import fnmatch # used by cleanup method in Episode
import glob # used by m3u method - consider replacing with some other library
import shutil # used by cleanup method
import argparse # parse command line arguments
import ConfigParser # parse config files
from random import SystemRandom 




# In[11]:

releaseNotes = '''Release Notes
V 5.1
* Added "Artist" tag to NPR Segments
* Added date to album name
V5.0
* Rewrite and cleanup 
 - Cleanup of variables
 - Tidy messy loops
* Adapt NPREpisode object to use new class attributes for output paths
'''


# # TO DO
# ## Downloading
#  * add User-Agent string to NPREpisode class getEpisode https://docs.python.org/2/library/urllib2.html
#  * add command line option to download a show at a specific URL
#  * flawed logic causes the def download to return "false" if any segment does not download causing no m3u to be written later
#  * add feature to retry failed segments up to N times
#  
# ## Configuration
#  * Add configuration option to download album art from a specific URL and shove it into each episode folder
# 
# ## Completed
#  * General rewrite and cleanup 
#   - Move variables to one place
#   - reconsider some of the messier loops
#  * remove % in front of section names in configuration
#  * change name from 'Default' to 'Main' 
#  * Adapt NPREpisode object to use new class attributes for output paths
#  * complete the cleanup method
#  * remove any 'stale' episodes
#  * add a check to see if a program is already downloaded (maybe look for m3u) or at the download log
#  * -v overrides configuration file
#  * remove download logging - this is not necessary; it's a holdover from previous versions
#  * reorganize configuration options to allow commandline to influence logging  
#      - only log to a file if a logfile is specified
#      - add support for setting log from configuration file, setting logging level
#  * consider removing all the day and time checking for episodes; it's not relevant for HTML queries
#      - the day and time checking may be needed for API queries if this is implemented
#  * consider removing all the day and time checking for episodes; it's not relevant for HTML queries
#      - consider removing date and time check from showConfig class
#  * implement User-Agent in urllib2 request
#  * consider chainging import from urllib2; 2x import because of URLError AND urlopen
#  * Add option to generate configuration file if it is missing
#  * change default name of configuration file to ~/.programname.ini
#  * Test command line
#   - test all command line options 
#   - test all configuration options (remove options, sections, and otherwise break the config file) 
# 

# In[12]:

def loadModules():
    '''load non standard python modules'''
    import logging
    logging.basicConfig()
    logging.debug('loading module: requests')
    try:
        global requests
        import requests
    except Exception as e:
        logging.critical('Fatal Error\nFailed to load module: requests\n%s', e)
        logging.critical('Please install requests module: http://docs.python-requests.org/')
        exit(2)
        return(False)

    logging.debug('loading module: mutagen.mp3')
    # create a global list of all the taggers available
    global taggers
    taggers = {}
    try:
        global MP3
        from mutagen.mp3 import EasyMP3 as MP3
    except Exception, e:
        logging.critical('Failed to load module: mutagen.mp3\n%s', e)
        logging.critical('mp3 tagging may not be available')    
    taggers['mp3'] = MP3

    
    logging.debug('loading module: mutagen.mp4')
    try:
        global MP4
        from mutagen.mp4 import MP4
    except Exception, e:
        logging.critical('Failed to load module: mutagen.mp4\n%s', e)
        logging.critical('mp4 tagging may not be available')    
    taggers['mp4'] = MP4

    return(True)


# In[13]:

def div(num = 10, char = '*'):
    '''
    returns a multiple copies of a passed string
    Args:
        num (int): number of times to repeat string
        char (string): characters to repeat
    Returns:
        char*n (string)
    '''
    if isinstance(num, int):
        return(str(str(char)*num))
    else:
        return(str(char))


# In[14]:

class Episode():
    '''Podcast episode object'''

    def __init__(self, name = 'No Name', programURL = 'undef', outputBasePath = './', 
                 m3u = 'playlist.m3u', downloadLog = 'download.log', keep = 3, showDate = None,):
        '''
        Args:
            name (str): name of episode/podcast
            programURL (str): Index URL containing list of files to download
            showDate (str): date of episode
            outputBasePath (str): base path to use for output of files (default is ./)
            m3u (str): m3u playlist filename
            downloadLog (str): download log filename
            keep(int): maximumnumber of programs to keep
            
        Attributes:
            name (str): name of episode/podcast
            programURL (str): Index URL containing list of files to download
            segments (list): Segment() objects to be downloaded
            showDate (str): date of episode
            outputBasePath (str): base path to use for output of files (default is ./)
            outputShowPath (str): path within outputBasePath - slugified version of name
            outputPath (str): path within outputShowPath - set to outputShowPath by default
            m3u (str): m3u playlist filename
            downloadLog (str): download log filename
            keep (int): maximum number of programs to keep
        '''
        self.name = name # str
        self.programURL = programURL # str
        self.segments = [] # list
        self.segmentsFailed = [] #
        self.showDate = showDate # str
        self.outputBasePath = self._slash(outputBasePath) # str
        self.outputShowPath = self.outputBasePath + self._slash(self._slugify(self.name))
        self.outputPath = self.outputShowPath
        self.m3u = m3u
        self.downloadLog = downloadLog  
        self.keep = keep
    
    def attributes(self, display = None):
        '''
        method to show relevant attributes of
        Args:
            display (list): list of specific attributes to display
        Retruns:
            Specific attributes
        '''
        if isinstance(display, list):
            display = display
        else:
            display = ['name', 'programURL', 'showDate', 'outputBasePath', 'outputShowPath', 'outputPath', 
                   'm3u', 'downloadLog', 'keep']
        attributes = {}
        for key in self.__dict__:
            if (key in display) and (key in self.__dict__):
                attributes[key] = self.__dict__[key]
        
        return(attributes)
                
        
    
    def _slugify(self, value):
        """
        Normalizes string, converts to lowercase, removes non-alpha characters,
        and converts spaces to hyphens.

        From Django's "django/template/defaultfilters.py".
        Args:
            value (str): string to be normalized for use with a filename
        
        Returns:
            unicode: sluggified string
        """
        _slugify_strip_re = re.compile(r'[^\w\s-]')
        _slugify_hyphenate_re = re.compile(r'[-\s]+')

        import unicodedata
        if not isinstance(value, unicode):
            value = unicode(value)
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
        value = unicode(_slugify_strip_re.sub('', value).strip())
        return _slugify_hyphenate_re.sub('-', value)

    def _slash(self, value):
        '''
        Ensures path has a trailing slash
        
        Args:
            value (str): string to check and modify
        
        Returns:
            value (str): string with trailing slash
            
        '''
        if not re.match('.*\/$', value):
            logging.debug('adding trailing slash to path: %s', value)
            return(value + '/')
        else:
            return(value)
    
    def setOutputPath(self, outputShowPath = None, outputEpisodePath = None):
        '''
        Method to update the output paths
        Args:
            outputShowPath (str): path within the outputBasePath
            outputEpisodePath (str): path within outputShowPath
        Returns:
            outputEpisodePath (str)
        '''
        if outputShowPath:
            self.outputShowPath = self._slash(self.outputBasePath) + self._slash(outputShowPath)
        
        if outputEpisodePath:
            self.outputPath = self._slash(self.outputShowPath) + self._slash(outputEpisodePath)
        else:
            self.outputPath = self.outputShowPath
            
        return(self.outputPath)
    
    def setM3U(self, name = 'playlist'):
        '''
        Update the m3u file name
        Args:
            name (str): filename for the m3u
        '''
        self.m3u = self._slugify(name) + '.m3u'
        return(True)
    
    def writeM3U(self, filename = False):
        '''
        Write M3U playlist for the episode in the root of the output directory
        Args:
            filename (str): path to output filename
        Returns:
            bool: True
        '''
        
        logging.info('opening m3u playlist: %s for writing', self.m3u)
        if filename:
            self.setm3u(filename)
        
        try:
            #m3ufile = open(self.outputBasePath + self.m3u, 'w')
            m3ufile = open(self._slash(self.outputPath) + self.m3u, 'w')
        except Exception as e:
            logging.error('could not open m3u file: %s\n%s', self.m3u, e)
            return(False)
        logging.debug('writing segments to: %s', self.m3u)
        # recurse all the segments 
        for segment in self.segments:
            # if it was successfully downloaded write it to the m3u file
            if segment.downloaded:
                logging.debug('writing segment to m3u file: %s', segment.filename)
                try:
                    #m3ufile.write(self.outputPath + segment.filename + '\n')
                    m3ufile.write(segment.filename + '\n')
                except Exception as e:
                    logging.error('could not write to: %s\n%s', self.m3u, e)
                    logging.error('halting m3u writing')
                    return(False)
        # cleanup
        try:
            m3ufile.close()
        except Exception as e:
            logging.error('could not close m3u file: %s\n%s', self.m3u, e)
            return(False)
        
        return(True)
    
    
    def download(self, dryrun = False, timeout = 5, useragent = ''):
        '''
        Download all segments in self.segment into self.outputPath
        Args:
            dryrun (bool): When true do all other steps, but do not download and return: False
            timeout (real): time in seconds to wait for a download to complete before timing out
        
        Returns: 
            bool: True for successful download of one or more segments
        '''
        
        success = False
        lockfile = self.outputPath + '.' + programName + '.lock'
        logging.info('downloading program: %s', self.name)
        
        # check for output path
        logging.debug('checking for output directory: %s', self.outputPath)
        if not os.path.isdir(self.outputPath):
            logging.debug('output directory (%s) not found', self.outputPath)
            logging.debug('attempiting to create output directory')
            try:
                os.makedirs(self.outputPath)
            except Exception as e:
                logging.error('could not create outputpath for this episdoe at: %s\n%s', self.outputPath, e)
                logging.error('download failed')
                return(False)
            
            # make a 'lock file' in the folder to help with cleanup later  
            logging.debug('writing lockfile: %s', lockfile)
            try:
                with open(lockfile, 'a'):
                    os.utime(lockfile, None)
            except Exception as e:
                logging.error('could not create lockfile: %s', lockfile)
                logging.error('file error: %s', e)
        
        # check for existing m3u files; stop downloading if it exists
        if len(glob.glob(self.outputPath + '/*.m3u')) > 0:
            logging.info('episode previously downloaded; skipping')
            return(False)
        
        logging.debug('dryrun = %s', dryrun)
        if dryrun:
            logging.info('downloads will be simulated')
        # begin downloading
        for segment in self.segments:
            # update the path for the current segment
            filePath = self.outputPath + segment.filename
            logging.debug('downloading %s', segment.audioURL)
            logging.debug('using URL: %s', segment.audioURL)
            logging.debug('using User-Agent: %s', useragent)
            if not dryrun:
                try:
#                     audioFile = urlopen(segment.audioURL, timeout = timeout, 
#                           data = {'User-Agent' : useragent}).read()
# #                     audioFile = urlopen(segment.audioURL, timeout = timeout).read()
                    request = urllib2.Request(segment.audioURL, headers = {'User-Agent' : useragent})
                    audioFile = urllib2.urlopen(request, timeout = timeout).read()
                except urllib2.URLError as e:
                    logging.warning('could not download segment number: %s', segment.number)
                    logging.warning('error: %s; timeout: %s', e, timeout)
                    continue
                # if one segment was downloaded report a successful download
                success=True
            
            logging.info('writing file to %s', filePath)
            
            if not dryrun:
                try:
                    with open(filePath, 'wb') as code:
                        code.write(audioFile)
                        # record if the writing was successful
                        segment.downloaded = True
                except Exception as e:
                    logging.warning('could not write segment number %s to %s\nerrors follow', segment.number, filePath)
                    logging.warning(e)
                    success = False
                    continue
            else:
                # record succsessful downloading of all segments when doing a dry run
                segment.downloaded = True
                # Dry runs return "false"
                success = False
            
        
        # This is a holdover from a previous version; it is not really needed
        #self.logDownload()
            
        return(success)       
            
    def logDownload(self):
        '''
        Holdover from a previous version as a method for tracking files that were downloaded; no longer needed
        Log successfully downloaded episodes
        Args:
        Returns: 
            bool: True
        '''
        logFile = self.outputBasePath + self.downloadLog
        
        logging.debug('opening log file: %s', logFile)
        try:
            f = open(logFile, 'a')
        except Exception as e:
            logging.error('could not open log file: %s\n%s', logFile, e)
            return(False)
        
        try: 
            f.write(self.outputPath + '\n')
        except Exception as e:
            logging.error('could not write to log file: %s\n%s', logFile, e)
            return(False)
        
        try:
            f.close()
        except Exception as e:
            logging.error('could not close log file: %s\n%s', logFile, e)
            return(False)
        
        return(True)
            
    
    def addSegment(self, segment):
        '''
        Add a downloadable segment to the segment list
        Args:
            segment (Segment): Segment() object containing information
        Returns:
            bool: True
        '''
        self.segments.append(segment)
        return(True)
        
            
    def tagSegments(self):
        '''
        Tag all downloaded segments
        Args:

        Returns:
            bool: True
        '''
        logging.info('tagging segments')
        
        for segment in self.segments:
            if segment.downloaded:
                logging.debug('title: %s,\n tracknumber: %s,\n album: %s,\n artist: %s', segment.title, segment.number, 
                              segment.programName, segment.artist)

                filename = self.outputPath + segment.filename
                try:
                    # find the file extension and guess at the type based on the extension
                    filetype = re.search('\.(\w+$)', filename).group(1)
                except:
                    filetype = None

                if filetype.lower() in taggers: # check to see if this is a known filetype
                    logging.debug('tagging %s', filename)
                    myTagger = taggers[filetype] # create a tagger object with the appropriate mutagen module
                    audio = myTagger(filename) 

                    # write the appropriate tags
                    audio['title'] = segment.title
                    audio['tracknumber'] = str(segment.number)
                    audio['album'] = segment.programName + '-' + self.showDate
                    audio['artist'] = segment.artist

                    try:
                        audio.save()
                    except Exception as e:
                        logging.error('could not write tags for: %s\n%s', filename, e)        
                else:
                    logging.info('could not tag, unknown filetype: %s', filename)
            else:
                logging.warn('segment %s not downloaded; skipping tagging', segment.title)
                
    def cleanUp(self, dryrun = False, lockfile = '*.lock', keep = None):
        '''
        Remove stale episodes, keeping at maximum self.keep episodes

        Args:
            dryrun (bool): when true, do not actually delete anything
            lockfile (str): lockfile pattern glob to use when searching for lockfiles; default:*.lock
            keep (int): maximum number of episodes to keep
        Returns:
            removed (list): removed paths
        '''
      
        if keep:
            self.keep = keep
        if self.keep <= 0:
            self.keep = 1
            
        logging.info('cleaning up stale shows for %s', self.name)
        if not isinstance(self.keep, int):
            logging.error('%s is not an integer: keep')
        logging.info('keeping a maximum of %s shows', self.keep)
        # candididate directories that contain lockfiles for deletion
        matchdir = {}
        logging.debug('searching path: %s', self.outputShowPath)
        for root, dirnames, filenames in os.walk(self.outputShowPath):
            logging.debug('%s', root)
            for filename in fnmatch.filter(filenames, lockfile):
                logging.debug('      %s', filename)
                matchdir[root] = filename
        
        logging.debug('previously downloaded episodes found: %s', len(matchdir))
        # files to delete
        delete = []
        
        # files successfully deleted:
        removed = []
        for directory in range(0, len(sorted(matchdir))-self.keep):
            logging.debug('flagged for deletion: %s', sorted(matchdir)[directory])
            delete.append(sorted(matchdir)[directory])
        
        for key, val in enumerate(delete):
            lockfile = os.path.join(delete[key], matchdir[delete[key]])
            logging.debug('attempting to clean episode files in: %s', delete[key])
            # double check that a *.lock file exists before attempting a delete
            if os.path.isfile(lockfile):
                logging.debug('found lock file in path: %s', delete[key])

                if dryrun:
                    logging.info('dryrun: simulating deletion (nothing will be removed)')
                else:
                    logging.debug('deleting path: %s\n', delete[key])
                    try:
                        shutil.rmtree(delete[key])
                        # record those paths removed
                        removed.append(delete[key])
                    except OSError as e:
                        logging.error('could not delete path: %s', e)
                    
                
            else:
                logging.warn('discovered missing lock file when attempting cleanup: %s', lockfile)
                logging.warn('manual deletion required: %s', delete[key])
                logging.warn('skipping path: %s\n', delete[key])

        return(removed)   


# In[15]:

class NPREpisode(Episode, object):
    '''NPR program episode object
        Args:
            name (str): name of episode/podcast
            programURL (str): Index URL containing list of files to download
            showDate (str): date of episode
            outputBasePath (str): base path to use for output of files (default is ./)
            m3u (str): m3u playlist filename
            downloadLog (str): download log filename
            jsonData 
    '''
    
    
    def __init__(self, name = 'unknown', programURL = None, outputBasePath = './', m3u ='playlist.m3u', 
                 downloadLog = 'download.log', keep = 3):
        super(NPREpisode, self).__init__(name = name, programURL = programURL, outputBasePath = outputBasePath, 
                                         m3u = m3u, downloadLog = downloadLog, keep = keep)
        self.jsonData = None

    def recentEpisodes(self):
        '''Identify the most recent episodes
        Not yet implemented
        '''
        pass
        
        
    def getepisode_API():
        '''
        Use the NPR API to get a list of episodes
        Not yet implemented
        '''
        pass
    
    def getepisode_HTML(self):
        '''
        Scrape the HTML for JSON containing the date segment and title information
        Attributes set here:
            self.jsonData (json obj) - JSON listing of episodes from NPR
            self.showDate (str) - YYYY-MM-DD formatted string
            self.name (str) - human readable show name 
            self.segments (:obj: Segment) - episode segments are populated and added

        Returns: 
            bool: True if episode information is scraped from the HTML, False otherwise
        '''
        
        logging.debug('fetching episode info via HTML method')
        logging.debug('source: %s' % self.programURL)
        
        # search terms hardcoded here
        search_PlayAll = "<b.*data-play-all='({.*})'><\/b>" #re search string for JSON data in program HTML
        search_FileName = "(^[\s|\w|\.|'|-]*)\[?|$]" #(anySpaces OR anyWords OR anyPeriod OR any' OR any-)? OR EOL
        search_showDate = "datetime=\"(\d{4}-\d{2}-\d{2})" #re search for show date
               
        
        # variables defined here
        filename = '' # extracted filename for each segment
        defaultArtist = 'National Public Radio' # default artist for NPR Episodes
        
        # add an extension to help differentiate between episodes; set to epoch seconds to prevent clobbering
        # if no valid extension is set elsewhere
        output_extension = int((datetime.now() - datetime.utcfromtimestamp(0)).total_seconds())
        
       
        try: # fetch the full show HTML
            programHTML = urllib2.urlopen(self.programURL).read()
        except Exception as e:
            logging.warning('could not fetch episode information from %s' % self.programURL)
            logging.error(e)
            return(False)
        logging.debug('HTML retrieved successfully')
        
        # find the show date and record it 
        self.showDate = re.search(search_showDate, programHTML).group(1)
        
        if len(self.showDate) < 1:
            logging.warning('no valid showDate found')
        else: logging.debug('show date: %s', self.showDate)
        
        try: # find the JSON program data
            self.jsonData = json.loads(re.search(search_PlayAll, programHTML).group(1))
        except Exception as e:
            logging.error('no valid JSON episode listing found in HTML from %s', self.programURL)
            logging.error(e)
            return(False)
        
        # check that some JSON data was found - not terribly robust
        if len(self.jsonData['audioData']) > 1:
            logging.debug('JSON program information found for %s', self.jsonData['audioData'][0]['program'].upper())
            logging.debug('setting name to: %s', self.name)
            self.name = self.jsonData['audioData'][0]['program'].upper() # set the episode name
            logging.debug('segments found: %s', len(self.jsonData['audioData']))
        else:
            logging.warn('no valid audioData found in JSON object for program (%s)', self.name)
            return(False)
        
        # grab the first character of each word in the program name; grab the last two characters of the last word
        if len(self.name) > 0:
            short_name = '_'
            output_extension = '_'
            for each, val in enumerate(self.name.split(' ')):
                if each + 1 >= len(self.name.split(' ')):
                    char = 2
                else: 
                    char = 1
                output_extension = output_extension + val[:char]
                short_name = short_name + val[:char]

        # create a sub directory within the output path
        self.setOutputPath(outputEpisodePath = self.showDate + short_name) 
        logging.debug('output path set to: %s', self.outputPath)
        
        #set m3u name
        self.setM3U(self.showDate + '-' + self.name)
        logging.debug('m3u filename set to: %s', self.m3u)
        
        # recurse the JSON object and find all the audioData information
        for key, val in enumerate(self.jsonData['audioData']):
            artist = '' # set the artist to an empty string for each loop
            
            logging.debug('%s - %s', int(key)+1, val['title'] )
            try:
                audioURL = val['audioUrl'] 
                title = val['title']
            except Exception as e:
                    logging.warning('failed to find URL or title data: %s', e)
                    
            # search for artist data
            try:
                artist = val['artist']
            except Exception as e:
                logging.warning('failed to find artist data: %s', e)
            
            if len(artist)<1:
                logging.info('no artist data provided in JSON; using default: %s', defaultArtist)
                artist = defaultArtist
                    
            number = int(key)+1 # set the human readable segment number
            filename = re.search(search_FileName, val['audioUrl'].split('/')[-1:][0]).group(1) # set the filename
            
            # append the segment number
            filename = str(number).zfill(3) + '_' + filename
            
            if filename < 1:
                logging.warning('no filename found; dropping segment')
                continue

            self.addSegment(Segment(audioURL = audioURL, filename = filename, 
                                    number = number, programName = self.name,
                                    title = title, artist = artist))
            
        return(True)
            


# In[16]:

class Segment():
    '''One segment of a podcast'''
    
    def __init__(self, audioURL = None, filename = None, number = 0, programName = None, artist = None, title = None):
        '''
        Args:
            audioURL (str): URL to specific downloadable content
            number (int): ordinal number of segment
            filename (str): output filename
            programName (str): program Name
            artist(str): artist
            title (str): human readable segment title
            downloaded (bool): true if segment was successfully downloaded
            
        '''
        self.audioURL = audioURL
        self.number = number
        self.filename = filename
        self.title = title
        self.programName = programName
        self.artist = artist
        self.downloaded = False 


# In[17]:

class showConfig():
    '''Configuration object for a downloadable show'''
   
    def __init__(self, optionsDict = {}):
        '''
        Args:
            optionsDict (dict): dictionary of options to be used in configuration
                showname (str): human readable string
                fetchmethod (str): method for downloading show (NPR_HTML or NRP_API)
                programs (int): number of programs to keep
                updatedays (list): integers [0-6] representing days of the week to update (sun-sat)
                updatetime (str): time in 24H HH:MM format after which an update should be attempted
                timezone (str): timezone in which to preform time calculatinos
                url (str): url to NPR program page
        Attributes:
            options (dict): dictionary of options
            showName (str): human readable name of show
            fetchMethod (str): method for downloading show (NPR_HTML or NPR_API)
            programs (int): number of programs to keep
            updateDays (list): integers [0-6] representing days of the week to update (sun-sat)
            updateTime (str): time in HH:MM after which an update should be attempted
            timezone (str): timezone in which to preform time calculations
            url (str): url to NPR program page
    
        '''
        
        self.options = optionsDict
        self.showName = 'No Name'
        self.fetchMethod = 'NPR_HTML'
        self.programs = 1
        self.updateDays = []
        self.updateTime = ''
        self.timezone = 'EST'
        self.url = None
        
    def verifyConfig(self):
        '''
        
        Validates and sets configuration paramaters for a downloadable show:
        
        Attributes:
            showName (str): human readable name of show
            fetchMethod (str): method for downloading show (NPR_HTML or NPR_API)
            programs (int): number of programs to keep
            updateDays (list): integers [0-6] representing days of the week to update (sun-sat)
            updateTime (str): time in HH:MM after which an update should be attempted
            timezone (str): timezone in which to preform time calculations
            
        Args:
            None
        
        Returns: 
            bool: True - configuration is OK or has been made OK
            
        '''
        
        logging.debug('verifying configuration')
        
        if 'showname' in self.options:
            self.showName = self.options['showname']
            logging.debug('show name set to: %s', self.showName)
        else: 
            logging.warn('no show name found; set to: %s', self.showName)
        
        if 'programs' in self.options:
            try:
                self.programs = int(self.options['programs'])
            except ValueError as e:
                logging.error('programs option not an integer: %s', e)
                logging.error('programs set to: %s', self.programs)
        else:
            logging.warning('no programs setting found in configuration file for %s; set to: %s', self.showName, self.programs)
        
        
        if 'url' in self.options:
            if re.match('^http:\/\/.*', self.options['url'].lower()):
                self.url = self.options['url']
            else:
                logging.error('no vlaid URL found for %s: %s', self.showName, self.options['url'])
                return(False)
        else:
            logging.error('no valid URL found for %s', self.showName)
            logging.error('valid url format: http://host.com/show/')
            return(False)
        
        
        if 'fetchmethod' in self.options:
            self.fetchMethod = self.options['fetchmethod']
            logging.debug('fetchmethod set to: %s', self.fetchMethod)
        else:
            logging.warning('no fetchmethod set; setting to: %s', self.fetchMethod)
        
        # This all may be undeeded; consider removing all of this.
        # user cmd+/ to uncomment the block below        
#         defaultUpdateDays = [1, 2, 3, 4, 5, 6, 7]
#         if 'updatedays' in self.options:
#             # remove any non-numerals, -, or commas
#             self.options['updatedays'] = re.sub('[^\,0-9]+', '', self.options['updatedays'])
#             # clear out any superflous commas
#             self.options['updatedays'] = re.sub('\,\,', ',', self.options['updatedays']) 
            
#             try:
#                 self.updateDays = map(int, self.options['updatedays'].split(','))
#             except ValueError as e:
#                 logging.warn('bad or missing update date format: %s',e )
#                 logging.warn('using sun through sat')
#                 self.updateDays = defaultUpdateDays
 
#             badValues = []
#             for index in self.updateDays:
#                 # check for bad values that are less than 1 or greater than 7
#                 if index > 7 or index < 1:
#                     logging.warn('found invalid day in configuration file: %s',index)
#                     badValues.append(index)   
                    
#             # get rid of bad values
#             for index in badValues:
#                 logging.warn('removing invalid day: %s', index)
#                 self.updateDays.remove(index)
#             # sort the list 
#             self.updateDays.sort()
#         else:
#             # supply a list if none is supplied
#             logging.warn('no update days were supplied using sun through sat')
#             self.updateDays = defaultUpdateDays
        
        
#         # do some validation of valid timezones
#         if 'timezone' in self.options:
#             if self.options['timezone'].upper() in pytz.all_timezones:
#                 self.timezone = self.options['timezone'].upper()
#             else: 
#                 logging.error('specified timezone not found in database: %s', self.options['timezone'])
#                 logging.error('setting timezone to: UTC')
#                 self.timezone = 'UTC'
                
#         else:
#             logging.warning('no timezone found; setting timezone to: %s', self.timezone)

    
        
        # do some validation of valid times
        # time format
        timeFMT = '%H:%M'
        defaultTime = '23:59'
        if 'updatetime' in self.options:
            # sanitize the time string datetime.time(datetime.strptime('13:55', timeFMT))
            try:
                self.updateTime = datetime.time(datetime.strptime(re.sub('[^0-9\:]+', '', self.options['updatetime']), timeFMT))
            except ValueError as e:
                logging.error('bad updatetime time format: %s', self.options['updatetime'])
                logging.error('setting updatetime to: %s', defaultTime)
                self.updateTime = datetime.time(datetime.strptime(defaultTime, timeFMT))    
        else:
            self.updateTime = datetime.time(datetime.strptime(defaultTime, timeFMT))
            
        
        return(True)
                    


# In[19]:

def main(argv=None):
    ############### init variables 
    
    ##### LOGGING INIT
    # init the log; this removes any old log handlers (this is particularly useful when testing in an IDE)
    log = logging.getLogger()
    if len(log.handlers) > 0:
        for each in range(0, len(log.handlers)):
            log.removeHandler(log.handlers[0])
            
    # set the log format:
    # [  DEBUG 2017-02-12 19:14] loading module: requests
    logFormatter = logging.Formatter('[%(levelname)8s %(asctime)s] %(message)s', '%Y-%m-%d %H:%M')
    consoleFormatter = logging.Formatter('[%(levelname)-8s] %(message)s')
    # set root logger
    rootLogger = logging.getLogger()       
    
    # add a conshole handle to the root logger
    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler) 
    
    ############### CONFIGURATION VARIABLES
    # default configuration file
    homeDir = os.path.expanduser('~')
    cfgFile = homeDir + '/.podcastdownload.ini' 
    
    # set the configuration parser
    configParser = ConfigParser.SafeConfigParser()

    # required options in 'Main' section in 
    # dict {'option name' : [configParser.getfloat; get; getboolean, 'default value]}   
    mainSection = 'Main'    
    # list any special reserved section names here
    reservedSectionNames = [mainSection]
    # required items in the main section
    required = {'outputpath' : [configParser.get, homeDir + '/DownloadedShows']}
    
    # optional items in the configuration file
    optional = {'dryrun' : [configParser.getboolean, False],
                'timeout' : [configParser.getfloat, 5], 
                'loglevel': [configParser.get, 'ERROR'],
                'logfile' : [configParser.getboolean, False],
                'useragent': [configParser.get, '']}
    
    
    # sample show for creating a configuration file
    sampleShow = {'showname' : 'SAMPLE SHOW: All Things Considered',
              'url' : 'http://www.npr.org/programs/all-things-considered/',
              'fetchmethod' : 'NPR_HTML',
              'programs' : 2}
    
    ############### SHOW/DOWNLOAD VARIABLES
    # list of show configurations found in configuration file
    shows = []
    
    # list of program episodes to download
    downloadEpisodes = []
    
    # random generator object
    randomGenerator = SystemRandom()
    

    ############### READ AND ACT ON COMMAND LINE ARGUMENTS  
    # disable -h for help so the second parser can deal with this
    # http://stackoverflow.com/questions/3609852/which-is-the-best-way-to-allow-configuration-options-be-overridden-at-the-comman
    cmdlineParser = argparse.ArgumentParser(description = __doc__, 
                                           formatter_class = argparse.RawDescriptionHelpFormatter,
                                          add_help = False)
    # handle the jupyter -f option while developing in jupyter ipython notebook
    #cmdlineParser.add_argument('-f', '--fconfig', help='fake config file', action='store')
    # set the configuration file
    cmdlineParser.add_argument('-c', '--configfile', help='configuration file', metavar='FILE',
                              action='store', default = cfgFile)
    cmdlineParser.add_argument('-C', '--createconfig', help='create configuration file (can be used with -c)', 
                              action='store_true', default=False)
    # determine if this is a dry run or not
    cmdlineParser.add_argument('-d', '--dryrun', help='preform a dry-run with no downloads',
                              action='store_true', default=False)
    cmdlineParser.add_argument('-L', '--logfile', help = 'enable logging to file', 
                               action = 'store_true', default = False)
    cmdlineParser.add_argument('-o', '--outputpath', action = 'store', metavar = 'PATH', 
                        help = 'path to output downloaded files')
    cmdlineParser.add_argument('-t', '--timeout', action = 'store')
    cmdlineParser.add_argument('-v', '--verbose', action = 'count', 
                        help = 'verbose mode; add more -v to increase verbosity')
    cmdlineParser.add_argument('-V', '--version', action = 'store_true', default = False, help = 'print version and quit')

  
    # reamining arguments stored in unknownArgs
    args, unknownArgs = cmdlineParser.parse_known_args()
    
    if args.version:
        print version
        sys.exit()
        
    # set the logging level based on command line options
    if args.verbose:
        # remove 10 for each V bringing the level from 40 (ERROR) down
        logLevel = logging.ERROR - args.verbose * 10
        # if the log level shold somehow end up above 50 or below 10 it is set to 10 (DEBUG)
        if (50 < logLevel) or (logLevel < 10):
            logLevel = logging.DEBUG
        rootLogger.setLevel(logLevel)
    else:
        # the default level is ERROR 
        rootLogger.setLevel(logging.ERROR)    
    
    # create the configuration file and exit 
    if args.createconfig:
        logging.info('%s writing sample configuration file: %s', div(10, '-'), args.configfile)
        configParser.add_section(mainSection)
        logging.debug('adding section: %s', mainSection)
        logging.debug('adding required options: ')
        for value in required:
            logging.debug('     %s = %s', value, required[value][1])
            configParser.set(mainSection, str(value), str(required[value][1]))

        logging.debug('adding optional options:')
        for value in optional:
            logging.debug('     %s = %s', value, optional[value][1])            
            configParser.set(mainSection, str(value), str(optional[value][1]))

        configParser.add_section(sampleShow['showname'])
        logging.debug('adding sample show: %s', sampleShow['showname'])
        logging.debug('with options: ')
        for value in sampleShow:
            logging.debug('     %s = %s', value, sampleShow[value])
            configParser.set(sampleShow['showname'], str(value), str(sampleShow[value]))
        if os.path.isfile(args.configfile):
            print 'cowardly refusing to overwrite existing configuration file:', args.configfile
            print 'remove or rename existing config file before attempting to create a new one'
        else:
            try:
                with open(args.configfile, 'wb') as configoutput:
                    configParser.write(configoutput)
            except (IOError, OSError) as e:
                print 'error writing to configuration file', e
    
    ############### READ AND ACT ON CONFIGURATION FILE
    configParser.read(args.configfile)
    
    if mainSection not in configParser.sections():
        logging.error('No "%s" section in configuration file: %s', mainSection, args.configfile)
        logging.error('exiting')
        sys.exit()
    
    # look for each required option and set to default specified above if not found
    # container for all default settings read from config file
    default = {}
        
    for key in required:
        try:
            #default[key] = configParser.get(mainSection, key)
            default[key] = required[key][0](mainSection, key)
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError) as e:
            logging.error('problem in configuraiton file: %s', e)
            logging.error('using default value: %s = %s', key, required[key][1])
            default[key] = required[key][1]     
    
    
    for key in optional:
        try:
            default[key] = optional[key][0](mainSection, key)
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError) as e:
            logging.info('"%s" optional setting not found in configuration file "%s" section', key, 'Default')
            logging.info('this is OK!')
            logging.info('using default value: %s', optional[key][1])
            default[key] = optional[key][1]     
            
    
    ############### MERGE COMMANDLINE AND CONFIGURATION FILES TOGETHER
    # add in commandline arguments
    parser = argparse.ArgumentParser(parents=[cmdlineParser])
    # add in configuration file defaults
    parser.set_defaults(**default)
    
    # add all the known arguments to the parserArgs namespace, discard any unknown arguments
    parserArgs, uknownArgs = parser.parse_known_args()
 
    # add a file handler for the file log if needed
    if parserArgs.logfile:
        # Add the a file handle to the root logger
        fileHandler = logging.FileHandler(programName+'.log')
        fileHandler.setFormatter(logFormatter)
        rootLogger.addHandler(fileHandler)

    # match the loging level set in the config file or on the command line
    # commandline -v options override
    if parserArgs.loglevel and not args.verbose:
        if isinstance(logging.getLevelName(parserArgs.loglevel.upper()), int):
            rootLogger.setLevel(parserArgs.loglevel.upper())

    # verify configuration options before proceeding
    # deal with unknwon options
    if len(unknownArgs) > 0:
        logging.warn('ignoring unknown command line options:')
        for arg in unknownArgs:
            logging.warn('     %s', arg)
        
    # check for unreasonable timeouts
    if parserArgs.timeout > 120:
        logging.warn('timeout values under 120s are reccomended: %s', parserArgs.timeout)    
    
    # add a trailing '/' to the output path
    if not re.match('.*\/$', parserArgs.outputpath):
        parserArgs.outputpath = str(parserArgs.outputpath) + str('/')   
    
    # expand out any path variables
    parserArgs.outputpath = os.path.expanduser(parserArgs.outputpath)
                                 
    ############### LOAD NON STANDARD MODULES
    loadModules()
        
    ############### READ SHOWS FROM CONFIGURATION FILE
    logging.info('%s searching config file for shows', div(10, '-'))
        
    for section in configParser.sections():
        if section not in reservedSectionNames and '#' not in section:
            logging.info('%s found show: %s', div(5), section)
            show = (showConfig((dict(configParser.items(section)))))
            if show.verifyConfig():
                shows.append(show)
            else:
                logging.error('bad configuration for show "%s", skipping', section)
    if len(shows) <= 0:
        logging.critical('no shows found in configuration file') 
        logging.critical('nothing to do')
        sys.exit()
    
    #pdb.set_trace()
    
    ############### PARSE CONIFIGURATION FOR EACH SHOW
    logging.info('%s parsing show information', div(10, '-'))
    for show in shows:
        # create an NPREpisode object and populate
        logging.debug('%s parsing configuration for show: [%s]', div(5), show.showName)
        myEpisode = NPREpisode(name = show.showName, outputBasePath = parserArgs.outputpath, keep = show.programs)
        #myEpisode.outputBasePath = parserArgs.outputpath
        myEpisode.programURL = show.url
        if myEpisode.getepisode_HTML():
            downloadEpisodes.append(myEpisode)
        else:
            logging.warning('error fetching show JSON information; see errors above')
    
    ############### DOWNLOAD EACH SHOW
    logging.info('%s downloading episodes', div(10, '-'))
    logging.debug('found %s episodes', len(downloadEpisodes))

    for episode in downloadEpisodes:
                
        logging.info('%s downloading: %s', div(5), episode.name)
        if episode.download(dryrun = parserArgs.dryrun, timeout = parserArgs.timeout,
                        useragent = randomGenerator.choice(parserArgs.useragent.split('|'))):
            
            if not parserArgs.dryrun:
                logging.debug('attempting to write M3U file')
                episode.writeM3U()
                episode.tagSegments()
            logging.info('success!')
            logging.info('%s cleaning up old episodes fpr %s', div(5), episode.name)
            #logging.debug('keeping a maximum of %s episodes', episode.keep)
            removed = episode.cleanUp()
            logging.debug('removed: %s', removed)

    print 'done'
    
    return(shows)

if __name__ == '__main__':
    main()

