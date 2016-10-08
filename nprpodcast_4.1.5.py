#!/usr/bin/env python
#Copyright 2014 Aaron Ciuffo

changelog='''
TO DO:
  * if ConfigParser module is missing no proper error is delivered - FIx THIS!
  * talk to Martin re: finding a less brittle method for sorting the programDict
    - if the index map has fewer elements than then dict, I'm done for
  * add cleanup routine - purge old episodes
  * add local TZ awareness - Work out proper shows based on time on Eastern Time
    - http://stackoverflow.com/questions/1398674/python-display-the-time-in-a-different-time-zone

DONE:
  X write a method for generating the config file on the first run V4.1
  X write lock file after downloading IS SUCCESSFUL
  X add dry run options that work
  X write playlist
  X figure out how to make a good data structure for passing segments to the m3u writer

Changes:

4.1.5 - 22 July 2016 
  * switched to mutagen.mp4.MP4 from .EasyMP4 
4.1.4 - 15 September 
  * Fixed some typos
4.1.3 - 15 September
  * Fixed boolean bug introduced by adding dryrun to configuration file
    - options['dryrun'] must be explicitly treated as a boolean throughout 
    - fixed by using getboolean method of ConfigParser

4.1.1 - 13 September 2015
  * Fixing dry run option
  * Changed naming to make playlists sort better on devices 
  * added system for creating a config file if it is not found

4.1 - 1 Jan 2015
  * NPR is blocking the combination of ip/OS (linux) from downloading.
    * need to finish writing and testing this version then replace V3

4.0 - 7 December
  * Rewrite to use NPR API / JSON queries

3.2 - 6 December
  * it appears that NPR is wise to robot downloaders; attempting to add
    a useragent field to deal with this.

  * still thinking about timezone awareness - timezones are hard.

3.1 - 21 October
  * Attempting to add timezone awareness to make timezones less insane


** code snips to add
import pytz
import datetime
oslo=pytz.timezone('Europe/Oslo')
eastern=pytz.timezone('US/Eastern')
datetime.datetime.utcnow().replace(tzinfo=oslo).astimezone(eastern)


3.0 - 7 August
  * Total rewrite - it was a mess of poorly trapped subroutines and bad logic
  * Cleaned up some bad logic and trapped things a bit more soundly
  * still struggling with removing directories with unexpected files (.AppleDouble)
'''


version='''NPR Podcast Downloader V4.1

by Aaron Ciuffo (txoof.com)
released without warranty under GPLV3:
http://www.gnu.org/licenses/gpl-3.0.html
Please don't sue me.
'''

#[Imports]#
import os # interacting with OS
import argparse # loading configuration
import ConfigParser # loadign configuration
import datetime
import shutil # deleting directories
import string
import re # regular expressions - finding and removing old directories
from math import log10
from random import randint # used to make downloads more "human"
from time import sleep
from urllib2 import urlopen
from json import load, dumps

# a magical spell written by Martin Muggli
class NPR_part:
  def __init__(self, filename, date, partnum):
    self.filename, self.date, self.partnum = filename, date, partnum
  def __str__(self): return "Date: " + str(self.date) + " part: " + str(self.partnum) + " Filename: " +self.filename #define a way for the class to represent itself as a string
  def __repr__(self): return self.__str__() # reuse the __str__ method


def load_modules(options):
  try:
    global requests
    import requests
  except Exception, e:
    print 'Failed to load module: requests -', e
    print 'Please install requests module: http://docs.python-requests.org/'
    print 'exiting'
    exit(2)

  #try to load the id3 tagging module by default
  if not options['notag']:
    try:
      #global EasyMP4 
      global MP4
      from mutagen.mp4 import MP4
      #from mutagen.easymp4 import EasyMP4
    except Exception, e:
      print 'Error: failed to load tagger:', e
      print 'Please install the mutagen module or specify --notag'
      print 'Mutagen python module: http://code.google.com/p/mutagen/'
      print 'Disabling tagging'
      #set the notag option to true
      options['notag']=True
  ## end load_modules
  return(options)

