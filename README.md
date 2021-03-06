# rhythmbox-skill
RhythmboxSkill for Mycroft
## About 
Let Mycroft help you control Rhythmbox. When asked Mycroft interfaces with Rhythmbox to play selections from your music library. 

## Examples 
* "play rock" - plays any genre with "rock" in it (e.g. rock, rock/pop, rock/country)
* "play **" - plays closest match (genre/artist/album/song)
* "play ** playlist" - by playlist
* "play something by **" - by artist
* "shuffle **" - plays closest match (playlist/album)
* "refresh Rhythmbox database" - pull in any recently added playlists
* "pause"
* "resume"
* "next song"
* "previous song"
* "stop Rhythmbox"
* "play some music by Huey Lewis and the News"
* "play Feelin' Alright by Joe Cocker"
* "play Greatist Hits album by Heart"
* "shuffle Greatest Hits album by Fleetwood Mac"

## Credits 
@dwfalk - Base project
@gras64 - German Translations
@unwisebard - Ability to search/play by genre

## Dependencies
mycroft-pip install fuzzywuzzy

apt install rhythmbox

## Category
**Entertainment**

## Tags
#songs
#music
#rhythmbox
#mycroft
#skill

To install:
~/mycroft-core/bin/mycroft-msm install https://github.com/dwfalk/rhythmbox-skill
