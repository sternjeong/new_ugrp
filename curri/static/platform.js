'use strict';
// Platform features: screen URLs, consent and privacy, email verification, password reset, notification and
// graduate settings, account deletion, AI research guide, plain-language summaries, lab watch, anonymous Q&A,
// coffee chat, blocking and reports. Loaded before app.js; it only uses app.js globals (state, api, action, h,
// main, toast, setView, openLab, ...) when its functions are called.

const VIEW_PATHS = {home: '/', results: '/results', saved: '/saved', board: '/board', inbox: '/inbox', profile: '/profile',
  privacy: '/privacy', reset: '/reset', graduate: '/graduate'};
const el = id => document.getElementById(id);
function pathFor(view) { return view === 'detail' && state.lab ? '/lab/' + encodeURIComponent(state.lab.id) : (VIEW_PATHS[view] || '/'); }
async function routeFromLocation() {
  const path = location.pathname, params = new URLSearchParams(location.search);
  const lab = path.match(/^\/lab\/(.+)$/);
  if (lab) { await openLab(decodeURIComponent(lab[1]), false); return true; }
  if (path === '/privacy') { await renderPrivacy(); return true; }
  if (path === '/reset') { renderReset(params.get('token') || ''); return true; }
  if (path === '/graduate') { await renderGraduate(); return true; }
  if (['/board', '/inbox', '/profile'].includes(path)) { await showView(path.slice(1)); return true; }
  if (path === '/saved') { await renderSaved(); return true; }
  if (path === '/results' && state.session.profile.interests) { await showResults(); return true; }
  return false;
}
async function restorePlatformView(view) {
  if (view === 'privacy') { await renderPrivacy(); return true; }
  if (view === 'graduate') { await renderGraduate(); return true; }
  return false;
}
function shortDate(ts) { return new Date(ts * 1000).toLocaleDateString('ko-KR', {month: 'short', day: 'numeric'}); }

// ---- consent, search notice, prewarm ----
const CONSENT_ITEMS = [
  ['terms', true, '이용 안내에 동의합니다.'],
  ['privacy', true, '개인정보 수집·이용과 국외 보관에 동의합니다. 이메일·이름·별명·학교·관심 분야를 회원 관리와 선배 연결에 쓰고 탈퇴하면 지웁니다. 서버가 일본(Oracle 도쿄 리전)에 있어 정보가 국외에 보관돼요.'],
  ['age14', true, '만 14세 이상입니다.'],
  ['overseas', false, '의미 검색과 AI 연구 가이드를 위해 검색 문장·선택 과목·학과·학년을 미국 사업자(Google Kaggle, Anthropic)에서 처리하는 데 동의합니다. 이름·이메일은 보내지 않아요. 동의하지 않아도 가입할 수 있어요.'],
];
function consentHTML() {
  return `<fieldset class="form-section consent"><legend>동의 <button type="button" class="text-button inline" data-action="privacy">개인정보 처리방침 보기</button></legend>${CONSENT_ITEMS.map(([k, required, label]) => `<label class="check"><input type="checkbox" name="consent-${k}" ${required ? 'required' : ''}><span><b>${required ? '[필수]' : '[선택]'}</b> ${h(label)}</span></label>`).join('')}<p class="micro">필수 항목에 동의하지 않으면 가입할 수 없어요. 비회원으로 첫 연구실 탐색은 할 수 있어요.</p></fieldset>`;
}
function readConsents(form) { return Object.fromEntries(CONSENT_ITEMS.map(([k]) => [k, !!form.querySelector(`[name=consent-${k}]`)?.checked])); }
function searchNoticeHTML() {
  const on = state.session?.overseas;
  return `<p class="micro overseas-note">${on ? '의미 검색을 위해 검색 문장이 해외(미국) 서버에서 처리될 수 있어요. 이름·연락처 같은 개인정보는 적지 마세요.' : '해외 처리 없이 사전 검색으로 찾고 있어요.'} <button type="button" class="text-button inline" data-action="toggle-overseas">${on ? '해외 처리 없이 검색' : '의미 검색 사용하기'}</button> · <button type="button" class="text-button inline" data-action="privacy">처리방침</button></p>`;
}
let prewarmed = false;
document.addEventListener('focusin', event => {
  if (event.target.id === 'interests' && !prewarmed) { prewarmed = true; api('prewarm', {}).catch(() => {}); }
});

// ---- privacy policy ----
async function renderPrivacy() {
  const data = await api('privacy'); setView('privacy');
  const p = data.policy, c = data.consent;
  main.innerHTML = `<section class="page-heading"><h1>${h(p.title)}</h1><p>운영: ${h(p.operator)} · 버전 ${h(p.version)}</p></section>${p.missing_slots.length ? `<div class="notice strong">운영자 정보가 아직 비어 있어요: ${p.missing_slots.map(h).join(', ')}</div>` : ''}<div class="policy">${p.sections.map(s => `<section><h3>${h(s.heading)}</h3><ul>${s.items.map(i => `<li>${h(i)}</li>`).join('')}</ul></section>`).join('')}<section><h3>가입할 때 받는 동의</h3><ul>${c.required_summary.concat(c.optional_summary).map(x => `<li><b>${h(x.purpose)}</b> — ${h(x.items)} · ${h(x.retention)}</li>`).join('')}<li>${h(c.refusal)}</li></ul></section></div><button class="secondary" data-action="home">처음으로</button>`;
}