# createa  yyyy-mm-dd string for naming
def ymd(timedata):
  timestr=str(timedata.year)+'-'+str(timedata.month)+'-'+str(timedata.day)
  return(timestr)

# compare two items
def npr_part_cmp(arg, arg2):
  if arg.date == arg2.date: return arg.partnum - arg2.partnum # if dates are the same, order based on parts
  timedelta = (arg.date - arg2.date) # when subtracting to datetime objects the objects know how to create an object of timedelta
  return timedelta.days # use the days field of that timedelta 

def format_filename(s):
  maxlen=110
  valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
  filename = ''.join(c for c in s if c in valid_chars)
  filename = filename.replace(' ','_') # I don't like spaces in filenames.
  if len(filename)>=maxlen:
    filename=filename[0:maxlen]
  return(filename)
  

def parse_args():
  #command line options over ride configuration file
  scriptName="nprpodcast"
  defaultConfigPath=os.path.expanduser('~/.'+scriptName)
  defaultConfig=defaultConfigPath+'/config.ini'

  #defaultconf=os.path.expanduser('~/.'+scriptName+'/config.ini')

  #create parser object
  parser = argparse.ArgumentParser(description='Fetch all segments for the most recent NPR news program')

  #set the configuraiton file
  helpstr='default configuration file: ' + defaultConfig
  parser.add_argument('-c', '--config', action='store', type=str, metavar='<path>', help=helpstr, default=defaultConfig)

  # user agent string
  parser.add_argument('-a', '--useragent', action='store', type=str, metavar='<user agent>', help='User agent string to use')

  #API Key
  parser.add_argument('--apikey', action='store', type=str, metavar='<API Key>', help='NPR API key to use (required)')

  parser.add_argument('--cleanup', action='store_true', default=False, help='clean up old stale episodes')

  # do a dry run without downloading
  parser.add_argument('-d', '--dryrun', action='store_true', default=False, help='dry run - do not download')

  # maximum episodes to keep
  parser.add_argument('-k', '--keep', action='store', type=int, metavar='<i>', help='keep <i> old episodes')

  # output path for files
  parser.add_argument('-o', '--outpath', action='store', type=str, metavar='<path>', help='output path for downloaded mp3s')

  # quiet - do not report anything
  parser.add_argument('-q', '--quiet', action='store_true', default=False, help='Quiet opperation; only errors are output')

  # do not try to id3 tag
  parser.add_argument('-t', '--notag', action='store_true', default=False, help='turn off id3 tagging of segments')

  #URL to use in queries
  parser.add_argument('-u', '--baseurl', action='store', type=str, metavar='<url>', help='base url to query')

  # turn on verbose output
  parser.add_argument('-v', '--verbose', action='store_true', default=False, help='turn on verbose reporting')

  # version information
  parser.add_argument('-V', '--version', action='store_true', default=False, help='display version and exit')


  args=parser.parse_args()

  ## end parse_args
  return(args)

