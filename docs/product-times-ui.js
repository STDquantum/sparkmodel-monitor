const ProductTimes=(()=>{
  const editing=new URLSearchParams(location.search).get('edit')==='1';
  let data=window.PRODUCT_TIMES||{},handle=null,queue=Promise.resolve();
  const key=p=>String(p.properties?.['Product number']||p.model||'').trim();
  const get=p=>data[key(p)]||{};
  const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const rows=p=>[['发布时间','published'],['出货时间','shipped']].map(([name,field])=>`<tr data-time-field="${field}"><th>${name}</th><td>${escape(get(p)[field]||'无')}</td></tr>`).join('');
  function updateVisibleTimes(model){
    if(['published','shipped'].includes(document.querySelector('#sort').value)){
      render({preserveScroll:true});
      return;
    }
    document.querySelectorAll('#grid > article').forEach(card=>{
      const product=productById.get(card.dataset.productId);
      if(!product||(model!==undefined&&key(product)!==model))return;
      card.querySelectorAll('[data-time-field]').forEach(row=>{row.querySelector('td').textContent=get(product)[row.dataset.timeField]||'无'});
    });
  }
  const compare=(a,b,field,direction)=>{const x=get(a)[field]||'',y=get(b)[field]||'';return !x!==!y?(x?-1:1):x.localeCompare(y)*direction};
  const sort=(list,by,order)=>{const direction=order==='desc'?-1:1;return [...list].sort((a,b)=>compare(a,b,by,direction)||(by==='shipped'?compare(a,b,'published',direction):0)||key(a).localeCompare(key(b),'zh-CN'))};
  const ready=Promise.resolve();
  const serialize=value=>'window.PRODUCT_TIMES='+JSON.stringify(value,null,2)+';\n';
  function parse(source){const match=source.replace(/^\uFEFF/,'').match(/^\s*window\.PRODUCT_TIMES\s*=\s*([\s\S]*?)\s*;?\s*$/);if(!match)throw Error('请选择 product-times.js 时间数据文件');const value=JSON.parse(match[1]);if(!value||Array.isArray(value)||typeof value!=='object')throw Error('时间数据格式错误');return value}
  function status(message){document.querySelector('#time-status').textContent=message}
  async function save(model,values){
    if(location.protocol==='file:'){
      if(!handle)throw Error('请先选择 docs/product-times.js，授权自动保存');
      const next={...parse(await (await handle.getFile()).text()),[model]:values},writer=await handle.createWritable();await writer.write(serialize(next));await writer.close();data=next;
      status('已实时保存 product-times.js；刷新主网页即可查看');
    }else{
      const response=await fetch('/api/product-times',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model,...values})});
      if(!response.ok)throw Error(await response.text());data=await response.json();status('已实时保存 product-times.js');
    }
    updateVisibleTimes(model);
  }
  document.addEventListener('DOMContentLoaded',()=>{
    if(!editing)return;
    document.querySelector('h1').textContent='Model Shop · 本地时间标注';
    const bar=document.createElement('p');bar.innerHTML='<a href="index.html">返回主网页</a> · <a href="product-editor.html">添加 / 修改商品</a> · <span id="time-status">选择日期后自动保存</span>';
    document.querySelector('main').prepend(bar);
    if(location.protocol==='file:'){
      const button=document.createElement('button');button.textContent='选择时间 JS，启用自动保存';bar.append(' ',button);
      button.onclick=async()=>{try{if(!window.showOpenFilePicker)throw Error('请使用 Chrome / Edge，或双击本地启动入口');const [selected]=await showOpenFilePicker({types:[{description:'时间 JS',accept:{'text/javascript':['.js']}}],multiple:false});const loaded=parse(await (await selected.getFile()).text());handle=selected;data=loaded;status('已连接 JS，修改日期后自动保存');updateVisibleTimes()}catch(error){status(error.message)}};
      status('先选择 docs/product-times.js；推荐使用本地启动入口');
    }
    const dialog=document.createElement('dialog');dialog.id='time-editor';dialog.style.cssText='background:#171b23;color:#fff;border:1px solid #526074;border-radius:12px;width:min(430px,90vw)';
    dialog.innerHTML='<form method="dialog"><h2 style="height:auto" id="time-model"></h2><label>发布时间<input type="date" id="published-date"></label><label>出货时间<input type="date" id="shipped-date"></label><p>格式 YYYY-MM-DD；清空表示无。修改后自动保存。</p><p id="time-result" role="status"></p><button id="time-close">关闭</button></form>';
    document.body.append(dialog);
    let model='',pendingValues={},closeRequested=false,saveFailed=false,pendingSaves=0;
    const closeEditor=()=>{closeRequested=true;if(!pendingSaves)dialog.close()};
    let pressedOutside=false;
    const outside=event=>{const rect=dialog.getBoundingClientRect();return event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom};
    dialog.addEventListener('pointerdown',event=>{pressedOutside=event.target===dialog&&outside(event)});
    dialog.addEventListener('click',event=>{if(pressedOutside&&event.target===dialog&&outside(event))closeEditor();pressedOutside=false});
    document.querySelector('#grid').addEventListener('click',event=>{
      const button=event.target.closest('[data-edit-time]');if(!button)return;
      model=button.dataset.editTime;
      closeRequested=false;saveFailed=false;
      const product=productById.get(button.closest('[data-product-id]').dataset.productId),productYear=Number(yearOf(product)||product.properties?.Year||0);
      pendingValues={published:data[model]?.published||'',shipped:data[model]?.shipped||''};
      document.querySelector('#time-model').textContent='货号 '+model;
      for(const field of ['published','shipped']){
        const defaultYear=productYear+(field==='shipped'?1:0);
        document.querySelector('#'+field+'-date').value=pendingValues[field]||(productYear>=1000&&defaultYear<=9999?`${defaultYear}-01-01`:'');
      }
      document.querySelector('#time-result').textContent=productYear?'未填写的时间已预填年份，月日暂为 01-01；仅修改过的日期会保存。':'';
      dialog.showModal();
    });
    for(const field of ['published','shipped'])document.querySelector('#'+field+'-date').addEventListener('change',()=>{
      pendingValues[field]=document.querySelector('#'+field+'-date').value;
      const current=model,values={...pendingValues};
      pendingSaves++;saveFailed=false;
      document.querySelector('#time-close').disabled=true;document.querySelector('#time-result').textContent='正在保存…';
      queue=queue.catch(()=>{}).then(()=>save(current,values)).then(()=>{document.querySelector('#time-result').textContent='已保存'}).catch(error=>{saveFailed=true;closeRequested=false;document.querySelector('#time-result').textContent='保存失败：'+error.message}).finally(()=>{pendingSaves--;document.querySelector('#time-close').disabled=pendingSaves>0;if(closeRequested&&!pendingSaves&&!saveFailed)dialog.close()});
    });
    dialog.addEventListener('cancel',event=>{if(pendingSaves){event.preventDefault();closeEditor()}});
  });
  return {get,rows,sort,ready,editButton:p=>editing?`<button type="button" data-edit-time="${escape(key(p))}" ${key(p)?'':'disabled'} style="margin-top:1rem;padding:.6rem;border-radius:.5rem;cursor:pointer">添加 / 修改时间</button>`:''};
})();
