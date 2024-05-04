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
