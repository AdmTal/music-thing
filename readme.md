# Music Thing

TLDR - I didn't come up with the idea for this video; I saw someone else do it and thought it would be fun to try recreating it myself.

However - the code in this repo takes a MIDI file, and creates a video like this:

https://github.com/AdmTal/music-thing/assets/3382568/470d4db7-dd4b-4761-85f7-bf967de41600

I later found the project I've been replicating - It's amazing you should check that out if you're interested: https://github.com/quasar098/midi-playground

# Repo Quality

I work on this repo for fun to blow off steam - It's a mess, please don't judge me on it's quality.  It's just a junk drawer repo for fun.

# Longer History

I'm trying to make videos like this https://www.tiktok.com/@jb.reddit

I've seen many others like it on TikTok by other creators.

Still WIP - just getting started.

I don't know why I'm so obsessed with replicating these videos right now.

I'll prob give this a few more hours over the next couple of weeks and then move on to something else.

You can run this with any MIDI file

~~If anyone already knows of an open source repo that makes these videos already, please let me know.~~

Update - I found the repo!  https://github.com/quasar098/midi-playground

It's incredible - go look at that instead

# How to Run

1. Install the "soundfont" file found here: https://www.doomworld.com/forum/topic/98376-recommended-soundfonts/?tab=comments#comment-1827928)
2. Save it to "assets/soundfont.sf2"
2. Create Virtualenv, install deps, and run the code

```shell
python3 -m venv venv
pip install -r requirements.txt
source venv/bin/activate
python main.py
```

### Help

```shell
Usage: main.py [OPTIONS]

Options:
  -m, --midi PATH                Path to a MIDI file.  [required]
  -mf, --max_frames INTEGER      Max number of frames to generate
  -ni, --new_instrument INTEGER  General Midi program number for desired
                                 instrument
                                 https://en.wikipedia.org/wiki/General_MIDI
  -at, --animate_tracks TEXT     Comma delimited list of track numbers to
                                 animate the ball to
  -i, --isolate                  Mute all non animated tracks
  --show_carve                   Generate a Carving Video
  --show_platform                Generate a Platform placement Video
  --help                         Show this message and exit.
```
