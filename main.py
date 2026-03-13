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

import virtualcam


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
    parser.add_argument("--bg-color", "-bg-color", action="store_true", help="Render colors to the terminal background")
    parser.add_argument("--fit-terminal", "-fit-terminal", action="store_true", help="Fit output to the current terminal size")
    parser.add_argument("--aspect-ratio", "-aspect-ratio", type=positive_float, default=0.5, help="Character height-to-width correction factor")
    parser.add_argument("--invert", "-invert", action="store_true", help="Invert the brightness mapping")
    parser.add_argument("--edges", "-edges", action="store_true", help="Apply edge detection filter")
    parser.add_argument("--charset", "-charset", choices=sorted(CHARSET_PRESETS), default="standard", help="ASCII character set preset")
    parser.add_argument("--mode", "-mode", choices=("ascii", "blocks", "braille"), default="ascii", help="Rendering mode")
    parser.add_argument("--html", "-html", action="store_true", help="Render the output as an HTML document")
    parser.add_argument("--brightness", "-brightness", type=positive_float, default=1.0, help="Brightness multiplier")
    parser.add_argument("--contrast", "-contrast", type=positive_float, default=1.0, help="Contrast multiplier")
    parser.add_argument("--gamma", "-gamma", type=positive_float, default=1.0, help="Gamma correction factor")
    parser.add_argument("--dither", "-dither", action="store_true", help="Apply Floyd-Steinberg dithering")
    parser.add_argument("--rotate", "-rotate", type=float, default=0.0, help="Rotate image by degrees")
    parser.add_argument("--flip", "-flip", choices=("horizontal", "vertical"), default=None, help="Flip image horizontally or vertically")
    parser.add_argument("--crop", "-crop", choices=("none", "cover", "contain"), default="none", help="Resize strategy when fitting the image")
    parser.add_argument("--webcam", "-webcam", action="store_true", help="Use webcam as input")
    parser.add_argument("--virtual-webcam", "-virtual-webcam", action="store_true", help="Output standard terminal ANSI to a virtual webcam device")
    parser.add_argument("--virtual-cam-fps", "-virtual-cam-fps", type=positive_int, default=20, help="Framerate for the virtual webcam")
    parser.add_argument("--virtual-cam-width", "-virtual-cam-width", type=positive_int, default=160, help="Terminal characters width for the virtual camera (for a high-res stream)")
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

    if args.bg_color:
        args.color = True

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


def render_size_for_mode(width, height, mode):
    if mode == "blocks":
        return width, height * 2
    if mode == "braille":
        return width * 2, height * 4
    return width, height


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


def build_terminal_ascii_art(grayscale_bytes, width, ascii_chars, use_color=False, use_bg_color=False, color_bytes=b""):
    ascii_art = []
    for pixel_index, pixel in enumerate(grayscale_bytes):
        ascii_char = get_ascii_char(pixel, ascii_chars)
        if use_bg_color and use_color:
            color_offset = pixel_index * 3
            red = color_bytes[color_offset]
            green = color_bytes[color_offset + 1]
            blue = color_bytes[color_offset + 2]
            ascii_art.append(f"\x1b[48;2;{red};{green};{blue}m \x1b[0m")
        elif use_color:
            color_offset = pixel_index * 3
            red = color_bytes[color_offset]
            green = color_bytes[color_offset + 1]
            blue = color_bytes[color_offset + 2]
            ascii_art.append(f"\x1b[38;2;{red};{green};{blue}m{ascii_char}")
        else:
            ascii_art.append(ascii_char)

        if (pixel_index + 1) % width == 0:
            if use_color and not use_bg_color:
                ascii_art.append("\x1b[0m")
            ascii_art.append("\n")
    return "".join(ascii_art)


