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


class BadSimulaiton(Exception):
    pass


class Thing:
    def __init__(self, x_coord, y_coord, width, height, color):
        self.x_coord = x_coord
        self.y_coord = y_coord
        self.width = width
        self.height = height
        self.color = color

    def render(self, image, offset_x, offset_y):
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            [
                self.x_coord - offset_x,
                self.y_coord - offset_y,
                self.x_coord + self.width - offset_x,
                self.y_coord + self.height - offset_y,
            ],
            fill=self.color,
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

    def predict_position(self, frames):
        future_x = self.x_coord + self.x_speed * frames
        future_y = self.y_coord + self.y_speed * frames
        return future_x, future_y

    def move(self, platforms, frame):
        # Calculate potential next position of the ball
        next_x = self.x_coord + self.x_speed
        next_y = self.y_coord + self.y_speed
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
                        ball_right > plat_left,
                        ball_left < plat_right,
                        ball_bottom > plat_top,
                        ball_top < plat_bottom,
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

        # Add platform in advance if it's a bounce frame
        if not self._platforms_set and self.frame_count in self.bounce_frames:
            # Get the ball's next frame position
            future_x, future_y = self.ball.predict_position(1)

            PWIDTH = ball.width // 2
            PHEIGHT = ball.height * 2
            choice = self._platform_orientations[self.frame_count]
            if choice:
                PWIDTH, PHEIGHT = PHEIGHT, PWIDTH

            # Adjust placement to ensure collision
            if self.ball.x_speed > 0:
                new_platform_x = future_x + PHEIGHT / 2
            else:
                new_platform_x = future_x - PHEIGHT / 2
            if self.ball.y_speed > 0:
                new_platform_y = future_y + PWIDTH / 2
            else:
                new_platform_y = future_y - PWIDTH / 2

            # Create and add the new platform
            new_platform = Platform(
                new_platform_x,
                new_platform_y,
                PWIDTH,
                PHEIGHT,
                "black",
            )
            self.platforms.append(new_platform)

        # Move the ball
        hit_platform = self.ball.move(self.platforms, self.frame_count)
        if self._platforms_set:
            if not hit_platform and self.frame_count in self._platform_expectations:
                raise BadSimulaiton(f"Bounce should have happened on {self.frame_count} but did not")
            if hit_platform and self.frame_count != hit_platform.expected_bounce_frame():
                raise BadSimulaiton(f"A platform was hit on the wrong frame {self.frame_count}")
        self.adjust_camera()

    def render(self) -> Image:
        image = Image.new("RGB", (self.screen_width, self.screen_height), "white")
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


SCREEN_WIDTH = 1088
SCREEN_HEIGHT = 1920

BALL_START_X = SCREEN_WIDTH // 2
BALL_START_Y = SCREEN_HEIGHT // 2
BALL_SIZE = 100
BALL_COLOR = "red"
BALL_SPEED = 15
MIDI_FILE = "wii-music.mid"
FPS = 60
FRAME_BUFFER = 15

frames_where_notes_happen = get_frames_where_notes_happen(MIDI_FILE, FPS, FRAME_BUFFER)
NUM_FRAMES = max(frames_where_notes_happen) // 10
click.echo(f"{MIDI_FILE} requires {NUM_FRAMES} frames")

click.echo(f"Choose random platform orientations...")
choices = {frame: random.choice([True, False]) for frame in frames_where_notes_happen}
click.echo(f"Simulate platform orientations until a good one is found...")
valid = False
simulation_num = 0
while not valid:
    simulation_num += 1
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, frames_where_notes_happen, choices)
    for _ in range(NUM_FRAMES):
        scene.update()

    # Check Valid
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    platforms = scene.platforms
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball)
    scene.set_platforms(platforms)
    try:
        for _ in range(NUM_FRAMES):
            scene.update()
    except BadSimulaiton as err:
        click.echo(f"\rSimulation {simulation_num} Failed :: {err}{' ' * 10}", nl=False)
        choices = {
            frame: random.choice([True, False]) for frame in frames_where_notes_happen
        }
        continue

    valid = True

click.echo(f"Run the simulation again - with the platforms already in place")
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

writer.close()

click.echo(f"Generate the video")
finalize_video_with_music(
    writer,
    VIDEO_FILE,
    "final",
    MIDI_FILE,
    FPS,
    SOUND_FONT_FILE_BETTER,
    scene.frame_count,
    FRAME_BUFFER,
)
