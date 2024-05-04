# Music Thing

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
  --midi PATH               Path to a MIDI file.  [required]
  --max_frames INTEGER      Max number of frames to generate
  --new_instrument INTEGER  General Midi program number for desired instrument
                            https://en.wikipedia.org/wiki/General_MIDI
  --show_carve              Generate a Carving Video
  --show_platform           Generate a Platform placement Video
  --animate_tracks TEXT     Comma delimited list of track numbers to animate
                            the ball to
  --isolate_tracks          Mute all non animated tracks
  --help                    Show this message and exit.
```