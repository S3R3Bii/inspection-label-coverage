"""Capture one official bulk file; publish only the prespecified factual projection."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,gzip,hashlib,io,json,subprocess,zipfile
import requests

ROOT=Path(__file__).resolve().parents[1]
FIELDS={
 'facilities':['PGM_SYS_ID','STATE','EPA_REGION','AIR_POLLUTANT_CLASS_CODE','AIR_OPERATING_STATUS_CODE'],
 'evaluations':['PGM_SYS_ID','ACTIVITY_ID','STATE_EPA_FLAG','COMP_MONITOR_TYPE_CODE','ACTUAL_END_DATE'],
 'stack_tests':['PGM_SYS_ID','ACTIVITY_ID','STATE_EPA_FLAG','COMP_MONITOR_TYPE_CODE','ACTUAL_END_DATE','AIR_STACK_TEST_STATUS_CODE']}
MEMBERS={'facilities':'ICIS-AIR_FACILITIES.csv','evaluations':'ICIS-AIR_FCES_PCES.csv','stack_tests':'ICIS-AIR_STACK_TESTS.csv'}
URL='https://echo.epa.gov/files/echodownloads/ICIS-AIR_downloads.zip'
def sha(data): return hashlib.sha256(data).hexdigest()
def write(p,x): p.write_bytes((json.dumps(x,indent=2,ensure_ascii=False)+'\n').encode())
def main():
    p=argparse.ArgumentParser();p.add_argument('--private-dir',type=Path,required=True);a=p.parse_args()
    assert not (ROOT/'data/source_manifest.json').exists(),'A capture is already present; never overwrite it.'
    a.private_dir.mkdir(exist_ok=False)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert head=='c0595a6922ddd36248bff499c5b75eb59bbedc96'
    start=datetime.now(timezone.utc).isoformat()
    r=requests.get(URL,timeout=(20,120))
    end=datetime.now(timezone.utc).isoformat()
    receipt=dict(url=URL,start_utc=start,end_utc=end,http_status=r.status_code,bytes=len(r.content),sha256=sha(r.content),headers={k:v for k,v in r.headers.items() if k.lower() in ['content-length','content-type','etag','last-modified']},pre_retrieval_protocol=head)
    (a.private_dir/'ICIS-AIR_downloads.zip').write_bytes(r.content)
    write(a.private_dir/'request.json',receipt)
    r.raise_for_status()
    result={};manifest=dict(request=receipt,tables={})
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for table,wanted in FIELDS.items():
            choices=[n for n in z.namelist() if Path(n).name.upper()==MEMBERS[table].upper()]
            assert len(choices)==1,(table,choices)
            raw=z.read(choices[0]);reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
            assert set(wanted)<=set(reader.fieldnames),(table,reader.fieldnames)
            rows=[]
            for i,row in enumerate(reader,1):
                item={field:row[field] for field in wanted}
                for field in ['PGM_SYS_ID','ACTIVITY_ID']:
                    if field in item:
                        original=item.pop(field)
                        item[field+'_KEY']=sha(original.strip().encode()) if original.strip() else ''
                item['source_row']=i;rows.append(item)
            result[table]=rows
            manifest['tables'][table]=dict(member=choices[0],member_sha256=sha(raw),bytes=len(raw),fields=wanted,source_rows=len(rows),projection_fields=list(rows[0]) if rows else [])
    manifest['projection_packaging']='Fixed 100000-row JSON gzip shards, per table and source order; minimal selected cells only.'
    manifest['shards']=[]
    for table,rows in result.items():
        for start in range(0,len(rows),100000):
            name='data/'+table+'-'+str(start//100000+1).zfill(3)+'.json.gz'
            content=gzip.compress((json.dumps(rows[start:start+100000],ensure_ascii=False,separators=(',',':'))+'\n').encode(),mtime=0)
            (ROOT/name).write_bytes(content)
            manifest['shards'].append(dict(table=table,file=name,first_source_row=start+1,rows=min(100000,len(rows)-start),bytes=len(content),sha256=sha(content)))
    manifest.update(snapshot='Current source; historical event dates do not establish original publication vintages',rights='Minimal attributed factual fields; raw archive and identity mapping excluded; see DATA_RIGHTS.md')
    write(ROOT/'data/source_manifest.json',manifest)
    print(json.dumps(dict(state='CAPTURED_NOT_YET_VALIDATED',sha256=receipt['sha256'],tables={k:len(v) for k,v in result.items()},projection_bytes=sum(x['bytes'] for x in manifest['shards']))))
if __name__=='__main__':main()
