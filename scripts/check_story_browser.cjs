/* Local browser regression: requires Playwright and a running game server.
   NODE_PATH may point at an existing Playwright installation. No model calls:
   all commands below use exact local-parser forms. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const story = JSON.parse(fs.readFileSync(path.join(root, 'data/story.json'), 'utf8'));
const walk = JSON.parse(fs.readFileSync(path.join(root, 'data/walkthrough.json'), 'utf8'));
const base = process.env.GAME_URL || 'http://127.0.0.1:8012';
const output = path.join(root, 'tmp/browser-story-check');
fs.mkdirSync(output, {recursive:true});
fs.writeFileSync(path.join(output,'result.json'), JSON.stringify({status:'running'}));

(async () => {
  const browser = await chromium.launch({headless:true, ...(process.env.BROWSER_CHANNEL ? {channel:process.env.BROWSER_CHANNEL} : {})});
  const errors = [];
  const context = await browser.newContext({viewport:{width:1440,height:1000}});
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  let commands = 0;
  try {
    await page.goto(base);
    await page.locator('#storySceneDialog').waitFor({state:'visible'});
    const opening = await (await context.request.get(`${base}/scene`)).json();
    assert.equal(opening.initial_state.started_at, null);
    assert.equal(opening.opening_scene.pages.length, 5);
    assert.equal(opening.opening_scene.id, 'boarding');
    await page.screenshot({path:path.join(output, '01-intro.png'), fullPage:true});
    // Reading or stepping back through the opening must not consume case time.
    for (let index = 0; index < 5; index++) {
      assert.equal(await page.locator('#narrativeProgress').innerText(), `${index + 1} / 5`);
      assert.equal((await (await context.request.get(`${base}/scene`)).json()).initial_state.started_at, null);
      await page.locator('#narrativeNext').click();
    }
    await page.waitForFunction(() => !document.getElementById('sendBtn').disabled);
    assert.equal((await (await context.request.get(`${base}/scene`)).json()).opening_scene, null);
    assert.equal((await (await context.request.get(`${base}/reconstruction`)).json()).scene, null);
    async function readScene(expectedPages, screenshot) {
      await page.locator('#storySceneDialog').waitFor({state:'visible'});
      assert.equal(await page.locator('#narrativeProgress').innerText(), `1 / ${expectedPages}`);
      await page.locator('#narrativeNext').click();
      await page.locator('#narrativePrevious').click();
      assert.equal(await page.locator('#narrativeProgress').innerText(), `1 / ${expectedPages}`);
      if (screenshot) await page.screenshot({path:path.join(output, screenshot), fullPage:true});
      for (let index = 0; index < expectedPages; index++) {
        assert.equal(await page.locator('#narrativeProgress').innerText(), `${index + 1} / ${expectedPages}`);
        await page.locator('#narrativeNext').click();
      }
      await page.locator('#storySceneDialog').waitFor({state:'hidden'});
    }
    async function send(text, allowed=true, expectedScene=null) {
      await page.locator('#chatInput').fill(text);
      const response = page.waitForResponse(res => res.url().endsWith('/command') && res.request().postDataJSON()?.text === text);
      await page.locator('#chatInput').press('Enter');
      const data = await (await response).json();
      commands++;
      assert.equal(data.decision.allowed, allowed, `${text}: ${data.decision.message}`);
      assert.equal(data.narrative_scene?.id || null, expectedScene);
      // submit() awaits reading the scene. Close it before waiting for input.
      if (expectedScene) {
        assert.equal(data.narrative_scene.pages.length, 4);
        await readScene(4, '03-confrontation.png');
      }
      await page.waitForFunction(() => !document.getElementById('sendBtn').disabled || gameOver);
      return data;
    }
    async function chooseEvidence(container, ids) {
      for (const id of ids) {
        const label = page.locator(`${container} label`).filter({has:page.getByText(story.objects[id].name_th,{exact:true})});
        await label.locator('input').check();
      }
    }
    // Real locks: inspecting hidden content fails; a spoken node earns its key.
    await send('ไปตู้ 4');
    await send('examine secret_file', false);
    await send('interrogate dr_liora_venn father', false);
    await send('สอบปากคำลิโอรา');
    await page.getByRole('button',{name:'◇ สมุดคดี'}).click();
    assert.match(await page.locator('.inventory-note').innerText(), /กุญแจห้องแพทย์/);
    await page.locator('#peopleTab').click();
    await page.getByRole('button',{name:'การตรวจศพและกุญแจห้องแพทย์',exact:true}).click();
    assert.equal(await page.locator('#casebookDialog').evaluate(el => el.open), false);
    assert.match(await page.locator('#chatInput').inputValue(), /เรื่องการตรวจศพ/);
    await send('ใช้กุญแจห้องแพทย์กับประตูห้องแพทย์');
    await send('examine secret_file');
    await send('ถามดร. ลิโอรา เวนน์ (Dr. Liora Venn) เรื่องคำให้การของเอเลียส');
    await send('examine letter_opener');
    await send('move lounge_car');
    for (const step of walk.steps) {
      if (['infer','accuse'].includes(step[0])) break;
      await send(step.join(' '));
    }
    // Possessing every raw clue does not bypass the player's explicit inference.
    await send('interrogate gideon_hart confrontation', false);
    const unearned = await (await context.request.post(`${base}/journal`)).json();
    assert.deepEqual(unearned.scene_followups, []);
    // A typed inference opens the same chooser, without recording an attempt
    // or preselecting the proposed answer before the player attaches evidence.
    await send('infer claim_two_times', false);
    await page.locator('#inferenceChoice').waitFor({state:'visible'});
    assert.equal(await page.locator('#inferenceChoice').inputValue(), '');
    await page.locator('#cancelInference').click();
    await page.getByRole('button',{name:'◇ สมุดคดี'}).click();
    await page.locator('#questionsTab').click();
    await page.getByRole('button',{name:'เสนอข้อสรุปและแนบหลักฐาน',exact:true}).click();
    assert.equal(await page.locator('#inferenceChoice').inputValue(), '');
    assert.equal(await page.locator('#confirmInference').isDisabled(), true);
    await chooseEvidence('#inferenceEvidence', [...walk.inference_evidence,'letter_opener']);
    await page.locator('#inferenceChoice').selectOption('claim_blackout_murder');
    let inferenceReply = page.waitForResponse(res => res.url().endsWith('/command'));
    await page.locator('#confirmInference').click();
    let inference = await (await inferenceReply).json();
    commands++;
    assert.equal(inference.decision.allowed, false);
    assert.equal(inference.new_state.failed_accusations, 0);
    await page.locator('#inferenceStatus').getByText(/เวลาพบศพ/).waitFor();
    await page.locator('#inferenceChoice').selectOption('claim_two_times');
    await page.screenshot({path:path.join(output, '02-inference.png'), fullPage:true});
    inferenceReply = page.waitForResponse(res => res.url().endsWith('/command'));
    await page.locator('#confirmInference').click();
    inference = await (await inferenceReply).json();
    commands++;
    assert.equal(inference.decision.allowed, true);
    assert.deepEqual(inference.new_state.validated_claims, ['claim_two_times']);
    await page.locator('#confirmInference').waitFor({state:'hidden'});
    await page.locator('#casebookDialog .history-close').click();
    // The optional confrontation is discoverable through the earned journal cue.
    await page.getByRole('button',{name:'◇ สมุดคดี'}).click();
    await page.locator('#questionsTab').click();
    await page.getByRole('button',{name:'ถามต่อ: ทักท้วงพยานเรื่องสองเวลา',exact:true}).click();
    const confrontationCommand = await page.locator('#chatInput').inputValue();
    assert.match(confrontationCommand, /เรื่องทักท้วงพยานเรื่องสองเวลา/);
    const beforeConfrontation = (await (await context.request.get(`${base}/scene`)).json()).initial_state;
    const confrontation = await send(confrontationCommand, true, 'gideon_confrontation');
    assert.deepEqual(confrontation.new_state.discovered_evidence, beforeConfrontation.discovered_evidence);
    assert.deepEqual(confrontation.new_state.validated_claims, beforeConfrontation.validated_claims);
    assert.equal(confrontation.new_state.ending_id, null);
    assert.ok(confrontation.new_state.dialogue_history.includes('gideon_hart:confrontation'));
    // Reload must retain the earned claim and show only actual suspects.
    await page.reload();
    await page.waitForFunction(() => !document.getElementById('sendBtn').disabled);
    assert.deepEqual((await (await context.request.post(`${base}/journal`)).json()).scene_followups, []);
    await send('กล่าวหากิเดียน', false);
    await page.locator('#accusationEvidence label').first().waitFor();
    assert.match(await page.locator('#accusationLimits').innerText(), /20/);
    await chooseEvidence('#accusationEvidence', walk.submitted_evidence);
    const endingReply = page.waitForResponse(res => res.url().endsWith('/command'));
    await page.locator('#confirmAccusation').click();
    const ending = await (await endingReply).json();
    commands++;
    assert.equal(ending.new_state.ending_id, 'true_ending');
    await page.locator('#restartGame').waitFor({state:'visible'});
    await page.locator('#confirmAccusation').waitFor({state:'hidden'});
    await page.screenshot({path:path.join(output, '04-ending.png'), fullPage:true});
    // The reconstruction is opt-in and reflects the submitted button/wax route.
    assert.equal(await page.locator('#storySceneDialog[open]').count(), 0);
    const reconstruction = (await (await context.request.get(`${base}/reconstruction`)).json()).scene;
    assert.equal(reconstruction.id, 'case_reconstruction');
    assert.deepEqual(reconstruction.pages.map(item => item.id), [
      'earlier_violence','why_this_file','contact_button_wax','the_wait','the_true_memory','a_case_to_handover',
    ]);
    for (const scenePage of reconstruction.pages) {
      for (const evidence of scenePage.evidence) {
        assert.ok(walk.submitted_evidence.includes(evidence.id), `Recap leaked ${evidence.id}`);
      }
    }
    await page.locator('#reconstructCase').click();
    await readScene(6, '05-reconstruction.png');
    await page.locator('#reconstructCase').click();
    await page.locator('#storySceneDialog').waitFor({state:'visible'});
    await page.locator('#narrativeClose').click();
    const exported = await (await context.request.get(`${base}/study-export`)).json();
    assert.deepEqual(exported.inference_attempts.map(item => item.accepted), [false,true]);
    assert.equal(exported.submitted_evidence.length, 19);
    // Responsive layout and a fresh session remain independent of this ending.
    const mobile = await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    const mobilePage = await mobile.newPage();
    mobilePage.on('pageerror', error => errors.push(error.message));
    await mobilePage.goto(base);
    await mobilePage.locator('#storySceneDialog').waitFor({state:'visible'});
    assert.equal(await mobilePage.locator('#narrativeText').evaluate(el => getComputedStyle(el).fontSize), '18px');
    assert.equal(await mobilePage.locator('#storySceneDialog').evaluate(el => el.scrollWidth <= el.clientWidth), true);
    await mobilePage.screenshot({path:path.join(output, '06-mobile-opening.png'),fullPage:true});
    await mobilePage.locator('#storySceneDialog').evaluate(el => { el.scrollTop = el.scrollHeight; });
    const mobileReading = await mobilePage.evaluate(() => ({
      textBottom: document.getElementById('narrativeText').getBoundingClientRect().bottom,
      controlsTop: document.querySelector('.narrative-footer').getBoundingClientRect().top,
    }));
    assert.ok(mobileReading.textBottom <= mobileReading.controlsTop, 'Mobile scene text must scroll fully above the controls');
    await mobilePage.screenshot({path:path.join(output, '06b-mobile-reading.png'),fullPage:true});
    await mobilePage.locator('#narrativeSkip').click();
    assert.equal(await mobilePage.locator('#narrativeProgress').innerText(), '5 / 5');
    assert.equal((await (await mobile.request.get(`${base}/scene`)).json()).initial_state.started_at, null);
    await mobilePage.locator('#narrativeNext').click();
    await mobilePage.waitForFunction(() => !document.getElementById('sendBtn').disabled);
    await mobilePage.screenshot({path:path.join(output, '07-mobile-game.png'),fullPage:true});
    assert.equal(await mobilePage.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({status:'passed',commands,ending:'true_ending',inference_attempts:2,selected_evidence:19,opening_pages:5,confrontation_pages:4,reconstruction_pages:6,reconstruction_route:'button_wax',mobile_scene_font:'18px',page_errors:errors},null,2));
    console.log(JSON.stringify({status:'passed',commands,output}));
    await mobile.close();
  } catch (error) {
    await page.screenshot({path:path.join(output, 'failure.png'),fullPage:true}).catch(()=>{});
    throw error;
  } finally { await browser.close(); }
})().catch(error => {
  fs.writeFileSync(path.join(output,'result.json'), JSON.stringify({status:'failed',error:error.message},null,2));
  console.error(error);process.exitCode=1;
});