def build_html_ascii_art(grayscale_bytes, width, ascii_chars, use_color=False, use_bg_color=False, color_bytes=b""):
    ascii_art = ["<pre class=\"ascii-art\">\n"]
    for pixel_index, pixel in enumerate(grayscale_bytes):
        ascii_char = html.escape(get_ascii_char(pixel, ascii_chars))
        if use_bg_color and use_color:
            color_offset = pixel_index * 3
            red = color_bytes[color_offset]
            green = color_bytes[color_offset + 1]
            blue = color_bytes[color_offset + 2]
            ascii_art.append(f"<span style=\"background-color: rgb({red}, {green}, {blue}); color: transparent;\">{ascii_char}</span>")
        elif use_color:
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


def build_terminal_braille_art(grayscale_bytes, width, height, invert, use_color=False, color_bytes=b""):
    ascii_art = []
    source_width = width * 2
    source_height = height * 4
    
    dot_map = [
        [0x01, 0x08],
        [0x02, 0x10],
        [0x04, 0x20],
        [0x40, 0x80]
    ]

    for row in range(height):
        for col in range(width):
            braille_val = 0
            base_y = row * 4
            base_x = col * 2
            
            r_sum, g_sum, b_sum, color_count = 0, 0, 0, 0
            
            for dy in range(4):
                y = base_y + dy
                for dx in range(2):
                    x = base_x + dx
                    
                    if y < source_height and x < source_width:
                        idx = y * source_width + x
                        pixel_val = grayscale_bytes[idx]
                        
                        is_active = pixel_val < 128
                        if invert:
                            is_active = not is_active
                        
                        if is_active:
                            braille_val |= dot_map[dy][dx]
                            if use_color:
                                r_sum += color_bytes[idx*3]
                                g_sum += color_bytes[idx*3+1]
                                b_sum += color_bytes[idx*3+2]
                                color_count += 1
            
            char = chr(0x2800 + braille_val)
            
            if use_color:
                if color_count > 0:
                    r = r_sum // color_count
                    g = g_sum // color_count
                    b = b_sum // color_count
                else:
                    idx = (base_y * source_width + base_x) * 3
                    if idx + 2 < len(color_bytes):
                        r, g, b = color_bytes[idx], color_bytes[idx+1], color_bytes[idx+2]
                    else:
                        r, g, b = 255, 255, 255
                
                ascii_art.append(f"\x1b[38;2;{r};{g};{b}m{char}")
            else:
                ascii_art.append(char)
                
        if use_color:
            ascii_art.append("\x1b[0m")
        ascii_art.append("\n")
        
    return "".join(ascii_art)

def build_html_braille_art(grayscale_bytes, width, height, invert, use_color=False, color_bytes=b""):
    ascii_art = ["<pre class=\"ascii-art\">\n"]
    source_width = width * 2
    source_height = height * 4
    
    dot_map = [
        [0x01, 0x08],
        [0x02, 0x10],
        [0x04, 0x20],
        [0x40, 0x80]
    ]

    for row in range(height):
        for col in range(width):
            braille_val = 0
            base_y = row * 4
            base_x = col * 2
            
            r_sum, g_sum, b_sum, color_count = 0, 0, 0, 0
            
            for dy in range(4):
                y = base_y + dy
                for dx in range(2):
                    x = base_x + dx
                    
                    if y < source_height and x < source_width:
                        idx = y * source_width + x
                        pixel_val = grayscale_bytes[idx]
                        
                        is_active = pixel_val < 128
                        if invert:
                            is_active = not is_active
                        
                        if is_active:
                            braille_val |= dot_map[dy][dx]
                            if use_color:
                                r_sum += color_bytes[idx*3]
                                g_sum += color_bytes[idx*3+1]
                                b_sum += color_bytes[idx*3+2]
                                color_count += 1
            
            char = html.escape(chr(0x2800 + braille_val))
            
            if use_color:
                if color_count > 0:
                    r = r_sum // color_count
                    g = g_sum // color_count
                    b = b_sum // color_count
                else:
                    idx = (base_y * source_width + base_x) * 3
                    if idx + 2 < len(color_bytes):
                        r, g, b = color_bytes[idx], color_bytes[idx+1], color_bytes[idx+2]
                    else:
                        r, g, b = 255, 255, 255
                
                ascii_art.append(f"<span style=\"color: rgb({r}, {g}, {b});\">{char}</span>")
            else:
                ascii_art.append(char)
                
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

    if args.mode == "braille":
        if use_html:
            return build_html_document(
                build_html_braille_art(grayscale_bytes, width, height, args.invert, args.color, color_bytes),
                os.path.basename(args.image_path) if args.image_path else "webcam",
            )
        return build_terminal_braille_art(grayscale_bytes, width, height, args.invert, args.color, color_bytes)

    if args.mode == "blocks":
        if use_html:
            return build_html_document(
                build_html_block_art(grayscale_bytes, width, height, args.invert, args.color, color_bytes),
                os.path.basename(args.image_path) if args.image_path else "webcam",
            )
        return build_terminal_block_art(grayscale_bytes, width, height, args.invert, args.color, color_bytes)

    ascii_chars = CHARSET_PRESETS[args.charset]
    if args.invert:
        ascii_chars = ascii_chars[::-1]

    if use_html:
        return build_html_document(
            build_html_ascii_art(grayscale_bytes, width, ascii_chars, args.color, args.bg_color, color_bytes),
            os.path.basename(args.image_path) if args.image_path else "webcam",
        )
    return build_terminal_ascii_art(grayscale_bytes, width, ascii_chars, args.color, args.bg_color, color_bytes)


