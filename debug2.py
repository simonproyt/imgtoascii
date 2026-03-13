import main
import argparse
from PIL import Image

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

img = Image.new("RGB", (100, 100))
main.process_and_build_frame(img, args, False)
