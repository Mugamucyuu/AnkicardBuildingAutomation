"use strict";
class UpdatePanel {
  constructor({api,t,notify,beforeInstall}) {
    Object.assign(this,{api,t,notify,beforeInstall});
    this.value=null;
    this.autoInstall=false;
    this.requesting=false;
    this.timer=null;
    document.getElementById('update-check').addEventListener('click',()=>this.send('check'));
    document.getElementById('update-install').addEventListener('click',()=>this.update());
    document.getElementById('update-cancel').addEventListener('click',()=>{this.autoInstall=false;this.send('cancel');});
  }
  render(value=this.value) {
    if(!value)return;
    this.value=value;
    const node=id=>document.getElementById(id);
    node('app-version').textContent='v'+value.current_version;
    node('version-current').textContent='v'+value.current_version;
    node('version-latest').textContent=value.latest_version?'v'+value.latest_version:this.t('updateUnknown');
    node('update-status').textContent=this.t(value.error?'updateError_'+value.error:'updateState_'+value.state);
    if(value.checked_at)node('update-checked').textContent=this.t('updateChecked')+' '+new Date(value.checked_at).toLocaleString(document.documentElement.lang);
    const busy=['checking','downloading','install_requested','installing'].includes(value.state);
    node('update-check').disabled=busy||this.requesting;
    node('update-install').disabled=busy||this.requesting||!value.can_install||!['available','ready','error'].includes(value.state)||!value.latest_version;
    node('update-install').textContent=this.t(value.state==='ready'?'updateRestart':'updateNow');
    node('update-cancel').hidden=value.state!=='downloading';
    node('update-source-hint').hidden=value.can_install;
    node('update-release').href=value.release_url;
    node('update-progress').hidden=value.state!=='downloading';
    node('update-progress').max=value.total||1;
    node('update-progress').value=value.downloaded||0;
    node('update-download-size').textContent=value.state==='downloading'?`${(value.downloaded/1048576).toFixed(1)} / ${(value.total/1048576).toFixed(1)} MB`:'';
    node('update-last').textContent=value.last_result?this.t(value.last_result.ok?'updateLastSuccess':'updateLastFailure')+' · v'+value.last_result.version:'';
    clearTimeout(this.timer);
    if(busy)this.timer=setTimeout(()=>this.refresh(),1000);
    if(value.state==='ready'&&this.autoInstall&&!this.requesting){this.autoInstall=false;this.install();}
    if(value.state==='error')this.autoInstall=false;
  }
  async refresh() {
    try{this.render(await this.api('/api/updates'));}catch(error){this.timer=setTimeout(()=>this.refresh(),3000);}
  }
  async send(action) {
    if(this.requesting)return;
    this.requesting=true;
    this.render();
    try{this.value=await this.api('/api/updates/'+action,{});}
    catch(error){this.autoInstall=false;this.notify(error.message,true);}
    finally{this.requesting=false;this.render();}
  }
  async install() {
    if(!this.beforeInstall()){this.autoInstall=false;return;}
    await this.send('install');
  }
  async update() {
    if(this.value?.state==='ready')return this.install();
    this.autoInstall=true;
    await this.send('download');
  }
}
