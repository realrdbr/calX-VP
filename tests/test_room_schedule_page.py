from datetime import date, datetime, timedelta, time
from types import SimpleNamespace as NS
from unittest.mock import patch
from html import unescape

from room_schedule_page import available_rooms, room_table_plans, render_room_schedule_page
from teacher_page import collect_teacher_lessons
from rooms_page import render_rooms_page

DAY = date(2026, 9, 14)


def lesson(room, subject='Mathe'):
    return NS(räume=(room,), fach=subject, lehrer=('AB',), beginn=time(8), ende=time(9),
              änderung=False, ausfall=False, info='Stundeninfo <sicher>')


def plan(*lessons):
    return NS(klassen={'11a': NS(stunden={1: list(lessons)})}, zeitstempel=datetime(2026, 9, 14, 7),
              zusatzinfo='Tagesinfo <sicher>', zeitplan={})


def test_catalogue_collects_both_weeks_and_sorts_numeric_and_named_rooms():
    assert available_rooms({DAY: plan(lesson('10'), lesson('2'), lesson('-'))},
                           {DAY + timedelta(days=7): plan(lesson('Sporthalle'), lesson('2'))}) == ['2', '10', 'Sporthalle']


def test_room_filter_preserves_popup_details_and_missing_days():
    adapted = room_table_plans({DAY: plan(lesson('101'), lesson('102', 'Deutsch')), DAY + timedelta(days=1): None})
    items = collect_teacher_lessons(adapted, '101')[1][DAY]
    assert len(items) == 1
    assert items[0].fach == 'Mathe'
    assert items[0].klassen == ('11a',)
    assert items[0].lehrer == ('AB',)
    assert adapted[DAY].zusatzinfo == 'Tagesinfo <sicher>'
    assert adapted[DAY + timedelta(days=1)] is None


def test_room_page_reuses_table_and_includes_rooms_from_next_normal_week():
    week = {DAY + timedelta(days=i): plan(lesson('101')) if i == 0 else None for i in range(5)}
    following = {DAY + timedelta(days=7): plan(lesson('201'))}
    with patch('room_schedule_page.get_week_plans_for_page', side_effect=[week, following]), \
         patch('room_schedule_page.get_official_weekly_plans_for_page', side_effect=[week, following]) as normal:
        html = render_room_schedule_page(DAY, '201')
    assert normal.call_args_list[1].args == (DAY + timedelta(days=7),)
    assert '<title>Raumplan</title>' in html
    assert 'Raum 201' in html
    assert 'class="week-table"' in html  # empty room still has the entire week's grid
    assert html.count('class="period-head">') == 9
    assert 'Tagesinfo &lt;sicher&gt;' in html
    assert '/raeume?woche=' in unescape(html)
    assert 'Freie Räume' in html
    assert '<div class="room-view-switch"><a ' in html


def test_room_labels_are_escaped_and_urls_encoded():
    room = '\"><script>alert(1)</script>'
    week = {DAY: plan(lesson(room))}
    with patch('room_schedule_page.get_week_plans_for_page', return_value=week), \
         patch('room_schedule_page.get_official_weekly_plans_for_page', return_value=week):
        html = render_room_schedule_page(DAY, room)
    assert '<script>alert(1)</script>' not in html
    assert '%3Cscript%3E' in html
    assert 'Stundeninfo &lt;sicher&gt;' in html


def test_free_room_switch_stays_on_same_route_and_keeps_free_mode_on_submit():
    html = render_rooms_page(DAY, 1, [101])
    assert 'href="/raeume?woche=2026-W38"' in html
    assert '>Raumplan</a>' in html
    assert '<div class="room-view-switch"><a ' in html


def test_missing_next_week_does_not_hide_existing_room_schedule():
    from vp_data import ResourceNotFound
    week = {DAY: plan(lesson('101'))}
    with patch('room_schedule_page.get_week_plans_for_page', side_effect=[week, ResourceNotFound('missing')]), \
         patch('room_schedule_page.get_official_weekly_plans_for_page', side_effect=[week, ResourceNotFound('missing')]):
        html = render_room_schedule_page(DAY, '101')
    assert 'Raum 101' in html
    assert 'Nicht alle Plandaten' in html
    assert 'class="week-table"' in html


def test_main_room_handler_selects_schedule_by_default_and_preserves_auth_flags():
    from main import AppRequestHandler
    from unittest.mock import Mock
    handler = Mock()
    handler._cookies.return_value = {'selected_room': '101'}
    session = NS(csrf_token='csrf')
    handler._session.return_value = session
    handler._nav_flags.return_value = {'session_username': 'alice', 'force_pin_change': False}
    with patch('main.render_room_schedule_page', return_value='room html') as render, patch('main.send_html') as send:
        AppRequestHandler.handle_rooms_page(handler, {'woche': ['2026-W38']})
    assert render.call_args.args[1] == '101'
    assert render.call_args.kwargs['session_username'] == 'alice'
    assert render.call_args.kwargs['logout_csrf_token'] == 'csrf'
    assert send.call_args.args[1] == 'room html'


def test_main_free_room_mode_does_not_redirect():
    from main import AppRequestHandler
    from unittest.mock import Mock
    handler = Mock()
    handler._session.return_value = None
    with patch('main.get_room_plan_for_page', return_value=None), \
         patch('main.render_rooms_page', return_value='free html') as render, \
         patch('main.send_html') as send, patch('main.redirect') as redirect:
        AppRequestHandler.handle_rooms_page(handler, {'frei': ['1'], 'woche': ['2026-W38']})
    assert render.call_args.args[0] == DAY
    assert send.call_args.args[1] == 'free html'
    redirect.assert_not_called()
