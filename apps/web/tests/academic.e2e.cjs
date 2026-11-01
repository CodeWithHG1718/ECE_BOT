// Run against the local frontend and backend. Requires Playwright + Chromium.
const { chromium } = require(process.env.SIGNAL_PLAYWRIGHT_PATH || 'playwright');
const assert = require('node:assert/strict');
(async () => {
 const browser = await chromium.launch({headless:true});
 try {
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[];page.on('pageerror', e=>errors.push(e.message));
  const ready=page.waitForResponse(r=>r.url().endsWith('/api/v1/health'));
  await page.goto('http://localhost:3000');await ready;
  await page.getByRole('button',{name:'Launch Signal'}).click();
  await page.locator('#study-year').selectOption('3');
  await page.locator('#study-section').selectOption('24EC1');
  await page.getByRole('button',{name:'Continue to Signal'}).click();
  await page.locator('.workspace-shell').waitFor();
  async function send(text) {
   await page.getByRole('textbox',{name:'Your message'}).fill(text);
   const response=page.waitForResponse(r=>r.url().endsWith('/messages') && r.request().method()==='POST');
   await page.getByRole('button',{name:'Send message'}).click();
   const result=await response;assert.equal(result.status(),200);
   await page.getByRole('textbox',{name:'Your message'}).waitFor({state:'visible'});
   await page.waitForFunction(()=>!document.querySelector('textarea').disabled);
   const answer=(await result.json()).assistant_message;
   console.log(JSON.stringify({query:text,presentation:answer.presentation,rows:answer.data?.length,content:answer.content}));
   return answer;
  }
  assert.equal((await send('3rd year timetable')).data.length,59);
  assert.equal(await page.locator('.facts-table tbody tr').count(),59);
  assert.equal((await send('my timetable')).data.length,13);
  const exam=await send('ETE schedule');assert(exam.data.length>0 && exam.data.length<808);
  const faculty=await send('Who teaches it?');assert(faculty.data.length>0);
  assert.equal((await send('ECC303')).data[0].code,'ECC-303');
  assert.equal((await send('microwve course')).data[0].code,'ECC-303');
  assert.equal((await send('ECC301 and ECC303')).data.length,2);
  assert.equal(await page.locator('.message-assistant').last().locator('.course-record-title').count(),2);
  assert((await send('Sparsh Mittal projects')).data.length>0);
  const tomorrow=await send('classes tomorrow');assert(tomorrow.data.every(r=>r.date));
  const learning=await send('help me learn my microwave course');
  assert.equal(learning.presentation,'answer');assert.equal(learning.data,null);
  assert(!/unavailable|not configured|No matching source/.test(learning.content));
  assert(learning.content.split(/\s+/).length<180);
  const credentials=await page.evaluate(()=>JSON.parse(localStorage.getItem('signal.session.v1')));
  for(let i=0;i<32;i++) {
   const r=await page.request.post(`http://localhost:8000/api/v1/sessions/${credentials.session_id}/conversations`,{headers:{'X-Session-Token':credentials.session_token}});
   assert.equal(r.status(),201);
  }
  await page.reload();await page.locator('.conversation-link').nth(32).waitFor();
  // Open the populated conversation, rather than the newly created empty chats.
  await page.locator('.conversation-link').last().click();
  await page.locator('.facts-table').first().waitFor();
  await page.waitForTimeout(600);
  const scrollState=()=>page.evaluate(()=>({window:scrollY,main:document.querySelector('.conversation-body').scrollTop,side:document.querySelector('.conversation-list').scrollTop}));
  await page.evaluate(()=>{document.querySelector('.conversation-list').scrollTop=0});
  let before=await scrollState();
  await page.locator('.conversation-list').hover();await page.mouse.wheel(0,600);await page.waitForTimeout(300);
  let after=await scrollState();assert(after.side>before.side);assert.equal(after.main,before.main);assert.equal(after.window,0);
  before=after;
  await page.locator('.conversation-body').hover();await page.mouse.wheel(0,-600);await page.waitForTimeout(300);
  after=await scrollState();assert(after.main<before.main);assert.equal(after.side,before.side);assert.equal(after.window,0);
  // Wheel at the sidebar boundary must not chain into the page or chat.
  await page.evaluate(()=>{const e=document.querySelector('.conversation-list');e.scrollTop=e.scrollHeight});
  before=await scrollState();await page.locator('.conversation-list').hover();await page.mouse.wheel(0,800);await page.waitForTimeout(300);
  after=await scrollState();assert.equal(after.main,before.main);assert.equal(after.window,0);
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Open conversation menu'}).click();
  await page.waitForTimeout(300);
  assert(await page.getByRole('button',{name:'Close conversation menu',exact:true}).first().isVisible());
  const mobile=await page.evaluate(()=>({width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,viewport:innerHeight}));
  assert(mobile.width<=390);assert.equal(mobile.height,mobile.viewport);
  await page.getByRole('button',{name:'Close conversation menu',exact:true}).first().click();
  await page.waitForTimeout(300);
  await page.evaluate(()=>{document.querySelector('.conversation-body').scrollTop=0});
  await page.screenshot({path:'tmp/student-context-mobile.png'});
  await page.setViewportSize({width:1440,height:900});
  await page.screenshot({path:'tmp/student-context-desktop.png'});
  assert.deepEqual(errors,[]);
  console.log('PASS: live chat, complete records, personal exams, course/faculty context, model response, desktop scroll isolation, mobile layout, no browser errors');
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