def read_config(args):
  #Check to see if the config path exists
  splitPath=args.config.split('/')
  configPath='/'
  if len(splitPath[0])==0:
    del(splitPath[0])
  for i in range(len(splitPath)-1):
    configPath=configPath+splitPath[i]+'/'

  #Create config path it if necessary
  if not os.path.isdir(configPath):
    try: 
      os.makedirs(configPath)
    except Exception, e:
      print 'Could not create: ', configPath, e

  # if the config file does not exist, create it 
  if not os.path.isfile(args.config):
    print 'Configuration file not found at: ', args.config
    print 'This script can help create a proper config file with some input from you.'
    response=raw_input('Create a configuration file at the above path? (y/N): ')
    if response=='Y' or response=='y':
      try:
        open(args.config, 'w').write(str(''))
      except Exception, e:
        print 'Could not write config file: ', e
        exit(1)
    else:
      print 'Quiting...'
      exit(0)

  # check with user to help create the configuration file


  config=ConfigParser.RawConfigParser()
  try:
    config.readfp(open(args.config))
  except Exception, e:
    print 'Failed to load configuration file at:', args.config
    print 'Error: ', e
    exit(1)

  #check for sections
  configChanges=False
  requiredSections=['options', 'api', 'episodes']

  for i in requiredSections:
    if not config.has_section(i):
      config.add_section(i)
      configChanges=True

  #API Query section
  if not config.has_option('api', 'apikey'):
    print 'Missing NPR api Key. Get yours at: http://www.npr.org/templates/reg/'
    response=raw_input('apikey: ')
    if response=='':
      print 'Cannot continue without API key.'
      exit(0)
    else:
      config.set('api', 'apikey', response)
      configChanges=True

  if not config.has_option('api', 'baseurl'):
    print 'The default NPR API query URL is: http://api.npr.org/query?'
    print 'To use a different URL please enter it below or press ENTER to use the default.'
    response=raw_input('baseurl: ')
    configChanges=True
    if response=='':
      response='http://api.npr.org/query?'
    config.set('api', 'baseurl', response)
 
  if not config.has_option('api', 'useragent'):
    print 'Enter your prefered browser user agent string Below. Press ENTER to use the default.'
    print 'This is OK to skip if you are unsure.'
    response=raw_input('useragent: ')
    configChanges=True
    if response=='':
      response='Mozilla/5.0'
    config.set('api', 'useragent', response)

  if not config.has_option('episodes', 'maxeps'):
    print 'What is the maximum number of episodes to attempt to download at a time?'
    print 'Default: 2'
    response=raw_input('maxeps: ')
    configChanges=True
    if response=='':
      response=2
    config.set('episodes', 'maxeps', response)

  if not config.has_option('episodes', 'keep'):
    print 'How many old episodes should be kept?'
    print 'Default: 4'
    response=raw_input('keep: ')
    configChanges=True
    if response=='':
      response=4
    config.set('episodes', 'keep', response)

  if not config.has_option('episodes', 'outpath'):
    print 'Where shall the downloaded episodes be kept?'
    print 'Default: ~/nprpodcast/' 
    response=raw_input('outpath: ')
    configChanges=True
    if response=='':
      response='~/nprpodcast'
    config.set('episodes', 'outpath', response)

  additionalOptions=['dryrun', 'notag', 'quiet']
  for i in additionalOptions:
    if not config.has_option('options', i):
      config.set('options', i, 'False')
      configChanges=True

  if configChanges:
    print 'Please see ', args.config, ' for additional options.'
    with open(args.config, 'wb') as configfile:
      config.write(configfile)

  #config=ConfigParser.ConfigParser()
  #config.read(args.config)

  ## end read_config
  return(config)

def merge_options(args, config):
  options={}

  #try to load options from the configuration file; except: set the option to the default

  if not args.useragent:
    try:
      options['useragent']=config.get('api', 'useragent')
    except:
      options['useragent']='Mozilla/5.0'
  else:
    options['useragent']=args.useragent

  if not args.apikey:
    try:
      options['apikey']=config.get('api', 'apikey')
    except:
      print 'Cannot continue without an API key.  Exiting'
      exit(1)
  else:
    options['apikey']=args.apikey

  if not args.dryrun:
    try:
      options['dryrun']=config.getboolean('options', 'dryrun')
    except:
      options['dryrun']=False
  else:
    options['dryrun']=args.dryrun

  if not args.outpath:
    try:
      options['outpath']=str(config.get('episodes', 'outpath'))
    except:
      options['outpath']='./'
  else:
    options['outpath']=args.outpath
    #append a final / for good measure

  options['outpath']=options['outpath']+'/'
  #clean and expand outpath as needed
  options['outpath']=os.path.expanduser(options['outpath'])

  #number of episodes to keep
  if not args.keep:
    try:
      options['keep']=int(config.get('episodes', 'keep'))
    except:
      #default: 4 episodes
      options['keep']=4
  else:
    options['keep']=args.keep

  #do not try to tag
  if not args.notag:
    try:
      options['notag']=config.getboolean('options', 'notag')
    except:
      options['notag']=False
  else:
    options['notag']=True

  #settings that need to be available everywhere
  options['dnloadlog']=options['outpath']+'nprpodcast.log'

  # Turn off all chatter except errors
  if args.quiet:
    try:
      options['quiet']=config.getboolean('options', 'quiet')
    except:
      options['quiet']=False
  else:
    options['quiet']=False

  #turn on verbosity
  if args.verbose:
    options['verbose']=True
    options['quiet']=False
  else:
    options['verbose']=False

  if not args.baseurl:
    try:
      options['baseurl']=str(config.get('api', 'baseurl'))
    except:
      # default
      options['baseurl']='http://api.npr.org/query?'
  else:
    options['baseurl']=args.baseurl

  if not args.useragent:
    try:
      options['useragent']=str(config.get('api', 'useragent'))
    except:
      # default
      options['useragent']='Mozilla/5.0'
  ## end merge_options
  return(options)

