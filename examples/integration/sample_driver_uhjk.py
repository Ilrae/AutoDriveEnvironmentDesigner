"""Sample keyboard driver module for AED integration testing.

Keys:
- U: throttle
- J: brake
- H: steer left
- K: steer right
- Space: hand brake
"""

CONTROL_HINT = "U throttle / H left / J brake / K right / Space hand brake / ESC exit"
DRIVER_DISPLAY_NAME = "Sample U/H/J/K keyboard driver"


def apply_keyboard_control(keys, control, pygame):
    if keys[pygame.K_u]:
        control.throttle = min(control.throttle + 0.04, 0.75)
    else:
        control.throttle = 0.0

    if keys[pygame.K_j]:
        control.brake = min(control.brake + 0.2, 1.0)
    else:
        control.brake = 0.0

    if keys[pygame.K_h]:
        control.steer = max(control.steer - 0.05, -0.7)
    elif keys[pygame.K_k]:
        control.steer = min(control.steer + 0.05, 0.7)
    else:
        control.steer *= 0.6

    control.hand_brake = bool(keys[pygame.K_SPACE])
    return control
