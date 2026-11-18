'use strict';
const $ = (selector) => document.querySelector(selector);
const main = $('#main');
const h = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {session: null, results: [], searchInfo: {}, lab: null, selected: new Set(), paperSelected: new Set(), guide: null, note: '', saved: false, dirty: false, view: 'home', pendingLab: null, register: false, concepts: [], community: null, thread: null, threadData: null, board: null, boardLab: ''};
let busy = false;
let toastTimer;
let draftTimer;
let draftUnsaved = false;

async function api(path, data) {
  const response = await fetch(`/api/${path}`, {method: data === undefined ? 'GET' : 'POST', headers: data === undefined ? {} : {'Content-Type': 'application/json'}, credentials: 'same-origin', body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.error || '잠시 후 다시 시도해 주세요.'); error.code = result.code; throw error; }
  return result;
}
// Keep each phrase (text up to a comma or full stop) on one line, so lines break at punctuation instead of mid-phrase.
// Applies to fixed guidance text only; lab, paper and course text keeps normal wrapping.
const PHRASED = '.hero-intro p, .page-heading > p, .sub, .sheet-sub, .empty p, .notice, .scope, .overseas-note, .how-list li, .save-panel > p, .selection-actions p, dialog > p, .ai-guide.muted p, .ai-guide.pending p, .footer-note';
function phrase(root) {
  const targets = [...(root.matches?.(PHRASED) ? [root] : []), ...(root.querySelectorAll?.(PHRASED) || [])];
  targets.forEach(el => {
    if (el.dataset.ph) return; el.dataset.ph = '1';
    [...el.childNodes].forEach(node => {
      if (node.nodeType !== 3 || !node.nodeValue.trim()) return;
      const parts = node.nodeValue.split(/(?<=[,.?!…]) +/);
      if (parts.length < 2) return;
      const frag = document.createDocumentFragment();
      parts.forEach((part, i) => { const span = document.createElement('span'); span.className = 'ph'; span.textContent = part; frag.append(span, i < parts.length - 1 ? ' ' : ''); });
      node.replaceWith(frag);
    });
  });
}
new MutationObserver(records => records.forEach(r => r.addedNodes.forEach(n => { if (n.nodeType === 1 && !n.classList.contains('ph')) phrase(n); }))).observe(document.documentElement, {childList: true, subtree: true});
document.addEventListener('DOMContentLoaded', () => phrase(document.body));
function toast(text) {
  clearTimeout(toastTimer); $('#toast').textContent = text; $('#toast').hidden = false;
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 5500);
}
async function action(work) {
  if (busy) return;
  busy = true; main.setAttribute('aria-busy', 'true');
  const controls = [...document.querySelectorAll('button, input, textarea, select')].map(element => [element, element.disabled]);
  controls.forEach(([element]) => { element.disabled = true; });
  try { await work(); }
  catch (error) { toast(error.message || '연결을 확인하고 다시 시도해 주세요.'); }
  finally { busy = false; main.removeAttribute('aria-busy'); controls.forEach(([element, disabled]) => { element.disabled = disabled; }); }
}
async function refreshSession() { state.session = await api('session'); header(); }
function header() {
  $('#saved-count').textContent = state.session?.explorations.filter(e => e.saved).length || 0;
  const user = state.session?.user;
  $('#account').textContent = user ? (user.nickname || '내 프로필') : '로그인';
  $('#inbox-nav').hidden = !user;
  $('#unread-count').textContent = state.session?.unread || 0;
  $('#unread-count').classList.toggle('alert', Boolean(state.session?.unread));
}
// Each screen gets a browser history entry, so the phone's back button moves between screens instead of leaving the site.
let restoring = false;
function setView(view) {
  state.view = view; sessionStorage.setItem('curri-view', view);
  const entry = {view, lab: view === 'detail' ? state.lab?.id || null : null}, current = history.state;
  if (!restoring && !(current && current.view === entry.view && current.lab === entry.lab)) history[current ? 'pushState' : 'replaceState'](entry, '', pathFor(view));
  main.focus({preventScroll:true}); window.scrollTo({top:0, behavior:'instant'}); }
function nameOf(lab) {
  // A lab without a known professor name carries its lab name instead; don't append "연구실" twice.
  if (lab.professors.length===1 && /연구실|\blab\b|laboratory|group/i.test(lab.professors[0])) return lab.professors[0];
  return lab.professors.map(p => p.split(' (')[0]).join(' · ') + ' 연구실';
}
// The lab's own name only when it adds something to "<교수> 연구실" (older catalogs send only lab_name).
function subtitleOf(lab) { const s = lab.lab_subtitle ?? lab.lab_name ?? ''; return s && s !== nameOf(lab) ? s : ''; }
// Professor line only when it says more than the title (e.g. an affiliation note in parentheses).
function professorLine(lab) { const s = lab.professors.join(' · '); return nameOf(lab).startsWith(s) ? '' : s; }
// Research overview as a short list. The note says where the items come from (lab material,
// OpenAlex paper classification or paper titles); cards repeat it only when it is not the lab's own words.
const overviewKey = text => String(text).slice(0,100).replace(/[\s.,;:]+$/,'');
function overviewHTML(lab, limit, alwaysNote, matched=new Set()) {
  const o = lab.overview;
  if (!o) return lab.summary ? `<p class="summary">${h(lab.summary)}</p>` : '';
  if (!o.items.length) return `<p class="micro">${h(o.note)}</p>`;
  const rest = o.items.length - limit, note = alwaysNote || o.source !== 'lab_material';
  return `<div class="overview"><p class="overview-title">${h(o.title)}</p><ul>${o.items.slice(0,limit).map(i=>matched.has(overviewKey(i))?`<li class="matched">${h(i)} <span class="micro">관심과 일치</span></li>`:`<li>${h(i)}</li>`).join('')}</ul>${rest>0?`<p class="micro">외 ${rest}개</p>`:''}${note?`<p class="micro">${h(o.note)}</p>`:''}</div>`;
}
function tags(topics) { return `<div class="tag-list">${topics.map(t => `<span class="pill ${t.role === 'method' ? 'method' : ''}">${h(t.label)}</span>`).join('')}</div>`; }
// Highlight query terms inside already-escaped text. Marks are exact substrings of the original text.
function marked(text, marks) { let out = h(text); (marks||[]).forEach(m => { const em = h(m); if (em) out = out.split(em).join(`<mark>${em}</mark>`); }); return out; }
function sourceLinks(e) { const label = e.section==='representative_paper' ? '논문 보기' : '홈페이지'; return (e.urls||[]).map((url,i) => `<a href="${h(url)}" target="_blank" rel="noopener noreferrer">${label}${e.urls.length > 1 ? ' '+(i+1) : ''} ↗</a>`).join(''); }
// Research areas from one source become a single line of tags; other passages keep their own block.
function groupEvidence(items) {
  const out = [];
  items.forEach(e => {
    if (e.kind && e.section==='research_area') {
      const prev = out.find(x => x.section==='research_area' && x.urls.join() === e.urls.join());
      if (prev) { prev.tags.push(e.title); return; }
      out.push({...e, tags:[e.title]}); return;
    }
    out.push(e);
  });
  return out;
}
function evidence(items, count=items.length) { return evidenceList(groupEvidence(items).slice(0,count)); }
function evidenceList(list) {
  return list.map(e => {
    if (!e.kind) return `<div class="evidence"><p>${h(e.text)}</p>${(e.urls||[]).map((url,i) => `<a href="${h(url)}" target="_blank" rel="noopener noreferrer">원문 ${e.urls.length > 1 ? i+1 : ''} ↗</a>`).join('')}</div>`;
    const kind = `<span class="ev-kind">${h(e.kind)}${e.year?` · ${h(e.year)}`:''}</span>`;
    if (e.tags) return `<div class="evidence">${kind}<p class="ev-tags">${e.tags.map(h).join(' · ')}</p>${sourceLinks(e)}</div>`;
    return `<div class="evidence">${kind}${e.title && e.section!=='research_intro' ? `<p class="ev-title">${h(e.title)}</p>` : ''}${e.snippet ? `<p class="ev-snippet">${marked(e.snippet, e.marks)}</p>` : ''}${sourceLinks(e)}${e.full ? `<details class="ev-full"><summary>${e.section==='representative_paper'?'초록 전체':'전체 보기'}</summary><p>${h(e.full)}</p></details>` : ''}</div>`;
  }).join('');
}
function steps(active) { return `<ol class="steps" aria-label="진행 단계">${['연구실 고르기','수강한 과목 표시','연구 가이드'].map((label,n)=>`<li${active===n+1?' aria-current="step"':''}>${label}</li>`).join('')}</ol>`; }
function pageTop(active, label='연구실 목록으로', back='results') { return `<div class="page-top"><button class="back" data-action="${back}">← ${label}</button>${steps(active)}</div>`; }

