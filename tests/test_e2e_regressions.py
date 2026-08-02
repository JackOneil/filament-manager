"""Regression tests for bugs found during the post-release E2E sweep (v1.120.4).

These cover defects introduced by the review-fix batches that the existing
suite did not catch:

1. Project undo snapshot/restore used non-existent ProjectPrintItem fields
   (label/print_time_seconds/...) and ProjectComment.author_user_id — the
   restore crashed with TypeError/AttributeError whenever a deleted project
   had print items or comments.
2. The new quote_issue_invoice endpoint was missing from
   auth.SECTION_BY_ENDPOINT — every POST returned 403 (unmapped endpoint).
3. add_brand ignored the shop_url field while edit_brand validated it.
"""
import io
import os
import shutil
import tempfile
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import (
    Brand, Color, Filament, Material, Project, ProjectComment, ProjectPrintItem,
    ProjectQuote, User,
)


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='e2e-reg-')
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
            self.admin = User(
                email='admin@example.com', name='Admin',
                password_hash=hash_password('password123'), role='admin',
            )
            db.session.add(self.admin)
            db.session.commit()
            self.admin_id = self.admin.id
            brand = Brand.query.filter_by(name='Prusament').first()
            material = Material.query.filter_by(name='PLA').first()
            color = Color.query.first()
            self.filament = Filament(
                name='Reg PLA', brand_id=brand.id, material_id=material.id,
                color_id=color.id, weight_total=1000, weight_remaining=1000,
                price=500, quantity=1,
            )
            db.session.add(self.filament)
            db.session.commit()
            self.filament_id = self.filament.id

        self.client.post(
            '/login', data={'email': 'admin@example.com', 'password': 'password123'},
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class ProjectUndoRestoreTests(_Base):
    def test_undo_restores_comments_and_print_items(self):
        """Deleting a project with comments + print items and undoing must
        restore both — the snapshot/restore previously crashed on
        non-existent fields (TypeError/AttributeError)."""
        with self.app.app_context():
            project = Project(name='Undo Me', owner_user_id=self.admin_id,
                              created_by_user_id=self.admin_id, status='NEW')
            db.session.add(project)
            db.session.commit()
            pid = project.id
            db.session.add(ProjectComment(project_id=pid, user_id=self.admin_id, body='hello'))
            db.session.add(ProjectPrintItem(project_id=pid, name='Part A',
                                            quantity_total=2, quantity_done=1))
            db.session.add(ProjectQuote(
                project_id=pid, filament_id=self.filament_id, filament_name='Reg PLA',
                weight=100.0, print_time=2.0, material_cost=50.0, electricity_cost=1.5,
                base_cost=51.5, margin_percent=25.0, margin_amount=12.875,
                final_price=64.375, currency='CZK',
            ))
            db.session.commit()

        r = self.client.post(f'/projects/{pid}/delete')
        self.assertIn(r.status_code, (200, 302))
        with self.app.app_context():
            self.assertIsNone(db.session.get(Project, pid))

        with self.client.session_transaction() as sess:
            pending = sess.get('project_pending_undo')
        self.assertIsNotNone(pending)
        r = self.client.post('/projects/undo', data={'undo_id': pending['undo_log_id']})
        self.assertIn(r.status_code, (200, 302))

        with self.app.app_context():
            restored = Project.query.filter_by(name='Undo Me').first()
            self.assertIsNotNone(restored)
            self.assertGreaterEqual(ProjectComment.query.filter_by(project_id=restored.id).count(), 1)
            self.assertGreaterEqual(ProjectPrintItem.query.filter_by(project_id=restored.id).count(), 1)
            self.assertGreaterEqual(ProjectQuote.query.filter_by(project_id=restored.id).count(), 1)


class QuoteIssueInvoiceTests(_Base):
    def test_issue_invoice_endpoint_is_mapped(self):
        """quote_issue_invoice must be registered in SECTION_BY_ENDPOINT —
        an unmapped endpoint makes the auth guard abort(403) on every POST."""
        from auth import SECTION_BY_ENDPOINT
        self.assertIn('quote_issue_invoice', SECTION_BY_ENDPOINT)

        with self.app.app_context():
            project = Project(name='Inv', owner_user_id=self.admin_id,
                              created_by_user_id=self.admin_id, status='NEW')
            db.session.add(project)
            db.session.commit()
            quote = ProjectQuote(
                project_id=project.id, filament_id=self.filament_id, filament_name='Reg PLA',
                weight=100.0, print_time=2.0, material_cost=50.0, electricity_cost=1.5,
                base_cost=51.5, margin_percent=25.0, margin_amount=12.875,
                final_price=64.375, currency='CZK',
            )
            db.session.add(quote)
            db.session.commit()
            qid = quote.id

        r = self.client.post(f'/calculator/quote/{qid}/issue')
        self.assertIn(r.status_code, (200, 302), 'issue must not be blocked by the auth guard')
        with self.app.app_context():
            quote = db.session.get(ProjectQuote, qid)
            self.assertIsNotNone(quote.invoice_number)

    def test_export_does_not_assign_invoice_on_get(self):
        with self.app.app_context():
            project = Project(name='Inv2', owner_user_id=self.admin_id,
                              created_by_user_id=self.admin_id, status='NEW')
            db.session.add(project)
            db.session.commit()
            quote = ProjectQuote(
                project_id=project.id, filament_id=self.filament_id, filament_name='Reg PLA',
                weight=100.0, print_time=2.0, material_cost=50.0, electricity_cost=1.5,
                base_cost=51.5, margin_percent=25.0, margin_amount=12.875,
                final_price=64.375, currency='CZK',
            )
            db.session.add(quote)
            db.session.commit()
            qid = quote.id

        r = self.client.get(f'/calculator/quote/{qid}/export')
        self.assertEqual(r.status_code, 200)
        with self.app.app_context():
            quote = db.session.get(ProjectQuote, qid)
            self.assertIsNone(quote.invoice_number)


class AddBrandShopUrlTests(_Base):
    def test_add_brand_stores_valid_shop_url(self):
        """add_brand previously dropped shop_url while edit_brand validated it."""
        r = self.client.post('/settings', data={
            'action': 'brand', 'name': 'ShopBrand',
            'shop_url': 'https://shop.example.com',
        })
        self.assertIn(r.status_code, (200, 302))
        with self.app.app_context():
            brand = Brand.query.filter_by(name='ShopBrand').first()
            self.assertIsNotNone(brand)
            self.assertEqual(brand.shop_url, 'https://shop.example.com')

    def test_add_brand_rejects_javascript_shop_url(self):
        self.client.post('/settings', data={
            'action': 'brand', 'name': 'BadShopBrand',
            'shop_url': 'javascript:alert(1)',
        })
        with self.app.app_context():
            brand = Brand.query.filter_by(name='BadShopBrand').first()
            self.assertIsNotNone(brand)
            self.assertIsNone(brand.shop_url)


if __name__ == '__main__':
    unittest.main()
