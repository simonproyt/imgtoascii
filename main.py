import sys
import os
import argparse
import shutil
import PIL.Image


CHARSET_PRESETS = {
    "standard": "@%#*+=-:. ",
    "dense": "@$B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/|()1{}[]?-_+~<>i!;:,. ",
    "simple": "@#*:. ",
    "classic": "#A@%S+<*. ",
}


def positive_int(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


def positive_float(value):
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Convert an image to ASCII art")
    parser.add_argument("image_path", help="Path to the image file")
    parser.add_argument("--width", "-width", type=positive_int, default=None, help="Output width in characters")
    parser.add_argument("--height", "-height", type=positive_int, default=None, help="Output height in characters")
    parser.add_argument("--color", "-color", action="store_true", help="Render ANSI colored ASCII output")
    parser.add_argument("--fit-terminal", "-fit-terminal", action="store_true", help="Fit output to the current terminal size")
    parser.add_argument("--aspect-ratio", "-aspect-ratio", type=positive_float, default=0.5, help="Character height-to-width correction factor")
    parser.add_argument("--invert", "-invert", action="store_true", help="Invert the ASCII brightness mapping")
    parser.add_argument("--charset", "-charset", choices=sorted(CHARSET_PRESETS), default="standard", help="ASCII character set preset")
    parser.add_argument("--output", "-output", default=None, help="Write the ASCII art to a file")

    args, extras = parser.parse_known_args(argv)
    for token in extras:
        if token.startswith("width="):
            if args.width is not None:
                parser.error("Width was provided more than once")
            args.width = positive_int(token.split("=", 1)[1])
        elif token.startswith("height="):
            if args.height is not None:
                parser.error("Height was provided more than once")
            args.height = positive_int(token.split("=", 1)[1])
        else:
            parser.error(f"Unrecognized argument: {token}")
    return args


def fit_to_terminal(original_width, original_height, aspect_ratio):
    terminal_size = shutil.get_terminal_size(fallback=(80, 24))
    max_width = max(1, terminal_size.columns)
    max_height = max(1, terminal_size.lines - 1)
    corrected_height = max(1.0, original_height * aspect_ratio)
    scale = min(1.0, max_width / original_width, max_height / corrected_height)
    width = max(1, round(original_width * scale))
    height = max(1, round(original_height * scale * aspect_ratio))
    return width, height


def resolve_size(original_width, original_height, requested_width, requested_height, fit_terminal, aspect_ratio):
    if requested_width and requested_height:
        return requested_width, requested_height
    if requested_width:
        scaled_height = max(1, round(original_height * requested_width / original_width * aspect_ratio))
        return requested_width, scaled_height
    if requested_height:
        scaled_width = max(1, round(original_width * requested_height / (original_height * aspect_ratio)))
        return scaled_width, requested_height
    if fit_terminal:
        return fit_to_terminal(original_width, original_height, aspect_ratio)
    return original_width, max(1, round(original_height * aspect_ratio))


def get_ascii_char(pixel_value, ascii_chars):
    index = int(pixel_value / 255 * (len(ascii_chars) - 1))
    return ascii_chars[index]


def build_ascii_art(grayscale_image, width, ascii_chars, use_color=False, color_bytes=b""):
    ascii_art = []
    for pixel_index, pixel in enumerate(grayscale_image.get_flattened_data()):
        ascii_char = get_ascii_char(pixel, ascii_chars)
        if use_color:
            color_offset = pixel_index * 3
            red = color_bytes[color_offset]
            green = color_bytes[color_offset + 1]
            blue = color_bytes[color_offset + 2]
            ascii_art.append(f"\x1b[38;2;{red};{green};{blue}m{ascii_char}")
        else:
            ascii_art.append(ascii_char)

        if (pixel_index + 1) % width == 0:
            if use_color:
                ascii_art.append("\x1b[0m")
            ascii_art.append("\n")
    return "".join(ascii_art)


def main():
    args = parse_args(sys.argv[1:])

    image_path = args.image_path
    if not os.path.isfile(image_path):
        print(f"Error: File '{image_path}' does not exist.")
        return
    try:
        with PIL.Image.open(image_path) as source_image:
            original_width, original_height = source_image.size
            width, height = resolve_size(
                original_width,
                original_height,
                args.width,
                args.height,
                args.fit_terminal,
                args.aspect_ratio,
            )
            if (width, height) != (original_width, original_height):
                source_image = source_image.resize((width, height), PIL.Image.Resampling.BILINEAR)

            grayscale_image = source_image.convert("L")
            color_bytes = source_image.convert("RGB").tobytes() if args.color else b""

        ascii_chars = CHARSET_PRESETS[args.charset]
        if args.invert:
            ascii_chars = ascii_chars[::-1]

        ascii_output = build_ascii_art(grayscale_image, width, ascii_chars, args.color, color_bytes)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as output_file:
                output_file.write(ascii_output)
        else:
            sys.stdout.write(ascii_output)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
