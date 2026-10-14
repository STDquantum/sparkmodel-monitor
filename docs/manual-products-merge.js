(()=>{
  const data=window.MANUAL_PRODUCT_DATA||{entries:{},imageHashes:{}};
  if(!window.MODEL_CATALOG)return;
  const products=new Map(window.MODEL_CATALOG.products.map(p=>[String(p.id),p]));
  for(const [id,entry] of Object.entries(data.entries)){
    const original=products.get(id)||{id,properties:{},images:[]};
    const product={...original,...entry.fields,properties:{...original.properties,...entry.properties}};
    for(const key of entry.hiddenProperties||[])delete product.properties[key];
    const seen=new Set();product.images=[...(entry.images||[]),...(original.images||[])].filter(src=>{const hash=data.imageHashes[src]||src;if((entry.hiddenHashes||[]).includes(hash)||seen.has(hash))return false;seen.add(hash);return true});
    products.set(id,product);
  }
  window.MODEL_CATALOG={...window.MODEL_CATALOG,products:[...products.values()]};
})();
