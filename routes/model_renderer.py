"""Automatic 3D model thumbnail renderer.

Renders STL files (binary + ASCII) to PNG thumbnails using pure-Python
3D math + Pillow.  No heavy dependencies (numpy/trimesh/pyrender) needed.

Used by:
- The auto-thumbnail background worker (periodic scan)
- The model upload handler (immediate trigger for new uploads)
"""
import os
import math
import struct
import logging

logger = logging.getLogger(__name__)

# Output dimensions (matches 16:10 card thumbnail aspect ratio in the UI)
DEFAULT_THUMB_W = 400
DEFAULT_THUMB_H = 250

# Renderer limits — protect server from pathological files
MAX_TRIANGLES = 500_000
MAX_FILE_BYTES = 200 * 1024 * 1024  # 200 MB

# Light direction (unit vector) for simple directional shading
_LIGHT = (0.4, -0.6, 0.8)


def _parse_binary_stl(fh):
    """Parse binary STL format.  Returns list of 9-tuples (9 floats per triangle)."""
    header = fh.read(80)
    count_bytes = fh.read(4)
    if len(count_bytes) < 4:
        raise ValueError("Truncated binary STL: missing triangle count")
    (num_triangles,) = struct.unpack('<I', count_bytes)
    if num_triangles > MAX_TRIANGLES:
        raise ValueError(f"STL has {num_triangles} triangles, exceeds limit {MAX_TRIANGLES}")
    triangles = []
    for _ in range(num_triangles):
        chunk = fh.read(50)
        if len(chunk) < 50:
            break
        # 12 bytes normal (ignored — we recompute), 36 bytes vertices, 2 bytes attribute
        _nx, _ny, _nz = struct.unpack('<3f', chunk[0:12])
        v = struct.unpack('<9f', chunk[12:48])
        triangles.append(v)
    return triangles


def _parse_ascii_stl(fh):
    """Parse ASCII STL format.  Returns list of 9-tuples."""
    triangles = []
    current = []
    for line in fh:
        line = line.strip().lower()
        if line.startswith('vertex'):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    current.append(float(parts[1]))
                    current.append(float(parts[2]))
                    current.append(float(parts[3]))
                except ValueError:
                    pass
                if len(current) == 9:
                    triangles.append(tuple(current))
                    current = []
            if len(triangles) >= MAX_TRIANGLES:
                break
    return triangles


def _parse_stl(filepath):
    """Auto-detect binary vs ASCII and return list of triangles.

    Each triangle is 9 floats: v0x,v0y,v0z, v1x,v1y,v1z, v2x,v2y,v2z
    """
    size = os.path.getsize(filepath)
    if size > MAX_FILE_BYTES:
        raise ValueError(f"STL file too large: {size} bytes")
    with open(filepath, 'rb') as fh:
        head = fh.read(5)
        fh.seek(0)
        # Binary STL starts with an 80-byte header followed by a 4-byte uint32 count.
        # ASCII STL starts with the word "solid".
        if head.lower() == b'solid' and size > 84:
            # Could still be binary — peek at the triangle count
            fh.seek(80)
            count_bytes = fh.read(4)
            if len(count_bytes) == 4:
                (num_triangles,) = struct.unpack('<I', count_bytes)
                expected_size = 84 + num_triangles * 50
                if expected_size == size:
                    fh.seek(0)
                    return _parse_binary_stl(fh)
        # Try ASCII
        try:
            fh.seek(0)
            text = fh.read().decode('utf-8', errors='ignore')
            from io import StringIO
            triangles = _parse_ascii_stl(StringIO(text))
            if triangles:
                return triangles
        except Exception:
            pass
        # Fallback: binary
        fh.seek(0)
        return _parse_binary_stl(fh)


def _triangle_normal(tri):
    """Compute the unit normal of a triangle (3 vertices, each xyz)."""
    ax, ay, az = tri[0], tri[1], tri[2]
    bx, by, bz = tri[3], tri[4], tri[5]
    cx, cy, cz = tri[6], tri[7], tri[8]
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length < 1e-12:
        return (0.0, 0.0, 1.0)
    return (nx / length, ny / length, nz / length)


def _triangle_centroid_z(tri):
    """Average Z of the 3 vertices (used for painter's algorithm)."""
    return (tri[2] + tri[5] + tri[8]) / 3.0


def _rotate_x(p, angle):
    x, y, z = p
    c, s = math.cos(angle), math.sin(angle)
    return (x, y * c - z * s, y * s + z * c)


def _rotate_y(p, angle):
    x, y, z = p
    c, s = math.cos(angle), math.sin(angle)
    return (x * c + z * s, y, -x * s + z * c)


