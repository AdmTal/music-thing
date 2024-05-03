from PIL import Image, ImageDraw, ImageColor
import click
import imageio
import numpy as np
import random

from src.midi_stuff import (
    get_frames_where_notes_happen,
    SOUND_FONT_FILE_BETTER,
)
from src.video_stuff import finalize_video_with_music
from src.cache_stuff import get_cache_dir, cleanup_cache_dir

BG_COLOR = "#d6d1cd"
BALL_COLOR = "#e0194f"
WALL_COLOR = "#3d3f41"
PADDLE_COLOR = WALL_COLOR
HIT_SHRINK = 0.3
HIT_ANIMATION_LENGTH = 10


SCREEN_WIDTH = 1088
SCREEN_HEIGHT = 1920

BALL_START_X = SCREEN_WIDTH // 2
BALL_START_Y = SCREEN_HEIGHT // 2

BALL_SIZE = 35
PLATFORM_HEIGHT = BALL_SIZE
PLATFORM_WIDTH = BALL_SIZE // 3

BALL_SPEED = 15
FPS = 60
FRAME_BUFFER = 15


class BadSimulaiton(Exception):
    pass


def lerp(start, end, alpha):
    """Linearly interpolates between start and end."""
    return start + (end - start) * alpha


def animate_throb(n, peak=HIT_ANIMATION_LENGTH // 2, width=HIT_ANIMATION_LENGTH):
    # Calculate the cycle midpoint based on the specified width
    midpoint = width // 2
    # Calculate the current position in the cycle using modulo operation
    position_in_cycle = abs((n - 1) % width - midpoint)
    # Generate the triangular value based on distance from midpoint
    return peak - position_in_cycle


def brighten_color(hex_color, increase=20):
    # Convert hex to RGB
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)

    # Brighten the color
    r = min(255, r + increase)
    g = min(255, g + increase)
    b = min(255, b + increase)

    # Convert back to hex
    return f"#{r:02x}{g:02x}{b:02x}"


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
        self.visible = True

    def get_color(self):
        return self.color

    def hide(self):
        self.visible = False

    def render(self, image, offset_x, offset_y):
        if not self.visible:
            return
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

    def in_frame(self, visible_bounds):
        """Check if the object is within the visible bounds."""
        visible_left, visible_right, visible_top, visible_bottom = visible_bounds
        return (
            self.x_coord + self.width >= visible_left
            and self.x_coord <= visible_right
            and self.y_coord + self.height >= visible_top
            and self.y_coord <= visible_bottom
        )