// ---- password reset ----
function openForgot() {
  el('auth-dialog').close();
  openSheet(`<h2 id="sheet-title">비밀번호 재설정</h2><p class="sheet-sub">가입한 이메일로 재설정 링크를 보내 드려요. 링크는 1시간 동안 쓸 수 있어요.</p><form id="forgot-form"><label>이메일<input name="email" type="email" required maxlength="254" autocomplete="email"></label><p id="sheet-error" class="error" role="alert"></p><button class="primary full" type="submit">재설정 링크 받기</button></form>`);
}
function renderReset(token) {
  setView('reset');
  main.innerHTML = `<section class="page-heading"><h1>새 비밀번호 정하기</h1><p>바꾸면 모든 기기에서 로그아웃돼요.</p></section><form id="reset-form" class="profile-form narrow" data-token="${h(token)}"><label>새 비밀번호<input name="password" type="password" minlength="10" maxlength="128" required autocomplete="new-password"></label><label>한 번 더<input name="again" type="password" minlength="10" maxlength="128" required autocomplete="new-password"></label><p id="reset-error" class="error" role="alert"></p><button class="primary" type="submit">비밀번호 바꾸기</button></form>`;
}

// ---- profile: verification, notifications, overseas consent, graduate settings, deletion ----
function platformProfileHTML(user) {
  const n = user.notify || {}, a = user.account || {}, mail = state.session.features?.mail;
  const verify = user.email_verified ? '<p class="micro ok">이메일 인증 완료</p>' : `<div class="notice">이메일 인증을 하면 쪽지·만남 알림을 받을 수 있고, 학교 메일이면 선배 인증도 신청할 수 있어요.${mail ? '' : '<br>지금은 메일 발송이 설정되지 않아 코드가 바로 오지 않을 수 있어요.'}</div><form id="verify-form" class="inline-form"><button type="button" class="secondary" data-action="send-code">인증 코드 받기</button><input name="code" inputmode="numeric" pattern="\\d{6}" maxlength="6" placeholder="6자리 코드"><button class="primary" type="submit">인증</button></form>`;
  const labels = {messages: '새 쪽지', meetings: '만남 요청·확정·하루 전 알림', watch: '지켜보는 연구실의 새 논문', qna: '내 질문의 새 답변'};
  const notify = `<form id="notify-form" class="check-list">${Object.entries(labels).map(([k, l]) => `<label class="check"><input type="checkbox" name="${k}" ${n[k] !== false ? 'checked' : ''}><span>${l}</span></label>`).join('')}</form>`;
  const overseas = `<p>${state.session.overseas ? '동의함: 의미 검색과 AI 연구 가이드를 써요.' : '동의하지 않음: 사전 검색과 기본 가이드만 써요.'} <button class="text-button inline" data-action="toggle-overseas">${state.session.overseas ? '동의 철회' : '동의하기'}</button></p>`;
  let grad = '';
  if (user.role === 'graduate') grad = `<form id="grad-settings-form" class="profile-form"><label class="check"><input type="checkbox" name="contact_consent" ${a.contact_consent ? 'checked' : ''}><span>학생의 쪽지·커피챗 요청 받기</span></label><label class="check"><input type="checkbox" name="show_email" ${a.show_email ? 'checked' : ''}><span>로그인한 사용자에게 내 이메일 보이기</span></label><div class="form-grid"><label>한 달에 받을 새 문의 수<input name="monthly_limit" type="number" min="0" max="30" value="${h(a.monthly_limit ?? 4)}"></label><label>가능한 시간<input name="availability" maxlength="120" value="${h(a.availability || '')}" placeholder="예: 평일 저녁, 금요일 오후"></label></div><button class="secondary" type="submit">선배 설정 저장</button></form>`;
  else if (user.grad_status === 'pending') grad = '<p>선배 인증을 심사하고 있어요. 결과는 메일로 알려 드려요.</p>';
  else grad = `<p>${user.grad_status === 'rejected' ? '이전 신청이 승인되지 않았어요. 내용을 보완해 다시 신청할 수 있어요. ' : ''}대학원생이라면 학교 메일 인증 후 선배로 등록해 후배의 질문에 답할 수 있어요.</p><button class="secondary" data-action="graduate">선배 인증 신청하기</button>`;
  return `<section class="settings"><h2>계정 설정</h2><div class="settings-block"><h3>이메일 인증</h3>${verify}</div><div class="settings-block"><h3>알림 메일</h3>${notify}</div><div class="settings-block"><h3>해외 처리 동의 <small>선택</small></h3>${overseas}</div><div class="settings-block"><h3>${user.role === 'graduate' ? '선배 설정' : '선배 인증'}</h3>${grad}</div><details class="settings-block danger"><summary>계정 삭제</summary><p>프로필·탐색 기록·후기·질문이 바로 삭제돼요. 이미 상대가 받은 쪽지는 ‘탈퇴한 사용자’로 표시돼 상대에게만 남아요. 되돌릴 수 없어요.</p><form id="delete-form" class="inline-form"><input name="password" type="password" required placeholder="비밀번호 확인" autocomplete="current-password"><button class="danger-button" type="submit">계정 삭제</button></form></details><p class="micro"><button class="text-button inline" data-action="privacy">개인정보 처리방침</button></p></section>`;
}

