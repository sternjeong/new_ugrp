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
  main.innerHTML = `<section class="page-heading"><div class="eyebrow">PRIVACY</div><h1>${h(p.title)}</h1><p>운영: ${h(p.operator)} · 버전 ${h(p.version)}</p></section>${p.missing_slots.length ? `<div class="notice strong">운영자 정보가 아직 비어 있어요: ${p.missing_slots.map(h).join(', ')}</div>` : ''}<div class="policy">${p.sections.map(s => `<section><h3>${h(s.heading)}</h3><ul>${s.items.map(i => `<li>${h(i)}</li>`).join('')}</ul></section>`).join('')}<section><h3>가입할 때 받는 동의</h3><ul>${c.required_summary.concat(c.optional_summary).map(x => `<li><b>${h(x.purpose)}</b> — ${h(x.items)} · ${h(x.retention)}</li>`).join('')}<li>${h(c.refusal)}</li></ul></section></div><button class="secondary" data-action="home">처음으로</button>`;
}

// ---- password reset ----
function openForgot() {
  el('auth-dialog').close();
  openSheet(`<div class="eyebrow">FORGOT PASSWORD</div><h2 id="sheet-title">비밀번호 재설정</h2><p class="sheet-sub">가입한 이메일로 재설정 링크를 보내 드려요. 링크는 1시간 동안 쓸 수 있어요.</p><form id="forgot-form"><label>이메일<input name="email" type="email" required maxlength="254" autocomplete="email"></label><p id="sheet-error" class="error" role="alert"></p><button class="primary full" type="submit">재설정 링크 받기 <span>→</span></button></form>`);
}
function renderReset(token) {
  setView('reset');
  main.innerHTML = `<section class="page-heading"><div class="eyebrow">RESET PASSWORD</div><h1>새 비밀번호 정하기</h1><p>바꾸면 모든 기기에서 로그아웃돼요.</p></section><form id="reset-form" class="profile-form narrow" data-token="${h(token)}"><label>새 비밀번호<input name="password" type="password" minlength="10" maxlength="128" required autocomplete="new-password"></label><label>한 번 더<input name="again" type="password" minlength="10" maxlength="128" required autocomplete="new-password"></label><p id="reset-error" class="error" role="alert"></p><button class="primary" type="submit">비밀번호 바꾸기 <span>→</span></button></form>`;
}

