import assert from 'node:assert/strict';
import test from 'node:test';
import { permitsPinSetupRequest, requiresPersonalPin } from '../server/pinPolicy';
import { dbGetUser, dbSaveUser, dbSetRequiredPin, verifyPin, generateSessionToken, deleteUserSessions, getSessionUsername } from '../server/db';

test('missing PIN requires setup; an existing personal PIN remains unaffected', () => {
  assert.equal(requiresPersonalPin({}), true);
  assert.equal(requiresPersonalPin({ pin: '' }), true);
  assert.equal(requiresPersonalPin({ pin: 'hash' }), false);
  assert.equal(requiresPersonalPin({ pin: 'hash', preferences: { forcePinChange: true } }), true);
});

test('setup sessions can only inspect themselves, set PIN or log out', () => {
  for (const [method, path] of [['GET', '/api/session'], ['GET', '/api/users/alice'], ['POST', '/api/pin'], ['POST', '/api/logout']]) {
    assert.equal(permitsPinSetupRequest(method, path, 'alice'), true);
  }
  for (const [method, path] of [['GET', '/api/events'], ['POST', '/api/events'], ['GET', '/api/admin/users'], ['POST', '/api/users/alice'], ['GET', '/api/users/bob'], ['DELETE', '/api/pin']]) {
    assert.equal(permitsPinSetupRequest(method, path, 'alice'), false);
  }
});

test('PIN setup hashes the credential, clears force flag and rejects stale overwrite', async () => {
  const username = 'pin-setup-test';
  await dbSaveUser(username, {});
  assert.equal(await dbSetRequiredPin(username, undefined, '1357'), true);
  const user = await dbGetUser(username);
  assert.notEqual(user.pin, '1357');
  assert.equal(verifyPin('1357', user.pin), true);
  assert.equal(user.preferences.forcePinChange, false);
  assert.equal(await dbSetRequiredPin(username, undefined, '2468'), false);
  assert.equal(await dbSetRequiredPin(username, user.pin, '2468'), false);
  assert.equal(verifyPin('1357', (await dbGetUser(username)).pin), true);
  await assert.rejects(dbSetRequiredPin(username, user.pin, '12'), /vier Ziffern/);
});

test('reset requires a new PIN and revokes only the affected users sessions', async () => {
  await dbSaveUser('reset-target', { pin: '1234' });
  await dbSaveUser('reset-other', { pin: '5678' });
  const first = await generateSessionToken('reset-target');
  const second = await generateSessionToken('reset-target');
  const other = await generateSessionToken('reset-other');
  await dbSaveUser('reset-target', { pin: null });
  await deleteUserSessions('reset-target');
  assert.equal(await getSessionUsername(first), null);
  assert.equal(await getSessionUsername(second), null);
  assert.equal(await getSessionUsername(other), 'reset-other');
  assert.equal(requiresPersonalPin(await dbGetUser('reset-target')), true);
  assert.equal(requiresPersonalPin(await dbGetUser('reset-other')), false);
  await deleteUserSessions('reset-other');
});