// ---- graduate application ----
async function renderGraduate() {
  await refreshSession(); const user = state.session.user;
  if (!user) { renderHome(); showAuth(); return; }
  const labs = (await api('labs')).labs; setView('graduate');
  const ok = user.email_verified && /@postech\.ac\.kr$/i.test(user.email);
  main.innerHTML = `<section class="page-heading"><h1>선배 인증 신청</h1><p>승인되면 연구실 상세에 선배로 소개되고, 쪽지·커피챗과 익명 질문에 답할 수 있어요.</p></section>${ok ? '' : `<div class="notice strong">학교 메일(@postech.ac.kr)로 가입하고 이메일 인증을 마친 계정만 신청할 수 있어요. 지금 계정: ${h(user.email)} ${user.email_verified ? '(인증됨)' : '(미인증)'}</div>`}<form id="graduate-form" class="profile-form"><label>소속 연구실<select name="lab_id" required><option value="">선택해 주세요</option>${labs.map(l => `<option value="${h(l.id)}">${h(l.department)} · ${h(l.professors.join(', '))} · ${h(l.name)}</option>`).join('')}</select></label><div class="form-grid"><label>과정<select name="program" required>${['석사과정', '박사과정', '석박통합과정', '박사후연구원'].map(p => `<option>${p}</option>`).join('')}</select></label><label>한 달에 받을 새 문의 수<input name="monthly_limit" type="number" min="0" max="30" value="4"></label></div><label>연구 분야<input name="research" required minlength="2" maxlength="120" placeholder="예: 로봇 파지, 3D 비전"></label><label>가능한 시간<input name="availability" maxlength="120" placeholder="예: 평일 저녁"></label><label>확인 메모 <small>운영자만 봐요</small><input name="note" maxlength="300" placeholder="예: 2025년 입학, 지도교수 ○○○"></label><label class="check"><input type="checkbox" name="contact_consent" checked><span>학생의 쪽지·커피챗 요청을 받을게요.</span></label><p id="graduate-error" class="error" role="alert"></p><button class="primary" type="submit" ${ok ? '' : 'disabled'}>신청하기</button></form>`;
}

// ---- detail page: summary, watch, share, Q&A ----
function platformSidebarHTML(lab) {
  return `<div class="lab-tools"><span id="watch-box"></span><button class="text-button" data-action="share">링크 복사</button></div><div id="easy-summary"></div>`;
}
function platformAfterDetail() {
  const id = state.lab?.id; if (!id) return;
  loadSummary(id); loadWatch(id); loadQna(id);
  if (['queued', 'running'].includes(state.guide?.ai?.status)) pollGuide(id, Date.now());
}
async function loadSummary(labId, tries = 0) {
  const box = el('easy-summary'); if (!box) return;
  const r = await api(`summary?lab_id=${encodeURIComponent(labId)}`).catch(() => null);
  if (!r || state.lab?.id !== labId || !el('easy-summary')) return;
  if (r.status === 'done') { el('easy-summary').innerHTML = summaryHTML(r.summary) + citedHTML(r.cited); api('event', {name: 'summary_view'}).catch(() => {}); }
  else if (['queued', 'running'].includes(r.status) && tries < 25) { el('easy-summary').innerHTML = '<p class="micro">연구실 자료를 쉬운 말로 정리하고 있어요…</p>' + citedHTML(r.cited); setTimeout(() => loadSummary(labId, tries + 1), 8000); }
  else el('easy-summary').innerHTML = citedHTML(r.cited);
}
function summaryHTML(s) {
  const focus = (s.focus || []).length ? `<div class="easy-focus"><p class="ev-title">중점 연구 주제</p>${s.focus.map(f => `<p><b>${h(f.title)}</b> ${h(f.plain)} <span class="micro">근거: ${h(f.basis)}</span></p>`).join('')}</div>` : '';
  return `<details class="easy-summary" open><summary>이 연구실은 어떤 곳인가요 <span class="pill neutral">AI 요약</span></summary><p class="oneliner">${h(s.lab_oneliner)}</p>${focus}${s.papers.map(p => `<div class="easy-paper"><p class="ev-title">${h(p.title)} <span class="micro">${h(p.year || '')}</span></p><p>${h(p.plain)}</p>${p.terms.length ? `<dl class="terms">${p.terms.map(t => `<div><dt>${h(t.term)}</dt><dd>${h(t.meaning)}</dd></div>`).join('')}</dl>` : ''}<a class="small-link" href="${h(p.url)}" target="_blank" rel="noopener noreferrer">원문 ↗</a></div>`).join('')}<p class="micro">연구실 자료와 초록을 바탕으로 AI가 풀어 쓴 설명이에요. 정확한 내용은 원문을 확인하세요. 교수님의 지도 방식이나 연구실 분위기는 공개 자료에 없어 다루지 않았어요. 선배 후기를 참고해 주세요.</p></details>`;
}
function citedHTML(c) {
  if (!c || (!c.papers.length && !c.note)) return '';
  return `<div class="cited-papers"><p class="ev-title">인용이 많은 논문</p>${c.papers.map(p => `<p><a href="${h(p.url)}" target="_blank" rel="noopener noreferrer">${h(p.title)} ↗</a><br><span class="micro">${h([p.year, p.venue, `인용 ${p.cited_by_count}회`, p.lab_led ? '' : '공동 연구'].filter(Boolean).join(' · '))}</span></p>`).join('')}<p class="micro">${h(c.note)}</p></div>`;
}
async function loadWatch(labId) {
  const r = await api(`watch?lab_id=${encodeURIComponent(labId)}`).catch(() => null);
  if (!r || state.lab?.id !== labId || !el('watch-box')) return;
  state.watch = r;
  el('watch-box').innerHTML = `<button class="text-button ${r.watching ? 'on' : ''}" data-action="watch">${r.watching ? '새 논문 알림 받는 중' : '새 논문 알림 받기'}</button>${r.new_papers.length ? `<div class="new-papers"><p class="micro">최근 확인된 새 논문</p>${r.new_papers.map(p => `<a href="${h(p.url)}" target="_blank" rel="noopener noreferrer">${h(p.title)} (${h(p.year || '')})</a>`).join('')}</div>` : ''}`;
}
async function loadQna(labId) {
  const r = await api(`qna?lab_id=${encodeURIComponent(labId)}`).catch(() => null);
  if (!r || state.lab?.id !== labId || !el('qna')) return;
  state.qna = r; el('qna').outerHTML = qnaHTML(r);
}
function qnaHTML(q) {
  const user = state.session?.user;
  const ask = q.can_ask ? `<form id="qna-ask-form" class="qna-form"><textarea name="body" required minlength="10" maxlength="1000" placeholder="이 연구실 선배에게 궁금한 점을 남겨 보세요. 이름과 별명은 표시되지 않아요."></textarea><button class="secondary" type="submit">익명으로 질문하기</button></form>` : (!user ? '<button class="secondary" data-action="account">로그인하고 질문하기</button>' : '');
  const items = q.questions.map(x => `<article class="qna-item"><p class="qna-q"><b>Q.</b> ${h(x.body)}</p><p class="micro">${h(x.author)} · ${shortDate(x.created)} ${x.mine ? `<button class="text-button inline" data-action="qna-delete" data-kind="question" data-id="${x.id}">삭제</button>` : (user ? `<button class="text-button inline" data-action="report" data-kind="question" data-id="${x.id}">신고</button>` : '')}</p>${x.answers.map(a => `<div class="qna-a"><p><b>A.</b> ${h(a.body)}</p><p class="micro">${h(a.author)} · ${shortDate(a.created)} ${a.mine ? `<button class="text-button inline" data-action="qna-delete" data-kind="answer" data-id="${a.id}">삭제</button>` : (user ? `<button class="text-button inline" data-action="report" data-kind="answer" data-id="${a.id}">신고</button>` : '')}</p></div>`).join('')}${q.can_answer ? `<form class="qna-answer-form qna-form" data-id="${x.id}"><textarea name="body" required minlength="5" maxlength="2000" placeholder="선배로서 답변하기"></textarea><button class="secondary" type="submit">답변</button></form>` : ''}</article>`).join('');
  return `<section id="qna" class="community"><h2>익명 질문</h2><p class="sub">질문자는 ‘익명 학생’으로만 보여요. 이 연구실 인증 선배가 답해요.</p>${ask}${items || '<div class="empty small"><p>아직 질문이 없어요. 첫 질문을 남겨 보세요.</p></div>'}</section>`;
}

