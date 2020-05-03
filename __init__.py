# The MIT License (MIT)
#
# Copyright (c) 2020 Donald Falk, @gras64, Andrew Buis
# Initial programing from Donald Falk here: https://github.com/dwfalk/rhythmbox-skill
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
from mycroft.skills.common_play_skill import CommonPlaySkill, CPSMatchLevel
from os.path import expanduser, isabs
from urllib.parse import unquote
from fuzzywuzzy import fuzz, process as fuzz_process

import os
import pathlib
import random
import time
import xml.etree.cElementTree as ET

__author__ = 'dwfalk, gras64, andrewbuis'

logger = getLogger(__name__)


class RhythmboxSkill(CommonPlaySkill):

    def __init__(self):
        super(RhythmboxSkill, self).__init__(name="RhythmboxSkill")
        self.rhythmbox_playlist_xml = expanduser('~/.local/share/rhythmbox/playlists.xml')
        self.rhythmbox_database_xml = expanduser('~/.local/share/rhythmbox/rhythmdb.xml')
        self.shuffle = False
        self.debug_mode = True
        self.playlists = []
        self.titles = []
        self.artists = []
        self.bys = []
        self.albums = []
        self.album_bys = []
        self.genres = []

    def initialize(self):
        stop_rhythmbox_intent = IntentBuilder("StopRhythmboxIntent"). \
            require("StopKeyword").require("RhythmboxKeyword").build()
        self.register_intent(stop_rhythmbox_intent, self.handle_stop_rhythmbox_intent)

        shuffle_rhythmbox_intent = IntentBuilder("ShuffleRhythmboxIntent"). \
            require("ShuffleKeyword").optionally("RhythmboxKeyword").build()
        self.register_intent(shuffle_rhythmbox_intent, self.handle_shuffle_rhythmbox_intent)

        refresh_database_intent = IntentBuilder("RefreshDatabaseIntent"). \
            require("RefreshKeyword").require("DatabaseKeyword").build()
        self.register_intent(refresh_database_intent, self.handle_refresh_database_intent)

        # Messages from the skill-playback-control / common Audio service
        self.add_event('mycroft.audio.service.pause', self.handle_canned_pause)
        self.add_event('mycroft.audio.service.resume', self.handle_canned_resume)
        self.add_event('mycroft.audio.service.next', self.handle_canned_next_song)
        self.add_event('mycroft.audio.service.prev', self.handle_canned_previous_song)
        self.add_event('mycroft.audio.service.stop', self.handle_canned_stop)

        # Pre-build cache
        self._build_cache()
        # Rebuild cache every hour
        self.schedule_repeating_event(self._build_cache, None, 3600)

    def CPS_match_query_phrase(self, phrase):
        ordering = {}
        if self.debug_mode:
            logger.info('CPS_match_query: ' + phrase)
        if not self.playlists and not self.titles and not self.artists and not self.albums and not self.genres:
            self._build_cache()
        if "by" in phrase:
            album, album_by, confidence = self._search_album_by(phrase)
            ordering["album by"] = confidence
            title, title_by, confidence = self._search_by(phrase)
            ordering["title by"] = confidence
            ordered = sorted(ordering, key=ordering.__getitem__, reverse=True)
            if "album by" == ordered[0] and ordering["album by"] > 75:
                return (phrase, CPSMatchLevel.MULTI_KEY, {"by": album_by, "album": album, "confidence": ordering["album by"]})
            elif "title by" == ordered[0] and ordering["title by"] > 65:
                return (phrase, CPSMatchLevel.MULTI_KEY, {"by": title_by, "title": title, "confidence": ordering["title by"]})
        ordering = {}
        genre, confidence = self._search_genre(phrase)
        ordering["genre"] = confidence
        # If we have a high confidence genre, start playing
        # without parsing additional properties.
        if "playlist" not in phrase and confidence > 95:
            return (phrase, CPSMatchLevel.EXACT, {"genre": genre, "confidence": confidence})
        playlist, confidence = self._search_playlist(phrase)
        ordering["playlist"] = confidence
        # If we have a high confidence playlist, start playing
        # without parsing additional properties.
        if confidence >= 95:
            return (phrase, CPSMatchLevel.EXACT, {"playlist": playlist, "confidence": confidence})
        artist, confidence = self._search_artist(phrase)
        ordering["artist"] = confidence
        # If we have a high confidence artist, start playing
        # without parsing additional properties.
        if "playlist" not in phrase and confidence >= 95:
            return (phrase, CPSMatchLevel.EXACT, {"artist": artist, "confidence": confidence})
        album, confidence = self._search_album(phrase)
        ordering["album"] = confidence
        # If we have a high confidence album, start playing
        # without parsing additional properties.
        if "playlist" not in phrase and confidence >= 95:
            return (phrase, CPSMatchLevel.EXACT, {"album": album, "confidence": confidence})
        title, confidence = self._search_title(phrase)
        ordering["title"] = confidence
        # If we have a high confidence title, start playing
        # without parsing additional properties.
        if "playlist" not in phrase and confidence >= 95:
            return (phrase, CPSMatchLevel.EXACT, {"title": title, "confidence": confidence})
        # Parsed all properties, no high confidence property except perhaps album.
        # Do lower confidence returns now.
        if "on rhythmbox" in phrase:
            ordered = sorted(ordering, key=ordering.__getitem__, reverse=True)
            if "playlist" == ordered[0] and ordering["playlist"] > 65:
                return (phrase, CPSMatchLevel.MULTI_KEY, {"playlist": playlist, "confidence": ordering["playlist"]})
            if "genre" == ordered[0] and ordering["genre"] > 70:
                return (phrase, CPSMatchLevel.MULTI_KEY, {"genre": genre, "confidence": ordering["genre"]})
            if "title" == ordered[0] and ordering["title"] > 65:
                return (phrase, CPSMatchLevel.MULTI_KEY, {"title": title, "confidence": ordering["title"]})
            if "artist" == ordered[0] and ordering["artist"] > 70:
                return (phrase, CPSMatchLevel.MULTI_KEY, {"artist": artist, "confidence": ordering["artist"]})
            if "album" == ordered[0] and ordering["album"] > 75:
                return (phrase, CPSMatchLevel.MULTI_KEY, {"album": album, "confidence": ordering["album"]})
            return None
        else:
            ordered = sorted(ordering, key=ordering.__getitem__, reverse=True)
            if "playlist" == ordered[0] and ordering["playlist"] > 65:
                return (phrase, CPSMatchLevel.MULTI_KEY, {"playlist": playlist, "confidence": ordering["playlist"]})
            if "genre" == ordered[0] and ordering["genre"] > 70:
                return (phrase, CPSMatchLevel.GENERIC, {"genre": genre, "confidence": ordering["genre"]})
            if self._general_artist_request(phrase) and "artist" == ordered[0]:
                return (phrase, CPSMatchLevel.MULTI_KEY, {"artist": artist, "confidence": ordering["artist"]})
            if "title" == ordered[0] and ordering["title"] > 65:
                return (phrase, CPSMatchLevel.TITLE, {"title": title, "confidence": ordering["title"]})
            if "artist" == ordered[0] and ordering["artist"] > 70:
                return (phrase, CPSMatchLevel.ARTIST, {"artist": artist, "confidence": ordering["artist"]})
            if "album" == ordered[0] and ordering["album"] > 75:
                return (phrase, CPSMatchLevel.GENERIC, {"album": album, "confidence": ordering["album"]})
            return None

    def CPS_start(self, phrase, data):
        self.shuffle = False
        if self.debug_mode:
            logger.info('CPS_start: ' + phrase)
        if 'by' in data:
            if 'album' in data:
                self._play_album_by(data['by'], data['album'], data['confidence'])
                return None
            elif 'title' in data:
                self._play_by(data['by'], data['title'], data['confidence'])
                return None
        if 'genre' in data:
            self._play_genre(data['genre'], data['confidence'])
        if 'title' in data:
            self._play_title(data['title'], data['confidence'])
        if 'artist' in data:
            self._play_artist(data['artist'], data['confidence'])
        if 'playlist' in data:
            self._play_playlist(data['playlist'], data['confidence'])
        elif 'album' in data:
            self._play_album(data['album'], data['confidence'])

    def handle_stop_rhythmbox_intent(self, message):
        logger.info("Stop Rhythmbox")
        os.system("pkill rhythmbox")
        self.speak_dialog("stop.rhythmbox")

    def handle_shuffle_rhythmbox_intent(self, message):
        self.shuffle = True
        ordering = {}
        utterance = message.utterance_remainder() + " "
        if self.debug_mode:
            logger.info('Shuffle: ' + utterance)
        playlist, confidence = self._search_playlist(utterance)
        ordering["playlist"] = confidence
        album, confidence = self._search_album(utterance)
        ordering["album"] = confidence
        album_by, artist, confidence = self._search_album_by(utterance)
        ordering["album by"] = confidence
        ordered = sorted(ordering, key=ordering.__getitem__, reverse=True)
        if "playlist" == ordered[0] and ordering["playlist"] > 65: 
            self._play_playlist(playlist, ordering["playlist"])
        elif "album" == ordered[0] and ordering["album"] > 75: 
            self._play_album(album, ordering["album"])
        elif "album by" == ordered[0] and ordering["album by"] > 75:
            self._play_album_by(artist, album_by, ordering["album by"])
        else:
            return None 

    def handle_refresh_database_intent(self, message):
        self.speak_dialog("Refreshing Rhythmbox database")
        self._build_cache()

    def handle_canned_pause(self, message):
        os.system("rhythmbox-client --pause")
    
    def handle_canned_stop(self, message):        
        logger.info("Stop Rhythmbox")
        os.system("pkill rhythmbox")
        self.speak_dialog("stop.rhythmbox")

    def handle_canned_resume(self, message):
        os.system("rhythmbox-client --play")

    def handle_canned_next_song(self, message):
        os.system("rhythmbox-client --next")

    def handle_canned_previous_song(self, message):
        os.system("rhythmbox-client --previous")

    def _build_cache(self):
        logger.info("Building Cache")
        self.playlists = []
        self.titles = []
        self.artists = []
        self.bys = []
        self.albums = []
        self.album_bys = []
        self.genres = []
        tree = ET.parse(self.rhythmbox_database_xml)
        root = tree.getroot()
        for entry in root.iter('entry'):
            if entry.attrib["type"] == 'song':
                genre = entry.find('genre').text.lower()
                artist = entry.find('artist').text.lower()
                title = entry.find('title').text.lower()
                album = entry.find('album').text.lower()
                self.bys.append(title + " by " + artist)
                self.album_bys.append(album + " album by " + artist)
                if genre not in self.genres:
                    self.genres.append(genre)
                if artist not in self.artists:
                    self.artists.append(artist)
                if album not in self.albums:
                    self.albums.append(album)
                if title not in self.titles:
                    self.titles.append(title)
        tree = ET.parse(self.rhythmbox_playlist_xml)
        root = tree.getroot()
        for playlist in root.iter('playlist'):
            self.playlists.append(playlist.get('name'))

    def _general_artist_request(self, phrase):
        if "something by" in phrase:
            return True
        if "music by" in phrase:
            return True
        if "tunes by" in phrase:
            return True
        if "a song by" in phrase:
            return True
        if "some songs by" in phrase:
            return True
        if "music from" in phrase:
            return True
        if "tunes from" in phrase:
            return True
        if "a song from" in phrase:
            return True
        if "some songs from" in phrase:
            return True
        return False

    def _search_playlist(self, phrase):
        utterance = phrase + " "
        strip_these = ["playlist ", "on rhythmbox "]
        for words in strip_these:
            utterance = utterance.replace(words, " ")
        utterance.lstrip()
        if self.debug_mode:
            logger.info("Playlist Utterance: " + str(utterance))
        probabilities = fuzz_process.extractOne(utterance, self.playlists, scorer=fuzz.ratio)
        if self.debug_mode:
            logger.info("Playlist Probabilities: " + str(probabilities))
        if probabilities[1] > 65:
            playlist = probabilities[0]
            confidence = probabilities[1]
            return playlist, confidence
        else:
            return "Null", 0

    def _search_title(self, phrase):
        utterance = phrase + " "
        strip_these = ["title ", "song ", "on rhythmbox "]
        for words in strip_these:
            utterance = utterance.replace(words, " ")
        utterance.lstrip()
        if self.debug_mode:
            logger.info("Title Utterance: " + str(utterance))
        probabilities = fuzz_process.extractOne(utterance, self.titles, scorer=fuzz.ratio)
        if self.debug_mode:
            logger.info("Title Probabilities: " + str(probabilities))
        if probabilities[1] > 70:
            title = probabilities[0]
            confidence = probabilities[1]
            return title, confidence
        else:
            return "Null", 0

    def _search_artist(self, phrase):
        utterance = phrase + " "
        strip_these = ["some ", "something ", "music ", "songs ", "tunes ", "by ", "from ", "artist ", "on rhythmbox "]
        for words in strip_these:
            utterance = utterance.replace(words, " ")
        utterance.lstrip()
        if self.debug_mode:
            logger.info("Artist Utterance: " + str(utterance))
        probabilities = fuzz_process.extractOne(utterance, self.artists, scorer=fuzz.ratio)
        if self.debug_mode:
            logger.info("Artist Probabilities: " + str(probabilities))
        if probabilities[1] > 70:
            artist = probabilities[0]
            confidence = probabilities[1]
            return artist, confidence
        else:
            return "Null", 0

    def _search_album(self, phrase):
        utterance = phrase + " "
        strip_these = ["album ", "on rhythmbox "]
        for words in strip_these:
            utterance = utterance.replace(words, " ")
        utterance.lstrip()
        if self.debug_mode:
            logger.info("Album Utterance: " + str(utterance))
        probabilities = fuzz_process.extractOne(utterance, self.albums, scorer=fuzz.ratio)
        if self.debug_mode:
            logger.info("Album Probabilities: " + str(probabilities))
        if probabilities[1] > 70:
            album = probabilities[0]
            confidence = probabilities[1]
            return album, confidence
        else:
            return "Null", 0

    def _search_genre(self, phrase):
        utterance = phrase + " "
        strip_these = ["genre ", "on rhythmbox "]
        for words in strip_these:
            utterance = utterance.replace(words, " ")
        utterance.lstrip()
        if self.debug_mode:
            logger.info("Genre Utterance: " + str(utterance))
        probabilities = fuzz_process.extractOne(utterance, self.genres, scorer=fuzz.ratio)
        if self.debug_mode:
            logger.info("Genre Probabilities: " + str(probabilities))
        if probabilities[1] > 70:
            genre = probabilities[0]
            confidence = probabilities[1]
            return genre, confidence
        else:
            return "Null", 0

    def _search_by(self, phrase):
        utterance = phrase
        if self.debug_mode:
            logger.info("By Utterance: " + str(utterance))
        probabilities = fuzz_process.extractOne(utterance, self.bys, scorer=fuzz.ratio)
        if self.debug_mode:
            logger.info("By Probabilities: " + str(probabilities))
        if probabilities[1] > 85:
            match = probabilities[0]
            x = match.rfind('by')
            title = match[:x-1]
            artist = match[x+3:]
            confidence = probabilities[1]
            return title, artist, confidence
        else:
            return "Null", "Null", 0

    def _search_album_by(self, phrase):
        utterance = phrase
        if self.debug_mode:
            logger.info("Album By Utterance: " + str(utterance))
        probabilities = fuzz_process.extractOne(utterance, self.album_bys, scorer=fuzz.ratio)
        if self.debug_mode:
            logger.info("Album By Probabilities: " + str(probabilities))
        if probabilities[1] > 85:
            match = probabilities[0]
            x = match.rfind('album by')
            album = match[:x-1]
            artist = match[x+9:]
            confidence = probabilities[1]
            return album, artist, confidence
        else:
            return "Null", "Null", 0

    def _play_playlist(self, selection, confidence):
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
                    y = unquote(x)
                    if isabs(y) == True:
                        uri = pathlib.Path(y).as_uri()
                        songs.append(uri)
                if self.shuffle:
                    random.shuffle(songs)
                for uri in songs:
                    song = "rhythmbox-client --enqueue {}".format(uri)
                    os.system(song)
                if len(songs) > 0:
                    self.speak_dialog("selecting playlist")
                    time.sleep(1)
                    os.system("rhythmbox-client --play")
                else:
                    self.speak_dialog("Sorry, I don't know how to play that, yet")
                    if self.debug_mode:
                        logger.info("Cannot play relative paths.")
            if len(songs) > 0:
                break

    def _play_title(self, selection, confidence):
        tree = ET.parse(self.rhythmbox_database_xml)
        root = tree.getroot()
        for entry in root.iter('entry'):
            if entry.attrib["type"] == 'song':
                if selection == entry.find('title').text.lower():
                    os.system("rhythmbox-client --stop")
                    os.system("rhythmbox-client --clear-queue")
                    x = entry.find('location').text[7:]
                    y = unquote(x)
                    if isabs(y) == True:
                        uri = pathlib.Path(y).as_uri()
                        song = "rhythmbox-client --enqueue {}".format(uri)
                        os.system(song)
                        os.system("rhythmbox-client --play")
                    else:
                        self.speak_dialog("Sorry, I don't know how to play that, yet")
                        if self.debug_mode:
                            logger.info("Cannot play relative paths.")

    def _play_artist(self, selection, confidence):
        selection = selection + " "
        strip_these = ["some ", "something ", "music ", "songs ", "tunes ", "by ", "from ", "artist ", "on rhythmbox ", "play "]
        for words in strip_these:
            selection = selection.replace(words, " ")
        os.system("rhythmbox-client --stop")
        os.system("rhythmbox-client --clear-queue")
        songs = []
        tree = ET.parse(self.rhythmbox_database_xml)
        root = tree.getroot()
        for entry in root.iter('entry'):
            if entry.attrib["type"] == 'song':
                if selection.lower() in entry.find('artist').text.lower():
                    x = entry.find('location').text[7:]
                    y = unquote(x)
                if fuzz.ratio(selection.lower(), entry.find('artist').text.lower()) > 80:
                    x = entry.find('location').text[7:]
                    y = unquote(x)
                    if isabs(y) == True:
                        uri = pathlib.Path(y).as_uri()
                        songs.append(uri)
        random.shuffle(songs)
        for uri in songs:
            song = "rhythmbox-client --enqueue {}".format(uri)
            os.system(song)
        if len(songs) > 0:
            self.speak_dialog("selecting artist")
            time.sleep(1)
            os.system("rhythmbox-client --play")
        else:
            self.speak_dialog("Sorry, I don't know how to play that, yet")
            if self.debug_mode:
                logger.info("Cannot play relative paths.")

    def _play_album(self, selection, confidence):
        selection = selection + " "
        strip_these = ["album ", "on rhythmbox ", "play "]
        for words in strip_these:
            selection = selection.replace(words, " ")
        os.system("rhythmbox-client --stop")
        os.system("rhythmbox-client --clear-queue")
        tracks = {}
        songs = []
        tree = ET.parse(self.rhythmbox_database_xml)
        root = tree.getroot()
        for entry in root.iter('entry'):
            if entry.attrib["type"] == 'song':
                if fuzz.ratio(selection.lower(), entry.find('album').text.lower()) > 90:
                    t = entry.find('track-number').text
                    try:
                        t = int(t)
                    except ValueError:
                        t = 0  
                    x = entry.find('location').text[7:]
                    y = unquote(x)
                    if isabs(y) == True:
                        uri = pathlib.Path(y).as_uri()
                        tracks[uri] = t
        if self.shuffle:
            for uri, t in tracks.items():
                songs.append(uri)
                random.shuffle(songs)
        else:
            songs = sorted(tracks, key=tracks.__getitem__)
        for uri in songs:
            song = "rhythmbox-client --enqueue {}".format(uri)
            os.system(song)
        if len(songs) > 0:
            self.speak_dialog("selecting album")
            time.sleep(1)
            os.system("rhythmbox-client --play")
        else:
            self.speak_dialog("Sorry, I don't know how to play that, yet")
            if self.debug_mode:
                logger.info("Cannot play relative paths.")
     
    def _play_genre(self, selection, confidence):
        os.system("rhythmbox-client --stop")
        os.system("rhythmbox-client --clear-queue")
        songs = []
        tree = ET.parse(self.rhythmbox_database_xml)
        root = tree.getroot()
        for entry in root.iter('entry'):
            if entry.attrib["type"] == 'song':
                if fuzz.ratio(selection.lower(), entry.find('genre').text.lower()) > 80 or selection.lower() in entry.find('genre').text.lower():
                    x = entry.find('location').text[7:]
                    y = unquote(x)
                    if isabs(y) == True:
                        uri = pathlib.Path(y).as_uri()
                        songs.append(uri)
        random.shuffle(songs)
        for uri in songs:
            song = "rhythmbox-client --enqueue {}".format(uri)
            os.system(song)
        if len(songs) > 0:
            self.speak_dialog("playing " + selection + " genre")
            time.sleep(1)
            os.system("rhythmbox-client --play")
        else:
            self.speak_dialog("Sorry, I don't know how to play that, yet")
            if self.debug_mode:
                logger.info("Cannot play relative paths.")
   
    def _play_by(self, artist, title, confidence):
        tree = ET.parse(self.rhythmbox_database_xml)
        root = tree.getroot()
        for entry in root.iter('entry'):
            if entry.attrib["type"] == 'song':
                if artist == entry.find('artist').text.lower():
                    if title == entry.find('title').text.lower():
                        os.system("rhythmbox-client --stop")
                        os.system("rhythmbox-client --clear-queue")
                        x = entry.find('location').text[7:]
                        y = unquote(x)
                        if isabs(y) == True:
                            uri = pathlib.Path(y).as_uri()
                            song = "rhythmbox-client --enqueue {}".format(uri)
                            os.system(song)
                            os.system("rhythmbox-client --play")
                        else:
                            self.speak_dialog("Sorry, I don't know how to play that, yet")
                            if self.debug_mode:
                                logger.info("Cannot play relative paths.")

    def _play_album_by(self, artist, album, confidence):
        os.system("rhythmbox-client --stop")
        os.system("rhythmbox-client --clear-queue")
        tracks = {}
        songs = []
        tree = ET.parse(self.rhythmbox_database_xml)
        root = tree.getroot()
        for entry in root.iter('entry'):
            if entry.attrib["type"] == 'song':
                if artist == entry.find('artist').text.lower():
                    if album == entry.find('album').text.lower():
                        t = entry.find('track-number').text
                        try:
                            t = int(t)
                        except ValueError:
                            t = 0  
                        x = entry.find('location').text[7:]
                        y = unquote(x)
                        if isabs(y) == True:
                            uri = pathlib.Path(y).as_uri()
                            tracks[uri] = t
        if self.shuffle:
            for uri, t in tracks.items():
                songs.append(uri)
                random.shuffle(songs)
        else:
            songs = sorted(tracks, key=tracks.__getitem__)
        for uri in songs:
            song = "rhythmbox-client --enqueue {}".format(uri)
            os.system(song)
        if len(songs) > 0:
            self.speak_dialog("selecting album")
            time.sleep(1)
            os.system("rhythmbox-client --play")
        else:
            self.speak_dialog("Sorry, I don't know how to play that, yet")
            if self.debug_mode:
                logger.info("Cannot play relative paths.")

    def stop(self):
        pass


def create_skill():
    return RhythmboxSkill()
