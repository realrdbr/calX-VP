import fs from 'node:fs';
import dns from 'node:dns/promises';
import { isIP } from 'node:net';
import type { Express } from 'express';

export function dockerGateway(route: string): string[] {
  return route.split('\n').flatMap(line => {
    const fields = line.trim().split(/\s+/);
    if (fields[1] !== '00000000' || !/^[0-9a-f]{8}$/i.test(fields[2] || '') || !(parseInt(fields[3], 16) & 2)) return [];
    return [Buffer.from(fields[2], 'hex').reverse().join('.')];
  });
}

export async function configureProxyTrust(app: Express) {
  const configured = (process.env.TRUSTED_PROXIES ?? '127.0.0.1,::1').split(',').map(s => s.trim()).filter(Boolean);
  const hosts = (process.env.TRUSTED_PROXY_HOSTS || '').split(',').map(s => s.trim()).filter(Boolean);
  let refreshedAt = 0;
  const refresh = async () => {
    refreshedAt = Date.now();
    let gateway: string[] = [];
    if (process.env.TRUST_DOCKER_GATEWAY === 'true' && fs.existsSync('/.dockerenv')) {
      gateway = dockerGateway(fs.readFileSync('/proc/net/route', 'utf8'));
    }
    const resolved = await Promise.all(hosts.map(host => dns.lookup(host, { all: true }).catch(() => [])));
    app.set('trust proxy', [...configured, ...gateway, ...resolved.flat().map(entry => entry.address)]);
  };
  await refresh();
  const timer = setInterval(() => { void refresh().catch(() => {}); }, 10000);
  timer.unref();
  // Invalid proxy chains must never enter rate-limit or audit-log identities.
  app.use(async (req, _res, next) => {
    // A Compose proxy may acquire its address after the app starts. Refresh on
    // an unknown peer instead of logging its proxy address until the next timer.
    if (hosts.length && !app.get('trust proxy fn')(req.socket.remoteAddress || '', 0) && Date.now() - refreshedAt >= 1000) {
      try { await refresh(); } catch (error) { next(error); return; }
    }
    const chain = req.headers['x-forwarded-for'];
    if (chain && (typeof chain !== 'string' || chain.split(',').some(value => !isIP(value.trim())))) {
      delete req.headers['x-forwarded-for'];
    }
    next();
  });
  return () => clearInterval(timer);
}
