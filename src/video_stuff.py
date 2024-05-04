import os
import time
import subprocess

import click
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment

from src.midi_stuff import convert_midi_to_wav, change_instrument
from src.cache_stuff import get_cache_dir


def finalize_video_with_music(
    writer,
    video_file_path,
    output_file_name,
    midi_file_path,
    frame_rate,
    soundfont_file,
    frames_written,
    frame_offset,
    new_instrument=None,
    isolated_tracks=None,
):
    # Ensure the writer is closed
    writer.close()

    # Audio processing
    temp_music_file = os.path.join(get_cache_dir(), "temp_music.wav")
    open(temp_music_file, "ab").close()
    click.echo("Converting midi to wave...")

    if new_instrument:
        new_mid_path = f"{get_cache_dir()}/alter.mid"
        change_instrument(
            midi_file_path,
            new_mid_path,
            new_instrument=new_instrument,
            isolated_tracks=isolated_tracks,
        )
        midi_file_path = new_mid_path

    convert_midi_to_wav(
        midi_file_path,
        temp_music_file,
        soundfont_file,
    )
    silent_segment = AudioSegment.silent(duration=frame_offset * 1000 / frame_rate)
    audio_duration = int((frames_written / frame_rate) * 1000)

    audio_clip = AudioSegment.from_file(temp_music_file)
    audio_clip = audio_clip[:audio_duration]  # Truncate the audio

    temp_audio = f"{get_cache_dir()}/music.wav"
    audio_clip.export(temp_audio, format="wav")
    delayed_audio_clip = silent_segment + audio_clip
    delayed_audio_clip.export(temp_audio, format="wav")

    final_video = VideoFileClip(video_file_path)
    final_video_audio = AudioFileClip(temp_audio)
    final_video = final_video.set_audio(final_video_audio)

    timestamp = int(time.time())
    final_output_path = f"{output_file_name}_{timestamp}.mp4"
    final_video.write_videofile(final_output_path, codec="libx264", audio_codec="aac")

    subprocess.run(["open", final_output_path])

    return final_output_path