function renderHome() {
  setView('home');
  const profile = state.session?.profile || {};
  main.innerHTML = `<section class="hero"><div><div class="hero-intro"><h1>관심 분야를 적으면 POSTECH 연구실을 찾아 드려요.</h1><p>연구실 소개와 논문에서 내 관심과 겹치는 내용을 찾아 보여 주고, 그 연구실과 이어지는 과목까지 알려 드려요.</p></div><form id="interest-form" class="input-card"><label for="interests">무엇이 궁금한가요? <small>관심 분야, 재미있었던 수업, 고민 모두 괜찮아요</small><textarea id="interests" name="interests" required minlength="2" maxlength="500" placeholder="요즘 궁금한 것을 편하게 적어 주세요. 아래 예시를 눌러서 시작해도 돼요.">${h(profile.interests || '')}</textarea></label>${searchNoticeHTML()}<div class="chips" role="group" aria-label="예시로 채우기"><button type="button" class="chip" data-action="example" data-value="로봇이 스스로 주변을 인식하고 움직이는 게 신기해요. 자율주행처럼 센서 데이터로 판단하는 연구를 해보고 싶어요.">로봇·자율주행</button><button type="button" class="chip" data-action="example" data-value="반도체 소자가 어떻게 만들어지는지 궁금해요. 새로운 소자 구조나 공정을 연구해 보고 싶어요.">반도체·소자</button><button type="button" class="chip" data-action="example" data-value="영상이나 상품을 추천해 주는 시스템이 어떻게 동작하는지 궁금해요. 강화학습으로 더 나은 추천을 만드는 연구에 관심이 있어요.">추천·강화학습</button><button type="button" class="chip" data-action="example" data-value="AI가 틀린 답을 자신 있게 말하는 게 걱정돼요. AI를 안전하고 믿을 수 있게 만드는 연구를 해보고 싶어요.">AI 안전성</button></div><fieldset class="goal-set"><legend>지금 어떤 단계인가요?</legend><div class="goal-row">${[['explore','아직 알아보는 중'],['research','연구참여'],['graduate','연구실 진학']].map(([value,label]) => `<label><input type="radio" name="goal" value="${value}" ${(profile.goal || 'explore')===value?'checked':''}><span>${label}</span></label>`).join('')}</div></fieldset><button class="primary full" type="submit">나와 연결되는 연구실 찾기</button></form></div><aside class="hero-aside"><h2>이렇게 진행돼요</h2><ol class="how-list"><li><b>연구실 고르기</b>내 관심과 겹치는 연구실을<br>근거 문장과 함께 보여 줘요.</li><li><b>수강한 과목 표시</b>그 연구실과 이어지는 과목 중<br>수강한 것을 골라요.</li><li><b>연구 가이드</b>관심사와 수강한 과목 정보를 기반으로<br>연구 주제와 학습 전략을 제안해 줘요.</li></ol><p class="micro scope">현재 자료 범위는 추천 가능한 연구실 307곳과 과목 1,151개예요. 모든 연구실과 과목이 들어 있지는 않아요. 첫 연구실은 로그인 없이 끝까지 볼 수 있어요.</p></aside></section>`;
}

function labCard(lab,index) {
  // Lead with one quoted passage; research-area tags repeat the overview list, so they stay folded.
  const ev = groupEvidence(lab.evidence).slice(0,3), lead = ev.find(e => e.kind && !e.tags && e.snippet), rest = ev.filter(e => e !== lead);
  return `<article class="lab-card" data-search-text="${h((nameOf(lab)+' '+lab.department+' '+lab.topics.map(t=>t.label).join(' ')).toLowerCase())}"><div class="lab-main"><h3>${h(nameOf(lab))}</h3>${subtitleOf(lab)?`<p class="micro">${h(subtitleOf(lab))}</p>`:''}<p class="lab-meta">${h(lab.department)}</p>${professorLine(lab)?`<p class="professor">${h(professorLine(lab))}</p>`:''}${cardOverview(lab)}${ev.length?`<div class="lab-evidence"><p class="group-title">연결 근거</p>${lead?evidenceList([lead]):''}${rest.length?`<details><summary>근거 ${rest.length}개 ${lead?'더 ':''}보기</summary>${evidenceList(rest)}</details>`:''}</div>`:''}<p class="reason">${h(lab.reason)}</p></div><div class="lab-side"><button class="explore-button" data-action="explore" data-id="${h(lab.id)}" data-rank="${index}">이 연구실 알아보기</button><a href="${h(lab.url)}" target="_blank" rel="noopener noreferrer">연구실 홈페이지 ↗</a></div>${resultFeedbackHTML(lab,index)}</article>`;
}
// Card: overview list (matched areas marked in place) plus pills only for matches not already listed.
function cardOverview(lab) {
  const hits = lab.topics.filter(t=>lab.matched_topics.includes(t.id));
  const listed = new Set((lab.overview?.items || []).slice(0,3).map(overviewKey));
  const matched = new Set(hits.map(t=>overviewKey(t.label)).filter(k=>listed.has(k)));
  return overviewHTML(lab,3,false,matched) + tags(hits.filter(t=>!matched.has(overviewKey(t.label))));
}
async function runSearch(payload) {
  let r = await api('search', payload);
  if (r.mode === 'starting') {
    toast('의미 검색을 준비하고 있어요. 첫 검색은 1~3분 걸릴 수 있습니다.');
    let ready = false;
    for (let attempt = 0; attempt < 60 && !ready; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 3000));
      ready = !!(await api('engine')).embedding;
    }
    if (ready) r = await api('search', payload);
    if (!ready || r.mode === 'starting') {
      r.mode = 'dictionary';
      r.message = '의미 검색 준비가 늦어져 현재 가능한 검색 결과를 보여드립니다.';
    }
  }
  state.results = r.labs;
  state.searchInfo = {intent: r.intent || 'search', message: r.message || '', interpretation: r.interpretation || {likes: [], dislikes: []}, mode: r.mode || '', uncertain: !!r.uncertain, courses: r.courses || [], mirror: r.mirror || null};
  mirrorInit(r.mirror);
}

// Long text only: what the student said, grouped by dimension, with the sentence it came from.
// The student can edit the list and confirm it; confirming is stored but does not change ranking.
const MIRROR_DIMS = [['topic','관심 주제'],['style','하고 싶은 방식'],['output','만들고 싶은 결과'],['constraint','환경·조건']];
function mirrorInit(m) {
  const saved = (state.session.profile.confirmed_slots || []);
  const source = saved.length ? saved : ((m && m.slots) || []);
  state.mirror = {draft: Object.fromEntries(MIRROR_DIMS.map(([key]) => [key, ((source.find(s => s.key === key) || {}).values || []).slice()])),
    quotes: Object.fromEntries(((m && m.slots) || []).map(s => [s.key, s.quote || ''])), confirmed: saved.length > 0};
}
function mirrorHTML() {
  const m = (state.searchInfo || {}).mirror, d = state.mirror;
  if (!m || !m.slots || !m.slots.length || !d) return '';
  const rows = MIRROR_DIMS.map(([key, label]) => {
    const values = d.draft[key], quote = d.quotes[key];
    const chips = values.map((v, i) => `<span class="pill neutral">${h(v)}${d.confirmed ? '' : `<button type="button" class="mirror-x" data-action="mirror-remove" data-key="${key}" data-index="${i}" aria-label="${h(v)} 지우기">×</button>`}</span>`).join('');
    const add = d.confirmed ? '' : `<span class="mirror-add"><input class="mirror-input" id="mirror-add-${key}" data-key="${key}" maxlength="40" aria-label="${h(label)} 추가" placeholder="직접 적기"><button type="button" class="secondary" data-action="mirror-add" data-key="${key}">추가</button></span>`;
    if (d.confirmed && !values.length) return '';
    return `<li><span class="mirror-label">${h(label)}</span><span class="mirror-values">${chips || '<span class="micro">아직 적지 않으셨어요</span>'}</span>${quote && !d.confirmed ? `<q class="mirror-quote">${h(quote)}</q>` : ''}${add}</li>`;
  }).join('');
  const foot = d.confirmed
    ? `<p class="micro">확정했어요. 이 검색 내용에만 저장되고, 검색 순위에는 쓰이지 않아요.</p><button type="button" class="text-button" data-action="mirror-edit">고치기</button>`
    : `<div class="mirror-actions"><button type="button" class="secondary" data-action="mirror-confirm">이대로 확정</button></div><p class="micro">적어 주신 문장에서 표현을 그대로 가져온 정리예요. 어떤 사람인지 판단한 것이 아니고, 틀린 건 지우거나 직접 고칠 수 있어요. 확정해도 검색 순위에는 쓰이지 않아요.</p>`;
  return `<details class="mirror" id="mirror-box" open><summary>적어 주신 내용을 이렇게 정리해 봤어요</summary><ul>${rows}</ul>${foot}</details>`;
}
function renderMirror() { const box = $('#mirror-box'); if (box) box.outerHTML = mirrorHTML(); }
async function mirrorAction(name, button) {
  const d = state.mirror;
  if (name === 'mirror-remove') d.draft[button.dataset.key].splice(Number(button.dataset.index), 1);
  else if (name === 'mirror-add') {
    const input = $(`#mirror-add-${button.dataset.key}`), value = input.value.replace(/\s+/g, ' ').trim();
    if (!value) return;
    if (value.length > 40) { toast('각 항목은 40자 이하로 적어 주세요.'); return; }
    const list = d.draft[button.dataset.key];
    if (list.length >= 8) { toast('항목은 8개까지 적을 수 있어요.'); return; }
    if (!list.includes(value)) list.push(value);
  } else if (name === 'mirror-edit') d.confirmed = false;
  else if (name === 'mirror-confirm') {
    const slots = MIRROR_DIMS.filter(([key]) => d.draft[key].length).map(([key]) => ({key, values: d.draft[key]}));
    try {
      const r = await api('mirror/confirm', {slots});
      state.session.profile.confirmed_slots = r.confirmed_slots;
      d.confirmed = r.confirmed_slots.length > 0;
      toast(d.confirmed ? '정리한 내용을 확정했어요.' : '정리한 내용을 비웠어요.');
    } catch (error) { toast(error.message); return; }
  }
  renderMirror();
}

function searchInfoHTML() {
  const i = state.searchInfo || {};
  const likes = (i.interpretation && i.interpretation.likes) || [], dislikes = (i.interpretation && i.interpretation.dislikes) || [];
  const parts = [];
  if (i.intent === 'search' && (likes.length || dislikes.length)) parts.push(`<div class="interest-line"><span class="micro">이렇게 이해했어요</span>${likes.map(x => `<span class="pill">${h(x)}</span>`).join('')}${dislikes.map(x => `<span class="pill method">제외 · ${h(x)}</span>`).join('')}</div>`);
  if (i.intent === 'search') parts.push(mirrorHTML());
  if (i.uncertain) parts.push('<div class="notice">관심을 정확히 이해했는지 확실하지 않아요. 위에 이해한 내용이 맞는지 확인하고, 아니라면 다른 표현으로 다시 적어 보세요.</div>');
  if (i.mode === 'embedding') parts.push('<p class="micro">표현이 달라도 의미가 비슷한 내용까지 함께 찾았어요.</p>');
  if ((i.courses || []).length) parts.push(`<p class="micro">관련 수업: ${i.courses.slice(0,3).map(c => `‘${h(c.name)}’`).join(' · ')}${i.courses.length > 3 ? ` 외 ${i.courses.length-3}개` : ''}. 이 수업을 맡은 교수의 연구실과 수업 내용이 가까운 연구실도 함께 찾았어요. 공식 선수과목 관계는 아니에요.</p>`);
  return parts.join('');
}