class Wall(Thing):
    pass


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
    def __init__(self, x_coord, y_coord, size, color, speed, show_carve=False):
        super().__init__(x_coord, y_coord, size, size, color)
        self.x_speed = speed
        self.y_speed = speed
        self.color_fade_frames_remaining = 0
        self.size_fade_frames_remaining = 0
        self.original_color = color
        self.original_size = size
        self.current_size = size

        self._carve_top_left_corner = None
        self._carve_top_right_corner = None
        self._carve_bottom_left_corner = None
        self._carve_bottom_right_corner = None
        self._initialize_carve_square()
        self.show_carve = show_carve

    def hit(self):
        self.color_fade_frames_remaining = HIT_ANIMATION_LENGTH // 2
        self.size_fade_frames_remaining = HIT_ANIMATION_LENGTH

    def render(self, image, offset_x, offset_y):
        draw = ImageDraw.Draw(image)
        # Calculate the size reduction effect
        if self.size_fade_frames_remaining > 0:
            factor = 1 - HIT_SHRINK * (animate_throb(self.size_fade_frames_remaining) / HIT_ANIMATION_LENGTH)
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
            width=5,
        )

        if self.show_carve:
            corners = [
                self._carve_top_left_corner,
                self._carve_top_right_corner,
                self._carve_bottom_left_corner,
                self._carve_bottom_right_corner,
            ]
            # Calculate the coordinates adjusted by offset
            adjusted_corners = [(x - offset_x, y - offset_y) for x, y in corners]
            # Find the minimum and maximum x and y from the corners
            min_x = min(adjusted_corners, key=lambda t: t[0])[0]
            max_x = max(adjusted_corners, key=lambda t: t[0])[0]
            min_y = min(adjusted_corners, key=lambda t: t[1])[1]
            max_y = max(adjusted_corners, key=lambda t: t[1])[1]
            # Draw the rectangle using the top-left and bottom-right corners
            draw.rectangle([(min_x, min_y), (max_x, max_y)], outline="red", width=3)

    def get_color(self):
        if self.color_fade_frames_remaining > 0:
            faded_color = fade_color(
                brighten_color(self.original_color),
                self.original_color,
                HIT_ANIMATION_LENGTH,
                self.color_fade_frames_remaining,
            )
            self.color_fade_frames_remaining -= 1
            return faded_color
        return self.original_color

    def predict_position(self, frames=1):
        future_x = self.x_coord + self.x_speed * frames
        future_y = self.y_coord + self.y_speed * frames
        return future_x, future_y

    def move(self, platforms, walls, frame, visible_bounds):
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
                min_overlap = min(overlap_left, overlap_right, overlap_top, overlap_bottom)

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

        if hit_platform:
            self._initialize_carve_square()

        for wall in walls:
            if not wall.in_frame(visible_bounds):
                continue
            # Get the minimum and maximum x and y values from the carving corners
            ball_left = min(self._carve_top_left_corner[0], self._carve_bottom_left_corner[0])
            ball_right = max(self._carve_top_right_corner[0], self._carve_bottom_right_corner[0])
            ball_top = min(self._carve_top_left_corner[1], self._carve_top_right_corner[1])
            ball_bottom = max(self._carve_bottom_left_corner[1], self._carve_bottom_right_corner[1])

            # Check collision with wall
            if (
                ball_right >= wall.x_coord
                and ball_left <= wall.x_coord + wall.width
                and ball_bottom >= wall.y_coord
                and ball_top <= wall.y_coord + wall.height
            ):
                wall.hide()

        self._update_carve_square()

        return hit_platform

    def _initialize_carve_square(self):
        self._carve_top_left_corner = (self.x_coord, self.y_coord)
        self._carve_top_right_corner = (self.x_coord + self.width, self.y_coord)
        self._carve_bottom_left_corner = (self.x_coord, self.y_coord + self.height)
        self._carve_bottom_right_corner = (self.x_coord + self.width, self.y_coord + self.height)
        if self.x_speed > 0:
            # Moving right
            if self.y_speed > 0:
                # Moving down
                self._locked_corner = "top_left"
            else:
                # Moving up
                self._locked_corner = "bottom_left"
        else:
            # Moving left
            if self.y_speed > 0:
                # Moving down
                self._locked_corner = "top_right"
            else:
                # Moving up
                self._locked_corner = "bottom_right"

    def _update_carve_square(self):
        if self._locked_corner == "top_left":
            self._carve_bottom_right_corner = (self.x_coord + self.width + 1, self.y_coord + self.height + 1)
        elif self._locked_corner == "top_right":
            self._carve_bottom_left_corner = (self.x_coord - 1, self.y_coord + self.height + 1)
        elif self._locked_corner == "bottom_left":
            self._carve_top_right_corner = (self.x_coord + self.width + 1, self.y_coord - 1)
        elif self._locked_corner == "bottom_right":
            self._carve_top_left_corner = (self.x_coord - 1, self.y_coord - 1)


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
        self.walls = []
        self.carved = False

    def set_platforms(self, platforms):
        self._platforms_set = True
        self._platform_expectations = {platform.expected_bounce_frame(): platform for platform in platforms}
        self.platforms = platforms

    def set_walls(self, walls, carved=False):
        self.carved = carved
        self.walls = walls

    def update(self, change_colors=False):
        self.frame_count += 1

        # When the platforms were not set, we are creating them
        if not self._platforms_set and self.frame_count in self.bounce_frames:
            # A note will play on this frame, so we need to put a Platform where the ball will be next
            future_x, future_y = self.ball.predict_position(1)

            platform_orientation = self._platform_orientations.get(self.frame_count, False)
            # Horizontal orientation
            if platform_orientation:
                pwidth, pheight = PLATFORM_HEIGHT, PLATFORM_WIDTH
                new_platform_x = future_x + pwidth // 2 if self.ball.x_speed > 0 else future_x - pwidth // 2
                new_platform_y = future_y - pheight if self.ball.y_speed < 0 else future_y + pheight * 2
            # Vertical orientation
            else:
                pwidth, pheight = PLATFORM_WIDTH, PLATFORM_HEIGHT
                new_platform_x = future_x - pwidth if self.ball.x_speed < 0 else future_x + pwidth
                new_platform_y = future_y + pheight // 2 if self.ball.y_speed < 0 else future_y - pheight // 2

            new_platform = Platform(new_platform_x, new_platform_y, pwidth, pheight, PADDLE_COLOR)
            self.platforms.append(new_platform)

        hw = self.screen_width // 2
        hh = self.screen_height // 2
        visible_bounds = (
            self.offset_x - hw,
            self.offset_x + self.screen_width + hw,
            self.offset_y - hh,
            self.offset_y + self.screen_height + hh,
        )

        # Move ball and check for collisions
        # If the walls are already carved, don't pass them into Move, since we can skip the collision checks
        if self.carved:
            hit_platform = self.ball.move(self.platforms, [], self.frame_count, visible_bounds)
        else:
            hit_platform = self.ball.move(self.platforms, self.walls, self.frame_count, visible_bounds)

        self.adjust_camera()

        if change_colors and hit_platform:
            hit_platform.color = random.choice(list(ImageColor.colormap.keys()))

        if not self._platforms_set:
            return

        if not hit_platform and self.frame_count in self._platform_expectations:
            raise BadSimulaiton(f"Bounce should have happened on {self.frame_count} but did not")
        if hit_platform and self.frame_count != hit_platform.expected_bounce_frame():
            raise BadSimulaiton(f"A platform was hit on the wrong frame {self.frame_count}")

    def render(self) -> Image:
        image = Image.new(
            "RGBA",
            (
                self.screen_width,
                self.screen_height,
            ),
            BG_COLOR,
        )

        # Determine the visible area based on the current offset
        visible_bounds = (
            self.offset_x,
            self.offset_x + self.screen_width,
            self.offset_y,
            self.offset_y + self.screen_height,
        )

        # Only render the ball if it's within the visible area
        if self.ball.in_frame(visible_bounds):
            self.ball.render(image, self.offset_x, self.offset_y)

        # Only render walls and platforms if they are within the visible area
        for obj in self.walls + self.platforms:
            if obj.in_frame(visible_bounds):
                obj.render(image, self.offset_x, self.offset_y)

        return image

    def adjust_camera(self):
        edge_x = self.screen_width * 0.5
        edge_y = self.screen_height * 0.5

        # Desired offsets based on ball's position
        desired_offset_x = (
            self.ball.x_coord - edge_x if self.ball.x_speed < 0 else self.ball.x_coord - (self.screen_width - edge_x)
        )
        desired_offset_y = (
            self.ball.y_coord - edge_y if self.ball.y_speed < 0 else self.ball.y_coord - (self.screen_height - edge_y)
        )

        # Smoothing factor
        alpha = BALL_SPEED / 100

        # Update camera offsets using linear interpolation for smoother movement
        self.offset_x = lerp(self.offset_x, desired_offset_x, alpha)
        self.offset_y = lerp(self.offset_y, desired_offset_y, alpha)

    @staticmethod
    def create_squares(list_of_x_coords, list_of_y_coords):
        list_of_x_coords = sorted(list_of_x_coords)
        list_of_y_coords = sorted(list_of_y_coords)
        return [
            [x, y, x2 - x, y2 - y]
            for x, x2 in zip(list_of_x_coords[:-1], list_of_x_coords[1:])
            for y, y2 in zip(list_of_y_coords[:-1], list_of_y_coords[1:])
            if x2 - x and y2 - y
        ]

    def place_walls(self):
        list_of_x_coords = []
        list_of_y_coords = []
        for platform in self.platforms:
            list_of_x_coords += [platform.x_coord, platform.x_coord + platform.width]
            list_of_y_coords += [platform.y_coord, platform.y_coord + platform.height]

        walls = self.create_squares(list_of_x_coords, list_of_y_coords)
        for x, y, W, H in walls:
            self.walls.append(Wall(x, y, W, H, WALL_COLOR))
        # Find the minimum and maximum extents of existing walls
        minX = min(w[0] for w in walls)
        maxX = max(w[0] + w[2] for w in walls)
        minY = min(w[1] for w in walls)
        maxY = max(w[1] + w[3] for w in walls)

        WS = SCREEN_WIDTH * 2
        HS = SCREEN_HEIGHT * 2

        edge_walls = [
            Wall(minX - WS, minY - HS, WS, HS + (maxY - minY) + HS, WALL_COLOR),
            Wall(maxX, minY - HS, WS, HS + (maxY - minY) + HS, WALL_COLOR),
            Wall(minX - WS, minY - HS, 2 * WS + (maxX - minX), HS, WALL_COLOR),
            Wall(minX - WS, maxY, 2 * WS + (maxX - minX), HS, WALL_COLOR),
        ]
        for ew in edge_walls:
            self.walls.append(ew)

    def render_full_image(self):
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

        for wall in self.walls:
            if not wall.visible:
                continue
            draw.rectangle(
                [
                    wall.x_coord - min_x,
                    wall.y_coord - min_y,
                    wall.x_coord + wall.width - min_x,
                    wall.y_coord + wall.height - min_y,
                ],
                fill=wall.get_color(),
            )

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

    def run_simulation(self, midi, filename, num_frames, save_video, new_instrument, change_colors=False):
        video_file = f"{get_cache_dir()}/{filename}.mp4"
        writer = imageio.get_writer(video_file, fps=FPS)
        for _ in range(num_frames):
            self.update(change_colors)
            if save_video:
                writer.append_data(np.array(self.render()))
            progress = (self.frame_count / num_frames) * 100
            click.echo(f"\r{progress:0.0f}% ({self.frame_count} frames)", nl=False)

        if save_video:
            click.echo(f"\nGenerating the {filename} video...")
            finalize_video_with_music(
                writer,
                video_file,
                filename,
                midi,
                FPS,
                SOUND_FONT_FILE_BETTER,
                self.frame_count,
                FRAME_BUFFER,
                new_instrument,
            )


