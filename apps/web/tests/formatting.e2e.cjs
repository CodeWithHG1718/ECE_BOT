const {chromium}=require(process.env.SIGNAL_PLAYWRIGHT_PATH || 'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const session=await (await page.request.post('http://localhost:8000/api/v1/sessions')).json();
  const headers={'X-Session-Token':session.session_token};
  assert.equal((await page.request.put(`http://localhost:8000/api/v1/sessions/${session.session_id}/profile`,{headers,data:{study_year:3,section:'24EC2'}})).status(),200);
  await page.request.post(`http://localhost:8000/api/v1/sessions/${session.session_id}/conversations`,{headers});
  await context.addInitScript(s=>localStorage.setItem('signal.session.v1',JSON.stringify(s)),session);
  await page.goto('http://localhost:3000');await page.locator('.workspace-shell').waitFor();
  async function send(text){
   await page.getByRole('textbox',{name:'Your message'}).fill(text);
   const done=page.waitForResponse(r=>r.url().endsWith('/messages')&&r.request().method()==='POST');
   await page.getByRole('button',{name:'Send message'}).click();const response=await done;assert.equal(response.status(),200);
   await page.waitForFunction(()=>!document.querySelector('textarea').disabled);
   return (await response.json()).assistant_message;
  }
  const timetable=await send('give me time table in proper format');
  assert.equal(timetable.presentation,'timetable');assert(timetable.data.length>0);
  assert.equal(await page.locator('.schedule-table tbody tr').count(),timetable.data.length);
  assert(await page.locator('.schedule-day h3').count()>0);
  assert.equal(await page.locator('.schedule-table th').filter({hasText:'Applicability'}).count(),0);
  await page.locator('.conversation-body').evaluate(e=>e.scrollTop=0);
  await page.screenshot({path:'tmp/formatted-timetable.png'});
  await send('my end term exam schedule');
  const exam=page.locator('.message-assistant').last();assert.equal(await exam.locator('.schedule-table tbody tr').count(),4);
  assert(!/applicability|all_programmes|unverified|source notes/i.test(await exam.innerText()));
  assert.equal(await page.locator('.citation-list,.message-warnings').count(),0);
  await exam.scrollIntoViewIfNeeded();await page.screenshot({path:'tmp/formatted-exams.png'});
  // Deterministic display fixture reproduces the screenshot's Markdown, independent of model wording.
  const text='### Study resources\n\nFor **ECC-301 Digital Signal Processing**, use:\n\n- [Full NPTEL course](https://nptel.ac.in/courses/108106151)\n- **S. K. Mitra**, *Digital Signal Processing*\n\n| Topic | Start here |\n|---|---|\n| LTI systems | Convolution |\n\n*2026–27 Autumn source record; applicability unverified.*\n\nThe NPTEL course is a study resource, not an official IIT Roorkee course equivalent.\n\n[unsafe](javascript:alert(1))';
  await page.route('**/messages',async route=>{
   if(route.request().method()!=='POST')return route.continue();
   const now=new Date().toISOString();
   await route.fulfill({json:{user_message:{id:'format-user',role:'user',content:'give me resources',presentation:'answer',created_at:now},assistant_message:{id:'format-answer',role:'assistant',content:text,presentation:'answer',data:null,sources:[{title:'Source record',status:'unverified'}],warnings:['Draft exam schedule.','Applicability unverified'],created_at:now}}});
  });
  await send('give me resources');const answer=page.locator('.message-assistant').last();
  assert.equal(await answer.locator('h3').innerText(),'Study resources');
  assert.equal(await answer.locator('strong').count(),2);assert.equal(await answer.locator('ul li').count(),2);
  assert.equal(await answer.locator('a[href="https://nptel.ac.in/courses/108106151"]').count(),1);
  assert.equal(await answer.locator('table tbody tr').count(),1);
  assert.equal(await answer.locator('a[href^="javascript:"]').count(),0);
  assert(!/unverified|applicability|not an official/.test(await answer.innerText()));
  await answer.scrollIntoViewIfNeeded();await page.screenshot({path:'tmp/formatted-resources.png'});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollHeight),844);
  await page.screenshot({path:'tmp/formatted-mobile.png'});
  assert.deepEqual(errors,[]);
  console.log('PASS: live timetable wording and rows, day groups, compact exam schedule, no source/status clutter, Markdown headings/lists/links/tables, unsafe links blocked, mobile viewport.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
