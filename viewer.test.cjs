// DOM/canvas simulation only. This does not launch a browser or claim visual QA.
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert/strict');
// reference-viewer.html no longer embeds a replay, so build the same page with Replay3.json embedded for these tests.
const bare=fs.readFileSync(path.join(__dirname,'reference-viewer.html'),'utf8');
assert.ok(bare.length<1e6,'Default reference-viewer.html does not embed a replay');
assert.match(bare,/<script type="application\/json" id="sample"><\/script>/,'Embedded replay slot is empty by default');
const html=fs.readFileSync(path.join(__dirname,'viewer.template.html'),'utf8').replace('__SAMPLE_JSON__',()=>fs.readFileSync(path.join(__dirname,'Replay3.json'),'utf8').replaceAll('<','\\u003c')).replace('__PLAYBACK_CODE__',()=>fs.readFileSync(path.join(__dirname,'playback.mjs'),'utf8').replaceAll('export function','function'));
const template=fs.readFileSync(path.join(__dirname,'viewer.template.html'),'utf8');
assert.doesNotMatch(template,/[\u00c2\u00c3]|\u00e2\u20ac/,'Viewer template contains encoding corruption');
assert.ok(template.includes('3D \u00b7 METERS'));assert.ok(template.includes('speedSlider'));assert.ok(template.includes("+'\u00b0'"));
const sample=html.match(/<script type="application\/json" id="sample">([\s\S]*?)<\/script>/)[1];
const code=html.match(/<script type="module">([\s\S]*?)<\/script>/)[1];
const elements=new Map(),ctx=new Proxy({},{get(o,k){return o[k]??(()=>{});},set(o,k,v){o[k]=v;return true;}});
function elem(id){if(!elements.has(id))elements.set(id,{textContent:'',value:id==='speed'?'1':'0',files:[],children:[],style:{},setAttribute(){},replaceChildren(...kids){this.children=kids;},getBoundingClientRect(){return {width:1000,height:650,left:0,top:0};},getContext(){return ctx;}});return elements.get(id);}
elem('sample').textContent=sample;const context=vm.createContext({document:{getElementById:elem,createElement:()=>({textContent:'',style:{},replaceChildren(...k){this.children=k;}})},devicePixelRatio:1,window:{},requestAnimationFrame(){},console});
vm.runInContext(code,context,{filename:'reference-viewer-inline.js'});
const setProj=on=>{if(!!vm.runInContext('missileToggle',context)!==on){const c=elem('dp-projectiles');c.checked=on;c.onchange({target:c});}};
if(JSON.parse(sample).mission.MissionID===29){
 assert.equal(vm.runInContext('unitName(units.find(u=>u.id===21))',context),'REX');
 assert.equal(vm.runInContext('unitName(units.find(u=>u.id===804))',context),'TASHA');
 assert.equal(vm.runInContext('unitName(units.find(u=>u.id===801))',context),'NOISE');
 assert.equal(vm.runInContext('units.find(u=>u.id===801).recordedLabel',context),'Noise');
 assert.equal(vm.runInContext('units.find(u=>u.id===66).recordedLabel',context),'TU-95');
 assert.equal(vm.runInContext('units.find(u=>u.id===2487).recordedLabel',context),'TU-160');
 elem('unitSearch').value='little bee';vm.runInContext('renderSearch()',context);
 assert.ok(elem('unitResults').children.length>=1,'Little Bee search returns a unit');
 assert.match(elem('unitResults').children[0].children.map(c=>c.textContent).join(''),/LITTLE BEE · \w+ · \d+ kills?/i);
 vm.runInContext('selected=21;time=2000;updateUnitPanel()',context);assert.match(elem('unitKills').textContent,/\d+ kills? so far · \d+ in mission/);
 assert.ok(vm.runInContext('killsOf(21).length',context)>100,'Rex has inferred kills');
 assert.equal(vm.runInContext('sideName(units.find(u=>u.id===21))',context),'Player');
 elem('unitSearch').value='';vm.runInContext('time=0;lastPanelKey=""',context);
}
assert.ok(elem('mission').textContent.includes('Mission ID '+JSON.parse(sample).mission.MissionID));assert.match(elem('clock').textContent,/00:00/);
vm.runInContext("$('play').onclick();frame(1000);frame(1100);",context);assert.equal(elem('play').textContent,'\u23F8');assert.match(elem('clock').textContent,/00:00\.2/);
vm.runInContext("$('play').onclick();$('timeline').oninput({target:{value:'200'}});",context);assert.match(elem('clock').textContent,/03:20/);assert.ok(elem('events').children.length>0);
vm.runInContext("$('reset').onclick();",context);assert.equal(elem('play').textContent,'\u25B6');assert.match(elem('clock').textContent,/00:00\.0/);
context.nextDoc=JSON.parse(fs.readFileSync(path.join(__dirname,'Replay15.json')));vm.runInContext('load(nextDoc)',context);assert.match(elem('mission').textContent,/Mission ID 3/);
vm.runInContext(`
camera.yaw=0;camera.elevation=Math.PI/4;
if(!(projectVector(0,0,100)[1]<0))throw Error('Altitude must project upward');
if(!(projectVector(0,100,0)[1]>0))throw Error('Recorded positive Y must remain down');
$('topDown').onclick();
if(viewMode!=='2d'||Math.abs(projectVector(0,0,100)[1])>1e-8)throw Error('Top down must remove altitude projection');
$('viewMode').onclick();
if(viewMode!=='3d')throw Error('3D view button must select 3D');
canvas.onpointerdown({button:0,clientX:0,clientY:0,pointerId:1});
canvas.onpointermove({clientX:50,clientY:20});canvas.onpointerup();
if(camera.yaw===0)throw Error('Orbit drag did not change yaw');
const beforeZoom=camera.zoom;canvas.onwheel({preventDefault(){},deltaY:-100});
if(camera.zoom<=beforeZoom)throw Error('Zoom did not increase');
$('viewReset').onclick();
load({schema:'ac8-tactical-replay',schemaVersion:1,source:{file:'test'},mission:{MissionID:99},duration:10,events:[],units:[{id:77,iconType:'Air',iconTypeCode:1,classIndex:12,startTime:0,tracks:{position:[[0,0,0,1000,0],[10,0,100,2000,0]],quaternion:[[0,0,0,0,1,0]],state:[[0,7],[5,3]]}}]});
`,context);
vm.runInContext('selected=77;draw();',context);
assert.match(elem('selection').textContent,/Altitude [\d,]+ m/);assert.match(elem('selection').textContent,/Position -?[\d.]+, -?[\d.]+ km/);
vm.runInContext('time=2;',context);elem('fwd5').onclick();assert.equal(vm.runInContext('time',context),7);elem('fwd5').onclick();assert.equal(vm.runInContext('time',context),10);elem('back5').onclick();assert.equal(vm.runInContext('time',context),5);elem('back5').onclick();assert.equal(vm.runInContext('time',context),0);elem('sideCollapse').onclick();
vm.runInContext(`
const followUnit=(id,offset,player)=>({id,iconType:'Air',iconTypeCode:1,isPlayer:player,isWingman:!player,startTime:0,tracks:{position:[[0,100+offset,200,1000,0],[10,1100+offset,1200,2000,0]],quaternion:[[0,0,0,0,1,0]],state:[[0,3]]}});
load({schema:'ac8-tactical-replay',schemaVersion:1,source:{file:'formation-test'},mission:{MissionID:99},duration:10,events:[],units:[followUnit(1,0,true),followUnit(2,100,false)]});
$('follow').value='player';camera.zoom=2;draw();
for(const t of [0,5,10]){time=t;draw();const m=markers.find(m=>m.u.isPlayer);if(Math.abs(m.x-500)>1e-8||Math.abs(m.y-325)>1e-8)throw Error('Pilot is not centered across the timeline');}
canvas.onwheel({preventDefault(){},deltaY:-100});const centered=markers.find(m=>m.u.isPlayer);if(Math.abs(centered.x-500)>1e-8||Math.abs(centered.y-325)>1e-8)throw Error('Zoom lost pilot center');
if(Math.abs(markers[1].x-markers[0].x)<20)throw Error('Zoom does not separate nearby wingman');
selected=2;$('follow').value='selected';$('follow').onchange();if(cameraTarget().unit.id!==2)throw Error('Selected follow did not change subject');
selected=2;const wing=markers.find(m=>m.u.id===2);if(Math.abs(wing.x-500)>1e-8||Math.abs(wing.y-325)>1e-8)throw Error('Selected aircraft not centered');
load({schema:'ac8-tactical-replay',schemaVersion:1,source:{file:'target-test'},mission:{MissionID:99},duration:10,events:[],units:[followUnit(1,0,true),{id:9,iconType:'Air',iconTypeCode:1,startTime:0,tracks:{position:[[0,8000,200,1000,0],[10,9000,300,1000,0]],quaternion:[[0,0,0,0,1,0]],state:[[0,67]]}}]});selected=1;$('follow').value='target';$('follow').onchange();draw();const tgt=targetOf(unitMap.get(1),0);if(!tgt||tgt.unit.id!==9)throw Error('Target view did not find the hostile target');const tb=cameraTarget().box;if(tb.w<7000)throw Error('Target frame does not span selected unit and target');replay.events.push({t:4,type:'destroyed',unitId:9,position:[8500,250,1000]});buildKills();selected=9;$('lockTarget').onclick();if(!lock||lock.target!==9)throw Error('Lock did not capture the unit');selected=1;$('follow').value='target';time=8;draw();const held=targetOf(unitMap.get(1),8);if(!held||!held.dead||held.pos[0]!==8500)throw Error('Locked target did not hold its death point');selected=9;$('lockTarget').onclick();if(lock)throw Error('Unlock failed');selected=1;time=0;$('follow').value='player';$('follow').onchange();

$('follow').value='off';$('follow').onchange();if(cameraTarget().unit!==null)throw Error('Whole mission did not release follow');
`,context);
vm.runInContext(`
camera.yaw=0;camera.elevation=Math.PI/4;
const idq=[0,0,0,1],s2=Math.SQRT1_2,roll=[1,0,0,0],pitchUp=[0,-s2,0,s2];
const a=doritoPoints(idq),b=doritoPoints(roll),c=doritoPoints(pitchUp);
if(Math.abs(a.T[1]-b.T[1])<1)throw Error('Roll must change the projected fin position');
if(Math.abs(a.N[1]-c.N[1])<1)throw Error('Pitch must change the projected nose position');
const d=rotateByQuat(pitchUp,[1,0,0]);if(!(d[2]>0.99))throw Error('Positive pitch quaternion must raise the nose');
`,context);
context.m28=JSON.parse(fs.readFileSync(path.join(__dirname,'Replay10.json')));
vm.runInContext('load(m28)',context);assert.match(elem('mission').textContent,/Mission ID 28/);
assert.ok(vm.runInContext('units.length',context)>300&&vm.runInContext('hasAttribution',context),'Mission ID 28 loads with kill attribution');
vm.runInContext("time=300;draw();replayLabel({missionNumber:27,missionId:28,file:'Replay10.json',duration:620,killAttribution:true})",context);
assert.match(vm.runInContext("replayLabel({missionNumber:27,missionId:28,file:'Replay10.json',duration:620,killAttribution:true})",context),/^M27 · Mission ID 28/);
assert.ok(vm.runInContext("units.filter(isNonTarget).length",context)>=15,'Shutter and Naval Gun are flagged non-targets');
assert.equal(vm.runInContext("replay.events.filter(e=>{const v=unitMap.get(e.unitId);return v&&isNonTarget(v);}).length",context),0,'Non-targets have no destruction events');
assert.equal(vm.runInContext("sideName(units.find(isNonTarget))",context),'Non-target');
{const styles=[],orig=ctx.stroke;ctx.stroke=function(){styles.push(String(ctx.strokeStyle));};
 context.m29=JSON.parse(sample);vm.runInContext("load(m29);time=96;draw();",context);
 assert.ok(styles.some(s=>s.startsWith('rgba(255,64,64')),'Red kill line drawn from attacker to target');
 styles.length=0;vm.runInContext("time=1230;draw();",context);
 assert.ok(!styles.some(s=>s.startsWith('rgba(255,64,64')),'Kill lines fade out after KILL_LINE_SECONDS');ctx.stroke=orig;}
