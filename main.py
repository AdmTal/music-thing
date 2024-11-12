from PIL import Image, ImageDraw
import click
import imageio
import numpy as np
import random
import math

from src.midi_stuff import (
    get_frames_where_notes_happen,
    SOUND_FONT_FILE_BETTER,
)
from src.video_stuff import finalize_video_with_music
from src.cache_stuff import get_cache_dir, cleanup_cache_dir
from src.animation_stuff import lerp

# Define main colors for the game elements
BG_COLOR = "#b1afaf"
BALL_COLOR = "#2c2c2c"
BALL_FILL = "#ff6347"
WALL_COLOR = "#666666"
PADDLE_COLOR = WALL_COLOR

RAND_COLORS = [
    "#42a5f5",  # Light Blue
    "#26a69a",  # Teal
    "#ef5350",  # Soft Red
]

PARTICLE_COLORS = [
    "#ffeb3b",  # Vivid Yellow
    "#ff9800",  # Orange
    "#cddc39",  # Lime Green
]


SCREEN_WIDTH = int(576 * 1.5)
SCREEN_HEIGHT = int(1024 * 1.5)

BALL_START_X = SCREEN_WIDTH // 2
BALL_START_Y = SCREEN_HEIGHT // 2

BALL_SIZE = 35
PLATFORM_HEIGHT = BALL_SIZE
PLATFORM_WIDTH = BALL_SIZE // 3

A_STRETCH = BALL_SIZE // 3
B_STRETCH = BALL_SIZE // 5
C_STRETCH = 10

BALL_SPEED = 9
FPS = 60
FRAME_BUFFER = 15
END_VIDEO_FREEZE_SECONDS = 3

BUMP_DIST = math.floor(BALL_SPEED * 1.5)

STRATEGY_RANDOM = "random"
STRATEGY_ALTERNATE = "alternate"


class BadSimulation(Exception):
    pass


def bump_pattern(n, skip=3):
    # Generate the ascending sequence with the specified step
    seq = list(range(0, abs(n) + 1, skip)) + list(range(abs(n) - skip, -1, -skip))
    # Apply the negative sign if n is negative
    return [x if n >= 0 else -x for x in seq]


