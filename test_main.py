import argparse
import pytest
from PIL import Image
import main

def test_positive_int():
    assert main.positive_int("5") == 5
    
    with pytest.raises(argparse.ArgumentTypeError):
        main.positive_int("-1")
        
    with pytest.raises(argparse.ArgumentTypeError):
        main.positive_int("0")
        
    with pytest.raises(argparse.ArgumentTypeError):
        main.positive_int("abc")

def test_positive_float():
    assert main.positive_float("5.5") == 5.5
    
    with pytest.raises(argparse.ArgumentTypeError):
        main.positive_float("-1.2")
        
    with pytest.raises(argparse.ArgumentTypeError):
        main.positive_float("0.0")

def test_resolve_size():
    # resolve_size(original_width, original_height, requested_width, requested_height, fit_terminal, aspect_ratio)
    
    # Test width only
    w, h = main.resolve_size(100, 100, 50, None, False, 0.5)
    assert w == 50
    assert h == 25  # (100 / 100) * 50 * 0.5
    
    # Test height only
    w, h = main.resolve_size(100, 100, None, 40, False, 0.5)
    assert w == 80  # 100 * 40 / (100 * 0.5) -> scaled_width calculation
    assert h == 40
    
    # Test both width and height
    w, h = main.resolve_size(100, 100, 50, 40, False, 0.5)
    assert w == 50
    assert h == 40

def test_render_size_for_mode():
    assert main.render_size_for_mode(10, 10, "ascii") == (10, 10)
    assert main.render_size_for_mode(10, 10, "blocks") == (10, 20)
    assert main.render_size_for_mode(10, 10, "braille") == (20, 40)

def test_get_ascii_char():
    chars = "@%#*+=-:. "
    assert main.get_ascii_char(0, chars) == "@"
    assert main.get_ascii_char(255, chars) == " "

def test_get_block_char():
    # No invert
    # top, bottom < 128 = filled
    assert main.get_block_char(0, 0, False) == "█"
    assert main.get_block_char(255, 255, False) == " "
    assert main.get_block_char(0, 255, False) == "▀"
    assert main.get_block_char(255, 0, False) == "▄"

    # Inverted
    assert main.get_block_char(0, 0, True) == " "
    assert main.get_block_char(255, 255, True) == "█"
    assert main.get_block_char(0, 255, True) == "▄"
    assert main.get_block_char(255, 0, True) == "▀"
    
def test_get_block_char_gray():
    # Difference < 48 (which means it matches into gradient shades instead of stark binary blocks)
    # Using blocks shade chars "█▓▒░ "
    char = main.get_block_char(100, 100, False)
    assert char in "█▓▒░ "

def test_resize_image():
    img = Image.new("RGB", (100, 100))
    resized = main.resize_image(img, (50, 50), "none")
    assert resized.size == (50, 50)

def test_orient_image():
    img = Image.new("RGB", (100, 50))
    
    rotated = main.orient_image(img, 90, None)
    assert rotated.size == (50, 100)
    
    flipped = main.orient_image(img, 0.0, "horizontal")
    assert flipped.size == (100, 50)

def test_build_terminal_ascii_art():
    # 2x2 image, grayscale bytes
    pixels = bytes([0, 255, 0, 255])
    chars = "@ "
    art = main.build_terminal_ascii_art(pixels, 2, chars, use_color=False, use_bg_color=False)
    
    expected = "@ \n@ \n"
    assert art == expected

def test_build_terminal_braille_art():
    # 2x4 braille character = 1 letter
    # All black (val=0 -> < 128 -> dots activated)
    pixels = bytes([0] * 8)
    art = main.build_terminal_braille_art(pixels, 1, 1, invert=False, use_color=False)
    
    # ⣿ is the fully filled braille char
    assert art == "⣿\n"
    
    # All white (val=255 -> dots deactivated)
    pixels_white = bytes([255] * 8)
    art_white = main.build_terminal_braille_art(pixels_white, 1, 1, invert=False, use_color=False)
    assert art_white == "⠀\n"  # Empty braille char

def test_parse_filters_arg():
    assert main.parse_filters_arg("pixelate") == ["pixelate"]
    assert main.parse_filters_arg("blur,sharpen, matrix ") == ["blur", "sharpen", "matrix"]
    assert main.parse_filters_arg("invalid, emboss") == ["emboss"]
    assert main.parse_filters_arg("") == []

class DummyArgs:
    def __init__(self):
        self.mode = "ascii"
        self.brightness = 1.0
        self.contrast = 1.0
        self.color = False
        self.bg_color = False
        self.invert = False
        self.edges = False
        self.dither = False
        self.charset = "standard"
        self.rotate = 0.0
        self.flip = None
        self.crop = "none"
        self.crop = "none"
        self.gamma = 1.0
        self.filter = []

def test_terminal_tui_filters():
    args = DummyArgs()
    main.HAS_TERMIOS = False
    main.HAS_TERMIOS = False
    tui = main.TerminalTUI(args)
    
    # Test setting a new filter
    tui._handle_key("p")
    assert args.filter == ["pixelate"]
    tui._handle_key("p")
    assert args.filter == ["matrix"]
    
    # Test pushing a new filter layer
    tui._handle_key("P")
    assert args.filter == ["matrix", "none"]
    tui._handle_key("p")
    assert args.filter == ["matrix", "pixelate"]
    
    # Test popping a filter layer
    tui._handle_key("O")
    assert args.filter == ["matrix"]
    tui._handle_key("O")
    assert args.filter == ["none"]


def test_build_html_document():
    art = "Hello\nWorld"
    doc = main.build_html_document(art, "img")
    assert "<html lang=" in doc
    assert "Hello\nWorld" in doc

def test_process_and_build_frame(tmp_path):
    img = Image.new("RGB", (10, 10))
    args = DummyArgs()
    args.width = 5
    args.height = 5
    args.fit_terminal = False
    args.aspect_ratio = 1.0
    res = main.process_and_build_frame(img, args)
    assert isinstance(res, str)
    assert len(res) > 0

