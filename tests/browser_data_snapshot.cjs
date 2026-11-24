/* Optional browser acceptance test. Run against an isolated test DB/server. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.CURRI_URL || 'http://127.0.0.1:8000';
(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1050}});
    const page = await context.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    fs.mkdirSync('/tmp/curri-screenshots',{recursive:true});
    await page.goto(base);
    await page.locator('#interests').waitFor();
    await page.screenshot({path:'/tmp/curri-screenshots/home.png',fullPage:true});
    await page.locator('#interests').fill('자율주행');
    await page.getByRole('button',{name:'나와 연결되는 연구실 찾기'}).click();
    await page.locator('.lab-card').first().waitFor();
    assert.ok(await page.locator('.lab-card').count()>2);
    await page.screenshot({path:'/tmp/curri-screenshots/results.png',fullPage:true});
    const first=page.locator('.lab-card').filter({has:page.getByRole('heading',{name:'곽수하 연구실',exact:true})});
    await first.getByRole('button',{name:'이 연구실 알아보기'}).click();
    await page.locator('[data-course-id]').first().waitFor();
    // Lab intro: the name appears once and research areas are a list, not one ' · '-joined line.
    assert.equal(await page.locator('.lab-sidebar h2').innerText(),'곽수하 연구실');
    assert.equal(await page.locator('.lab-sidebar .micro').first().innerText(),'컴퓨터비전 연구실');
    assert.ok(await page.locator('.lab-sidebar .overview li').count()>0);
    await page.locator('[data-course-id]').first().check();
    await page.locator('#note').fill('영상 연구의 접근법을 비교하고 싶어요. <script>unsafe</script>');
    await page.waitForTimeout(1000);
    await page.reload();
    await page.locator('#note').waitFor();
    assert.equal(await page.locator('[data-course-id]:checked').count(),1);
    assert.ok((await page.locator('#note').inputValue()).includes('<script>unsafe</script>'));
    await page.getByRole('button',{name:'나의 연구 가이드 보기'}).click();
    await page.locator('.guide-columns').waitFor();
    assert.equal(await page.locator('.guide-column').count(),2);
    await page.getByRole('button',{name:'후보와 메모 저장'}).click();
    await page.waitForFunction(()=>document.querySelector('#saved-count').textContent==='1');
    await page.screenshot({path:'/tmp/curri-screenshots/detail.png',fullPage:true});
    assert.deepEqual(errors, []);
    const mobile = await browser.newContext({viewport:{width:390,height:844},isMobile:true});
    const mp = await mobile.newPage();
    mp.on('pageerror', error=>errors.push(error.message));
    await mp.goto(base);
    await mp.locator('#interests').fill('자율주행');
    await mp.getByRole('button',{name:'나와 연결되는 연구실 찾기'}).click();
    await mp.locator('.lab-card').first().waitFor();
    assert.ok(await mp.locator('.lab-card').count()>2);
    await mp.locator('.lab-card').first().getByRole('button',{name:'이 연구실 알아보기'}).click();
    await mp.locator('[data-course-id]').first().waitFor();
    await mp.getByRole('button',{name:'나의 연구 가이드 보기'}).click();
    await mp.locator('.guide-columns').waitFor();
    assert.deepEqual(errors, []);
    console.log('Desktop search/detail/course selection/note reload/guide/save and mobile search/detail/guide passed');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
