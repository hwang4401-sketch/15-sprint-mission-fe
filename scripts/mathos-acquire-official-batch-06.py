#!/usr/bin/env python3
from pathlib import Path
import hashlib, html, json, re, shutil, time, urllib.parse
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

R=Path('MathOS-official-source-batch-06'); O=R/'originals'; P=R/'source-pages'; I=R/'index'; D=R/'diagnostics'
for x in (O,P,I,D): x.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 MathOS-Official-Source-Audit/6.2','Accept-Language':'ko-KR,ko;q=0.9'})
logs=[]; rows=[]; errs=[]
DL='https://www.sje.go.kr/comm/nttFileDownload.do?fileKey={}'
P44=['https://www.sje.go.kr/sje/na/ntt/selectNttInfo.do?mi=52119&nttSn=3017872','https://www.sje.go.kr/sje/na/ntt/selectNttInfo.do?mi=52119&nttSn=3017873']
P49=['https://www.sje.go.kr/ssok/na/ntt/selectNttInfo.do?mi=52288&nttSn=3005934','https://www.sje.go.kr/ssok/na/ntt/selectNttInfo.do?mi=52288&nttSn=3005935','https://www.sje.go.kr/sje/na/ntt/selectNttInfo.do?mi=52522&nttSn=372646']
DP='https://dandi.pen.go.kr/board/repository/detail?noticeId=144&page=1'; DF='https://drive.google.com/drive/folders/1OYH46rr71gEqdS6gGwbLv8rQdjsFDe7x?usp=drive_link'
FB=[
('SRC-0044','54e7bcf67dbdd80d1b002b9cb155d951',P44[0],'편수자료 I 편수 일반'),('SRC-0044','22888c47df93aec825fb66c68d8b6aa2',P44[0],'편수자료 II-1 인문사회과학'),('SRC-0044','58d23868856f61afa87be1aeaa24ddae',P44[0],'편수자료 II-2 체육 음악 미술'),
('SRC-0049','d54b9b13a7218e249f925686e0e572c9',P49[0],'촘촘수학 1학년 1학기'),('SRC-0049','6b5ecaf645558e93e0046845fa4e9169',P49[0],'촘촘수학 1학년 2학기'),('SRC-0049','6ff9f9a33265c2064c06693c9e1dfe6e',P49[1],'촘촘수학 2학년 1학기'),('SRC-0049','719665bcf139866194c1b9c790574bf1',P49[1],'촘촘수학 2학년 2학기')]
E44=[('I-general',['편수자료','편수','일반']),('II-1-humanities-social',['편수자료','인문','사회']),('II-2-pe-music-art',['편수자료','체육','음악','미술']),('III-basic-science-information',['편수자료','기초','과학','정보'])]
E49=[('grade1-semester1',['촘촘','1학년','1학기']),('grade1-semester2',['촘촘','1학년','2학기']),('grade2-semester1',['촘촘','2학년','1학기']),('grade2-semester2',['촘촘','2학년','2학기'])]
E46=[('elementary-1-2-math',['초등','1','2학년','수학']),('elementary-1-2-integrated',['초등','1','2학년','통합']),('elementary-3-4-science-2',['초등','3','4학년','과학','2']),('elementary-3-4-science-1',['초등','3','4학년','과학']),('elementary-3-4-korean',['초등','3','4학년','국어']),('elementary-3-4-math',['초등','3','4학년','수학']),('elementary-5-6-korean',['초등','5','6학년','국어']),('elementary-5-6-social',['초등','5','6학년','사회']),('elementary-5-6-math',['초등','5','6학년','수학']),('elementary-5-6-practical-arts',['초등','5','6학년','실과'])]

