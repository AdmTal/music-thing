from PIL import Image, ImageDraw, ImageFilter
import click
import imageio
import numpy as np
import random

from src.midi_stuff import (
    get_frames_where_notes_happen,
    SOUND_FONT_FILE_BETTER,
)
from src.video_stuff import finalize_video_with_music
from src.cache_stuff import get_cache_dir

BG_COLOR = "#2AC9F9"
PADDLE_COLOR = "#243e36"
BALL_COLOR = "#BF4BF8"
HIT_SHRINK = 0.3
HIT_ANIMATION_LENGTH = 30

CUTTER = 2

SCREEN_WIDTH = 1088 // CUTTER
SCREEN_HEIGHT = 1920 // CUTTER

BALL_START_X = SCREEN_WIDTH // CUTTER
BALL_START_Y = SCREEN_HEIGHT // CUTTER

BALL_SIZE = 100 // CUTTER
PLATFORM_HEIGHT = 200 // CUTTER
PLATFORM_WIDTH = 50 // CUTTER

BALL_SPEED = 30
MIDI_FILE = "wii-music.mid"
FPS = 60
FRAME_BUFFER = 15


class BadSimulaiton(Exception):
    pass


def lerp(start, end, alpha):
    """Linearly interpolates between start and end."""
    return start + (end - start) * alpha


class Thing:
    def __init__(self, x_coord, y_coord, width, height, color):
        self.x_coord = x_coord
        self.y_coord = y_coord
        self.width = width
        self.height = height
        self.color = color

    def get_color(self):
        return self.color

    def render(self, image, offset_x, offset_y):
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            [
                self.x_coord - offset_x,
                self.y_coord - offset_y,
                self.x_coord + self.width - offset_x,
                self.y_coord + self.height - offset_y,
            ],
            fill=self.get_color(),
        )


class Platform(Thing):
    def __init__(self, x_coord, y_coord, width, height, color):
        super().__init__(x_coord, y_coord, width, height, color)
        self._expected_bounce_frame = None

    def set_expected_bounce_frame(self, frame):
        if self._expected_bounce_frame:
            return
        self._expected_bounce_frame = frame

    def expected_bounce_frame(self):
        return self._expected_bounce_frame


