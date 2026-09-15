import test from 'node:test';
import assert from 'node:assert/strict';
import { weekEventSegment, weekEventIsAllDay, intervalLanes } from '../src/lib/weekEventSegment';

test('multi-day times apply only to their respective boundary days', () => {
  const event = { date: '2026-09-14', endDate: '2026-09-16', startTime: '15:30', endTime: '10:15' };
  assert.deepEqual(weekEventSegment(event, event.date), { startMinute: 930, endMinute: 1440, label: '15:30 – 24:00 Uhr' });
  assert.equal(weekEventSegment(event, '2026-09-15'), null);
  assert.equal(weekEventIsAllDay(event, '2026-09-15'), true);
  assert.equal(weekEventIsAllDay(event, event.date), false);
  assert.equal(weekEventIsAllDay(event, event.endDate), false);
  assert.deepEqual(weekEventSegment(event, event.endDate), { startMinute: 0, endMinute: 615, label: '00:00 – 10:15 Uhr' });
  assert.equal(weekEventSegment(event, '2026-09-17'), null);
  assert.equal(weekEventSegment(event, '2026-09-13'), null);
});

test('single-day and all-day events retain their meaning', () => {
  assert.deepEqual(weekEventSegment({ date: '2026-09-15', startTime: '09:10', endTime: '10:30' }, '2026-09-15'), { startMinute: 550, endMinute: 630, label: '09:10 – 10:30 Uhr' });
  assert.equal(weekEventSegment({ date: '2026-09-15' }, '2026-09-15'), null);
});

test('midnight end does not occupy the following day, including DST weekend', () => {
  const event = { date: '2026-10-24', endDate: '2026-10-26', startTime: '20:00', endTime: '00:00' };
  assert.equal(weekEventSegment(event, '2026-10-25'), null);
  assert.equal(weekEventIsAllDay(event, '2026-10-25'), true);
  assert.equal(weekEventSegment(event, '2026-10-26'), null);
});

 test('overlapping spans use separate lanes and adjacent spans reuse them', () => {
   const result = intervalLanes([{ start: 0, end: 3 }, { start: 1, end: 2 }, { start: 2, end: 4 }, { start: 4, end: 5 }]);
   assert.deepEqual(result.map(({lane, laneCount}) => [lane, laneCount]), [[0, 2], [1, 2], [1, 2], [0, 1]]);
 });
 test('no-end-time events receive a one-hour visual duration capped at midnight', () => {
   assert.equal(weekEventSegment({date: '2026-09-15', startTime: '23:30'}, '2026-09-15')?.endMinute, 1440);
 });
