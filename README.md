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
- `--fit-terminal` / `-fit-terminal`: Scale the output to fit the current terminal.
- `--aspect-ratio` / `-aspect-ratio`: Character height-to-width correction factor. Default: `0.5`.
- `--invert` / `-invert`: Reverse the brightness-to-character mapping.
- `--charset` / `-charset`: Choose a preset: `standard`, `dense`, `simple`, or `classic`.
- `--mode` / `-mode`: Choose `ascii` or `blocks` rendering.
- `--html` / `-html`: Export the result as an HTML document.
- `--brightness` / `-brightness`: Adjust brightness. Default: `1.0`.
- `--contrast` / `-contrast`: Adjust contrast. Default: `1.0`.
- `--gamma` / `-gamma`: Adjust gamma. Default: `1.0`.
- `--crop` / `-crop`: Choose `none`, `cover`, or `contain` resizing behavior.
- `--output` / `-output`: Write the result to a file instead of stdout.

## Examples

```bash
python main.py examples/img1.png --fit-terminal
python main.py examples/img1.png --width 120 --color
python main.py examples/img1.png --height 60 --invert --charset dense
python main.py examples/img1.png width=80 --output out.txt
python main.py examples/img1.png --mode blocks --color
python main.py examples/img1.png --html --color --output out.html
python main.py examples/img1.png --brightness 1.15 --contrast 1.25 --gamma 0.9
python main.py examples/img1.png --width 120 --height 40 --crop cover
```