def process_and_build_frame(source_image, args, use_html=False):
    import copy
    args = copy.copy(args)
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
    render_size = render_size_for_mode(width, height, args.mode)
    prepared_image = resize_image(source_image, render_size, args.crop)
    processed_image = preprocess_image(prepared_image, args.brightness, args.contrast, args.gamma)
    
    if args.edges:
        if cv2 is not None:
            import numpy as np
            # Convert to numpy array for OpenCV
            cv_img = np.array(processed_image)
            # Convert to grayscale for Canny
            cv_gray = cv2.cvtColor(cv_img, cv2.COLOR_RGB2GRAY)
            # Apply Canny edge detection
            edges = cv2.Canny(cv_gray, 100, 200)
            # Convert back to PIL Image
            import PIL.Image
            processed_image = PIL.Image.fromarray(edges).convert("RGB")
        else:
            import PIL.ImageFilter
            processed_image = processed_image.filter(PIL.ImageFilter.FIND_EDGES)

    grayscale_image = processed_image.convert("L")
    
    if args.edges and not args.invert:
        # Edges are white on black bg. Invert so edges are drawn with dense characters
        grayscale_image = PIL.ImageOps.invert(grayscale_image)

    if args.dither:
        num_shades = len(CHARSET_PRESETS[args.charset]) if args.mode == "ascii" else len(BLOCK_SHADE_CHARS) * 2
        grayscale_image = apply_dithering(grayscale_image, num_shades)

    return render_output(grayscale_image, processed_image, width, height, args, use_html)


def play_gif(image, args, use_html):
    sys.stdout.write("\033[2J")  # Clear screen once
    vcam = virtualcam.VirtualWebcamManager(fps=args.virtual_cam_fps) if args.virtual_webcam else None
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
                
                if vcam:
                    import copy
                    vcam_args = copy.copy(args)
                    vcam_args.width = args.virtual_cam_width
                    vcam_args.fit_terminal = False
                    vcam_output = process_and_build_frame(bg, vcam_args, use_html=False)
                    vcam.send_frame(vcam_output)
                
                duration = frame.info.get('duration', 100)
                time.sleep((duration or 100) / 1000.0)
    except KeyboardInterrupt:
        # Terminate cleanly
        sys.stdout.write("\n")
    finally:
        if vcam:
            vcam.close()


import threading

try:
    import termios
    import tty
    import select
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False

