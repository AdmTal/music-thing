from ursina import *


app = Ursina()

SCREEN_WIDTH = 880
SCREEN_HEIGHT = 1536

window.size = (SCREEN_WIDTH, SCREEN_HEIGHT)

# Main scene setup
camera.position = (0, 0, -20)


def px_to_unit(px):
    return px / 100


# Create a cube with a basic shader in the main scene
cube = Entity(
    model="cube",
    shader=Shader("shaders/basic_lighting"),
    scale=(px_to_unit(100), px_to_unit, 5),
    color=color.white,
    position=(0, 0, 20),
)

camera.position = (0, 0, -20)
PointLight(position=(0, 0, -20), color=color.white, eternal=True)
AmbientLight(color=(0.5, 0.5, 0.5, 1), eternal=True)


def update():
    move_speed = 0.1
    # Handle movement
    move = False
    if held_keys["left arrow"]:
        move = True
        cube.x -= move_speed
    if held_keys["right arrow"]:
        move = True
        cube.x += move_speed
    if held_keys["up arrow"]:
        move = True
        cube.y += move_speed
    if held_keys["down arrow"]:
        move = True
        cube.y -= move_speed
    if held_keys["w"]:
        move = True
        cube.z += move_speed
    if held_keys["s"]:
        move = True
        cube.z -= move_speed

    # Print current position of the cube
    if move:
        print(f"Cube position: {cube.position}")

    # Save screenshot if 's' key is held, not ideal for 's' since it controls z-axis, consider changing the key
    if held_keys["p"]:  # Changed to 'p' to avoid conflict with z-axis control
        base.win.saveScreenshot("screenshot.jpg")


app.run()
