"""Regression tests: Alpine expressions must survive hostile user data.

Background (BUG-782): the Jinja ``|tojson`` filter returns Markup, so Jinja
does NOT HTML-escape its output. When a ``|tojson`` value was interpolated
into a double-quoted HTML attribute (e.g. ``x-show="...{{ x|tojson }}..."``),
a double quote inside the user data terminated the attribute early. Alpine
then compiled a truncated expression (``!filamentSearch || ``) plus stray
``}`` → ``SyntaxError: Unexpected token '}'`` on the affected pages.

Rule: attributes that interpolate ``|tojson`` MUST use single-quoted HTML
delimiters (``|tojson`` escapes ``'`` as ``\u0027``, making single quotes
safe). These tests render the affected pages with hostile data and verify
the extracted attribute values are complete and syntactically plausible.
"""
import os
import shutil
import tempfile
import unittest
from html.parser import HTMLParser

from app import create_app
from auth import hash_password
from database import db
from models import Brand, Color, Filament, Material, ModelCategory, Project, ProjectFile, User

HOSTILE = 'Heavy" } \' PLA 50%'


class _AttrCollector(HTMLParser):
    """Collects every (name, value) attribute pair from the page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.attrs = []

    def handle_starttag(self, tag, attrs):
        self.attrs.extend(attrs)


class AlpineExpressionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='alpine-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'AUTH_REQUIRED_IN_TESTS': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            admin = User(
                email='admin@example.com', name='Ad"min } X',
                password_hash=hash_password('password123'), role='admin',
            )
            db.session.add(admin)
            db.session.commit()

            brand = Brand.query.filter_by(name='Prusament').first()
            color = Color.query.first()
            material = Material.query.filter_by(name='PLA').first()
            for suffix in ('One', 'Two', 'Three', 'Four'):
                db.session.add(Filament(
                    name=f'{HOSTILE} {suffix}',
                    brand_id=brand.id, color_id=color.id, material_id=material.id,
                    weight_total=1000, weight_remaining=800, price=500, quantity=1,
                ))
            project = Project(name='Proj"ect } X', client_name='ACME" } Ltd', tag_text='proto" } urgent')
            db.session.add(project)
            db.session.commit()
            self.project_id = project.id

            category = ModelCategory(name='Cat" } A')
            db.session.add(category)
            db.session.commit()
            model_file = ProjectFile(
                project_id=project.id, filename='part" } v1.stl', filepath='/tmp/x.stl',
                display_name='Part" } One', category_id=category.id, version=1,
                uploaded_by_user_id=admin.id, version_note='Note " with } braces',
            )
            db.session.add(model_file)
            db.session.commit()
            self.model_id = model_file.id

        self.client.post(
            '/login', data={'email': 'admin@example.com', 'password': 'password123'},
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _attr_values(self, path, name):
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        parser = _AttrCollector()
        parser.feed(resp.data.decode('utf-8'))
        return [value for attr_name, value in parser.attrs if attr_name == name]

    def test_calculator_filament_option_expressions_are_complete(self):
        """x-show on every filament option must contain the full .includes()
        expression — a truncated attribute (broken by an unescaped quote)
        would end right after '||'."""
        xshows = self._attr_values('/calculator', 'x-show')
        option_shows = [v for v in xshows if 'filamentSearch' in v]
        self.assertGreaterEqual(len(option_shows), 4)
        for value in option_shows:
            self.assertTrue(value.startswith('!filamentSearch || '), value)
            self.assertIn('.includes(filamentSearch.toLowerCase())', value)
            self.assertTrue(value.endswith(')'), value)

    def test_calculator_click_expressions_are_complete(self):
        clicks = self._attr_values('/calculator', '@click')
        label_clicks = [v for v in clicks if 'filamentSelectedLabel' in v]
        self.assertGreaterEqual(len(label_clicks), 4)
        for value in label_clicks:
            self.assertIn('filamentSelectedLabel = ', value)
            self.assertIn('dropdownOpen = false', value)

    def test_projects_tag_and_client_expressions_are_complete(self):
        clicks = self._attr_values('/projects', '@click.prevent')
        tag_clicks = [v for v in clicks if 'selectTag(' in v]
        client_clicks = [v for v in clicks if 'selectClient(' in v]
        self.assertEqual(len(tag_clicks), 1)
        self.assertEqual(len(client_clicks), 1)
        # |tojson escapes the double quote as \" — the argument must be a
        # complete, balanced JS string literal.
        self.assertIn('selectTag("proto\\" } urgent")', tag_clicks[0])
        self.assertIn('selectClient("ACME\\" } Ltd")', client_clicks[0])
        # tojson escapes the apostrophe — the argument must be a complete string
        self.assertTrue(tag_clicks[0].strip().endswith(')'))
        self.assertTrue(client_clicks[0].strip().endswith(')'))

    def test_models_index_tag_expressions_are_complete(self):
        # Model cards/rows are rendered via the AJAX endpoint (the index page
        # fetches them client-side), so validate the partial directly.
        resp = self.client.get('/api/models-list')
        self.assertEqual(resp.status_code, 200)
        # The endpoint returns JSON-wrapped HTML — decode it first so the
        # backslashes from |tojson are exactly as the browser would see them.
        import json as _json
        payload = _json.loads(resp.data)
        html = payload.get('html', '')
        self.assertIn('selectTag(', html)
        parser = _AttrCollector()
        parser.feed(html)
        tag_clicks = [v for n, v in parser.attrs if n == '@click.prevent' and 'selectTag(' in v]
        self.assertGreaterEqual(len(tag_clicks), 1)
        for value in tag_clicks:
            # |tojson output inside a single-quoted attribute: the double
            # quote is JSON-escaped (\") and must not terminate the attribute.
            self.assertIn('selectTag(\"proto\\" } urgent\")', value)

    def test_model_detail_load_model_version_is_complete(self):
        clicks = self._attr_values(f'/models/{self.model_id}', '@click')
        load_clicks = [v for v in clicks if 'loadModelVersion(' in v]
        self.assertGreaterEqual(len(load_clicks), 1)
        for value in load_clicks:
            self.assertIn('loadModelVersion(', value)
            self.assertTrue(value.strip().endswith(')'), value)
            self.assertIn('part\\" } v1.stl', value)
            self.assertIn('Note \\" with } braces', value)
            self.assertIn('Ad\\"min } X', value)

    def test_project_detail_page_has_no_truncated_expressions(self):
        """The project detail page renders many Alpine expressions; none of
        the extracted attribute values may be cut off mid-expression."""
        resp = self.client.get(f'/projects/{self.project_id}')
        self.assertEqual(resp.status_code, 200)
        parser = _AttrCollector()
        parser.feed(resp.data.decode('utf-8'))
        for attr_name, value in parser.attrs:
            if attr_name in ('x-show', 'x-data', '@click', '@click.prevent', 'x-text', ':class'):
                # Heuristic: an expression truncated by a stray quote ends
                # with whitespace/operators or contains a lone double quote.
                self.assertFalse(value.endswith('|| '), (attr_name, value))
                self.assertFalse(value.endswith('&& '), (attr_name, value))


if __name__ == '__main__':
    unittest.main()
