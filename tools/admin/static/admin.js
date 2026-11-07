'use strict';
const main = document.getElementById('main');
const h = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const when = ts => ts ? new Date(ts * 1000).toLocaleString('ko-KR') : '';
async function api(name, body) {
  const r = await fetch('/api/admin/' + name, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}
const table = (cols, rows) => `<table><tr>${cols.map(c => `<th>${h(c[0])}</th>`).join('')}</tr>${rows.map(r => `<tr>${cols.map(c => `<td>${c[1](r)}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${cols.length}" class="muted">없음</td></tr>`}</table>`;
const TABS = {
  async overview() {
    const o = await api('overview');
    const card = (v, l) => `<div class="card"><b>${h(v)}</b><span>${h(l)}</span></div>`;
    const top = Math.max(1, ...o.metrics.funnel.map(f => f.sessions));
    return `<h2>현황</h2><div class="cards">${card(o.users.student || 0, '학생 회원')}${card(o.users.graduate || 0, '선배 회원')}${card(o.verified, '이메일 인증')}${card(o.pending_graduates, '선배 인증 대기')}${card(o.open_reports, '열린 신고')}${card(o.threads, '실제 대화')}${card(o.meetings, '확정된 만남')}${card(o.questions, '익명 질문')}${card(o.watches, '지켜보기')}${card(o.llm.online ? '연결됨' : '꺼짐', 'AI 워커')}${card(o.embedding_online ? '연결됨' : '꺼짐', '임베딩 워커')}${card(o.mail_enabled ? '발송' : '보류', '메일')}</div>
    <p class="muted">마지막 백업: ${o.last_backup ? h(o.last_backup.name) + ' · ' + when(o.last_backup.time) : '없음'} · 지켜보기 점검: ${when(o.watch_last_run) || '아직 없음'} · 메일함: ${h(JSON.stringify(o.outbox))}</p>
    <h2>최근 ${o.metrics.days}일 흐름 (세션 수)</h2>${table([['단계', f => h(f.step)], ['세션', f => h(f.sessions)], ['', f => `<meter max="100" value="${Math.round(f.sessions / top * 100)}"></meter>`]], o.metrics.funnel)}
    <p class="muted">0건 검색 비율 ${h(o.metrics.zero_result_rate)} · AI 가이드 피드백 👍 ${h(o.metrics.guide_feedback.up)} 👎 ${h(o.metrics.guide_feedback.down)} · 실험군별: ${h(JSON.stringify(o.metrics.arms))}</p>
    <h2>결과가 0건이었던 검색어 (90일 보관)</h2>${table([['검색어', z => h(z.text)], ['횟수', z => h(z.n)]], o.metrics.zero_queries)}`;
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
    return `<h2>사용자</h2><form id="user-search"><input name="q" value="${h(TABS.q || '')}" placeholder="이메일·별명 검색"> <button class="act plain">검색</button></form><br>${table([['ID', u => h(u.id)], ['이메일(일부)', u => h(u.email)], ['별명', u => h(u.nickname)], ['역할', u => h(u.role) + (u.dummy ? ' (더미)' : '')], ['연구실', u => h(u.lab)], ['상태', u => [u.email_verified ? '인증' : '', u.suspended ? '정지' : '', u.deleted ? '탈퇴' : '', u.grad_status || ''].filter(Boolean).join(' · ')], ['', u => u.deleted ? '' : `<button class="act ${u.suspended ? 'ok' : 'no'}" data-suspend="${u.id}" data-on="${u.suspended ? 0 : 1}">${u.suspended ? '정지 해제' : '이용 정지'}</button>`]], d.users)}`;
  },
  async mail() {
    const d = await api('outbox');
    return `<h2>메일 발송함</h2><p class="muted">${d.mail_enabled ? 'SMTP 설정됨' : 'SMTP 미설정: 메일은 보내지 않고 보류(held) 상태로 쌓여요. .local/mail.json을 넣고 재시작하세요.'}</p><button class="act plain" data-mail-retry>보류·실패 메일 다시 보내기</button><br><br>${table([['받는 사람', m => h(m.to_addr)], ['제목', m => h(m.subject)], ['종류', m => h(m.kind)], ['상태', m => h(m.status) + (m.error ? ` (${h(m.error)})` : '')], ['만든 시각', m => when(m.created)]], d.outbox)}`;
  },
  async ai() {
    const o = await api('overview');
    return `<h2>AI 작업 (연구 가이드·논문 요약)</h2><p>워커: ${o.llm.online ? '연결됨' : '꺼짐 — 개발 VM의 tmux 세션 curri-llm을 확인하세요'} · 상태별: ${h(JSON.stringify(o.llm.counts))}</p><button class="act plain" data-prefill>전체 연구실 쉬운 요약 미리 만들기</button> <button class="act plain" data-watch-run>지켜보기 점검 지금 실행</button><br><br>${table([['ID', j => h(j.id)], ['종류', j => h(j.kind)], ['상태', j => h(j.status)], ['시도', j => h(j.attempts)], ['초', j => h(j.seconds)], ['오류', j => h(j.error)], ['요청', j => when(j.created)]], o.llm.recent)}`;
  },
  async experiments() {
    const o = await api('overview');
    return `<h2>실험 비율</h2><p class="muted">세션마다 무작위로 고정 배정돼요. 예: {"guide": {"R": 0.5, "A": 0.5}} — R은 AI 가이드, A는 기본 가이드만.</p><textarea id="exp">${h(JSON.stringify(o.experiments, null, 1))}</textarea><button class="act ok" data-exp-save>저장</button>`;
  },
  async audit() {
    const d = await api('audit');
    return `<h2>관리자 감사 로그 (2년 보관)</h2>${table([['시각', a => when(a.ts)], ['관리자', a => h(a.admin)], ['작업', a => h(a.action)], ['내용', a => h(a.detail)]], d.audit)}`;
  },
};
const NAMES = {overview: '개요', graduates: '선배 인증', reports: '신고', users: '사용자', mail: '메일', ai: 'AI 작업', experiments: '실험', audit: '감사 로그'};
let current = 'overview';
async function show(tab) {
  current = tab;
  document.getElementById('tabs').innerHTML = Object.entries(NAMES).map(([k, v]) => `<button data-tab="${k}" class="${k === tab ? 'on' : ''}">${v}</button>`).join('');
  try { main.innerHTML = await TABS[tab](); } catch (e) { main.innerHTML = `<p class="no">${h(e.message)}</p>`; }
}
async function run(work, message) { try { await work(); if (message) alert(message); await show(current); } catch (e) { alert(e.message); } }
document.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.tab) return show(b.dataset.tab);
  if (b.dataset.grad) { const ok = b.dataset.ok === '1'; const note = ok ? '' : (prompt('반려 사유(신청자에게 메일로 전달)') || ''); return run(() => api('graduates/decide', {user_id: Number(b.dataset.grad), approve: ok, note})); }
  if (b.dataset.report) return run(() => api('reports/resolve', {id: Number(b.dataset.report), action: b.dataset.do}));
  if (b.dataset.suspend) return run(() => api('users/suspend', {user_id: Number(b.dataset.suspend), suspended: b.dataset.on === '1'}));
  if ('mailRetry' in b.dataset) return run(() => api('mail/retry', {}));
  if ('prefill' in b.dataset) return run(async () => { const r = await api('summaries/prefill', {}); alert(`${r.queued}곳 요약 작업을 넣었어요.`); });
  if ('watchRun' in b.dataset) return run(() => api('watch/run', {}), '지켜보기 점검을 시작했어요.');
  if ('expSave' in b.dataset) return run(() => api('experiments', {experiments: JSON.parse(document.getElementById('exp').value)}), '저장했어요.');
});
document.addEventListener('submit', e => { if (e.target.id === 'user-search') { e.preventDefault(); TABS.q = new FormData(e.target).get('q'); show('users'); } });
show('overview');
