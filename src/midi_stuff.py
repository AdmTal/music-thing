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
    isolated_tracks=None,
    sustain_pedal=False,
):
    # Load MIDI file
    midi_data = pretty_midi.PrettyMIDI(midi_file_path)

    # MIDI volume can range from 0 (silent) to 127 (maximum)
    volume_level = max(0, min(new_volume, 127))

    # Iterate over all instrument tracks
    for i, instrument in enumerate(midi_data.instruments, start=1):
        # Change the instrument program (0 is Acoustic Grand Piano, etc.)
        instrument.program = new_instrument
        # Create and append the volume control change at the beginning of the track
        if isolated_tracks and i not in isolated_tracks:
            instrument.is_drum = False
            instrument.notes = []
            continue

        volume_change = pretty_midi.ControlChange(number=7, value=volume_level, time=0)
        instrument.control_changes.append(volume_change)

        sustain = pretty_midi.ControlChange(number=64, value=1, time=0)
        instrument.control_changes.append(sustain)

        if sustain_pedal:
            # Sustain ON at the start of the track
            sustain_on = pretty_midi.ControlChange(number=64, value=127, time=0)
            instrument.control_changes.append(sustain_on)

            # Optionally, turn off sustain at the end of the track
            # Find the last note's end time to place sustain off event
            last_note_end = max(note.end for note in instrument.notes) if instrument.notes else 0
            sustain_off = pretty_midi.ControlChange(number=64, value=0, time=last_note_end)
            instrument.control_changes.append(sustain_off)

    # Save modified MIDI file
    midi_data.write(output_file_path)


def get_frames_where_notes_happen(midi_file_path, fps, frame_buffer=0, animate_tracks=[]):
    # Load the MIDI file
    midi_data = pretty_midi.PrettyMIDI(midi_file_path)
    frames = set()
    for i, instrument in enumerate(midi_data.instruments, start=1):
        if animate_tracks and i not in animate_tracks:
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
