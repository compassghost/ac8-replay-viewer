// Reference playback policy. Native interpolation is not claimed to be identical.
export function dedupe(rows) {
  const out=[];
  for (const row of rows) {
    if (out.length && row[0]<out.at(-1)[0]) throw new Error('Track timestamps decrease');
    if (out.length && row[0]===out.at(-1)[0]) out[out.length-1]=row;
    else out.push(row);
  }
  return out;
}
export function bracket(rows,t) {
  if (!rows.length) return null;
  let lo=0,hi=rows.length;
  while(lo<hi){const mid=(lo+hi)>>>1;if(rows[mid][0]<=t)lo=mid+1;else hi=mid;}
  const a=rows[Math.max(0,lo-1)],b=rows[Math.min(rows.length-1,lo)];
  return [a,b,a===b||b.at(-1)||b[0]===a[0]?0:Math.max(0,Math.min(1,(t-a[0])/(b[0]-a[0])))];
}
export function positionAt(rows,t) {
  const pair=bracket(rows,t);if(!pair)return null;
  const [a,b,u]=pair;return a.slice(1,4).map((v,i)=>v+(b[i+1]-v)*u);
}
export function quaternionAt(rows,t) {
  const pair=bracket(rows,t);if(!pair)return [0,0,0,1];
  const [a,b,u]=pair;let qa=a.slice(1,5),qb=b.slice(1,5),dot=qa.reduce((n,v,i)=>n+v*qb[i],0);
  if(dot<0){qb=qb.map(v=>-v);dot=-dot;}
  let q;
  if(dot>0.9995)q=qa.map((v,i)=>v+(qb[i]-v)*u);
  else {const theta=Math.acos(Math.max(-1,Math.min(1,dot))),s=Math.sin(theta);q=qa.map((v,i)=>(Math.sin((1-u)*theta)*v+Math.sin(u*theta)*qb[i])/s);}
  const norm=Math.hypot(...q);return norm?q.map(v=>v/norm):[0,0,0,1];
}
export function headingAt(rows,t) {
  const [x,y,z,w]=quaternionAt(rows,t);return Math.atan2(2*(x*y+w*z),1-2*(y*y+z*z));
}
export function stateAt(rows,t) {
  let lo=0,hi=rows.length;while(lo<hi){const mid=(lo+hi)>>>1;if(rows[mid][0]<=t)lo=mid+1;else hi=mid;}
  return lo?rows[lo-1][1]:null;
}
// Scene cuts: the player (and wingmen) teleport kilometres between two samples less than a second apart. Returns the sorted
// times (seconds) at which a new section starts, excluding 0. Derived, not a native field.
const SECTION_JUMP_METERS=2000,SECTION_JUMP_SECONDS=1;
export function detectSections(doc) {
  const player=doc.units.find(u=>u.isPlayer&&u.tracks.position.length);
  if(!player)return [];
  const rows=player.tracks.position,cuts=[];
  for(let i=1;i<rows.length;i++){
    const a=rows[i-1],b=rows[i];
    if(b[0]-a[0]>SECTION_JUMP_SECONDS||b[0]<=0)continue;
    if(Math.hypot(b[1]-a[1],b[2]-a[2],b[3]-a[3])>SECTION_JUMP_METERS&&(!cuts.length||b[0]-cuts.at(-1)>SECTION_JUMP_SECONDS))cuts.push(b[0]);
  }
  return cuts;
}
export function sectionIndex(sections,t) {
  let n=0;
  while(n<sections.length&&sections[n]<=t)n++;
  return n;
}
export function prepare(doc) {
  if(doc.schema!=='ac8-tactical-replay'||doc.schemaVersion!==1)throw new Error('Unsupported replay JSON schema');
  const out={...doc,units:doc.units.map(u=>({...u,tracks:Object.fromEntries(Object.entries(u.tracks).map(([k,rows])=>[k,dedupe(rows)]))}))};
  out.sections=Array.isArray(doc.sections)?doc.sections:detectSections(out);
  return out;
}