def download_list(options):
  # maximum number of episodes to look for
  maxeps=2 
  utcnow=datetime.datetime.utcnow()
  #naive translation to eastern time
  estnow=utcnow-datetime.timedelta(hours=5) 
  # variable for working with the time
  utcnow=datetime.datetime.utcnow()
  #naive translation to eastern time
  estnow=utcnow-datetime.timedelta(hours=5) 
  # variable for working with the time
  backtime=estnow
  # create a dict to hold the episodes that will be processed
  episodes={}

  #count backwards to find the most recent two episodes
  count=0
  while count < maxeps:
    #search ME episodes - available around 8:00 eastern
    if backtime.hour == 8 and backtime.weekday() in range (0,5):
      #add an episode of morning edition
      episodes[count]={'date':backtime, 'program':3}
      count += 1
      backtime=backtime-datetime.timedelta(hours=1)
      continue
    #weekend edition saturday after 13:00
    if backtime.hour == 13 and backtime.weekday()==5:
      #add an episode of weekend saturday
      episodes[count]={'date':backtime, 'program':7}
      count += 1
      backtime=backtime-datetime.timedelta(hours=1)
      continue
    #weekend edition sunday after 13:00
    if backtime.hour == 13 and backtime.weekday()==6:
      #add an episode of wekkend sunday
      episodes[count]={'date':backtime, 'program':10}
      count += 1
      backtime=backtime-datetime.timedelta(hours=1)
      continue
    #ATC after 19:00 eastern
    if backtime.hour == 19:
      #add an episode of ATC
      episodes[count]={'date':backtime, 'program':2}
      count += 1
      backtime=backtime-datetime.timedelta(hours=1)
      continue
    #if no match was made, count backwards 
    backtime=backtime-datetime.timedelta(hours=1)
  
  if options['verbose']:
    print 'Queuing episodes:'
    for i in episodes:
      if episodes[i]['program'] == 3:
        print 'Morning Edition for', episodes[i]['date']
      if episodes[i]['program'] == 2:
        print 'All Things Considered for', episodes[i]['date']
      if episodes[i]['program'] == 7:
        print 'Weekend Edition Saturday for', episodes[i]['date']
      if episodes[i]['program'] == 10:
        print 'Weekend Edition Sunday for', episodes[i]['date']

  #end download_list
  return(episodes)


