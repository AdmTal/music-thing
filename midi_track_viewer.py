from PIL import Image
import click
import pygame
from src.midi_stuff import get_frames_where_notes_happen_by_track, convert_midi_to_wav
from src.cache_stuff import get_cache_dir, cleanup_cache_dir


def pygame_surface_to_pil_image(surface):
    """Convert a PyGame surface to a PIL Image."""
    # First, convert the surface to string buffer with the same pixel layout as the surface
    string_image = pygame.image.tostring(surface, "RGBA")

    # Create a PIL Image from the string buffer
    return Image.frombytes("RGBA", surface.get_size(), string_image)


@click.command()
@click.option(
    "--midi",
    required=True,
    type=click.Path(exists=True),
    help="Path to a MIDI file.",
)
def main(midi):
    frame_rate = 60
    note_starts_in_frames = get_frames_where_notes_happen_by_track(midi, frame_rate)
    pygame.init()
    pygame.mixer.init()

    wav_file = f"{get_cache_dir()}/converted_midi.wav"
    convert_midi_to_wav(midi, wav_file)
    sound = pygame.mixer.Sound(wav_file)

    WIDTH, HEIGHT = 1088 // 2, 1920 // 2
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("MIDI Animation")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 36)  # Default font and a size of 36

    curr_frame = 0
    frame_grabs = []
    running = True
    track_display_counters = {track: 0 for track in note_starts_in_frames}
    sound.play()

    while running:
        # Handle quitting the window
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill((255, 255, 255))  # White background

        # Check each track to see if a note is starting on this frame
        for track, frames in note_starts_in_frames.items():
            if frames.get(curr_frame, False):
                track_display_counters[track] = 1

        # Display track names if required
        x = 0
        for track, counter in track_display_counters.items():
            x += 1
            text_surface = font.render(track, True, (200, 200, 200))
            screen.blit(
                text_surface,
                (
                    WIDTH // 2 - text_surface.get_width() // 2,
                    (text_surface.get_height() // 2) + x * 30,
                ),
            )
            if counter > 0:
                text_surface = font.render(track, True, (0, 0, 0))
                screen.blit(
                    text_surface,
                    (
                        WIDTH // 2 - text_surface.get_width() // 2,
                        (text_surface.get_height() // 2) + x * 30,
                    ),
                )
                track_display_counters[track] -= 1  # Decrement the counter

        pygame.display.flip()  # Update the display

        # Save screen
        frame_surface = pygame.Surface(screen.get_size())
        frame_surface.blit(screen, (0, 0))
        frame_grabs.append(pygame_surface_to_pil_image(frame_surface))

        curr_frame += 1

        clock.tick(frame_rate)

    pygame.quit()
    cleanup_cache_dir()


if __name__ == "__main__":
    main()