class TerminalTUI:
    def __init__(self, args):
        self.args = args
        self.modes = ["ascii", "blocks", "braille"]
        if self.args.mode not in self.modes:
            self.modes.append(self.args.mode)
        self.running = True
        if HAS_TERMIOS and os.name != 'nt':
            self.old_settings = termios.tcgetattr(sys.stdin.fileno())

    def start(self):
        if os.name == 'nt':
            self.thread = threading.Thread(target=self._windows_loop, daemon=True)
        else:
            self.thread = threading.Thread(target=self._unix_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if HAS_TERMIOS and os.name != 'nt':
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_settings)

    def _unix_loop(self):
        if not HAS_TERMIOS: return
        fd = sys.stdin.fileno()
        tty.setcbreak(fd)
        while self.running:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if rlist:
                ch = sys.stdin.read(1)
                if ch == '\x1b':
                    rlist2, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if rlist2:
                        ch2 = sys.stdin.read(1)
                        if ch2 == '[':
                            rlist3, _, _ = select.select([sys.stdin], [], [], 0.05)
                            if rlist3:
                                ch3 = sys.stdin.read(1)
                                if ch3 == 'A': self._handle_key("UP")
                                elif ch3 == 'B': self._handle_key("DOWN")
                                elif ch3 == 'C': self._handle_key("RIGHT")
                                elif ch3 == 'D': self._handle_key("LEFT")
                elif ch == '\t': self._handle_key("TAB")
                elif ch == 'c': self._handle_key("c")
                elif ch == 'i': self._handle_key("i")
                elif ch == 'e': self._handle_key("e")
                elif ch == 'b': self._handle_key("b")
                elif ch == 'd': self._handle_key("d")
                elif ch == 's': self._handle_key("s")
                elif ch == 'r': self._handle_key("r")
                elif ch == 'f': self._handle_key("f")
                elif ch == 'g': self._handle_key("g")
                elif ch == 'G': self._handle_key("G")
                elif ch == '\x03': # ctrl+c
                    import _thread
                    _thread.interrupt_main()
                    break
                else: self._handle_key(ch)

    def _windows_loop(self):
        import msvcrt
        while self.running:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch in (b'\x00', b'\xe0'):
                    ch2 = msvcrt.getch()
                    if ch2 == b'H': self._handle_key("UP")
                    elif ch2 == b'P': self._handle_key("DOWN")
                    elif ch2 == b'M': self._handle_key("RIGHT")
                    elif ch2 == b'K': self._handle_key("LEFT")
                elif ch == b'\t': self._handle_key("TAB")
                elif ch == b'c': self._handle_key("c")
                elif ch == b'i': self._handle_key("i")
                elif ch == b'e': self._handle_key("e")
                elif ch == b'b': self._handle_key("b")
                elif ch == b'd': self._handle_key("d")
                elif ch == b's': self._handle_key("s")
                elif ch == b'r': self._handle_key("r")
                elif ch == b'f': self._handle_key("f")
                elif ch == b'g': self._handle_key("g")
                elif ch == b'G': self._handle_key("G")
                elif ch == b'\x03':
                    import _thread
                    _thread.interrupt_main()
                    break
                else: self._handle_key(ch.decode('utf-8', 'ignore'))
            else:
                time.sleep(0.05)

    def _handle_key(self, key):
        step = 0.1
        if key == "UP":
            self.args.brightness += step
        elif key == "DOWN":
            self.args.brightness = max(0.0, self.args.brightness - step)
        elif key == "RIGHT":
            self.args.contrast += step
        elif key == "LEFT":
            self.args.contrast = max(0.0, self.args.contrast - step)
        elif key == "TAB":
            idx = self.modes.index(self.args.mode)
            self.args.mode = self.modes[(idx + 1) % len(self.modes)]
        elif key == "c":
            self.args.color = not self.args.color
        elif key == "i":
            self.args.invert = not self.args.invert
        elif key == "e":
            self.args.edges = not self.args.edges
        elif key == "b":
            self.args.bg_color = not self.args.bg_color
            if self.args.bg_color:
                self.args.color = True
        elif key == "d":
            self.args.dither = not self.args.dither
        elif key == "s":
            charsets = sorted(CHARSET_PRESETS)
            idx = charsets.index(self.args.charset)
            self.args.charset = charsets[(idx + 1) % len(charsets)]
        elif key == "r":
            self.args.rotate = (self.args.rotate + 90.0) % 360.0
        elif key == "f":
            if self.args.flip is None: self.args.flip = "horizontal"
            elif self.args.flip == "horizontal": self.args.flip = "vertical"
            else: self.args.flip = None
        elif key == "g":
            self.args.gamma += 0.1
        elif key == "G":
            self.args.gamma = max(0.1, self.args.gamma - 0.1)

    def get_status_line(self):
        return f"\033[0m\033[K[TUI] Mode(TAB):{self.args.mode.upper()} | Bri(\u2191\u2193):{self.args.brightness:.1f} | Con(\u2190\u2192):{self.args.contrast:.1f} | Gam(g/G):{self.args.gamma:.1f}\n\033[K[TUI] Color(c):{self.args.color} | Bg(b):{self.args.bg_color} | Inv(i):{self.args.invert} | Edges(e):{self.args.edges} | Dith(d):{self.args.dither} | Set(s):{self.args.charset} | Rot(r):{self.args.rotate} | Flip(f):{self.args.flip}"

