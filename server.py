"""Didban Tennis: auditable prediction, settlement, evaluation and surface Elo."""
import json, math, os, sqlite3, urllib.request, urllib.error, threading, time
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

ROOT=Path(__file__).resolve().parent; DB=ROOT/'tennis_ai.db'; BASE='https://api.livetennisapi.com/api/public/v1'; MODEL='tennis-surface-elo-v2'
SYNC_STATE={'last_run':None,'last_result':None}
def now():return datetime.now(timezone.utc).isoformat()
@contextmanager
def connect():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 try:yield c;c.commit()
 finally:c.close()
def init_db():
 with connect() as c:
  c.execute('''CREATE TABLE IF NOT EXISTS predictions(id INTEGER PRIMARY KEY,created_at TEXT NOT NULL,match_id TEXT NOT NULL,mode TEXT NOT NULL,player1 TEXT,player2 TEXT,p1 REAL,p2 REAL,odds1 REAL,odds2 REAL,model TEXT,result INTEGER,brier REAL,settled_at TEXT,input_json TEXT NOT NULL)''')
  existing={r['name'] for r in c.execute('PRAGMA table_info(predictions)')}
  for name,typ in [('surface','TEXT'),('tour','TEXT'),('round_name','TEXT'),('start_time','TEXT'),('log_loss','REAL'),('correct','INTEGER'),('result_score','TEXT'),('settlement_source','TEXT')]:
   if name not in existing:c.execute(f'ALTER TABLE predictions ADD COLUMN {name} {typ}')
  c.execute('''CREATE TABLE IF NOT EXISTS ratings(player TEXT NOT NULL,surface TEXT NOT NULL,rating REAL NOT NULL DEFAULT 1500,games INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,PRIMARY KEY(player,surface))''')
  c.execute('CREATE INDEX IF NOT EXISTS ix_predictions_match ON predictions(match_id,result)')

def clamp(x,a=.001,b=.999):return max(a,min(b,x))
def logistic(x):return 1/(1+math.exp(-x))
def rating(player,surface,default):
 if not player:return float(default)
 with connect() as c:r=c.execute('SELECT rating FROM ratings WHERE player=? AND surface=?',(player,surface or 'Unknown')).fetchone()
 return float(r[0]) if r else float(default)
def prematch(p):
 surface=str(p.get('surface') or 'Unknown');e1=rating(p.get('player1'),surface,p.get('elo1',1500));e2=rating(p.get('player2'),surface,p.get('elo2',1500));r1=max(1,float(p.get('rank1') or 100));r2=max(1,float(p.get('rank2') or 100));f1=float(p.get('form1',.5));f2=float(p.get('form2',.5));fat1=float(p.get('fatigue1',0));fat2=float(p.get('fatigue2',0))
 score=(e1-e2)/360+(math.log(r2)-math.log(r1))*.18+(f1-f2)*.7-(fat1-fat2)*.45
 q=clamp(logistic(score));return q,1-q,e1,e2
def live_adjust(base,p):
 s1=int(p.get('sets1',0));s2=int(p.get('sets2',0));g1=int(p.get('games1',0));g2=int(p.get('games2',0));pts={'0':0,'15':1,'30':2,'40':3,'AD':4,'A':4};q1=pts.get(str(p.get('point1','0')).upper(),0);q2=pts.get(str(p.get('point2','0')).upper(),0);server=int(p.get('server',1));target=int(p.get('best_of',3))//2+1
 if s1>=target:return .999
 if s2>=target:return .001
 z=math.log(base/(1-base))+(s1-s2)*1.35+(g1-g2)*.16+(q1-q2)*.045+(.09 if server==1 else -.09)
 return clamp(logistic(z))
def predict(p):
 p1,p2,e1,e2=prematch(p)
 if p.get('mode')=='live':p1=live_adjust(p1,p);p2=1-p1
 return {'player1_win':p1,'player2_win':p2,'fair_odds1':1/p1,'fair_odds2':1/p2,'elo1':e1,'elo2':e2,'confidence':'high' if max(p1,p2)>=.7 else 'medium' if max(p1,p2)>=.58 else 'low','model':MODEL,'generated_at':now()}
def provider(path,params=None):
 key=os.getenv('LIVE_TENNIS_API_KEY','').strip()
 if not key:return {'data':[],'error':'not_configured'}
 url=BASE+path+('?' + urlencode(params) if params else '');req=urllib.request.Request(url,headers={'Authorization':'Bearer '+key,'X-API-Key':key,'User-Agent':'DidbanTennis/2.0'})
 try:
  with urllib.request.urlopen(req,timeout=12) as r:return json.load(r)
 except urllib.error.HTTPError as e:return {'data':[],'error':f'HTTP {e.code}'}
 except (urllib.error.URLError,TimeoutError,OSError) as e:return {'data':[],'error':str(e)}
