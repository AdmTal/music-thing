def lerp(start, end, alpha):
    """Linearly interpolates between start and end."""
    return start + (end - start) * alpha


def animate_throb(n, peak, width):
    # Calculate the cycle midpoint based on the specified width
    midpoint = width // 2
    # Calculate the current position in the cycle using modulo operation
    position_in_cycle = abs((n - 1) % width - midpoint)
    # Generate the triangular value based on distance from midpoint
    return peak - position_in_cycle