def n(s): return re.sub(r'[^0-9A-Za-z가-힣]+','',html.unescape(s).replace('Ⅰ','I').replace('Ⅱ','II').replace('Ⅲ','III')).lower()
def sh(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def get(u,ref=None,t=180):
 st=time.time()
 try:
  q=S.get(u,headers={'Referer':ref} if ref else None,timeout=t,allow_redirects=True); logs.append({'url':u,'final_url':q.url,'status':q.status_code,'bytes':len(q.content),'type':q.headers.get('content-type',''),'cd':q.headers.get('content-disposition',''),'seconds':round(time.time()-st,2)}); q.raise_for_status(); return q
 except Exception as e: logs.append({'url':u,'error':repr(e),'seconds':round(time.time()-st,2)}); raise
def page(u,label):
 q=get(u,t=120); (P/f'{label}.html').write_bytes(q.content); q.encoding=q.apparent_encoding or q.encoding; return q.text
def name(q,fb):
 cd=q.headers.get('content-disposition','')
 for pat in [r"filename\*=UTF-8''([^;]+)",r'filename="([^"]+)"',r'filename=([^;]+)']:
  m=re.search(pat,cd,re.I)
  if m:
   z=urllib.parse.unquote(m.group(1).strip().strip('"'))
   try: z=z.encode('latin1').decode('utf-8')
   except: pass
   return re.sub(r'[\\/:*?"<>|]+','_',z)
 return re.sub(r'[\\/:*?"<>|]+','_',fb)
def info(p,k=35):
 r=PdfReader(str(p)); tx=[]
 for x in r.pages[:min(len(r.pages),k)]:
  try: tx.append(x.extract_text() or '')
  except: tx.append('')
 return len(r.pages),'\n'.join(tx)
def verify(p,label,tokens,minp):
 if p.read_bytes()[:5]!=b'%PDF-': raise RuntimeError('not PDF')
 pc,tx=info(p)
 if pc<minp: raise RuntimeError(f'pages {pc} < {minp}')
 h=n(label+' '+tx)
 miss=[x for x in tokens if n(x) not in h]
 if miss: raise RuntimeError(f'missing terms {miss}')
 return pc,tx

def keys(u,txt,sid):
 out=[]; soup=BeautifulSoup(txt,'html.parser')
 for e in soup.find_all(True):
  z=' '.join(str(e.get(a,'')) for a in ('href','onclick','data-url','data-file-key','value'))+' '+' '.join(e.stripped_strings)+' '+(' '.join(e.parent.stripped_strings) if e.parent else '')
  for k in re.findall(r'(?:fileKey=|fileKey[\'"\s,:=]+)([0-9a-fA-F]{32})',z): out.append((sid,k.lower(),u,z[:300]))
 for k in re.findall(r'[0-9a-fA-F]{32}',txt):
  i=txt.find(k); a=BeautifulSoup(txt[max(0,i-500):i+500],'html.parser').get_text(' ',strip=True)
  if any(x in a for x in ('pdf','PDF','첨부','촘촘','편수자료')): out.append((sid,k.lower(),u,a[:300]))
 return out

def expected(sid,label,tx):
 h=n(label+' '+tx); es=E44 if sid=='SRC-0044' else E49
 ok=[]
 for slug,t in es:
  if all(n(x) in h for x in t): ok.append((len(t),slug,t))
 return sorted(ok,reverse=True)[0][1:] if ok else None

def sje():
 c={}
 for sid,ps in [('SRC-0044',P44),('SRC-0049',P49)]:
  for i,u in enumerate(ps,1):
   try:
    tx=page(u,f'{sid}__SJE__page-{i}')
    for z in keys(u,tx,sid): c[z[1]]=z
   except Exception as e: errs.append({'source_id':sid,'stage':'page','url':u,'error':repr(e)})
 for z in FB: c.setdefault(z[1],z)
 used=set(); hashes=set()
 for sid,k,u,label in c.values():
  try:
   q=get(DL.format(k),u,300); fn=name(q,label+'.pdf'); p=D/'sje-candidates'/f'{sid}__{k}__{fn}'; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(q.content)
   pc,tx=info(p); m=expected(sid,fn+' '+label,tx)
   if not m: raise RuntimeError(f'unmatched title {fn}')
   slug,t=m; pc,_=verify(p,fn+' '+label,t,20 if sid=='SRC-0044' else 40); hh=sh(p)
   if (sid,slug) in used or hh in hashes: continue
   used.add((sid,slug)); hashes.add(hh); cat='content-production' if sid=='SRC-0044' else 'math-remediation'; dst=O/cat/f'{sid}__SJE__{slug}.pdf'; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dst)
   rows.append({'source_id':sid,'title':fn.rsplit('.',1)[0],'publisher':'세종특별자치시교육청','source_page_url':u,'official_attachment_url':q.url,'official_file_key':k,'file_name':dst.name,'relative_path':dst.relative_to(R).as_posix(),'size_bytes':dst.stat().st_size,'sha256':sh(dst),'signature':'PDF','pdf_pages':pc,'status':'VERIFIED','rights_status':'RIGHTS_UNREVIEWED'})
  except Exception as e: errs.append({'source_id':sid,'stage':'download/verify','file_key':k,'page':u,'error':repr(e)})

