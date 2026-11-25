const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function viewer(){
  const handlers={},captured=new Set(),view={scale:1,x:0,y:0},moves=[];
  let now=1000;
  const image={
    addEventListener:(name,callback)=>handlers[name]=callback,
    setPointerCapture:id=>captured.add(id),hasPointerCapture:id=>captured.has(id),
    releasePointerCapture:id=>captured.delete(id),
    getBoundingClientRect:()=>({left:200+view.x-100*view.scale,top:200+view.y-100*view.scale,width:200*view.scale,height:200*view.scale}),
  };
  const context=vm.createContext({window:{},Date:{now:()=>now}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../docs/gallery-gestures.js'),'utf8'),context);
  const control=context.window.bindGalleryGestures(image,{state:()=>view,apply(){},constrain(){},move:step=>moves.push(step)});
  function send(type,id,x,y,extra={}){
    now+=20;
    handlers[type]({pointerId:id,clientX:x,clientY:y,pointerType:'touch',button:0,preventDefault(){},...extra});
  }
  return {view,moves,control,send,captured};
}

test('pinch scales around its midpoint, then one finger pans without flipping',()=>{
  const v=viewer();
  v.send('pointerdown',1,100,200);v.send('pointerdown',2,200,200);
  v.send('pointermove',1,50,200);v.send('pointermove',2,250,200);
  assert.equal(v.view.scale,2);assert.equal(v.view.x,50);assert.equal(v.view.y,0);
  v.send('pointerup',2,250,200);v.send('pointermove',1,80,220);
  assert.equal(v.view.x,80);assert.equal(v.view.y,20);
  v.send('pointerup',1,80,220);
  assert.deepEqual(v.moves,[]);assert.equal(v.view.dragging,false);assert.equal(v.captured.size,0);
});

test('double tap zooms in and resets; a synthetic touch dblclick does not undo it',()=>{
  const v=viewer();
  for(let i=0;i<2;i++){v.send('pointerdown',1,150,150);v.send('pointerup',1,150,150)}
  assert.equal(v.view.scale,2);
  v.send('dblclick',1,150,150);assert.equal(v.view.scale,2);
  for(let i=0;i<2;i++){v.send('pointerdown',1,150,150);v.send('pointerup',1,150,150)}
  assert.equal(v.view.scale,1);assert.equal(v.view.x,0);assert.equal(v.view.y,0);
});

test('single finger swipes still flip; cancellation never flips or zooms',()=>{
  const v=viewer();
  v.send('pointerdown',1,200,100);v.send('pointerup',1,100,100);
  assert.deepEqual(v.moves,[1]);
  v.send('pointerdown',1,200,100);v.send('pointercancel',1,100,100);
  assert.deepEqual(v.moves,[1]);assert.equal(v.view.scale,1);
});

test('pinch clamps at 1–8x and reset releases all pointers',()=>{
  const v=viewer();
  v.send('pointerdown',1,100,100);v.send('pointerdown',2,200,100);
  v.send('pointermove',2,2000,100);assert.equal(v.view.scale,8);
  v.send('pointermove',2,101,100);assert.equal(v.view.scale,1);assert.equal(v.view.x,0);
  v.control.reset();assert.equal(v.captured.size,0);assert.equal(v.view.dragging,false);
  v.send('pointermove',2,500,100);assert.equal(v.view.scale,1);
});

test('desktop wheel zoom and mouse drag remain available',()=>{
  const v=viewer();
  v.send('wheel',1,100,100,{deltaY:-100});assert.ok(v.view.scale>1);
  v.send('pointerdown',1,100,100,{pointerType:'mouse'});
  v.send('pointermove',1,140,130,{pointerType:'mouse'});
  v.send('pointerup',1,140,130,{pointerType:'mouse'});
  assert.equal(v.view.x,40);assert.equal(v.view.y,30);assert.equal(v.view.dragging,false);
});
