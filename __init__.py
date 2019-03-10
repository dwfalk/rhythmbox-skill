# The MIT License (MIT)
#
# Copyright (c) 2019 Donald Falk
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Requires: mycroft-pip install fuzzywuzzy
#

from adapt.intent import IntentBuilder

from mycroft.skills.core import MycroftSkill
from mycroft.util.log import getLogger
from mycroft.audio import wait_while_speaking
from mycroft.skills.common_play_skill import CommonPlaySkill, CPSMatchLevel
from os.path import expanduser
from fuzzywuzzy import fuzz, process as fuzz_process

import re
import os
import pathlib
import random
import xml.etree.cElementTree as ET

__author__ = 'dwfalk'

logger = getLogger(__name__)


class RhythmboxSkill(CommonPlaySkill):

    def __init__(self):
        super(RhythmboxSkill, self).__init__(name="RhythmboxSkill")
        self.rhythmbox_playlist_xml = expanduser('~/.local/share/rhythmbox/playlists.xml')
        self.rhythmbox_database_xml = expanduser('~/.local/share/rhythmbox/rhythmdb.xml')
        self.shuffle = False
        self.debug_mode = True

    def initialize(self):
        stop_rhythmbox_intent = IntentBuilder("StopRhythmboxIntent"). \
            require("StopKeyword").require("RhythmboxKeyword").build()
        self.register_intent(stop_rhythmbox_intent, self.handle_stop_rhythmbox_intent)

        shuffle_rhythmbox_intent = IntentBuilder("ShuffleRhythmboxIntent"). \
        require("ShuffleKeyword").optionally("RhythmboxKeyword").build()
        self.register_intent(shuffle_rhythmbox_intent, self.handle_shuffle_rhythmbox_intent)

        # Messages from the skill-playback-control / common Audio service
        self.add_event('mycroft.audio.service.pause', self.handle_canned_pause)
        self.add_event('mycroft.audio.service.resume', self.handle_canned_resume)
        self.add_event('mycroft.audio.service.next', self.handle_canned_next_song)
        self.add_event('mycroft.audio.service.prev', self.handle_canned_previous_song)
        self.add_event('mycroft.audio.service.stop', self.handle_stop_rhythmbox_intent)

    def CPS_match_query_phrase(self, phrase):
        if self.debug_mode:
            logger.info('CPS_match_query: ' + phrase)
        playlist, p_confidence = self._search_playlist(phrase)
        title, t_confidence = self._search_title(phrase)
        artist, a_confidence = self._search_artist(phrase)
        if "playlist" in phrase and p_confidence > 65:
            return (phrase, CPSMatchLevel.CATEGORY, {"playlist": playlist})
        if "artist" in phrase and a_confidence > 70:
            return (phrase, CPSMatchLevel.ARTIST, {"artist": artist})
        if t_confidence > p_confidence and t_confidence > a_confidence and t_confidence > 70:
            return (phrase, CPSMatchLevel.TITLE, {"title": title})
        if a_confidence > p_confidence and a_confidence > 70:
            return (phrase, CPSMatchLevel.ARTIST, {"artist": artist})
        if p_confidence > 75:
            return (phrase, CPSMatchLevel.GENERIC, {"playlist": playlist})
        return None

    def CPS_start(self, phrase, data):
        self.shuffle = False
        if self.debug_mode:
            logger.info('CPS_start: ' + phrase)
        if 'title' in data:
            self._play_title(data['title'])
        if 'artist' in data:
            self._play_artist(data['artist'])
        elif 'playlist' in data:
            self._play_playlist(data['playlist'])

    def handle_stop_rhythmbox_intent(self, message):
        os.system("pkill rhythmbox")
        self.speak_dialog("stop.rhythmbox")

    def handle_shuffle_rhythmbox_intent(self, message):
        self.shuffle = True
        utterance = message.utterance_remainder()
        playlist, confidence = self._search_playlist(utterance)
        if playlist: 
            if "playlist" in utterance:
                self._play_playlist(playlist)
            else:
                self._play_playlist(playlist)

    def handle_canned_pause(self, message):
        os.system("rhythmbox-client --pause")

    def handle_canned_resume(self, message):
        os.system("rhythmbox-client --play")

    def handle_canned_next_song(self, message):
        os.system("rhythmbox-client --next")

    def handle_canned_previous_song(self, message):
        os.system("rhythmbox-client --previous")

    def _search_playlist(self, phrase):
        utterance = phrase
        strip_these = [" to", " on", " playlist", " rhythmbox", " play"]
        for words in strip_these:
            utterance = utterance.replace(words, " ")
        utterance.lstrip()
        if self.debug_mode:
            logger.info("Playlist Utterance: " + str(utterance))
        tree = ET.parse(self.rhythmbox_playlist_xml)
        root = tree.getroot()
        playlists = []
        for playlist in root.iter('playlist'):
            playlists.append(playlist.get('name'))
        probabilities = fuzz_process.extractOne(utterance, playlists, scorer=fuzz.ratio)
        if self.debug_mode:
            logger.info("Playlist Probabilities: " + str(probabilities))
        if probabilities[1] > 65:
            playlist = probabilities[0]
            confidence = probabilities[1]
            return playlist, confidence
        else:
            return "Null", 0

    def _search_title(self, phrase):
        utterance = phrase
        strip_these = [" to", " on", " title", " song", " rhythmbox", " play"]
        for words in strip_these:
            utterance = utterance.replace(words, " ")
        utterance.lstrip()
        if self.debug_mode:
            logger.info("Title Utterance: " + str(utterance))
        tree = ET.parse(self.rhythmbox_database_xml)
        root = tree.getroot()
        titles = []
        for entry in root.iter('entry'):
            if entry.attrib["type"] == 'song':
                title = entry.find('title').text
                titles.append(title)
        probabilities = fuzz_process.extractOne(utterance, titles, scorer=fuzz.ratio)
        if self.debug_mode:
            logger.info("Title Probabilities: " + str(probabilities))
        if probabilities[1] > 70:
            title = probabilities[0]
            confidence = probabilities[1]
            return title, confidence
        else:
            return "Null", 0

    def _search_artist(self, phrase):
        utterance = phrase
        strip_these = ["some ", "something ", " music", " songs", " by", " from", " artist", " rhythmbox", " play"]
        for words in strip_these:
            utterance = utterance.replace(words, " ")
        utterance.lstrip()
        if self.debug_mode:
            logger.info("Artist Utterance: " + str(utterance))
        tree = ET.parse(self.rhythmbox_database_xml)
        root = tree.getroot()
        artists = []
        for entry in root.iter('entry'):
            if entry.attrib["type"] == 'song':
                artist = entry.find('artist').text
                artists.append(artist)
        probabilities = fuzz_process.extractOne(utterance, artists, scorer=fuzz.ratio)
        if self.debug_mode:
            logger.info("Artist Probabilities: " + str(probabilities))
        if probabilities[1] > 70:
            artist = probabilities[0]
            confidence = probabilities[1]
            return artist, confidence
        else:
            return "Null", 0
                
    def _play_playlist(self, selection):
        self.speak_dialog("selecting playlist")
        songs = []
        tree = ET.parse(self.rhythmbox_playlist_xml)
        root = tree.getroot()
        for playlist in root.iter('playlist'):
            name = playlist.get('name') 
            if name == selection:
                os.system("rhythmbox-client --stop")
                os.system("rhythmbox-client --clear-queue")
                for location in playlist.iter('location'):
                    x = location.text[7:]
                    y = re.sub("%20", " ",x)
                    uri = pathlib.Path(y).as_uri()
                    songs.append(uri)
                if self.shuffle:
                    random.shuffle(songs)
                for uri in songs:
                    song = "rhythmbox-client --enqueue {}".format(uri)
                    os.system(song)
                os.system("rhythmbox-client --play")
            if len(songs) > 0:
                break

    def _play_title(self, selection):
        tree = ET.parse(self.rhythmbox_database_xml)
        root = tree.getroot()
        for entry in root.iter('entry'):
            if entry.attrib["type"] == 'song':
                if selection == entry.find('title').text:
                    os.system("rhythmbox-client --stop")
                    os.system("rhythmbox-client --clear-queue")
                    x = entry.find('location').text[7:]
                    y = re.sub("%20", " ",x)
                    uri = pathlib.Path(y).as_uri()
                    song = "rhythmbox-client --enqueue {}".format(uri)
                    os.system(song)
                    os.system("rhythmbox-client --play")

    def _play_artist(self, selection):
        self.speak_dialog("selecting artist")
        os.system("rhythmbox-client --stop")
        os.system("rhythmbox-client --clear-queue")
        songs = []
        tree = ET.parse(self.rhythmbox_database_xml)
        root = tree.getroot()
        for entry in root.iter('entry'):
            if entry.attrib["type"] == 'song':
                if fuzz.ratio(selection, entry.find('artist').text) > 90:
                    x = entry.find('location').text[7:]
                    y = re.sub("%20", " ",x)
                    uri = pathlib.Path(y).as_uri()
                    songs.append(uri)
        random.shuffle(songs)
        for uri in songs:
            song = "rhythmbox-client --enqueue {}".format(uri)
            os.system(song)
        os.system("rhythmbox-client --play")
        

    def stop(self):
        pass


def create_skill():
    return RhythmboxSkill()