def rows_of(raw):
 if isinstance(raw,dict) and (raw.get('id') or raw.get('match_id')) and not any(k in raw for k in ('data','matches','results')):return [raw]
 rows=raw.get('data',raw.get('matches',raw.get('results',[]))) if isinstance(raw,dict) else []
 if isinstance(rows,dict):rows=rows.get('items',rows.get('data',[rows] if rows.get('id') else []))
 return rows or []
def normalize_match(x):
 players=x.get('players') or {}
 if isinstance(players,dict):a=players.get('p1') or players.get('player1') or {};b=players.get('p2') or players.get('player2') or {}
 else:a=players[0] if len(players)>0 else {};b=players[1] if len(players)>1 else {}
 return {'id':str(x.get('id') or x.get('match_id') or x.get('matchId')),'start_time':x.get('scheduled_time') or x.get('start_time') or x.get('startTime') or x.get('scheduled_at'),'status':x.get('event_status') or x.get('status'),'tournament':x.get('tournament'),'surface':x.get('surface'),'tour':x.get('tour'),'round':x.get('round'),'player1':a.get('name') if isinstance(a,dict) else a,'player2':b.get('name') if isinstance(b,dict) else b,'rank1':(a.get('ranking') or a.get('rank')) if isinstance(a,dict) else None,'rank2':(b.get('ranking') or b.get('rank')) if isinstance(b,dict) else None,'score':x.get('score'),'outcome':x.get('outcome')}
def normalize_matches(raw):return [normalize_match(x) for x in rows_of(raw) if x.get('id') or x.get('match_id')]
def winner_of(m):
 out=m.get('outcome') or {};score=m.get('score') or {}
 if isinstance(out,str):
  if out.lower() in ('p1','player1','1'):return 1
  if out.lower() in ('p2','player2','2'):return 2
 if isinstance(out,dict):
  w=str(out.get('winner') or out.get('winner_side') or out.get('winner_position') or '').lower()
  if w in ('p1','player1','1'):return 1
  if w in ('p2','player2','2'):return 2
 sets=score.get('sets') if isinstance(score,dict) else None
 if isinstance(sets,list) and sets and all(isinstance(x,(list,tuple)) and len(x)>=2 for x in sets):
  a=sum(1 for x in sets if x[0]>x[1]);b=sum(1 for x in sets if x[1]>x[0])
  if a!=b:return 1 if a>b else 2
 return None
def settle(pid,winner,score=None,source='manual'):
 with connect() as c:
  row=c.execute('SELECT * FROM predictions WHERE id=? AND result IS NULL',(pid,)).fetchone()
  if not row:return False
  y=1 if winner==1 else 0;p=clamp(row['p1']);brier=(p-y)**2;logloss=-(y*math.log(p)+(1-y)*math.log(1-p));correct=int((p>=.5 and winner==1) or (p<.5 and winner==2))
  c.execute('UPDATE predictions SET result=?,brier=?,log_loss=?,correct=?,result_score=?,settled_at=?,settlement_source=? WHERE id=?',(winner,brier,logloss,correct,json.dumps(score,ensure_ascii=False) if score is not None else None,now(),source,pid))
  surf=row['surface'] or 'Unknown';expected=p;actual=y;k=24
  for player,old,delta in [(row['player1'],rating(row['player1'],surf,1500),k*(actual-expected)),(row['player2'],rating(row['player2'],surf,1500),-k*(actual-expected))]:
   c.execute('INSERT INTO ratings(player,surface,rating,games,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(player,surface) DO UPDATE SET rating=?,games=games+1,updated_at=?',(player,surf,old+delta,1,now(),old+delta,now()))
 return True
def void_match(match_id,status):
 with connect() as c:
  cur=c.execute("UPDATE predictions SET result=0,settled_at=?,settlement_source=?,result_score=? WHERE match_id=? AND result IS NULL",(now(),'void:'+str(status),None,match_id))
  return cur.rowcount
def sync_results(limit=20):
 with connect() as c:rows=c.execute("SELECT MIN(id) id,match_id FROM predictions WHERE result IS NULL AND match_id NOT IN ('custom','demo1') GROUP BY match_id LIMIT ?",(limit,)).fetchall()
 settled=0;errors=[]
 for row in rows:
  raw=provider('/matches/'+row['match_id']);items=normalize_matches(raw)
  if raw.get('error'):errors.append({'match_id':row['match_id'],'error':raw['error']});continue
  if not items:continue
  item=items[0]
  with connect() as c:
   c.execute('''UPDATE predictions SET
    player1=CASE WHEN player1 IS NULL OR player1 IN ('بازیکن اول','Player 1') THEN ? ELSE player1 END,
    player2=CASE WHEN player2 IS NULL OR player2 IN ('بازیکن دوم','Player 2') THEN ? ELSE player2 END,
    surface=COALESCE(surface,?),tour=COALESCE(tour,?),round_name=COALESCE(round_name,?),start_time=COALESCE(start_time,?)
    WHERE match_id=?''',(item.get('player1'),item.get('player2'),item.get('surface'),item.get('tour'),item.get('round'),item.get('start_time'),row['match_id']))
  winner=winner_of(item)
  if winner:
   with connect() as c:ids=[x[0] for x in c.execute('SELECT id FROM predictions WHERE match_id=? AND result IS NULL',(row['match_id'],))]
   for pid in ids:settled+=int(settle(pid,winner,item.get('score'),'provider'))
  elif str(item.get('status') or '').lower() in ('cancelled','canceled','abandoned','postponed','void'):
   settled+=void_match(row['match_id'],item.get('status'))
 result={'checked':len(rows),'settled':settled,'errors':errors};SYNC_STATE.update({'last_run':now(),'last_result':result});return result
