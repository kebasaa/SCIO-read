"""Coverage-driven, serial pilot. Explicit --live is required to send requests."""
import argparse
import base64
import contextlib
import io
import json
import time
import uuid
from pathlib import Path
import requests
import numpy as np
import _bootstrap
from scio import cloud, credentials, session, store
from scio_offline import research as r


def probes(rows):
    base=rows[0]; payload=session.to_payload(base['record']); result=[]
    def add(name, changes):
        p=dict(payload)
        for role,b in changes.items(): p[role]=store.wrap_b64(b)
        edits={role:[{'offset':i,'before':x,'after':y} for i,(x,y) in enumerate(zip(base['blobs'][role],b)) if x!=y] for role,b in changes.items()}
        result.append({'name':name,'payload':p,'changes':edits})
    for role,b in sorted(base['blobs'].items()):
        for name,index in [('status',0),('word2',4),('begin',8),('middle',8+(len(b)-8)//2),('end',len(b)-1)]:
            v=bytearray(b); v[index]^=1; add(role+'_'+name,{role:bytes(v)})
    b=base['blobs']['sample']
    for i in (23,24,39,40):
        v=bytearray(b); v[i]^=1; add('sample_boundary_'+str(i),{'sample':bytes(v)})
    for role in sorted(base['blobs']):
        peer=next((x for x in rows[1:] if x['device']==base['device'] and x['blobs'][role]!=base['blobs'][role]),None)
        if peer: add(role+'_intact_substitution',{role:peer['blobs'][role]})
    # Preserve both byte sum and XOR exactly; no claim either is an integrity field.
    v=bytearray(b); v[24],v[25]=v[25],v[24]
    if v!=b: add('sample_swap_sum_xor_preserved',{'sample':bytes(v)})
    jobs=[{'name':'control_initial','payload':payload,'changes':{}}]
    for i,probe in enumerate(result,1):
        jobs.append(probe)
        if i%6==0: jobs.append({'name':'control_'+str(i),'payload':payload,'changes':{}})
    jobs.append({'name':'control_final','payload':payload,'changes':{}})
    if len(jobs)>60: raise ValueError('pilot exceeds request budget')
    return jobs


def gradient_followup(rows,previous):
    """Use only the unused budget, after a completed successful primary pilot."""
    summary=json.loads((previous/'summary.json').read_text())
    if (previous/'halt.json').exists() or summary['requests'][-1]['name']!='control_final':
        raise ValueError('primary pilot did not finish cleanly')
    remaining=60-len(list(previous.glob('*_request.json')))
    base=rows[0]; peer=next(x for x in rows[1:] if x['device']==base['device'] and x['id']!=base['id'])
    jobs=[]
    def add(row,name,action=None,roles=()):
        payload=session.to_payload(row['record']); changes={}
        for role in roles:
            if action=='omit': del payload[role]
            elif action=='zero': payload[role]=store.wrap_b64(bytes(len(row['blobs'][role])))
            elif action=='flip':
                b=bytearray(row['blobs'][role]); b[8]^=1; payload[role]=store.wrap_b64(bytes(b))
            changes[role]={'operation':action,'offset':8 if action=='flip' else None}
        jobs.append({'name':name,'payload':payload,'changes':changes,'control_group':row['id']})
    roles=('sample_gradient','sample_white_gradient')
    add(base,'control_initial')
    add(base,'omit_sample_gradient','omit',roles[:1]); add(base,'omit_white_gradient','omit',roles[1:])
    add(base,'omit_both_gradients','omit',roles); add(base,'control_base')
    add(base,'zero_both_gradients','zero',roles)
    add(peer,'control_peer')
    add(peer,'peer_sample_gradient_flip','flip',roles[:1]); add(peer,'peer_white_gradient_flip','flip',roles[1:])
    add(peer,'peer_omit_both_gradients','omit',roles); add(peer,'control_final')
    if len(jobs)>remaining: raise ValueError('insufficient remaining pilot budget')
    return jobs


def run(out,live=False,followup_from=None):
    rows=r.contexts(); jobs=gradient_followup(rows,followup_from) if followup_from else probes(rows)
    return run_jobs(out,jobs,live,followup_from)


def run_jobs(out,jobs,live=False,followup_from=None):
    """Shared bounded transport for explicitly constructed evidence campaigns."""
    if len(jobs)>60: raise ValueError('pilot exceeds request budget')
    r.write_new(out/'plan.json',{'jobs':jobs,'max_requests':60,'min_gap_seconds':20})
    if not live: return
    if followup_from:
        r.write_new(followup_from/'followup_reservation.json',{'requests_reserved':len(jobs),'output':r.label(out)})
        time.sleep(20)
    try:
        # Existing login helper can print error bodies; do not expose them.
        with contextlib.redirect_stdout(io.StringIO()): token=credentials.get_token(prompt_if_needed=False)
    except Exception as exc:
        r.write_new(out/'halt.json',{'reason':'authentication unavailable','exception_type':type(exc).__name__}); return
    last=0; errors=0; baselines={}; statuses=[]
    for i,job in enumerate(jobs):
        dependency=job.get('requires_valid_spectrum')
        if dependency and not any(s['name']==dependency and s['status']==200 and s['spectrum'] for s in statuses):
            r.write_new(out/f'{i:02d}_skipped.json',{'name':job['name'],'reason':'required earlier spectrum unavailable','dependency':dependency})
            continue
        time.sleep(max(0,20-(time.monotonic()-last)))
        encoded=json.dumps(job['payload'],sort_keys=True,separators=(',',':')).encode()
        r.write_new(out/f'{i:02d}_request.json',{'name':job['name'],'payload':job['payload'],'payload_sha256':r.sha(encoded),'changes':job['changes'],'control_group':job.get('control_group','primary'),'started_at':store.now_iso()})
        status=0; response={}; spectrum=None
        try:
            resp=requests.post(cloud.SPECTRO_URL,json=job['payload'],headers={'Authorization':'Bearer '+token,'Accept':'application/json','X-SCiO-Client-Version':'Android 1.3.8.554','X-Request-ID':str(uuid.uuid4())},timeout=45)
            status=resp.status_code
            try: response=resp.json()
            except ValueError: response={'non_json_sha256':r.sha(resp.content),'bytes':len(resp.content)}
            # Redact authentication echoes without losing the spectral response.
            serialized=json.dumps(response).replace(token,'<redacted>')
            response=json.loads(serialized)
            if status==200:
                _,spectrum=cloud.spectrum_from_response(response)
                if len(spectrum)!=331 or not np.isfinite(spectrum).all(): spectrum=None
        except Exception as exc: response={'exception_type':type(exc).__name__}
        last=time.monotonic()
        r.write_new(out/f'{i:02d}_response.json',{'name':job['name'],'status':status,'response':response,'spectrum':spectrum,'finished_at':store.now_iso()})
        statuses.append({'name':job['name'],'status':status,'spectrum':spectrum is not None})
        print(i+1,len(jobs),job['name'],status,flush=True)
        errors=errors+1 if status==0 or status>=500 else 0
        reason=None
        if status in (401,403,429): reason='authentication or rate limit'
        if errors>=2: reason='repeated server/transport errors'
        if job['name'].startswith('control'):
            group=job.get('control_group','primary')
            if spectrum is None: reason='unchanged control failed'
            elif job.get('expected_spectrum') is not None and not np.allclose(spectrum,job['expected_spectrum'],atol=1e-6,rtol=1e-6): reason='historical control drift'
            elif group not in baselines: baselines[group]=spectrum
            elif not np.allclose(spectrum,baselines[group],atol=1e-6,rtol=1e-6): reason='unchanged control drift'
        if reason:
            r.write_new(out/'halt.json',{'reason':reason}); break
    r.write_new(out/'summary.json',{'requests':statuses,'limits':'Rejections do not establish a MAC, a cipher, key architecture, or processing order.'})


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True,type=Path); p.add_argument('--live',action='store_true'); p.add_argument('--followup-from',type=Path); a=p.parse_args(); run(a.output,a.live,a.followup_from)
