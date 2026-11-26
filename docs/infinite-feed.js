/* Append a small DOM batch at a time, independently of data file boundaries. */
window.InfiniteFeed=class{
  constructor({container,sentinel,load,append,changed=()=>{},size=48}){
    Object.assign(this,{container,sentinel,load,append,changed,size,items:[],loaded:0,version:0,busy:null,error:false,ready:false});
    sentinel.addEventListener('click',event=>{if(event.target.closest('button'))this.more()});
    this.observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting))this.more()},{rootMargin:'500px'});
    this.observer.observe(sentinel);
  }
  async reset(items){
    this.version++;this.items=items;this.loaded=0;this.busy=null;this.error=false;this.ready=true;
    this.container.replaceChildren();return this.more();
  }
  status(){
    this.sentinel.setAttribute('aria-busy',String(!!this.busy));
    this.sentinel.innerHTML=this.busy?'正在加载…':this.error?'<button type="button">加载失败，点击重试</button>':this.loaded<this.items.length?'<button type="button">加载更多</button>':this.items.length?'已全部加载':'暂无符合条件的内容';
    this.changed(this.loaded,this.items.length);
  }
  more(){
    if(!this.ready)return Promise.resolve();
    if(this.busy)return this.busy;
    if(this.loaded>=this.items.length){this.status();return Promise.resolve()}
    const version=this.version,batch=this.items.slice(this.loaded,this.loaded+this.size);
    this.error=false;
    this.busy=Promise.resolve().then(()=>this.load(batch)).then(()=>{
      if(version!==this.version)return;
      this.append(batch);this.loaded+=batch.length;
    }).catch(()=>{if(version===this.version)this.error=true}).finally(()=>{
      if(version!==this.version)return;
      this.busy=null;this.status();
      if(!this.error&&this.loaded<this.items.length)requestAnimationFrame(()=>{
        if(version!==this.version||this.error)return;
        const rect=this.sentinel.getBoundingClientRect();
        if(rect.top<window.innerHeight+500&&rect.bottom>=0)this.more();
      });
    });
    this.status();return this.busy;
  }
  async ensure(index){
    const version=this.version;
    while(this.loaded<=index&&this.loaded<this.items.length){
      await this.more();
      if(version!==this.version||this.error)return false;
    }
    return version===this.version&&this.loaded>index;
  }
};
