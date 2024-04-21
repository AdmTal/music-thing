from PIL import Image, ImageDraw
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

BG_COLOR = "#494a73"
PADDLE_COLOR = "#110c1d"
BALL_COLOR = "#e9e9fc"
HIT_SHRINK = 0.2
HIT_ANIMATION_LENGTH = 5

SCREEN_WIDTH = 1088
SCREEN_HEIGHT = 1920

BALL_START_X = SCREEN_WIDTH // 2
BALL_START_Y = SCREEN_HEIGHT // 2
BALL_SIZE = 60
BALL_SPEED = 15
MIDI_FILE = "wii-music.mid"
FPS = 60
FRAME_BUFFER = 0


class BadSimulaiton(Exception):
    pass


def animate_throb(n, peak=HIT_ANIMATION_LENGTH // 2, width=HIT_ANIMATION_LENGTH):
    # Calculate the cycle midpoint based on the specified width
    midpoint = width // 2
    # Calculate the current position in the cycle using modulo operation
    position_in_cycle = abs((n - 1) % width - midpoint)
    # Generate the triangular value based on distance from midpoint
    return peak - position_in_cycle


def fade_color(start_color_hex, dest_color_hex, num_frames, curr_frame_number):
    # Extract RGB components from hexadecimal color values
    r_start, g_start, b_start = (
        int(start_color_hex[1:3], 16),
        int(start_color_hex[3:5], 16),
        int(start_color_hex[5:7], 16),
    )
    r_end, g_end, b_end = (
        int(dest_color_hex[1:3], 16),
        int(dest_color_hex[3:5], 16),
        int(dest_color_hex[5:7], 16),
    )

    # Calculate the current color's RGB values using linear interpolation
    r_curr = int(r_start + (r_end - r_start) * (curr_frame_number / num_frames))
    g_curr = int(g_start + (g_end - g_start) * (curr_frame_number / num_frames))
    b_curr = int(b_start + (b_end - b_start) * (curr_frame_number / num_frames))

    # Return the current color in hexadecimal format
    return f"#{r_curr:02x}{g_curr:02x}{b_curr:02x}"


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
        self.color_fade_frames_remaining = 0
        self.size_fade_frames_remaining = 0
        self.original_color = color
        self.original_size = size
        self.current_size = size

    def hit(self):
        self.color_fade_frames_remaining = HIT_ANIMATION_LENGTH
        self.size_fade_frames_remaining = HIT_ANIMATION_LENGTH

    def render(self, image, offset_x=0, offset_y=0):
        draw = ImageDraw.Draw(image)
        # Calculate the size reduction effect
        if self.size_fade_frames_remaining > 0:
            factor = 1 - HIT_SHRINK * (
                animate_throb(self.size_fade_frames_remaining) / HIT_ANIMATION_LENGTH
            )
            spacer_factor = 1 - factor
            self.current_size = int(self.original_size * factor)
            spacer = int(self.current_size * spacer_factor)
            self.size_fade_frames_remaining -= 1
            left = self.x_coord - offset_x + spacer
            right = self.x_coord - offset_x + self.current_size
            top = self.y_coord - offset_y + spacer
            bottom = self.y_coord - offset_y + self.current_size
        else:
            self.current_size = self.original_size
            left = self.x_coord - offset_x
            right = self.x_coord - offset_x + self.current_size
            top = self.y_coord - offset_y
            bottom = self.y_coord - offset_y + self.current_size
        draw.rectangle(
            [left, top, right, bottom],
            outline=self.get_color(),
            fill=None,
            width=10,
        )

    def get_color(self):
        if self.color_fade_frames_remaining > 0:
            faded_color = fade_color(
                "#ffffff",
                self.original_color,
                HIT_ANIMATION_LENGTH,
                self.color_fade_frames_remaining,
            )
            self.color_fade_frames_remaining -= 1
            return faded_color
        return self.original_color

    def predict_position(self, frames):
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
        self._ball_history = []

    def set_platforms(self, platforms):
        self._platforms_set = True
        self._platform_expectations = {
            platform.expected_bounce_frame(): platform for platform in platforms
        }
        self.platforms = platforms

    def update(self):
        self.frame_count += 1

        # Add platform in advance if it's a bounce frame
        if not self._platforms_set and self.frame_count in self.bounce_frames:
            # Get the ball's next frame position
            future_x, future_y = self.ball.predict_position(1)

            # Platform - oriented vertical
            PWIDTH = self.ball.width // 3
            PHEIGHT = self.ball.height
            choice = self._platform_orientations[self.frame_count]
            if choice:
                # Platform - oriented horizontal
                PWIDTH, PHEIGHT = PHEIGHT, PWIDTH

            # Adjust placement to ensure collision
            if self.ball.x_speed > 0:
                new_platform_x = future_x + PHEIGHT
            else:
                new_platform_x = future_x - PHEIGHT
            if self.ball.y_speed > 0:
                new_platform_y = future_y + PWIDTH
            else:
                new_platform_y = future_y - PWIDTH
            # Create and add the new platform
            new_platform = Platform(
                new_platform_x,
                new_platform_y,
                PWIDTH,
                PHEIGHT,
                PADDLE_COLOR,
            )
            self.platforms.append(new_platform)

        hit_platform = self.ball.move(self.platforms, self.frame_count)
        self.adjust_camera()

        if not self._platforms_set:
            return

        if not hit_platform and self.frame_count in self._platform_expectations:
            raise BadSimulaiton(
                f"Bounce should have happened on {self.frame_count} but did not"
            )
        if hit_platform and self.frame_count != hit_platform.expected_bounce_frame():
            raise BadSimulaiton(
                f"A platform was hit on the wrong frame {self.frame_count}"
            )

    def render(self) -> Image:
        image = Image.new("RGB", (self.screen_width, self.screen_height), BG_COLOR)
        self.ball.render(image, self.offset_x, self.offset_y)
        for platform in self.platforms:
            platform.render(image, self.offset_x, self.offset_y)
        return image

    def adjust_camera(self):
        edge_x = self.screen_width * 0.4
        edge_y = self.screen_height * 0.4
        if self.ball.x_coord - self.offset_x < edge_x:
            self.offset_x = self.ball.x_coord - edge_x
        elif self.ball.x_coord - self.offset_x > self.screen_width - edge_x:
            self.offset_x = self.ball.x_coord - (self.screen_width - edge_x)
        if self.ball.y_coord - self.offset_y < edge_y:
            self.offset_y = self.ball.y_coord - edge_y
        elif self.ball.y_coord - self.offset_y > self.screen_height - edge_y:
            self.offset_y = self.ball.y_coord - (self.screen_height - edge_y)

    def draw_ball_history(self, image):
        # Create an ImageDraw object
        draw = ImageDraw.Draw(image)

        # Draw the lines connecting each point in the coordinates list
        draw.line(self._ball_history, fill=(255, 0, 0), width=2)

        return image

    def render_platforms_image(self):
        if not self.platforms:
            return None

        # Determine the size of the image needed
        max_x = max((p.x_coord + p.width) for p in self.platforms)
        max_y = max((p.y_coord + p.height) for p in self.platforms)

        # Create an image large enough to hold all platforms
        image = Image.new("RGB", (int(max_x), int(max_y)), BG_COLOR)
        draw = ImageDraw.Draw(image)

        self.ball.render(image)

        # Draw each platform
        for platform in self.platforms:
            draw.rectangle(
                [
                    platform.x_coord,
                    platform.y_coord,
                    platform.x_coord + platform.width,
                    platform.y_coord + platform.height,
                ],
                fill=platform.get_color(),
            )

        self.draw_ball_history(image)

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
def main(midi):
    frames_where_notes_happen = get_frames_where_notes_happen(midi, FPS, FRAME_BUFFER)
    NUM_FRAMES = max(frames_where_notes_happen)
    frames_where_notes_happen = {i for i in frames_where_notes_happen if i <= NUM_FRAMES}
    click.echo(f"{midi} requires {NUM_FRAMES} frames")

    click.echo(
        f"Searching for valid placement for {len(frames_where_notes_happen)} platforms..."
    )
    boolean_choice_list = get_valid_platform_choices(frames_where_notes_happen, [True])
    choices = {}
    frame_list = sorted(list(frames_where_notes_happen))
    for idx, choice in enumerate(boolean_choice_list):
        choices[frame_list[idx]] = choice
    NUM_FRAMES = max(choices.keys())
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, frames_where_notes_happen, choices)
    for _ in range(NUM_FRAMES):
        scene.update()

    # scene.render_platforms_image().show()

    click.echo(f"\nRunning the simluation again to generate the video")
    platforms = scene.platforms
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball)
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

    click.echo(f"Generate the video")
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
