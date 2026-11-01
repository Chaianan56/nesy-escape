const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const base = process.env.GAME_URL || 'http://127.0.0.1:8012';
const output = path.join(root, 'tmp/browser-story-check');
fs.mkdirSync(output, {recursive:true});
const load = file => JSON.parse(fs.readFileSync(path.join(root,file),'utf8'));
(async () => {
  const browser = await chromium.launch({headless:true, channel:process.env.BROWSER_CHANNEL || 'msedge'});
  const errors = [], results = [];
  let page;
  try {
    for (const [caseId,file] of [['case_01_gideon','data/walkthrough.json'],['case_02_vincent','data/walkthrough_case_02.json'],['case_03_liora','data/walkthrough_case_03.json']]) {
      const context = await browser.newContext({viewport:{width:1440,height:1000}});
      page = await context.newPage();
      page.on('pageerror', e => errors.push(e.message));
      page.on('response', r => {if(r.status() >= 500) errors.push(`${r.status()} ${r.url()}`);});
      await context.request.get(`${base}/scene?case_id=${caseId}`);
      await page.goto(base);
      await page.locator('#storySceneDialog').waitFor({state:'visible'});
      const opening = await (await context.request.get(`${base}/scene`)).json();
      assert.equal(opening.initial_state.case_id,caseId);
      assert.equal(opening.initial_state.started_at,null);
      for(let i=0;i<opening.opening_scene.pages.length;i++) {
        assert.equal(await page.locator('#narrativeProgress').innerText(),`${i+1} / ${opening.opening_scene.pages.length}`);
        await page.locator('#narrativeNext').click();
      }
      await page.waitForFunction(() => !document.getElementById('sendBtn').disabled);
      const walk = load(file), world = load(`data/cases/${caseId}.json`);
      async function send(text) {
        await page.locator('#chatInput').fill(text);
        const reply = page.waitForResponse(r => r.url().endsWith('/command'));
        await page.locator('#chatInput').press('Enter');
        const result = await (await reply).json();
        if(result.narrative_scene) {
          await page.locator('#storySceneDialog').waitFor({state:'visible'});
          await page.locator('#narrativeClose').click();
        }
        return result;
      }
      async function choose(container, ids) {
        for(const id of ids) await page.locator(`${container} label`).filter({has:page.getByText(world.objects[id].name_th,{exact:true})}).locator('input').check();
      }
      let result;
      for(const step of walk.steps) {
        result = await send(step.join(' '));
        if(step[0] === 'infer' && !result.decision.allowed) {
          await page.locator('#inferenceChoice').selectOption(step[1]);
          await choose('#inferenceEvidence',walk.inference_evidence);
          const reply = page.waitForResponse(r => r.url().endsWith('/command'));
          await page.locator('#confirmInference').click();
          result = await (await reply).json();
        }
        if(step[0] === 'accuse' && !result.decision.allowed && walk.submitted_evidence) {
          await choose('#accusationEvidence',walk.submitted_evidence);
          const reply = page.waitForResponse(r => r.url().endsWith('/command'));
          await page.locator('#confirmAccusation').click();
          result = await (await reply).json();
        }
        assert.equal(result.decision.allowed,true,`${caseId} ${step.join(' ')}: ${result.decision.message}`);
        await page.waitForFunction(() => !document.getElementById('sendBtn').disabled || gameOver);
      }
      assert.equal(result.new_state.ending_id,'true_ending');
      assert.equal(await page.evaluate(() => {
        const title = document.querySelector('.wordmark').getBoundingClientRect();
        const controls = document.querySelector('.header-right').getBoundingClientRect();
        return title.right <= controls.left || title.bottom <= controls.top;
      }),true,'Game title must not overlap timer or player profile');
      await page.locator('#restartGame').waitFor({state:'visible'});
      await page.getByRole('button',{name:'◇ สมุดคดี'}).click();
      await page.locator('#casebookDialog .history-close').click();
      await page.locator('#tabTimeline').click();
      await page.getByText('ข้อสรุปหลังปิดคดี',{exact:true}).waitFor();
      await page.screenshot({path:path.join(output,`${caseId}-timeline.png`),fullPage:true});
      await page.reload();
      await page.locator('#restartGame').waitFor({state:'visible'});
      assert.equal((await (await context.request.get(`${base}/scene`)).json()).initial_state.ending_id,'true_ending');
      results.push({case_id:caseId,commands:walk.steps.length,ending:'true_ending'});
      await context.close();
    }
    const mobile = await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    page = await mobile.newPage();
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base);
    await page.locator('#storySceneDialog').waitFor({state:'visible'});
    assert.equal(await page.locator('#storySceneDialog').evaluate(el => el.scrollWidth <= el.clientWidth),true);
    await page.locator('#narrativeSkip').click();
    await page.locator('#narrativeNext').click();
    await page.waitForFunction(() => !document.getElementById('sendBtn').disabled);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true);
    await page.getByRole('button',{name:'◇ สมุดคดี'}).click();
    assert.equal(await page.locator('#casebookDialog').evaluate(el => el.scrollWidth <= el.clientWidth),true);
    await page.locator('#casebookDialog .history-close').click();
    for(const tab of ['#tabEvidence','#tabPeople','#tabTimeline','#tabChat']) {
      await page.locator(tab).click();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true);
    }
    await page.screenshot({path:path.join(output,'mobile-journal.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    const report = {status:'passed',cases:results,mobile_width:390,page_errors:errors};
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  } catch(error) {
    if(page && !page.isClosed()) await page.screenshot({path:path.join(output,'failure.png'),fullPage:true});
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({status:'failed',error:String(error)},null,2));
    throw error;
  } finally {await browser.close();}
})().catch(e => {console.error(e);process.exitCode=1;});