function renderResults() {
  setView('results');
  const asking = !state.results.length && state.searchInfo?.intent && state.searchInfo.intent !== 'search';
  main.innerHTML = `${pageTop(1,'관심 수정하기','home')}<section class="page-heading"><h1>${asking?'어떤 연구가 궁금한지 알려 주세요.':'내 관심과 겹치는 연구실'}</h1>${asking?'':'<p>연구실마다 어떤 문장을 보고 연결했는지 함께 보여 줘요. 관심 주제는 연구의 대상일 수도, 방법일 수도 있어요.</p>'}<blockquote class="query-echo">${h(state.session.profile.interests)}</blockquote>${searchInfoHTML()}</section>${asking?'':`<div class="results-toolbar"><p>연결 근거를 찾은 연구실 <strong class="num">${state.results.length}</strong>곳</p><input id="lab-filter" type="search" aria-label="결과 안에서 연구실 찾기" placeholder="교수명·연구 분야로 좁혀보기"></div>`}${state.results.length ? `<div class="labs-grid">${state.results.map(labCard).join('')}</div><p id="filter-empty" class="notice" hidden>검색 조건에 맞는 연구실이 없어요.</p>` : (state.searchInfo&&state.searchInfo.message?`<div class="empty"><h3>조금만 더 알려 주세요.</h3><p>${h(state.searchInfo.message)}</p><button class="secondary" data-action="home">관심 다시 적기</button></div>`:'<div class="empty"><h3>지금 자료에서는 연결 근거를 찾지 못했어요.</h3><p>관심이 잘못된 것은 아니에요. 현재 정제 자료에서 추천 가능한 연구실 307곳을 검색하고 있어요. 관심을 다른 표현으로 적어보셔도 좋아요.</p><button class="secondary" data-action="home">관심 다시 적기</button></div>')}${searchFeedbackHTML()}<div class="notice">이 목록은 수집된 연구 내용과 관심을 연결한 탐색 후보입니다. 현재 모집이나 참여 가능성을 보장하지 않아요. 자료 범위는 정제본에서 추천 가능으로 표시된 연구실 307곳입니다. 모든 교수진을 포함한다는 뜻은 아닙니다.</div>`;
}

function courseLinkHTML(course) {
  const l = course.link;
  if (!l) return `<div class="evidence"><span class="ev-kind">과목 소개</span>${(course.intro&&course.intro.length?course.intro:[course.evidence]).map(x=>`<p class="ev-snippet">${h(x)}</p>`).join('')}<p class="micro">과목 설명과 연구실 자료가 전체적으로 비슷하다는 자동 계산 결과예요. 실제로 이어지는지는 강의계획서에서 확인해 주세요.</p></div>`;
  return `<div class="evidence"><span class="ev-kind">이 과목에서</span><p class="ev-snippet">${marked(l.course_line, l.course_marks)}</p>${l.course_full?`<details class="ev-full"><summary>전체 보기</summary><p>${h(l.course_full)}</p></details>`:''}</div><div class="evidence"><span class="ev-kind">연구실 자료 · ${h(l.lab_kind)}</span><p class="ev-title">${h(l.lab_title)}</p>${l.lab_snippet?`<p class="ev-snippet">${marked(l.lab_snippet, l.lab_marks)}</p>`:''}${l.lab_full?`<details class="ev-full"><summary>전체 보기</summary><p>${h(l.lab_full)}</p></details>`:''}</div><p class="micro">겹치는 표현으로 찾은 연결이에요. 공식 선수과목은 아니에요.</p>`;
}
function courseItem(course) {
  return `<article class="course-item" data-course-search="${h([course.name,course.code,...(course.other_codes||[])].join(' ').toLowerCase())}"><label><input type="checkbox" data-course-id="${h(course.id)}" ${state.selected.has(course.id)?'checked':''}><div><span class="course-name">${h(course.name)}</span><span class="course-code">${h([course.code,...(course.other_codes||[])].join(' · '))}</span><p class="course-reason">${h(course.reason)}</p></div></label><details><summary>${course.link?'어떤 내용이 이어지나요?':'과목 소개 보기'}${course.quality_flags.includes('compound_course_code_not_split')?' · 복합 코드 확인 필요':''}</summary>${courseLinkHTML(course)}</details></article>`;
}
function researchSelectionHTML(papers) {
  if (!papers) return '';
  if (!papers.length) return '<div class="notice">이 연구실에서 선택할 논문 자료가 아직 없어요.</div>';
  return `<section class="research-papers"><h3>어떤 최근 연구가 궁금한가요?</h3><p class="micro">관심 논문을 최대 3편 선택해 주세요. 선택하지 않아도 계속할 수 있어요.</p><div class="course-list">${papers.map(p=>`<article class="course-item"><label><input type="checkbox" data-paper-id="${h(p.id)}" ${state.paperSelected.has(p.id)?'checked':''}><div><span class="course-name">${h(p.title)}</span><p class="micro">${h(p.year || '연도 미확인')}</p></div></label><details><summary>논문 내용 보기</summary><p>${h(p.abstract || '초록을 확보하지 못했어요.')}</p><a href="${h(p.url)}" target="_blank" rel="noopener noreferrer">논문 원문 확인 ↗</a></details></article>`).join('')}</div></section>`;
}
function researchResultHTML(research) {
  if (!research) return '';
  const chosen=research.selected.map(p=>`<li><a href="${h(p.url)}" target="_blank" rel="noopener noreferrer">${h(p.title)}</a> (${h(p.year || '연도 미확인')})</li>`).join('');
  const refs=research.references.map(p=>`<li><a href="${h(p.url)}" target="_blank" rel="noopener noreferrer">${h(p.title)}</a> (${h(p.year || '연도 미확인')}, 인용 ${h(p.cited_by_count)}회)</li>`).join('');
  const related=(research.related || []).map(p=>`<li><a href="${h(p.url)}" target="_blank" rel="noopener noreferrer">${h(p.title)}</a> (${h(p.year || '연도 미확인')})</li>`).join('');
  return `<section class="guide-column"><h3>선택한 연구와 참고 논문</h3>${chosen?`<ul>${chosen}</ul>`:'<p>선택한 논문이 없어요. 연구실의 연구 내용부터 살펴볼 수 있어요.</p>'}${research.unavailable?'<p>참고 논문을 지금 불러오지 못했어요. 잠시 후 다시 시도해 주세요.</p>':(refs?`<p>선택한 논문이 직접 인용한 논문 중 인용 수가 높은 후보예요. 연구의 기초 논문인지와 학습 적합성은 확인이 필요해요.</p><ul>${refs}</ul>`:(chosen?'<p>확인된 참고 논문이 없어요.</p>':''))}${related?`<p>같은 교수의 논문 중 제목 단어가 겹치는 연구예요. 연결은 원문을 확인해 주세요.</p><ul>${related}</ul>`:''}</section>`;
}
function renderDetail() {
  setView('detail'); const lab=state.lab;
  const concerns = lab.quality_flags.filter(f => !['collection_date_unknown','recruitment_status_unverified'].includes(f));
  main.innerHTML = `${pageTop(state.guide?3:2)}<div class="detail-layout"><aside class="lab-sidebar"><h2>${h(nameOf(lab))}</h2>${subtitleOf(lab)?`<p class="micro">${h(subtitleOf(lab))}</p>`:''}<p class="professor">${h(lab.department)}</p>${overviewHTML(lab,6,true)}${lab.overview?(lab.overview.classification.length?`<p class="micro">대표 논문의 OpenAlex 주제 분류</p>${tags(lab.overview.classification.map(label=>({label})))}`:''):tags(lab.topics.filter(t=>t.weight!=='secondary'))}<a class="small-link" href="${h(lab.url)}" target="_blank" rel="noopener noreferrer">홈페이지에서 더 알아보기 ↗</a>${platformSidebarHTML(lab)}<details><summary>연구 내용과 출처</summary>${evidence(lab.evidence)}</details><details><summary>추천을 읽기 전에</summary><p class="micro">현재 모집 여부와 연구실 분위기는 확인되지 않았어요. ${concerns.length ? '일부 자료는 내용이 부족하거나 추가 확인이 필요합니다.' : ''} 교수별 자료가 공동 홈페이지를 공유할 수 있어요.</p></details><p class="micro">${state.session.user?'로그인한 계정에 탐색을 이어갑니다.':'첫 연구실은 로그인 없이 끝까지 볼 수 있어요.'}</p></aside><section class="detail-main"><h2>이 연구실과 이어지는 과목</h2><p class="sub">수강한 과목에 표시하면 가이드에 반영돼요. 아직 수강한 과목이 없어도 가이드를 볼 수 있어요.</p>${researchSelectionHTML(lab.research_papers)}<div class="selection-head"><input id="course-filter" type="search" aria-label="연관 과목 찾기" placeholder="과목명·코드로 찾기"><span class="selection-count"><b id="selected-count">${state.selected.size}</b>개 수강 표시</span></div><p class="micro">연관 과목 ${lab.courses.length}개 · 공식 필수과목 목록이 아닙니다.</p><div class="course-list">${lab.courses.length ? lab.courses.map(courseItem).join('') : '<div class="empty"><p>보유한 자료에서 연관 과목을 찾지 못했어요. 수강 선택 없이 연구 내용부터 살펴볼 수 있습니다.</p></div>'}</div><p id="course-filter-empty" class="micro" hidden>조건에 맞는 과목이 없어요.</p><div class="selection-actions"><p>수강 여부로 실력이나 지원 자격을 판단하지 않아요.</p><button class="primary" data-action="guide">${state.guide?'선택한 과목으로 다시 보기':'나의 연구 가이드 보기'}</button></div><p id="dirty-notice" class="dirty-notice" hidden>수강 선택이 바뀌었어요. 가이드를 다시 확인해 주세요.</p><div id="guide-content">${state.guide?guideHTML(state.guide):''}</div><section class="save-panel"><h3>후보로 저장하기</h3><p>이 연구실이 마음에 드는 이유나 더 알아볼 점을 적어 두면 ‘나의 탐색’에서 다시 볼 수 있어요.</p><label for="note">메모<textarea id="note" maxlength="2000" placeholder="이 연구실이 궁금한 이유는…">${h(state.note)}</textarea></label><div class="save-actions"><button class="secondary" data-action="save">${state.saved?'메모 저장하기':'후보와 메모 저장'}</button><button class="text-button" data-action="results">다른 연구실도 알아보기</button></div></section>${communityHTML()}<section id="qna" class="community"></section></section></div>`;
  platformAfterDetail();
}
function topicHTML(topic) {
  return `<article class="topic-card"><span class="pill neutral">${h(topic.difficulty)}</span><h4>${h(topic.title)}</h4><p>${h(topic.basis)}</p><ol>${topic.steps.map(s=>`<li>${h(s)}</li>`).join('')}</ol>${topic.courses.length?`<div class="course-mini"><p>연결되는 학습 과목</p>${topic.courses.map(c=>`<span class="pill neutral">${h(c.name)}</span>`).join(' ')}</div>`:''}${topic.self_study?`<p>${h(topic.self_study)}</p>`:''}<details><summary>이 방향과 연결한 원문</summary>${evidence(topic.evidence)}</details></article>`;
}
function guideHTML(guide) {
  return `<section class="guide"><h2>연구 가이드</h2><div class="notice">${h(guide.notice)}</div>${researchResultHTML(guide.research)}${aiGuideHTML(guide)}<p class="micro">수강 표시: ${guide.selected_courses.length ? guide.selected_courses.map(c=>h(c.name)).join(' · ') : '없음 — 역량이 없다는 뜻은 아닙니다.'}</p>${guide.insufficient_evidence?'<div class="empty"><h3>구체적인 주제를 제안할 근거가 부족해요.</h3><p>연구실 원문과 관심 분야의 연결을 먼저 확인해 주세요. 자료에 없는 연구를 만들지는 않았습니다.</p></div>':`${guide.ai?.status==='done'?'<details class="basic-guide"><summary>기본 가이드 보기</summary>':''}<div class="guide-columns"><section class="guide-column"><h3>지금 시작할 탐색</h3>${guide.start_now.map(topicHTML).join('')}</section><section class="guide-column"><h3>더 준비하고 도전할 연구</h3>${guide.prepare_next.map(topicHTML).join('')}</section></div>${guide.ai?.status==='done'?'</details>':''}`}</section>`;
}