vm.runInContext("load(m29);$('follow').value='dynamic';$('follow').onchange();",context);
for(const t of [10,500,1500]){vm.runInContext(`time=${t};draw();`,context);
 const box=vm.runInContext('cameraTarget().box',context),whole=vm.runInContext('wholeBox()',context);
 assert.ok(box.w>=4000&&box.h>=4000,'Dynamic box has a minimum size');
 assert.ok(box.w<whole.w||box.h<whole.h,'Dynamic box is tighter than the whole mission at t='+t);
 const inside=vm.runInContext('combatPoints().every(p=>{const b=cameraTarget().box;return p[0]>=b.cx-b.w/2-1&&p[0]<=b.cx+b.w/2+1&&p[1]>=b.cy-b.h/2-1&&p[1]<=b.cy+b.h/2+1;})',context);
 assert.ok(inside,'All combat-relevant objects are inside the dynamic frame at t='+t);}
vm.runInContext("$('follow').value='off';$('follow').onchange();",context);
vm.runInContext("load(m29)",context);
{const cats=JSON.parse(vm.runInContext("JSON.stringify(units.reduce((c,u)=>{const k=nameplateCategory(u)||'none';c[k]=(c[k]||0)+1;return c;},{}))",context));
 assert.equal(cats.player,1);assert.ok(cats.wingmen>=1&&cats.enemyUnits>100&&cats.alliedUnits>=1&&cats.namedEnemies>=1,'Nameplate categories populated: '+JSON.stringify(cats));
 for(const id of [24,27,30])assert.equal(vm.runInContext(`nameplateCategory(units.find(u=>u.id===${id}))`,context),'namedAllies','JACKPOT '+id+' is a named ally');
 assert.equal(vm.runInContext("nameplateOn(units.find(u=>u.isPlayer))",context),true);
 assert.equal(vm.runInContext("nameplateOn(units.find(u=>nameplateCategory(u)==='enemyUnits'))",context),false,'Enemy unit plates are off by default');
 elem('np-enemyUnits').onchange({target:{checked:true}});
 assert.equal(vm.runInContext("nameplateOn(units.find(u=>nameplateCategory(u)==='enemyUnits'))",context),true,'Enemy units toggle turns plates on');
 elem('np-enemyUnits').onchange({target:{checked:false}});}
{const fills=[],origFill=ctx.fillRect;ctx.fillRect=function(){fills.push(String(ctx.fillStyle));};
 context.m29=JSON.parse(sample);vm.runInContext("load(m29);",context);
 const mid=vm.runInContext("(()=>{const m=replay.missiles.find(m=>m.t1-m.t0>10);return (m.t0+m.t1)/2;})()",context);
 vm.runInContext(`time=${mid};draw();`,context);assert.ok(fills.includes('#ffd27a'),'Projectiles are on by default');
 setProj(true);fills.length=0;vm.runInContext(`time=${mid};draw();`,context);
 assert.ok(fills.includes('#ffd27a'),'Missile head drawn when the Projectiles button is on');
 setProj(false);fills.length=0;vm.runInContext("draw();",context);assert.ok(!fills.includes('#ffd27a'),'Projectiles button turns them off again');
 ctx.fillRect=origFill;}
{vm.runInContext("load(m29);time=100;draw();",context);const li=elem('events').children[0];assert.ok(li&&li.onclick,'Kill feed entries are clickable');
 const t=vm.runInContext("replay.events.filter(e=>e.type==='destroyed'&&e.t<=time&&unitMap.has(e.unitId)).at(-1).t",context);li.onclick();
 assert.ok(Math.abs(vm.runInContext("time",context)-(t-1))<1e-9,'Clicking a feed kill loads 1 s prior');}
{vm.runInContext("load(m29);time=0;follow=undefined;draw();",context);const cv=elem('canvas'),mk=(x,y)=>({button:0,clientX:x,clientY:y,pointerId:1});
 elem('speedSlider').value='0';elem('speedSlider').oninput();if(elem('speed').value!=='1'||elem('speedLabel').textContent!=='1×')throw Error('Speed slider stop 0 must be 1x');elem('speedSlider').value='20';elem('speedSlider').oninput();if(elem('speed').value!=='40')throw Error('Speed slider max must be 40x');elem('speedSlider').value='3';elem('speedSlider').oninput();if(elem('speed').value!=='6')throw Error('Speed slider stop 3 must be 6x');elem('speedSlider').value='10';elem('speedSlider').oninput();elem('capPanelOpen').onclick();elem('capDraw').onclick();
 cv.onpointerdown(mk(200,150));cv.onpointermove(mk(420,260));cv.onpointerup();
 const f=JSON.parse(vm.runInContext("JSON.stringify(frameRect)",context));
 assert.ok(f&&f.x1>f.x0&&Math.abs((f.x1-f.x0)/(f.y1-f.y0)-2)<1e-6,'Freeform drag keeps whatever ratio was drawn (220x110 px = 2:1)');
 vm.runInContext("time=100;",context);elem('capSetStart').onclick();vm.runInContext("time=300;",context);elem('capSetEnd').onclick();
 const cmd=vm.runInContext("capCommand()",context);
 assert.match(cmd,/--from 100\.0 --to 300\.0 --speed 20 --view 3d --frame -?\d+,-?\d+,-?\d+,-?\d+ --yaw 0\.00 --elevation 45\.00/,'command carries range, frame and view');
 assert.match(cmd,/render_video\.mjs \.\\Replay3\.json/,'command names the replay');
 // moving the rectangle keeps its size
 const w0=f.x1-f.x0;cv.onpointerdown(mk(310,205));cv.onpointermove(mk(360,235));cv.onpointerup();
 const g=JSON.parse(vm.runInContext("JSON.stringify(frameRect)",context));assert.ok(Math.abs((g.x1-g.x0)-w0)<1e-6&&g.x0>f.x0,'Dragging inside moves the frame');
 // too-small drag is discarded, clear works
 elem('capClear').onclick();assert.equal(vm.runInContext("frameRect",context),null,'Clear removes the frame');
 // Draw frame must keep the current camera (here: follow selected) instead of resetting to whole mission
 elem('follow').value='selected';vm.runInContext("selected=27;time=500;draw();",context);const yawBefore=vm.runInContext("camera.yaw=0.4;camera.yaw",context);vm.runInContext("draw();",context);
 elem('capDraw').onclick();elem('capDraw').onclick();assert.equal(elem('follow').value,'selected','Draw frame keeps the follow camera');assert.equal(vm.runInContext("camera.yaw",context),yawBefore,'Draw frame keeps the camera angle');
 cv.onpointerdown(mk(300,200));cv.onpointermove(mk(450,330));cv.onpointerup();
 assert.ok(vm.runInContext("frameRect",context),'Frame can be drawn while following a unit');
 assert.match(vm.runInContext("capCommand()",context),/--camera selected --unit 27 .*--frame /,'command carries the follow camera');
 elem('follow').value='0';vm.runInContext("camera.yaw=0;",context);
 elem('capDraw').onclick();vm.runInContext("capStart=null;capEnd=null;",context);
 assert.match(vm.runInContext("capCommand()",context),/--from 0\.0 --to 2068\.0 /,'no markers = whole replay');}
{const sp=v=>{elem('speed').value=v;return vm.runInContext("capSpeedValue()",context);};
 assert.deepEqual([sp('7'),sp('1'),sp('40'),sp('99'),sp('0'),sp('abc'),sp('12.6')],[7,1,40,40,6,6,13],'Capture speed is a whole number from 1 to 40');elem('speed').value='20';}
{const cap=()=>elem('capCmd').value;vm.runInContext("capStart=null;capEnd=null;frameRect=null;",context);elem('capPanelOpen').onclick();if(elem('capPanel').hidden)elem('capPanelOpen').onclick();
 setProj(false);assert.ok(!/--missiles/.test(cap()),'command has no --missiles when off');
 setProj(true);assert.match(cap(),/--missiles/,'Projectiles button updates the capture command');
 elem('np-enemyUnits').onchange({target:{checked:true}});assert.match(cap(),/--plates [^ ]*enemyUnits/,'Nameplate toggle updates the capture command');
 elem('np-enemyUnits').onchange({target:{checked:false}});assert.ok(!/enemyUnits/.test(cap()),'Nameplate toggle off updates the capture command');
 setProj(false);elem('capPanelClose').onclick();}
{vm.runInContext("frameRect=null;frameView=null;camera.yaw=0.5;camera.elevation=0.6;camera.zoom=2;draw();",context);
 const c=vm.runInContext("capCommand()",context);
 assert.match(c,/--yaw 28\.65 --elevation 34\.38 --zoom 2\.000/,'Camera angle and zoom are captured without a frame');
 vm.runInContext("camera.yaw=0;camera.elevation=Math.PI/4;camera.zoom=1;",context);
 assert.match(vm.runInContext("capCommand()",context),/--yaw 0\.00 --elevation 45\.00(?! --zoom)/,'Default zoom is omitted');}
{const cv=elem('canvas'),mk=(x,y)=>({button:0,clientX:x,clientY:y,pointerId:1});vm.runInContext("frameRect=null;frameView=null;camera.zoom=1;draw();",context);
 const wasOn=vm.runInContext("capMode",context);if(!wasOn)elem('capDraw').onclick();
 cv.onpointerdown(mk(200,150));cv.onpointermove(mk(500,300));cv.onpointerup();
 let f=JSON.parse(vm.runInContext("JSON.stringify(frameRect)",context));assert.ok(Math.abs((f.x1-f.x0)/(f.y1-f.y0)-2)<1e-6,'Frames are freeform (300x150 px = 2:1)');
 assert.match(vm.runInContext("capInfoText()",context),/output 800×400/,'Frame renders at its own shape');
 vm.runInContext("frameRect=null;frameView=null;capMode=false;",context);assert.match(vm.runInContext("capInfoText()",context),/800×450 \(16:9\)/,'No frame: default render is 16:9');vm.runInContext("capMode=true;",context);
 elem('capDraw').onclick();vm.runInContext("frameRect=null;frameView=null;",context);}
{ // Units mounted on another unit (AEGIS guns/VLS, carrier parts) get no nameplate; only the parent does.
 context.m2=JSON.parse(fs.readFileSync(path.join(__dirname,'Replay2.json'),'utf8'));vm.runInContext("load(m2);",context);
 const r=JSON.parse(vm.runInContext("JSON.stringify((()=>{const a=units.find(u=>u.recordedLabel==='AEGIS');const kids=units.filter(u=>u.tracks.parent.some(r=>r[1]===a.id));return {parent:nameplateCategory(a),side:sideName(a),kids:kids.map(k=>[k.recordedLabel,nameplateCategory(k),isSubUnit(k)]),parentIsSub:isSubUnit(a)};})())",context));
 assert.ok(r.kids.length>=3&&r.kids.every(k=>k[2]===true&&k[1]===null),'AEGIS sub-units get no nameplate: '+JSON.stringify(r));
 assert.ok(['alliedUnits','enemyUnits','namedAllies','namedEnemies'].includes(r.parent),'AEGIS itself is labelled as a unit: '+JSON.stringify(r));
 assert.equal(vm.runInContext("replay.events.find(e=>e.type==='destroyed'&&e.unitId===18155).attacker.unitId",context),17595,'M26 cruiser kill is credited to REX (the missile whose flight ends at the kill), not the AEGIS missiles that hit earlier');
 assert.equal(vm.runInContext("units.filter(u=>u.iconType==='Air'&&isSubUnit(u)).length",context),0,'Aircraft are never treated as sub-units here');
 vm.runInContext("load(m29);",context);}
{ // Top-left panel buttons, renamed; Projectiles is a pressed-state button
 const tpl=fs.readFileSync(path.join(__dirname,'viewer.template.html'),'utf8');
 const top=tpl.match(/<div class="top-tools">([\s\S]*?)<\/div>/)[1];
 for(const [id,label] of [['selPanelOpen','Unit Info'],['unitPanelOpen','Unit Tracker'],['namePanelOpen','Display Settings']])assert.ok(top.includes('id="'+id+'"')&&top.includes('>'+label+'<'),label+' button is in the top-left group');
 const tools=tpl.match(/<div class="view-tools">([\s\S]*?)<\/div><\/div><aside>/)[1];
 assert.ok(!/selPanelOpen|unitPanelOpen|namePanelOpen/.test(tools),'Panel buttons are no longer in the camera toolbar');
 assert.ok(!/showMissiles|Projectiles/.test(tools),'Projectiles is no longer in the camera toolbar');
 const dp=tpl.match(/id="namePanel"[\s\S]*?<div class="unit-panel sel-panel"/)[0];
 assert.match(dp,/id="dp-projectiles" checked>Show projectiles/,'Projectiles is a checkbox in Display Settings, checked by default');
 setProj(true);assert.equal(elem('dp-projectiles').checked,true);setProj(false);assert.equal(elem('dp-projectiles').checked,false);}
{ // Clicking a kill in the Unit Tracker jumps 1 s before it AND centers the camera on the target
 vm.runInContext("load(m29);follow=undefined;selected=21;time=2000;lastPanelKey='';draw();",context);elem('follow').value='off';
 const li=elem('unitKillList').children[0];assert.ok(li&&li.onclick,'Unit Tracker kill rows are clickable');
 const ev=JSON.parse(vm.runInContext("JSON.stringify(killsOf(21)[0])",context));li.onclick();
 assert.ok(Math.abs(vm.runInContext("time",context)-Math.max(0,ev.t-1))<1e-9,'Jumps to 1 s before the kill');
 assert.equal(vm.runInContext("centerOn",context),ev.unitId,'Centers on the target (victim)');
 assert.equal(vm.runInContext("cameraTarget().unit.id",context),ev.unitId,'Camera follows the target');
 assert.equal(vm.runInContext("selected",context),ev.unitId,'Clicking a kill selects the victim, like clicking its marker');assert.ok(elem('unitKillList').children.length>0,'The tracker still lists the killer\'s kills (list does not vanish)');assert.equal(vm.runInContext("trackerId",context),21,'The tracker keeps browsing the killer');
 assert.match(vm.runInContext("capCommand()",context),new RegExp('--camera selected --unit '+ev.unitId+' '),'Capture command reproduces the centered camera');
 elem('follow').onchange();assert.equal(vm.runInContext("centerOn",context),null,'Changing the camera mode releases the lock');
 li.onclick();assert.equal(vm.runInContext("centerOn",context),ev.unitId);elem('viewReset').onclick();assert.equal(vm.runInContext("centerOn",context),null,'Reset view releases the lock');}
{ // The Unit Tracker also shows who destroyed the selected unit
 vm.runInContext("load(m29);follow=undefined;",context);elem('follow').value='off';const fate=()=>elem('unitFate').children.map(c=>c.textContent).join('');
 const ev=JSON.parse(vm.runInContext("JSON.stringify(replay.events.find(e=>e.type==='destroyed'&&e.attacker&&e.attacker.weapon==='missile'&&unitMap.has(e.unitId)&&unitMap.has(e.attacker.unitId)))",context));
 vm.runInContext(`selected=${ev.unitId};lastPanelKey='';time=0;draw();`,context);
 const killer=vm.runInContext(`unitName(unitMap.get(${ev.attacker.unitId}))`,context);
 assert.ok(fate().startsWith('Destroyed ')&&fate().includes(' by '+killer+' (missile'),'Fate line names the killer: '+fate());
 elem('unitFate').onclick();assert.equal(vm.runInContext("centerOn",context),ev.unitId,'Clicking the fate line centers on the unit');assert.ok(Math.abs(vm.runInContext("time",context)-(ev.t-1))<1e-9);
 elem('follow').onchange();
 vm.runInContext("selected=21;lastPanelKey='';draw();",context);assert.equal(fate(),'','Survivors have no fate line: '+fate());}
{ // Unlabelled parts mounted on another unit (a tank's turret) are not separate targets: no kill markers or kill credit
 context.m1=JSON.parse(fs.readFileSync(path.join(__dirname,'Replay1.json'),'utf8'));
 const raw=context.m1.events.filter(e=>e.type==='destroyed'&&e.unitId===7454).length;assert.equal(raw,1,'fixture: the export has a destroyed event for the TANK #7451 sub-object #7454');
 vm.runInContext("load(m1);",context);
 assert.equal(vm.runInContext("isNonTarget(unitMap.get(7454))",context),true,'Unlabelled sub-object of a TANK is a part');
 assert.equal(vm.runInContext("isNonTarget(unitMap.get(7451))",context),false,'The TANK itself is still a target');
 assert.equal(vm.runInContext("replay.events.filter(e=>e.unitId===7454).length",context),0,'Parts have no destruction events in the viewer');
 vm.runInContext("load(m29);",context);}
{ // Ground vehicles draw as cubes; ships with a recorded heading as pentagons
 vm.runInContext("load(m2);",context);
 const shape=id=>vm.runInContext(`groundShape(unitMap.get(${id}))`,context);
 assert.equal(shape(17651),'ship','AEGIS is a pentagon hull');
 const apc=JSON.parse(vm.runInContext("JSON.stringify(units.filter(u=>u.recordedLabel==='APC').map(u=>groundShape(u)))",context));assert.ok(apc.length&&apc.every(s=>s==='cube'),'APCs are cubes');
 const fills=[];const o=ctx.fill;ctx.fill=function(){fills.push(String(ctx.fillStyle));};
 vm.runInContext("time=10;draw();",context);ctx.fill=o;assert.ok(fills.some(f=>/38$/.test(f)),'cube faces drawn');assert.ok(fills.some(f=>/44$/.test(f)),'pentagonal prism hulls drawn');
 vm.runInContext("load(m29);",context);}
{ // selecting an unspawned unit from the tracker fast-forwards to its spawn; a timeline tick marks the spawn time
 vm.runInContext("load(m29);time=0;",context);
 const info=JSON.parse(vm.runInContext("JSON.stringify((()=>{const u=units.find(u=>spawnTime(u)>20&&!isNonTarget(u)&&unitName(u)&&units.filter(x=>unitName(x)===unitName(u)).length===1);return {id:u.id,name:unitName(u),t:spawnTime(u)};})())",context));
 elem('unitSearch').value=info.name;vm.runInContext('renderSearch()',context);
 for(const li of elem('unitResults').children){li.onclick();if(vm.runInContext('selected',context)===info.id)break;}
 assert.equal(vm.runInContext('selected',context),info.id);
 assert.ok(Math.abs(vm.runInContext('time',context)-info.t)<1e-6,'Selecting an unspawned unit jumps to its spawn time');
 assert.equal(elem('spawnTick').style.display,'block','Spawn tick shown on the timeline');
 vm.runInContext("time=info_t+5;",Object.assign(context,{info_t:info.t}));vm.runInContext("selected=units[0].id;",context);
 elem('unitSearch').value='';vm.runInContext("time=0;load(m29);",context);}
{ // Track component kills: AA guns / SAMs / parts are credited only when the option is on; vehicles always are
 vm.runInContext(`
 const mk=(id,type,code,label,x,extra={})=>Object.assign({id,iconType:type,iconTypeCode:code,recordedLabel:label,isPlayer:id===1,isWingman:false,startTime:0,tracks:{position:[[0,x,200,1000,0],[10,x+50,250,1000,0]],quaternion:[[0,0,0,0,1,0]],state:[[0,id===1?131:67]]}},extra);
 load({schema:'ac8-tactical-replay',schemaVersion:1,source:{file:'compkill-test'},mission:{MissionID:99},duration:10,
  events:[{t:5,type:'destroyed',unitId:2,position:[1,2,3],attacker:{unitId:1,weapon:'missile',confidence:'inferred-high'}},{t:6,type:'destroyed',unitId:3,position:[4,5,6],attacker:{unitId:1,weapon:'gun',confidence:'inferred-high'}}],
  units:[mk(1,'Air',1,'F-16C',0),mk(2,'Ground',5,'TANK',500),mk(3,'Building',6,'AA GUN',900)]});`,context);
 assert.equal(vm.runInContext("killsOf(1).length",context),1,'Only the vehicle kill is credited by default');
 assert.equal(vm.runInContext("replay.events.find(e=>e.unitId===3).attacker",context),null,'AA gun destruction stays unattributed by default');
 const c=elem('dp-compkills');c.checked=true;c.onchange({target:c});
 assert.equal(vm.runInContext("killsOf(1).length",context),2,'Component kill is credited when the option is on');
 const cap=()=>String(vm.runInContext('capCommand()',context));
 assert.match(cap(),/--component-kills/,'Capture command carries --component-kills');
 c.checked=false;c.onchange({target:c});
 assert.equal(vm.runInContext("killsOf(1).length",context),1,'Turning the option off removes the component kill again');
 assert.ok(!/--component-kills/.test(cap()),'No --component-kills flag when off');
 vm.runInContext("load(m29);",context);}{ // Unit Info shows the locked unit too, with distance and relative speed, when a different unit is selected
 vm.runInContext(`
 const lu=(id,x,y,vx,vy,player)=>({id,iconType:'Air',iconTypeCode:1,recordedLabel:player?'F-16C':'F-15C',isPlayer:player,isWingman:false,startTime:0,tracks:{position:[[0,x,y,1000,0],[10,x+vx*10,y+vy*10,1000,0]],quaternion:[[0,0,0,0,1,0]],state:[[0,id===1?131:67]]}});
 load({schema:'ac8-tactical-replay',schemaVersion:1,source:{file:'lock-test'},mission:{MissionID:99},duration:10,events:[],units:[lu(1,0,0,100,0,true),lu(2,3000,4000,-100,0,false)]});
 selected=1;time=2;draw();`,context);
 elem('lockTarget').onclick();
 vm.runInContext("selected=2;time=2;draw();",context);
 const txt=elem('selection').textContent+'\n'+elem('lockedInfo').textContent;assert.match(elem('selection').textContent,/SELECTED/,'Selected block is labelled');assert.ok(!/LOCKED/.test(elem('selection').textContent),'Locked info is in its own block, below the Lock button');
 assert.match(txt,/SELECTED/,'Panel labels the selected unit');assert.match(txt,/LOCKED/,'Panel labels the locked unit');
 assert.match(txt,/Distance 4\.\d\d km|Distance [345],\d{3} m/,'Distance between selected and locked');
 assert.match(txt,/Relative speed 720 km\/h/,'Relative speed is the velocity difference (200 m/s = 720 km/h)');
 assert.equal(elem('clearRow').style.display,'','Clear lock row is offered, at the bottom');
 elem('clearLock').onclick();assert.equal(elem('lockedInfo').style.display,'none','Clearing the lock hides the locked block');assert.ok(!/LOCKED/.test(elem('selection').textContent),'Clearing the lock returns to a single unit');
 vm.runInContext("load(m29);",context);}{ // Unit Tracker clicks behave like marker clicks: they select the unit and open Unit Info (where Lock lives)
 vm.runInContext("load(m29);time=0;",context);
 const info=JSON.parse(vm.runInContext("JSON.stringify((()=>{const k=[...killMap.keys()].find(id=>unitMap.has(id)&&killMap.get(id).some(e=>unitMap.has(e.unitId)&&e.unitId!==id));const e=killMap.get(k).find(e=>unitMap.has(e.unitId));return {killer:k,victim:e.unitId,killerName:unitName(unitMap.get(k))};})())",context));
 elem('selPanelClose').onclick();assert.equal(elem('selPanel').hidden,true,'Unit Info starts closed for this check');
 elem('unitSearch').value='';vm.runInContext('renderSearch()',context);
 let clicked=false;for(const li of elem('unitResults').children){li.onclick();if(vm.runInContext('selected',context)===info.killer){clicked=true;break;}}
 assert.ok(clicked,'A tracker row selects its unit');assert.equal(elem('selPanel').hidden,false,'Picking a unit in the tracker opens Unit Info, like clicking a marker');
 vm.runInContext("selected="+info.killer+";trackerId=null;lastPanelKey='';draw();",context);
 const row=elem('unitKillList').children[0];assert.ok(row,'Killer has kill rows');row.onclick();
 assert.ok(vm.runInContext("unitMap.has(selected)&&killMap.get("+info.killer+").some(e=>e.unitId===selected)",context),'Clicking a kill row selects the victim');
 assert.equal(elem('selPanel').hidden,false,'...and shows it in Unit Info');
 assert.equal(elem('unitName').textContent.split(' · ')[0],info.killerName,'The tracker keeps showing the killer whose kills are being browsed');
 vm.runInContext("trackerId=null;load(m29);",context);}{ // Firing line: drawn from the nose only while the player's trigger is down
 vm.runInContext(`
 load({schema:'ac8-tactical-replay',schemaVersion:1,source:{file:'fire-test'},mission:{MissionID:99},duration:10,events:[],playerFire:{unitId:1,intervals:[[2,4]]},
  units:[{id:1,iconType:'Air',iconTypeCode:1,recordedLabel:'F-16C',isPlayer:true,isWingman:false,startTime:0,tracks:{position:[[0,0,0,1000,0],[10,1000,0,1000,0]],quaternion:[[0,0,0,0,1,0]],state:[[0,131]]}}]});`,context);
 assert.equal(vm.runInContext("firingAt(1)",context),false,'Trigger up before the burst');assert.equal(vm.runInContext("firingAt(3)",context),true,'Trigger down inside the burst');assert.equal(vm.runInContext("firingAt(5)",context),false,'Trigger up after the burst');
 const nose=JSON.parse(vm.runInContext("JSON.stringify(noseDirection(units[0],3))",context));assert.ok(Math.abs(nose[0]-1)<1e-9&&Math.abs(nose[1])<1e-9,'Identity orientation points the nose along +X');
 const strokes=[],origStroke=ctx.stroke;ctx.stroke=function(){strokes.push(String(ctx.strokeStyle));};
 setProj(true);vm.runInContext('time=3;draw();',context);assert.ok(strokes.includes('#ffd84a'),'Firing line drawn while firing with projectiles on');
 strokes.length=0;ctx.strokeStyle='#000';setProj(false);vm.runInContext('time=3;draw();',context);assert.ok(!strokes.includes('#ffd84a'),'Firing line is part of the projectile display: hidden when projectiles are off');
 vm.runInContext('time=5;',context);setProj(true);strokes.length=0;ctx.strokeStyle='#000';vm.runInContext('draw();',context);assert.ok(!strokes.includes('#ffd84a'),'No firing line when the trigger is up');ctx.stroke=origStroke;
 vm.runInContext("load(m29);",context);}{ // Unit Tracker: projectiles fired, with bombs counted once and their submunitions listed
 vm.runInContext(`
 const fu=(id,player)=>({id,iconType:'Air',iconTypeCode:1,recordedLabel:player?'F-16C':'F-15C',isPlayer:player,isWingman:false,startTime:0,tracks:{position:[[0,id*100,0,1000,0],[10,id*100+500,0,1000,0]],quaternion:[[0,0,0,0,1,0]],state:[[0,id===1?131:67]]}});
 load({schema:'ac8-tactical-replay',schemaVersion:1,source:{file:'fired-test'},mission:{MissionID:99},duration:10,events:[],
  playerFire:{unitId:1,intervals:[[1,3],[6,7]]},
  fire:{'2':{m:[2.5,8],b:[[4,5],[9,4]]}},
  units:[fu(1,true),fu(2,false)]});
 selected=2;lastPanelKey='';time=5;draw();`,context);
 let txt=elem('unitFired').textContent;
 assert.match(txt,/fired so far: 1 missile, 1 bomb \(5 submunitions\)/,'So-far counts follow the clock');assert.ok(!/gun/i.test(txt),'Gun rounds are not counted');
 assert.match(txt,/In mission: 2 missiles, 2 bombs \(9 submunitions\)/,'Mission totals');
 vm.runInContext("selected=1;lastPanelKey='';time=6.5;draw();",context);txt=elem('unitFired').textContent;
 assert.match(txt,/fired so far: none/,'A unit with no recorded launches shows none');
 assert.match(txt,/Trigger down: 2\.5 s so far, 3\.0 s in mission/,'The player shows trigger time');
 vm.runInContext("load(m29);",context);}{ // Unit Tracker kill list: timeline by default, swappable to cumulative counts by type or label
 vm.runInContext(`
 const ku=(id,type,code,label,player)=>({id,iconType:type,iconTypeCode:code,recordedLabel:label,isPlayer:!!player,isWingman:false,startTime:0,tracks:{position:[[0,id*200,0,1000,0],[20,id*200+500,0,1000,0]],quaternion:[[0,0,0,0,1,0]],state:[[0,player?131:67]]}});
 const ke=(t,v)=>({t,type:'destroyed',unitId:v,position:[v*200,0,1000],attacker:{unitId:1,weapon:'gun',confidence:'inferred-aim'}});
 load({schema:'ac8-tactical-replay',schemaVersion:1,source:{file:'killview-test'},mission:{MissionID:99},duration:20,
  events:[ke(2,2),ke(4,3),ke(6,4),ke(8,5),ke(10,6)],
  units:[ku(1,'Air',1,'F-16C',true),ku(2,'Air',1,'A-6E'),ku(3,'Air',1,'A-6E'),ku(4,'Air',1,'F-4E'),ku(5,'BuildingParent',9,'DESTROYER'),ku(6,'Ground',5,'TANK')]});
 selected=1;trackerId=null;lastPanelKey='';time=7;draw();`,context);
 const rowsText=()=>[...elem('unitKillList').children].map(li=>li.textContent||[...li.children].map(c=>c.textContent).join(' ')).join(' | ');
 assert.equal(elem('unitKillList').children.length,5,'Timeline is the default: one row per kill');
 const btn=v=>elem('kv-'+v);
 btn('label').onclick();assert.match(rowsText(),/A-6E.*2 \/ 2/,'By label groups A-6E');assert.match(rowsText(),/F-4E.*1 \/ 1/,'...and F-4E');assert.ok(!/DESTROYER/.test(rowsText()),'Kills after the clock (8 s and later) are not counted yet');assert.match(rowsText(),/Total.*3 \/ 5/,'Total is so far / in mission');
 btn('type').onclick();assert.match(rowsText(),/Aircraft.*3 \/ 3/,'By type groups the aircraft');
 vm.runInContext('time=11;draw();',context);assert.match(rowsText(),/Ships.*1 \/ 1/,'Ships appear once their kill is reached');assert.match(rowsText(),/Ground vehicles.*1 \/ 1/,'Ground vehicles appear too');assert.match(rowsText(),/Total.*5 \/ 5/,'Cumulative total grows with the clock');
 btn('timeline').onclick();assert.equal(elem('unitKillList').children.length,5,'Swapping back restores the timeline');
 vm.runInContext("load(m29);",context);}{ // 3D orbit in Capture: the command carries --orbit 30, and the renderer turns the camera by footage time
 vm.runInContext("load(m29);follow=undefined;",context);const cap=()=>String(vm.runInContext("capCommand()",context));
 elem('follow').value='player';elem('follow').onchange();
 assert.ok(!/--orbit/.test(cap()),'No --orbit by default');
 const c=elem('cap-orbit');c.checked=true;c.onchange({target:c});assert.match(cap(),/--orbit 30/,'The orbit checkbox adds --orbit 30');
 vm.runInContext("viewMode='2d';",context);assert.ok(!/--orbit/.test(cap()),'No orbit in the top-down view');vm.runInContext("viewMode='3d';",context);
 vm.runInContext("capStart=100;capEnd=190;",context);assert.match(elem('capInfo').textContent+vm.runInContext("capInfoText()",context),/one turn per 30 s of footage/,'The panel explains the orbit');
 c.checked=false;c.onchange({target:c});assert.ok(!/--orbit/.test(cap()),'Unchecking removes it');vm.runInContext("capStart=null;capEnd=null;",context);
 elem('canvas').toDataURL=()=>'data:image/png;base64,';
 vm.runInContext("window.replayApi.setup({view:'3d',speed:10,follow:'player',yaw:0.5,elevation:0.6,orbit:30});",context);
 const yawAt=s=>{vm.runInContext("window.replayApi.frame(100,'png',"+s+")",context);return vm.runInContext("camera.yaw",context);};
 const y0=yawAt(0);assert.ok(Math.abs(y0-0.5)<1e-9,'Footage second 0 keeps the starting yaw');
 assert.ok(Math.abs(yawAt(7.5)-(0.5+Math.PI/2))<1e-9,'A quarter turn after 7.5 s of footage');
 assert.ok(Math.abs(yawAt(30)-(0.5+2*Math.PI))<1e-9,'One full turn after 30 s of footage');
 vm.runInContext("window.replayApi.setup({view:'3d',speed:10,follow:'player',yaw:0.5,elevation:0.6});",context);vm.runInContext("window.replayApi.frame(100,'png',15)",context);assert.ok(Math.abs(vm.runInContext("camera.yaw",context)-0.5)<1e-9,'Without orbit the camera does not turn');
 vm.runInContext("captureMode=false;load(m29);",context);}{const fade=(t,play)=>vm.runInContext("replay.sections=[200];captureMode=false;playing="+play+";time="+t+";cutFade()",context);
 assert.strictEqual(fade(100,true),0,'No fade far from a cut');assert.ok(fade(200,true)>0.99,'Black at the cut while playing');assert.ok(fade(200.5,true)>0&&fade(200.5,true)<1,'Fades back in after the cut');assert.ok(fade(199.5,true)>0,'Fades out before the cut');assert.strictEqual(fade(200,false),0,'No fade when paused on a cut (section jump)');
 vm.runInContext("playing=false;replay.sections=[];",context);}
const result={status:'passed',method:'Node DOM/canvas simulation',checks:['sample loads','play/pause changes clock','scrub updates events','reset restores start','another exported recording loads','altitude and corrected Y projection','top-down toggle','orbit and zoom','target ID selection and designation changes','pilot centered throughout playback and zoom','formation separation','selected aircraft follow and whole-mission release'],note:'Browser rendering not visually verified; local-file navigation was blocked by browser policy.'};
fs.writeFileSync(path.join(__dirname,'viewer-validation.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
