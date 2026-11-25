/* Shared mouse and touch controls for both full-size image viewers. */
window.bindGalleryGestures=function(image,{state,apply,constrain,move}){
  const pointers=new Map();
  let gesture=null,lastTap=null,lastTouch=0;
  const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
  const midpoint=(a,b)=>({x:(a.x+b.x)/2,y:(a.y+b.y)/2});
  function begin(suppressTap=false){
    const view=state(),points=[...pointers.values()];
    if(points.length>=2){
      const rect=image.getBoundingClientRect();
      gesture={pinch:true,suppressTap:true,distance:Math.max(1,distance(...points.slice(0,2))),
        midpoint:midpoint(...points.slice(0,2)),scale:view.scale,x:view.x,y:view.y,
        center:{x:rect.left+rect.width/2-view.x,y:rect.top+rect.height/2-view.y}};
      lastTap=null;
    }else if(points.length){
      gesture={start:points[0],x:view.x,y:view.y,time:Date.now(),suppressTap};
    }else gesture=null;
    view.dragging=!!gesture&&(points.length>=2||view.scale>1);apply();
  }
  function zoom(scale){
    const view=state();view.scale=Math.max(1,Math.min(8,scale));
    if(view.scale===1)view.x=view.y=0;
    constrain();apply();
  }
  image.addEventListener('pointerdown',event=>{
    if(event.pointerType==='mouse'&&event.button!==0)return;
    event.preventDefault();
    if(event.pointerType==='touch')lastTouch=Date.now();
    pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
    image.setPointerCapture(event.pointerId);begin(gesture?.suppressTap);
  });
  image.addEventListener('pointermove',event=>{
    if(!pointers.has(event.pointerId)||!gesture)return;
    pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
    const view=state(),points=[...pointers.values()];
    if(gesture.pinch&&points.length>=2){
      const mid=midpoint(...points.slice(0,2));
      view.scale=Math.max(1,Math.min(8,gesture.scale*distance(...points.slice(0,2))/gesture.distance));
      const ratio=view.scale/gesture.scale;
      view.x=mid.x-gesture.center.x-(gesture.midpoint.x-gesture.center.x-gesture.x)*ratio;
      view.y=mid.y-gesture.center.y-(gesture.midpoint.y-gesture.center.y-gesture.y)*ratio;
      if(view.scale===1)view.x=view.y=0;
    }else if(view.scale>1){
      view.x=event.clientX-gesture.start.x+gesture.x;
      view.y=event.clientY-gesture.start.y+gesture.y;
    }
    constrain();apply();
  });
  function finish(event,cancelled=false){
    if(!pointers.has(event.pointerId))return;
    const previous=gesture,view=state();
    pointers.delete(event.pointerId);
    if(image.hasPointerCapture(event.pointerId))image.releasePointerCapture(event.pointerId);
    if(!cancelled&&previous&&!previous.pinch&&!previous.suppressTap&&event.pointerType==='touch'){
      const point={x:event.clientX,y:event.clientY},dx=point.x-previous.start.x,dy=point.y-previous.start.y;
      if(view.scale===1&&Math.abs(dx)>48&&Math.abs(dx)>Math.abs(dy)){lastTap=null;move(dx<0?1:-1)}
      else if(distance(point,previous.start)<12&&Date.now()-previous.time<300){
        if(lastTap&&Date.now()-lastTap.time<320&&distance(point,lastTap)<32){lastTap=null;zoom(view.scale>1?1:2)}
        else lastTap={...point,time:Date.now()};
      }else lastTap=null;
    }else lastTap=null;
    begin(true);
  }
  image.addEventListener('pointerup',event=>finish(event));
  image.addEventListener('pointercancel',event=>finish(event,true));
  image.addEventListener('lostpointercapture',event=>finish(event,true));
  image.addEventListener('dblclick',()=>{if(Date.now()-lastTouch>600)zoom(state().scale>1?1:2)});
  image.addEventListener('wheel',event=>{event.preventDefault();zoom(state().scale*(event.deltaY<0?1.12:.89))},{passive:false});
  return {reset(){
    const ids=[...pointers.keys()];pointers.clear();gesture=lastTap=null;
    for(const id of ids)if(image.hasPointerCapture(id))image.releasePointerCapture(id);
    state().dragging=false;
  }};
};