function scheduleDraft() {
  draftUnsaved = true;
  clearTimeout(draftTimer);
  draftTimer = setTimeout(() => {
    if (busy) { scheduleDraft(); return; }
    action(async () => { await persist(); });
  }, 650);
}
window.addEventListener('beforeunload', event => {
  if (draftUnsaved) { event.preventDefault(); event.returnValue = ''; }
});
async function persist(saved=state.saved) {
  if (state.view!=='detail' || !state.lab) return;
  clearTimeout(draftTimer);
  state.note = $('#note')?.value ?? state.note;
  const fingerprint = JSON.stringify([[...state.selected], state.note]);
  await api('save', {lab_id:state.lab.id, selected_ids:[...state.selected], note:state.note, saved});
  draftUnsaved = fingerprint !== JSON.stringify([[...state.selected], state.note]);
  if (draftUnsaved) scheduleDraft();
  state.saved = saved;
  await refreshSession();
}
async function openLab(id, saveCurrent=true, meta=null) {
  if (saveCurrent) await persist();
  try {
    const result=await api('explore',{lab_id:id,...(meta||{})});
    state.lab=result.lab; const existing=result.exploration;
    const offered=new Set(result.lab.courses.map(c=>c.id));
    state.selected=new Set((existing?.selected_ids || []).filter(id=>offered.has(id))); state.guide=existing?.guide || null; state.paperSelected=new Set((state.guide?.research?.selected || []).map(p=>p.id)); state.note=existing?.note || ''; state.saved=existing?.saved || false; state.dirty=false;
    if(existing?.stale_selection_dropped) toast(`이전에 표시한 수강 과목 ${existing.stale_selection_dropped}개는 현재 연관 과목 목록에 없어 해제했어요. 다시 확인해 주세요.`);
    state.community=await api(`community?lab_id=${encodeURIComponent(state.lab.id)}`);
    sessionStorage.setItem('curri-lab',state.lab.id); await refreshSession(); renderDetail();
  } catch(error) {
    if (error.code==='login_required') {if (!state.lab) renderHome();state.pendingLab=id;showAuth();} else throw error;
  }
}
async function showResults() {
  await persist();
  const profile=state.session.profile;
  if (!profile.interests) {renderHome();return;}
  await runSearch(profile); await refreshSession();renderResults();
}
async function renderSaved() {
  await persist(); await refreshSession();setView('saved');
  const records=state.session.explorations.filter(r=>r.saved && r.lab);
  main.innerHTML=`<div class="page-top"><button class="back" data-action="home">← 처음으로</button></div><section class="page-heading"><h1>나의 탐색</h1><p>저장한 연구실 후보와 메모예요. 다시 열어서 이어 볼 수 있어요.</p></section>${!state.session.user?'<div class="notice">이 브라우저의 비회원 세션에 저장되어 있어요. 로그인하면 계정으로 이어집니다. 쿠키를 지우면 비회원 기록에 다시 접근할 수 없어요.</div>':''}${records.length?`<div class="saved-grid">${records.map(r=>`<article class="saved-card"><h3>${h(nameOf(r.lab))}</h3><p class="micro">${h(r.lab.department)} · 수강 표시 ${r.selected_ids.length}개 · ${r.guide?'가이드 확인함':'가이드 보기 전'}</p><div class="note">${h(r.note || '아직 메모가 없어요.')}</div>${savedGuideHTML(r)}${r.previous_versions?.length?`<details><summary>이전 탐색 메모 ${r.previous_versions.length}개</summary>${r.previous_versions.map(v=>`<p class="micro">${h(v.note||'메모 없음')}</p>`).join('')}</details>`:''}<div class="actions"><button class="explore-button" data-action="explore" data-id="${h(r.lab_id)}">이어서 보기</button><button class="text-button" data-action="unsave" data-id="${h(r.lab_id)}">후보에서 빼기</button></div></article>`).join('')}</div>`:'<div class="empty"><h3>아직 저장한 후보가 없어요.</h3><p>연구실 상세 화면 아래의 ‘후보와 메모 저장’을 누르면 여기에 모여요.</p><button class="secondary" data-action="results">연구실 살펴보기</button></div>'}`;
}
function showAuth(register=false) { state.register=register; updateAuth();$('#auth-error').textContent='';$('#auth-dialog').showModal(); }
function updateAuth() {
  const fields=$('#register-fields');
  fields.innerHTML=state.register?accountFields({school:'POSTECH'},'',false)+consentHTML():'';fields.hidden=!state.register;
  if($('#forgot-link'))$('#forgot-link').hidden=state.register;
  $('#auth-dialog').classList.toggle('wide',state.register);
  $('#auth-submit').textContent=state.register?'계정 만들고 이어가기':'로그인하고 이어가기';
  $('#auth-title').textContent=state.register?'계정 만들기':'로그인';
  $('#auth-toggle').textContent=state.register?'이미 계정이 있나요? 로그인':'처음 오셨나요? 계정 만들기';
  $('#auth-form input[name=password]').autocomplete=state.register?'new-password':'current-password';
}
$('#auth-dialog').addEventListener('cancel',()=>{state.pendingLab=null;});
$('#auth-form').addEventListener('submit',event=>{
  // Read everything before action() disables the inputs (disabled fields are left out of FormData).
  event.preventDefault();const form=new FormData(event.target), account=state.register?readAccount(event.target):null, consents=state.register?readConsents(event.target):null;action(async()=>{
    $('#auth-error').textContent='';
    try {
      const credentials={email:form.get('email'),password:form.get('password')};
      if(account) {credentials.account=account;credentials.consents=consents;}
      state.session=await api(state.register?'register':'login',credentials);header();
      $('#auth-dialog').close();event.target.reset();
      const next=state.pendingLab;state.pendingLab=null;
      if(next) await openLab(next,false);
      else if(state.view==='saved') await renderSaved();
      else if(state.view==='detail') await openLab(state.lab.id,false);
      else if(['board','inbox','profile'].includes(state.view)) await showView(state.view);
      const carried=state.session.explorations.length>0;
      toast(state.register?`환영해요, ${state.session.user.nickname}님.${carried?' 첫 탐색을 계정으로 이어왔어요.':''}`:(carried?'첫 탐색을 그대로 이어왔어요. 이제 다른 연구실도 살펴보세요.':`${state.session.user.nickname||''}님, 다시 만나 반가워요.`));
    } catch(error) {$('#auth-error').textContent=error.message;}
  });
});
document.addEventListener('submit',event=>{
  if(communitySubmit(event))return;
  if(event.target.id!=='interest-form')return;
  event.preventDefault();const form=new FormData(event.target);
  action(async()=>{await runSearch({interests:form.get('interests'),goal:form.get('goal')});await refreshSession();renderResults();});
});
document.addEventListener('input',event=>{
  if(event.target.id==='lab-filter' || event.target.id==='course-filter'){
    const isLab=event.target.id==='lab-filter', query=event.target.value.trim().toLowerCase();let visible=0;
    document.querySelectorAll(isLab?'[data-search-text]':'[data-course-search]').forEach(row=>{const text=isLab?row.dataset.searchText:row.dataset.courseSearch;row.hidden=!text.includes(query);if(!row.hidden)visible++;});
    const empty=$(isLab?'#filter-empty':'#course-filter-empty');if(empty)empty.hidden=visible>0;
  }
  if(event.target.classList.contains('tag-filter')){
    const query=event.target.value.trim().toLowerCase();
    event.target.closest('.field').querySelectorAll('.tag-option').forEach(option=>{option.hidden=!option.dataset.label.includes(query);});
  }
  if(event.target.id==='board-filter')applyBoardFilter();
  if(event.target.id==='note'){state.note=event.target.value;scheduleDraft();}
});
document.addEventListener('change',event=>{
  if(event.target.id==='board-dept'){applyBoardFilter();return;}
  if(event.target.name==='mode'&&event.target.form?.id==='meeting-form'){const offline=event.target.value==='offline',place=$('#meeting-place');place.hidden=!offline;place.querySelector('input').required=offline;return;}
  if(event.target.name==='interest_tags'){const field=event.target.closest('.field');field.querySelector('.tag-count').textContent=field.querySelectorAll('[name=interest_tags]:checked').length;return;}
  const paper=event.target.dataset.paperId; if(paper){if(event.target.checked && state.paperSelected.size>=3){event.target.checked=false;toast('논문은 최대 3편까지 선택할 수 있어요.');return;} if(event.target.checked)state.paperSelected.add(paper);else state.paperSelected.delete(paper);if(state.guide){state.guide=null;$('#guide-content').innerHTML='';$('#dirty-notice').hidden=false;}return;}
  const id=event.target.dataset.courseId;if(!id)return;
  if(event.target.checked)state.selected.add(id);else state.selected.delete(id);
  $('#selected-count').textContent=state.selected.size;
  if(state.guide){state.guide=null;$('#guide-content').innerHTML='';$('#dirty-notice').hidden=false;}
  state.dirty=true; scheduleDraft();
});
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action]');if(!button || busy)return;
  const name=button.dataset.action;
  if(platformClick(name,button))return;
  if(name.startsWith('mirror-')){mirrorAction(name,button);return;}
  if(name==='example'){$('#interests').value=button.dataset.value;$('#interests').focus();return;}
  if(name==='toggle-auth'){state.register=!state.register;updateAuth();return;}
  if(name==='close-auth'){$('#auth-dialog').close();state.pendingLab=null;return;}
  if(name==='close-sheet'){$('#sheet-dialog').close();return;}
  if(name==='board-lab'){state.boardLab=state.boardLab===button.dataset.id?'':button.dataset.id;applyBoardFilter();return;}
  if(name==='write-review'){openReviewForm();return;}
  if(name==='contact'){openContact(Number(button.dataset.id));return;}
  if(name==='meeting-new'){openMeetingForm();return;}
  action(async()=>{
    if(name==='home'){await persist();renderHome();}
    else if(name==='results')await showResults();
    else if(name==='explore')await openLab(button.dataset.id,true,button.dataset.rank!==undefined?{rank:Number(button.dataset.rank),from:state.view}:null);
    else if(name==='saved')await renderSaved();
    else if(name==='account'){
      if($('#sheet-dialog').open)$('#sheet-dialog').close();
      await persist();
      if(state.session?.user) await showView('profile');
      else showAuth();
    }
    else if(name==='logout'){state.session=await api('logout',{});header();state.lab=null;state.guide=null;state.thread=null;sessionStorage.removeItem('curri-lab');renderHome();toast('로그아웃했어요. 계정의 저장 내용은 유지됩니다.');}
    else if(name==='board'||name==='inbox'){await persist();await showView(name);}
    else if(name==='open-thread'){state.thread=Number(button.dataset.id);await renderInbox();}
    else if(name==='inbox-list'){state.thread=null;await renderInbox();}
    else if(name==='meeting-cancel'){
      if(!confirm('이 만남 약속을 취소할까요? 상대방에게 쪽지로 알려요.'))return;
      await api('meeting/cancel',{meeting_id:Number(button.dataset.id)});await renderInbox();toast('만남 약속을 취소했어요.');
    }
    else if(name==='delete-review'){
      if(!confirm('이 연구실에 남긴 후기를 삭제할까요?'))return;
      state.community=await api('review/delete',{lab_id:state.lab.id});refreshCommunity();toast('후기를 삭제했어요.');
    }
    else if(name==='guide'){
      await persist();state.guide=(await api('guide',{lab_id:state.lab.id,selected_ids:[...state.selected],paper_ids:[...state.paperSelected]})).guide;state.dirty=false;await refreshSession();renderDetail();$('#guide-content').scrollIntoView({behavior:'smooth',block:'start'});
    }
    else if(name==='save'){await persist(true);button.textContent='메모 저장하기';toast('후보와 메모를 저장했어요. 나의 탐색에서 다시 볼 수 있어요.');askService('save');}
    else if(name==='unsave'){
      const record=state.session.explorations.find(r=>r.lab_id===button.dataset.id);
      await api('save',{lab_id:record.lab_id,selected_ids:record.selected_ids,note:record.note,saved:false});await renderSaved();
    }
    else if(name==='retry')await boot();
  });
});
// ---- Community: personal profile, research-participation reviews, graduate contact ----
const DEPARTMENTS = ['수학과','물리학과','화학과','생명과학과','신소재공학과','기계공학과','산업경영공학과','전자전기공학과','컴퓨터공학과','화학공학과','IT융합공학과','반도체공학과','기타'];
const GRADES = ['1학년','2학년','3학년','4학년','5학년 이상','휴학·기타'];
const GOAL_LABELS = {explore:'아직 알아보는 중', research:'연구참여', graduate:'연구실 진학'};
function stars(value) { const n=Math.round(value||0); return `<span class="stars" aria-label="5점 중 ${h(value)}점">${'★'.repeat(n)}<span class="stars-off">${'★'.repeat(5-n)}</span></span>`; }
function monthOf(ts) { const d=new Date(ts*1000); return `${d.getFullYear()}.${String(d.getMonth()+1).padStart(2,'0')}`; }
function timeOf(ts) { return new Date(ts*1000).toLocaleString('ko-KR',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}); }
function options(list, selected) { return '<option value="">선택 안 함</option>'+list.map(v=>`<option ${v===selected?'selected':''}>${h(v)}</option>`).join(''); }

