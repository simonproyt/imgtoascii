import argparse
import html
import os
import shutil
import sys

import PIL.Image
import PIL.ImageEnhance
import PIL.ImageOps


CHARSET_PRESETS = {
    "standard": "@%#*+=-:. ",
    "dense": "@$B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/|()1{}[]?-_+~<>i!;:,. ",
    "simple": "@#*:. ",
    "classic": "#A@%S+<*. ",
}
BLOCK_SHADE_CHARS = "█▓▒░ "


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
    parser.add_argument("--invert", "-invert", action="store_true", help="Invert the brightness mapping")
    parser.add_argument("--charset", "-charset", choices=sorted(CHARSET_PRESETS), default="standard", help="ASCII character set preset")
    parser.add_argument("--mode", "-mode", choices=("ascii", "blocks"), default="ascii", help="Rendering mode")
    parser.add_argument("--html", "-html", action="store_true", help="Render the output as an HTML document")
    parser.add_argument("--brightness", "-brightness", type=positive_float, default=1.0, help="Brightness multiplier")
    parser.add_argument("--contrast", "-contrast", type=positive_float, default=1.0, help="Contrast multiplier")
    parser.add_argument("--gamma", "-gamma", type=positive_float, default=1.0, help="Gamma correction factor")
    parser.add_argument("--crop", "-crop", choices=("none", "cover", "contain"), default="none", help="Resize strategy when fitting the image")
    parser.add_argument("--output", "-output", default=None, help="Write the result to a file")

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


def detect_html_output(args):
    if args.html:
        return True
    if args.output:
        return args.output.lower().endswith((".html", ".htm"))
    return False


def render_height_for_mode(height, mode):
    if mode == "blocks":
        return height * 2
    return height


def resize_image(image, target_size, crop_mode):
    if image.size == target_size:
        return image.copy()
    if crop_mode == "cover":
        return PIL.ImageOps.fit(image, target_size, method=PIL.Image.Resampling.BILINEAR, centering=(0.5, 0.5))
    if crop_mode == "contain":
        return PIL.ImageOps.pad(
            image,
            target_size,
            method=PIL.Image.Resampling.BILINEAR,
            color=(255, 255, 255),
            centering=(0.5, 0.5),
        )
    return image.resize(target_size, PIL.Image.Resampling.BILINEAR)


def adjust_gamma(image, gamma):
    if gamma == 1.0:
        return image
    lookup = [round(((value / 255) ** (1 / gamma)) * 255) for value in range(256)]
    return image.point(lookup * len(image.getbands()))


def preprocess_image(image, brightness, contrast, gamma):
    processed = image.convert("RGB")
    if brightness != 1.0:
        processed = PIL.ImageEnhance.Brightness(processed).enhance(brightness)
    if contrast != 1.0:
        processed = PIL.ImageEnhance.Contrast(processed).enhance(contrast)
    if gamma != 1.0:
        processed = adjust_gamma(processed, gamma)
    return processed


def get_ascii_char(pixel_value, ascii_chars):
    index = int(pixel_value / 255 * (len(ascii_chars) - 1))
    return ascii_chars[index]


def get_block_char(top_pixel, bottom_pixel, invert):
    shade_chars = BLOCK_SHADE_CHARS[::-1] if invert else BLOCK_SHADE_CHARS
    if abs(top_pixel - bottom_pixel) < 48:
        index = int(((top_pixel + bottom_pixel) / 2) / 255 * (len(shade_chars) - 1))
        return shade_chars[index]

    top_filled = top_pixel < 128
    bottom_filled = bottom_pixel < 128
    if invert:
        top_filled = not top_filled
        bottom_filled = not bottom_filled

    if top_filled and bottom_filled:
        return "█"
    if top_filled:
        return "▀"
    if bottom_filled:
        return "▄"
    return " "


def build_terminal_ascii_art(grayscale_bytes, width, ascii_chars, use_color=False, color_bytes=b""):
    ascii_art = []
    for pixel_index, pixel in enumerate(grayscale_bytes):
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


def build_html_ascii_art(grayscale_bytes, width, ascii_chars, use_color=False, color_bytes=b""):
    ascii_art = ["<pre class=\"ascii-art\">\n"]
    for pixel_index, pixel in enumerate(grayscale_bytes):
        ascii_char = html.escape(get_ascii_char(pixel, ascii_chars))
        if use_color:
            color_offset = pixel_index * 3
            red = color_bytes[color_offset]
            green = color_bytes[color_offset + 1]
            blue = color_bytes[color_offset + 2]
            ascii_art.append(f"<span style=\"color: rgb({red}, {green}, {blue});\">{ascii_char}</span>")
        else:
            ascii_art.append(ascii_char)

        if (pixel_index + 1) % width == 0:
            ascii_art.append("\n")
    ascii_art.append("</pre>")
    return "".join(ascii_art)


