from datetime import date
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock
import requests
import pytest
import school_calendar as sc

BASIS = b'''<splan><Sw SwDatumVon="05.10.2026" SwDatumBis="09.10.2026">8</Sw>
<Sw SwDatumVon="26.10.2026" SwDatumBis="30.10.2026">9</Sw>
<Sw SwDatumVon="02.11.2026" SwDatumBis="06.11.2026">10</Sw></splan>'''

@pytest.fixture(autouse=True)
def isolate():
    with patch.object(sc, '_weeks', ()), patch.object(sc, '_last_attempt', None):
        yield


def test_navigation_skips_published_index_gaps_both_directions():
    sc._weeks = sc.parse_school_weeks(BASIS)
    assert sc.adjacent_school_week(date(2026, 10, 5)) == date(2026, 10, 26)
    assert sc.adjacent_school_week(date(2026, 10, 26), -1) == date(2026, 10, 5)
    assert sc.school_week(date(2026, 10, 12)) == date(2026, 10, 26)
    assert sc.school_week(date(2026, 10, 21)) == date(2026, 10, 26)
    assert sc.adjacent_school_week(date(2026, 11, 2)) == date(2026, 11, 2)


def test_all_three_navigation_paths_use_teaching_weeks():
    from plan_page import render_week_navigation
    from teacher_page import render_week_navigation as teacher_navigation
    sc._weeks = sc.parse_school_weeks(BASIS)
    for html in [render_week_navigation(date(2026, 10, 5), '11'),
                 teacher_navigation(date(2026, 10, 5), 'AB'),
                 teacher_navigation(date(2026, 10, 5), 'H3', route='/raeume', selection_key='raum')]:
        assert 'woche=2026-W44' in html
        assert 'woche=2026-W42' not in html


def test_index_failure_preserves_valid_cache_and_does_not_invent_holidays():
    with TemporaryDirectory() as directory:
        response = Mock(content=BASIS)
        with patch('school_calendar.requests.get', return_value=response):
            sc.refresh_school_weeks('school', 'user', 'secret', directory)
        sc._weeks = (); sc._last_attempt = None
        with patch('school_calendar.requests.get', side_effect=requests.Timeout):
            sc.refresh_school_weeks('school', 'user', 'secret', directory)
        assert sc.adjacent_school_week(date(2026, 10, 5)) == date(2026, 10, 26)
    sc._weeks = ()
    assert sc.adjacent_school_week(date(2026, 10, 5)) == date(2026, 10, 12)


def test_room_catalogue_uses_week_after_holidays():
    from room_schedule_page import render_room_schedule_page
    from types import SimpleNamespace as NS
    sc._weeks = sc.parse_school_weeks(BASIS)
    with patch('room_schedule_page.get_week_plans_for_page', return_value={}) as daily, \
         patch('room_schedule_page.get_official_weekly_plans_for_page', return_value={}):
        render_room_schedule_page(date(2026, 10, 5))
    assert daily.call_args_list[1].args == (date(2026, 10, 26),)


def test_empty_index_is_not_a_holiday_calendar():
    with pytest.raises(ValueError):
        sc.parse_school_weeks(b'<splan/>')


@pytest.mark.parametrize('path', ['/', '/lehrer', '/raeume'])
def test_direct_holiday_week_url_redirects_without_losing_selection(path):
    from main import AppRequestHandler
    from types import SimpleNamespace as NS
    from urllib.parse import parse_qs, urlparse
    sc._weeks = sc.parse_school_weeks(BASIS)
    handler = Mock(path=path + '?woche=2026-W42&raum=H3&lehrer=AB&klasse=11&block=1')
    handler._session.return_value = NS(user=NS(must_change_pin=False))
    with patch('school_calendar.refresh_school_weeks'), patch('main.redirect') as redirect:
        AppRequestHandler.do_GET(handler)
    target = urlparse(redirect.call_args.args[1])
    assert target.path == path
    query = parse_qs(target.query)
    assert query['woche'] == ['2026-W44']
    assert query['raum'] == ['H3']
    assert query['block'] == ['1']


def test_missing_session_is_rejected_before_index_access():
    from main import AppRequestHandler
    handler = Mock(path='/raeume?woche=2026-W42')
    handler._session.return_value = None
    with patch('school_calendar.refresh_school_weeks') as refresh, patch('main.redirect') as redirect:
        AppRequestHandler.do_GET(handler)
    refresh.assert_not_called()
    assert redirect.call_args.args[1] == '/login'


def test_free_room_urls_are_canonicalized():
    from main import AppRequestHandler
    from types import SimpleNamespace as NS
    handler = Mock(path='/raeume?woche=2026-W38&raum=H3&frei=1')
    handler._session.return_value = NS(user=NS(must_change_pin=False))
    with patch('school_calendar.refresh_school_weeks'), patch('main.redirect') as redirect:
        AppRequestHandler.do_GET(handler)
    target = redirect.call_args.args[1]
    assert target.startswith('/raeume?frei=1&datum=2026-09-14&stunde=')


def test_teacher_catalogue_uses_next_teaching_week_and_heading():
    from teacher_page import render_teacher_page
    sc._weeks = sc.parse_school_weeks(BASIS)
    with patch('teacher_page.get_week_plans_for_page', return_value={}) as load:
        html = render_teacher_page(date(2026, 10, 5))
    assert load.call_args_list[1].args == (date(2026, 10, 26),)
    assert '<h1>Lehrerplan</h1>' in html
