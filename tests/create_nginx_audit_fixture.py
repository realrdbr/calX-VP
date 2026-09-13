"""Build an isolated host-nginx -> loopback Docker ports -> real login logs test."""
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = Path('/tmp/cal11-nginx-audit')
OUT.mkdir(exist_ok=True)
(OUT / 'logs').mkdir(exist_ok=True)
config = (ROOT / 'proxy/nginx.conf').read_text()
config = re.sub(r'server \{\s*listen 80;.*?\n\}', '', config, flags=re.S)
config = config.replace('listen 443 ssl http2;', 'listen 172.30.247.1:39002;')
config = config.replace('127.0.0.1:3000', '127.0.0.1:39000').replace('127.0.0.1:8000', '127.0.0.1:39001').replace('127.0.0.1:8090', '127.0.0.1:39003')
(OUT / 'nginx.conf').write_text("events {}\nhttp {\nlog_format proof '$remote_addr $host $request';\naccess_log /proof/access.log proof;\n" + config + '\n}')
(OUT / 'init.sql').write_text("""USE regression;
CREATE TABLE users (username VARCHAR(64) PRIMARY KEY, pin VARCHAR(255), courses LONGTEXT, preferences LONGTEXT, status VARCHAR(20) DEFAULT 'ACTIVE') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO users VALUES ('ip-test-user','1234','[]','{}','ACTIVE');
""")
(OUT / 'vp.py').write_text("""import sys, os
sys.path.insert(0,'/work')
from main import AppRequestHandler
from accounts import AccountStore
from http.server import ThreadingHTTPServer
AppRequestHandler.store=AccountStore('mysql://root:regression-only-password@database:3306/regression', os.environ['APP_ENCRYPTION_KEY'])
ThreadingHTTPServer(('0.0.0.0',8000),AppRequestHandler).serve_forever()
""")
(OUT / 'check.py').write_text('''import os,time,requests,pymysql,socket
expected=socket.gethostbyname(socket.gethostname())
tag=expected.rsplit('.',1)[1]
base='http://172.30.247.1:39002'
for attempt in range(120):
 try:
  response=requests.get(base+'/api/health',headers={'Host':'cal11.de'},timeout=2)
  if response.status_code==200: break
 except requests.RequestException: pass
 time.sleep(.25)
else: raise AssertionError('Calendar did not become healthy')
for attempt in range(120):
 try:
  if requests.get(base+'/login',headers={'Host':'vp.cal11.de'},timeout=2).status_code==200: break
 except requests.RequestException: pass
 time.sleep(.25)
else: raise AssertionError('VP did not become healthy')
connection=pymysql.connect(host='database',user='root',password='regression-only-password',database='regression',autocommit=True)
for host,path,table in [('cal11.de','/api/login','calendar_login_attempts'),('vp.cal11.de','/login','vp_login_attempts')]:
 for index,xff in enumerate(['1.2.3.4','127.0.0.1','1.2.3.4, 127.0.0.1','2001:db8::123','bad-value','']):
  username=f'probe-{tag}-{index}'
  headers={'Host':host,'X-Forwarded-For':xff,'X-Real-IP':'1.2.3.4','Forwarded':'for=1.2.3.4'}
  payload={'username':username,'pin':'9999'}
  url=base+path+'?proof='+tag+'-'+str(index)
  result=requests.post(url,headers=headers,allow_redirects=False,timeout=5,**({'json':payload} if host=='cal11.de' else {'data':payload}))
  assert result.status_code in (200,404),(host,result.status_code,result.text)
  with connection.cursor() as cursor:
   cursor.execute(f'SELECT ip_address, successful FROM {table} WHERE username=%s',(username,))
   rows=cursor.fetchall()
  assert rows==((expected,0),),(host,xff,rows,expected)
 payload={'username':'ip-test-user','pin':'1234'}
 result=requests.post(base+path,headers={'Host':host,'X-Forwarded-For':'127.0.0.1'},allow_redirects=False,timeout=5,**({'json':payload} if host=='cal11.de' else {'data':payload}))
 assert result.status_code in (200,303,302),(host,result.status_code,result.text)
 with connection.cursor() as cursor:
  cursor.execute(f'SELECT COUNT(*) FROM {table} WHERE username=%s AND ip_address=%s AND successful=1',('ip-test-user',expected))
  assert cursor.fetchone()[0]>=1
 print('PASS: real',table,'records correct client IP for success/failure and six header variants:',expected,flush=True)
# Confirm the nginx access log itself, not just the backend's response.
for attempt in range(40):
 lines=open('/proof/access.log').read().splitlines()
 if all(any(line.startswith(expected+' '+host+' ') and '?proof='+tag+'-'+str(i) in line for line in lines) for host in ('cal11.de','vp.cal11.de') for i in range(6)): break
 time.sleep(.1)
else: raise AssertionError('nginx access log did not contain the correct remote IP')
print('PASS: nginx access log contains actual client IP:',expected,flush=True)
connection.close()
''')
(OUT / 'rate_limit.py').write_text('''import sys,requests,pymysql,socket
expected=socket.gethostbyname(socket.gethostname())
count=8 if sys.argv[1]=='blocked' else 1
codes=[]
for i in range(count):
 response=requests.post('http://172.30.247.1:39002/api/login',headers={'Host':'cal11.de','X-Forwarded-For':'127.0.0.1'},json={'username':'shared-rate-limit-probe','pin':'9999'},timeout=5)
 codes.append(response.status_code)
assert codes==[404]*count,codes
if sys.argv[1]=='blocked':
 for forged in ['1.2.3.4','127.0.0.1','2001:db8::123','bad-value']:
  response=requests.post('http://172.30.247.1:39002/api/login',headers={'Host':'cal11.de','X-Forwarded-For':forged},json={'username':'shared-rate-limit-probe','pin':'9999'},timeout=5)
  assert response.status_code==429,(forged,response.status_code)
connection=pymysql.connect(host='database',user='root',password='regression-only-password',database='regression',autocommit=True)
with connection.cursor() as cursor:
 cursor.execute("SELECT DISTINCT ip_address FROM calendar_login_attempts WHERE username='shared-rate-limit-probe'")
 addresses={row[0] for row in cursor.fetchall()}
assert expected in addresses and '127.0.0.1' not in addresses,addresses
print('PASS: calendar lockout and spoofing protection:',sys.argv[1],expected,flush=True)
if sys.argv[1]=='blocked':
 for i in range(8):
  response=requests.post('http://172.30.247.1:39002/api/login',headers={'Host':'cal11.de','X-Forwarded-For':str(i)+'.2.3.4'},json={'username':'ip-test-user','pin':'9999'},timeout=5)
  assert response.status_code==401,response.status_code
response=requests.post('http://172.30.247.1:39002/api/login',headers={'Host':'cal11.de','X-Forwarded-For':'1.2.3.4'},json={'username':'ip-test-user','pin':'1234'},timeout=5)
assert response.status_code==(429 if sys.argv[1]=='blocked' else 200),response.status_code
assert ('Set-Cookie' not in response.headers) if sys.argv[1]=='blocked' else ('Set-Cookie' in response.headers)
print('PASS: calendar correct PIN rejected only for locked IP:',expected,flush=True)
# A correct PIN must still be rejected for the locked client, but work for another IP.
for i in range(5 if sys.argv[1]=='blocked' else 0):
 response=requests.post('http://172.30.247.1:39002/login',headers={'Host':'vp.cal11.de','X-Forwarded-For':str(i)+'.2.3.4'},data={'username':'ip-test-user','pin':'9999'},allow_redirects=False,timeout=5)
 assert response.status_code==200,response.status_code
for forged in ['127.0.0.1','1.2.3.4']:
 response=requests.post('http://172.30.247.1:39002/login',headers={'Host':'vp.cal11.de','X-Forwarded-For':forged},data={'username':'ip-test-user','pin':'1234'},allow_redirects=False,timeout=5)
 assert response.status_code==(200 if sys.argv[1]=='blocked' else 303),response.status_code
 assert ('Set-Cookie' not in response.headers) if sys.argv[1]=='blocked' else ('Set-Cookie' in response.headers)
print('PASS: VP correct PIN rejected only for locked IP, including forged headers:',expected,flush=True)
response=requests.get('http://172.30.247.1:39002/private-probe/json?poll=1',headers={'Host':'notify.cal11.de','X-Forwarded-For':'127.0.0.1','X-Real-IP':'1.2.3.4'},timeout=5)
assert response.status_code==403,response.status_code
print('PASS: ntfy request denied as expected; inspect visitor_ip in ntfy JSON log',flush=True)
''')
common = {'TRUSTED_PROXIES':'127.0.0.1,::1','TRUST_DOCKER_GATEWAY':'true','TRUSTED_PROXY_HOSTS':'','APP_ENCRYPTION_KEY':'MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA='}
vol = [str(ROOT)+':/work:ro','/dev/null:/work/.env:ro',str(OUT)+':/check:ro']
services = {
 'database': {'image':'mariadb:11.4','environment':{'MYSQL_ROOT_PASSWORD':'regression-only-password','MYSQL_DATABASE':'regression'},'volumes':[str(OUT/'init.sql')+':/docker-entrypoint-initdb.d/init.sql:ro'],'healthcheck':{'test':['CMD','healthcheck.sh','--connect','--innodb_initialized'],'interval':'1s','timeout':'3s','retries':60}},
 'app': {'image':'node:22-slim','working_dir':'/work','volumes':vol,'environment':{**common,'NODE_ENV':'production','DB_HOST':'database','DB_NAME':'regression','DB_USER':'root','DB_PASSWORD':'regression-only-password','BIND_HOST':'0.0.0.0','CAL11_PORT':'3000'},'command':['node','dist/server.cjs'],'ports':['127.0.0.1:39000:3000'],'depends_on':{'database':{'condition':'service_healthy'}}},
 'vp': {'image':'jahrgangskalender-vp','working_dir':'/work','volumes':vol,'environment':common,'command':['python','/check/vp.py'],'ports':['127.0.0.1:39001:8000'],'depends_on':{'database':{'condition':'service_healthy'}}},
 'ntfy': {'image':'binwiederhier/ntfy:v2.25.0','command':['serve'],'ports':['127.0.0.1:39003:80'],'environment':{'NTFY_BEHIND_PROXY':'true','NTFY_AUTH_FILE':'/tmp/auth.db','NTFY_AUTH_DEFAULT_ACCESS':'deny-all','NTFY_LOG_LEVEL':'debug','NTFY_LOG_FORMAT':'json'}},
 'nginx': {'image':'nginx:stable-alpine','network_mode':'host','volumes':[str(OUT/'nginx.conf')+':/etc/nginx/nginx.conf:ro',str(OUT/'logs')+':/proof']},
}
for number in (10,11):
 services['client'+str(number)]={'image':'jahrgangskalender-vp','command':['sleep','infinity'],'volumes':[str(OUT)+':/check:ro',str(OUT/'logs')+':/proof:ro'],'networks':{'default':{'ipv4_address':f'172.30.247.{number}'}}}
(OUT/'compose.yml').write_text(yaml.safe_dump({'services':services,'networks':{'default':{'ipam':{'config':[{'subnet':'172.30.247.0/24','gateway':'172.30.247.1'}]}}}}))
print(OUT/'compose.yml')