def build_terminal_block_art(grayscale_bytes, width, height, invert, use_color=False, color_bytes=b""):
    ascii_art = []
    source_height = height * 2
    for row in range(height):
        top_row = row * 2
        bottom_row = top_row + 1
        for column in range(width):
            top_index = top_row * width + column
            bottom_index = bottom_row * width + column
            top_pixel = grayscale_bytes[top_index]
            bottom_pixel = grayscale_bytes[bottom_index] if bottom_row < source_height else 255
            if use_color:
                top_color_index = top_index * 3
                top_red = color_bytes[top_color_index]
                top_green = color_bytes[top_color_index + 1]
                top_blue = color_bytes[top_color_index + 2]
                if bottom_row < source_height:
                    bottom_color_index = bottom_index * 3
                    bottom_red = color_bytes[bottom_color_index]
                    bottom_green = color_bytes[bottom_color_index + 1]
                    bottom_blue = color_bytes[bottom_color_index + 2]
                    ascii_art.append(
                        f"\x1b[38;2;{top_red};{top_green};{top_blue}m"
                        f"\x1b[48;2;{bottom_red};{bottom_green};{bottom_blue}m▀"
                    )
                else:
                    ascii_art.append(f"\x1b[38;2;{top_red};{top_green};{top_blue}m\x1b[49m▀")
            else:
                ascii_art.append(get_block_char(top_pixel, bottom_pixel, invert))

        if use_color:
            ascii_art.append("\x1b[0m")
        ascii_art.append("\n")
    return "".join(ascii_art)


def build_html_block_art(grayscale_bytes, width, height, invert, use_color=False, color_bytes=b""):
    ascii_art = ["<pre class=\"ascii-art\">\n"]
    source_height = height * 2
    for row in range(height):
        top_row = row * 2
        bottom_row = top_row + 1
        for column in range(width):
            top_index = top_row * width + column
            bottom_index = bottom_row * width + column
            top_pixel = grayscale_bytes[top_index]
            bottom_pixel = grayscale_bytes[bottom_index] if bottom_row < source_height else 255
            if use_color:
                top_color_index = top_index * 3
                top_red = color_bytes[top_color_index]
                top_green = color_bytes[top_color_index + 1]
                top_blue = color_bytes[top_color_index + 2]
                style = f"color: rgb({top_red}, {top_green}, {top_blue});"
                if bottom_row < source_height:
                    bottom_color_index = bottom_index * 3
                    bottom_red = color_bytes[bottom_color_index]
                    bottom_green = color_bytes[bottom_color_index + 1]
                    bottom_blue = color_bytes[bottom_color_index + 2]
                    style += f" background-color: rgb({bottom_red}, {bottom_green}, {bottom_blue});"
                ascii_art.append(f"<span style=\"{style}\">▀</span>")
            else:
                ascii_art.append(html.escape(get_block_char(top_pixel, bottom_pixel, invert)))
        ascii_art.append("\n")
    ascii_art.append("</pre>")
    return "".join(ascii_art)


def build_html_document(content, title):
    escaped_title = html.escape(title)
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        f"  <title>{escaped_title}</title>\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "  <style>\n"
        "    :root { color-scheme: dark; }\n"
        "    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: radial-gradient(circle at top, #2b2b2b 0%, #111 55%, #050505 100%); color: #f4f4f0; font-family: Iosevka, 'JetBrains Mono', 'Fira Code', monospace; }\n"
        "    .frame { padding: 24px; border-radius: 18px; border: 1px solid rgba(255,255,255,0.12); background: rgba(12, 12, 12, 0.78); box-shadow: 0 20px 60px rgba(0, 0, 0, 0.45); overflow: auto; max-width: calc(100vw - 32px); }\n"
        "    .ascii-art { margin: 0; white-space: pre; line-height: 0.9; font-size: 12px; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <div class=\"frame\">\n"
        f"{content}\n"
        "  </div>\n"
        "</body>\n"
        "</html>\n"
    )


def render_output(grayscale_image, rgb_image, width, height, args, use_html):
    grayscale_bytes = grayscale_image.tobytes()
    color_bytes = rgb_image.tobytes() if args.color else b""

    if args.mode == "blocks":
        if use_html:
            return build_html_document(
                build_html_block_art(grayscale_bytes, width, height, args.invert, args.color, color_bytes),
                os.path.basename(args.image_path),
            )
        return build_terminal_block_art(grayscale_bytes, width, height, args.invert, args.color, color_bytes)

    ascii_chars = CHARSET_PRESETS[args.charset]
    if args.invert:
        ascii_chars = ascii_chars[::-1]

    if use_html:
        return build_html_document(
            build_html_ascii_art(grayscale_bytes, width, ascii_chars, args.color, color_bytes),
            os.path.basename(args.image_path),
        )
    return build_terminal_ascii_art(grayscale_bytes, width, ascii_chars, args.color, color_bytes)


def main():
    args = parse_args(sys.argv[1:])
    image_path = args.image_path
    if not os.path.isfile(image_path):
        print(f"Error: File '{image_path}' does not exist.")
        return

    try:
        use_html = detect_html_output(args)
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
            render_size = (width, render_height_for_mode(height, args.mode))
            prepared_image = resize_image(source_image, render_size, args.crop)
            processed_image = preprocess_image(prepared_image, args.brightness, args.contrast, args.gamma)
            grayscale_image = processed_image.convert("L")

        output = render_output(grayscale_image, processed_image, width, height, args, use_html)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as output_file:
                output_file.write(output)
        else:
            sys.stdout.write(output)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