// ---- AI research guide ----
function aiGuideHTML(guide) {
  const ai = guide.ai; if (!ai) return '';
  if (ai.status === 'done') return `<section class="ai-guide"><div class="ai-head"><h3>AI가 고른 학부생 연구 주제</h3><span class="pill neutral">AI 제안 · 근거 인용은 원문과 대조했어요</span></div><div class="ai-topics">${ai.topics.map((t, i) => `<article class="topic-card ai"><span class="pill neutral">${h(t.difficulty)}</span><h4>${h(t.title)}</h4><p class="question">${h(t.question)}</p><p>${h(t.interest_link)}</p>${t.courses.length ? `<div class="course-mini"><p>내가 들은 과목과의 연결</p>${t.courses.map(c => `<p><b>${h(c.name)}</b> — ${h(c.concept)}: ${h(c.how_used)}</p>`).join('')}</div>` : ''}${t.gaps.length ? `<p class="micro">더 배우면 좋은 것: ${t.gaps.map(h).join(', ')}</p>` : ''}<p class="first-step"><b>첫 단계</b> ${h(t.first_step)}</p><details><summary>이 주제의 근거</summary>${evidence(t.evidence)}</details><div class="feedback" data-topic="${i}"><span class="micro">이 제안이 도움이 됐나요?</span><button class="fb-btn" data-action="guide-feedback" data-topic="${i}" data-helpful="1">도움 됐어요</button><button class="fb-btn" data-action="guide-down" data-topic="${i}">아쉬워요</button></div></article>`).join('')}</div>${ai.next_courses.length ? `<div class="ai-next"><h4>다음에 들어 볼 과목</h4>${ai.next_courses.map(c => `<p><b>${h(c.name)}</b> <span class="micro">${h(c.code)}</span> — ${h(c.reason)}</p>`).join('')}</div>` : ''}${ai.caution ? `<p class="micro">${h(ai.caution)}</p>` : ''}${guide.ai_previous?.length ? `<p class="micro">이전 제안(${guide.ai_previous.map(t => h(t.title)).join(' · ')})과 다른 방향으로 다시 받은 결과예요.</p>` : ''}</section>`;
  if (['queued', 'running'].includes(ai.status)) return '<section class="ai-guide pending"><p><span class="spinner" aria-hidden="true"></span> AI가 이 연구실의 최근 논문과 내 관심·수강 과목을 보고 주제를 고르고 있어요. 보통 30초쯤 걸려요.</p></section>';
  if (ai.status === 'no_consent') return `<section class="ai-guide muted"><p>AI 연구 가이드는 해외 처리 동의가 있어야 만들 수 있어요. <button class="text-button inline" data-action="toggle-overseas">동의하고 AI 가이드 받기</button></p></section>`;
  if (ai.status === 'offline') return '<section class="ai-guide muted"><p>AI 가이드 작업자가 잠시 쉬고 있어요. 아래 기본 가이드를 먼저 보고, 잠시 뒤 다시 눌러 주세요.</p></section>';
  if (ai.status === 'failed') return '<section class="ai-guide muted"><p>근거를 확인할 수 있는 AI 제안을 만들지 못했어요. 아래 기본 가이드를 보세요.</p></section>';
  return '';
}
async function pollGuide(labId, started) {
  await new Promise(r => setTimeout(r, 4000));
  if (state.lab?.id !== labId || Date.now() - started > 5 * 60 * 1000) return;
  const r = await api(`guide/status?lab_id=${encodeURIComponent(labId)}`).catch(() => null);
  if (!r || state.lab?.id !== labId) return;
  if (r.guide && r.guide.ai?.status !== state.guide?.ai?.status) {
    state.guide = r.guide;
    if (r.guide.ai?.status === 'done') askService('guide');
    if (el('guide-content')) el('guide-content').innerHTML = guideHTML(state.guide);
  }
  if (['queued', 'running'].includes(state.guide?.ai?.status)) pollGuide(labId, started);
}
function savedGuideHTML(record) {
  const ai = record.guide?.ai;
  if (ai?.status !== 'done') return '';
  return `<details class="saved-guide"><summary>AI가 제안한 주제 ${ai.topics.length}개</summary>${ai.topics.map(t => `<p><b>${h(t.title)}</b><br><span class="micro">첫 단계: ${h(t.first_step)}</span></p>`).join('')}</details>`;
}

