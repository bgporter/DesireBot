#! /usr/bin/env/python

# Copyright (c) 2015 Brett g Porter
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.



from datetime import datetime
from datetime import date
from glob import glob
from pprint import pprint
from random import choice
from random import random
import re
from time import time
from twython import Twython
from urllib2 import quote


import os.path

from jsonSettings import JsonSettings as Settings
import jsonSettings

# if we're started without a config file, we create a default/empty 
# file that the user can fill in and then restart the app.
kDefaultConfigDict = {
   "appKey"             : "!!! Your app's 'Consumer Key'",
   "appSecret"          : "!!! Your app's 'Consumer Secret'",
   "accessToken"        : "!!! your access token",
   "accessTokenSecret"  : "!!! your access token secret",
   "lyricFilePath"      : "*.lyric",
   "tweetProbability"   : 24.0 / 1440,
   "minimumSpacing"     : 60*60,
   "minimumDaySpacing"  : 30,
   "logFilePath"        : "%Y-%m.txt"
}


rtPat = re.compile(r"\bRT\s")


class DesireBot(object):
   def __init__(self, argDict=None):
      if not argDict:
         argDict = { 'debug' : False, "force": False, 'botPath' : "."}
      # update this object's internal dict with the dict of args that was passed
      # in so we can access those values as attributes.   
      self.__dict__.update(argDict)

      # we build a list of dicts containing status (and whatever other args 
      # we may need to pass to the update_status function as we exit, most 
      # probably 'in_reply-to_status_id' when we're replying to someone.)
      self.tweets = []
      self.retweets = []

      self.settings = Settings(self.GetPath("desireBot.json"), kDefaultConfigDict)
      s = self.settings
      self.twitter = Twython(s.appKey, s.appSecret, s.accessToken, s.accessTokenSecret)   

   def GetPath(self, path):
      '''
         Put all the relative path calculations in one place. If we're given a path
         that has a leading slash, we treat it as absolute and do nothing. Otherwise, 
         we treat it as a relative path based on the botPath setting in our config file.
      '''
      if not path.startswith(os.sep):
         path = os.path.join(self.botPath, path)
      return path

   def Log(self, eventType, dataList):
      '''
         Create an entry in the log file. Each entry will look like:
         timestamp\tevent\tdata1\tdata2 <etc>\n
         where:
         timestamp = integer seconds since the UNIX epoch
         event = string identifying the event
         data1..n = individual data fields, as appropriate for each event type.
         To avoid maintenance issues w/r/t enormous log files, the log filename 
         that's stored in the settings file is passed through datetime.strftime()
         so we can expand any format codes found there against the current date/time
         and create e.g. a monthly log file.
      '''
      now = int(time())
      today = datetime.fromtimestamp(now)
      fileName = self.settings.logFilePath
      if not fileName:
         fileName = "%Y-%m.txt"
         self.settings.logFilePath = fileName
      path = self.GetPath(fileName)
      path = today.strftime(path)
      with open(path, "a+t") as f:
         f.write("{0}\t{1}\t".format(now, eventType))
         f.write("\t".join(dataList))
         f.write("\n")      

   def SendTweets(self):
      ''' send each of the status updates that are collected in self.tweets 
      '''
      for msg in self.tweets:
         if self.debug:
            print msg['status'].encode("UTF-8")
         else:
            self.twitter.update_status(**msg)

      for rt in self.retweets:
         if self.debug:
            print "{0}: {1}".format(rt['id'], rt['text'][:60].encode("UTF-8"))
         else:
            self.twitter.retweet(id=rt['id'])


   def Search(self, searchString):
      ''' return a bunch of tweets that contain the search string, and are NOT retweets. '''
      results = self.twitter.search(q=quote(searchString), src="typd")
      tweets = results['statuses']
      retval = []
      for tweet in tweets:
         text = tweet['text']
         tweetId = tweet['id']
         # ignore manual retweets
         if (not rtPat.search(text)) and ("magick" not in text.lower()):
            retval.append({"id" : tweetId, "text" : text})

      return retval


   def CreateUpdate(self):
      '''
         Called everytime the bot is Run(). 
         If a random number is less than the probability that we should generate
         a tweet (or if we're told to force one), we look into the lyrics database
         and (we hope) append a status update to the list of tweets.

         1/11/14: Added a configurable 'minimumSpacing' variable to prevent us from 
         posting an update too frequently. Starting at an hour ()

      '''
      doUpdate = False
      last = self.settings.lastUpdate or 0
      now = int(time())
      lastTweetAge = now - last

      maxSpace = self.settings.maximumSpacing
      if not maxSpace:
         # default to creating a tweet at *least* every 4 hours.
         maxSpace = 4 * 60 * 60
         self.settings.maximumSpacing = maxSpace

      if lastTweetAge > maxSpace:
         # been too long since the last tweet. Make a new one for our fans!
         doUpdate = True

      elif random() < self.settings.tweetProbability:
         # Make sure that we're not tweeting too frequently. Default is to enforce 
         # a 1-hour gap between tweets (configurable using the 'minimumSpacing' key
         # in the config file, providing a number of minutes we must remain silent.)
         requiredSpace = self.settings.minimumSpacing
         if not requiredSpace:
            # no entry in the file -- let's create one. Default = 1 hour.
            requiredSpace = 60*60
            self.settings.minimumSpacing = requiredSpace

         if lastTweetAge > requiredSpace:
            # Our last tweet was a while ago, let's make another one.
            doUpdate = True

      if doUpdate or self.force:
         desire = choice(["need", "want", "desire"])
         iWant = self.Search('"All I {0}"'.format(desire))
         youWant = self.Search('"All you {0}"'.format(desire))
         if iWant and youWant:
            self.retweets.append(choice(youWant))      
            self.retweets.append(choice(iWant))      
            self.settings.lastUpdate = int(time())
            # we'll log album name, track name, number of lines, number of characters
            self.Log("Retweet", [str(self.retweets[0]['id']), str(self.retweets[1]['id'])])



   def HandleMentions(self):
      '''
         Get all the tweets that mention us since the last time we ran and process each
         one.
         Any time we're mentioned in someone's tweet, we favorite it. If they ask 
         us a question, we reply to them.
      '''
      mentions = self.twitter.get_mentions_timeline(since_id=self.settings.lastMentionId)
      if mentions:
         # Remember the most recent tweet id, which will be the one at index zero.
         self.settings.lastMentionId = mentions[0]['id_str']
         for mention in mentions:
            who = mention['user']['screen_name']
            text = mention['text']
            theId = mention['id_str']

            # we favorite every mention that we see
            if self.debug:
               print "Faving tweet {0} by {1}:\n {2}".format(theId, who, text.encode("utf-8"))
            else:
               self.twitter.create_favorite(id=theId)
            
            eventType = 'Mention'
            # if they asked us a question, reply to them.   
            # if "?" in text:
            #    # create a reply to them. 
            #    maxReplyLen = 120 - len(who)
            #    album, track, msg = self.GetLyric(maxReplyLen)
            #    # get just the first line
            #    msg = msg.split('\n')[0]
            #    # In order to post a reply, you need to be sure to include their username
            #    # in the body of the tweet.
            #    replyMsg = "@{0} {1}".format(who, msg)
            #    self.tweets.append({'status': replyMsg, "in_reply_to_status_id" : theId})
            #    eventType = "Reply"

            self.Log(eventType, [who])

   def Run(self):
      self.CreateUpdate()
      self.HandleMentions()
      self.SendTweets()

      # if anything we did changed the settings, make sure those changes get written out.
      self.settings.lastExecuted = str(datetime.now())
      self.settings.Write()


if __name__ == "__main__":
   import argparse
   parser = argparse.ArgumentParser()
   parser.add_argument("--debug", action='store_true', 
      help="print to stdout instead of tweeting")
   parser.add_argument("--force", action='store_true', 
      help="force operation now instead of waiting for randomness")
   args = parser.parse_args()
   # convert the object returned from parse_args() to a plain old dict
   argDict = vars(args)


   # Find the path where this source file is being loaded from -- we use
   # this when resolving relative paths (e.g., to the data/ directory)
   botPath = os.path.split(__file__)[0]
   argDict['botPath'] = botPath

   try:
      bot = DesireBot(argDict)
      bot.Run()
   except (jsonSettings.SettingsFileError, ) as e:
      # !!! TODO: Write this into a log file (also)
      bot.Log("ERROR", [str(e)])
      print str(e)      