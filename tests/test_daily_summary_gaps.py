"""Daily summaries retain interior free blocks without adding trailing ones."""
from datetime import date
from email.header import decode_header, make_header
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from ntfy.notifications import NotificationConfig, ScheduleNotifier, NtfyClient
from subscriptions import SubscriptionNotifier, subject_key


class DailySummaryGapTests(unittest.TestCase):
    def test_ntfy_transport_preserves_unicode_and_line_breaks(self):
        message = 'Heute:\n1. Block: Französisch in Hörsaal\n2. Block: -\n3. Block: Entfall (Änderung)'
        title = 'Tagesübersicht – Änderungen'
        for personal in (True, False):
            with self.subTest(personal=personal), patch('requests.post') as post:
                if personal:
                    SubscriptionNotifier(Mock(), 'https://ntfy.invalid')._publish(NS(ntfy_topic='test'), message, title)
                else:
                    NtfyClient(NotificationConfig(classes=('11',))).publish(message, title=title)
                sent = post.call_args.kwargs
                self.assertEqual(sent['data'], message.encode('utf-8'))
                self.assertEqual(str(make_header(decode_header(sent['headers']['Title']))), title)
                self.assertTrue(sent['headers']['Title'].isascii())

    def render(self, periods, cancelled=(), personal=True):
        plan = NS(datum=date(2026, 9, 15), klassen={'11': NS(kurse={}, stunden={
            period: [NS(fach='Mathe', räume=('101',), ausfall=period in cancelled,
                        änderung=period in cancelled, info=None, kursnummer=None)]
            for period in periods
        })})
        if personal:
            notifier = SubscriptionNotifier(Mock(), 'https://ntfy.invalid')
            recipient = NS(selected_classes=['11'], subject_selections={'11': {subject_key('Mathe')}})
            return notifier._daily_summary_lines(recipient, plan)
        notifier = ScheduleNotifier(NotificationConfig(classes=('11',)))
        notifier.client = Mock()
        notifier.send_morning(plan)
        return notifier.client.publish.call_args.args[0].splitlines()[1:]

    def test_gaps_and_trailing_empty_blocks_in_both_summary_paths(self):
        for personal in (True, False):
            for periods, numbers, free in [
                ([1, 5], [1, 2, 3], [2]),
                ([1, 7], [1, 2, 3, 4], [2, 3]),
                ([1, 3, 7], [1, 2, 3, 4], [3]),
                ([1, 3], [1, 2], []),
                ([1], [1], []),
                ([], [], []),
                ([4], [1, 2], [1]),
            ]:
                with self.subTest(personal=personal, periods=periods):
                    lines = self.render(periods, personal=personal)
                    self.assertEqual([int(line.split('.')[0]) for line in lines], numbers)
                    self.assertEqual([line for line in lines if line.endswith(' -')],
                                     [f'{number}. Block: -' for number in free])

    def test_explicit_cancellation_is_preserved_even_at_end(self):
        for personal in (True, False):
            lines = self.render([1, 5], cancelled=[5], personal=personal)
            self.assertEqual(lines[1], '2. Block: -')
            self.assertIn('Entfall', lines[2])
            self.assertEqual(len(lines), 3)

    def test_unselected_courses_do_not_extend_personal_day(self):
        notifier = SubscriptionNotifier(Mock(), 'https://ntfy.invalid')
        recipient = NS(selected_classes=['11'], subject_selections={'11': {subject_key('Mathe')}})
        lesson = lambda subject: NS(fach=subject, räume=('101',), ausfall=False, änderung=False, kursnummer=None)
        plan = NS(klassen={'11': NS(kurse={}, stunden={1: [lesson('Mathe')], 7: [lesson('Deutsch')]})})
        self.assertEqual(len(notifier._daily_summary_lines(recipient, plan)), 1)
