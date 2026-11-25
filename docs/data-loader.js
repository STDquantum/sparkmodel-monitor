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
  const index=kind=>(toc||(toc=load('toc.json').catch(error=>{toc=null;throw error}))).then(data=>load(data[kind])).then(unpack);
  async function hydrate(products){
    const paths=[...new Set(products.map(p=>p._shard).filter(Boolean))];
    const batches=await Promise.all(paths.map(load));
    const full=new Map(batches.flatMap(batch=>batch.products).map(p=>[String(p.id),p]));
    for(const product of products){const detail=full.get(String(product.id));if(detail){Object.assign(product,detail);delete product._shard}}
  }
  return {load,index,hydrate};
})();