def choices_are_valid(note_frames, boolean_choice_list):
    choices = {}
    frame_list = sorted(list(note_frames))
    for idx, choice in enumerate(boolean_choice_list):
        choices[frame_list[idx]] = choice
    num_frames = max(choices.keys())

    # First - Run Choices through empty Environment to place the Platforms
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, note_frames, choices)
    for _ in range(num_frames):
        scene.update()

    # Then - Check if Scene is valid when platforms placed at start
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    platforms = scene.platforms
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball)
    scene.set_platforms(platforms)
    try:
        for _ in range(num_frames):
            scene.update()
    except BadSimulaiton:
        return False

    return True


def get_valid_platform_choices(note_frames, boolean_choice_list=[]):
    if not boolean_choice_list:
        boolean_choice_list.append(random.choice([True, False]))

    progress_string = "".join(["T" if i else "F" for i in boolean_choice_list])
    prog_length = 60
    expected = len(note_frames)
    actual = len(boolean_choice_list)
    progress = int((actual / expected) * 100)
    trunc = f"({len(progress_string)-prog_length}):" if len(progress_string) >= prog_length else ""
    click.echo(f"\rProgress: {progress}%\t{trunc}{progress_string[-(prog_length-len(trunc)):]}", nl=False)
    if len(boolean_choice_list) == len(note_frames):
        if choices_are_valid(note_frames, boolean_choice_list):
            return boolean_choice_list
        else:
            return None

    # Check if the current partial string is valid
    if not choices_are_valid(note_frames, boolean_choice_list):
        # Prune the search tree here
        return None

    # There is opportunity here to add spice and bias the search to produce more interesting scenes
    next_choices = [True, False]
    if random.choice([True, False]):
        next_choices = next_choices[::-1]
    for rand_choice in next_choices:
        result = get_valid_platform_choices(
            note_frames,
            boolean_choice_list + [rand_choice],
        )
        if result is not None:
            return result

    return None


