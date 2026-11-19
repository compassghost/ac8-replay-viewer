"""Read-only ACE COMBAT 8 replay extraction. Standard library only."""
from __future__ import annotations
import argparse,struct,pathlib,json,math,hashlib,collections,bisect
class FormatError(ValueError):pass
class Reader:
 def __init__(self,data,at=0):self.data=data;self.at=at
 def take(self,n):
  if n<0 or self.at+n>len(self.data):raise FormatError(f'Out of bounds at {self.at} for {n} bytes')
  v=self.data[self.at:self.at+n];self.at+=n;return v
 def unpack(self,fmt):return struct.unpack(fmt,self.take(struct.calcsize(fmt)))
 def u32(self):return self.unpack('<I')[0]
 def string(self):
  n=self.unpack('<i')[0]
  if not n:return ''
  if abs(n)>1_000_000:raise FormatError(f'Invalid FString length {n} at {self.at-4}')
  raw=self.take(abs(n)*(2 if n<0 else 1));term=b'\0\0' if n<0 else b'\0'
  if not raw.endswith(term):raise FormatError(f'Unterminated FString at {self.at-len(raw)}')
  return raw[:-len(term)].decode('utf-16le' if n<0 else 'utf-8')
 def typename(self,depth=0):
  if depth>10:raise FormatError('Type nesting too deep')
  name=self.string();count=self.u32()
  if count>20:raise FormatError('Invalid type parameter count')
  return {'name':name,'params':[self.typename(depth+1) for _ in range(count)]}
 def tags(self):
  result=[]
  while True:
   start=self.at;name=self.string()
   if name=='None':break
   typ=self.typename();size=self.u32();flags=self.take(1)[0]
   if flags&~0x3b:raise FormatError(f'Unsupported property tag flags {flags:#x} in {name}')
   if flags&1:self.take(4)
   if flags&2:self.take(16)
   offset=self.at;data=self.take(size)
   result.append({'name':name,'type':typ,'flags':flags,'size':size,'offset':offset,'data':data})
   if self.at<=start:raise FormatError('Parser did not advance')
  return result
def tagged_value(t):
 data=t['data'];name=t['type']['name'];r=Reader(data)
 if name=='BoolProperty':return bool(t['flags']&16)
 fmts={'IntProperty':'<i','UInt32Property':'<I','FloatProperty':'<f','DoubleProperty':'<d','Int64Property':'<q','UInt64Property':'<Q','ByteProperty':'<B'}
 if name in fmts and len(data)==struct.calcsize(fmts[name]):return struct.unpack(fmts[name],data)[0]
 if name in ['StrProperty','NameProperty']:return r.string()
 if name=='StructProperty':
  subtype=t['type']['params'][0]['name']
  if subtype in ['DateTime','Timespan']:return struct.unpack('<q',data)[0]
  try:return {x['name']:tagged_value(x) for x in r.tags()}
  except (FormatError,UnicodeError,struct.error):return {'structType':subtype,'bytes':len(data)}
 if name=='ArrayProperty' and t['type']['params'][0]['name']=='StrProperty':return [r.string() for _ in range(r.u32())]
 if name=='ArrayProperty' and t['type']['params'][0]['name']=='StructProperty':
  try:return [{x['name']:tagged_value(x) for x in r.tags()} for _ in range(r.u32())]
  except (FormatError,UnicodeError,struct.error):return {'type':name,'bytes':len(data)}
 if name=='MapProperty' and [x['name'] for x in t['type']['params']]==['UInt32Property','UInt32Property']:
  removed=r.u32()
  if removed:raise FormatError('Unexpected removed map keys')
  return {r.u32():r.u32() for _ in range(r.u32())}
 return {'type':name,'bytes':len(data)}
def lz4_block(src,expected):
 if not 0<=expected<=1024*1024*1024:raise FormatError('Invalid decoded buffer size')
 dst=bytearray(expected);ip=op=0
 def extended(n):
  nonlocal ip
  if n==15:
   while True:
    if ip>=len(src):raise FormatError('Truncated LZ4 length')
    x=src[ip];ip+=1;n+=x
    if x!=255:break
  return n
 while ip<len(src):
  token=src[ip];ip+=1;lit=extended(token>>4)
  if ip+lit>len(src) or op+lit>expected:raise FormatError('LZ4 literal overflow')
  dst[op:op+lit]=src[ip:ip+lit];ip+=lit;op+=lit
  if ip==len(src):break
  if ip+2>len(src):raise FormatError('Truncated LZ4 match')
  back=struct.unpack_from('<H',src,ip)[0];ip+=2
  if not 0<back<=op:raise FormatError('LZ4 invalid back reference')
  count=extended(token&15)+4
  if op+count>expected:raise FormatError('LZ4 match overflow')
  # Copy repeating patterns in larger chunks while preserving overlapping semantics.
  while count:
   n=min(count,back);dst[op:op+n]=dst[op-back:op-back+n];op+=n;count-=n
 if op!=expected:raise FormatError(f'LZ4 decoded {op}, expected {expected}')
 return bytes(dst)
