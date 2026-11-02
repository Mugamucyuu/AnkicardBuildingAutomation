/* Real-browser smoke check; state is isolated in output, never the user's profile. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || path.resolve('output/browser-check/node_modules/playwright'));

async function main() {
  fs.mkdirSync('output', {recursive:true});
  const directory = fs.mkdtempSync(path.resolve('output/ui-check-'));
  const serverCode = [
    'import threading, secrets, sys',
    'from http.server import ThreadingHTTPServer',
    'from vocab_app.ui_service import UIService',
    'from vocab_app.ui_server import make_handler',
    'service=UIService()',
    'server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(service,secrets.token_urlsafe(32)))',
    'thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()',
    'print("http://127.0.0.1:"+str(server.server_port),flush=True)',
    'sys.stdin.readline()',
    'server.shutdown();server.server_close();service.pool.shutdown(wait=True)'
  ].join('\n');
  const env = {...process.env, ANKICARD_DATA_DIR:directory};
  for (const key of ['DEEPSEEK_API_KEY','OPENAI_API_KEY','DEEPSEEK_SEARCH_API_KEY','ANKICONNECT_API_KEY']) delete env[key];
  const child = spawn(process.env.UI_TEST_PYTHON || 'python', ['-u','-c',serverCode], {env,windowsHide:true});
  let browser;
  let stderr = '';
  child.stderr.on('data',chunk=>stderr+=chunk);
  const exited = once(child,'exit');
  try {
    const url = await new Promise((resolve,reject)=>{
      let output='';
      const timeout=setTimeout(()=>reject(Error('UI server startup timed out: '+stderr)),20000);
      child.stdout.on('data',chunk=>{output+=chunk;const match=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timeout);resolve(match[0]);}});
      child.on('error',error=>{clearTimeout(timeout);reject(error);});
      child.on('exit',()=>{clearTimeout(timeout);reject(Error('UI server exited: '+stderr));});
    });
    browser = await chromium.launch(process.platform==='win32'?{channel:'msedge',headless:true}:{headless:true});
    const context=await browser.newContext({viewport:{width:1360,height:1000},colorScheme:'light'});
    await context.route('**/*',route=>route.request().url().startsWith(url+'/')?route.continue():route.abort());
    const page=await context.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url);
    await page.waitForFunction(()=>document.querySelector('#prompt-text').value.length>0);
    const getJSON=async route=> (await context.request.get(url+route)).json();
    const boot=await getJSON('/api/bootstrap');
    assert.equal(boot.settings.palette,'iris');
    const post=async(route,data)=>{const response=await context.request.post(url+route,{data,headers:{'X-Vocab-Token':boot.token}});assert.equal(response.status(),200);return response.json();};

    await page.locator('[data-page=settings]').click();
    for(const palette of ['ink','paper','iris','graphite']){
      await page.locator(`[data-palette-choice=${palette}]`).click();
      for(const appearance of ['light','dark']){
        await page.locator('#theme').selectOption(appearance);
        assert.equal(await page.locator('html').getAttribute('data-theme'),appearance);
        assert.equal(await page.locator('html').getAttribute('data-palette'),palette);
        await page.locator('[data-page=import]').click();
        await page.evaluate(()=>document.fonts.ready);
        await page.screenshot({path:path.join(directory,`${palette}-${appearance}.png`),fullPage:true});
        await page.locator('[data-page=settings]').click();
      }
    }
    await page.locator('#theme').selectOption('system');
    await page.emulateMedia({colorScheme:'dark'});
    await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
    await page.locator('[data-palette-choice=iris]').click();
    await page.locator('#settings-form button[type=submit]').click();
    await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('保存'));
    await page.reload();
    await page.waitForFunction(()=>document.documentElement.dataset.palette==='iris'&&document.documentElement.dataset.theme==='dark');

    await page.locator('[data-page=prompts]').click();
    await page.waitForFunction(()=>!document.querySelector('#prompt-text').readOnly);
    await page.locator('#prompt-type').selectOption('style_en');
    await page.waitForFunction(()=>document.querySelector('#prompt-name').value==='style_en.txt');
    const builtin=await page.locator('#prompt-text').inputValue();
    assert(await page.locator('#prompt-delete').isDisabled());
    await page.locator('#prompt-text').fill('First custom instructions.\n中文 / 日本語 / 한국어');
    assert.equal(await page.locator('html').getAttribute('data-prompt-dirty'),'true');
    // Cancel a category change rather than losing the editor contents.
    page.once('dialog',dialog=>dialog.dismiss());
    await page.locator('#prompt-type').selectOption('style_ja');
    assert.equal(await page.locator('#prompt-type').inputValue(),'style_en');
    await page.locator('#prompt-text').press('Control+s');
    await page.waitForFunction(()=>document.documentElement.dataset.promptDirty==='false');
    const first=await page.locator('#prompt-reader').inputValue();
    assert(first.startsWith('custom/'));
    assert.equal((await getJSON('/api/prompts/preview')).generation.includes('First custom instructions.'),false);
    await page.locator('#prompt-activate').click();
    await page.waitForFunction(()=>document.querySelector('#prompt-activate').disabled&&document.documentElement.dataset.promptDirty==='false');
    assert((await getJSON('/api/prompts/preview')).generation.includes('First custom instructions.'));

    // A real offline job must retain its first snapshot after editing and deletion.
    const job=await post('/api/jobs',{language:'en',text:'apple',provider:'offline',mode:'independent',image:'none',audio:'none'});
    await page.locator('#prompt-text').fill('Second custom instructions.');
    await page.locator('#prompt-activate').click();
    await page.waitForFunction(()=>document.documentElement.dataset.promptDirty==='false');
    const second=await page.locator('#prompt-reader').inputValue();
    assert.notEqual(first,second);
    assert((await getJSON('/api/prompts/preview')).generation.includes('Second custom instructions.'));
    const snapshot=await getJSON('/api/jobs/prompts?id='+job.id+'&index=0');
    assert.equal(snapshot.snapshot.style_en,'First custom instructions.\n中文 / 日本語 / 한국어');
    page.once('dialog',dialog=>dialog.accept());
    await page.locator('#prompt-delete').click();
    await page.waitForFunction(()=>document.querySelector('#prompt-reader').value==='builtin/style_en.txt'&&!document.querySelector('#prompt-text').readOnly);
    assert.equal(await page.locator('#prompt-text').inputValue(),builtin);
    assert((await getJSON('/api/jobs/prompts?id='+job.id+'&index=0')).snapshot.style_en.includes('First custom'));

    // Native upload, editing an imported file, saving, and creating a new supplement.
    await page.locator('#prompt-file').setInputFiles({name:'imported.md',mimeType:'text/markdown',buffer:Buffer.from('Imported instructions.\nSecond line.')});
    await page.waitForFunction(()=>document.querySelector('#prompt-name').value==='imported.md'&&!document.querySelector('#prompt-text').readOnly);
    await page.locator('#prompt-text').fill('Imported and edited.');
    await page.locator('#prompt-save').click();
    await page.waitForFunction(()=>document.documentElement.dataset.promptDirty==='false');
    await page.locator('#prompt-type').selectOption('supplement');
    await page.locator('#prompt-new').click();
    await page.locator('#prompt-text').fill('My new supplement.');
    await page.locator('#prompt-save').click();
    await page.waitForFunction(()=>document.documentElement.dataset.promptDirty==='false');
    assert.equal(await page.locator('#supplement option').count(),2);
    // Translation must not reload or discard a dirty draft.
    await page.locator('#prompt-text').fill('Unsaved bilingual draft.');
    await page.locator('[data-page=settings]').click();
    await page.locator('#locale').selectOption('en');
    await page.locator('[data-page=prompts]').click();
    assert.equal(await page.locator('#prompt-text').inputValue(),'Unsaved bilingual draft.');
    await page.locator('#prompt-save').click();
    await page.waitForFunction(()=>document.documentElement.dataset.promptDirty==='false');
    await page.screenshot({path:path.join(directory,'prompt-editor.png'),fullPage:true});
    for(const width of [1360,960,680,360]){
      await page.setViewportSize({width,height:1000});
      for(const view of ['import','prompts','settings','jobs']){
        await page.locator(`[data-page=${view}]`).click();
        await page.waitForTimeout(50);
        const layout=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
        assert(layout.scroll<=layout.client+2,`${view} overflows at ${width}: ${JSON.stringify(layout)}`);
      }
    }
    await page.setViewportSize({width:1360,height:1000});
    await page.locator('[data-page=settings]').click();
    assert((await page.locator('#version-current').textContent()).startsWith('v'));
    // The release transport is stubbed here; installer/handoff are exercised separately on Windows.
    let updateState='idle';const updateCalls=[];
    await page.route('**/api/updates**',route=>{
      const action=new URL(route.request().url()).pathname.split('/').at(-1);
      if(route.request().method()==='POST'){
        updateCalls.push(action);
        updateState={check:'available',download:'downloading',install:'install_requested',cancel:'available'}[action];
      }else if(updateState==='downloading')updateState='ready';
      return route.fulfill({json:{state:updateState,current_version:'0.2.0',latest_version:'0.3.0',can_install:true,
        release_url:'https://github.com/Mugamucyuu/AnkicardBuildingAutomation/releases/tag/v0.3.0',
        downloaded:100,total:100,error:null,checked_at:new Date().toISOString()}});
    });
    await page.locator('#update-check').click();
    await page.waitForFunction(()=>!document.querySelector('#update-install').disabled);
    await page.locator('#update-install').click();
    await page.waitForFunction(()=>document.querySelector('#update-status').textContent.includes('restart'));
    assert.deepEqual(updateCalls,['check','download','install']);
    await page.screenshot({path:path.join(directory,'version-updates.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('UI smoke passed: 8 appearances, system mode, saved preferences, prompt editing/versioning/import/deletion, snapshot isolation, dirty drafts and responsive layouts.');
    console.log('Screenshots: '+directory);
  } finally {
    if(browser) await browser.close();
    child.stdin.end('\n');
    await exited;
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