function accountFields(a, nickname, openOptional=true) {
  const tags=new Set(a.interest_tags||[]);
  const ordered=[...state.concepts].sort((x,y)=>tags.has(y.id)-tags.has(x.id));
  return `<fieldset class="form-section"><legend>필수 정보</legend><div class="form-grid"><label>이름(실명)<input name="real_name" required minlength="2" maxlength="40" autocomplete="name" value="${h(a.real_name)}"></label><label>별명 <small>서비스에서 보이는 이름</small><input name="nickname" required minlength="2" maxlength="20" pattern="[^\\s@&lt;&gt;]+" title="공백, @, &lt;, &gt; 없이 2~20자" value="${h(nickname)}" placeholder="예: 지곡동다람쥐"></label></div><label>학교<input name="school" required minlength="2" maxlength="60" autocomplete="organization" value="${h(a.school)}"></label><div class="field"><span class="field-label">관심 분야 <small>태그 1개 이상 또는 직접 입력 · <b class="tag-count">${tags.size}</b>개 선택</small></span><input type="search" class="tag-filter" aria-label="관심 분야 태그 찾기" placeholder="태그 찾기: 로봇, 반도체, 추천…"><div class="tag-picker">${ordered.map(c=>`<label class="tag-option" data-label="${h(c.ko.toLowerCase())}"><input type="checkbox" name="interest_tags" value="${h(c.id)}" ${tags.has(c.id)?'checked':''}><span>${h(c.ko)}</span></label>`).join('')}</div><label class="sub-label">직접 입력<input name="interest_text" maxlength="300" value="${h(a.interest_text)}" placeholder="태그에 없는 관심을 자유롭게 적어 주세요"></label></div></fieldset><details class="optional" ${openOptional?'open':''}><summary>더 알려주기 <small>선택 · 선배에게 연락할 때 함께 전달돼요</small></summary><div class="form-grid"><label>학과<select name="department">${options(DEPARTMENTS,a.department)}</select></label><label>복수전공·부전공<select name="second_major">${options(DEPARTMENTS,a.second_major)}</select></label><label>학년<select name="grade">${options(GRADES,a.grade)}</select></label><label>연구참여 목표<select name="goal"><option value="">선택 안 함</option>${Object.entries(GOAL_LABELS).map(([v,l])=>`<option value="${v}" ${a.goal===v?'selected':''}>${l}</option>`).join('')}</select></label></div><label>희망 시기<input name="timing" maxlength="60" value="${h(a.timing)}" placeholder="예: 2027 겨울방학부터"></label><label>한 줄 소개<input name="headline" maxlength="80" value="${h(a.headline)}" placeholder="예: 센서 데이터로 세상을 이해하고 싶은 3학년"></label><label>자기소개 · 하고 싶은 말<textarea name="intro" maxlength="1500" placeholder="관심을 갖게 된 계기, 해본 프로젝트, 선배에게 하고 싶은 말 등 자유롭게 적어 주세요.">${h(a.intro)}</textarea></label></details>`;
}
function readAccount(form) {
  const data=new FormData(form), out={interest_tags:data.getAll('interest_tags')};
  for (const key of ['real_name','nickname','school','interest_text','department','second_major','grade','goal','timing','headline','intro']) out[key]=data.get(key)||'';
  return out;
}

