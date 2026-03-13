# imgtoascii

Convert images into ASCII art in the terminal or write the result to a file.

## Usage

```bash
python main.py <image_path> [options]
```

## Options

- `--width` / `-width`: Set the output width in characters.
- `--height` / `-height`: Set the output height in characters.
- `width=<n>` / `height=<n>`: Alternative width and height syntax.
- `--color` / `-color`: Render ANSI truecolor ASCII output.
- `--bg-color` / `-bg-color`: Render colors to the terminal background (implies `--color`).
- `--fit-terminal` / `-fit-terminal`: Scale the output to fit the current terminal.
- `--aspect-ratio` / `-aspect-ratio`: Character height-to-width correction factor. Default: `0.5`.
- `--invert` / `-invert`: Reverse the brightness-to-character mapping.
- `--edges` / `-edges`: Apply edge-detection filter for line-art styles.
- `--filter` / `-filter`: Apply video filters (`none`, `pixelate`, `matrix`, `bg-remove`, `blur`, `sharpen`, `emboss`).
- `--charset` / `-charset`: Choose a preset: `standard`, `dense`, `simple`, or `classic`.
- `--mode` / `-mode`: Choose `ascii` (default), `blocks`, or `braille` rendering.
- `--html` / `-html`: Export the result as an HTML document.
- `--brightness` / `-brightness`: Adjust brightness. Default: `1.0`.
- `--contrast` / `-contrast`: Adjust contrast. Default: `1.0`.
- `--gamma` / `-gamma`: Adjust gamma. Default: `1.0`.
- `--dither` / `-dither`: Apply Floyd-Steinberg dithering for smoother gradients.
- `--rotate` / `-rotate`: Rotate image by degrees. Default: `0.0`.
- `--flip` / `-flip`: Flip image `horizontal` or `vertical`.
- `--crop` / `-crop`: Choose `none`, `cover`, or `contain` resizing behavior.
- `--output` / `-output`: Write the result to a file instead of stdout.
- `--webcam` / `-webcam`: Read live feed from webcam and output as animated ASCII art.
- `--virtual-webcam` / `-virtual-webcam`: Create a virtual camera device broadcasting the ASCII art to other apps.
- `--virtual-cam-width` / `-virtual-cam-width`: Character width for the high-res virtual camera stream (default: `160`).
- `--virtual-cam-fps` / `-virtual-cam-fps`: Framerate limit for virtual camera (default: 20).

## Media Support

- **URLs**: You can pass a direct URL to an image or GIF (e.g., `https://example.com/image.png`) as the `<image_path>` and it will be downloaded and processed automatically.
- **Animated GIFs**: If an animated GIF is provided, the script will loop through the frames infinitely, printing each directly to the terminal.
- **Video Files**: Pass any supported local video file (`.mp4`, `.mkv`, `.avi`, `.webm`) and it will natively stream to the terminal.
- **Webcams**: Providing the `--webcam` flag bypasses all paths and hooks directly into `cv2.VideoCapture(0)`. Useful for interactive live ascii feeds.

### Interactive TUI

If you are running in Video File or Webcam stream mode, the program enables an interactive Text User Interface (TUI) overlay, allowing real-time edits without restarting:

- `TAB`: Cycle between `ascii`, `blocks`, and `braille` modes
- `Up` / `Down` Arrow: Adjust image Brightness
- `Left` / `Right` Arrow: Adjust image Contrast
- `g` / `G` (`Shift+G`): Adjust Gamma correction up or down
- `c`: Toggle Truecolor RGB mode
- `b`: Toggle Background Color mode
- `i`: Toggle Inverse rendering mode
- `e`: Toggle Canny Edge Detection (Line Art) mode
- `p`: Cycle through interactive visual Filters (`pixelate`, `matrix`, `bg-remove`, etc.)
- `d`: Toggle Dithering mode
- `s`: Cycle ASCII character sets (`standard`, `dense`, etc.)
- `r`: Rotate video feed by 90 degrees
- `f`: Cycle video flip mirroring (`horizontal`, `vertical`, `none`)

Press `CTRL+C` to cleanly exit video, webcam, and looping modes.

## Virtual Webcam 🎥

You can output the terminal ASCII art directly to a virtual webcam, allowing you to use it in OBS, Zoom, Discord, or Teams!

```bash
# Output webcam through the ASCII filter to a virtual camera
python main.py --webcam --virtual-webcam --mode braille --color

# Play a video filter to the virtual camera
python main.py examples/video.mp4 --virtual-webcam --virtual-cam-fps 30 --mode blocks --color
```

*Note: You may need to install and load the `v4l2loopback` kernel module on Linux (e.g., `sudo modprobe v4l2loopback exclusive_caps=1 card_label="ASCII Camera"`) before the virtual camera device is recognized. OBS Studio on Windows/macOS usually handles this natively.*

## Examples

```bash
python main.py examples/img1.png --fit-terminal
python main.py examples/img1.png --width 120 --color
python main.py examples/img1.png --height 60 --invert --charset dense
python main.py examples/img1.png width=80 --output out.txt
python main.py examples/img1.png --mode blocks --color
python main.py examples/img1.png --html --color --output out.html
python main.py examples/img1.png --brightness 1.15 --contrast 1.25 --gamma 0.9
python main.py examples/img1.png --width 120 --dither --rotate 90 --flip horizontal
python main.py examples/img1.png --width 120 --height 40 --crop cover
```
