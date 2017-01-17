#!/usr/bin/env python
# Copyright 2016 Aaron ciuffo

version = '''NPR Podcast Downloader V5.0

by Aaron Ciuffo (txoof.com)
released without warranty under GPLV3:
http://www.gnu.org/licenses/gpl-3.0.html
Please don't sue me.
'''

# regexp for finding titles titleList = re.findall(r"audio-module-title\"\>(.*)\<, file)
# regexp for finding urls urlList = re.findall(r"download.*href\=\"(https:\/\/ondemand.npr.org\/.*mp3).*\?", file)


# Imports
import time


class episode():
  '''
  Return an episode object for downloading programs from NPR

  Attributes:
    program: human readable string for program name
    programShortURL: shortened URL for screenscraping program information from HTML
    programCode: program code for API interface (soon to be depricated by NPR)
    segmentcount: integer for number of segments downloaded
    seg_titles: list of titles for all segments in an episode
    seg_files: list of files downloaded for an episode
    episodeDate: datetime object indicating date of episode
  '''
  programs = {"ATC": ("All Things Considered", "all-things-considered", 2), 
              "MED": ("Morning Edition", "morning-edition", 3), 
              "WSA": ("Weekend Edition Saturday", "weekend-edition-saturday", 7),
              "WSU": ("Weekend Edition Sunday", "weekend-edition-sunday", 10)}

  def __init__(self, prg = "ATC"):
    self.program = self.programs[prg][0]
    self.programShortURL = self.programs[prg][1]
    self.programCode = self.programs[prg][2]
    self.segmentcount = 0
    self.outputpath = ""
    #self.seg_titles = []
    #self.seg_files = []
    #self.index
    self.episodeDate = ""


  def setProgram(self, prg):
    '''
    Set the current program and return the human readable name
    '''
    try:
      self.program = self.programs[prg][0]
      self.programShortURL = self.programs[prg][1]
      self.programCode = self.programs[prg][2]
      return(self.program)
    except:
      print "Short program name not found:", prg
      print "Valid program short names:" 
      for keys in self.programs:
        print keys, "-", self.programs[keys][0]


def main():
 print version 

main()