class Ball(Thing):
    def __init__(self, x_coord, y_coord, size, color, speed):
        super().__init__(x_coord, y_coord, size, size, color)
        self.x_speed = speed
        self.y_speed = speed
        self.explosion_fade_frames_remaining = HIT_ANIMATION_LENGTH
        self.original_color = color
        self.original_size = size
        self.current_size = size

    def hit(self):
        self.explosion_fade_frames_remaining = HIT_ANIMATION_LENGTH

    def render(self, image, offset_x=0, offset_y=0):
        draw = ImageDraw.Draw(image)

        # Draw the regular square
        left = self.x_coord - offset_x
        right = self.x_coord - offset_x + self.current_size
        top = self.y_coord - offset_y
        bottom = self.y_coord - offset_y + self.current_size
        draw.rectangle(
            [left, top, right, bottom],
            outline=self.get_color(),
            fill=None,
            width=10 // CUTTER,
        )

        # Draw and blur the "explosion" effect
        if self.explosion_fade_frames_remaining > 0:
            expansion = int(
                2
                * self.original_size
                * (1 - (self.explosion_fade_frames_remaining / HIT_ANIMATION_LENGTH))
            )
            explosion_size = self.original_size + expansion
            explosion_image = Image.new("RGBA", (explosion_size, explosion_size))
            explosion_draw = ImageDraw.Draw(explosion_image)

            # Draw the explosion at the center of the new image
            explosion_draw.rectangle(
                [
                    expansion // 2,
                    expansion // 2,
                    explosion_size - expansion // 2,
                    explosion_size - expansion // 2,
                ],
                outline="#FF5BFF",
            )

            # Apply Gaussian Blur
            radius = 2 * (
                1 - (self.explosion_fade_frames_remaining / HIT_ANIMATION_LENGTH)
            )  # Increase blur as it fades
            explosion_image = explosion_image.filter(
                ImageFilter.GaussianBlur(radius=radius)
            )

            # Paste the blurred explosion onto the original image
            explosion_left = int(self.x_coord - offset_x - expansion // 2)
            explosion_top = int(self.y_coord - offset_y - expansion // 2)
            image.paste(
                explosion_image, (explosion_left, explosion_top), explosion_image
            )

            self.explosion_fade_frames_remaining -= 1

    def get_color(self):
        return self.original_color

    def predict_position(self, frames=1):
        future_x = self.x_coord + self.x_speed * frames
        future_y = self.y_coord + self.y_speed * frames
        return future_x, future_y

    def move(self, platforms, frame):
        # Calculate potential next position of the ball
        next_x = self.x_coord
        next_y = self.y_coord
        hit_platform = None

        # Check each platform for a possible collision
        for platform in platforms:
            # Define the bounds of the ball at its next position
            ball_left = next_x
            ball_right = next_x + self.width
            ball_top = next_y
            ball_bottom = next_y + self.height

            # Define the bounds of the current platform
            plat_left = platform.x_coord
            plat_right = platform.x_coord + platform.width
            plat_top = platform.y_coord
            plat_bottom = platform.y_coord + platform.height

            # Check if the ball's next position overlaps with the platform
            if all(
                [
                    ball_right >= plat_left,
                    ball_left <= plat_right,
                    ball_bottom >= plat_top,
                    ball_top <= plat_bottom,
                ]
            ):
                # Calculate the overlap on each side
                overlap_left = ball_right - plat_left
                overlap_right = plat_right - ball_left
                overlap_top = ball_bottom - plat_top
                overlap_bottom = plat_bottom - ball_top

                # Determine the smallest overlap to resolve the collision minimally
                min_overlap = min(
                    overlap_left, overlap_right, overlap_top, overlap_bottom
                )

                # Adjust ball's speed and position based on the minimal overlap side
                if min_overlap == overlap_left:
                    # Reverse horizontal speed
                    self.x_speed = -abs(self.x_speed)
                    # Reposition to the left of the platform
                    self.x_coord = plat_left - self.width
                elif min_overlap == overlap_right:
                    # Maintain horizontal speed
                    self.x_speed = abs(self.x_speed)
                    # Reposition to the right of the platform
                    self.x_coord = plat_right
                elif min_overlap == overlap_top:
                    # Reverse vertical speed
                    self.y_speed = -abs(self.y_speed)
                    # Reposition above the platform
                    self.y_coord = plat_top - self.height
                elif min_overlap == overlap_bottom:
                    # Maintain vertical speed
                    self.y_speed = abs(self.y_speed)
                    # Reposition below the platform
                    self.y_coord = plat_bottom

                platform.set_expected_bounce_frame(frame)
                hit_platform = platform
                self.hit()
                break

        # Update the ball's position with the potentially new speed
        self.x_coord += self.x_speed
        self.y_coord += self.y_speed

        return hit_platform


class Scene:
    def __init__(
        self,
        screen_width,
        screen_height,
        ball,
        bounce_frames=[],
        platform_orientations={},
    ):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.ball = ball
        self.platforms = []
        self.bounce_frames = set(bounce_frames)
        self.frame_count = 0
        self.offset_x = 0
        self.offset_y = 0
        self._platforms_set = False
        self._platform_orientations = platform_orientations

    def set_platforms(self, platforms):
        self._platforms_set = True
        self._platform_expectations = {
            platform.expected_bounce_frame(): platform for platform in platforms
        }
        self.platforms = platforms

    def update(self):
        self.frame_count += 1

        # When the platforms are not set, we are creating them
        if not self._platforms_set and self.frame_count in self.bounce_frames:
            future_x, future_y = self.ball.predict_position()

            platform_orientation = self._platform_orientations.get(
                self.frame_count,
                False,
            )
            # Horizontal orientation
            if platform_orientation:
                pwidth, pheight = PLATFORM_HEIGHT, PLATFORM_WIDTH
                new_platform_x = future_x - pwidth // 2
                new_platform_y = (
                    future_y - pheight if self.ball.y_speed < 0 else future_y + pheight
                )
            # Vertical orientation
            else:
                pwidth, pheight = PLATFORM_WIDTH, PLATFORM_HEIGHT
                new_platform_x = (
                    future_x - pwidth if self.ball.x_speed < 0 else future_x + pwidth
                )
                new_platform_y = future_y - pheight // 2

            new_platform = Platform(
                new_platform_x,
                new_platform_y,
                pwidth,
                pheight,
                PADDLE_COLOR,
            )
            self.platforms.append(new_platform)

        # Move ball and check for collisions
        hit_platform = self.ball.move(self.platforms, self.frame_count)
        self.adjust_camera()

        if self._platforms_set:
            if not hit_platform and self.frame_count in self._platform_expectations:
                raise BadSimulaiton(
                    f"Bounce should have happened on {self.frame_count} but did not"
                )
            if (
                hit_platform
                and self.frame_count != hit_platform.expected_bounce_frame()
            ):
                raise BadSimulaiton(
                    f"A platform was hit on the wrong frame {self.frame_count}"
                )

    def render(self) -> Image:
        image = Image.new("RGBA", (self.screen_width, self.screen_height), BG_COLOR)
        self.ball.render(image, self.offset_x, self.offset_y)
        for platform in self.platforms:
            platform.render(image, self.offset_x, self.offset_y)
        return image

    def adjust_camera(self):
        edge_x = self.screen_width * 0.5
        edge_y = self.screen_height * 0.5

        # Desired offsets based on ball's position
        desired_offset_x = (
            self.ball.x_coord - edge_x
            if self.ball.x_speed < 0
            else self.ball.x_coord - (self.screen_width - edge_x)
        )
        desired_offset_y = (
            self.ball.y_coord - edge_y
            if self.ball.y_speed < 0
            else self.ball.y_coord - (self.screen_height - edge_y)
        )

        # Smoothing factor
        alpha = BALL_SPEED / 100

        # Update camera offsets using linear interpolation for smoother movement
        self.offset_x = lerp(self.offset_x, desired_offset_x, alpha)
        self.offset_y = lerp(self.offset_y, desired_offset_y, alpha)

    def render_platforms_image(self):
        if not self.platforms:
            return None

        min_x = min(p.x_coord for p in self.platforms)
        max_x = max(p.x_coord + p.width for p in self.platforms)
        min_y = min(p.y_coord for p in self.platforms)
        max_y = max(p.y_coord + p.height for p in self.platforms)

        img_width = max_x - min_x
        img_height = max_y - min_y

        image = Image.new("RGB", (img_width, img_height), BG_COLOR)
        draw = ImageDraw.Draw(image)

        for platform in self.platforms:
            draw.rectangle(
                [
                    platform.x_coord - min_x,
                    platform.y_coord - min_y,
                    platform.x_coord + platform.width - min_x,
                    platform.y_coord + platform.height - min_y,
                ],
                fill=platform.get_color(),
            )

        return image


def choices_are_valid(frames_where_notes_happen, boolean_choice_list):
    choices = {}
    frame_list = sorted(list(frames_where_notes_happen))
    for idx, choice in enumerate(boolean_choice_list):
        choices[frame_list[idx]] = choice
    NUM_FRAMES = max(choices.keys())

    # First - Run Choices through empty Environment to place the Platforms
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, frames_where_notes_happen, choices)
    for _ in range(NUM_FRAMES):
        scene.update()

    # Then - Check if Scene is valid when platforms placed at start
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    platforms = scene.platforms
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball)
    scene.set_platforms(platforms)
    try:
        for _ in range(NUM_FRAMES):
            scene.update()
    except BadSimulaiton:
        return False

    return True


