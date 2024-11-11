import click
from moviepy.editor import VideoFileClip


@click.command()
@click.argument("video_path")
def get_video_properties(video_path):
    """Process the video file to extract and print its properties."""
    try:
        # Load the video file
        clip = VideoFileClip(video_path)
        # Retrieve width, height, and duration of the video
        width = clip.size[0]
        height = clip.size[1]
        duration = clip.duration

        # Print the results
        print(f"Screen Width: {width} pixels")
        print(f"Screen Height: {height} pixels")
        print(f"Duration: {duration} seconds")
        print(f"FPS: {clip.fps}")


    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        # Ensure the clip is closed in case of success or failure
        if "clip" in locals():
            clip.close()


if __name__ == "__main__":
    get_video_properties()