// ---- seniors: coffee chat ----
function seniorExtraHTML(g) {
  return `${g.verified ? '<span class="pill">인증 선배</span> ' : ''}${g.availability ? `<p class="micro">가능한 시간: ${h(g.availability)}</p>` : ''}${g.full ? '<p class="micro">이번 달 문의를 모두 받았어요.</p>' : ''}`;
}
function seniorActionHTML(g) {
  if (state.session?.user?.role === 'graduate') return '';
  if (g.thread_id) return `<button class="explore-button" data-action="open-thread" data-id="${g.thread_id}">대화 이어가기</button>`;
  return g.full ? '' : `<button class="explore-button" data-action="coffeechat" data-id="${g.id}">커피챗 요청하기</button>`;
}
function openCoffeeChat(id) {
  if (!requireMember('선배에게 연락하려면')) return;
  const g = state.community.graduates.find(x => x.id === id); if (!g) return;
  const user = state.session.user, a = user.account;
  const greeting = `안녕하세요, ${g.name} 선배님. ${[a.department, a.grade, user.nickname].filter(Boolean).join(' ')}입니다. 3분커리에서 연구실을 알아보다 연락드려요.\n\n궁금한 점:\n1. `;
  const slot = n => `<label>후보 ${n}<input type="datetime-local" name="slot" ${n === 1 ? 'data-first' : ''}></label>`;
  openSheet(`<h2 id="sheet-title">${h(g.name)} 선배에게 커피챗 요청</h2><p class="sheet-sub">${h(nameOf(state.lab))} · ${h(g.program)} · ${h(g.research)}${g.availability ? ` · 가능한 시간: ${h(g.availability)}` : ''}</p><form id="coffee-form" data-id="${g.id}"><label>제목<input name="subject" required minlength="2" maxlength="80" value="${h((g.research.split(' · ')[0] || '연구실') + ' 커피챗 요청')}"></label><label>내용<textarea name="body" required minlength="10" maxlength="2000">${h(greeting)}</textarea></label><label class="check"><input type="checkbox" name="with_meeting" checked><span>만남 시간도 함께 제안할게요</span></label><fieldset class="meeting-fields"><div class="form-grid"><label>방식<select name="mode"><option value="online">온라인</option><option value="offline">대면</option></select></label><label>시간<select name="minutes"><option value="20">20분</option><option value="30">30분</option></select></label></div><div class="form-grid three">${slot(1)}${slot(2)}${slot(3)}</div><label>대면 장소 <small>대면일 때만</small><input name="place" maxlength="100" placeholder="예: 학생회관 카페"></label></fieldset><div class="share-preview"><p class="micro">요청과 함께 선배에게 전달되는 내 정보</p><p><b>${h(a.real_name)}</b> (${h(user.nickname)}) · ${h(user.email)}<br>${h([a.school, a.department, a.grade].filter(Boolean).join(' · '))}</p></div><label class="check"><input type="checkbox" name="share_consent" required><span><b>[필수]</b> 위 이름·이메일·프로필을 이 선배에게 전달하는 데 동의합니다.</span></label><p id="sheet-error" class="error" role="alert"></p><button class="primary full" type="submit">요청 보내기</button></form>`);
}

// ---- reports and blocks ----
function openReport(kind, id) {
  if (!requireMember('신고하려면')) return;
  openSheet(`<h2 id="sheet-title">신고하기</h2><p class="sheet-sub">운영자가 확인한 뒤 숨김·이용 제한 등 조치해요. 신고자는 공개되지 않아요.</p><form id="report-form" data-kind="${h(kind)}" data-id="${h(id)}"><label>사유<textarea name="reason" required minlength="2" maxlength="500" placeholder="예: 욕설, 개인정보 노출, 허위 정보"></textarea></label><p id="sheet-error" class="error" role="alert"></p><button class="primary full" type="submit">신고 보내기</button></form>`);
}
function threadToolsHTML(t) {
  const o = t.other; if (!o || o.deleted || !o.id) return '';
  return `<p class="thread-tools"><button class="text-button inline" data-action="report" data-kind="user" data-id="${o.id}">신고</button> · <button class="text-button inline" data-action="block" data-id="${o.id}">차단</button></p>`;
}
function reviewReportHTML(r) {
  return state.session?.user && !r.mine ? `<button class="text-button inline" data-action="report" data-kind="review" data-id="${r.id}">신고</button>` : '';
}