def dandi():
 try:
  tx=page(DP,'SRC-0046__PEN-DANDI__notice-144')
  if '1OYH46rr71gEqdS6gGwbLv8rQdjsFDe7x' not in tx: raise RuntimeError('Drive folder absent from official page')
  import gdown
  st=D/'dandi-drive'; shutil.rmtree(st,ignore_errors=True); st.mkdir(parents=True)
  if not gdown.download_folder(url=DF,output=str(st),quiet=False,use_cookies=False,remaining_ok=True): raise RuntimeError('no Drive files')
  used=set()
  for p in sorted(st.rglob('*.pdf')):
   z=n(p.name); match=None
   for slug,t in E46:
    if slug in used or not all(n(x) in z for x in t): continue
    if slug.endswith('science-2') and not ('과학2' in z or '과학_2' in p.name): continue
    if slug.endswith('science-1') and ('과학2' in z or '과학_2' in p.name): continue
    match=(slug,t); break
   if not match: continue
   slug,t=match; pc,_=verify(p,p.name,['디지털','미디어','리터러시','초등'],5); dst=O/'digital-learning'/f'SRC-0046__PEN-DANDI__{slug}.pdf'; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dst); used.add(slug)
   rows.append({'source_id':'SRC-0046','title':p.stem,'publisher':'부산광역시교육청','source_page_url':DP,'official_attachment_url':DF,'official_file_name':p.name,'file_name':dst.name,'relative_path':dst.relative_to(R).as_posix(),'size_bytes':dst.stat().st_size,'sha256':sh(dst),'signature':'PDF','pdf_pages':pc,'status':'VERIFIED','rights_status':'RIGHTS_UNREVIEWED'})
  miss=[x for x,_ in E46 if x not in used]
  if miss: errs.append({'source_id':'SRC-0046','stage':'completeness','missing':miss})
 except Exception as e: errs.append({'source_id':'SRC-0046','stage':'page/Drive','error':repr(e)})

def main():
 sje(); dandi(); rows.sort(key=lambda x:(x['source_id'],x['file_name']));
 (I/'verified-originals.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8'); (I/'errors.json').write_text(json.dumps(errs,ensure_ascii=False,indent=2),encoding='utf-8'); (I/'request-log.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2),encoding='utf-8')
 by={}
 for x in rows: by[x['source_id']]=by.get(x['source_id'],0)+1
 need={'SRC-0044':4,'SRC-0046':10,'SRC-0049':4}; comp={k:by.get(k,0)>=v for k,v in need.items()}; sm={'batch':'MathOS-official-source-batch-06','verified_original_files':len(rows),'verified_by_source':by,'expected_minimum_by_source':need,'complete_by_source':comp,'all_three_sources_complete':all(comp.values()),'error_count':len(errs),'canonical_vault_promotion':'NOT_PERFORMED','rights_review':'NOT_COMPLETED'}
 (I/'summary.json').write_text(json.dumps(sm,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(sm,ensure_ascii=False,indent=2))
main()
