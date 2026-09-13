import assert from 'node:assert/strict';
import test from 'node:test';
import mysql from 'mysql2/promise';
import { initDatabase, isDbConnected, closeDatabase, dbCleanupExpiredLoginAttempts, dbGetUser, dbSaveUser, dbSetRequiredPin, dbCreateEvent, dbUpdateEvent, dbGetEvents, dbDeleteEvent, verifyPin } from '../server/db';

test('MariaDB PIN setup and event editor migration', { skip: process.env.CAL11_SQL_INTEGRATION !== '1' }, async () => {
  // Only the explicitly isolated regression database is permitted.
  assert.equal(process.env.DB_NAME, 'regression');
  assert.equal(process.env.DB_HOST, 'database');
  const connection = await mysql.createConnection({ host: 'database', user: 'root', password: 'regression-only-password', database: 'regression' });
  try {
    // Minimal historical tables: preserve accounts, credentials and events while adding columns.
    await connection.query("CREATE TABLE users (username VARCHAR(64) PRIMARY KEY, pin VARCHAR(64), courses LONGTEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    await connection.query("INSERT INTO users VALUES ('legacy-person', '1234', '[\"MA1\"]'), ('legacy-no-pin', NULL, '[]')");
    await connection.query("CREATE TABLE events (id VARCHAR(64) PRIMARY KEY, title VARCHAR(255), date VARCHAR(32), course_id VARCHAR(64), type VARCHAR(32)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    await connection.query("INSERT INTO events VALUES ('legacy-event', 'Alter Termin', '2999-01-01', 'ALLGEMEIN', 'SONSTIGES')");
    await connection.query("CREATE TABLE courses (id VARCHAR(64) PRIMARY KEY, name VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin");
    await connection.query("INSERT INTO courses VALUES ('LEGACY', 'Alter Kurs')");
    await connection.query("CREATE TABLE event_categories (id VARCHAR(64) PRIMARY KEY, name VARCHAR(255), color VARCHAR(16)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    await connection.query("INSERT INTO event_categories VALUES ('LEGACY', 'Alte Kategorie', '#ffffff')");
    for (let startup = 0; startup < 2; startup++) {
      await initDatabase();
      assert.equal(isDbConnected(), true, 'migration must connect to real SQL, never pass against memory fallback');
      const user = await dbGetUser('legacy-person');
      assert.equal(user.pin, '1234');
      assert.deepEqual(user.courses, ['MA1']);
      assert.equal(user.status, 'ACTIVE');
      assert.equal(verifyPin('1234', user.pin), true);
      assert.equal((await dbGetUser('legacy-no-pin')).pin, undefined);
      assert.equal((await dbGetEvents()).find(e => e.id === 'legacy-event')?.title, 'Alter Termin');
      if (startup === 0) await closeDatabase();
    }
    await connection.query("DELETE FROM users WHERE username LIKE 'regression-%'");
    await connection.query("DELETE FROM events WHERE id = 'regression-event'");
    await connection.query("INSERT INTO calendar_login_attempts(username, ip_address, attempted_at, successful) VALUES ('expired', '127.0.0.1', '2000-01-01T00:00:00.000Z', 0)");
    await dbCleanupExpiredLoginAttempts();
    const [attempts]: any = await connection.query("SELECT * FROM calendar_login_attempts WHERE username = 'expired'");
    assert.equal(attempts.length, 0);
    await dbSaveUser('regression-no-pin', {});
    assert.equal(await dbSetRequiredPin('regression-no-pin', undefined, '1357'), true);
    assert.equal(verifyPin('1357', (await dbGetUser('regression-no-pin')).pin), true);
    assert.equal(await dbSetRequiredPin('regression-no-pin', undefined, '2468'), false);
    await dbSaveUser('regression-existing-pin', { pin: '9876' });
    const existing = await dbGetUser('regression-existing-pin');
    assert.equal(await dbSetRequiredPin(existing.username, existing.pin, '2468'), false);
    assert.equal((await dbGetUser(existing.username)).pin, existing.pin);
    await dbCreateEvent({ id: 'regression-event', title: 'Allgemein', date: '2026-09-14', courseId: 'ALLGEMEIN', type: 'HAUSAUFGABE', author: 'creator' });
    await dbUpdateEvent('regression-event', { title: 'Kursaufgabe', courseId: 'MA1' }, undefined, 'actual-editor');
    const [rows]: any = await connection.query('SELECT course_id, author, updated_by FROM events WHERE id = ?', ['regression-event']);
    assert.deepEqual(rows.map((row: any) => ({ ...row })), [{ course_id: 'MA1', author: 'creator', updated_by: 'actual-editor' }]);
    assert.equal((await dbGetEvents(false, [])).some(event => event.id === 'regression-event'), false);
    await dbDeleteEvent('regression-event', 'actual-editor');
    assert.equal((await dbGetEvents()).some(event => event.id === 'regression-event'), false);
  } finally {
    await connection.end();
    await closeDatabase();
  }
});
