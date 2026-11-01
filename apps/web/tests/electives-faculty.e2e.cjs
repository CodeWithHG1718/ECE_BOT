// Live integration proof: no mocked API responses or fabricated timetable slots.
const {chromium}=require(process.env.SIGNAL_PLAYWRIGHT_PATH || 'playwright');
const assert=require('node:assert/strict');
const source=require('../../../datafiles/academic/timetable_records.json');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1050}});
  let page=await context.newPage();const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const ready=page.waitForResponse(r=>r.url().endsWith('/api/v1/health'));
  await page.goto('http://localhost:3000');await ready;
  await page.getByRole('button',{name:'Launch Signal'}).click();
  assert.equal(await page.locator('#hss-course').inputValue(),'');
  assert.equal(await page.locator('#oec-course').inputValue(),'');
  assert.equal(await page.locator('#hss-course').getAttribute('required'),null);
  assert.equal(await page.locator('#oec-course').getAttribute('required'),null);
  await page.locator('#study-year').selectOption('3');await page.locator('#study-section').selectOption('24EC1');
  await page.locator('#hss-course option[value="HSS-302"]').waitFor({state:'attached'});
  assert.equal(await page.locator('#hss-course option[value="HSS-302"]').textContent(),'HSS-302 : Social Studies of Science');
  await page.getByRole('button',{name:'Continue to Signal'}).click();
  await page.locator('.workspace-shell').waitFor();
  async function send(text){
   await page.getByRole('textbox',{name:'Your message'}).fill(text);
   const done=page.waitForResponse(r=>r.url().endsWith('/messages')&&r.request().method()==='POST');
   await page.getByRole('button',{name:'Send message'}).click();const response=await done;
   assert.equal(response.status(),200);await page.waitForFunction(()=>!document.querySelector('textarea').disabled);
   return (await response.json()).assistant_message;
  }
  const core=new Set(['ECC-301','ECC-303','ECC-305','ECC-351']);
  function assertSource(answer,hss){
   const expected=source.filter(r=>r.study_year===3&&(core.has(r.course_code)||r.course_code===hss)&&(!r.student_sections.length||r.student_sections.includes('24EC1')));
   assert.deepEqual(answer.data.map(r=>r.record_id).sort(),expected.map(r=>r.record_id).sort());
   for(const row of answer.data){const original=source.find(r=>r.record_id===row.record_id);for(const key of ['day','start_time','end_time','room','faculty','session_type'])assert.equal(row[key],original[key]);}
  }
  assertSource(await send('My timetable'),null);
  assert.equal((await send('3rd year timetable')).data.length,59);
  async function profile(hss,oec){
   await page.getByRole('button',{name:'Change academic profile'}).click();
   await page.locator('#hss-course option[value="HSS-302"]').waitFor({state:'attached'});
   await page.locator('#hss-course').selectOption(hss||'');await page.locator('#oec-course').selectOption(oec||'');
   if(hss&&oec)await page.screenshot({path:'tmp/elective-profile.png'});
   await page.getByRole('button',{name:'Continue to Signal'}).click();await page.locator('.workspace-shell').waitFor();
  }
  await profile('HSS-302',null);let timetable=await send('Show my complete schedule');assertSource(timetable,'HSS-302');
  assert(timetable.data.some(r=>r.clashes_with.length));
  await page.locator('.conversation-body').evaluate(e=>e.scrollTop=e.scrollHeight);
  await page.screenshot({path:'tmp/elective-timetable.png'});
  assert.equal((await send('What is my HSS course?')).data[0].code,'HSS-302');
  const hss=await send('When is my HSS class?');assert(hss.data.every(r=>r.course_code==='HSS-302'));
  assert((await send('Who teaches it?')).data.some(r=>r.faculty.includes('Anindya')));
  const professor=await send('Tell me about that professor');assert(professor.content.includes('Anindya'));
  await profile(null,'ECO-101');timetable=await send('My ECE timetable');assertSource(timetable,null);assert(timetable.warnings.some(s=>s.includes('ECO-101')&&s.includes('unavailable')));
  await profile('HSS-302','ECO-101');timetable=await send('My timetable');assertSource(timetable,'HSS-302');
  assert(timetable.warnings.some(s=>s.includes('ECO-101')));
  await profile('HSS-305','ECO-102');assertSource(await send('Show my weekly schedule'),'HSS-305');
  // New page restores the same anonymous profile from persistent browser storage.
  await page.close();page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://localhost:3000');await page.locator('.workspace-shell').waitFor();
  assert((await page.locator('.profile-electives').innerText()).includes('HSS-305'));
  assert((await page.locator('.profile-electives').innerText()).includes('ECO-102'));
  await page.getByRole('button',{name:'Change academic profile'}).click();
  await page.locator('#hss-course option[value="HSS-305"]').waitFor({state:'attached'});
  assert.equal(await page.locator('#hss-course').inputValue(),'HSS-305');assert.equal(await page.locator('#oec-course').inputValue(),'ECO-102');
  await page.locator('#study-semester').selectOption('6');
  await page.waitForFunction(()=>!document.querySelector('#hss-course').disabled);
  assert.equal(await page.locator('#hss-course').inputValue(),'');assert.equal(await page.locator('#oec-course').inputValue(),'');
  assert.equal(await page.locator('#hss-course option').count(),1);
  await page.locator('#study-semester').selectOption('5');await page.locator('#hss-course option[value="HSS-302"]').waitFor({state:'attached'});
  await page.getByRole('button',{name:'Continue to Signal'}).click();await page.locator('.workspace-shell').waitFor();
  await send('Tell me about Vinod Pankajakshan');
  const checks=[['What courses does he teach?','Teaching Engagements'],['His research interests','Research Interests'],['His academic background','Educational Details'],['His publications','Publications'],['Tell me about Pankajakshan','Research Interests']];
  for(const [query,heading] of checks){const a=await send(query);assert.equal(a.data[0].faculty_id,'iitr-ece-100564');assert(a.data[0].profile_sections.some(s=>s.heading===heading));}
  const full=await send('Show me all information about Vinod Pankajakshan');assert(full.data[0].profile_sections.length>=10);assert.equal(full.data[0].projects.length,3);
  await page.locator('.conversation-body').evaluate(e=>e.scrollTop=e.scrollHeight);
  await page.screenshot({path:'tmp/faculty-details.png'});
  assert.equal((await send('His projects')).data.length,3);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
  await page.getByRole('button',{name:'Open conversation menu'}).click();
  await page.getByRole('button',{name:'Change academic profile'}).click();
  await page.locator('#hss-course option[value="HSS-302"]').waitFor({state:'attached'});
  assert.equal(await page.locator('#hss-course').inputValue(),'');
  assert.equal(await page.locator('#oec-course').inputValue(),'');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
  await page.screenshot({path:'tmp/elective-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log('PASS: None defaults, optional fields, actual course labels, all four selection combinations, source-exact schedules, real clashes, unavailable OEC slots, course/faculty follow-ups, changed selections, new-tab persistence, semester refresh, six faculty queries, complete cross-document projects, responsive layout.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
