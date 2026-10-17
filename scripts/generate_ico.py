import os
import struct
from io import BytesIO
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtCore import Qt, QSize, QByteArray, QBuffer
from PySide6.QtSvg import QSvgRenderer

def svg_to_ico(svg_path: str, ico_path: str):
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        raise ValueError(f"Invalid SVG: {svg_path}")

    sizes = [16, 24, 32, 48, 64, 128, 256]
    png_images = []

    for s in sizes:
        img = QImage(s, s, QImage.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        painter = QPainter(img)
        renderer.render(painter)
        painter.end()

        byte_arr = QByteArray()
        buffer = QBuffer(byte_arr)
        buffer.open(QBuffer.WriteOnly)
        img.save(buffer, "PNG")
        png_bytes = bytes(byte_arr.data())
        png_images.append((s, png_bytes))

    # Build ICO file with embedded PNGs
    num_images = len(png_images)
    header = struct.pack("<HHH", 0, 1, num_images)
    entries = []
    offset = 6 + (16 * num_images)
    image_data = b""

    for s, data in png_images:
        w = 0 if s == 256 else s
        h = 0 if s == 256 else s
        size_bytes = len(data)
        entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, size_bytes, offset)
        entries.append(entry)
        offset += size_bytes
        image_data += data

    with open(ico_path, "wb") as f:
        f.write(header)
        for e in entries:
            f.write(e)
        f.write(image_data)

    print(f"Generated {ico_path} successfully ({len(sizes)} sizes, {os.path.getsize(ico_path)} bytes)")


def svg_to_png(svg_path: str, png_path: str, size: int = 32):
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        raise ValueError(f"Invalid SVG: {svg_path}")
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    img.save(png_path, "PNG")
    print(f"Generated {png_path} successfully ({size}x{size})")


if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    svg = os.path.join(base_dir, "src", "assets", "beaver.svg")
    ico = os.path.join(base_dir, "src", "assets", "beaver.ico")
    if os.path.isfile(svg):
        svg_to_ico(svg, ico)

    check_svg = os.path.join(base_dir, "src", "assets", "check.svg")
    check_png = os.path.join(base_dir, "src", "assets", "check.png")
    if os.path.isfile(check_svg):
        svg_to_png(check_svg, check_png, 32)
