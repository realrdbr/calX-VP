"""Published school weeks, independent of missing individual timetable files."""
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from threading import Lock
from time import monotonic
from xml.etree import ElementTree
import requests

_weeks = ()
_last_attempt = None
_lock = Lock()


def parse_school_weeks(content):
    result = set()
    for node in ElementTree.fromstring(content).findall('.//Sw'):
        start = datetime.strptime(node.attrib['SwDatumVon'], '%d.%m.%Y').date()
        end = datetime.strptime(node.attrib['SwDatumBis'], '%d.%m.%Y').date()
        if end < start or (end - start).days > 7:
            raise ValueError('Invalid school week range')
        result.add(start - timedelta(days=start.weekday()))
    if not result:
        raise ValueError('Empty school week index')
    return tuple(sorted(result))


def refresh_school_weeks(school, username, password, cache_dir):
    """On failure retain the last valid index; an HTTP error is never a holiday."""
    global _weeks, _last_attempt
    with _lock:
        if _last_attempt is not None and monotonic() - _last_attempt < 300:
            return
        _last_attempt = monotonic()
        path = Path(cache_dir) / 'school-weeks.json'
        if not _weeks:
            try:
                saved = json.loads(path.read_text())
                if saved['school'] == str(school):
                    _weeks = tuple(sorted({date.fromisoformat(day) for day in saved['weeks']}))
            except (OSError, ValueError, KeyError, TypeError):
                pass
        try:
            response = requests.get(f'https://www.stundenplan24.de/{school}/wplan/wdatenk/SPlanKl_Basis.xml',
                                    auth=(username, password), timeout=10)
            response.raise_for_status()
            weeks = parse_school_weeks(response.content)
        except (requests.RequestException, ValueError, KeyError, ElementTree.ParseError):
            return
        _weeks = weeks
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'school': str(school), 'weeks': [day.isoformat() for day in weeks]}))
            temporary.replace(path)
        except OSError:
            pass


def school_week(value):
    monday = value - timedelta(days=value.weekday())
    if not _weeks or monday in _weeks:
        return monday
    return next((week for week in _weeks if week >= monday), _weeks[-1])


def adjacent_school_week(value, direction=1):
    monday = value - timedelta(days=value.weekday())
    if not _weeks:
        return monday + timedelta(days=7 * direction)
    candidates = [week for week in _weeks if (week > monday if direction > 0 else week < monday)]
    return (candidates[0] if direction > 0 else candidates[-1]) if candidates else school_week(monday)