class Thing:
    def __init__(self, x_coord, y_coord, width, height, color, fill_color=None):
        self.x_coord = x_coord
        self.y_coord = y_coord
        self.width = width
        self.height = height
        self.color = color
        self.visible = True
        self.fill_color = fill_color

        self._x_bump = []
        self._y_bump = []

    def get_color(self):
        return self.color

    def get_fill_color(self):
        return self.fill_color

    def hide(self):
        self.visible = False

    def bump_left(self, bump_dist=BUMP_DIST):
        self._x_bump = bump_pattern(-bump_dist)

    def bump_right(self, bump_dist=BUMP_DIST):
        self._x_bump = bump_pattern(bump_dist)

    def bump_up(self, bump_dist=BUMP_DIST):
        self._y_bump = bump_pattern(-bump_dist)

    def bump_down(self, bump_dist=BUMP_DIST):
        self._y_bump = bump_pattern(bump_dist)

    def render(self, image, offset_x, offset_y):
        if not self.visible:
            return
        draw = ImageDraw.Draw(image)
        # Calculate the adjusted coordinates with bump included

        x_bump = 0
        y_bump = 0
        if self._x_bump:
            x_bump = self._x_bump.pop(0)
        if self._y_bump:
            y_bump = self._y_bump.pop(0)

        x0 = max(self.x_coord - offset_x + x_bump, 0)
        y0 = max(self.y_coord - offset_y + y_bump, 0)
        x1 = min(self.x_coord + self.width - offset_x + x_bump, SCREEN_WIDTH)
        y1 = min(self.y_coord + self.height - offset_y + y_bump, SCREEN_HEIGHT)

        # Draw the rectangle within the screen boundaries
        if x1 > x0 and y1 > y0:  # Ensuring x1 and y1 are greater than x0 and y0 respectively
            draw.rectangle(
                [x0, y0, x1, y1],
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


class Particle:
    def __init__(self, x, y, vx, vy, color, lifespan, size):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.lifespan = lifespan
        self.original_lifespan = lifespan  # Storing the original lifespan for reference
        self.size = size
        self.drag = random.uniform(0.85, 0.95)
        self.shrinking_start = random.randint(
            int(0.7 * lifespan), int(0.9 * lifespan)
        )  # Start shrinking randomly between 70% to 90% of lifespan

    def update(self):
        """Update the particle's position, reduce its lifespan, apply drag, and handle shrinking."""
        self.vx *= self.drag
        self.vy *= self.drag

        self.x += self.vx
        self.y += self.vy
        self.lifespan -= 1

        # Check if it's time to start shrinking the particle
        if self.lifespan <= self.shrinking_start:
            self.size -= self.size * 0.1  # Reduce size by 10% of its current size each frame
            if self.size < 1:
                self.size = 0  # Ensure size doesn't go negative

    def render(self, image, offset_x, offset_y):
        """Render the particle if it's still alive and has a size greater than zero."""
        if self.lifespan > 0 and self.size > 0:
            draw = ImageDraw.Draw(image)
            radius = self.size
            draw.ellipse(
                [
                    (self.x - radius - offset_x, self.y - radius - offset_y),
                    (self.x + radius - offset_x, self.y + radius - offset_y),
                ],
                fill=self.color,
            )


class Platform(Thing):
    def __init__(self, x_coord, y_coord, width, height, color):
        super().__init__(x_coord, y_coord, width, height, color)
        self._expected_bounce_frame = None
        self.particles = []

    def emit_particles(self, direction):
        """Emit particles in the opposite direction of the hit."""
        num_particles = 15
        particle_speed = BALL_SPEED / 1.5
        particle_lifespan = 20

        for _ in range(num_particles):
            angle = random.uniform(0, 2 * math.pi)  # Generate a random angle
            speed_modifier = random.uniform(0.5, 1.5)  # Randomize the speed for burstiness

            # Maintain the direction logic but add randomness to the speed
            if "right" in direction:
                vx = -particle_speed * speed_modifier * abs(math.cos(angle))  # Emit left
            elif "left" in direction:
                vx = particle_speed * speed_modifier * abs(math.cos(angle))  # Emit right
            else:
                # Randomize vx for top and bottom to spread particles horizontally
                vx = particle_speed * speed_modifier * math.cos(angle) * random.choice([-1, 1])

            if "top" in direction:
                vy = particle_speed * speed_modifier * abs(math.sin(angle))  # Emit downward
            elif "bottom" in direction:
                vy = -particle_speed * speed_modifier * abs(math.sin(angle))  # Emit upward
            else:
                # Randomize vy for left and right to spread particles vertically
                vy = particle_speed * speed_modifier * math.sin(angle) * random.choice([-1, 1])

            particle_size = random.uniform(3, 6)  # Random size between 1 and 3 pixels
            color = random.choice(PARTICLE_COLORS)  # Choose a random bright color
            self.particles.append(
                Particle(
                    self.x_coord + self.width // 2,
                    self.y_coord + self.height // 2,
                    vx,
                    vy,
                    color,
                    particle_lifespan,
                    particle_size,
                ),
            )

    def update_particles(self):
        """Update all particles and remove the dead ones."""
        for particle in self.particles[:]:
            particle.update()
            if particle.lifespan <= 0:
                self.particles.remove(particle)

    def render(self, image, offset_x, offset_y):
        for particle in self.particles:
            particle.render(image, offset_x, offset_y)
        super().render(image, offset_x, offset_y)

    def set_expected_bounce_frame(self, frame):
        if self._expected_bounce_frame:
            return
        self._expected_bounce_frame = frame

    def expected_bounce_frame(self):
        return self._expected_bounce_frame


class Ball(Thing):
    def __init__(self, x_coord, y_coord, size, color, speed, show_carve=False, fill_color=None):
        super().__init__(x_coord, y_coord, size, size, color, fill_color)
        self.x_speed = speed
        self.y_speed = speed
        self.original_color = color
        self.size = size

        self._carve_top_left_corner = None
        self._carve_top_right_corner = None
        self._carve_bottom_left_corner = None
        self._carve_bottom_right_corner = None
        self._initialize_carve_square()
        self.show_carve = show_carve
        self._box_modifiers = [0, 0, 0, 0, 0, 0]  # L, T, R, B, X, Y

    def hit(self, direction):
        # If hit on the SIDES, will get skinny + tall
        tilt = (A_STRETCH // 2) + C_STRETCH
        if direction == "top":
            self._box_modifiers = [-A_STRETCH, B_STRETCH, A_STRETCH, -B_STRETCH, 0, -tilt]
        if direction == "bottom":
            self._box_modifiers = [-A_STRETCH, B_STRETCH, A_STRETCH, -B_STRETCH, 0, tilt]
        if direction in "left":
            self._box_modifiers = [B_STRETCH, -A_STRETCH, -B_STRETCH, A_STRETCH, -tilt, 0]
        if direction in "right":
            self._box_modifiers = [B_STRETCH, -A_STRETCH, -B_STRETCH, A_STRETCH, tilt, 0]

    @staticmethod
    def fix_box_modifiers(x, y=1):
        return max(0, x - y) if x > 0 else min(0, x + y)

    def tick_fix_box_modifiers(self):
        fix_speed = 1.5
        self._box_modifiers = [
            self.fix_box_modifiers(self._box_modifiers[0], fix_speed),
            self.fix_box_modifiers(self._box_modifiers[1], fix_speed),
            self.fix_box_modifiers(self._box_modifiers[2], fix_speed),
            self.fix_box_modifiers(self._box_modifiers[3], fix_speed),
            self.fix_box_modifiers(self._box_modifiers[4], fix_speed),
            self.fix_box_modifiers(self._box_modifiers[5], fix_speed),
        ]

    def render(self, image, offset_x, offset_y):
        ld, rd, td, bd, xd, yd = self._box_modifiers
        draw = ImageDraw.Draw(image)
        left = self.x_coord - offset_x + xd
        right = self.x_coord - offset_x + self.size + xd
        top = self.y_coord - offset_y + yd
        bottom = self.y_coord - offset_y + self.size + yd

        draw.rectangle(
            [left + ld, top + td, right + rd, bottom + bd],
            outline=self.get_color(),
            fill=self.get_fill_color(),
            width=2,
        )

        self.tick_fix_box_modifiers()

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
            draw.rectangle([(min_x, min_y), (max_x, max_y)], outline="red", width=1)

    def get_color(self):
        return self.original_color

    def predict_position(self, frames=1):
        future_x = self.x_coord + self.x_speed * frames
        future_y = self.y_coord + self.y_speed * frames
        return future_x, future_y

    def move(self, platforms, walls, frame, visible_bounds, bump_paddles=False):
        # Calculate potential next position of the ball
        next_x = self.x_coord
        next_y = self.y_coord
        hit_platform = None
        is_carving = len(walls) > 0

        # Check each platform for a possible collision
        for platform in platforms:
            if not platform.in_frame(visible_bounds):
                continue
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
                ball_hit_on = ""
                if min_overlap == overlap_left:
                    # Reverse horizontal speed
                    self.x_speed = -abs(self.x_speed)
                    # Reposition to the left of the platform
                    self.x_coord = plat_left - self.width
                    if bump_paddles:
                        platform.bump_right()
                        ball_hit_on = "right"
                        platform.emit_particles("left")
                elif min_overlap == overlap_right:
                    # Maintain horizontal speed
                    self.x_speed = abs(self.x_speed)
                    # Reposition to the right of the platform
                    self.x_coord = plat_right
                    if bump_paddles:
                        platform.bump_left()
                        ball_hit_on = "left"
                        platform.emit_particles("right")
                elif min_overlap == overlap_top:
                    # Reverse vertical speed
                    self.y_speed = -abs(self.y_speed)
                    # Reposition above the platform
                    self.y_coord = plat_top - self.height
                    if bump_paddles:
                        platform.bump_down()
                        ball_hit_on = "bottom"
                        platform.emit_particles("top")
                elif min_overlap == overlap_bottom:
                    # Maintain vertical speed
                    self.y_speed = abs(self.y_speed)
                    # Reposition below the platform
                    self.y_coord = plat_bottom
                    if bump_paddles:
                        platform.bump_up()
                        ball_hit_on = "top"
                        platform.emit_particles("bottom")

                platform.set_expected_bounce_frame(frame)
                hit_platform = platform
                self.hit(ball_hit_on)
                break

        # Update the ball's position with the potentially new speed
        self.x_coord += self.x_speed
        self.y_coord += self.y_speed

        if is_carving:
            self._update_carve_square()

        for wall in walls:
            if not wall.in_frame(visible_bounds):
                continue
            # Get the minimum and maximum x and y values from the carving corners
            buffer = PLATFORM_WIDTH
            ball_left = min(self._carve_top_left_corner[0], self._carve_bottom_left_corner[0]) + buffer
            ball_right = max(self._carve_top_right_corner[0], self._carve_bottom_right_corner[0]) - buffer
            ball_top = min(self._carve_top_left_corner[1], self._carve_top_right_corner[1]) + buffer
            ball_bottom = max(self._carve_bottom_left_corner[1], self._carve_bottom_right_corner[1]) - buffer

            # Check collision with wall
            if (
                ball_right >= wall.x_coord
                and ball_left <= wall.x_coord + wall.width
                and ball_bottom >= wall.y_coord
                and ball_top <= wall.y_coord + wall.height
            ):
                wall.hide()

        if is_carving and hit_platform:
            self._initialize_carve_square()

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
            self._carve_bottom_right_corner = (self.x_coord + self.width, self.y_coord + self.height)
        elif self._locked_corner == "top_right":
            self._carve_bottom_left_corner = (self.x_coord, self.y_coord + self.height)
        elif self._locked_corner == "bottom_left":
            self._carve_top_right_corner = (self.x_coord + self.width, self.y_coord)
        elif self._locked_corner == "bottom_right":
            self._carve_top_left_corner = (self.x_coord, self.y_coord)


class Scene:
    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        ball: Ball,
        bounce_frames: set = None,
        platform_orientations: dict = None,
    ):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.ball = ball
        self.platforms = []
        self.bounce_frames = bounce_frames
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

    def update(self, change_colors=False, bump_paddles=False):
        self.frame_count += 1

        # When the platforms were not set, we are creating them
        if not self._platforms_set and self.frame_count in self.bounce_frames:
            # A note will play on this frame, so we need to put a Platform where the ball will be next
            future_x, future_y = self.ball.predict_position(2)

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

        visible_bounds = (
            self.offset_x - self.screen_width,
            self.offset_x + (2 * self.screen_width),
            self.offset_y - self.screen_height,
            self.offset_y + (2 * self.screen_height),
        )

        # Move ball and check for collisions
        # If the walls are already carved, don't pass them into Move, since we can skip the collision checks
        if self.carved:
            hit_platform = self.ball.move(self.platforms, [], self.frame_count, visible_bounds, bump_paddles)
        else:
            hit_platform = self.ball.move(self.platforms, self.walls, self.frame_count, visible_bounds)

        self.adjust_camera()

        for platform in self.platforms:
            platform.update_particles()

        if change_colors and hit_platform:
            hit_platform.color = random.choice(RAND_COLORS)

        if not self._platforms_set:
            return

        if not hit_platform and self.frame_count in self._platform_expectations:
            raise BadSimulation(f"Bounce should have happened on {self.frame_count} but did not")
        if hit_platform and self.frame_count != hit_platform.expected_bounce_frame():
            raise BadSimulation(f"A platform was hit on the wrong frame {self.frame_count}")

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

        # Only render walls and platforms if they are within the visible area
        for obj in self.walls + self.platforms:
            if obj.in_frame(visible_bounds):
                obj.render(image, self.offset_x, self.offset_y)

        # Only render the ball if it's within the visible area
        if self.ball.in_frame(visible_bounds):
            self.ball.render(image, self.offset_x, self.offset_y)

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
        alpha = BALL_SPEED / 150

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

        self.ball.render(image, min_x, min_y)

        return image

    def run_simulation(
        self,
        midi,
        filename,
        num_frames,
        save_video,
        new_instrument,
        isolated_tracks,
        change_colors=False,
        sustain_pedal=False,
        zoomed_out=False,
        bump_paddles=False,
    ):
        video_file = f"{get_cache_dir()}/{filename}.mp4"
        writer = imageio.get_writer(video_file, fps=FPS)

        for _ in range(num_frames):
            self.update(change_colors, bump_paddles=bump_paddles)
            if save_video:
                if zoomed_out:
                    writer.append_data(np.array(self.render_full_image()))
                else:
                    writer.append_data(np.array(self.render()))
            progress = (self.frame_count / num_frames) * 100
            click.echo(f"\r{progress:0.0f}% ({self.frame_count} frames)", nl=False)

        if save_video:
            # "Pause" for a few seconds
            for _ in range(FPS * END_VIDEO_FREEZE_SECONDS):
                if zoomed_out:
                    writer.append_data(np.array(self.render_full_image()))
                else:
                    writer.append_data(np.array(self.render()))

            click.echo(f"\nGenerating the {filename} video...")
            vid_name = finalize_video_with_music(
                writer,
                video_file,
                filename,
                midi,
                FPS,
                SOUND_FONT_FILE_BETTER,
                self.frame_count,
                FRAME_BUFFER,
                new_instrument,
                isolated_tracks,
                sustain_pedal,
            )
            # self.render_full_image().save(f"{vid_name.split('.mp4')[0]}.png")


def choices_are_valid(note_frames, boolean_choice_list):
    choices = {}
    frame_list = sorted(list(note_frames))
    for idx, choice in enumerate(boolean_choice_list):
        choices[frame_list[idx]] = choice
    num_frames = max(choices.keys())

    # First - Run Choices through empty Environment to place the Platforms
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED, show_carve=False, fill_color=BALL_FILL)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, note_frames, choices)
    for _ in range(num_frames):
        scene.update()

    # Then - Check if Scene is valid when platforms placed at start
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED, show_carve=False, fill_color=BALL_FILL)
    platforms = scene.platforms
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball)
    scene.set_platforms(platforms)
    try:
        for _ in range(num_frames):
            scene.update()
    except BadSimulation:
        return False

    return True


