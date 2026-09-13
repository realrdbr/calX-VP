import json,re
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=Path('/tmp/cal11-proxy-check');out.mkdir(exist_ok=True)
nginx=(root/'proxy/nginx.conf').read_text();nginx=re.sub(r'server \{\s*listen 80;.*?\n\}', '', nginx, flags=re.S);nginx=nginx.replace('listen 443 ssl http2;', 'listen 80;').replace('127.0.0.1:3000','app:3000').replace('127.0.0.1:8000','vp:8000').replace('127.0.0.1:8090','app:3000');(out/'nginx.conf').write_text('events {}\nhttp {\n'+nginx+'\n}')
caddy=(root/'proxy/Caddyfile').read_text();caddy=caddy[caddy.index('cal11.de {'):];caddy=caddy.replace('cal11.de {','http://cal11.de {').replace('vp.http://','http://vp.').replace('notify.http://','http://notify.').replace('ntfy:80','app:3000');(out/'Caddyfile').write_text(caddy)
apache=(root/'proxy/apache-vhosts.conf').read_text();apache=re.sub(r'<VirtualHost \*:80>.*?</VirtualHost>','',apache,flags=re.S);apache=apache.replace('*:443','*:80');apache='\n'.join(l for l in apache.splitlines() if not l.strip().startswith(('SSLEngine','SSLCertificate')));apache=apache.replace('127.0.0.1:3000','app:3000').replace('127.0.0.1:8000','vp:8000').replace('127.0.0.1:8090','app:3000');prefix='ServerRoot /usr/local/apache2\nListen 80\nServerName localhost\nUser daemon\nGroup daemon\nErrorLog /proc/self/fd/2\n';prefix+=''.join('LoadModule '+module+'_module modules/mod_'+module+'.so\n' for module in ['mpm_event','unixd','authz_core','proxy','proxy_http','headers']);(out/'httpd.conf').write_text(prefix+apache)
import yaml
traefik=yaml.safe_load((root/'proxy/traefik-dynamic.yml').read_text());
for router in traefik['http']['routers'].values():router.pop('tls');router['entryPoints']=['web']
for svc in traefik['http']['services'].values():
 for server in svc['loadBalancer']['servers']:server['url']=server['url'].replace('127.0.0.1:3000','app:3000').replace('127.0.0.1:8000','vp:8000').replace('127.0.0.1:8090','app:3000')
(out/'traefik-dynamic.yml').write_text(yaml.safe_dump(traefik))
(out/'echo.ts').write_text("import express from '/work/node_modules/express/index.js'; import {configureProxyTrust} from '/work/server/proxyTrust.ts'; async function main(){const app=express(); await configureProxyTrust(app); app.get('/',(req,res)=>res.json({ip:req.ip}));app.listen(3000,'0.0.0.0');} main();")
(out/'echo.py').write_text("import sys,json\nsys.path.insert(0,'/work')\nfrom main import AppRequestHandler\nfrom http.server import ThreadingHTTPServer\nclass Echo(AppRequestHandler):\n def do_GET(self):\n  body=json.dumps({'ip':self._client_ip()}).encode(); self.send_response(200); self.end_headers(); self.wfile.write(body)\nThreadingHTTPServer(('0.0.0.0',8000),Echo).serve_forever()\n")
(out/'check.py').write_text('''import requests,socket,time
expected=socket.gethostbyname(socket.gethostname())
for proxy in ('nginx','caddy','apache','traefik'):
 for host in ('cal11.de','vp.cal11.de','notify.cal11.de'):
  for forged in ('1.2.3.4','1.2.3.4, 127.0.0.1','bad-header','2001:db8::123'):
   for attempt in range(50):
    try:
     response=requests.get('http://'+proxy+'/',headers={'Host':host,'X-Forwarded-For':forged,'X-Real-IP':'1.2.3.4','X-Forwarded-Host':'evil.invalid'},timeout=3)
     response.raise_for_status()
     assert response.json()['ip']==expected,(proxy,host,forged,response.text,expected)
     break
    except (requests.RequestException,AssertionError):
     if attempt==49: raise
     time.sleep(.2)
 print('PASS:',proxy,'real client IP through calendar/VP/notify routes; spoofed headers overwritten')
for host in ('app:3000','vp:8000'):
 assert requests.get('http://'+host+'/',headers={'X-Forwarded-For':'1.2.3.4'}).json()['ip']==expected
print('PASS: direct untrusted requests cannot forge IPs')
''')
services={}
common={'TRUSTED_PROXIES':'127.0.0.1,::1','TRUST_DOCKER_GATEWAY':'true','TRUSTED_PROXY_HOSTS':'nginx,caddy,apache,traefik','APP_ENCRYPTION_KEY':'MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA='}
vol=[str(root)+':/work:ro','/dev/null:/work/.env:ro',str(out)+':/check:ro']
services['app']={'image':'node:22-slim','working_dir':'/work','environment':common,'volumes':vol,'command':['node_modules/.bin/tsx','/check/echo.ts']}
services['vp']={'image':'jahrgangskalender-vp','working_dir':'/work','environment':common,'volumes':vol,'command':['python','/check/echo.py']}
services['nginx']={'image':'nginx:stable-alpine','volumes':[str(out/'nginx.conf')+':/etc/nginx/nginx.conf:ro']}
services['caddy']={'image':'caddy:2','volumes':[str(out/'Caddyfile')+':/etc/caddy/Caddyfile:ro']}
services['apache']={'image':'httpd:2.4','volumes':[str(out/'httpd.conf')+':/usr/local/apache2/conf/httpd.conf:ro']}
services['traefik']={'image':'traefik:v3.6','command':['--entryPoints.web.address=:80','--entryPoints.web.forwardedHeaders.insecure=false','--providers.file.filename=/check/traefik-dynamic.yml'],'volumes':[str(out)+':/check:ro']}
services['tester']={'image':'jahrgangskalender-vp','volumes':[str(out)+':/check:ro'],'command':['python','/check/check.py'],'depends_on':list(services)}
(out/'compose.yml').write_text(yaml.safe_dump({'services':services}))