// ---- click and submit delegation (called from app.js) ----
function platformClick(name, button) {
  if (feedbackClick(name, button)) return true;
  const id = Number(button.dataset.id);
  if (name === 'forgot') { openForgot(); return true; }
  if (name === 'coffeechat') { openCoffeeChat(id); return true; }
  if (name === 'report') { openReport(button.dataset.kind, id); return true; }
  if (name === 'share') {
    const url = location.origin + '/lab/' + encodeURIComponent(state.lab.id);
    (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(() => toast('연구실 링크를 복사했어요.'), () => prompt('이 링크를 복사해 주세요.', url));
    return true;
  }
  const handlers = {
    'privacy': async () => { if (el('auth-dialog').open) el('auth-dialog').close(); if (el('sheet-dialog').open) el('sheet-dialog').close(); await persist(); await renderPrivacy(); },
    'graduate': () => renderGraduate(),
    'toggle-overseas': async () => {
      const on = !state.session.overseas;
      if (on && !confirm('검색 문장·선택 과목·학과·학년을 미국 사업자(Google Kaggle, Anthropic)에서 처리하는 데 동의할까요? 언제든 철회할 수 있어요.')) return;
      state.session = await api('account/overseas', {allowed: on}); header();
      toast(on ? '의미 검색과 AI 가이드를 켰어요.' : '해외 처리를 껐어요. 사전 검색과 기본 가이드만 써요.');
      if (state.view === 'home') renderHome(); else if (state.view === 'profile') await renderProfile(); else if (state.view === 'detail' && el('guide-content') && state.guide) el('guide-content').innerHTML = guideHTML(state.guide);
    },
    'send-code': async () => { const r = await api('email/send', {}); toast(r.verified ? '이미 인증된 이메일이에요.' : (r.mail_enabled ? '인증 코드를 보냈어요. 메일함을 확인해 주세요.' : '코드를 만들었지만 메일 발송이 아직 설정되지 않았어요. 운영자에게 문의해 주세요.')); },
    'watch': async () => {
      if (!state.session?.user) { toast('지켜보려면 로그인해 주세요.'); showAuth(); return; }
      await api('watch', {lab_id: state.lab.id, on: !state.watch?.watching}); await loadWatch(state.lab.id);
      toast(state.watch.watching ? '새 논문이 나오면 메일로 알려 드릴게요.' : '지켜보기를 그만뒀어요.');
    },
    'qna-delete': async () => { if (!confirm('삭제할까요?')) return; state.qna = await api('qna/delete', {kind: button.dataset.kind, id}); el('qna').outerHTML = qnaHTML(state.qna); },
    'block': async () => { if (!confirm('이 사용자를 차단할까요? 서로 쪽지를 보낼 수 없게 돼요.')) return; await api('block', {user_id: id}); toast('차단했어요.'); },
    'guide-feedback': async () => { await api('guide/feedback', {lab_id: state.lab.id, helpful: button.dataset.helpful === '1', topic: Number(button.dataset.topic)}); button.parentElement.innerHTML = '<span class="micro">고마워요. 더 나은 제안에 반영할게요.</span>'; },
  };
  if (!handlers[name]) return false;
  action(handlers[name]);
  return true;
}
const PLATFORM_FORMS = ['forgot-form', 'reset-form', 'verify-form', 'notify-form', 'delete-form', 'grad-settings-form', 'graduate-form', 'qna-ask-form', 'coffee-form', 'report-form'];
function platformSubmit(event) {
  const form = event.target, id = form.id || (form.classList.contains('qna-answer-form') ? 'qna-answer-form' : '');
  if (![...PLATFORM_FORMS, 'qna-answer-form'].includes(id)) return false;
  event.preventDefault();
  const data = new FormData(form), checked = name => !!form.querySelector(`[name=${name}]`)?.checked;
  const showError = (message) => { const box = form.querySelector('.error') || el('sheet-error'); if (box) box.textContent = message; else toast(message); };
  action(async () => {
    try {
      if (id === 'forgot-form') { await api('password/forgot', {email: data.get('email')}); form.outerHTML = '<p>가입된 이메일이면 재설정 링크를 보냈어요. 메일함(스팸함 포함)을 확인해 주세요.</p>'; }
      else if (id === 'reset-form') {
        if (data.get('password') !== data.get('again')) { showError('두 비밀번호가 달라요.'); return; }
        await api('password/reset', {token: form.dataset.token, password: data.get('password')}); history.replaceState(null, '', '/'); renderHome(); showAuth(); toast('비밀번호를 바꿨어요. 새 비밀번호로 로그인해 주세요.');
      }
      else if (id === 'verify-form') { await api('email/verify', {code: (data.get('code') || '').trim()}); await renderProfile(); toast('이메일을 인증했어요.'); }
      else if (id === 'notify-form') { await api('account/notify', {notify: Object.fromEntries(['messages', 'meetings', 'watch', 'qna'].map(k => [k, checked(k)]))}); toast('알림 설정을 저장했어요.'); }
      else if (id === 'delete-form') {
        if (!confirm('정말 계정을 삭제할까요? 되돌릴 수 없어요.')) return;
        const r = await api('account/delete', {password: data.get('password')}); state.session = r.session; header(); renderHome(); toast('계정을 삭제했어요. 그동안 고마웠어요.');
      }
      else if (id === 'grad-settings-form') { await api('graduate/settings', {contact_consent: checked('contact_consent'), show_email: checked('show_email'), monthly_limit: Number(data.get('monthly_limit')), availability: data.get('availability') || ''}); toast('선배 설정을 저장했어요.'); }
      else if (id === 'graduate-form') { await api('graduate/apply', {lab_id: data.get('lab_id'), program: data.get('program'), research: data.get('research'), availability: data.get('availability') || '', note: data.get('note') || '', monthly_limit: Number(data.get('monthly_limit')), contact_consent: checked('contact_consent')}); await renderProfile(); toast('선배 인증을 신청했어요. 결과는 메일로 알려 드려요.'); }
      else if (id === 'qna-ask-form') { state.qna = await api('qna/ask', {lab_id: state.lab.id, body: data.get('body')}); el('qna').outerHTML = qnaHTML(state.qna); toast('질문을 남겼어요. 답이 달리면 메일로 알려 드려요.'); }
      else if (id === 'qna-answer-form') { state.qna = await api('qna/answer', {question_id: Number(form.dataset.id), body: data.get('body')}); el('qna').outerHTML = qnaHTML(state.qna); toast('답변을 남겼어요.'); }
      else if (id === 'report-form') { await api('report', {kind: form.dataset.kind, ref_id: Number(form.dataset.id), reason: data.get('reason')}); el('sheet-dialog').close(); toast('신고를 접수했어요. 운영자가 확인할게요.'); }
      else if (id === 'coffee-form') {
        const meeting = checked('with_meeting') ? {mode: data.get('mode'), minutes: Number(data.get('minutes')), slots: data.getAll('slot').filter(Boolean), place: data.get('place') || '', note: ''} : null;
        const r = await api('coffeechat', {graduate_id: Number(form.dataset.id), subject: data.get('subject'), body: data.get('body'), lab_id: state.lab.id, share_consent: checked('share_consent'), meeting});
        state.community = await api(`community?lab_id=${encodeURIComponent(state.lab.id)}`); el('sheet-dialog').close(); refreshCommunity();
        toast(r.meeting_error ? `쪽지는 보냈지만 만남 제안은 실패했어요: ${r.meeting_error} 쪽지함에서 다시 제안해 주세요.` : '커피챗을 요청했어요. 답장은 쪽지함과 메일로 알려 드려요.');
      }
    } catch (error) {
      if (error.code === 'login_required') { if (el('sheet-dialog').open) el('sheet-dialog').close(); showAuth(); }
      else if (error.code === 'profile_required') { if (el('sheet-dialog').open) el('sheet-dialog').close(); toast(error.message); await renderProfile(); }
      else showError(error.message);
    }
  });
  return true;
}

// ---- feedback loop: results, search, AI guide, meetings, service ----
const RESULT_REASONS = {great: '딱 찾던 곳이에요', new: '몰랐는데 흥미로워요', off_topic: '관심 분야와 달라요', too_hard: '지금 하기엔 어려워요', known: '이미 알던 곳이에요', no_info: '정보가 부족해요'};
const GUIDE_REASONS = {off_topic: '관심과 안 맞아요', too_hard: '너무 어려워요', too_easy: '너무 쉬워요', vague: '첫 단계가 막연해요', wrong_fact: '연구실 내용이 틀려요', courses: '과목 연결이 억지예요'};
const voted = {};
function resultFeedbackHTML(lab, index) {
  const v = voted['r:' + lab.id];
  const social = lab.social ? `<p class="micro social">${h(lab.social)}</p>` : '';
  if (v) return `${social}<div class="result-fb done"><span class="micro">${v === 'up' ? '고마워요! 비슷한 관심의 학생들에게 더 잘 보여 줄게요.' : '알려 줘서 고마워요. 다음 검색에 반영할게요.'}</span></div>`;
  return `${social}<div class="result-fb" data-lab="${h(lab.id)}" data-rank="${index}"><span class="micro">내 관심과 맞나요?</span><button class="fb-btn" data-action="result-up" data-id="${h(lab.id)}" data-rank="${index}">맞아요</button><button class="fb-btn" data-action="result-down" data-id="${h(lab.id)}" data-rank="${index}">아니에요</button></div>`;
}
function reasonChips(map, action, extra = '') {
  return `<div class="fb-reasons">${Object.entries(map).map(([k, l]) => `<button class="chip" data-action="${action}" data-reason="${k}" ${extra}>${h(l)}</button>`).join('')}</div>`;
}
function searchFeedbackHTML() {
  if (!state.results.length || state.searchInfo?.intent !== 'search') return '';
  if (voted['s:' + (state.session?.profile?.interests || '')]) return '<div class="search-fb done"><p class="micro">의견 고마워요. 검색을 더 낫게 만드는 데 쓸게요.</p></div>';
  return `<div class="search-fb"><p><b>원하던 연구실을 찾았나요?</b></p><div class="fb-scale">${[[5, '찾았어요'], [3, '일부만 찾았어요'], [1, '못 찾았어요']].map(([n, l]) => `<button class="chip" data-action="search-fb" data-rating="${n}">${l}</button>`).join('')}</div></div>`;
}
function meetingFeedbackHTML(t) {
  const m = (state.pendingMeetings || []).find(x => x.thread_id === t.id);
  if (!m) return '';
  return `<form class="meeting-fb" data-id="${m.id}"><p><b>만남은 어땠나요?</b> <span class="micro">${whenOf(m.start)} · 상대에게는 보이지 않아요</span></p><div class="fb-scale">${[1, 2, 3, 4, 5].map(n => `<label class="star"><input type="radio" name="rating" value="${n}" required><span>${'★'.repeat(n)}</span></label>`).join('')}</div><input name="comment" maxlength="500" placeholder="좋았던 점이나 아쉬운 점(선택)"><button class="secondary" type="submit">평가 보내기</button></form>`;
}
function askService(trigger) {
  const last = Number(localStorage.getItem('curri-service-asked') || 0);
  if (Date.now() - last < 14 * 86400000 || document.getElementById('service-pop')) return;
  localStorage.setItem('curri-service-asked', String(Date.now()));
  const pop = document.createElement('div');
  pop.id = 'service-pop'; pop.className = 'service-pop'; pop.setAttribute('role', 'dialog'); pop.setAttribute('aria-label', '서비스 평가');
  pop.innerHTML = `<button class="close-button" data-action="close-pop" aria-label="닫기">×</button><p><b>3분커리가 도움이 됐나요?</b></p><form id="service-form" data-trigger="${h(trigger)}"><div class="fb-scale">${[[1, '별로예요'], [2, '아쉬워요'], [3, '보통이에요'], [4, '좋아요'], [5, '아주 좋아요']].map(([n, e]) => `<label class="emoji"><input type="radio" name="rating" value="${n}" required><span>${e}</span></label>`).join('')}</div><textarea name="comment" maxlength="1000" placeholder="더 좋아지려면 무엇이 필요할까요? (선택)"></textarea><button class="primary full" type="submit">보내기</button></form>`;
  document.body.appendChild(pop);
}
function openFeedback() {
  openSheet(`<h2 id="sheet-title">의견 보내기</h2><p class="sheet-sub">불편한 점, 틀린 정보, 있었으면 하는 기능 무엇이든 좋아요. 이름은 함께 보내지 않아요.</p><form id="service-form" data-trigger="footer"><div class="fb-scale">${[[1, '별로예요'], [2, '아쉬워요'], [3, '보통이에요'], [4, '좋아요'], [5, '아주 좋아요']].map(([n, e]) => `<label class="emoji"><input type="radio" name="rating" value="${n}" required><span>${e}</span></label>`).join('')}</div><textarea name="comment" maxlength="1000" placeholder="자유롭게 적어 주세요"></textarea><p id="sheet-error" class="error" role="alert"></p><button class="primary full" type="submit">보내기</button></form>`);
}
async function sendFeedback(body) { return api('feedback', body); }
function feedbackClick(name, button) {
  const id = button.dataset.id, rank = Number(button.dataset.rank);
  if (name === 'close-pop') { button.closest('.service-pop')?.remove(); return true; }
  if (name === 'open-feedback') { openFeedback(); return true; }
  if (name === 'result-up') {
    sendFeedback({kind: 'result', lab_id: id, rank, helpful: true, reasons: []}).then(() => { voted['r:' + id] = 'up'; button.closest('.result-fb').outerHTML = resultFeedbackHTML({id}, rank); }).catch(e => toast(e.message));
    return true;
  }
  if (name === 'result-down') {
    const box = button.closest('.result-fb');
    box.innerHTML = `<span class="micro">어떤 점이 아쉬웠나요?</span>${reasonChips(Object.fromEntries(Object.entries(RESULT_REASONS).slice(2)), 'result-reason', `data-id="${h(id)}" data-rank="${rank}"`)}`;
    return true;
  }
  if (name === 'result-reason') {
    sendFeedback({kind: 'result', lab_id: id, rank, helpful: false, reasons: [button.dataset.reason]}).then(() => { voted['r:' + id] = 'down'; button.closest('.result-fb').outerHTML = resultFeedbackHTML({id}, rank); }).catch(e => toast(e.message));
    return true;
  }
  if (name === 'search-fb') {
    const rating = Number(button.dataset.rating), box = button.closest('.search-fb');
    sendFeedback({kind: 'search', rating}).then(() => {
      voted['s:' + (state.session?.profile?.interests || '')] = true;
      box.innerHTML = rating <= 3 ? `<p class="micro">무엇을 찾고 싶었는지 한 줄만 알려 주세요. 검색 사전과 순위를 고치는 데 써요.</p><form id="search-comment" class="inline-form"><input name="comment" maxlength="300" placeholder="예: 드론 제어 연구실이 안 나와요"><button class="secondary" type="submit">보내기</button></form>` : '<p class="micro">고마워요! 😀</p>';
    }).catch(e => toast(e.message));
    return true;
  }
  if (name === 'guide-down') {
    const box = button.closest('.feedback'), topic = button.dataset.topic;
    box.innerHTML = `<span class="micro">어떤 점이 아쉬웠나요? (여러 개 골라도 돼요)</span>${reasonChips(GUIDE_REASONS, 'guide-reason')}<div class="inline-form"><input class="fb-comment" maxlength="300" placeholder="더 하고 싶은 방향(선택)"><button class="secondary" data-action="guide-down-send" data-topic="${h(topic)}">보내기</button></div>`;
    return true;
  }
  if (name === 'guide-reason') { button.classList.toggle('on'); return true; }
  if (name === 'guide-down-send' || name === 'guide-retry') {
    const box = button.closest('.feedback, .ai-retry');
    const reasons = [...(box?.querySelectorAll('.chip.on') || [])].map(b => b.dataset.reason);
    const comment = box?.querySelector('.fb-comment')?.value || '';
    if (name === 'guide-down-send') {
      action(async () => {
        await api('guide/feedback', {lab_id: state.lab.id, helpful: false, topic: Number(button.dataset.topic), reasons, comment});
        state.retryFeedback = {reasons, comment};
        box.innerHTML = `<div class="ai-retry"><span class="micro">고마워요. 이 의견을 반영해 다른 방향을 받아 볼까요?</span><button class="secondary" data-action="guide-retry">다른 주제 다시 받기</button></div>`;
      });
    } else {
      action(async () => {
        const fb = state.retryFeedback || {reasons, comment};
        state.guide = (await api('guide/retry', {lab_id: state.lab.id, ...fb})).guide;
        if (el('guide-content')) el('guide-content').innerHTML = guideHTML(state.guide);
        pollGuide(state.lab.id, Date.now());
        toast('피드백을 반영해 새 주제를 만들고 있어요.');
      });
    }
    return true;
  }
  return false;
}
document.addEventListener('submit', event => {
  const form = event.target;
  if (!(form.id === 'service-form' || form.id === 'search-comment' || form.classList.contains('meeting-fb'))) return;
  event.preventDefault(); event.stopImmediatePropagation();
  const data = new FormData(form);
  action(async () => {
    try {
      if (form.id === 'service-form') {
        await sendFeedback({kind: 'service', rating: Number(data.get('rating')), comment: `${data.get('comment') || ''}`.trim(), reasons: []});
        el('service-pop')?.remove(); if (el('sheet-dialog').open) el('sheet-dialog').close(); toast('의견 고마워요. 꼼꼼히 읽어 볼게요.');
      } else if (form.id === 'search-comment') {
        await sendFeedback({kind: 'search', rating: 2, comment: `${data.get('comment') || ''}`.trim()}); form.outerHTML = '<p class="micro">고마워요. 검색 개선에 쓸게요.</p>';
      } else {
        await sendFeedback({kind: 'meeting', ref_id: Number(form.dataset.id), rating: Number(data.get('rating')), comment: `${data.get('comment') || ''}`.trim()});
        state.pendingMeetings = (state.pendingMeetings || []).filter(m => m.id !== Number(form.dataset.id)); form.outerHTML = '<p class="micro meeting-fb done">평가 고마워요. 더 좋은 만남을 만드는 데 쓸게요.</p>';
      }
    } catch (error) { toast(error.message); }
  });
}, true);
