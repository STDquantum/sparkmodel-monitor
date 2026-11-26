/* JSON over HTTP; script twins keep direct file:// browsing working. */
window.SiteData=(()=>{
  const pending=new Map();
  function load(path){
    if(pending.has(path))return pending.get(path);
    const task=(location.protocol==='file:'?new Promise((resolve,reject)=>{
      const script=document.createElement('script');script.src=path.replace(/\.json$/,'.js');
      script.onload=()=>{script.remove();const data=window.DATA_SHARDS?.[path];data?resolve(data):reject(Error('Missing data: '+path))};
      script.onerror=()=>{script.remove();reject(Error('Cannot load: '+path))};document.head.append(script);
    }):fetch(path,{cache:path==='toc.json'?'no-cache':'default'}).then(response=>{
      if(!response.ok)throw Error('Cannot load: '+path);return response.json();
    })).catch(error=>{pending.delete(path);throw error});
    pending.set(path,task);return task;
  }
  let toc;
  function unpack(data){
    if(!data.packed)return data;
    function decode(value){
      if(typeof value==='number')return data.strings[value];
      if(!value||typeof value!=='object')return value;
      if('$number' in value)return value.$number;
      if('$object' in value)return Object.fromEntries(Object.entries(value.$object).map(([key,item])=>[key,decode(item)]));
      if(Array.isArray(value))return value.map(decode);
      return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,decode(item)]));
    }
    return decode(data.packed);
  }
  const index=kind=>(toc||(toc=load('toc.json').catch(error=>{toc=null;throw error}))).then(async data=>{
    const paths=Array.isArray(data[kind])?data[kind]:[data[kind]];
    const parts=(await Promise.all(paths.map(load))).map(unpack);
    if(kind==='catalog')return {generated_at:parts[0].generated_at,products:parts.flatMap(part=>part.products)};
    if(parts[0].updates)return {updates:parts[0].updates.map(run=>({...run,entries:run.entries.map((entry,index)=>({...entry,_shard:run._shard,_offset:index}))}))};
    const runs=parts[0].runs.map(run=>({...run,entries:[]}));
    for(const entry of parts.flatMap(part=>part.entries))runs[entry._run].entries.push(entry);
    return {updates:runs};
  });
  async function hydrate(products){
    const paths=[...new Set(products.map(p=>p._shard).filter(Boolean))];
    const batches=await Promise.all(paths.map(load));
    const full=new Map(batches.flatMap(batch=>batch.products).map(p=>[String(p.id),p]));
    for(const product of products){const detail=full.get(String(product.id));if(detail){Object.assign(product,detail);delete product._shard}}
  }
  async function hydrateUpdates(entries){
    const paths=[...new Set(entries.map(entry=>entry._shard).filter(Boolean))];
    const batches=new Map(await Promise.all(paths.map(async path=>[path,await load(path)])));
    for(const entry of entries){
      if(!entry._shard)continue;
      const detail=batches.get(entry._shard).entries[entry._offset];
      Object.assign(entry,detail);delete entry._shard;delete entry._offset;
    }
  }
  return {load,index,hydrate,hydrateUpdates};
})();
