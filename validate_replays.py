import argparse,pathlib,json,time,gc,traceback
from ac8_replay import Replay
ap=argparse.ArgumentParser();ap.add_argument('directory',type=pathlib.Path);ap.add_argument('--limit',type=int,default=0);args=ap.parse_args();root=pathlib.Path(__file__).parent;files=sorted(args.directory.glob('Replay*.sav'),key=lambda x:x.stat().st_size)
if args.limit:files=files[:args.limit]
results=[]
for path in files:
 start=time.monotonic()
 try:
  replay=Replay(path);doc=replay.export();row={'file':path.name,'bytes':path.stat().st_size,'mission':doc['mission'],'duration':doc['duration'],'units':len(doc['units']),'positionSamples':sum(len(x['tracks']['position']) for x in doc['units']),'events':len(doc['events']),'validation':doc['validation'],'seconds':round(time.monotonic()-start,2)}
  if len(results)<4 and not doc['validation']['errors']:(root/path.with_suffix('.json').name).write_text(json.dumps(doc,separators=(',',':'),allow_nan=False))
  del doc,replay
 except Exception as exc:row={'file':path.name,'error':repr(exc),'traceback':traceback.format_exc(),'seconds':round(time.monotonic()-start,2)}
 results.append(row);(root/'validation-report.json').write_text(json.dumps(results,indent=2));print(json.dumps(row),flush=True);gc.collect()
