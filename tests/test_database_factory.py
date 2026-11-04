import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import importlib.util

from database.factory import create_store
from database.store import Store


class FactoryTests(unittest.TestCase):
    def test_local_defaults_to_sqlite(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"DATABASE_URL": "", "RENDER": "", "LOTTOPREDICT_DATA_DIR": folder}):
            store = create_store()
            self.assertIsInstance(store, Store)
            self.assertEqual(store.count(), 0)

    def test_render_never_silently_falls_back_to_ephemeral_sqlite(self):
        with patch.dict(os.environ, {"DATABASE_URL": "", "RENDER": "true"}):
            with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
                create_store()

    def test_invalid_url_rejected_without_printing_credentials(self):
        with patch.dict(os.environ, {"DATABASE_URL": "mysql://user:secret@host/db"}):
            with self.assertRaises(ValueError) as failure:
                create_store()
            self.assertNotIn("secret", str(failure.exception))

    @unittest.skipUnless(importlib.util.find_spec("psycopg"), "Driver PostgreSQL non installato")
    def test_neon_uses_verified_tls_and_local_tests_can_use_plain_tcp(self):
        from database.postgres import connection_options
        remote = connection_options("postgresql://user:example@ep-test-pooler.eu-central-1.aws.neon.tech/db?sslmode=disable")
        self.assertEqual(remote["sslmode"], "verify-full")
        import certifi
        import ssl
        self.assertEqual(remote["sslrootcert"], certifi.where())
        context = ssl.create_default_context(cafile=remote["sslrootcert"])
        self.assertTrue(context.check_hostname)
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)
        local = connection_options("postgresql://user@127.0.0.1:55432/db?sslmode=disable")
        self.assertEqual(local["sslmode"], "disable")

    @unittest.skipUnless(importlib.util.find_spec("psycopg"), "Driver PostgreSQL non installato")
    def test_explicit_postgres_ca_is_preserved_and_missing_ca_rejected(self):
        import certifi
        from psycopg.conninfo import make_conninfo
        from database.postgres import connection_options
        dsn = "postgresql://user:example@db.example.test/database"
        explicit = make_conninfo(dsn, sslrootcert=certifi.where())
        self.assertEqual(connection_options(explicit)["sslrootcert"], certifi.where())
        with patch.dict(os.environ, {"PGSSLROOTCERT": certifi.where()}):
            self.assertEqual(connection_options(dsn)["sslrootcert"], certifi.where())
        with patch.dict(os.environ, {"PGSSLROOTCERT": "/nonexistent/postgresql-ca.pem"}):
            with self.assertRaisesRegex(ValueError, "bundle CA"):
                connection_options(dsn)