// ---- profile: verification, notifications, overseas consent, graduate settings, deletion ----
function platformProfileHTML(user) {
  const n = user.notify || {}, a = user.account || {}, mail = state.session.features?.mail;
  const verify = user.email_verified ? '<p class="micro ok">✓ 이메일 인증 완료</p>' : `<div class="notice">이메일 인증을 하면 쪽지·만남 알림을 받을 수 있고, 학교 메일이면 선배 인증도 신청할 수 있어요.${mail ? '' : '<br>지금은 메일 발송이 설정되지 않아 코드가 바로 오지 않을 수 있어요.'}</div><form id="verify-form" class="inline-form"><button type="button" class="secondary" data-action="send-code">인증 코드 받기</button><input name="code" inputmode="numeric" pattern="\\d{6}" maxlength="6" placeholder="6자리 코드"><button class="primary" type="submit">인증 <span>→</span></button></form>`;
  const labels = {messages: '새 쪽지', meetings: '만남 요청·확정·하루 전 알림', watch: '지켜보는 연구실의 새 논문', qna: '내 질문의 새 답변'};
  const notify = `<form id="notify-form" class="check-list">${Object.entries(labels).map(([k, l]) => `<label class="check"><input type="checkbox" name="${k}" ${n[k] !== false ? 'checked' : ''}><span>${l}</span></label>`).join('')}</form>`;
  const overseas = `<p>${state.session.overseas ? '동의함: 의미 검색과 AI 연구 가이드를 써요.' : '동의하지 않음: 사전 검색과 기본 가이드만 써요.'} <button class="text-button inline" data-action="toggle-overseas">${state.session.overseas ? '동의 철회' : '동의하기'}</button></p>`;
  let grad = '';
  if (user.role === 'graduate') grad = `<form id="grad-settings-form" class="profile-form"><label class="check"><input type="checkbox" name="contact_consent" ${a.contact_consent ? 'checked' : ''}><span>학생의 쪽지·커피챗 요청 받기</span></label><label class="check"><input type="checkbox" name="show_email" ${a.show_email ? 'checked' : ''}><span>로그인한 사용자에게 내 이메일 보이기</span></label><div class="form-grid"><label>한 달에 받을 새 문의 수<input name="monthly_limit" type="number" min="0" max="30" value="${h(a.monthly_limit ?? 4)}"></label><label>가능한 시간<input name="availability" maxlength="120" value="${h(a.availability || '')}" placeholder="예: 평일 저녁, 금요일 오후"></label></div><button class="secondary" type="submit">선배 설정 저장</button></form>`;
  else if (user.grad_status === 'pending') grad = '<p>선배 인증을 심사하고 있어요. 결과는 메일로 알려 드려요.</p>';
  else grad = `<p>${user.grad_status === 'rejected' ? '이전 신청이 승인되지 않았어요. 내용을 보완해 다시 신청할 수 있어요. ' : ''}대학원생이라면 학교 메일 인증 후 선배로 등록해 후배의 질문에 답할 수 있어요.</p><button class="secondary" data-action="graduate">선배 인증 신청하기 →</button>`;
  return `<section class="settings"><h2>계정 설정</h2><div class="settings-block"><h3>이메일 인증</h3>${verify}</div><div class="settings-block"><h3>알림 메일</h3>${notify}</div><div class="settings-block"><h3>해외 처리 동의 <small>선택</small></h3>${overseas}</div><div class="settings-block"><h3>${user.role === 'graduate' ? '선배 설정' : '선배 인증'}</h3>${grad}</div><details class="settings-block danger"><summary>계정 삭제</summary><p>프로필·탐색 기록·후기·질문이 바로 삭제돼요. 이미 상대가 받은 쪽지는 ‘탈퇴한 사용자’로 표시돼 상대에게만 남아요. 되돌릴 수 없어요.</p><form id="delete-form" class="inline-form"><input name="password" type="password" required placeholder="비밀번호 확인" autocomplete="current-password"><button class="danger-button" type="submit">계정 삭제</button></form></details><p class="micro"><button class="text-button inline" data-action="privacy">개인정보 처리방침</button></p></section>`;
}