def auto_sync_loop():
 time.sleep(300)
 while True:
  try:sync_results(5)
  except Exception as e:SYNC_STATE.update({'last_run':now(),'last_result':{'error':str(e)}})
  time.sleep(14400)
def performance():
 with connect() as c:
  total=c.execute('SELECT COUNT(*) FROM predictions').fetchone()[0];pending=c.execute('SELECT COUNT(*) FROM predictions WHERE result IS NULL').fetchone()[0];voided=c.execute('SELECT COUNT(*) FROM predictions WHERE result=0').fetchone()[0];r=c.execute('SELECT COUNT(*) n,AVG(brier) b,AVG(log_loss) l,AVG(correct) a FROM predictions WHERE result IN (1,2)').fetchone();groups=[dict(x) for x in c.execute('SELECT COALESCE(surface,"Unknown") surface,COUNT(*) n,AVG(correct) accuracy,AVG(brier) brier FROM predictions WHERE result IN (1,2) GROUP BY surface ORDER BY n DESC')]
 return {'total':total,'settled':r['n'],'voided':voided,'pending':pending,'accuracy':r['a'],'brier':r['b'],'log_loss':r['l'],'by_surface':groups,'model':MODEL}

class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**k):super().__init__(*a,directory=str(ROOT),**k)
 def send_json(self,x,status=200):
  b=json.dumps(x,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b)
 def body(self):return json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),100000)) or b'{}')
 def do_GET(self):
  u=urlparse(self.path);q=parse_qs(u.query)
  if u.path=='/api/health':return self.send_json({'ok':True,'database':DB.exists(),'provider_configured':bool(os.getenv('LIVE_TENNIS_API_KEY')),'model':MODEL,'auto_sync':SYNC_STATE})
  if u.path=='/api/matches':
   status=(q.get('status') or ['upcoming'])[0];raw=provider('/matches',{'status':status});return self.send_json({'items':normalize_matches(raw),'provider_error':raw.get('error') if isinstance(raw,dict) else None})
  if u.path=='/api/history':
   with connect() as c:rows=c.execute('SELECT id,created_at,start_time,match_id,mode,player1,player2,p1,p2,odds1,odds2,model,surface,result,brier,log_loss,correct,settled_at FROM predictions ORDER BY id DESC LIMIT 200').fetchall()
   return self.send_json({'items':[dict(r) for r in rows]})
  if u.path=='/api/performance':return self.send_json(performance())
  if u.path=='/api/ratings':
   with connect() as c:rows=c.execute('SELECT * FROM ratings ORDER BY games DESC,rating DESC LIMIT 200').fetchall()
   return self.send_json({'items':[dict(r) for r in rows]})
  return super().do_GET()
 def do_POST(self):
  try:p=self.body()
  except Exception as e:return self.send_json({'error':str(e)},400)
  if self.path=='/api/predict':return self.send_json(predict(p))
  if self.path=='/api/predictions':
   o=predict(p)
   with connect() as c:
    old=c.execute('SELECT id FROM predictions WHERE match_id=? AND mode=? AND model=? AND result IS NULL',(str(p.get('match_id','custom')),p.get('mode','prematch'),MODEL)).fetchone()
    if old:return self.send_json(o|{'prediction_id':old['id'],'saved':False,'message':'already registered'})
    cur=c.execute('INSERT INTO predictions(created_at,match_id,mode,player1,player2,p1,p2,odds1,odds2,model,input_json,surface,tour,round_name,start_time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(o['generated_at'],str(p.get('match_id','custom')),p.get('mode','prematch'),p.get('player1'),p.get('player2'),o['player1_win'],o['player2_win'],p.get('odds1'),p.get('odds2'),MODEL,json.dumps(p),p.get('surface'),p.get('tour'),p.get('round'),p.get('start_time')))
   return self.send_json(o|{'prediction_id':cur.lastrowid,'saved':True})
  if self.path=='/api/settle':return self.send_json({'ok':settle(int(p.get('prediction_id')),int(p.get('winner')),p.get('score'),'manual')})
  if self.path=='/api/sync-results':return self.send_json(sync_results())
  return self.send_json({'error':'not found'},404)

if __name__=='__main__':
 init_db();threading.Thread(target=auto_sync_loop,daemon=True).start();print('Didban Tennis: http://127.0.0.1:8775');ThreadingHTTPServer(('127.0.0.1',8775),Handler).serve_forever()
