"""Fixture artificiali: i test non scaricano risultati reali."""
from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from data_sources.lotto_api import ApiHistory, BASE, CALENDAR, DAY_PREFIX, EXTRACTION, PROGRESS_KEY, parse_extraction
from data_sources.lotto_official import WHEELS
from database.store import Store
from games.rules import RuleRegistry


def response(day):
    return {'esito': 'OK', 'data': int(datetime(day.year, day.month, day.day, tzinfo=ZoneInfo('Europe/Rome')).timestamp() * 1000),
            'estrazione': [{'ruota': code, 'numeri': [1, 2, 3, 4, 5]} for code in WHEELS if code != 'NZ']}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rules = RuleRegistry()
        self.store = Store(Path(self.temp.name) / 'api.sqlite3', self.rules)
        self.calls = []
        self.fail_day = None

    def request(self, name, body):
        self.calls.append((name, body))
        if name == CALENDAR:
            return [1, 2, 3, 4], 'calendar-fixture'
        day = datetime.strptime(body['data'], '%Y%m%d').date()
        if day == self.fail_day:
            raise OSError('Errore artificiale')
        return response(day), 'fixture-digest'

    def fetch(self, limit=4):
        return ApiHistory(self.store, self.request, date(2025, 1, 5)).fetch(self.rules, limit)

    def test_full_window_persists_and_resume_reuses_older_days(self):
        draws, metadata = self.fetch()
        self.assertEqual(len(draws), 44)
        self.assertEqual(self.store.count(), 44)
        self.assertEqual(self.store.count(True), 0)
        self.assertEqual(metadata['downloaded_days'], 4)
        self.assertEqual(metadata['covered_days'], ['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-04'])
        self.assertTrue(all(d.date_precision == 'date' and d.source == BASE + EXTRACTION for d in draws))
        self.calls.clear()
        reopened = Store(self.store.path, self.rules)
        _, second = ApiHistory(reopened, self.request, date(2025, 1, 5)).fetch(self.rules, 4)
        self.assertEqual(second['progressive_inserted'], 0)
        self.assertEqual(second['reused_days'], 2)
        self.assertEqual(sum(name == EXTRACTION for name, _ in self.calls), 2)

    def test_failure_preserves_valid_days_but_does_not_claim_full_window(self):
        self.fail_day = date(2025, 1, 2)
        with self.assertRaisesRegex(ValueError, '2 di 4'):
            self.fetch()
        self.assertEqual(self.store.count(), 22)
        self.assertEqual(self.store.sync_info(PROGRESS_KEY)['state'], 'failed')
        self.assertIsNone(self.store.sync_info(DAY_PREFIX + '2025-01-02'))
        self.fail_day = None
        self.fetch()
        self.assertEqual(self.store.count(), 44)
        self.assertEqual(self.store.sync_info(PROGRESS_KEY)['state'], 'completed')

    def test_wrong_date_duplicate_wheels_or_numbers_fail_without_writes(self):
        day = date(2025, 1, 1)
        for modify in (lambda r: r.update(data=0), lambda r: r['estrazione'][0].update(numeri=[1, 1, 2, 3, 4]),
                       lambda r: r['estrazione'][0].update(ruota='CA')):
            body = response(day)
            modify(body)
            with self.assertRaises(ValueError):
                parse_extraction(body, day, self.rules)
        self.assertEqual(self.store.count(), 0)

    def test_correction_is_detected_without_overwriting(self):
        self.fetch()
        def corrected(name, body):
            result, digest = self.request(name, body)
            if name == EXTRACTION:
                result['estrazione'][0]['numeri'] = [6, 7, 8, 9, 10]
            return result, digest
        with self.assertRaisesRegex(ValueError, 'conflitto'):
            ApiHistory(self.store, corrected, date(2025, 1, 5)).fetch(self.rules, 4)
        self.assertEqual(self.store.history('Lotto', 'ordinario', 'Bari')[0].numbers, (1, 2, 3, 4, 5))

    def test_unavailable_past_draw_does_not_shrink_requested_window(self):
        def unavailable(name, body):
            if name == EXTRACTION and body['data'] == '20250102':
                return {'esito': 'KO'}, 'fixture'
            return self.request(name, body)
        with self.assertRaisesRegex(ValueError, '2 di 4'):
            ApiHistory(self.store, unavailable, date(2025, 1, 5)).fetch(self.rules, 4)
        self.assertEqual(self.store.sync_info(PROGRESS_KEY)['completed'], 2)

    def test_today_incomplete_is_skipped_but_other_malformed_data_fails(self):
        def incomplete(name, body):
            result, digest = self.request(name, body)
            if name == EXTRACTION and body['data'] == '20250104':
                result['estrazione'].pop()
            return result, digest
        _, metadata = ApiHistory(self.store, incomplete, date(2025, 1, 4)).fetch(self.rules, 2)
        self.assertTrue(metadata['partial_latest'])
        self.assertEqual(metadata['latest_day'], '2025-01-03')

    def test_sync_uses_api_and_success_metadata_only_after_requested_coverage(self):
        from data_sources.sync import KEY, Synchronizer
        with patch('data_sources.lotto_api.ApiHistory', return_value=ApiHistory(self.store, self.request, date(2025, 1, 5))):
            result = Synchronizer(self.store).ensure('Lotto', 'ordinario', 'Roma', 4)
        self.assertEqual(result['inserted'], 44)
        self.assertEqual(result['duplicates'], 0)
        self.assertEqual(result['connector'], 'official_api_v1')
        self.assertEqual(len(self.store.sync_info(KEY)['covered_days']), 4)


class TransportTests(unittest.TestCase):
    def test_retry_transient_error_and_reject_access_denials(self):
        from unittest.mock import MagicMock
        from urllib.error import HTTPError
        from data_sources.lotto_api import post
        response = MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = BASE + CALENDAR
        response.read.return_value = b'[]'
        opener = MagicMock()
        opener.open.side_effect = [HTTPError(BASE, 503, 'temporary', {}, None), response]
        with patch('data_sources.lotto_api.build_opener', return_value=opener), patch('data_sources.lotto_api.time.sleep') as pause:
            self.assertEqual(post(CALENDAR, {})[0], [])
            self.assertEqual(opener.open.call_count, 2)
            pause.assert_called_once()
        opener.open.reset_mock()
        opener.open.side_effect = HTTPError(BASE, 403, 'denied', {}, None)
        with patch('data_sources.lotto_api.build_opener', return_value=opener), patch('data_sources.lotto_api.time.sleep') as pause:
            with self.assertRaises(HTTPError):
                post(CALENDAR, {})
            self.assertEqual(opener.open.call_count, 1)
            pause.assert_not_called()

    def test_tls_failure_is_never_retried_or_bypassed(self):
        import ssl
        from urllib.error import URLError
        from unittest.mock import Mock
        from data_sources.lotto_api import post
        opener = Mock()
        opener.open.side_effect = URLError(ssl.SSLCertVerificationError('invalid certificate'))
        with patch('data_sources.lotto_api.build_opener', return_value=opener), patch('data_sources.lotto_api.time.sleep') as pause:
            with self.assertRaises(URLError):
                post(CALENDAR, {})
            self.assertEqual(opener.open.call_count, 1)
            pause.assert_not_called()