async function showView(view) {
  await persist();
  if (view==='board') await renderBoard();
  else if (!state.session?.user) { renderHome(); showAuth(); }
  else if (view==='inbox') await renderInbox();
  else await renderProfile();
}
async function renderProfile() {
  await refreshSession(); const user=state.session.user;
  if (!user) { renderHome(); showAuth(); return; }
  setView('profile'); const a=user.account||{};
  main.innerHTML=`<section class="page-heading"><h1>내 프로필</h1><p>후기에는 별명과 학과·학년만 보여요. 선배에게 쪽지를 보내면 이름·이메일과 아래 프로필이 그 선배에게 함께 전달돼요.</p></section>${user.profile_complete?'':'<div class="notice strong">필수 항목(이름·별명·학교·관심 분야)을 채우면 연구참여 후기 작성과 선배 연락을 할 수 있어요.</div>'}${user.role==='graduate'?`<div class="notice">연구실 선배 계정이에요 · ${h(a.program)} · ${h(a.research)}<br>연구실 상세의 선배 소개에는 이름·과정·연구 분야·한 줄 소개와, 로그인한 사용자에게만 이메일이 보여요.</div>`:''}<form id="profile-form" class="profile-form"><label>이메일 <small>로그인에 쓰는 주소는 바꿀 수 없어요</small><input value="${h(user.email)}" disabled></label>${accountFields(a,user.nickname||'',true)}<div class="profile-actions"><button type="submit" class="primary">프로필 저장</button><button type="button" class="text-button" data-action="logout">로그아웃</button></div></form>${platformProfileHTML(user)}`;
}

function reviewCard(r, withLab=false) {
  const labels=state.community?.rating_labels||state.board?.rating_labels||{};
  const values=Object.values(r.ratings), avg=values.reduce((a,b)=>a+b,0)/values.length;
  const who=[r.author.department,r.author.grade].filter(Boolean).join(' ');
  const attrs=withLab?`data-review-lab="${h(r.lab_id)}" data-dept="${h(r.lab.department)}" data-search-text="${h((nameOf(r.lab)+' '+r.lab.department+' '+r.activity+' '+r.good+' '+r.recommend_for).toLowerCase())}"`:'';
  return `<article class="review-card" ${attrs}><div class="review-head"><div><b>${h(r.author.nickname)}</b>${who?`<span class="micro"> · ${h(who)}</span>`:''}</div><span class="review-score">${stars(avg)} ${avg.toFixed(1)}</span></div>${withLab?`<p class="review-lab">${h(nameOf(r.lab))} <span>${h(r.lab.department)}</span></p>`:''}<div class="tag-list"><span class="pill neutral">${h(r.term)}</span><span class="pill neutral">${h(r.duration)}</span><span class="pill">연구참여 완료 · 자기 신고</span></div><dl class="review-ratings">${Object.entries(labels).map(([k,l])=>`<div><dt>${h(l)}</dt><dd>${stars(r.ratings[k])}</dd></div>`).join('')}</dl><div class="review-body"><h5>했던 일</h5><p>${h(r.activity)}</p><h5>좋았던 점</h5><p>${h(r.good)}</p>${r.improve?`<h5>아쉬운 점</h5><p>${h(r.improve)}</p>`:''}${r.recommend_for?`<h5>이런 학생에게 추천해요</h5><p>${h(r.recommend_for)}</p>`:''}</div><div class="review-foot"><span class="micro">${monthOf(r.created)} 작성</span>${r.mine&&!withLab?'<span><button class="text-button" data-action="write-review">수정</button> · <button class="text-button" data-action="delete-review">삭제</button></span>':''}${withLab?`<button class="explore-button" data-action="explore" data-id="${h(r.lab_id)}">이 연구실 알아보기</button>`:''}${reviewReportHTML(r)}</div></article>`;
}
function seniorCard(g) {
  const action=seniorActionHTML(g);
  return `<article class="senior-card"><div class="avatar" aria-hidden="true">${h(g.name.slice(0,1))}</div><div class="senior-info"><h4>${h(g.name)} <span>${h(g.program)}</span></h4><p class="research">${h(g.research)}</p>${g.interests.length?`<div class="tag-list">${g.interests.map(t=>`<span class="pill neutral">${h(t)}</span>`).join('')}</div>`:''}${g.headline?`<p class="headline">“${h(g.headline)}”</p>`:''}${seniorExtraHTML(g)}<p class="micro email">${g.email?h(g.email):(state.session?.user?'이메일 비공개 · 커피챗으로 연락해요':'이메일은 로그인 후 확인')}</p>${action}</div></article>`;
}
function communityHTML() {
  const c=state.community;
  if (!c || c.lab_id!==state.lab?.id) return '<section id="community" class="community"></section>';
  const s=c.summary;
  const write=c.viewer.role==='graduate'?'':`<button class="secondary" data-action="write-review">${c.my_review?'내 후기 수정하기':'후기 남기기'}</button>`;
  const summary=s.count?`<div class="review-summary"><div class="overall"><b>${s.overall.toFixed(1)}</b>${stars(s.overall)}<span class="micro">후기 ${s.count}개 평균</span></div><dl class="review-ratings">${Object.entries(c.rating_labels).map(([k,l])=>`<div><dt>${h(l)}</dt><dd>${stars(s.averages[k])} <span class="micro">${s.averages[k].toFixed(1)}</span></dd></div>`).join('')}</dl></div><div class="review-list">${c.reviews.map(r=>reviewCard(r)).join('')}</div>`:'<div class="empty small"><p>아직 이 연구실의 연구참여 후기가 없어요. 참여를 마쳤다면 첫 후기를 남겨 주세요.</p></div>';
  const seniors=c.graduates.length?`<div class="senior-grid">${c.graduates.map(seniorCard).join('')}</div>`:'<div class="empty small"><p>아직 연락을 허락한 선배가 없어요. 연구실 홈페이지의 연락처를 확인해 보세요.</p></div>';
  return `<section id="community" class="community"><h2>선배와 연구참여 후기</h2><p class="sub">이 연구실에서 연구참여를 마친 학부생의 후기와, 연락을 허락한 재학 중인 선배예요.</p><div class="community-block"><div class="block-head"><h3>재학 중인 선배 <span class="count">${c.graduates.length}</span></h3></div>${seniors}</div><div class="community-block"><div class="block-head"><h3>연구참여 후기 <span class="count">${s.count}</span></h3>${write}</div>${summary}</div><p class="micro">후기는 참여한 학생의 자기 신고 경험이며 연구실의 공식 정보나 현재 모집 여부가 아니에요. 선배 정보는 본인이 공개에 동의한 내용만 보여요.</p></section>`;
}
function refreshCommunity() { const section=$('#community'); if (section) section.outerHTML=communityHTML(); }

function openSheet(html) { $('#sheet-body').innerHTML=html; $('#sheet-dialog').showModal(); }
function requireMember(purpose) {
  const user=state.session?.user;
  if (!user) { toast(`${purpose} 로그인해 주세요.`); showAuth(); return false; }
  if (!user.profile_complete) { toast('필수 프로필(이름·별명·학교·관심 분야)을 먼저 완성해 주세요.'); action(()=>showView('profile')); return false; }
  return true;
}
function openReviewForm() {
  if (!requireMember('후기를 남기려면')) return;
  if (state.session.user.role==='graduate') { toast('선배 계정은 연구참여 후기를 작성할 수 없어요.'); return; }
  const r=state.community.my_review, labels=state.community.rating_labels;
  const ratings=Object.entries(labels).map(([k,l])=>`<div class="rating-row"><span>${h(l)}${k==='workload'?' <small>5 = 적절했어요</small>':''}</span><div class="rating-input">${[1,2,3,4,5].map(v=>`<label><input type="radio" name="rating-${k}" value="${v}" required ${r?.ratings[k]===v?'checked':''}><span>${v}</span></label>`).join('')}</div></div>`).join('');
  openSheet(`<h2 id="sheet-title">연구참여 후기</h2><p class="sheet-sub">${h(nameOf(state.lab))} · ${h(state.lab.department)}</p><form id="review-form"><label class="check"><input type="checkbox" name="completed" required ${r?'checked':''}><span>이 연구실에서 학부생 연구참여를 마쳤어요.</span></label><div class="form-grid"><label>참여 시기<input name="term" required minlength="2" maxlength="40" value="${h(r?.term)}" placeholder="예: 2025 여름방학"></label><label>참여 기간<input name="duration" required maxlength="40" value="${h(r?.duration)}" placeholder="예: 8주, 한 학기"></label></div><fieldset class="rating-set"><legend>항목별 평가 <small>1 아쉬웠어요 · 5 아주 좋았어요</small></legend>${ratings}</fieldset><label>했던 일<textarea name="activity" required minlength="10" maxlength="800" placeholder="맡았던 일, 세미나·미팅 방식 등">${h(r?.activity)}</textarea></label><label>좋았던 점<textarea name="good" required minlength="10" maxlength="1500">${h(r?.good)}</textarea></label><label>아쉬운 점 <small>선택</small><textarea name="improve" maxlength="1500" placeholder="다음 참여자가 미리 알면 좋을 점">${h(r?.improve)}</textarea></label><label>이런 학생에게 추천해요 <small>선택</small><input name="recommend_for" maxlength="300" value="${h(r?.recommend_for)}"></label><p class="micro">후기에는 별명과 학과·학년만 표시돼요. 실명과 이메일은 공개되지 않아요.</p><p id="sheet-error" class="error" role="alert"></p><button class="primary full" type="submit">${r?'후기 수정하기':'후기 등록하기'}</button></form>`);
}
function openContact(id) {
  if (!requireMember('선배에게 연락하려면')) return;
  const g=state.community.graduates.find(x=>x.id===id); if (!g) return;
  const user=state.session.user, a=user.account;
  const greeting=`안녕하세요, ${g.name} 선배님. ${[a.department,a.grade,user.nickname].filter(Boolean).join(' ')}입니다. 3분커리에서 연구실을 알아보다 연락드려요.\n\n`;
  openSheet(`<h2 id="sheet-title">${h(g.name)} 선배에게 쪽지</h2><p class="sheet-sub">${h(nameOf(state.lab))} · ${h(g.program)} · ${h(g.research)}</p><form id="contact-form" data-id="${g.id}"><label>제목<input name="subject" required minlength="2" maxlength="80" value="${h((g.research.split(' · ')[0]||'연구실')+' 연구참여 관련 질문')}"></label><label>내용<textarea name="body" required minlength="10" maxlength="2000" placeholder="간단한 자기소개와 궁금한 점을 구체적으로 적으면 답장받기 쉬워요.">${h(greeting)}</textarea></label><div class="share-preview"><p class="micro">쪽지와 함께 선배에게 전달되는 내 정보</p><p><b>${h(a.real_name)}</b> (${h(user.nickname)}) · ${h(user.email)}<br>${h([a.school,a.department,a.grade].filter(Boolean).join(' · '))}${a.headline?`<br>“${h(a.headline)}”`:''}</p><button type="button" class="text-button" data-action="account">프로필 수정하기</button></div><p class="micro">선배는 연구 일정에 따라 답장이 늦거나 어려울 수 있어요. 답장은 쪽지함에서 확인할 수 있어요.</p><p id="sheet-error" class="error" role="alert"></p><button class="primary full" type="submit">쪽지 보내기</button></form>`);
}