def download_program(program, date, options):
  success=False
  humanDate=str(date.year)+'-'+str(date.month)+'-'+str(date.day)
  json_obj={}
  # count the number of downloades segments
  segCount=0
  #create a structure for the data segment
  segment={}

  #create a structure for holding all of the segments
  programDict={}

  #set the useragemnt
  header={'User-Agent': options['useragent']}

  #URL components
  baseURL=options['baseurl']
  dateURL='&dateType=story&startDate='+humanDate+'&endDate='+humanDate
  outputURL='&output=JSON'
  apiURL='&apiKey='+options['apikey']
  idURL='&id='+str(program)
  resultsURL='&numResults=30'

  if program in (3, 7, 10):
    basepath=humanDate+'_01/'
  else:
    basepath=humanDate+'_02/'

  #set the output directory to match the date and program number
  outpath=options['outpath']+basepath
 
  #check for an existing manifest file - indicates a show ans been downloaded
  if os.path.exists(outpath+'npr.lock'):
    if options['verbose']:
      print 'Program is up to date; nothing downloaded.'
    return(True)

  # assemble the query 
  queryURL=baseURL+dateURL+outputURL+apiURL+idURL+resultsURL

  if options['verbose']:
    print 'Query URL:', queryURL

  try:
    response=urlopen(queryURL)
  except Exception, e:
    print 'error fetching query from NPR: ', e
    print 'URL used: ', queryURL
    return(False)

  #convert to response to a JSON object
  try:
    json_obj=load(response)
  except Exception, e:
    print 'error parsing JSON data: ', e
    json_obj['list']='False'
 
  if not 'story' in json_obj['list']:
    print 'no valid JSON data found in ', queryURL
    return(False)
  
    # make a directory for output
  if not (os.path.exists(outpath)):
    if options['verbose']:
      print 'creating output directory:', outpath
    if options['dryrun']==True:
      print 'Dry run - simulating creation of: ', outpath
    else:
      try:  
        os.makedirs(outpath)
      except Exception, e:
        print 'problem creating output directory:', e
        print 'stopping!'
        return(False)

  #calculate the maximum number of leading zeros needed to pad filenames   
  #excessive, but good practice
  maxmult=int(log10(len(json_obj['list']['story'])))

  for story in json_obj['list']['story']:

    #reinitialize the segment variable to make it clean
    segment={}


    segNum=int(story['show'][0]['segNum']['$text'])
    #add leading zeros to pad out filenames as needed
    segNum='0'*(maxmult-int(log10(segNum)))+str(segNum)
    segment['segNum']=segNum

    #clean any stray characters out of title ('!&*, )
    title=format_filename(story['title']['$text']) 
    segment['title']=title

    #get the program code
    program=str(story['show'][0]['program']['code'])
    segment['program']=program

    extension='.mp4'
    segment['filename']=segNum+'-'+program+'-'+title+extension

    #set the full output path
    segment['outpath']=outpath+'/'+segment['filename']

    #set the date of the broadcast
    segment['date']=humanDate

    try:
       segment['segURL']=story['audio'][0]['format']['mp4']['$text']
    except Exception, e:
        print 'No mp4 audio available for segment', segment['segNum']
        continue

    segment['header']=header
    
    if options['verbose']:
      print '\n','#'*20
      print 'Downloading segment:', segment['segNum']
      print 'URL:', segment['segURL']


    # sleep for a random amount of time between each attempted download
    if options['dryrun']==True:
      randT=0;
    else:
      randT=randint(3,25)

    if options['verbose']:
      print 'seconds sleeping: ', randT
      if options['dryrun']==True:
        print '*'*5, 'DRY RUN', '*'*5
        print 'Simulating download...'
    sleep(randT)
    
    # download the segment
    if options['dryrun']==False:
      if download_segment(segment, options['verbose']):
        # initialize the segment dictionary and make a list of everything downloaded
        programDict[segCount]={}
        programDict[segCount]=segment
        segCount += 1
        tag(segment, options['verbose'])

       
      else:
        print 'Segment', segment, 'not downloaded.'
   # end for loop

  # check to see how many segments have been downloaded
  if segCount > 0:
    
    # create an m3u file to make playback easier
    write_m3u(programDict, humanDate, program, outpath)

    # create a lock file to indicate that the program is downloaded
    try:
      open(outpath+'/npr.lock', 'w').write(str(segCount))
    except Exception, e:
      print 'Problem creating lock file:', e

    # record the directory created by this application for cleanup later
    try:
      with open(options['dnloadlog'], 'a') as output:
        output.write(outpath+'\n')
    except Exception, e:
      print 'Problem writing to file:', options['dnloadlog'], e
      print 'old episodes will not be properly cleaned up!'

    return(True)
  else:
    return(False)

