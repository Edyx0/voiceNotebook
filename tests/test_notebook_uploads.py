from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from notebook_uploads import configure_file_uploads


class NotebookUploadTests(unittest.TestCase):
    def test_uploads_use_selected_numeric_account_instead_of_email(self):
        uploader = SimpleNamespace(_auth=SimpleNamespace(authuser=2, account_email='chosen@example.test'))
        client = SimpleNamespace(sources=SimpleNamespace(_uploader=uploader))
        configure_file_uploads(client)
        self.assertEqual(uploader._authuser_query(), 'authuser=2')
        self.assertEqual(uploader._authuser_header(), '2')
        uploader._auth.authuser = 3
        self.assertEqual(uploader._authuser_header(), '3')

    def test_sdk_upload_streaming_and_reconciliation_are_unchanged(self):
        native_upload = AsyncMock()
        native_registration = AsyncMock()
        uploader = SimpleNamespace(_auth=SimpleNamespace(authuser=0), register_file_source=native_registration)
        client = SimpleNamespace(sources=SimpleNamespace(_uploader=uploader, add_file=native_upload))
        configure_file_uploads(client)
        self.assertIs(client.sources.add_file, native_upload)
        self.assertIs(uploader.register_file_source, native_registration)

    def test_adapters_without_sdk_uploader_are_unchanged(self):
        native_upload = AsyncMock()
        client = SimpleNamespace(sources=SimpleNamespace(add_file=native_upload))
        configure_file_uploads(client)
        self.assertIs(client.sources.add_file, native_upload)


if __name__ == '__main__':
    unittest.main()