async function renderBoard() {
  state.board=await api('reviews'); state.boardLab=''; setView('board');
  const b=state.board, depts=[...new Set(b.reviews.map(r=>r.lab.department))].sort();
  main.innerHTML=`<section class="page-heading"><h1>연구참여 후기</h1><p>학부생 연구참여를 마친 학생들이 남긴 후기예요. 연구실을 고를 때 함께 참고해 보세요.</p></section>${b.labs.length?`<div class="board-labs" aria-label="후기가 있는 연구실">${b.labs.map(l=>`<button class="lab-chip" data-action="board-lab" data-id="${h(l.lab.id)}" aria-pressed="false"><b>${h(nameOf(l.lab))}</b><span>${stars(l.overall)} ${l.overall.toFixed(1)} · ${l.count}개</span></button>`).join('')}</div>`:''}<div class="results-toolbar"><p>후기 <strong id="board-count">${b.reviews.length}</strong>개 · 연구실 ${b.labs.length}곳</p><div class="board-filters"><select id="board-dept" aria-label="학과로 좁히기"><option value="">전체 학과</option>${depts.map(d=>`<option>${h(d)}</option>`).join('')}</select><input id="board-filter" type="search" aria-label="후기 검색" placeholder="교수명·연구 내용으로 찾기"></div></div>${b.reviews.length?`<div class="review-grid">${b.reviews.map(r=>reviewCard(r,true)).join('')}</div><p id="board-empty" class="notice" hidden>조건에 맞는 후기가 없어요.</p>`:'<div class="empty"><h3>아직 남겨진 후기가 없어요.</h3><p>연구참여를 마쳤다면 연구실 상세 화면에서 첫 후기를 남겨 주세요.</p></div>'}<div class="notice">후기는 참여한 학생의 자기 신고 경험이며 연구실의 공식 정보나 현재 모집 여부가 아니에요. 시기와 사람에 따라 경험은 다를 수 있어요.</div>`;
}
function applyBoardFilter() {
  const query=($('#board-filter')?.value||'').trim().toLowerCase(), dept=$('#board-dept')?.value||''; let visible=0;
  document.querySelectorAll('[data-review-lab]').forEach(card=>{card.hidden=!(card.dataset.searchText.includes(query)&&(!dept||card.dataset.dept===dept)&&(!state.boardLab||card.dataset.reviewLab===state.boardLab));if(!card.hidden)visible++;});
  document.querySelectorAll('.lab-chip').forEach(chip=>chip.setAttribute('aria-pressed',String(chip.dataset.id===state.boardLab)));
  if ($('#board-count')) $('#board-count').textContent=visible;
  if ($('#board-empty')) $('#board-empty').hidden=visible>0;
}

