import assert from 'node:assert/strict';
import test from 'node:test';
import express from 'express';
import { configureProxyTrust, dockerGateway } from '../server/proxyTrust';

test('gateway discovery trusts only default gateway, never the whole subnet', () => {
  assert.deepEqual(dockerGateway('eth0 00000000 010012AC 0003\neth1 00FB1EAC 00000000 0001'), ['172.18.0.1']);
});

test('Express client IP follows the first untrusted hop and rejects malformed chains', async () => {
  process.env.TRUSTED_PROXIES = '127.0.0.1,::1';
  process.env.TRUSTED_PROXY_HOSTS = '';
  process.env.TRUST_DOCKER_GATEWAY = 'false';
  const app = express();
  const stop = await configureProxyTrust(app);
  app.get('/', (req, res) => res.json({ ip: req.ip }));
  const server = app.listen(0, '127.0.0.1');
  await new Promise<void>(resolve => server.once('listening', resolve));
  const port = (server.address() as any).port;
  const read = async (xff: string) => (await (await fetch(`http://127.0.0.1:${port}/`, { headers: { 'X-Forwarded-For': xff } })).json()).ip;
  try {
    assert.equal(await read('198.51.100.8'), '198.51.100.8');
    assert.equal(await read('1.2.3.4, 198.51.100.8'), '198.51.100.8');
    assert.equal(await read('2001:db8::8'), '2001:db8::8');
    assert.equal(await read('bad-ip, 198.51.100.8'), '127.0.0.1');
    app.set('trust proxy', false);
    assert.equal(await read('1.2.3.4'), '127.0.0.1');
  } finally {
    stop();
    await new Promise<void>(resolve => server.close(() => resolve()));
  }
});
