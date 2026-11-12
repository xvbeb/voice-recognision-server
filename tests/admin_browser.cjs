// Run against an isolated local HTTPS test server; never production.
const assert=require('node:assert/strict');
const {chromium}=require('../../bookmarklet/node_modules/playwright');
const url=process.env.Q_ADMIN_TEST_URL;
if(!url || !['127.0.0.1','localhost'].includes(new URL(url).hostname))throw Error('Local Q_ADMIN_TEST_URL required');
if(!process.env.Q_ADMIN_TEST_PASSWORD)throw Error('Synthetic Q_ADMIN_TEST_PASSWORD required');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1280,height:1000}});
  const page=await context.newPage();page.setDefaultTimeout(10000);page.setDefaultNavigationTimeout(10000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url+'/admin');
  assert.ok(page.url().endsWith('/admin/login'));
  await page.locator('input[name=password]').fill(process.env.Q_ADMIN_TEST_PASSWORD);
  await page.getByRole('button',{name:'Войти →'}).click();
  await page.locator('#data:not([hidden])').waitFor();
  assert.equal(await page.locator('.card').count(),9);
  assert.ok(await page.locator('.day').count()>0);
  await page.locator('.day').first().focus();
  assert.ok((await page.locator('#chart-detail').innerText()).includes('успешно'));
  await page.locator('#period').selectOption('all');
  await page.waitForFunction(()=>document.querySelector('#data').hidden===false && !document.querySelector('#refresh').disabled);
  assert.ok(await page.locator('#events tr').count()>0);
  await page.screenshot({path:'/private/tmp/q-admin-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  await page.screenshot({path:'/private/tmp/q-admin-mobile.png',fullPage:true});
  await page.route('**/api/admin/stats?*',route=>route.fulfill({status:503,contentType:'application/json',body:'{"detail":"unavailable"}'}));
  await page.locator('#refresh').click();
  await page.locator('#error:not([hidden])').waitFor();
  assert.equal(await page.locator('#data').isVisible(),false);
  await page.unroute('**/api/admin/stats?*');
  await page.locator('#refresh').click();
  await page.locator('#data:not([hidden])').waitFor();
  await page.locator('#logout').click();
  await page.waitForURL('**/admin/login');
  const r=await context.request.get(url+'/api/admin/stats');assert.equal(r.status(),401);
  assert.deepEqual(errors,[]);
  console.log('Chrome: login, 9 cards, interactive chart, periods, mobile, failure/recovery, logout PASS');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
