"""Bounded header-derived hypotheses. No device/network operations or spectral claims."""
from __future__ import annotations

import base64
import bz2
import copy
import gzip
import hashlib
import hmac
import json
import io
import lzma
import random
import sqlite3
import struct
import zlib
from pathlib import Path

from cryptography.hazmat.primitives import cmac
from cryptography.hazmat.primitives.ciphers import algorithms
from . import bounded_campaign as codecs, contributor_firmware as fw, research as r, search_v2

KEY_LIMIT = 4096
STAGE_VERSION = 'checksum-codecs-integrity-v1'


def digest(value):
    return r.sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def derivations(seed):
    out = {'md5': hashlib.md5(seed).digest(), 'sha256_16': hashlib.sha256(seed).digest()[:16],
           'sha256': hashlib.sha256(seed).digest()}
    if len(seed) in (16,32): out['raw'] = seed
    if 0 < len(seed) < 16:
        out['zeropad16'] = seed + bytes(16-len(seed))
        out['repeat16'] = (seed * (16//len(seed)+1))[:16]
    return out


def representations(words):
    return {'u32le': struct.pack('<'+'I'*len(words),*words),
            'u32be': struct.pack('>'+'I'*len(words),*words),
            'decimal': ':'.join(str(x) for x in words).encode(),
            'hex': ':'.join(f'{x:08x}' for x in words).encode()}


def keys_for(profile):
    fw.validate_profile(profile)
    known={'owner_fw147':{'dsp_id':'e24da26b2304c2c0','aptina_field':'328045ab1161f198'},
           'contributor_fw138':{'dsp_id':'5291a26b2304c2c0','aptina_field':'2ee0f4607c6b5fd5'}}
    if any(profile.get(k) and profile[k].lower()!=v for k,v in known[profile['profile_id']].items()):
        raise ValueError('mixed device identity field')
    headers = profile['file_headers']; keys = {}; missing = []
    seeds = {'boot_checksum':[headers['dsp_boot'][3]], 'dec_checksum':[headers['dsp_dec'][3]],
             'boot_dec_checksums':[headers[n][3] for n in ('dsp_boot','dsp_dec')],
             'boot_header':headers['dsp_boot'], 'dec_header':headers['dsp_dec'],
             'four_checksums':[headers[n][3] for n in ('ble','dsp_boot','dsp_dec','dsp_op')]}
    def add(label,seed):
        for form,key in derivations(seed).items(): keys.setdefault(key,[]).append(label+'.'+form)
    identities = {}
    for name in ('device_id','dsp_id','aptina_field'):
        value = profile.get(name)
        if not value:
            missing.append(name); continue
        raw = bytes.fromhex(value)
        identities[name] = {'raw':raw,'reverse':raw[::-1], 'lower':value.lower().encode(),
                            'upper':value.upper().encode()}
    for name,words in seeds.items():
        for rep,seed in representations(words).items():
            label = name+'.'+rep; add(label,seed)
            if name not in ('boot_checksum','dec_checksum','boot_dec_checksums'): continue
            for identity,forms in identities.items():
                for form,value in forms.items():
                    add(label+'+identity.'+identity+'.'+form,seed+value)
                    add('identity.'+identity+'.'+form+'+'+label,value+seed)
    return {k:sorted(set(v)) for k,v in keys.items()}, missing


def delta_keys():
    out = {}
    for delta in (-673,-26):
        for name,seed in {'signed_le':struct.pack('<i',delta),'signed_be':struct.pack('>i',delta),
                          'decimal':str(delta).encode()}.items():
            for form,key in derivations(seed).items():
                out.setdefault(key,[]).append(f'diagnostic.delta={delta}.{name}.{form}')
    return out


def check_cap(key_sets):
    count = len(set().union(*(set(x) for x in key_sets)))
    if count > KEY_LIMIT: raise ValueError('unique-key limit exceeded; revise plan, do not truncate')
    return count


def transform(blob,key,config):
    """No silent CBC/ECB truncation; reuse established AES IV constructions."""
    if len(blob)<24: raise ValueError('short blob')
    mode,iv,trailer = config
    body_len = len(blob)-8-trailer-(16 if iv=='first_block' else 0)
    if trailer not in (0,16) or body_len<=0: raise ValueError('invalid framing')
    if mode in ('ECB','CBC') and body_len%16: raise ValueError('unaligned block body')
    return search_v2.transform(blob,key,config)


def unique_entries(entries):
    seen = set(); out = []
    for entry in entries:
        identity = (entry['role'],r.sha(entry['blob']))
        if identity not in seen: out.append(entry);seen.add(identity)
    return out


def codec_checks(data):
    """Use established codec limits; expose image failures and missing support."""
    failures={};hits=[]
    def mark(tag): failures[tag]=failures.get(tag,0)+1
    def images(source):
        result=[]
        try:
            from PIL import Image
        except ImportError:
            mark('image:ImportError');return result
        for marker in (b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n',b'\xff\x4f\xff\x51',
                       b'\x00\x00\x00\x0cjP',b'II*\x00',b'MM\x00*',b'GIF8',b'RIFF'):
            start=0
            while (offset:=source.find(marker,start))>=0:
                start=offset+1
                try:
                    with Image.open(io.BytesIO(source[offset:])) as image:
                        if image.width*image.height>65536:mark('image:limit');continue
                        image.load()
                        result.append({'codec':'image','offset':offset,'format':image.format,
                            'size':list(image.size),'sha256':r.sha(image.tobytes()),'consumed':None,
                            'trailing':None,'extent_verified':False})
                except (OSError,ValueError,SyntaxError,Image.DecompressionBombError) as exc:
                    mark('image:'+type(exc).__name__)
        return result
    hits.extend(images(data))
    for offset in (0,4,8,16):
        source=data[offset:]
        for name,factory in [('zlib',lambda:zlib.decompressobj(15)),('deflate',lambda:zlib.decompressobj(-15)),
                ('gzip',lambda:zlib.decompressobj(31)),('bzip2',bz2.BZ2Decompressor),('xz',lzma.LZMADecompressor)]:
            try:
                decoder=factory();plain=decoder.decompress(source,codecs.LIMIT+1)
                if len(plain)>codecs.LIMIT:status='limit'
                elif not decoder.eof:status='incomplete'
                elif len(plain)<32:status='short_parse'
                else:
                    trailing=len(decoder.unused_data)
                    hits.append({'codec':name,'offset':offset,'bytes':len(plain),'sha256':r.sha(plain),
                        'consumed':len(source)-trailing,'trailing':trailing,
                        'trailing_zero':not any(decoder.unused_data),'inner_images':images(plain)})
                    status='hit'
            except (zlib.error,OSError,EOFError,ValueError,lzma.LZMAError,ImportError) as exc:status=type(exc).__name__
            mark(name+':'+status)
    return {'hits':hits,'codec_outcomes':failures}


def evaluate_decode(key,config,entries):
    """Confirm sample and dark separately, never require gradients or smoothness."""
    entries = unique_entries(entries); outcomes = []; signatures = {}; recovered = {}
    for role in ('sample','sample_dark'):
        selected = [e for e in entries if e['role']==role]
        if not selected: continue
        lead = False; common = None
        for index,entry in enumerate(selected):
            if index and not lead: break
            try:
                plain = entry['blob'][8:] if key is None else transform(entry['blob'],key,config)
                result = codec_checks(plain)
                hit_signatures = {digest({k:v for k,v in hit.items() if k in ('codec','offset','format','size','bytes')})
                                  for hit in result['hits']}
                common = hit_signatures if common is None else common & hit_signatures
                recovered[entry['source']+':'+role] = plain
                lead |= bool(result['hits'])
                outcomes.append({'role':role,'source':entry['source'],'group':entry['group'],
                                 'plaintext_sha256':r.sha(plain),'codec':result})
            except (ValueError,TypeError,ImportError) as exc:
                outcomes.append({'role':role,'source':entry['source'],'error':type(exc).__name__})
                common=set()
        groups = {e['group'] for e in selected}
        signatures[role] = {'consistent_signatures':sorted(common or []),
                            'acquisitions_available':len(groups)}
    lead = any(row.get('codec',{}).get('hits') for row in outcomes)
    candidate = any(v['consistent_signatures'] and v['acquisitions_available']>=3 for v in signatures.values())
    # Matching signatures alone are NOT structural validation; boundaries still need review.
    return {'status':'cross_acquisition_codec_lead' if candidate else 'codec_lead' if lead else 'no_codec_hit',
            'classification':'unvalidated', 'outcomes':outcomes,'same_role_confirmation':signatures}, recovered


def messages(blob,device_id):
    if len(blob)<8: raise ValueError('short integrity blob')
    body=blob[8:]
    return {'body':body,'word0_body':blob[:4]+body,'device_body':bytes.fromhex(device_id)+body}


def integrity_digest(key,algorithm,message):
    if algorithm=='HMAC-SHA256': return hmac.new(key,message,hashlib.sha256).digest()
    if algorithm=='AES-CMAC':
        engine=cmac.CMAC(algorithms.AES(key));engine.update(message);return engine.finalize()
    raise ValueError('unsupported integrity algorithm')


def integrity_value(key,config,blob,device_id):
    algorithm,layout,end,endian=config
    raw=integrity_digest(key,algorithm,messages(blob,device_id)[layout])
    part=raw[:4] if end=='first' else raw[-4:]
    return int.from_bytes(part,endian)


def integrity_configs():
    for algorithm in ('AES-CMAC','HMAC-SHA256'):
        for layout in ('body','word0_body','device_body'):
            for end in ('first','last'):
                for endian in ('little','big'): yield (algorithm,layout,end,endian)


def evaluate_integrity(key,config,entries,device_id):
    leads=[]
    for role in sorted({e['role'] for e in entries}):
        selected=[e for e in unique_entries(entries) if e['role']==role]
        matched=[]
        for entry in selected:
            expected=int.from_bytes(entry['blob'][4:8],'little')
            if integrity_value(key,config,entry['blob'],device_id)!=expected: break
            matched.append(entry)
        if matched:
            groups={e['group'] for e in matched}
            leads.append({'role':role,'matched_distinct_blobs':len(matched),'groups':sorted(groups),
                          'all_selected_match':len(matched)==len(selected),
                          'confirmed':len(matched)>=10 and len(groups)>=3 and len(matched)==len(selected)})
    return {'status':'integrity_candidate' if any(x['confirmed'] for x in leads)
            else 'integrity_lead' if leads else 'no_match','leads':leads}


def prior_coverage():
    path=r.DEV/'analysis_output/bounded_identity_20261004_run/manifest.json.gz'
    if not path.is_file(): raise ValueError('prior exact manifest missing')
    with gzip.open(path,'rt',encoding='utf-8') as stream: manifest=json.load(stream)
    seen={(row['key_sha256'],tuple(row['config'][1:])) for row in manifest['configurations']
          if row['config'][0]=='AES' and not row['stage'].endswith('controls')}
    return seen,{r.label(path):r.sha(path.read_bytes())}


def prepare():
    contributor=fw.load_profile(r.DEV/'profiles/contributor_fw138.json')
    owner=copy.deepcopy(fw.OWN)
    # Observed owner identity, not copied from contributor or merged across devices.
    identity_path=r.ROOT/'01_rawdata/scan_json/scan_20260907_185032_current_static_003.json'
    observed=json.loads(identity_path.read_text())['device']
    if observed['device_id']!=owner['device_id'] or observed['ble_id'].upper()!=owner['ble_id']:
        raise ValueError('owner identity mismatch')
    owner.update({k:observed[k] for k in ('dsp_id','aptina_field')})
    rows=[x for x in r.contexts() if x['device'].get('device_id')==owner['device_id']
          and x['acquisition_group']<'2026-10-03']
    rows.sort(key=lambda x:(x['acquisition_group'],x['id']))
    selected=[]
    for row in rows:
        if row['acquisition_group'] not in {x['acquisition_group'] for x in selected}: selected.append(row)
        if len(selected)==3: break
    if len(selected)!=3: raise ValueError('three owner acquisition groups required')
    def entries(records):
        return unique_entries([{'source':row['source'],'group':row['acquisition_group'],'role':role,'blob':blob}
            for row in records for role,blob in row['blobs'].items()])
    foreign_path=r.DEV/'analysis_output/foreign_fw138_20261008/device.json'
    foreign=json.loads(foreign_path.read_text())
    if foreign['device']['device_id']!=contributor['device_id']: raise ValueError('foreign identity mismatch')
    foreign_entries=[]
    for role,text in foreign['blobs_b64'].items():
        blob=base64.b64decode(text,validate=True)
        if r.sha(blob)!=foreign['blob_sha256'][role]: raise ValueError('foreign blob hash mismatch')
        foreign_entries.append({'source':r.label(foreign_path),'group':foreign['contributed_at'],'role':role,'blob':blob})
    groups={owner['profile_id']:{'profile':owner,'decode':entries(selected),'integrity':entries(rows)},
            contributor['profile_id']:{'profile':contributor,'decode':foreign_entries,'integrity':foreign_entries}}
    keysets={}; missing={}
    for name,group in groups.items(): keysets[name],missing[name]=keys_for(group['profile'])
    diagnostic=delta_keys(); unique_count=check_cap([*keysets.values(),diagnostic])
    seen,prior_hashes=prior_coverage(); configs=list(search_v2.configurations(True)); jobs=[]; skipped=0
    rng=random.Random(81382026)
    controls={rng.randbytes(length):['random-key-control'] for length in [16,32]*8}
    for name,group in groups.items():
        jobs.append((name,'direct',None,None,'compression-only'))
        for family,keys in [('header',keysets[name]),('delta',diagnostic),('random-key',controls),('random-body',controls)]:
            for key in sorted(keys):
                for config in configs:
                    if name==owner['profile_id'] and family in ('header','delta') and (r.sha(key),config) in seen:
                        skipped+=1;continue
                    jobs.append((name,'decode',key,config,family))
                for config in integrity_configs(): jobs.append((name,'integrity',key,config,family))
    sources={row['source'] for row in rows}|{r.label(foreign_path),contributor['provenance']['source'],
            'dev/profiles/contributor_fw138.json','README.md',r.label(identity_path)}
    selected_hashes={p:r.sha((r.ROOT/p).read_bytes()) for p in sorted(sources)}
    import subprocess
    manifest={'schema':'scio-checksum-campaign/1','stage_version':STAGE_VERSION,
        'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r.ROOT,text=True).strip(),
        'profiles':[group['profile'] for group in groups.values()], 'unique_hypothesis_keys':unique_count,
        'keys':{name:[{'sha256':r.sha(k),'labels':v} for k,v in sorted(keys.items())] for name,keys in keysets.items()},
        'diagnostic_keys':[{'sha256':r.sha(k),'labels':v} for k,v in sorted(diagnostic.items())],
        'missing_identifiers':missing,'prior_hashes':prior_hashes,'skipped_exact_owner_aes_configurations':skipped,
        'historical_header_association':'Owner current headers on older scans: exploratory, not established',
        'foreign_association':'Contributor-reported headers and scan, no independent firmware body verification',
        'frozen_policy':'Only owner acquisitions before 2026-10-03; frozen cap files not loaded',
        'input_file_hashes':selected_hashes,
        'code_hashes':{r.label(Path(m.__file__)):r.sha(Path(m.__file__).read_bytes()) for m in
                       (r,search_v2,codecs,fw)},
        'evaluator_sha256':r.sha(Path(__file__).read_bytes()),
        'driver_sha256':r.sha((r.DEV/'scripts/checksum_campaign.py').read_bytes()),
        'inputs':{name:{kind:[{k:v for k,v in e.items() if k!='blob'}|{'sha256':r.sha(e['blob'])}
                            for e in group[kind]] for kind in ('decode','integrity')} for name,group in groups.items()},
        'jobs':[{'profile':n,'kind':t,'key_sha256':r.sha(k) if k else None,'config':c,'family':f}
                for n,t,k,c,f in jobs]}
    try:
        from PIL import Image,features
        Image.init()
        manifest['image_capabilities']={'plugins':{name:name in Image.OPEN for name in ('JPEG','JPEG2000','PNG','TIFF','GIF','WEBP')},
                                      'backends':{name:features.check(name) for name in ('jpg','jpg_2000','zlib','libtiff','webp')}}
    except ImportError: manifest['image_capabilities']={'available':False,'exception':'ImportError'}
    return manifest,jobs,groups


def run(out,manifest,jobs,groups,*,max_jobs=None):
    out=fw.inside_dev(out); private=fw.inside_dev(r.DEV/'private'/'checksum_campaign'/(out.name+'_'+r.sha(r.label(out).encode())[:8]))
    path=out/'manifest.json.gz'
    if path.exists():
        with gzip.open(path,'rt',encoding='utf-8') as stream: prior=json.load(stream)
        if prior!=json.loads(json.dumps(manifest)): raise ValueError('resume manifest mismatch')
    else:
        fw.save_bytes(path,gzip.compress(json.dumps(manifest,sort_keys=True).encode(),mtime=0))
    private.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(private/'results.sqlite',timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS results(job INTEGER PRIMARY KEY, identity TEXT, profile TEXT, kind TEXT, family TEXT, status TEXT, result TEXT)')
    identity=digest(manifest); count=0
    try:
        for index,(name,kind,key,config,family) in enumerate(jobs):
            previous=db.execute('SELECT identity FROM results WHERE job=?',(index,)).fetchone()
            if previous:
                if previous[0]!=identity: raise ValueError('checkpoint mismatch')
                continue
            group=groups[name]; inputs=group['integrity' if kind=='integrity' else 'decode']
            if family=='random-body':
                rng=random.Random(286731)
                inputs=[{**entry,'blob':entry['blob'][:8]+rng.randbytes(len(entry['blob'])-8)} for entry in inputs]
            if kind=='integrity': result=evaluate_integrity(key,config,inputs,group['profile']['device_id'])
            else:
                result,recovered=evaluate_decode(key,config,inputs)
                if result['status']=='cross_acquisition_codec_lead':
                    for i,(source,body) in enumerate(recovered.items()):
                        target=private/f'lead_{index}_{i}.bin'
                        if not target.exists(): fw.save_bytes(target,body)
            db.execute('INSERT INTO results VALUES(?,?,?,?,?,?,?)',(index,identity,name,kind,family,result['status'],json.dumps(result)))
            count+=1
            if count%250==0:
                db.commit(); print(f'completed {index+1}/{len(jobs)} {name} {kind} {family}',flush=True)
            if max_jobs is not None and count>=max_jobs: break
        db.commit()
        stats=[{'profile':a,'kind':b,'family':c,'status':d,'count':n} for a,b,c,d,n in
            db.execute('SELECT profile,kind,family,status,COUNT(*) FROM results GROUP BY profile,kind,family,status')]
        completed=db.execute('SELECT COUNT(*) FROM results').fetchone()[0]
        summary={'completed':completed,'enumerated':len(jobs),'complete':completed==len(jobs),'outcomes':stats,
                 'validated_intermediate':False,'validated_reflectance':False,'validated_domain_vectors':False,
                 'limits':'Codec matches require boundary review; current owner headers on historical scans are unverified; foreign track has one acquisition'}
        checkpoint=out/f'summary_{completed}.json'
        if not checkpoint.exists(): r.write_new(checkpoint,summary)
        if completed==len(jobs) and not (out/'outcomes.json.gz').exists():
            # Lossless configuration outcomes without key bytes, firmware bodies or personal paths.
            rows=[{'job':i,'identity':ident,'profile':n,'kind':kind,'family':fam,'result':json.loads(result)}
                  for i,ident,n,kind,fam,result in db.execute('SELECT job,identity,profile,kind,family,result FROM results ORDER BY job')]
            fw.save_bytes(out/'outcomes.json.gz',gzip.compress(json.dumps(rows).encode(),mtime=0))
        return summary
    finally: db.close()


def audit_apps(apps,out):
    """Static, bounded call-site audit; never turns a filename into device authority."""
    apps=Path(apps).resolve();out=fw.inside_dev(out)
    names={'SCiOBLeService.java','ScioInternalDevice.java','FirmwareUpgradeModel.java',
           'FirmwareUpgradeActivity.java','CommandIDs.java','ScioCommands.java'}
    import re
    pattern=re.compile(r'performFileDownload|performReadFileHeader|performReadFileList|READ_FILE|FILE_DOWNLOAD|getChecksumData|getByteData|localChecksums|device_id|compression_version')
    files=[]
    for path in sorted(apps.rglob('*.java')):
        if path.name not in names: continue
        raw=path.read_bytes();lines=raw.decode('utf-8',errors='replace').splitlines()
        anchors=[{'line':i+1,'text':line.strip()[:400]} for i,line in enumerate(lines) if pattern.search(line)]
        files.append({'source':path.relative_to(apps).as_posix(),'sha256':r.sha(raw),'anchors':anchors})
    report={'files':files,'inspected_files':len(files),'supported_body_read_found':False,
            'device_commands_sent':0,
            'coverage_limit':'Named Java command/model/activity call sites, not proof that undocumented device firmware has no read operation',
            'findings':{'0x87':'READ_FILE_HEADER: LE file ID; four U32 response words; checksum at offset 12',
                        '0x94':'READ_FILE_LIST: file IDs/versions, not bodies',
                        '0x81':'FILE_DOWNLOAD sets outbound firmware bytes and write type; host-to-device write',
                        'misleading_log':'performFileDownload logs performReadFileList entered; log text is not operation direction',
                        'checksum':'Model separates first four bytes; inspected host code does not calculate a body byte sum'}}
    r.write_new(out/'usb_ble_audit.json',report)
    return report


def inspect_artifacts(out,artifact,name,format='raw',compare=None):
    """Preserve supplied artifacts; structural leads only, never arbitrary key windows."""
    out=fw.inside_dev(out)
    if out.exists(): raise FileExistsError('new inspection directory required')
    private=fw.inside_dev(r.DEV/'private'/'checksum_artifacts'/(out.name+'_'+r.sha(r.label(out).encode())[:8]))
    profiles=[fw.OWN,fw.load_profile(r.DEV/'profiles/contributor_fw138.json')]
    from .firmware import entropy,parse_ldr
    from .keyrecover import find_signatures
    records=[];bodies=[]
    for index,path in enumerate([artifact]+([compare] if compare else [])):
        path=Path(path)
        if path.stat().st_size>32*1024*1024: raise ValueError('artifact size limit')
        raw=path.read_bytes();fw.save_bytes(private/f'{index}_original.bin',raw)
        if format=='container':
            if len(raw)<=4: raise ValueError('short firmware container')
            body=raw[4:];meta=fw.describe(name,raw,profiles)
            fw.save_bytes(private/f'{index}_prefix.bin',raw[:4])
        elif format=='raw':
            body=raw;meta={'name':name,'body_bytes':len(body),'body_sha256':r.sha(body),
                'entropy_bits_per_byte':entropy(body),'unsigned_byte_sum':sum(body),
                'blackfin_ldr':parse_ldr(body),'checksum_algorithm_established':False,
                'header_comparisons':{p['profile_id']:{'matches_current_size':len(body)==p['file_headers'][name][1]}
                                      for p in profiles}}
        else: raise ValueError('unsupported artifact format')
        fw.save_bytes(private/f'{index}_body.bin',body)
        meta.update(original_sha256=r.sha(raw),format=format,cipher_signature_leads=find_signatures(body),
                    signature_limit='Library constants do not identify a used cipher or key',
                    architecture_limit='8051/Blackfin identity requires instruction and control-flow analysis')
        records.append(meta);bodies.append(body)
    result={'artifacts':records,'vendor_files_private':True,'network_requests':0,'device_commands':0}
    if len(bodies)==2:
        a,b=bodies;ranges=[];start=None;count=0
        for offset in range(max(len(a),len(b))):
            different=offset>=len(a) or offset>=len(b) or a[offset]!=b[offset]
            if different:
                count+=1
                if start is None:start=offset
            elif start is not None:
                if len(ranges)<256:ranges.append([start,offset])
                start=None
        if start is not None and len(ranges)<256:ranges.append([start,max(len(a),len(b))])
        result['comparison']={'equal_length':len(a)==len(b),'differing_positions':count,
            'first_256_half_open_ranges':ranges,'interpretation':'Byte differences only; does not establish personalization or keys'}
    r.write_new(out/'inspection.json',result)
    return result
