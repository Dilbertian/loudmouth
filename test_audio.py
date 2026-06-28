import pygame
import time

pygame.mixer.init()
time.sleep(1.0)
pygame.mixer.music.load("audio/test_turbo.mp3")
pygame.mixer.music.play()

# Wait for it to finish
while pygame.mixer.music.get_busy():
    time.sleep(0.1)

print("Done")
