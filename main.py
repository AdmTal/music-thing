from PIL import Image, ImageDraw
import imageio
import numpy as np
import random

from src.midi_stuff import (
    get_frames_where_notes_happen,
    SOUND_FONT_FILE_BETTER,
)
from src.video_stuff import finalize_video_with_music
from src.cache_stuff import get_cache_dir


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
    pass


class Ball(Thing):
    def __init__(self, x_coord, y_coord, size, color, speed):
        super().__init__(x_coord, y_coord, size, size, color)
        self.x_speed = speed
        self.y_speed = speed

    def predict_position(self, frames):
        future_x = self.x_coord + self.x_speed * frames
        future_y = self.y_coord + self.y_speed * frames
        return future_x, future_y

    def move(self, platforms):
        next_x = self.x_coord + self.x_speed
        next_y = self.y_coord + self.y_speed
        for platform in platforms:
            ball_left = next_x
            ball_right = next_x + self.width
            ball_top = next_y
            ball_bottom = next_y + self.height
            plat_left = platform.x_coord
            plat_right = platform.x_coord + platform.width
            plat_top = platform.y_coord
            plat_bottom = platform.y_coord + platform.height
            if all(
                [
                    ball_right > plat_left,
                    ball_left < plat_right,
                    ball_bottom > plat_top,
                    ball_top < plat_bottom,
                ]
            ):
                overlap_left = ball_right - plat_left
                overlap_right = plat_right - ball_left
                overlap_top = ball_bottom - plat_top
                overlap_bottom = plat_bottom - ball_top
                min_overlap = min(
                    overlap_left, overlap_right, overlap_top, overlap_bottom
                )
                if min_overlap == overlap_left:
                    self.x_speed = -abs(self.x_speed)
                    self.x_coord = plat_left - self.width
                elif min_overlap == overlap_right:
                    self.x_speed = abs(self.x_speed)
                    self.x_coord = plat_right
                elif min_overlap == overlap_top:
                    self.y_speed = -abs(self.y_speed)
                    self.y_coord = plat_top - self.height
                elif min_overlap == overlap_bottom:
                    self.y_speed = abs(self.y_speed)
                    self.y_coord = plat_bottom
                break
        self.x_coord += self.x_speed
        self.y_coord += self.y_speed


class Scene:
    def __init__(self, screen_width, screen_height, ball, bounce_frames=[]):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.ball = ball
        self.platforms = []
        self.bounce_frames = set(bounce_frames)
        self.frame_count = 0
        self.offset_x = 0
        self.offset_y = 0
        self._platforms_set = False

    def set_platforms(self, platforms):
        self._platforms_set = True
        self.platforms = platforms

    def update(self):
        self.frame_count += 1

        # Add platform in advance if it's a bounce frame
        if not self._platforms_set and self.frame_count in self.bounce_frames:
            # Get the ball's next frame position
            future_x, future_y = self.ball.predict_position(1)

            # Randomly choose orientation
            PWIDTH = ball.width // 2
            PHEIGHT = ball.height * 1.5
            if random.choice([True, False, False, False]):
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
        self.ball.move(self.platforms)
        self.adjust_camera()

    def render(self) -> Image:
        image = Image.new("RGB", (self.screen_width, self.screen_height), "white")
        self.ball.render(image, self.offset_x, self.offset_y)
        for platform in self.platforms:
            platform.render(image, self.offset_x, self.offset_y)
        return image

    def adjust_camera(self):
        edge_x = self.screen_width * 0.2
        edge_y = self.screen_height * 0.2
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
BALL_SIZE = 50
BALL_COLOR = "red"
BALL_SPEED = 25
MIDI_FILE = "wii-music.mid"
FPS = 60
FRAME_BUFFER = 15
frames_where_notes_happen = get_frames_where_notes_happen(MIDI_FILE, FPS, FRAME_BUFFER)
ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, frames_where_notes_happen)

NUM_FRAMES = 500

# Run simulation to place the Platforms
for _ in range(NUM_FRAMES):
    scene.update()

# Run the simulation again - with the platforms already in place
# and record the video
platforms = scene.platforms
ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball)
scene.set_platforms(platforms)

VIDEO_FILE = f"{get_cache_dir()}/scene.mp4"
writer = imageio.get_writer(VIDEO_FILE, fps=FPS)
for _ in range(NUM_FRAMES):
    scene.update()
    image = scene.render()
    writer.append_data(np.array(image))

writer.close()
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