// ---- graduate application ----
async function renderGraduate() {
  await refreshSession(); const user = state.session.user;
  if (!user) { renderHome(); showAuth(); return; }
  const labs = (await api('labs')).labs; setView('graduate');
  const ok = user.email_verified && /@postech\.ac\.kr$/i.test(user.email);
  main.innerHTML = `<section class="page-heading"><div class="eyebrow">GRADUATE VERIFICATION</div><h1>선배 인증 신청</h1><p>승인되면 연구실 상세에 선배로 소개되고, 쪽지·커피챗과 익명 질문에 답할 수 있어요.</p></section>${ok ? '' : `<div class="notice strong">학교 메일(@postech.ac.kr)로 가입하고 이메일 인증을 마친 계정만 신청할 수 있어요. 지금 계정: ${h(user.email)} ${user.email_verified ? '(인증됨)' : '(미인증)'}</div>`}<form id="graduate-form" class="profile-form"><label>소속 연구실<select name="lab_id" required><option value="">선택해 주세요</option>${labs.map(l => `<option value="${h(l.id)}">${h(l.department)} · ${h(l.professors.join(', '))} · ${h(l.name)}</option>`).join('')}</select></label><div class="form-grid"><label>과정<select name="program" required>${['석사과정', '박사과정', '석박통합과정', '박사후연구원'].map(p => `<option>${p}</option>`).join('')}</select></label><label>한 달에 받을 새 문의 수<input name="monthly_limit" type="number" min="0" max="30" value="4"></label></div><label>연구 분야<input name="research" required minlength="2" maxlength="120" placeholder="예: 로봇 파지, 3D 비전"></label><label>가능한 시간<input name="availability" maxlength="120" placeholder="예: 평일 저녁"></label><label>확인 메모 <small>운영자만 봐요</small><input name="note" maxlength="300" placeholder="예: 2025년 입학, 지도교수 ○○○"></label><label class="check"><input type="checkbox" name="contact_consent" checked><span>학생의 쪽지·커피챗 요청을 받을게요.</span></label><p id="graduate-error" class="error" role="alert"></p><button class="primary" type="submit" ${ok ? '' : 'disabled'}>신청하기 <span>→</span></button></form>`;
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
  if (r.status === 'done') { el('easy-summary').innerHTML = summaryHTML(r.summary); api('event', {name: 'summary_view'}).catch(() => {}); }
  else if (['queued', 'running'].includes(r.status) && tries < 25) { el('easy-summary').innerHTML = '<p class="micro">최근 논문을 쉬운 말로 정리하고 있어요…</p>'; setTimeout(() => loadSummary(labId, tries + 1), 8000); }
  else el('easy-summary').innerHTML = '';
}
function summaryHTML(s) {
  return `<details class="easy-summary" open><summary>최근 논문 쉽게 읽기 <span class="pill neutral">AI 요약</span></summary><p class="oneliner">${h(s.lab_oneliner)}</p>${s.papers.map(p => `<div class="easy-paper"><p class="ev-title">${h(p.title)} <span class="micro">${h(p.year || '')}</span></p><p>${h(p.plain)}</p>${p.terms.length ? `<dl class="terms">${p.terms.map(t => `<div><dt>${h(t.term)}</dt><dd>${h(t.meaning)}</dd></div>`).join('')}</dl>` : ''}<a class="small-link" href="${h(p.url)}" target="_blank" rel="noopener noreferrer">원문 ↗</a></div>`).join('')}<p class="micro">초록을 바탕으로 AI가 풀어 쓴 설명이에요. 정확한 내용은 원문을 확인하세요.</p></details>`;
}
async function loadWatch(labId) {
  const r = await api(`watch?lab_id=${encodeURIComponent(labId)}`).catch(() => null);
  if (!r || state.lab?.id !== labId || !el('watch-box')) return;
  state.watch = r;
  el('watch-box').innerHTML = `<button class="text-button ${r.watching ? 'on' : ''}" data-action="watch">${r.watching ? '★ 지켜보는 중' : '☆ 새 논문 지켜보기'}</button>${r.new_papers.length ? `<div class="new-papers"><p class="micro">최근 확인된 새 논문</p>${r.new_papers.map(p => `<a href="${h(p.url)}" target="_blank" rel="noopener noreferrer">${h(p.title)} (${h(p.year || '')})</a>`).join('')}</div>` : ''}`;
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
  return `<section id="qna" class="community"><div class="eyebrow">ASK ANONYMOUSLY</div><h2>익명으로 물어보기.</h2><p class="sub">질문자는 ‘익명 학생’으로만 보여요. 이 연구실 인증 선배가 답해요.</p>${ask}${items || '<div class="empty small"><p>아직 질문이 없어요. 첫 질문을 남겨 보세요.</p></div>'}</section>`;
}

