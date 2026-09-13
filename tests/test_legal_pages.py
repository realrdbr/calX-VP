from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from legal import legal_data, render_legal_page, render_legal_text
from main import AppRequestHandler
from web_utils import send_html, SESSION_WATCH_SCRIPT


class LegalPageTests(unittest.TestCase):
    def test_runtime_contact_is_escaped_and_used_in_both_pages(self):
        with patch.dict('os.environ', {'PRIVACY_CONTROLLER': '<script>Person</script>', 'PRIVACY_ADDRESS': 'Musterweg 1', 'SUPPORT_MAIL': 'help@example.test'}):
            for imprint in (False, True):
                page = render_legal_page(imprint=imprint)
                self.assertIn('&lt;script&gt;Person&lt;/script&gt;', page)
                self.assertNotIn('<script>Person</script>', page)
                self.assertIn('Musterweg 1', page)
                self.assertIn('help@example.test', page)
            self.assertIn('Quellcode auf GitHub', render_legal_page(info=True))

    def test_legal_routes_are_accessible_without_a_session(self):
        for path in ('/datenschutz', '/impressum'):
            handler = Mock()
            handler.path = path
            with patch('main.send_html') as send:
                AppRequestHandler.do_GET(handler)
            send.assert_called_once()
            handler._session.assert_not_called()

    def test_public_pages_have_footer_without_login_redirect_script(self):
        handler = Mock()
        handler.path = '/impressum'
        handler.wfile = BytesIO()
        send_html(handler, render_legal_page(imprint=True))
        page = handler.wfile.getvalue().decode()
        for path in ('/datenschutz', '/impressum'):
            self.assertIn(f'href="{path}"', page)
        self.assertNotIn(SESSION_WATCH_SCRIPT, page)

    def test_environment_punctuation_is_not_duplicated(self):
        for value in ('Text', 'Text.', 'Text. ', 'Text!', 'Text?','Text…'):
            expected = value.strip() + ('.' if value == 'Text' else '')
            self.assertEqual(render_legal_text('{VALUE}. Danach.', {'VALUE': value}), expected + ' Danach.')

    def test_info_opens_as_a_dialog(self):
        handler = Mock()
        handler.path = '/impressum'
        handler.wfile = BytesIO()
        send_html(handler, render_legal_page(imprint=True))
        page = handler.wfile.getvalue().decode()
        self.assertIn('data-info-open', page)
        self.assertEqual(page.count('<dialog '), 1)
        self.assertNotIn('href="/info"', page)