# end download_program


def data_pickle(data, outFile):
  import pickle
 
  try:
    pickle.dump( data, open( outFile, "wb"))
  except Exception, e:
    print 'failed to pickle data structure'
    print 'error writing file:', e



def download_segment(segment, verbose):
  
  if verbose:
    print 'downloading segment:',segment['segNum'], 'to file: ', segment['filename']
    print 'url: ', segment['segURL']
    print 'User-Agent: ', segment['header']
  try:
    r=requests.get(segment['segURL'], headers=segment['header'])
  except Exception, e:
    print 'failed to download segment:', e
    return(False)

  try:
    with open(segment['outpath'], 'wb') as code:
      try:
        code.write(r.content)
      except Exception, e:
        print 'failed to write downloaded data to:', segment['outpath']
        print 'error:', e
        return(False)
      else: 
        return(True)
  except Exception, e:
    print 'failed to open:', segment['outpath']
    print 'error:', e
    return(False)
  else:
    return(True)


def tag(segment, verbose):
  if verbose:
    print 'tagging segment:', segment['segNum'], segment['title']
  
  
  title=str(segment['title'])
  # remove _ to make the title pretty
  try:
    title=title.replace('_', ' ')
  except Exception, e:
    title = 'No title available'


  #load the file to be tagged
  try:
    #audio=EasyMP4(segment['outpath'])
    audio=MP4(segment['outpath'])
  except Exception, e:
    print 'Failed to load tags for:', segment['filename']
    print 'Error:', e
    return(False)

  try:
    audio['title']=title
  except Exception, e:
    #audio['title']='No title available'
    print 'Tagging error:', e

  try:
    audio['album']=segment['program']
  except Exception, e:
    #audio['album']='No program informaiton available'
    print 'Tagging error:', e
    
  try:
    audio['artist']='National Public Radio'
  except Exception, e:
     print 'Tagging error', e

  try:
    audio['tracknumber']=segment['segNum']
  except Exception, e:
    #audio['tracknumber']='00'
    print 'Tagging error:', e

  # try to add the date; if not available, skip it
  try:
    audio['date']=segment['date']
  except:
    pass

  if verbose:
    print 'TAGS:'
    for key in audio:
      print ' '*5, key, audio[key]

  #write the tags to the file
  try:
    audio.save()
  except Exception, e:
    print 'Error writing tags to file:', segment['filename']
    print 'Error:', e

def write_m3u(programDict, humanDate, program, outpath):

  # Add a playlist number to make playlist sorting more logical: 01- for WESAT, WESUN, ME;
  # 02- for ATC
  

  if program=='ATC':
    playListNumber='02-'
  else:
    playListNumber='01-'


  # define the filename
  m3uFile=outpath+humanDate+'_'+playListNumber+program+'.m3u'
  
  # create a map of index values to segment numbers
  index={}
  # FIXME this is brittle.  If the map does not have the same number of keys 
  # as the dictionary this will all go to hell
  # perhaps check the number of keys in the index versus the dict and fall back to an 
  # unsorted list
  for i in programDict:
    if 'segNum' in programDict[i]:
      index[i]=programDict[i]['segNum']

  # open the m3u file for writing
  try:
    f=open(m3uFile, 'w')
  except Exception, e:
    print 'Could not create m3u file:', e
    return(m3uFile)

  # use the index as a map 
  for q in sorted(programDict, key=index.__getitem__):
    try:
      f.write(programDict[q]['filename']+'\n')
    except Exception, e:
      print 'Could not write to m3u file:', e
  
  try:
    f.close
  except Exception, e:
    print 'Could not close m3u file:', e

  return(m3uFile)


