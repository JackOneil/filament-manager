"""Tests for the automatic STL thumbnail renderer."""
import os
import struct
import tempfile
import unittest

from routes.model_renderer import (
    _parse_binary_stl,
    _parse_ascii_stl,
    _parse_stl,
    render_stl_thumbnail,
    _render_stl_to_png,
    MAX_TRIANGLES,
)


def _make_binary_stl(path, triangles_data):
    """Write a list of 9-tuples as a binary STL file."""
    with open(path, 'wb') as f:
        f.write(b'Test STL' + b' ' * 72)  # 80-byte header
        f.write(struct.pack('<I', len(triangles_data)))
        for tri in triangles_data:
            # Normal + 3 vertices + attribute count
            f.write(struct.pack('<3f', 0.0, 0.0, 1.0))
            f.write(struct.pack('<9f', *tri))
            f.write(struct.pack('<H', 0))


def _cube_triangles():
    """Return 12 triangles forming a unit cube centered at the origin."""
    # 8 vertices of a unit cube centered at (0,0,0)
    v = [
        (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5),
    ]
    # 12 triangles (2 per face)
    faces = [
        (0, 1, 2), (0, 2, 3),  # front
        (5, 4, 7), (5, 7, 6),  # back
        (4, 0, 3), (4, 3, 7),  # left
        (1, 5, 6), (1, 6, 2),  # right
        (3, 2, 6), (3, 6, 7),  # top
        (4, 5, 1), (4, 1, 0),  # bottom
    ]
    triangles = []
    for (a, b, c) in faces:
        triangles.append(v[a] + v[b] + v[c])
    return triangles


class ParseBinaryStlTests(unittest.TestCase):
    def test_parses_valid_cube(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'cube.stl')
            tris = _cube_triangles()
            _make_binary_stl(path, tris)
            parsed = _parse_stl(path)
            self.assertEqual(len(parsed), 12)

    def test_rejects_truncated_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'bad.stl')
            with open(path, 'wb') as f:
                f.write(b'X' * 80)  # header only, no triangle data
            with self.assertRaises(Exception):
                _parse_stl(path)


class ParseAsciiStlTests(unittest.TestCase):
    def test_parses_ascii_cube(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'ascii.stl')
            lines = [
                'solid cube',
                '  facet normal 0.0 0.0 1.0',
                '    outer loop',
                '      vertex 0.0 0.0 0.0',
                '      vertex 1.0 0.0 0.0',
                '      vertex 0.0 1.0 0.0',
                '    endloop',
                '  endfacet',
                '  facet normal 0.0 0.0 1.0',
                '    outer loop',
                '      vertex 1.0 0.0 0.0',
                '      vertex 1.0 1.0 0.0',
                '      vertex 0.0 1.0 0.0',
                '    endloop',
                '  endfacet',
                'endsolid cube',
            ]
            with open(path, 'w') as f:
                f.write('\n'.join(lines))
            parsed = _parse_stl(path)
            self.assertEqual(len(parsed), 2)


class ParseStlTests(unittest.TestCase):
    def test_auto_detect_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'bin.stl')
            tris = _cube_triangles()
            _make_binary_stl(path, tris)
            parsed = _parse_stl(path)
            self.assertEqual(len(parsed), 12)

    def test_returns_empty_for_missing_file(self):
        with self.assertRaises((FileNotFoundError, OSError)):
            _parse_stl('/tmp/nonexistent_xyz.stl')


class RenderStlToPngTests(unittest.TestCase):
    def test_renders_cube(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, 'out.png')
            _render_stl_to_png(_cube_triangles(), out_path)
            self.assertTrue(os.path.isfile(out_path))
            self.assertGreater(os.path.getsize(out_path), 100)

    def test_renders_custom_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, 'out_thumb.png')
            _render_stl_to_png(_cube_triangles(), out_path, width=200, height=150)
            self.assertTrue(os.path.isfile(out_path))

    def test_handles_renders_failure_gracefully(self):
        result = render_stl_thumbnail('/tmp/nonexistent_xyz.stl', '/tmp/out.png')
        self.assertFalse(result)


class RenderIntegrationTests(unittest.TestCase):
    def test_tetrahedron_renders(self):
        # Manually build a tetrahedron
        # Vertex coordinates
        v0 = (0.0, 0.0, 0.0)
        v1 = (1.0, 0.0, 0.0)
        v2 = (0.5, 0.866, 0.0)
        v3 = (0.5, 0.289, 0.816)
        tri0 = v0 + v1 + v2
        tri1 = v0 + v2 + v3
        tri2 = v0 + v3 + v1
        tri3 = v1 + v3 + v2

        with tempfile.TemporaryDirectory() as tmp:
            stl_path = os.path.join(tmp, 'tetra.stl')
            _make_binary_stl(stl_path, [tri0, tri1, tri2, tri3])
            out_path = os.path.join(tmp, 'tetra.png')
            self.assertTrue(render_stl_thumbnail(stl_path, out_path))
            self.assertTrue(os.path.isfile(out_path))
            self.assertGreater(os.path.getsize(out_path), 100)