def play_video_stream(args, source=0):
    if cv2 is None:
        print("Error: opencv-python is required for video/webcam mode.")
        return
        
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"Error: Could not open video source {source}.")
        return
        
    sys.stdout.write("\033[2J")  # Clear screen
    
    tui = TerminalTUI(args)
    if sys.stdin.isatty():
        tui.start()
        
    vcam = virtualcam.VirtualWebcamManager(fps=args.virtual_cam_fps) if args.virtual_webcam else None
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0 or fps > 120:
        fps = 30
    frame_delay = 1.0 / fps

    try:
        while True:
            start_time = time.time()
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = PIL.Image.fromarray(frame_rgb)
            
            output = process_and_build_frame(pil_img, args, use_html=False)
            status_line = tui.get_status_line() if sys.stdin.isatty() else ""
            
            sys.stdout.write("\033[H" + output + "\n" + status_line)
            sys.stdout.flush()
            
            if vcam:
                vcam_args = copy.copy(args)
                vcam_args.width = args.virtual_cam_width
                vcam_args.fit_terminal = False
                vcam_output = process_and_build_frame(pil_img, vcam_args, use_html=False)
                vcam.send_frame(vcam_output)
            
            elapsed = time.time() - start_time
            sleep_time = frame_delay - elapsed
            if sleep_time > 0 and source != 0:
                time.sleep(sleep_time)
                
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\n\033[0m")
        cap.release()
        if sys.stdin.isatty():
            tui.stop()
        if vcam:
            vcam.close()

def main():
    args = parse_args(sys.argv[1:])
    
    if args.webcam:
        play_video_stream(args, source=0)
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
            
        image_ext = image_path.lower().split('.')[-1]
        video_exts = {'mp4', 'avi', 'mkv', 'mov', 'webm'}
        if image_ext in video_exts:
            play_video_stream(args, source=image_path)
            return
            
        image_file = image_path

    try:
        use_html = detect_html_output(args)
        with PIL.Image.open(image_file) as source_image:
            if getattr(source_image, "is_animated", False) and not use_html and not args.output:
                play_gif(source_image, args, use_html)
            else:
                output = process_and_build_frame(source_image.copy(), args, use_html)
                if args.virtual_webcam:
                    sys.stdout.write(output + "\nPress Ctrl+C to stop virtual webcam...\n")
                    sys.stdout.flush()
                    vcam = virtualcam.VirtualWebcamManager(fps=args.virtual_cam_fps)
                    import copy
                    vcam_args = copy.copy(args)
                    vcam_args.width = args.virtual_cam_width
                    vcam_args.fit_terminal = False
                    vcam_output = process_and_build_frame(source_image.copy(), vcam_args, use_html=False)
                    try:
                        while True:
                            vcam.send_frame(vcam_output)
                            time.sleep(1.0 / args.virtual_cam_fps)
                    except KeyboardInterrupt:
                        pass
                    finally:
                        vcam.close()
                elif args.output:
                    with open(args.output, "w", encoding="utf-8") as output_file:
                        output_file.write(output)
                else:
                    sys.stdout.write(output)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
