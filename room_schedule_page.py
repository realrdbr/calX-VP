"""Room schedules using the shared teacher-plan table and page shell."""
from datetime import timedelta
from school_calendar import adjacent_school_week
from html import escape
import re
from types import SimpleNamespace
from urllib.parse import urlencode

from lesson_status import has_value
from teacher_page import (_normalize_teacher_lesson, render_teacher_page,
                          render_teacher_week_table, render_week_navigation)
from vp_data import get_week_plans_for_page, get_official_weekly_plans_for_page, ResourceNotFound
from web_utils import format_week_value


def room_assignments(plan):
    """Read class data first; teacher-only exports are also supported."""
    classes = getattr(plan, 'klassen', {})
    sources = classes.items() if classes else getattr(plan, 'lehrer', {}).items()
    seen = set()
    for name, item in sources:
        for period, lessons in getattr(item, 'stunden', {}).items():
            for lesson in lessons:
                normalized = _normalize_teacher_lesson(lesson, name if classes else '')
                for raw_room in getattr(lesson, 'räume', ()):
                    if not has_value(raw_room):
                        continue
                    room = str(raw_room).strip()
                    key = (room, int(period), repr(vars(normalized)) if hasattr(normalized, '__dict__') else repr(normalized))
                    if key not in seen:
                        seen.add(key)
                        yield room, int(period), normalized


def available_rooms(*weeks):
    rooms = {room for week in weeks for plan in week.values() if plan is not None
             for room, _, _ in room_assignments(plan)}
    return sorted(rooms, key=lambda room: [(0, int(part)) if part.isdigit() else (1, part.casefold())
                                         for part in re.split(r'(\d+)', room)])


def room_table_plans(week):
    result = {}
    for day, plan in week.items():
        if plan is None:
            result[day] = None
            continue
        rooms = {}
        for room, period, lesson in room_assignments(plan):
            rooms.setdefault(room, SimpleNamespace(stunden={})).stunden.setdefault(period, []).append(lesson)
        # The shared table indexes a named timetable through `lehrer`; the actual
        # lesson's teachers, classes and rooms remain intact for the detail popup.
        result[day] = SimpleNamespace(lehrer=rooms, zeitstempel=getattr(plan, 'zeitstempel', None),
                                     zusatzinfo=getattr(plan, 'zusatzinfo', None),
                                     zeitplan=getattr(plan, 'zeitplan', {}))
    return result


def room_view_switch(selected_date, selected_room=None, *, free=False):
    fields = {'woche': format_week_value(selected_date)} if free else {
        'frei': '1', 'datum': selected_date.isoformat(), 'stunde': '1',
    }
    if free and selected_room:
        fields['raum'] = selected_room
    target = '/raeume?' + urlencode(fields)
    label = 'Raumplan' if free else 'Freie Räume'
    return f'''<style>
      .room-view-switch {{ margin: 12px 0; }}
            .room-view-switch a {{ display: inline-flex; align-items: center; justify-content: center;
                padding: 10px 14px; border: 1px solid var(--primary); border-radius: 8px;
                background: var(--surface-muted); color: var(--text); font-weight: 700; text-decoration: none; }}
            .room-view-switch a:hover {{ background: var(--surface); border-color: var(--primary); }}
            .room-view-switch a:focus-visible {{ outline: 2px solid var(--primary); outline-offset: 3px; }}
    .room-toolbar {{ display: grid; grid-template-columns: minmax(0, 1fr) auto auto auto; column-gap: 12px; align-items: center; margin-bottom: 12px; }}
      .room-toolbar > .room-view-switch {{ grid-column: 2; grid-row: 1; z-index: 1; margin: 0; }}
      .room-toolbar > .class-message {{ grid-column: 1 / -1; grid-row: 1; display: grid;
        grid-template-columns: subgrid; align-items: center; margin-bottom: 0; }}
      .room-toolbar .room-heading {{ grid-column: 1; margin: 0; }}
      .room-toolbar .block-switch {{ grid-column: 3; }}
      .room-toolbar .class-select {{ grid-column: 4; }}
      .free-room-controls {{ display: grid; grid-template-columns: minmax(160px, 1fr) minmax(100px, 1fr) 170px 184px;
        gap: 12px; align-items: end; width: 100%; min-width: 0; }}
      .free-room-controls > .room-view-switch {{ margin: 0; grid-column: 4; transform: translateY(1px); }}
            .free-room-controls > .room-view-switch a {{ width: 100%; justify-content: center;
        height: 40px; min-height: 40px; padding: 0 12px; border-radius: 6px; box-sizing: border-box; }}
      .free-room-controls > .form-row {{ margin: 0; display: grid; grid-column: 1 / 4; grid-template-columns: subgrid; }}
      .free-room-controls > .form-row > button {{ width: 100%; height: 38px; min-height: 38px; }}
      @media (max-width: 1000px) {{
        .room-toolbar {{ display: flex; flex-direction: column; align-items: stretch; gap: 12px; }}
        .room-toolbar > .room-view-switch, .room-toolbar > .room-view-switch a {{ width: 100%; box-sizing: border-box; }}
        .room-toolbar > .class-message {{ display: flex; flex-wrap: wrap; }}
      }}
      @media (max-width: 1000px) {{
        .free-room-controls {{ grid-template-columns: minmax(0, 1fr); }}
        .free-room-controls > .form-row {{ grid-column: 1; grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        .free-room-controls > .form-row > button {{ grid-column: 1 / -1; }}
        .free-room-controls > .room-view-switch {{ grid-column: 1; width: 100%; transform: none; }}
        .free-room-controls > .room-view-switch a {{ height: 40px; min-height: 40px; }}
      }}
      @media (max-width: 620px) {{
        .free-room-controls > .form-row {{ grid-template-columns: minmax(0, 1fr); }}
      }}
    </style><div class="room-view-switch"><a href="{escape(target, quote=True)}">{label}</a></div>'''


