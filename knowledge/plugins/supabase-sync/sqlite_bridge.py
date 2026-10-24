#!/usr/bin/env python3
import argparse,json,sqlite3,hashlib,sys
from pathlib import Path
from datetime import datetime,timezone
def digest(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def main():
 p=argparse.ArgumentParser(); p.add_argument('command',choices=['export','import','ack']); p.add_argument('--db',default=str(Path.home()/'.mnemos'/'memory.sqlite3')); p.add_argument('--output'); p.add_argument('--input'); p.add_argument('--snapshot'); a=p.parse_args()
 d=sqlite3.connect(str(Path(a.db).expanduser())); d.row_factory=sqlite3.Row
 names={x[0] for x in d.execute("select name from sqlite_master where type='table'")}
 if not {'memories','links'}<=names: raise RuntimeError('expected memories and links tables')
 if a.command=='export':
  ms=[]
  for rr in d.execute('select * from memories'):
   r=dict(rr); raw=r.get('tags',r.get('tags_json','[]')); meta=r.get('metadata',r.get('metadata_json','{}'))
   try: tags=json.loads(raw) if isinstance(raw,str) else raw
   except Exception: tags=[]
   try: metadata=json.loads(meta) if isinstance(meta,str) else meta
   except Exception: metadata={}
   ms.append({'id':r['id'],'content':r.get('content',''),'kind':r.get('kind','note'),'tags':tags if isinstance(tags,list) else [],'source':r.get('source'),'metadata':metadata if isinstance(metadata,dict) else {},'created_at':r.get('created_at'),'updated_at':r.get('updated_at')})
  ls=[{'source_id':r['source_id'],'target_id':r['target_id'],'relation':r['relation'],'created_at':r['created_at'] if 'created_at' in r.keys() else None} for r in d.execute('select * from links')]
  payload={'format':'mnemos-export-v1','exported_at':datetime.now(timezone.utc).isoformat(),'memories':ms,'links':ls}
  if not a.output: raise RuntimeError('--output required')
  Path(a.output).write_text(json.dumps(payload,ensure_ascii=False)+'\\n',encoding='utf-8')
  print(json.dumps({'snapshot_id':digest(payload),'memories':len(ms),'links':len(ls),'outbox_pending':'not safely identifiable; no rows acknowledged'})); return
 if a.command=='ack': raise RuntimeError('ACK disabled until a stable outbox schema and immutable row fingerprint are available; no data acknowledged')
 if not a.input: raise RuntimeError('--input required')
 payload=json.loads(Path(a.input).read_text()); mc={x[1] for x in d.execute('pragma table_info(memories)')}; lc={x[1] for x in d.execute('pragma table_info(links)')}; added=updated=preserved=0
 for m in payload.get('memories',[]):
  old=d.execute('select * from memories where id=?',(m['id'],)).fetchone(); local=dict(old) if old else {}; rt=str(m.get('updated_at') or m.get('created_at') or ''); lt=str(local.get('updated_at') or local.get('created_at') or '')
  if old and (not rt or rt<=lt): preserved+=1; continue
  vals={'id':m['id'],'content':m.get('content',''),'kind':m.get('kind','note'),'tags_json':json.dumps(m.get('tags',[]) if isinstance(m.get('tags'),list) else []),'source':m.get('source'),'metadata_json':json.dumps(m.get('metadata',{})),'created_at':m.get('created_at') or rt,'updated_at':rt}
  if not old:
   cc=[c for c in ('id','content','kind','tags_json','source','metadata_json','created_at','updated_at') if c in mc]; d.execute('insert into memories ('+','.join(cc)+') values ('+','.join('?' for _ in cc)+')',[vals[c] for c in cc]); added+=1
  else:
   cc=[c for c in ('content','kind','tags_json','source','metadata_json','updated_at') if c in mc]; d.execute('update memories set '+','.join(c+'=?' for c in cc)+' where id=?',[vals[c] for c in cc]+[m['id']]); updated+=1
 for l in payload.get('links',[]):
  if d.execute('select 1 from links where source_id=? and target_id=? and relation=?',(l['source_id'],l['target_id'],l.get('relation','relates_to'))).fetchone(): continue
  if d.execute('select count(*) from memories where id in (?,?)',(l['source_id'],l['target_id'])).fetchone()[0]!=2: continue
  vals={'source_id':l['source_id'],'target_id':l['target_id'],'relation':l.get('relation','relates_to'),'created_at':l.get('created_at')}; cc=[c for c in ('source_id','target_id','relation','created_at') if c in lc]; d.execute('insert or ignore into links ('+','.join(cc)+') values ('+','.join('?' for _ in cc)+')',[vals[c] for c in cc])
 d.commit(); print(json.dumps({'memories_added':added,'memories_updated':updated,'memories_preserved_local':preserved,'local_deletes':0}))
if __name__=='__main__':
 try: main()
 except Exception as e: print('sqlite_bridge: '+str(e),file=sys.stderr); sys.exit(2)
