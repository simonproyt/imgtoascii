import main
import argparse
from PIL import Image
import threading
import time

args = argparse.Namespace()
args.width = 40
args.height = None
args.fit_terminal = False
args.aspect_ratio = 0.5
args.mode = "blocks"
args.crop = "none"
args.brightness = 1.0
args.contrast = 1.0
args.gamma = 1.0
args.edges = True
args.invert = False
args.dither = True
args.rotate = 0.0
args.flip = None
args.color = True
args.bg_color = False
args.image_path = "debug"
args.charset = "standard"

def hammer_mode():
    while True:
        args.mode = "braille" if args.mode == "blocks" else "blocks"
        time.sleep(0.001)

t = threading.Thread(target=hammer_mode, daemon=True)
t.start()

img = Image.new("RGB", (100, 100))
for _ in range(100):
   main.process_and_build_frame(img, args, False)