def render_room_schedule_page(selected_date, selected_room=None, *, block_mode=False, error_message=None, **flags):
    navigation = render_week_navigation(selected_date, selected_room, block_mode, route='/raeume', selection_key='raum')
    switch = room_view_switch(selected_date, selected_room)
    if error_message:
        return render_teacher_page(selected_date, error_message=error_message, page_title='Raumplan',
                                   page_active='rooms', page_navigation=navigation + switch, **flags)
    week = get_week_plans_for_page(selected_date)
    missing_normal = False
    try:
        next_week = get_week_plans_for_page(adjacent_school_week(selected_date))
    except ResourceNotFound:
        next_week = {}
        missing_normal = True
    catalogues = [week, next_week]
    for anchor in (selected_date, adjacent_school_week(selected_date)):
        try:
            catalogues.append(get_official_weekly_plans_for_page(anchor))
        except ResourceNotFound:
            missing_normal = True
    rooms = available_rooms(*catalogues)

    def url(room, **extra):
        return '/raeume?' + urlencode({'woche': format_week_value(selected_date), 'raum': room,
                                      'block': '1' if block_mode else '0', **extra})

    content = ""
    if missing_normal:
        content += '<p class="empty">Nicht alle Plandaten der zwei Wochen sind verfügbar. Die Raumauswahl enthält die Räume der verfügbaren Plandaten.</p>'
    if selected_room not in rooms:
        content += switch + '<section class="message"><h2>Raum auswählen</h2></section><section class="choice-grid">'
        content += ''.join(f'<a class="choice-card" href="{escape(url(room), quote=True)}">{escape(room)}</a>' for room in rooms)
        content += '</section>'
        if not rooms:
            content += '<p class="empty">In diesen zwei Wochen wurden keine Räume gefunden.</p>'
    else:
        options = ''.join(f'<option value="{escape(url(room), quote=True)}" {"selected" if room == selected_room else ""}>{escape(room)}</option>' for room in rooms)
        content += f'''<div class="room-toolbar">{switch}<section class="message class-message"><h2 class="room-heading">Raum {escape(selected_room)}</h2>
          <label class="block-switch"><span>Block-Unterricht</span><input type="checkbox" {'checked' if block_mode else ''}
          data-url="{escape(url(selected_room, block='0' if block_mode else '1'), quote=True)}"
          onchange="window.location.assign(this.dataset.url)"><span class="block-switch-track" aria-hidden="true"><span></span></span></label>
          <select class="class-select" aria-label="Raum auswählen" data-plan-teacher-select>{options}</select></section></div>'''
        content += render_teacher_week_table(room_table_plans(week), selected_room, block_mode, show_empty=True, show_teachers=True)
    return render_teacher_page(selected_date, page_week_plans=week, page_content=content,
                               page_navigation=navigation, page_title='Raumplan', page_active='rooms', **flags)