def get_valid_platform_choices(frames_where_notes_happen, boolean_choice_list):
    expected = len(frames_where_notes_happen)
    actual = len(boolean_choice_list)
    progress = int((actual / expected) * 100)
    click.echo(f"\rProgress: {progress}%\t\t", nl=False)
    if len(boolean_choice_list) == len(frames_where_notes_happen):
        if choices_are_valid(frames_where_notes_happen, boolean_choice_list):
            return boolean_choice_list
        else:
            return None

    # Check if the current partial string is valid
    if not choices_are_valid(frames_where_notes_happen, boolean_choice_list):
        # Prune the search tree here
        return None

    next_choices = [True, False]
    if random.choice([True, False]):
        next_choices = [False, True]

    for rand_choice in next_choices:
        result = get_valid_platform_choices(
            frames_where_notes_happen,
            boolean_choice_list + [rand_choice],
        )
        if result is not None:
            return result

    return None


@click.command()
@click.option(
    "--midi",
    required=True,
    default=MIDI_FILE,
    type=click.Path(exists=True),
    help="Path to a MIDI file.",
)
@click.option(
    "--max_frames",
    default=None,
    type=int,
    help="Max number of frames to generate",
)
def main(midi, max_frames):
    frames_where_notes_happen = get_frames_where_notes_happen(midi, FPS, FRAME_BUFFER)
    NUM_FRAMES = max(frames_where_notes_happen) if max_frames is None else max_frames
    frames_where_notes_happen = {
        i for i in frames_where_notes_happen if i <= NUM_FRAMES
    }
    click.echo(f"{midi} requires {NUM_FRAMES} frames")

    click.echo(
        f"Searching for valid placement for {len(frames_where_notes_happen)} platforms..."
    )
    boolean_choice_list = get_valid_platform_choices(frames_where_notes_happen, [True])
    if not boolean_choice_list:
        click.echo("\nCould not figure out platforms :(")
        exit(0)
    choices = {}
    frame_list = sorted(list(frames_where_notes_happen))
    for idx, choice in enumerate(boolean_choice_list):
        choices[frame_list[idx]] = choice
    NUM_FRAMES = max(choices.keys())
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, frames_where_notes_happen, choices)
    for _ in range(NUM_FRAMES):
        scene.update()

    click.echo(f"\nRunning the simluation again to generate the video")
    platforms = scene.platforms
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, frames_where_notes_happen)
    scene.set_platforms(platforms)

    VIDEO_FILE = f"{get_cache_dir()}/scene.mp4"
    writer = imageio.get_writer(VIDEO_FILE, fps=FPS)
    for curr in range(NUM_FRAMES):
        try:
            scene.update()
        except BadSimulaiton as err:
            click.echo(f"BAD {scene.frame_count} :: {err}")
        image = scene.render()
        writer.append_data(np.array(image))
        progress = (scene.frame_count / NUM_FRAMES) * 100
        click.echo(f"\r{progress:0.0f}% ({scene.frame_count} frames)", nl=False)

    click.echo(f"\nGenerate the video")
    finalize_video_with_music(
        writer,
        VIDEO_FILE,
        "final",
        midi,
        FPS,
        SOUND_FONT_FILE_BETTER,
        scene.frame_count,
        FRAME_BUFFER,
    )


if __name__ == "__main__":
    main()