def cleanup(options):
  if options['dryrun']==True:
    if options['verbose'] > 0:
      print 'Dry Run: Simulating cleaning...'
    return(True)
  dnLoadLog=options['dnloadlog']

  # open down load log
  # read out lines
  # sort lines
  # remove all but N directories

  # only write changes if they are needed
  updateLog=False

  # create a compiled regexp for matching directories
  filename_re = re.compile(r"(\d{4})-(\d+)-(\d+)_(\d{2})")

  # list of all episodes and their parts
  npr_parts=[]

  #list of duplicate entries
  matches=[]

  # gather directory names from the download log
  # these are directories created by this script
  try:
    filenames= [line.strip() for line in open (dnLoadLog)]
  except Exception, e:
    print 'Could not open download log:', dnLoadLog, e
    print 'Old episodes may need to be removed manually'
    return(False)

  if options['verbose'] > 0:
    print 'download log contains: '
    for i in filenames:
      print i

  # Martin Muggli is responsible for this next section.  It is MAGIC
  for filename in filenames:
    match_obj = filename_re.search(filename)
    if match_obj:
      try:
        year, month, day, partnum = match_obj.groups()
        date = datetime.datetime(int(year), int(month), int(day))
        npr_part = NPR_part(filename, date, int(partnum))
        npr_parts.append(npr_part)
      except Exception, e:
        print 'Bad data in logfile:', e
        return(False)

  # sort the episodes using the npr_part function
  npr_parts.sort(cmp=npr_part_cmp)

  # dummy entry to compare the first list item to
  last = NPR_part('xxx', '1000-01-01 00:00:00', -1)

  #sort and then remove duplicate entries for deletion
  for i in npr_parts:
    #if entries match, record the position of the matches
    if i.filename == last.filename:
      matches.append(npr_parts.index(i))
      updateLog=True
    last=i

  #invert the list of duplicates and remove the highest entries first
  matches=sorted(matches, reverse=True)
  for i in matches:
    npr_parts.pop(i)

  #decide which episodes to remove
  if len(npr_parts) > options['keep']:
    updateLog=True
    for part in npr_parts[:-options['keep']]:
      #delete the full directory
      try:
        shutil.rmtree(part.filename)
      except Exception, e:
        print 'Could not remove', part.filename
        print 'Error:', e
        return(False)

  #open a new download log for writing and update list of current episodes
  if updateLog:
    try:
      f = open(dnLoadLog, 'w')
      for part in npr_parts[-options['keep']:]:
        f.write(part.filename+'\n')
    except Exception, e:
      print 'Could not create new list of downloaded files.'
      print 'Error:', e
    try:
      f.close()
    except Exception, e:
      print 'Could not close', f
      print 'Error:', e
  else:
    if options['verbose']:
      print 'No cleaning needed'
  
  #This appears to always return true unless it errors out.  This may be part of the problem.
  return(True)

  

def main():
  # parse command line options
  args=parse_args()

  #parse configuraiton file
  config=read_config(args)

  #merge the command line and config file options
  options=merge_options(args, config)

  #load non-standard python modules
  options=load_modules(options)

  if args.version:
    print version
    exit(0)

  if args.cleanup:
    cleanup(options) 
    return()

  #fetch a list of episodes to download
  episodes=download_list(options)

  dnLoadSuccess=False

  cleanSuccess=False

  for key in episodes:
    if options['verbose']:
      print '\n'+'*'*70
    if not options['quiet']:
      print 'downloading program', episodes[key]['program']
   
    dnLoadSuccess=download_program(episodes[key]['program'], episodes[key]['date'], options)
    if dnLoadSuccess and options['verbose']:
      print "Job complete"
    if not dnLoadSuccess: 
      print 'Nothing was downloaded for this episode.'
      print 'See previous errors for more details.'

  if options['verbose']:
    print 'Cleaning up old episodes.'
  if not cleanup(options):
    print 'Failed to clean up old episodes.'
  return()

main()