def parse_isolate_tracks(ctx, param, value):
    if not value:
        return
    try:
        return [int(track.strip()) for track in value.split(",")]
    except Exception as e:
        raise click.BadParameter("Track numbers must be a comma-delimited list of integers.")


@click.command()
@click.option(
    "--midi",
    required=True,
    default="wii-music.mid",
    type=click.Path(exists=True),
    help="Path to a MIDI file.",
)
@click.option(
    "--max_frames",
    default=None,
    type=int,
    help="Max number of frames to generate",
)
@click.option(
    "--new_instrument",
    default=None,
    type=int,
    help="General Midi program number for desired instrument https://en.wikipedia.org/wiki/General_MIDI",
)
@click.option(
    "--show_carve",
    default=False,
    is_flag=True,
    help="Generate a Carving Video",
)
@click.option(
    "--show_platform",
    default=False,
    is_flag=True,
    help="Generate a Platform placement Video",
)
@click.option(
    "--isolate_tracks",
    default=None,
    type=str,
    help="Comma delimited list of track numbers to animate the ball to",
    callback=parse_isolate_tracks,
)
def main(midi, max_frames, new_instrument, show_carve, show_platform, isolate_tracks):
    # Inspect the MIDI file to see which video frames line up with the music
    note_frames = get_frames_where_notes_happen(midi, FPS, FRAME_BUFFER, isolate_tracks)
    num_frames = max(note_frames) if max_frames is None else max_frames
    note_frames = {i for i in note_frames if i <= num_frames}
    click.echo(f"{midi} requires {num_frames} frames")

    # Run the backtracking alg to figure out where to place the platforms
    click.echo(f"Searching for valid placement for {len(note_frames)} platforms...")
    boolean_choice_list = get_valid_platform_choices(note_frames)
    if not boolean_choice_list:
        click.echo("\nCould not figure out platforms :(")
        click.echo("\nTry changing ball and platform size, and speed")
        exit(0)

    # Convert `boolean_choice_list` to `choices`
    # Choices is DICT, KEY=FRAME NUMBER, VAL=Bool for if the platform hit on this frame is Horizontal or Vertical
    choices = {}
    frame_list = sorted(list(note_frames))
    for idx, choice in enumerate(boolean_choice_list):
        choices[frame_list[idx]] = choice
    num_frames = max(choices.keys())

    click.echo(f"\nRunning simulation to generate Platforms...")
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, note_frames, choices)
    scene.run_simulation(midi, "platform-scene", num_frames, show_platform, new_instrument)

    # After the platforms are placed in the first simulation, place the walls
    scene.place_walls()
    walls = scene.walls

    # Run the next simulation with the platforms and walls in place, and carve the walls
    click.echo(f"\nRunning the simulation again to carve the walls ({len(walls)} walls)...")
    platforms = scene.platforms
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED, show_carve=show_carve)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, note_frames)
    scene.set_platforms(platforms)
    scene.set_walls(walls)
    scene.run_simulation(midi, "carve-scene", num_frames, show_carve, new_instrument)

    # Give the user something to look at while the video generates
    # scene.render_full_image().show()

    # Run the final simulation with the platforms and carved walls in place
    carved_walls = scene.walls
    click.echo(f"\nRunning the simulation again to make the video...")
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, note_frames)
    scene.set_platforms(platforms)
    scene.set_walls(carved_walls, carved=True)
    scene.run_simulation(midi, "scene", num_frames, True, new_instrument, True)

    cleanup_cache_dir(get_cache_dir())


if __name__ == "__main__":
    main()