function threadItem(t, active) {
  const o=t.other, title=o.nickname?`${h(o.nickname)} <span>${h(o.name)}</span>`:`${h(o.name)} <span>선배</span>`;
  const sub=o.nickname?[o.department,o.grade].filter(Boolean).join(' '):(t.lab?nameOf(t.lab):o.program);
  return `<button class="thread-item ${t.id===active?'active':''}" data-action="open-thread" data-id="${t.id}"><span class="thread-title"><b>${title}</b>${t.unread?`<span class="badge" aria-label="안 읽은 쪽지">${t.unread}</span>`:''}</span><span class="micro">${h(sub)}</span><span class="thread-subject">${h(t.subject)}</span><span class="thread-preview">${t.last?.mine?'나: ':''}${h(t.last?.body)}</span><span class="micro">${t.last?timeOf(t.last.created):''}</span></button>`;
}
const MEETING_MODES={online:'온라인',offline:'대면'}, MEETING_LINKS={google:'Google Meet',zoom:'Zoom',manual:'화상회의'};
function whenOf(ts) { return new Date(ts*1000).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',month:'long',day:'numeric',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}); }
function linkLabel(m) {
  if (m.provider!=='manual') return MEETING_LINKS[m.provider]||'화상회의';
  const host=new URL(m.join_url).hostname;
  return host==='meet.google.com'?'Google Meet':host==='zoom.us'||host.endsWith('.zoom.us')?'Zoom':'화상회의';
}
function kstInput(ms) { return new Date(ms).toLocaleString('sv-SE',{timeZone:'Asia/Seoul'}).replace(' ','T').slice(0,16); }
function meetingHTML(t) {
  const m=t.meetings.find(x=>x.can_cancel), auto=t.meeting_link;
  if (!m) return `<div class="meeting-panel"><div><b>만남 약속</b><p class="micro">대면 또는 온라인으로 만날 시간을 제안해 보세요.${auto?` 온라인 만남은 확정되면 ${h(auto.label)} 링크가 자동으로 만들어져요.`:''}</p></div><button class="secondary" data-action="meeting-new">만남 약속 잡기</button></div>`;
  const where=`${MEETING_MODES[m.mode]} ${m.minutes}분${m.place?` · ${h(m.place)}`:''}`;
  if (m.status==='confirmed') return `<div class="meeting-panel confirmed"><div><span class="pill">약속 확정</span><p class="meeting-when"><b>${h(whenOf(m.start))}</b> · ${where}</p>${m.join_url?`<p class="meeting-link"><a class="secondary" href="${h(m.join_url)}" target="_blank" rel="noopener noreferrer">${h(linkLabel(m))} 입장하기 ↗</a><span class="micro">${h(m.join_url)}</span></p>`:''}</div><button class="text-button" data-action="meeting-cancel" data-id="${m.id}">약속 취소</button></div>`;
  const slots=m.slots.map((ts,i)=>m.can_confirm?`<label class="check"><input type="radio" name="start" value="${ts}" required ${i===0?'checked':''}><span>${h(whenOf(ts))}</span></label>`:`<li>${h(whenOf(ts))}</li>`).join('');
  if (!m.can_confirm) return `<div class="meeting-panel"><div><span class="pill neutral">상대방의 확정 대기</span><p class="meeting-when">${where}</p><ul class="meeting-slots">${slots}</ul></div><button class="text-button" data-action="meeting-cancel" data-id="${m.id}">요청 취소</button></div>`;
  const link=m.mode!=='online'?'':auto?`<label>화상회의 링크 <small>선택 · 비워 두면 ${h(auto.label)} 링크를 자동으로 만들어요</small><input name="join_url" type="url" maxlength="500" placeholder="https://"></label>`:`<label>화상회의 링크 <small>Google Meet·Zoom 등에서 만든 링크</small><input name="join_url" type="url" required maxlength="500" placeholder="https://meet.google.com/..."></label>`;
  return `<form id="meeting-confirm-form" class="meeting-panel request" data-id="${m.id}"><div><span class="pill">만남 요청이 왔어요</span><p class="meeting-when">${where}</p>${m.note?`<p class="micro">“${h(m.note)}”</p>`:''}<fieldset class="meeting-slots"><legend>가능한 시간을 골라 확정해 주세요</legend>${slots}</fieldset>${link}</div><div class="meeting-actions"><button class="primary" type="submit">이 시간으로 확정</button><button type="button" class="text-button" data-action="meeting-cancel" data-id="${m.id}">어려워요</button></div></form>`;
}
function openMeetingForm() {
  const t=state.threadData; if (!t) return;
  const min=kstInput(Date.now()+3600e3), max=kstInput(Date.now()+60*86400e3), auto=t.meeting_link;
  const slot=(n)=>`<label>${n===1?'첫 번째 후보':`${n===2?'두':'세'} 번째 후보 <small>선택</small>`}<input name="slot" type="datetime-local" min="${min}" max="${max}" ${n===1?'required':''}></label>`;
  openSheet(`<h2 id="sheet-title">만남 약속 잡기</h2><p class="sheet-sub">${h(t.other.nickname||`${t.other.name} 선배`)}에게 가능한 시간을 최대 3개 제안해요. 상대방이 하나를 골라야 확정돼요.</p><form id="meeting-form"><fieldset class="meeting-mode"><legend>만나는 방식</legend><label class="check"><input type="radio" name="mode" value="online" checked><span>온라인 <small>${auto?`확정 시 ${h(auto.label)} 링크 자동 생성`:'확정하는 사람이 화상회의 링크 입력'}</small></span></label><label class="check"><input type="radio" name="mode" value="offline"><span>대면</span></label></fieldset><label id="meeting-place" hidden>만날 장소<input name="place" maxlength="100" placeholder="예: 학생회관 1층 카페"></label><label>만남 시간<select name="minutes"><option value="20">20분</option><option value="30">30분</option></select></label><div class="form-grid">${slot(1)}${slot(2)}</div>${slot(3)}<label>전달할 말 <small>선택</small><textarea name="note" maxlength="500" placeholder="미리 묻고 싶은 질문이 있다면 적어 주세요."></textarea></label><p class="micro">시간은 한국 시간 기준이에요.${auto?` 온라인 만남이 확정되면 링크가 쪽지함에 표시되고, 두 사람의 이메일이 일정 참석자로 등록돼요.`:''}</p><p id="sheet-error" class="error" role="alert"></p><button class="primary full" type="submit">만남 요청 보내기</button></form>`);
}
function threadHTML(t) {
  const o=t.other, graduate=t.role==='graduate';
  const profile=graduate?`<details class="sender-profile" open><summary>보낸 학생의 프로필</summary><dl>${[['이름',o.name],['별명',o.nickname],['이메일',o.email],['학교',o.school],['학과',[o.department,o.second_major&&`복수전공 ${o.second_major}`].filter(Boolean).join(' · ')],['학년',o.grade],['목표',o.goal],['희망 시기',o.timing],['한 줄 소개',o.headline],['관심 분야',[...o.interests,o.interest_text].filter(Boolean).join(', ')],['자기소개',o.intro]].filter(([,v])=>v).map(([k,v])=>`<div><dt>${k}</dt><dd>${h(v)}</dd></div>`).join('')}</dl></details>`:`<p class="thread-contact"><b>${h(o.name)} 선배</b> · ${h(o.program)} · ${h(o.research)}<br><span class="micro">${h(o.email)}</span></p>`;
  return `<header class="thread-head"><button class="back mobile-only" data-action="inbox-list">← 대화 목록</button><h2>${h(t.subject)}</h2>${t.lab?`<p class="micro">${h(nameOf(t.lab))} · ${h(t.lab.department)}</p>`:''}${profile}${threadToolsHTML(t)}</header>${meetingFeedbackHTML(t)}${meetingHTML(t)}<div class="messages">${t.messages.map(m=>`<div class="message ${m.mine?'mine':''}"><p>${h(m.body)}</p><span class="micro">${m.mine?'나':h(graduate?o.nickname:o.name)} · ${timeOf(m.created)}</span></div>`).join('')}</div><form id="reply-form" data-id="${t.id}" class="reply-form"><textarea name="body" required maxlength="2000" aria-label="답장" placeholder="${graduate?'후배에게 답장하기':'선배에게 답장하기'}"></textarea><button class="primary" type="submit">보내기</button></form>`;
}
async function renderInbox() {
  await persist();
  if (!state.session?.user) { renderHome(); showAuth(); return; }
  const box=await api('inbox');
  state.pendingMeetings=(await api('feedback/pending').catch(()=>({meetings:[]}))).meetings;
  if (!box.threads.some(t=>t.id===state.thread)) state.thread=null;
  if (!state.thread && box.threads.length && window.innerWidth>850) state.thread=box.threads[0].id;
  const thread=state.thread?await api(`thread?id=${state.thread}`):null;
  state.threadData=thread;
  if (thread) box.threads.forEach(t=>{ if (t.id===thread.id) t.unread=0; });
  await refreshSession(); setView('inbox');
  const graduate=box.role==='graduate';
  main.innerHTML=`<section class="page-heading"><h1>쪽지함</h1><p>${graduate?'연구실을 알아보는 후배들이 보낸 쪽지예요. 보낸 학생의 프로필을 함께 확인할 수 있어요.':'선배와 나눈 대화예요. 연구실 상세의 ‘재학 중인 선배’에서 새 쪽지를 보낼 수 있어요.'}</p></section>${box.threads.length?`<div class="inbox-layout ${thread?'has-thread':''}"><aside class="thread-list" aria-label="대화 목록">${box.threads.map(t=>threadItem(t,thread?.id)).join('')}</aside><section class="thread-view">${thread?threadHTML(thread):'<div class="empty small"><p>대화를 선택해 주세요.</p></div>'}</section></div>`:`<div class="empty"><h3>아직 주고받은 쪽지가 없어요.</h3><p>${graduate?'후배가 쪽지를 보내면 여기에 표시돼요.':'연구실 상세 화면의 ‘재학 중인 선배’에서 쪽지를 보내 보세요.'}</p>${graduate?'':'<button class="secondary" data-action="results">연구실 살펴보기</button>'}</div>`}`;
  const messages=$('.messages'); if (messages) messages.scrollTop=messages.scrollHeight;
}

function communitySubmit(event) {
  if (platformSubmit(event)) return true;
  const form=event.target, id=form.id;
  if (!['profile-form','review-form','contact-form','reply-form','meeting-form','meeting-confirm-form'].includes(id)) return false;
  event.preventDefault(); const data=new FormData(form), account=id==='profile-form'?readAccount(form):null;
  action(async()=>{
    try {
      if (id==='profile-form') { state.session=await api('account',account); header(); await renderProfile(); toast('프로필을 저장했어요.'); }
      else if (id==='review-form') {
        const ratings=Object.fromEntries(Object.keys(state.community.rating_labels).map(k=>[k,Number(data.get(`rating-${k}`))]));
        state.community=await api('review',{lab_id:state.lab.id,completed:data.get('completed')==='on',term:data.get('term'),duration:data.get('duration'),activity:data.get('activity'),good:data.get('good'),improve:data.get('improve'),recommend_for:data.get('recommend_for'),ratings});
        $('#sheet-dialog').close(); refreshCommunity(); toast('후기를 남겼어요. 다음 학생에게 큰 도움이 될 거예요.');
      }
      else if (id==='contact-form') {
        await api('contact',{graduate_id:Number(form.dataset.id),subject:data.get('subject'),body:data.get('body')});
        state.community=await api(`community?lab_id=${encodeURIComponent(state.lab.id)}`);
        $('#sheet-dialog').close(); refreshCommunity(); toast('쪽지를 보냈어요. 답장은 쪽지함에서 확인할 수 있어요.');
      }
      else if (id==='meeting-form') {
        const slots=data.getAll('slot').filter(Boolean);
        await api('meeting/request',{thread_id:state.thread,mode:data.get('mode'),minutes:Number(data.get('minutes')),slots,place:data.get('place')||'',note:data.get('note')});
        $('#sheet-dialog').close(); await renderInbox(); toast('만남을 요청했어요. 상대방이 시간을 고르면 약속이 확정돼요.');
      }
      else if (id==='meeting-confirm-form') {
        const t=await api('meeting/confirm',{meeting_id:Number(form.dataset.id),start:Number(data.get('start')),join_url:data.get('join_url')||''});
        await renderInbox(); const m=t.meetings[0]; toast(m?.join_url?'약속을 확정했어요. 화상회의 링크가 준비됐어요.':'약속을 확정했어요.');
      }
      else { state.thread=Number(form.dataset.id); await api('reply',{thread_id:state.thread,body:data.get('body')}); await renderInbox(); }
    } catch (error) {
      if (error.code==='login_required') { $('#sheet-dialog').close(); showAuth(); }
      else if (error.code==='profile_required') { $('#sheet-dialog').close(); toast(error.message); await renderProfile(); }
      else if ($('#sheet-dialog').open) $('#sheet-error').textContent=error.message;
      else throw error;
    }
  });
  return true;
}

async function restoreView(entry) {
  if (await restorePlatformView(entry.view)) return;
  if (entry.view==='detail' && entry.lab) await openLab(entry.lab);
  else if (entry.view==='results' && state.results.length) { await persist(); renderResults(); }
  else if (entry.view==='results' && state.session.profile.interests) await showResults();
  else if (entry.view==='saved') await renderSaved();
  else if (['board','inbox','profile'].includes(entry.view)) await showView(entry.view);
  else { await persist(); renderHome(); }
}
window.addEventListener('popstate', event => {
  if (!event.state || busy) return;
  for (const dialog of ['#sheet-dialog','#auth-dialog']) if ($(dialog).open) $(dialog).close();
  restoring = true;
  action(async()=>{ try { await restoreView(event.state); } finally { restoring = false; } });
});
async function boot() {
  await refreshSession();
  state.concepts=(await api('concepts')).concepts;
  if (await routeFromLocation()) return;
  const view=sessionStorage.getItem('curri-view'), lab=sessionStorage.getItem('curri-lab');
  if(view==='detail' && lab)await openLab(lab,false);
  else if(view==='board' || (['inbox','profile'].includes(view) && state.session.user))await showView(view);
  else if(view==='saved')await renderSaved();
  else if(view==='results' && state.session.profile.interests)await showResults();
  else renderHome();
}
boot().catch(error=>{main.innerHTML=`<div class="empty"><h3>연결을 확인해 주세요.</h3><p>${h(error.message)}</p><button class="secondary" data-action="retry">다시 시도</button></div>`;});
document.addEventListener('keydown', event => {
  const input = event.target.closest && event.target.closest('.mirror-input');
  if (input && event.key === 'Enter' && !event.isComposing) { event.preventDefault(); mirrorAction('mirror-add', {dataset: {key: input.dataset.key}}); }
});

// The lab sidebar scrolls on its own. Its height runs from wherever its top currently sits (below the header at the
// top of the page, pinned near the top once scrolled) to the bottom of the window, so its end is never cut off.
let sidebarFitQueued = false;
function fitSidebar() {
  sidebarFitQueued = false;
  const side = document.querySelector('.lab-sidebar');
  if (!side) return;
  const top = getComputedStyle(side).position === 'sticky' ? `${Math.max(0, Math.round(side.getBoundingClientRect().top))}px` : '';
  if (side.style.getPropertyValue('--sidebar-top') !== top) top ? side.style.setProperty('--sidebar-top', top) : side.style.removeProperty('--sidebar-top');
}
function queueSidebarFit() { if (!sidebarFitQueued) { sidebarFitQueued = true; requestAnimationFrame(fitSidebar); } }
window.addEventListener('scroll', queueSidebarFit, {passive: true});
window.addEventListener('resize', queueSidebarFit);
if (window.ResizeObserver) new ResizeObserver(queueSidebarFit).observe(main);
