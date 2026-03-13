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

## Media Support



- **URLs**: You can pass a direct URL to an image or GIF (e.g., `https://example.com/image.png`) as the `<image_path>` and it will be downloaded and processed automatically.

- **Animated GIFs**: If an animated GIF is provided, the script will loop through the frames infinitely, printing each directly to the terminal.

- **Video Files**: Pass any supported local video file (`.mp4`, `.mkv`, `.avi`, `.webm`) and it will natively stream to the terminal.

- **Webcams**: Providing the `--webcam` flag bypasses all paths and hooks directly into `cv2.VideoCapture(0)`. Useful for interactive live ascii feeds.



### Interactive TUI



If you are running in Video File or Webcam stream mode, the program enables an interactive Text User Interface (TUI) overlay, allowing real-time edits without restarting:

- `TAB`: Cycle between `ascii`, `blocks`, and `braille` modes.

- `Up` / `Down` Arrow: Adjust image Brightness

- `Left` / `Right` Arrow: Adjust image Contrast

- `c`: Toggle Truecolor RGB mode

- `i`: Toggle Inverse rendering mode
- `e`: Toggle Canny Edge Detection (Line Art) mode
- `b`: Toggle Background Color mode
- `d`: Toggle Dithering mode



Press `CTRL+C` to cleanly exit video, webcam, and looping modes.



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
