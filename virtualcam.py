import re
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import os

try:
    import pyvirtualcam
except ImportError:
    pyvirtualcam = None

def get_default_font():
    fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "C:\\Windows\\Fonts\\consola.ttf",
        "C:\\Windows\\Fonts\\cour.ttf"
    ]
    for f in fonts:
        if os.path.exists(f):
            return f
    return None

def render_ansi_to_image(ansi_text, font_path=None, font_size=14, bg_color=(0,0,0)):
    if font_path:
        font = ImageFont.truetype(font_path, font_size)
    else:
        try:
            font = ImageFont.truetype(get_default_font(), font_size)
        except:
            font = ImageFont.load_default()
            
    # Remove terminal clear codes like \033[2J and \033[H which confuse rendering
    ansi_text = ansi_text.replace('\x1b[2J', '').replace('\x1b[H', '')
    
    # Calculate bounding box for a single character to setup grid
    left, top, right, bottom = font.getbbox("A")
    char_width = right - left
    char_height = bottom - top
    
    char_height += 2

    lines = ansi_text.split('\n')
    width = max(len(re.sub(r'\x1b\[.*?m', '', line)) for line in lines) * char_width
    height = len(lines) * char_height
    
    if width == 0 or height == 0:
        return Image.new('RGB', (10, 10), bg_color)
        
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    x, y = 0, 0
    current_fg = (255, 255, 255)
    current_bg = bg_color
    
    ansi_escape = re.compile(r'(\x1b\[.*?m)')
    
    for line in lines:
        x = 0
        parts = ansi_escape.split(line)
        for part in parts:
            if not part: continue
            
            if part.startswith('\x1b['):
                m_fg = re.search(r'38;2;(\d+);(\d+);(\d+)', part)
                if m_fg:
                    current_fg = (int(m_fg.group(1)), int(m_fg.group(2)), int(m_fg.group(3)))
                m_bg = re.search(r'48;2;(\d+);(\d+);(\d+)', part)
                if m_bg:
                    current_bg = (int(m_bg.group(1)), int(m_bg.group(2)), int(m_bg.group(3)))
                if part == '\x1b[0m':
                    current_fg = (255, 255, 255)
                    current_bg = bg_color
            else:
                for char in part:
                    if current_bg != bg_color:
                        draw.rectangle([x, y, x + char_width, y + char_height], fill=current_bg)
                    draw.text((x, y), char, font=font, fill=current_fg)
                    x += char_width
        y += char_height
        
    return img

class VirtualWebcamManager:
    def __init__(self, fps=20):
        if not pyvirtualcam:
            print("Warning: pyvirtualcam is not installed. Virtual webcam will be disabled.")
        self.fps = fps
        self.cam = None
        self.expected_shape = None

    def send_frame(self, ansi_text):
        if not pyvirtualcam:
            return # Error handled at startup
            
        img = render_ansi_to_image(ansi_text)
        
        # Ensure standard 720p dimensions to prevent v4l2 buffer alignment issues in ffmpeg/browsers
        target_w, target_h = 1280, 720
        
        # Scale the image down if it exceeds the target, otherwise we simply center pad it
        img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
        
        padded_img = Image.new('RGB', (target_w, target_h), (0, 0, 0))
        # Center the image
        x_offset = (target_w - img.width) // 2
        y_offset = (target_h - img.height) // 2
        padded_img.paste(img, (x_offset, y_offset))
            
        frame = np.array(padded_img)
        
        # Initialize camera on first frame, or re-init if shape drastically changes
        if self.cam is None or (self.expected_shape is not None and frame.shape != self.expected_shape):
            if self.cam:
                self.cam.close()
            try:
                self.cam = pyvirtualcam.Camera(width=frame.shape[1], height=frame.shape[0], fps=self.fps)
                self.expected_shape = frame.shape
            except Exception as e:
                print(f"Virtual camera error: {e}")
                return
                
        if frame.shape == self.expected_shape:
            self.cam.send(frame)

    def close(self):
        if self.cam:
            self.cam.close()
            self.cam = None