def find_tags(data,first):
 needle=struct.pack('<i',len(first)+1)+first.encode()+b'\0';at=data.find(needle)
 if at<0:raise FormatError('Missing tagged section '+first)
 return Reader(data,at).tags()
class Replay:
 def __init__(self,path):
  self.path=pathlib.Path(path);raw=self.path.read_bytes()
  if raw[:4]!=b'GVAS':raise FormatError('Not a GVAS save')
  self.sha256=hashlib.sha256(raw).hexdigest();tags=find_tags(raw,'ReplayFileHeader');self.outer={t['name']:tagged_value(t) for t in tags if t['name']!='Buffer'}
  if self.outer.get('SavedVersion')!=32:raise FormatError(f'Unsupported SavedVersion {self.outer.get("SavedVersion")}; verified layout is version 32')
  fields={x['name']:x for x in tags};r=Reader(fields['Buffer']['data']);n=r.u32();compressed=r.take(n)
  if r.at!=len(r.data):raise FormatError('Byte array size mismatch')
  self.buffer=lz4_block(compressed,self.outer['UncompressedBufferSize']) if self.outer.get('bBufferCompressed') else compressed
  self.front=self.outer['BufferFrontSize'];self.back=self.outer['BufferBackSize']
  if self.front<16 or self.front+self.back>len(self.buffer):raise FormatError('Invalid front/back lengths')
  self.back_virtual=struct.unpack_from('<I',self.buffer,4)[0]
  self.records={};self.counts=collections.Counter()
  for start,end,region in [(16,self.front,'front'),(self.front,self.front+self.back,'back')]:
   at=start
   while at<end:
    units,payload,t=struct.unpack_from('<HBB',self.buffer,at);size=units*8
    if size<8 or at+size>end or payload*4>size:raise FormatError(f'Invalid record at {at}: {size}/{payload}/{t}')
    virtual=at if region=='front' else self.back_virtual+at-self.front
    self.records[virtual]={'offset':at,'virtual':virtual,'size':size,'payload':payload*4,'type':t,'region':region};self.counts[t]+=1;at+=size
   if at!=end:raise FormatError('Record region does not end exactly')
  extra=self.buffer[self.front+self.back:]
  self.system_tags=find_tags(extra,'NamedHashToIDMap');self.system={t['name']:tagged_value(t) for t in self.system_tags if t['name'] in ['NamedHashToIDMap','StringList']}
 def record(self,virtual):
  if virtual not in self.records:raise FormatError(f'Dangling record pointer {virtual:#x}')
  return self.records[virtual]
 def unpack(self,fmt,rec,relative=0):
  if relative+struct.calcsize(fmt)>rec['size']:raise FormatError('Record field overflow')
  return struct.unpack_from(fmt,self.buffer,rec['offset']+relative)
 def track(self,start):
  seen=set();result=[]
  while start!=-1:
   if start in seen:raise FormatError('Cyclic track')
   seen.add(start);rec=self.record(start);result.append(rec);start=self.unpack('<i',rec,4)[0]
  return result
 def objects(self):
  result=[];seen=set();root=self.record(struct.unpack_from('<I',self.buffer,8)[0])
  if root['type']!=2 or root['payload']+8192>root['size']:raise FormatError('Invalid root object table')
  active=[]
  for ptr in self.unpack('<2048i',root,root['payload']):
   while ptr!=-1:
    if ptr in seen:raise FormatError('Cyclic or duplicate object hash chain')
    seen.add(ptr);rec=self.record(ptr)
    if rec['type']!=3:raise FormatError('Non-object record in object hash table')
    active.append(rec);ptr=self.unpack('<i',rec,4)[0]
  for rec in active:
   if rec['size']!=80:raise FormatError('Unsupported object record layout')
   ident=self.unpack('<i',rec,12)[0];channels=self.unpack('<8i',rec,16);cls,flags,typ,sub,unk1,unk2=self.unpack('<HH4B',rec,48)
   result.append({'id':ident,'classIndex':None if cls==65535 else cls,'flags':flags,'iconTypeCode':typ,'categoryCode':sub,'extraCodes':[unk1,unk2],'iconOffset':list(self.unpack('<3d',rec,56)),'channels':list(channels),'recordOffset':rec['virtual']})
  if len({x['id'] for x in result})!=len(result):raise FormatError('Duplicate object IDs')
  return sorted(result,key=lambda x:x['id'])
 def summary(self):
  return {'file':self.path.name,'sha256':self.sha256,'outer':self.outer,'frontBytes':self.front,'backBytes':self.back,'recordCount':len(self.records),'recordTypes':dict(sorted(self.counts.items())),'objectCount':len(self.objects()),'debriefingObjectCount':sum(bool(x['flags']&0x21) for x in self.objects()),'strings':self.system.get('StringList',[]),'systemProperties':[{'name':t['name'],'type':t['type'],'size':t['size']} for t in self.system_tags]}
 def validate(self):
  errors=[];links=0;timestamps=0;packets=0;quaternions=[]
  for obj in self.objects():
   for ch,ptr in enumerate(obj['channels']):
    if ptr<0:continue
    last=-math.inf
    for rec in self.track(ptr):
     packets+=1;time=self.unpack('<f',rec,12)[0]
     if not math.isfinite(time) or time<0 or time+0.001<last:errors.append(f'Non-monotonic time in object {obj["id"]} channel {ch}')
     last=time;timestamps+=1
     prev=self.unpack('<i',rec,8)[0]
     if prev!=-1:
      pr=self.record(prev)
      if self.unpack('<i',pr,4)[0]!=rec['virtual']:errors.append('Non-reciprocal track link')
      links+=1
     if ch in [1,3]:
      vals=self.unpack('<3d',rec,rec['payload'])
      if not all(math.isfinite(v) and abs(v)<1e12 for v in vals):errors.append('Non-finite/out-of-range coordinates')
     elif ch in [2,4]:
      q=self.unpack('<4f',rec,rec['payload']);norm=sum(v*v for v in q)
      if not math.isfinite(norm) or abs(norm-1)>0.02:errors.append(f'Invalid quaternion norm {norm}')
      quaternions.append(norm)
  return {'records':len(self.records),'objects':len(self.objects()),'channelPackets':packets,'reciprocalLinksChecked':links,'timestampsChecked':timestamps,'quaternionsChecked':len(quaternions),'errors':list(dict.fromkeys(errors))}
 def export(self,include_all=False):
  enumfile=pathlib.Path(__file__).with_name('enums.json');enumdata=json.loads(enumfile.read_text()) if enumfile.exists() else {};types={v:k for k,v in enumdata.get('ELiveBriefingDebriefingIconType',{}).items()}
  units=[];events=[];warnings=[]
  def rows(obj,ch,fmt,expected,scale=1):
   start=obj['channels'][ch]
   if start<0:return []
   result=[]
   for r in self.track(start):
    if r['type'] not in expected:raise FormatError(f'Unexpected type {r["type"]} in channel {ch}')
    time=self.unpack('<f',r,12)[0];vals=self.unpack(fmt,r,r['payload']);step=r['type'] not in [234,238,242,246]
    result.append([time,*[v*scale for v in vals],int(step)])
   return result
  for obj in self.objects():
   if not include_all and not obj['flags']&0x21:continue
   pos=rows(obj,1,'<3d',[234,235,236,237],0.01);rot=rows(obj,2,'<4f',[238,239,240,241]);relative=rows(obj,3,'<3d',[242,243,244,245],0.01);relativeq=rows(obj,4,'<4f',[246,247,248,249])
   parents=[]
   if obj['channels'][0]>=0:
    for r in self.track(obj['channels'][0]):
     if r['type'] not in [232,233]:raise FormatError('Unknown parent packet')
     values=self.unpack('<iHH',r,r['payload']);parents.append([self.unpack('<f',r,12)[0],*values])
   states=[]
   if obj['channels'][7]>=0:
    for r in self.track(obj['channels'][7]):
     if r['type'] not in [252,253]:raise FormatError('Unknown state packet')
     mask=self.unpack('<I',r,r['payload'])[0];states.append([self.unpack('<f',r,12)[0],mask])
   for old,new in zip(states,states[1:]):
    if old[1]&2 and not new[1]&2:events.append({'t':new[0],'type':'destroyed','unitId':obj['id'],'source':'state-alive-bit-fell','confidence':'correlated'})
    if old[1]&1 and not new[1]&1:events.append({'t':new[0],'type':'removed','unitId':obj['id'],'source':'state-exists-bit-fell','confidence':'correlated'})
   unit={k:v for k,v in obj.items() if k not in ['channels','recordOffset']};unit['iconType']=types.get(obj['iconTypeCode'],'UnknownCode');unit['isPlayer']=bool(obj['flags']&4);unit['isWingman']=obj['categoryCode']==24
   strings=self.system.get('StringList',[]);index=obj['classIndex'];unit['labelStringIndex']=index;unit['recordedLabel']=strings[index] if index is not None and 0<=index<len(strings) else None
   unit['tracks']={'position':pos,'quaternion':rot,'parent':parents,'relativePosition':relative,'relativeQuaternion':relativeq,'state':states};unit['startTime']=min([x[0] for x in pos] or [0]);units.append(unit)
  ids={o['id'] for o in units};death_locations=[];health_events=[];raw_events=[]
  for rec in self.records.values():
   if rec['type']>=232 or rec['type'] in [2,3,4,5,149] or rec['payload']<20:continue
   ident=self.unpack('<i',rec,16)[0]
   if ident not in ids:continue
   t=self.unpack('<f',rec,12)[0];payload=self.buffer[rec['offset']+rec['payload']:rec['offset']+rec['size']]
   raw_events.append({'t':t,'unitId':ident,'recordType':rec['type'],'payloadHex':payload.hex()})
   if rec['type']==29 and len(payload)>=24:death_locations.append({'t':t,'unitId':ident,'position':[v*0.01 for v in struct.unpack_from('<3d',payload)],'recordType':29})
   if rec['type']==24 and len(payload)>=4:health_events.append({'t':t,'unitId':ident,'value':struct.unpack_from('<f',payload)[0],'recordType':24,'confidence':'correlated'})
  for event in events:
   if event['type']=='destroyed':
    candidates=[x for x in death_locations if x['unitId']==event['unitId'] and abs(x['t']-event['t'])<0.25]
    if candidates:
     found=min(candidates,key=lambda x:abs(x['t']-event['t']));event['position']=found['position'];event['recordTime']=found['t']
  header=self.outer['ReplayFileHeader'];duration=header.get('TotalReplayTime') if isinstance(header,dict) else None
  if duration is None:duration=max([x[0] for u in units for x in u['tracks']['position']] or [0])
  warnings.extend(['State bit names and destruction events are correlated with recorded events; exact native semantics remain under investigation.','Positions use recorded Unreal axes with centimeters converted to meters. Terrain/geographic alignment is not supplied.','Parent attachments, checkpoints/retries, scripted hiding, label changes and native interpolation require additional interpretation; raw tracks and events are preserved.'])
  return {'schema':'ac8-tactical-replay','schemaVersion':1,'source':{'file':self.path.name,'sha256':self.sha256,'savedVersion':self.outer['SavedVersion']},'mission':{k:header.get(k) for k in ['MissionID','LevelId','MapPath','GameDifficulty']} if isinstance(header,dict) else {},'duration':duration,'coordinates':{'units':'meters','axes':'Unreal X/Y horizontal, Z up','quaternionOrder':'x,y,z,w','positionRow':['seconds','x','y','z','stepIntoSample'],'quaternionRow':['seconds','x','y','z','w','stepIntoSample'],'stateRow':['seconds','rawBitMask'],'parentRow':['seconds','parentId','socketStringIndex','unknown16']},'units':units,'events':sorted(events,key=lambda x:x['t']),'healthEvents':health_events,'rawUnitEvents':raw_events,'validation':self.validate(),'warnings':warnings}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('save',type=pathlib.Path);ap.add_argument('--inspect',type=pathlib.Path);ap.add_argument('--export',type=pathlib.Path);ap.add_argument('--all-objects',action='store_true');args=ap.parse_args();r=Replay(args.save)
 if args.export:
  doc=r.export(args.all_objects)
  if doc['validation']['errors']:raise FormatError('Validation failed: '+str(doc['validation']['errors']))
  args.export.write_text(json.dumps(doc,separators=(',',':'),allow_nan=False),encoding='utf-8');print(json.dumps({'file':r.path.name,'export':str(args.export),'units':len(doc['units']),'duration':doc['duration'],'events':len(doc['events']),'validation':doc['validation']}))
 elif args.inspect:args.inspect.write_text(json.dumps(r.summary(),indent=2),encoding='utf-8')
 else:print(json.dumps(r.summary(),indent=2))
if __name__=='__main__':main()
