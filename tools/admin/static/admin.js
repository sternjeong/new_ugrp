'use strict';
const main = document.getElementById('main');
const h = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const when = ts => ts ? new Date(ts * 1000).toLocaleString('ko-KR') : '';
const ago = s => s < 3600 ? `${Math.round(s / 60)}분` : s < 86400 ? `${Math.round(s / 3600)}시간` : `${Math.round(s / 86400)}일`;
let me = null;
async function call(path, body) {
  const r = await fetch(path, body === undefined ? {credentials: 'same-origin'} : {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && data.code === 'login') { me = null; renderLogin(); throw new Error('로그인이 필요해요.'); }
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}
const api = (name, body) => call('/api/admin/' + name, body);
const table = (cols, rows) => `<table><tr>${cols.map(c => `<th>${h(c[0])}</th>`).join('')}</tr>${rows.map(r => `<tr>${cols.map(c => `<td>${c[1](r)}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${cols.length}" class="muted">없음</td></tr>`}</table>`;
const card = (v, l, cls = '') => `<div class="card"><b class="${cls}">${h(v)}</b><span>${h(l)}</span></div>`;
const TABS = {
  async overview() {
    const o = await api('overview');
    const top = Math.max(1, ...o.metrics.funnel.map(f => f.sessions));
    return `<h2>현황</h2><div class="cards">${card(o.users.student || 0, '학생 회원')}${card(o.users.graduate || 0, '선배 회원')}${card(o.verified, '이메일 인증')}${card(o.pending_graduates, '선배 인증 대기', o.pending_graduates ? 'bad' : '')}${card(o.open_reports, '열린 신고', o.open_reports ? 'bad' : '')}${card(o.threads, '실제 대화')}${card(o.meetings, '확정된 만남')}${card(o.questions, '익명 질문')}${card(o.watches, '지켜보기')}</div>
    <h2>최근 ${o.metrics.days}일 흐름 (세션 수)</h2>${table([['단계', f => h(f.step)], ['세션', f => h(f.sessions)], ['', f => `<meter max="100" value="${Math.round(f.sessions / top * 100)}"></meter>`]], o.metrics.funnel)}
    <p class="muted">0건 검색 비율 ${h(o.metrics.zero_result_rate)} · AI 가이드 피드백 👍 ${h(o.metrics.guide_feedback.up)} 👎 ${h(o.metrics.guide_feedback.down)} · 실험군별: ${h(JSON.stringify(o.metrics.arms))}</p>
    <h2>결과가 0건이었던 검색어 (90일 보관)</h2>${table([['검색어', z => h(z.text)], ['횟수', z => h(z.n)]], o.metrics.zero_queries)}`;
  },
  async status() {
    const [e, host] = await Promise.all([api('errors'), call('/host')]);
    const s = e.system, mem = s.memory_mb, hm = host.memory_mb;
    const ok = (v, yes, no) => v ? `<span class="good">${yes}</span>` : `<span class="bad">${no}</span>`;
    const lastBackup = host.backups[host.backups.length - 1];
    return `<h2>서비스 상태</h2><div class="cards">${card(ago(s.service_uptime_s), '서비스 가동 시간')}${card(`${mem.available}/${mem.total}MB`, '서비스 서버 여유 메모리', mem.available < 150 ? 'bad' : '')}${card(`${s.disk_gb.free}GB`, '서비스 서버 남은 디스크', s.disk_gb.free < 3 ? 'bad' : '')}${card(s.load ? s.load.map(x => x.toFixed(2)).join(' ') : '-', '부하(1·5·15분)')}${card(`${s.db_mb}MB`, 'DB 크기')}${card(`${hm.available}/${hm.total}MB`, '관리자 VM 여유 메모리')}</div>
    <p>AI 워커 ${ok(e.llm_online, '연결됨', '꺼짐 (개발 VM tmux curri-llm 확인)')} · 임베딩 워커 ${ok(e.embedding_online, '연결됨', '꺼짐 (첫 검색 때 자동 시작)')} · 메일 ${ok(e.mail_enabled, '발송', '미설정')} · 마지막 관리자 VM 백업 ${lastBackup ? `${h(lastBackup.name)} (${when(lastBackup.time)})` : '<span class="bad">없음</span>'}</p>
    <h2>서비스 오류 (최근 30일)</h2><p class="muted">요청 처리 실패와 백그라운드 작업 오류예요. 같은 위치가 반복되면 코드를 확인해야 해요.</p>${table([['시각', x => when(x.ts)], ['위치', x => h(x.place)], ['종류', x => h(x.kind)], ['코드', x => `<code>${h(x.detail)}</code>`]], e.errors)}
    <h2>실패한 메일</h2>${table([['ID', x => h(x.id)], ['종류', x => h(x.kind)], ['오류', x => h(x.error)], ['시도', x => h(x.attempts)], ['시각', x => when(x.created)]], e.failed_mail)}
    <h2>실패한 AI 작업</h2>${table([['ID', x => h(x.id)], ['종류', x => h(x.kind)], ['오류', x => h(x.error)], ['시도', x => h(x.attempts)], ['시각', x => when(x.created)]], e.failed_jobs)}
    <h2>관리자 VM 백업 (30일 보관)</h2>${table([['파일', b => h(b.name)], ['크기', b => h(b.mb) + 'MB'], ['시각', b => when(b.time)]], host.backups.slice().reverse())}`;
  },
  async graduates() {
    const d = await api('graduates');
    return `<h2>선배 인증 대기</h2><p class="muted">학교 메일 인증은 끝난 신청이에요. 연구실 홈페이지 구성원 명단 등으로 소속을 확인한 뒤 승인하세요.</p>${table([['신청자', g => `${h(g.nickname)}<br><span class="muted">${h(g.email)}</span>`], ['연구실', g => h(g.lab)], ['과정·분야', g => `${h(g.program)}<br>${h(g.research)}`], ['메모', g => h(g.note)], ['처리', g => `<button class="act ok" data-grad="${g.id}" data-ok="1">승인</button><button class="act no" data-grad="${g.id}" data-ok="0">반려</button>`]], d.pending)}`;
  },
  async reports() {
    const d = await api('reports');
    return `<h2>열린 신고</h2>${table([['대상', r => `${h(r.kind)} #${h(r.ref_id)}<br><span class="muted">작성자 ${h(r.author_id)}</span>`], ['내용', r => h(r.content)], ['사유', r => h(r.reason)], ['접수', r => when(r.created)], ['처리', r => `<button class="act no" data-report="${r.id}" data-do="hide">숨김</button><button class="act no" data-report="${r.id}" data-do="suspend">숨김+이용 제한</button><button class="act plain" data-report="${r.id}" data-do="dismiss">기각</button>`]], d.reports)}`;
  },
  async users() {
    const d = await api('users' + (TABS.q ? '?q=' + encodeURIComponent(TABS.q) : ''));
    return `<h2>회원 관리</h2><form id="user-search" class="inline"><input name="q" value="${h(TABS.q || '')}" placeholder="이메일·별명 검색"><button class="act plain">검색</button></form>${table([['ID', u => h(u.id)], ['이메일(일부)', u => h(u.email)], ['별명', u => h(u.nickname)], ['역할', u => h(u.role) + (u.dummy ? ' (더미)' : '')], ['연구실', u => h(u.lab)], ['상태', u => [u.email_verified ? '인증' : '', u.suspended ? '정지' : '', u.deleted ? '탈퇴' : '', u.grad_status || ''].filter(Boolean).join(' · ')], ['가입', u => when(u.created)], ['', u => u.deleted ? '' : `<button class="act ${u.suspended ? 'ok' : 'no'}" data-suspend="${u.id}" data-on="${u.suspended ? 0 : 1}">${u.suspended ? '정지 해제' : '이용 정지'}</button>`]], d.users)}`;
  },
  async mail() {
    const d = await api('outbox');
    return `<h2>메일 발송함</h2><p class="muted">${d.mail_enabled ? 'SMTP 설정됨' : 'SMTP 미설정: 메일은 보류(held) 상태로 쌓여요.'}</p><button class="act plain" data-mail-retry>보류·실패 메일 다시 보내기</button><br><br>${table([['받는 사람', m => h(m.to_addr)], ['제목', m => h(m.subject)], ['종류', m => h(m.kind)], ['상태', m => h(m.status) + (m.error ? ` (${h(m.error)})` : '')], ['만든 시각', m => when(m.created)]], d.outbox)}`;
  },
  async ai() {
    const o = await api('overview');
    return `<h2>AI 작업 (연구 가이드·논문 요약)</h2><p>워커: ${o.llm.online ? '<span class="good">연결됨</span>' : '<span class="bad">꺼짐 — 개발 VM의 tmux 세션 curri-llm을 확인하세요</span>'} · 상태별: ${h(JSON.stringify(o.llm.counts))}</p><div class="inline"><button class="act plain" data-prefill>전체 연구실 쉬운 요약 미리 만들기</button><button class="act plain" data-watch-run>지켜보기 점검 지금 실행</button></div>${table([['ID', j => h(j.id)], ['종류', j => h(j.kind)], ['상태', j => h(j.status)], ['시도', j => h(j.attempts)], ['초', j => h(j.seconds)], ['오류', j => h(j.error)], ['요청', j => when(j.created)]], o.llm.recent)}`;
  },
  async experiments() {
    const o = await api('overview');
    return `<h2>실험 비율</h2><p class="muted">세션마다 무작위로 고정 배정돼요. 예: {"guide": {"R": 0.5, "A": 0.5}} — R은 AI 가이드, A는 기본 가이드만.</p><textarea id="exp">${h(JSON.stringify(o.experiments, null, 1))}</textarea><button class="act ok" data-exp-save>저장</button>`;
  },
  async admins() {
    const d = await call('/admins');
    return `<h2>관리자 계정</h2>${table([['이름', a => h(a.name) + (a.name === d.me ? ' (나)' : '')], ['만든 날', a => when(a.created)], ['', a => a.name === d.me ? '' : `<button class="act no" data-admin-del="${h(a.name)}">삭제</button>`]], d.admins)}
    <h2>관리자 추가</h2><form id="admin-add" class="inline"><input name="name" required pattern="[A-Za-z0-9_.\\-]{2,32}" placeholder="이름(영문·숫자)"><input name="password" type="password" required minlength="12" placeholder="비밀번호 12자 이상" autocomplete="new-password"><button class="act ok">추가</button></form>
    <h2>내 비밀번호 바꾸기</h2><form id="admin-pw" class="inline"><input name="current" type="password" required placeholder="현재 비밀번호" autocomplete="current-password"><input name="password" type="password" required minlength="12" placeholder="새 비밀번호 12자 이상" autocomplete="new-password"><button class="act ok">변경</button></form>
    <p class="muted">관리자 계정을 사람마다 따로 만들고 공유하지 마세요. 그만두면 바로 삭제하세요. 계정 변경과 로그인은 관리자 VM의 admin_accounts.log에 남아요.</p>`;
  },
  async audit() {
    const d = await api('audit');
    return `<h2>감사 로그 (2년 보관)</h2>${table([['시각', a => when(a.ts)], ['관리자', a => h(a.admin)], ['작업', a => h(a.action)], ['내용', a => h(a.detail)]], d.audit)}`;
  },
};
const NAMES = {overview: '개요', status: '상태·오류', users: '회원', graduates: '선배 인증', reports: '신고', mail: '메일', ai: 'AI 작업', experiments: '실험', admins: '관리자 계정', audit: '감사 로그'};
let current = 'overview';
function renderLogin() {
  document.getElementById('tabs').innerHTML = ''; document.getElementById('who').innerHTML = '';
  main.innerHTML = `<form id="login" class="login"><h1>관리자 로그인</h1><p class="muted">3분커리 서비스 운영 콘솔이에요.</p><label>이름<input name="name" required autocomplete="username"></label><label>비밀번호<input name="password" type="password" required autocomplete="current-password"></label><p class="error" id="login-error"></p><button>로그인</button></form>`;
}
async function show(tab) {
  current = tab;
  document.getElementById('tabs').innerHTML = Object.entries(NAMES).map(([k, v]) => `<button data-tab="${k}" class="${k === tab ? 'on' : ''}">${v}</button>`).join('');
  document.getElementById('who').innerHTML = `${h(me)} · <button class="act plain" data-logout>로그아웃</button>`;
  try { main.innerHTML = await TABS[tab](); } catch (e) { if (me) main.innerHTML = `<p class="bad">${h(e.message)}</p>`; }
}
async function run(work, message) { try { await work(); if (message) alert(message); await show(current); } catch (e) { if (me) alert(e.message); } }
document.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.tab) return show(b.dataset.tab);
  if ('logout' in b.dataset) return call('/logout', {}).then(() => { me = null; renderLogin(); });
  if (b.dataset.grad) { const ok = b.dataset.ok === '1'; const note = ok ? '' : (prompt('반려 사유(신청자에게 메일로 전달)') || ''); return run(() => api('graduates/decide', {user_id: Number(b.dataset.grad), approve: ok, note})); }
  if (b.dataset.report) return run(() => api('reports/resolve', {id: Number(b.dataset.report), action: b.dataset.do}));
  if (b.dataset.suspend) { if (!confirm('이 회원의 상태를 바꿀까요?')) return; return run(() => api('users/suspend', {user_id: Number(b.dataset.suspend), suspended: b.dataset.on === '1'})); }
  if (b.dataset.adminDel) { if (!confirm(`${b.dataset.adminDel} 관리자를 삭제할까요?`)) return; return run(() => call('/admins', {action: 'delete', name: b.dataset.adminDel})); }
  if ('mailRetry' in b.dataset) return run(() => api('mail/retry', {}));
  if ('prefill' in b.dataset) return run(async () => { const r = await api('summaries/prefill', {}); alert(`${r.queued}곳 요약 작업을 넣었어요.`); });
  if ('watchRun' in b.dataset) return run(() => api('watch/run', {}), '지켜보기 점검을 시작했어요.');
  if ('expSave' in b.dataset) return run(() => api('experiments', {experiments: JSON.parse(document.getElementById('exp').value)}), '저장했어요.');
});
document.addEventListener('submit', async e => {
  e.preventDefault(); const f = new FormData(e.target);
  if (e.target.id === 'login') {
    try { me = (await call('/login', {name: f.get('name'), password: f.get('password')})).name; show('overview'); }
    catch (err) { document.getElementById('login-error').textContent = err.message; }
  }
  else if (e.target.id === 'user-search') { TABS.q = f.get('q'); show('users'); }
  else if (e.target.id === 'admin-add') run(() => call('/admins', {action: 'add', name: f.get('name'), password: f.get('password')}), '관리자를 추가했어요.');
  else if (e.target.id === 'admin-pw') run(() => call('/admins', {action: 'password', current: f.get('current'), password: f.get('password')}), '비밀번호를 바꿨어요.');
});
call('/me').then(r => { me = r.name; if (me) show('overview'); else renderLogin(); }).catch(() => renderLogin());
