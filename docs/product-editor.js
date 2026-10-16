const form=document.querySelector('#editor'),list=document.querySelector('#list'),status=document.querySelector('#status');
let catalog=window.MODEL_CATALOG,selectedId='',removed=new Set(),uploads=[],dirty=false;
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const model=p=>p.properties?.['Product number']||p.model||'';
const fixedProperties=new Set(['Year','Manufacturer','Scale','Product number','Availability','Properties','__proto__','constructor','prototype']);
function addProperty(key='',value=''){
  const row=document.createElement('div');row.className='extra-property';row.style.cssText='display:flex;gap:.5rem;align-items:flex-start;margin-bottom:.7rem';
  row.innerHTML=`<label style="flex:1;min-width:0;margin:0">字段名称<input class="property-key" required maxlength="200" placeholder="例如 Driver" value="${escape(key)}"></label><label style="flex:2;min-width:0;margin:0">内容<textarea class="property-value" required maxlength="10000" rows="2">${escape(value)}</textarea></label><button type="button" style="margin-top:1.8rem" aria-label="删除详情项">×</button>`;
  row.querySelector('button').onclick=()=>{row.remove();dirty=true};document.querySelector('#extra-properties').append(row);
}
document.querySelector('#add-property').onclick=()=>{addProperty();dirty=true;document.querySelector('#extra-properties').lastElementChild.querySelector('input').focus()};
function extraProperties(){const entries=[],seen=new Set();for(const row of document.querySelectorAll('.extra-property')){const key=row.querySelector('.property-key').value.trim(),value=row.querySelector('.property-value').value.trim();if(!key||!value)throw Error('请填写详情项名称和内容');if(fixedProperties.has(key))throw Error('请在上方修改固定字段：'+key);if(seen.has(key))throw Error('详情项名称不能重复：'+key);seen.add(key);entries.push([key,value])}return Object.fromEntries(entries)}
function normalized(value){if(/future|development|pre.?order/i.test(value))return 'Pre-order';if(/sold out|catalogue/i.test(value))return 'Catalogue';return 'Available'}
function options(name,values){const select=form.elements[name];select.innerHTML='<option value="">请选择</option>'+[...new Set(values)].map(v=>`<option value="${escape(v)}">${escape(v)}</option>`).join('')}
options('year',Array.from({length:201},(_,i)=>String(2100-i)));
options('scale',[...['1/5','1/8','1/12','1/18','1/24','1/32','1/43','1/64','1/87'],...catalog.products.map(p=>p.properties?.Scale).filter(Boolean)]);
function renderList(){const query=document.querySelector('#search-products').value.toLowerCase();list.innerHTML=catalog.products.filter(p=>`${p.name} ${model(p)} ${p.brand}`.toLowerCase().includes(query)).map(p=>`<button type="button" data-id="${escape(p.id)}" class="${p.id===selectedId?'active':''}">${escape(model(p))} · ${escape(p.name)}</button>`).join('')}
function current(){return catalog.products.find(p=>String(p.id)===selectedId)}
function renderImages(){document.querySelector('#images').innerHTML=[...(current()?.images||[]).filter(src=>!removed.has(src)).map(src=>({src,label:src.startsWith('manual-images/')?'手动图片':'采集图片',remove:src})),...uploads.map((file,i)=>({src:file.preview,label:'待添加',index:i}))].map(item=>`<div class="image"><img src="${escape(item.src)}" alt="商品图片"><span>${item.label}</span><button type="button" ${item.remove?`data-remove="${escape(item.remove)}"`:`data-upload="${item.index}"`}>删除图片</button></div>`).join('')}
function openProduct(id=''){
  if(dirty&&!confirm('有尚未保存的修改，是否放弃？'))return;
  uploads.forEach(file=>URL.revokeObjectURL(file.preview));uploads=[];removed.clear();selectedId=id;form.reset();dirty=false;
  const p=current();document.querySelector('#heading').textContent=p?'修改商品 · '+model(p):'添加商品';status.textContent='';
  document.querySelector('#extra-properties').replaceChildren();
  for(const [key,value] of Object.entries(p?.properties||{}))if(!fixedProperties.has(key))addProperty(key,String(value??''));
  if(p){const values={name:p.name,manufacturer:p.brand||p.properties?.Manufacturer,year:p.properties?.Year||p.name.match(/\b20\d{2}\b/)?.[0],model:model(p),scale:p.properties?.Scale,availability:normalized(p.availability),url:p.url,description:p.description};for(const [key,value] of Object.entries(values))form.elements[key].value=value||''}
  renderList();renderImages();
}
list.onclick=event=>{const button=event.target.closest('[data-id]');if(button)openProduct(button.dataset.id)};
document.querySelector('#new').onclick=()=>openProduct();document.querySelector('#search-products').oninput=renderList;
form.addEventListener('input',()=>{dirty=true});
document.querySelector('#uploads').onchange=event=>{for(const file of event.target.files){if(file.size>15*1024*1024){status.textContent='图片超过 15 MB：'+file.name;continue}uploads.push({file,preview:URL.createObjectURL(file)})}event.target.value='';dirty=true;renderImages()};
const preview=document.querySelector('#preview');
document.querySelector('#images').onclick=event=>{if(event.target.matches('img')){preview.querySelector('img').src=event.target.src;preview.showModal();return}const button=event.target.closest('button');if(!button)return;if(button.dataset.remove)removed.add(button.dataset.remove);else{const [file]=uploads.splice(Number(button.dataset.upload),1);URL.revokeObjectURL(file.preview)}dirty=true;renderImages()};
preview.onclick=event=>{if(event.target===preview)preview.close()};
const readFile=file=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve({data:reader.result.split(',')[1]});reader.onerror=()=>reject(Error('图片读取失败'));reader.readAsDataURL(file)});
form.onsubmit=async event=>{
  event.preventDefault();if(location.protocol==='file:'){status.textContent='请双击“管理商品与时间.bat”启动本地服务后，打开商品管理页保存。';return}
  document.querySelector('#save').disabled=true;status.textContent='正在保存…';
  try{const payload={...Object.fromEntries(new FormData(form)),extraProperties:extraProperties(),id:selectedId,removeImages:[...removed],uploads:await Promise.all(uploads.map(item=>readFile(item.file)))};const response=await fetch('/api/products',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!response.ok)throw Error(await response.text());const result=await response.json();catalog=result.catalog;dirty=false;const top=window.scrollY;openProduct(result.id);window.scrollTo({top,behavior:'instant'});status.textContent='已保存。刷新主网页即可查看。'}catch(error){status.textContent='保存失败：'+error.message}finally{document.querySelector('#save').disabled=false}
};
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue=''}});renderList();
