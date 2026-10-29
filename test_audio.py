"""Manual smoke script for local pygame audio playback."""

import os
import time


def main() -> None:
    import pygame

    sample = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio", "loudmouth-test.mp3")
    pygame.mixer.init()
    time.sleep(1.0)
    pygame.mixer.music.load(sample)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        time.sleep(0.1)

    pygame.mixer.quit()
    print("Done")


if __name__ == "__main__":
    main()
