import pretty_midi
from midi2audio import FluidSynth
from collections import defaultdict

SOUND_FONT_FILE_BETTER = "assets/soundfont.sf2"

TRACK_NOTE_DELIMITER = "#"


def convert_midi_to_wav(
    midi_file_path,
    wav_file_path,
    soundfont=SOUND_FONT_FILE_BETTER,
):
    fs = FluidSynth(soundfont)
    fs.midi_to_audio(midi_file_path, wav_file_path)


def change_instrument(
    midi_file_path,
    output_file_path,
    new_instrument=0,
    new_volume=127,
):
    # Load MIDI file
    midi_data = pretty_midi.PrettyMIDI(midi_file_path)

    # MIDI volume can range from 0 (silent) to 127 (maximum)
    volume_level = max(0, min(new_volume, 127))

    # Iterate over all instrument tracks
    for instrument in midi_data.instruments:
        # Change the instrument program (0 is Acoustic Grand Piano, etc.)
        instrument.program = new_instrument
        # Create and append the volume control change at the beginning of the track
        volume_change = pretty_midi.ControlChange(number=7, value=volume_level, time=0)
        instrument.control_changes.append(volume_change)

        sustain = pretty_midi.ControlChange(number=64, value=1, time=0)
        instrument.control_changes.append(sustain)

    # Save modified MIDI file
    midi_data.write(output_file_path)


def get_frames_where_notes_happen(midi_file_path, fps, frame_buffer=0, isolate_tracks=[]):
    # Load the MIDI file
    midi_data = pretty_midi.PrettyMIDI(midi_file_path)
    frames = set()
    for i, instrument in enumerate(midi_data.instruments, start=1):
        if isolate_tracks and i not in isolate_tracks:
            continue
        for note in instrument.notes:
            frames.add(int(note.start * fps) + frame_buffer)
    return frames


def get_frames_where_notes_happen_by_track(midi_file_path, fps):
    midi_data = pretty_midi.PrettyMIDI(midi_file_path)
    track_events_frames = defaultdict(lambda: defaultdict(bool))
    for i, instrument in enumerate(midi_data.instruments):
        for note in instrument.notes:
            frame = int(note.start * fps)
            track_events_frames[f"track_{i+1}"][frame] = True

    return track_events_frames
