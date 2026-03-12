import sys
import os
import argparse
import PIL.Image


def positive_int(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Convert an image to ASCII art")
    parser.add_argument("image_path", help="Path to the image file")
    parser.add_argument("--width", "-width", type=positive_int, default=None, help="Output width in characters")
    parser.add_argument("--height", "-height", type=positive_int, default=None, help="Output height in characters")
    parser.add_argument("--color", "-color", action="store_true", help="Render ANSI colored ASCII output")

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


def resolve_size(original_width, original_height, requested_width, requested_height):
    if requested_width and requested_height:
        return requested_width, requested_height
    if requested_width:
        scaled_height = max(1, round(original_height * requested_width / original_width))
        return requested_width, scaled_height
    if requested_height:
        scaled_width = max(1, round(original_width * requested_height / original_height))
        return scaled_width, requested_height
    return original_width, original_height


def get_ascii_char(pixel_value):
    ascii_chars = "@%#*+=-:. "
    index = int(pixel_value / 255 * (len(ascii_chars) - 1))
    return ascii_chars[index]


def main():
    print("Img to ascii art converter")
    args = parse_args(sys.argv[1:])

    image_path = args.image_path
    if not os.path.isfile(image_path):
        print(f"Error: File '{image_path}' does not exist.")
        return
    try:
        with PIL.Image.open(image_path) as source_image:
            original_width, original_height = source_image.size
            width, height = resolve_size(original_width, original_height, args.width, args.height)
            if (width, height) != (original_width, original_height):
                source_image = source_image.resize((width, height), PIL.Image.Resampling.BILINEAR)

            grayscale_image = source_image.convert("L")
            color_bytes = source_image.convert("RGB").tobytes() if args.color else b""

        ascii_art = []
        for pixel_index, pixel in enumerate(grayscale_image.get_flattened_data()):
            ascii_char = get_ascii_char(pixel)
            if args.color:
                color_offset = pixel_index * 3
                red = color_bytes[color_offset]
                green = color_bytes[color_offset + 1]
                blue = color_bytes[color_offset + 2]
                ascii_art.append(f"\x1b[38;2;{red};{green};{blue}m{ascii_char}")
            else:
                ascii_art.append(ascii_char)

            if (pixel_index + 1) % width == 0:
                if args.color:
                    ascii_art.append("\x1b[0m")
                ascii_art.append("\n")
        print("".join(ascii_art), end="")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
