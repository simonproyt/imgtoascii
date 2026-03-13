import argparse
import html
import io
import os
import shutil
import sys
import time
import urllib.request
from urllib.error import URLError

import PIL.Image
import PIL.ImageEnhance
import PIL.ImageOps
import PIL.ImageSequence

try:
    import cv2
except ImportError:
    cv2 = None


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
    filtered_argv = []
    extras_pre = []
    for arg in argv:
        if arg.startswith("width=") or arg.startswith("height="):
            extras_pre.append(arg)
        else:
            filtered_argv.append(arg)

    parser = argparse.ArgumentParser(description="Convert an image or webcam feed to ASCII art")
    parser.add_argument("image_path", nargs="?", default=None, help="Path or URL to the image file")
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
    parser.add_argument("--dither", "-dither", action="store_true", help="Apply Floyd-Steinberg dithering")
    parser.add_argument("--rotate", "-rotate", type=float, default=0.0, help="Rotate image by degrees")
    parser.add_argument("--flip", "-flip", choices=("horizontal", "vertical"), default=None, help="Flip image horizontally or vertically")
    parser.add_argument("--crop", "-crop", choices=("none", "cover", "contain"), default="none", help="Resize strategy when fitting the image")
    parser.add_argument("--webcam", "-webcam", action="store_true", help="Use webcam as input")
    parser.add_argument("--output", "-output", default=None, help="Write the result to a file")

    args, extras = parser.parse_known_args(filtered_argv)
    if not args.image_path and not args.webcam:
        parser.error("Must provide an image_path or use --webcam")

    for token in extras + extras_pre:
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


def orient_image(image, rotate, flip):
    if rotate != 0.0:
        image = image.rotate(rotate, expand=True)
    if flip == "horizontal":
        image = PIL.ImageOps.mirror(image)
    elif flip == "vertical":
        image = PIL.ImageOps.flip(image)
    return image


def apply_dithering(grayscale_image, num_shades):
    pal_img = PIL.Image.new("P", (1, 1))
    palette = []
    for i in range(num_shades):
        val = int(i * 255 / max(1, num_shades - 1))
        palette.extend([val, val, val])
    palette.extend([0] * (768 - len(palette)))
    pal_img.putpalette(palette)
    # Convert requires RGB for quantize with palette
    return grayscale_image.convert("RGB").quantize(palette=pal_img, dither=1).convert("L")


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


def process_and_build_frame(source_image, args, use_html=False):
    source_image = orient_image(source_image, args.rotate, args.flip)
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
    if args.dither:
        num_shades = len(CHARSET_PRESETS[args.charset]) if args.mode == "ascii" else len(BLOCK_SHADE_CHARS) * 2
        grayscale_image = apply_dithering(grayscale_image, num_shades)

    return render_output(grayscale_image, processed_image, width, height, args, use_html)


def play_gif(image, args, use_html):
    sys.stdout.write("\033[2J")  # Clear screen once
    try:
        while True:
            for frame in PIL.ImageSequence.Iterator(image):
                frame = frame.convert("RGBA")
                # Paste onto black background to fix transparent frames
                bg = PIL.Image.new("RGB", frame.size, (0, 0, 0))
                bg.paste(frame, mask=frame.split()[3])
                
                output = process_and_build_frame(bg, args, use_html)
                
                sys.stdout.write("\033[H" + output)
                sys.stdout.flush()
                
                duration = frame.info.get('duration', 100)
                time.sleep((duration or 100) / 1000.0)
    except KeyboardInterrupt:
        # Terminate cleanly
        sys.stdout.write("\n")


def play_webcam(args):
    if cv2 is None:
        print("Error: opencv-python is required for webcam mode. Install it with `pip config set global.index-url ...` or `uv add opencv-python`")
        return
        
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return
        
    sys.stdout.write("\033[2J")  # Clear screen
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = PIL.Image.fromarray(frame_rgb)
            
            output = process_and_build_frame(pil_img, args, use_html=False)
            
            sys.stdout.write("\033[H" + output)
            sys.stdout.flush()
    except KeyboardInterrupt:
        sys.stdout.write("\n")
    finally:
        cap.release()


def main():
    args = parse_args(sys.argv[1:])
    
    if args.webcam:
        play_webcam(args)
        return

    image_path = args.image_path
    
    if image_path.startswith("http://") or image_path.startswith("https://"):
        req = urllib.request.Request(image_path, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            response = urllib.request.urlopen(req)
            image_file = io.BytesIO(response.read())
        except URLError as e:
            print(f"Error fetching URL: {e}")
            return
    else:
        if not os.path.isfile(image_path):
            print(f"Error: File '{image_path}' does not exist.")
            return
        image_file = image_path

    try:
        use_html = detect_html_output(args)
        with PIL.Image.open(image_file) as source_image:
            if getattr(source_image, "is_animated", False) and not use_html and not args.output:
                play_gif(source_image, args, use_html)
            else:
                output = process_and_build_frame(source_image.copy(), args, use_html)
                if args.output:
                    with open(args.output, "w", encoding="utf-8") as output_file:
                        output_file.write(output)
                else:
                    sys.stdout.write(output)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