// ---- AI research guide ----
function aiGuideHTML(guide) {
  const ai = guide.ai; if (!ai) return '';
  if (ai.status === 'done') return `<section class="ai-guide"><div class="ai-head"><h3>AI가 고른 학부생 연구 주제</h3><span class="pill neutral">AI 제안 · 근거 인용은 원문과 대조했어요</span></div><div class="ai-topics">${ai.topics.map((t, i) => `<article class="topic-card ai"><span class="pill neutral">${h(t.difficulty)}</span><h4>${h(t.title)}</h4><p class="question">${h(t.question)}</p><p>${h(t.interest_link)}</p>${t.courses.length ? `<div class="course-mini"><p>내가 들은 과목과의 연결</p>${t.courses.map(c => `<p><b>${h(c.name)}</b> — ${h(c.concept)}: ${h(c.how_used)}</p>`).join('')}</div>` : ''}${t.gaps.length ? `<p class="micro">더 배우면 좋은 것: ${t.gaps.map(h).join(', ')}</p>` : ''}<p class="first-step"><b>첫 단계</b> ${h(t.first_step)}</p><details><summary>이 주제의 근거</summary>${evidence(t.evidence)}</details><div class="feedback"><span class="micro">이 제안이 도움이 됐나요?</span><button class="text-button inline" data-action="guide-feedback" data-topic="${i}" data-helpful="1">👍 도움 됐어요</button><button class="text-button inline" data-action="guide-feedback" data-topic="${i}" data-helpful="0">👎 아쉬워요</button></div></article>`).join('')}</div>${ai.next_courses.length ? `<div class="ai-next"><h4>다음에 들어 볼 과목</h4>${ai.next_courses.map(c => `<p><b>${h(c.name)}</b> <span class="micro">${h(c.code)}</span> — ${h(c.reason)}</p>`).join('')}</div>` : ''}${ai.caution ? `<p class="micro">${h(ai.caution)}</p>` : ''}</section>`;
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
  if (g.thread_id) return `<button class="explore-button" data-action="open-thread" data-id="${g.thread_id}">대화 이어가기 →</button>`;
  return g.full ? '' : `<button class="explore-button" data-action="coffeechat" data-id="${g.id}">커피챗 요청하기 →</button>`;
}
function openCoffeeChat(id) {
  if (!requireMember('선배에게 연락하려면')) return;
  const g = state.community.graduates.find(x => x.id === id); if (!g) return;
  const user = state.session.user, a = user.account;
  const greeting = `안녕하세요, ${g.name} 선배님. ${[a.department, a.grade, user.nickname].filter(Boolean).join(' ')}입니다. 3분커리에서 연구실을 알아보다 연락드려요.\n\n궁금한 점:\n1. `;
  const slot = n => `<label>후보 ${n}<input type="datetime-local" name="slot" ${n === 1 ? 'data-first' : ''}></label>`;
  openSheet(`<div class="eyebrow">COFFEE CHAT</div><h2 id="sheet-title">${h(g.name)} 선배에게 커피챗 요청</h2><p class="sheet-sub">${h(nameOf(state.lab))} · ${h(g.program)} · ${h(g.research)}${g.availability ? ` · 가능한 시간: ${h(g.availability)}` : ''}</p><form id="coffee-form" data-id="${g.id}"><label>제목<input name="subject" required minlength="2" maxlength="80" value="${h((g.research.split(' · ')[0] || '연구실') + ' 커피챗 요청')}"></label><label>내용<textarea name="body" required minlength="10" maxlength="2000">${h(greeting)}</textarea></label><label class="check"><input type="checkbox" name="with_meeting" checked><span>만남 시간도 함께 제안할게요</span></label><fieldset class="meeting-fields"><div class="form-grid"><label>방식<select name="mode"><option value="online">온라인</option><option value="offline">대면</option></select></label><label>시간<select name="minutes"><option value="20">20분</option><option value="30">30분</option></select></label></div><div class="form-grid three">${slot(1)}${slot(2)}${slot(3)}</div><label>대면 장소 <small>대면일 때만</small><input name="place" maxlength="100" placeholder="예: 학생회관 카페"></label></fieldset><div class="share-preview"><p class="micro">요청과 함께 선배에게 전달되는 내 정보</p><p><b>${h(a.real_name)}</b> (${h(user.nickname)}) · ${h(user.email)}<br>${h([a.school, a.department, a.grade].filter(Boolean).join(' · '))}</p></div><label class="check"><input type="checkbox" name="share_consent" required><span><b>[필수]</b> 위 이름·이메일·프로필을 이 선배에게 전달하는 데 동의합니다.</span></label><p id="sheet-error" class="error" role="alert"></p><button class="primary full" type="submit">요청 보내기 <span>→</span></button></form>`);
}

// ---- reports and blocks ----
function openReport(kind, id) {
  if (!requireMember('신고하려면')) return;
  openSheet(`<div class="eyebrow">REPORT</div><h2 id="sheet-title">신고하기</h2><p class="sheet-sub">운영자가 확인한 뒤 숨김·이용 제한 등 조치해요. 신고자는 공개되지 않아요.</p><form id="report-form" data-kind="${h(kind)}" data-id="${h(id)}"><label>사유<textarea name="reason" required minlength="2" maxlength="500" placeholder="예: 욕설, 개인정보 노출, 허위 정보"></textarea></label><p id="sheet-error" class="error" role="alert"></p><button class="primary full" type="submit">신고 보내기 <span>→</span></button></form>`);
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
        const r = await api('coffeechat', {graduate_id: Number(form.dataset.id), subject: data.get('subject'), body: data.get('body'), share_consent: checked('share_consent'), meeting});
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
