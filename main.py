import sys
import os
import PIL.Image


def main():
    print("Img to ascii art converter")
    # TODO: implement the functionality to convert images to ascii art
    if len(sys.argv) != 2:
        print("Usage: python main.py <image_path>")
        return
    image_path = sys.argv[1]
    if not os.path.isfile(image_path):
        print(f"Error: File '{image_path}' does not exist.")
        return
    try:
        image = PIL.Image.open(image_path).convert("L")
        width, _ = image.size
        # we need to write the main conversion logic here for black and white images
        # we can use the getdata() method to get the pixel data and convert it to ascii characters based on the intensity of the pixels
        def get_ascii_char(pixel_value):Img to ascii art converter
/home/simonuwu/imgtoascii/main.py:25: DeprecationWarning: Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead.
  for pixel in image.getdata():
Error: unsupported operand type(s) for /: 'tuple' and 'int'
            # Define a string of ascii characters from darkest to lightest
            ascii_chars = "@%#*+=-:. "
            # Map the pixel value (0-255) to the range of ascii characters
            index = int(pixel_value / 255 * (len(ascii_chars) - 1))
            return ascii_chars[index]
        ascii_art = []
        for pixel_index, pixel in enumerate(image.get_flattened_data(), start=1):
            # Assuming the image is in grayscale, we can use the pixel value to determine the ascii character
            ascii_char = get_ascii_char(pixel)

            ascii_art.append(ascii_char)
            if pixel_index % width == 0:
                ascii_art.append("\n")
        print("".join(ascii_art), end="")


    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