def get_valid_platform_choices(strategy, note_frames: set, boolean_choice_list: list = []):
    if not boolean_choice_list:
        boolean_choice_list.append(random.choice([True, False]))

    progress_string = "".join(["─" if i else "|" for i in boolean_choice_list])
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

    if strategy == STRATEGY_ALTERNATE:
        if boolean_choice_list[-1]:
            next_choices = [False, True]
        else:
            next_choices = [True, False]
    elif strategy == STRATEGY_RANDOM:
        next_choices = [True, False]
        if random.choice([True, False]):
            next_choices = next_choices[::-1]

    for rand_choice in next_choices:
        result = get_valid_platform_choices(
            strategy,
            note_frames,
            boolean_choice_list + [rand_choice],
        )
        if result is not None:
            return result

    return None


def parse_animate_tracks(ctx, param, value):
    if not value:
        return
    try:
        return [int(track.strip()) for track in value.split(",")]
    except Exception as e:
        raise click.BadParameter("Track numbers must be a comma-delimited list of integers.")


@click.command()
@click.option(
    "--midi",
    "-m",
    required=True,
    default="wii-music.mid",
    type=click.Path(exists=True),
    help="Path to a MIDI file.",
)
@click.option(
    "--max_frames",
    "-mf",
    default=None,
    type=int,
    help="Max number of frames to generate",
)
@click.option(
    "--new_instrument",
    "-ni",
    default=None,
    type=int,
    help="General Midi program number for desired instrument https://en.wikipedia.org/wiki/General_MIDI",
)
@click.option(
    "--animate_tracks",
    "-at",
    default=None,
    type=str,
    help="Comma delimited list of track numbers to animate the ball to",
    callback=parse_animate_tracks,
)
@click.option(
    "--isolate",
    "-i",
    default=False,
    is_flag=True,
    help="Mute all non animated tracks",
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
    "--sustain_pedal",
    "-sp",
    default=False,
    is_flag=True,
    help="You know, like on a Piano - let the notes drag out - make a meal of it",
)
@click.option(
    "--zoomed_out",
    "-zo",
    default=False,
    is_flag=True,
    help="Show the entire scene in the video, no zoom",
)
@click.option(
    "--strategy",
    "-s",
    default=STRATEGY_RANDOM,
    help='"random" or "alternate" for platform orientation placement',
)
def main(
    midi,
    max_frames,
    new_instrument,
    show_carve,
    show_platform,
    animate_tracks,
    isolate,
    sustain_pedal,
    zoomed_out,
    strategy,
):
    song_name = midi.split("/")[-1].split(".mid")[0]
    # Inspect the MIDI file to see which video frames line up with the music
    note_frames = get_frames_where_notes_happen(midi, FPS, FRAME_BUFFER, animate_tracks)
    num_frames = max(note_frames) if max_frames is None else max_frames
    note_frames = {i for i in note_frames if i <= num_frames}
    click.echo(f"{midi} requires {num_frames} frames")

    isolated_tracks = None
    if isolate:
        isolated_tracks = animate_tracks

    # Run the backtracking alg to figure out where to place the platforms
    num_platforms = len(note_frames)
    click.echo(f"Searching for valid placement for {num_platforms} platforms...")
    boolean_choice_list = get_valid_platform_choices(strategy, note_frames)
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

    click.echo(f"\nRunning simulation to place {num_platforms} platforms...")
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED, show_carve=False, fill_color=BALL_FILL)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, note_frames, choices)
    scene.run_simulation(midi, f"{song_name}-platforms", num_frames, show_platform, new_instrument, isolated_tracks)

    # After the platforms are placed in the first simulation, place the walls
    scene.place_walls()
    walls = scene.walls

    # Run the next simulation with the platforms and walls in place, and carve the walls
    click.echo(f"\nRunning the simulation again to carve {len(walls)} walls)...")
    platforms = scene.platforms
    ball = Ball(
        BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED, show_carve=show_carve, fill_color=BALL_FILL
    )
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, note_frames)
    scene.set_platforms(platforms)
    scene.set_walls(walls)
    scene.run_simulation(midi, f"{song_name}", num_frames, show_carve, new_instrument, isolated_tracks)

    # Run the final simulation with the platforms and carved walls in place
    carved_walls = scene.walls
    click.echo(f"\nRunning the simulation again to make the video...")
    ball = Ball(BALL_START_X, BALL_START_Y, BALL_SIZE, BALL_COLOR, BALL_SPEED, show_carve=False, fill_color=BALL_FILL)
    scene = Scene(SCREEN_WIDTH, SCREEN_HEIGHT, ball, note_frames)
    scene.set_platforms(platforms)
    scene.set_walls(carved_walls, carved=True)
    scene.run_simulation(
        midi,
        f"{song_name}",
        num_frames,
        True,
        new_instrument,
        isolated_tracks,
        change_colors=True,
        bump_paddles=True,
        sustain_pedal=sustain_pedal,
        zoomed_out=zoomed_out,
    )

    cleanup_cache_dir()


if __name__ == "__main__":
    main()
