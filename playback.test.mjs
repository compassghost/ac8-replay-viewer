import assert from 'node:assert/strict';
import {dedupe,positionAt,quaternionAt,headingAt,stateAt,detectSections,sectionIndex} from './playback.mjs';
{ // Scene cuts: >2 km player jump within 1 s; two jumps at one instant (player and wingman rows) count once.
  const doc={units:[{isPlayer:true,tracks:{position:[[0,0,0,0,0],[1,100,0,0,0],[5,200,0,0,0],[5.5,20000,0,0,0],[6,20100,0,0,0],[9,60000,0,0,0],[9.5,70000,0,0,0]]}}]};
  assert.deepEqual(detectSections(doc),[5.5,9.5]);
  assert.deepEqual(detectSections({units:[]}),[]);
  assert.equal(sectionIndex([5.5,9.5],5),0);assert.equal(sectionIndex([5.5,9.5],5.5),1);assert.equal(sectionIndex([5.5,9.5],20),2);
}
assert.deepEqual(dedupe([[0,1],[0,2],[1,3]]),[[0,2],[1,3]]);
assert.throws(()=>dedupe([[1,1],[0,2]]));
const path=[[0,0,0,0,0],[10,10,20,30,0],[20,100,100,100,1]];
assert.deepEqual(positionAt(path,5),[5,10,15]);
assert.deepEqual(positionAt(path,15),[10,20,30]); // Do not sweep through a teleport.
assert.deepEqual(positionAt(path,20),[100,100,100]);
assert.deepEqual(positionAt(path,-1),[0,0,0]);
assert.deepEqual(positionAt(path,30),[100,100,100]);
const q=[[0,0,0,0,1,0],[10,0,0,1,0,0]];
assert.ok(Math.abs(headingAt(q,5)-Math.PI/2)<1e-6);
assert.ok(Math.abs(Math.hypot(...quaternionAt(q,5))-1)<1e-9);
const flip=[[0,0,0,0,1,0],[10,0,0,0,-1,0]];
assert.ok(Math.abs(quaternionAt(flip,5)[3]-1)<1e-9);
assert.equal(stateAt([[2,3],[4,1]],1),null);
assert.equal(stateAt([[2,3],[4,1]],3),3);
assert.equal(stateAt([[2,3],[4,1]],4),1);
console.log('Playback checks passed: duplicate times, clamping, teleport cuts, quaternion shortest arc, state boundaries.');
