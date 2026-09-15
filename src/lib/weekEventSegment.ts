import type { AppEvent } from '../types';

export function weekEventIsAllDay(event: Pick<AppEvent, 'date' | 'endDate' | 'startTime'>, day: string) {
  const lastDay = event.endDate || event.date;
  return event.startTime
    ? day > event.date && day < lastDay
    : day >= event.date && day <= lastDay;
}

/** Clip timed events to a local calendar day, without parsing dates as UTC. */
export function weekEventSegment(event: Pick<AppEvent, 'date' | 'endDate' | 'startTime' | 'endTime'>, day: string) {
  if (!event.startTime) return null;
  const lastDay = event.endDate || event.date;
  if (day < event.date || day > lastDay) return null;
  if (weekEventIsAllDay(event, day)) return null;
  if (day !== event.date && day === lastDay && event.endTime === '00:00') return null;
  const start = day === event.date ? event.startTime : '00:00';
  const end = day === lastDay ? event.endTime : '24:00';
  const minutes = (value: string) => Number(value.split(':')[0]) * 60 + Number(value.split(':')[1]);
  const startMinute = minutes(start);
  const endMinute = end ? minutes(end) : Math.min(1440, startMinute + 60);
  if (endMinute <= startMinute) return null;
  return {
    startMinute,
    endMinute,
    label: `${start}${end ? ` – ${end}` : ''} Uhr`,
  };
}

/** Assign overlapping intervals separate lanes; touching boundaries may share one. */
export function intervalLanes<T extends { start: number; end: number }>(items: T[]) {
  const result: (T & { lane: number; laneCount: number })[] = [];
  let group: typeof result = [];
  let ends: number[] = [];
  let groupEnd = -Infinity;
  const finish = () => { for (const item of group) item.laneCount = ends.length; };
  for (const item of [...items].sort((a, b) => a.start - b.start || b.end - a.end)) {
    if (item.start >= groupEnd) {
      finish(); group = []; ends = []; groupEnd = -Infinity;
    }
    let lane = ends.findIndex(end => end <= item.start);
    if (lane < 0) lane = ends.length;
    ends[lane] = item.end;
    groupEnd = Math.max(groupEnd, item.end);
    const placed = { ...item, lane, laneCount: 1 };
    group.push(placed); result.push(placed);
  }
  finish();
  return result;
}