def _rotate_z(p, angle):
    x, y, z = p
    c, s = math.cos(angle), math.sin(angle)
    return (x * c - y * s, x * s + y * c, z)


def _render_stl_to_png(triangles, output_path, width=DEFAULT_THUMB_W, height=DEFAULT_THUMB_H,
                        bg_color=(245, 247, 250), model_color=(80, 120, 200)):
    """Render triangles to a PNG using orthographic isometric projection.

    Steps:
    1. Compute bounding box, center & scale to fit
    2. Rotate to isometric view (rotate Z by 45°, then X by -35.26°)
    3. Project to 2D (drop Z)
    4. Painter's algorithm: sort triangles back-to-front
    5. For each triangle: compute shading, draw filled polygon
    """
    from PIL import Image, ImageDraw

    if not triangles:
        raise ValueError("No triangles to render")

    # 1. Bounding box
    xs = [tri[i] for tri in triangles for i in (0, 3, 6)]
    ys = [tri[i] for tri in triangles for i in (1, 4, 7)]
    zs = [tri[i] for tri in triangles for i in (2, 5, 8)]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    cz = (min_z + max_z) / 2.0
    size_x = max_x - min_x or 1.0
    size_y = max_y - min_y or 1.0
    size_z = max_z - min_z or 1.0
    max_dim = max(size_x, size_y, size_z)

    # 2. Isometric rotation angles
    iso_z = math.radians(45.0)
    iso_x = math.radians(-35.2643897)  # arctan(1/sqrt(2))

    # Scale to fit (leave 8% padding on each side)
    scale = (min(width, height) * 0.84) / max_dim

    # Transform each triangle: center → rotate → scale
    transformed = []
    for tri in triangles:
        new_tri = []
        for i in range(0, 9, 3):
            p = (tri[i] - cx, tri[i + 1] - cy, tri[i + 2] - cz)
            p = _rotate_z(p, iso_z)
            p = _rotate_x(p, iso_x)
            new_tri.append(p[0] * scale + width / 2.0)   # screen X
            new_tri.append(-p[2] * scale + height / 2.0)  # screen Y (original Z, flipped)
            new_tri.append(p[1])                          # depth (original Y)
        transformed.append(tuple(new_tri))

    # 3. Compute depth and normal for each triangle (for sorting + shading)
    indexed = []
    for idx, tri in enumerate(transformed):
        v0 = (tri[0], tri[1], tri[2])
        v1 = (tri[3], tri[4], tri[5])
        v2 = (tri[6], tri[7], tri[8])
        ux, uy, uz = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
        vx, vy, vz = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        n_len = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        nx /= n_len
        ny /= n_len
        nz /= n_len
        depth = (tri[2] + tri[5] + tri[8]) / 3.0
        lp = _LIGHT
        lp = _rotate_z(lp, iso_z)
        lp = _rotate_x(lp, iso_x)
        l_len = math.sqrt(lp[0] ** 2 + lp[1] ** 2 + lp[2] ** 2) or 1.0
        lp = (lp[0] / l_len, lp[1] / l_len, lp[2] / l_len)
        dot = nx * lp[0] + ny * lp[1] + nz * lp[2]
        brightness = max(0.25, min(1.0, 0.55 + 0.45 * dot))
        indexed.append((depth, tri, brightness, nx, ny, nz))

    # 4. Sort by depth: larger depth = further away = draw first (painter's algorithm)
    indexed.sort(key=lambda x: -x[0])

    # 5. Render
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    for _depth, tri, brightness, _nx, _ny, _nz in indexed:
        if _ny > 0.05:
            continue
        r = int(model_color[0] * brightness)
        g = int(model_color[1] * brightness)
        b = int(model_color[2] * brightness)
        points = [(tri[0], tri[1]), (tri[3], tri[4]), (tri[6], tri[7])]
        draw.polygon(points, fill=(r, g, b))

    draw.rectangle([(0, 0), (width - 1, height - 1)], outline=(220, 225, 230), width=1)
    img.save(output_path, 'PNG', optimize=True)


def render_stl_thumbnail(stl_path, output_path, width=DEFAULT_THUMB_W, height=DEFAULT_THUMB_H):
    """Public entry point: parse STL file and render to PNG.

    Returns True on success, False on failure (logged).
    """
    try:
        triangles = _parse_stl(stl_path)
        if not triangles:
            logger.warning("STL parsing yielded no triangles: %s", stl_path)
            return False
        _render_stl_to_png(triangles, output_path, width=width, height=height)
        return True
    except Exception as e:
        logger.warning("STL thumbnail render failed for %s: %s", stl_path, e)
        return False
