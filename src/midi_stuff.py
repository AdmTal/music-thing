import pretty_midi
from midi2audio import FluidSynth

SOUND_FONT_FILE_BETTER = "assets/soundfont.sf2"

TRACK_NOTE_DELIMITER = "#"


def convert_midi_to_wav(midi_file_path, wav_file_path, soundfont):
    fs = FluidSynth(soundfont)
    fs.midi_to_audio(midi_file_path, wav_file_path)


def get_frames_where_notes_happen(midi_file_path, fps, frame_buffer=0):
    # Load the MIDI file
    midi_data = pretty_midi.PrettyMIDI(midi_file_path)
    frames = set()
    for i, instrument in enumerate(midi_data.instruments, start=1):
        for note in instrument.notes:
            frames.add(int(note.start * fps) + frame_buffer)
    return frames
