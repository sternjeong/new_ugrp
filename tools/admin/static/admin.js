'use strict';
// 3분커리 운영 콘솔. Talks to the admin server (same origin), which forwards /api/admin/* to the service.
const $ = id => document.getElementById(id);
const main = $('main');
const h = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const when = ts => ts ? new Date(ts * 1000).toLocaleString('ko-KR', {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}) : '';
const ago = s => s < 3600 ? `${Math.max(1, Math.round(s / 60))}분` : s < 86400 ? `${Math.round(s / 3600)}시간` : `${Math.round(s / 86400)}일`;
const pct = (a, b) => b ? Math.round(a / b * 100) + '%' : '–';
let me = null, current = 'overview', badges = {}, autoTimer = null;

// ---- server calls ----
async function call(path, body) {
  const r = await fetch(path, body === undefined ? {credentials: 'same-origin'} : {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && data.code === 'login') { me = null; renderLogin(); throw new Error('로그인이 필요해요.'); }
  if (!r.ok) throw new Error(data.error || `요청 실패 (HTTP ${r.status})`);
  return data;
}
const api = (name, body) => call('/api/admin/' + name, body);

// ---- feedback to the operator: toasts and a modal instead of alert/confirm/prompt ----
function toast(text, err = false) {
  const t = document.createElement('div'); t.className = 'toast' + (err ? ' err' : ''); t.textContent = text;
  $('toasts').appendChild(t); setTimeout(() => t.remove(), 4200);
}
function modal({title, text = '', input = null, okLabel = '확인', danger = false}) {
  return new Promise(resolve => {
    $('modal-title').textContent = title; $('modal-text').textContent = text;
    $('modal-extra').innerHTML = input ? `<textarea class="field short" id="modal-input" placeholder="${h(input)}"></textarea>` : '';
    $('modal-ok').textContent = okLabel; $('modal-ok').className = 'btn ' + (danger ? 'danger' : 'primary');
    const dialog = $('modal');
    dialog.onclose = () => resolve(dialog.returnValue === 'ok' ? (input ? ($('modal-input')?.value || '') : true) : null);
    dialog.showModal();
  });
}
async function run(work, done) {
  try { await work(); if (done) toast(done); await show(current, true); } catch (e) { if (me) toast(e.message, true); }
}

// ---- building blocks ----
const kpi = (value, label, state = '') => `<div class="card kpi ${state}"><b>${h(value)}</b><span>${h(label)}</span></div>`;
const pill = (text, tone = '') => `<span class="pill ${tone}">${h(text)}</span>`;
const dot = on => `<span class="dot ${on ? 'on' : 'off'}"></span>`;
function table(cols, rows, {filter = false, empty = '없음'} = {}) {
  const id = 't' + Math.random().toString(36).slice(2, 8);
  const head = filter ? `<div class="filter mb8"><input placeholder="표 안에서 찾기" data-filter="${id}"></div>` : '';
  const body = rows.map(r => `<tr>${cols.map(c => `<td class="${c[2] || ''}">${c[1](r)}</td>`).join('')}</tr>`).join('');
  return `${head}<div class="table-wrap"><table id="${id}"><thead><tr>${cols.map(c => `<th>${h(c[0])}</th>`).join('')}</tr></thead><tbody>${body || `<tr><td colspan="${cols.length}" class="empty">${h(empty)}</td></tr>`}</tbody></table></div>`;
}
const section = (title, sub = '', right = '') => `<div class="section"><div><h2>${h(title)}</h2>${sub ? `<p>${h(sub)}</p>` : ''}</div>${right}</div>`;
function bars(items, tone = '') {
  const top = Math.max(1, ...items.map(i => i.n));
  return items.map(i => `<div class="bar"><span>${h(i.label)}</span><div class="track"><div class="fill ${i.tone || tone}" data-w="${Math.round(i.n / top * 100)}"></div></div><span>${h(i.right ?? i.n)}</span></div>`).join('') || '<p class="muted">아직 데이터가 없어요.</p>';
}
function spark(byDay, keys, days = 14) {
  const dates = [...Array(days)].map((_, i) => { const d = new Date(Date.now() - (days - 1 - i) * 86400000); return d.toISOString().slice(0, 10); });
  const series = keys.map(k => dates.map(d => (byDay[d] || {})[k] || 0));
  const max = Math.max(1, ...series.flat()), W = 600, H = 120, P = 18;
  const x = i => P + i * (W - 2 * P) / (days - 1), y = v => H - P - v / max * (H - 2 * P);
  const path = s => s.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const area = `${path(series[0])}L${x(days - 1)},${H - P}L${x(0)},${H - P}Z`;
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="일별 추이"><path class="area" d="${area}"/>${series.map((s, i) => `<path class="${i ? 'line2' : 'line'}" d="${path(s)}"/>`).join('')}<text x="${P}" y="${H - 3}">${dates[0].slice(5)}</text><text x="${W - P - 28}" y="${H - 3}">${dates[days - 1].slice(5)}</text><text x="${P}" y="11">최대 ${max}</text></svg>`;
}
function download(name, data) {
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], {type: 'application/json'}));
  a.download = name; a.click(); URL.revokeObjectURL(a.href);
}
const STEP_NAMES = {search: '검색', explore: '연구실 열람', guide_request: '가이드 요청', guide_ready: 'AI 가이드 완성', save: '후보 저장', contact: '쪽지', coffeechat: '커피챗'};

// ---- pages ----
const PAGES = {
  overview: {title: '개요', sub: '최근 14일 서비스 흐름과 처리할 일', async render() {
    const o = await api('overview'); badges = {graduates: o.pending_graduates, reports: o.open_reports, feedback: o.feedback_new || 0, status: (o.llm.online ? 0 : 1) + (o.mail_enabled ? 0 : 1)}; paintNav();
    const f = o.metrics.funnel, first = f[0]?.sessions || 0;
    const todo = [o.pending_graduates && `선배 인증 ${o.pending_graduates}건 대기`, o.open_reports && `신고 ${o.open_reports}건 처리 필요`, o.feedback_new && `새 의견 ${o.feedback_new}건`, !o.llm.online && 'AI 워커 꺼짐', !o.last_backup && '관리자 VM 백업 없음'].filter(Boolean);
    return `${todo.length ? `<div class="card kpi warn mb12"><b class="title15">오늘 처리할 일</b><span>${todo.map(h).join(' · ')}</span></div>` : ''}
    <div class="grid cards">${kpi(o.users.student || 0, '학생 회원')}${kpi(o.users.graduate || 0, '선배 회원')}${kpi(o.verified, '이메일 인증')}${kpi(o.metrics.search_sessions, '검색한 세션 (14일)')}${kpi(o.threads, '실제 대화')}${kpi(o.meetings, '확정된 만남')}${kpi(o.questions, '익명 질문')}${kpi(o.watches, '지켜보기')}</div>
    <div class="grid two mt12">
      <div class="card"><h3>일별 추이 <span class="legend"><span><i></i>검색</span><span><i class="g"></i>연구실 열람</span></span></h3>${spark(o.metrics.by_day, ['search', 'explore'])}</div>
      <div class="card"><h3>이용 흐름 <small>세션 수 · 검색 대비</small></h3>${bars(f.map(s => ({label: STEP_NAMES[s.step] || s.step, n: s.sessions, right: `${s.sessions} · ${pct(s.sessions, first)}`})))}</div>
    </div>
    <div class="grid two mt12">
      <div class="card"><h3>시스템</h3><div class="status-list"><div class="status-row"><span>${dot(o.llm.online)}AI 워커</span><small>${o.llm.online ? '연결됨' : '꺼짐'}</small></div><div class="status-row"><span>${dot(o.embedding_online)}의미 검색 워커</span><small>${o.embedding_online ? '연결됨' : '첫 검색 때 자동 시작'}</small></div><div class="status-row"><span>${dot(o.mail_enabled)}메일 발송</span><small>${o.mail_enabled ? '설정됨' : '미설정'}</small></div><div class="status-row"><span>${dot(!!o.last_backup)}마지막 서비스 백업</span><small>${o.last_backup ? when(o.last_backup.time) : '없음'}</small></div></div></div>
      <div class="card"><h3>결과 0건 검색어 <small>0건 비율 ${pct(o.metrics.zero_result_rate * 100, 100)}</small></h3>${o.metrics.zero_queries.length ? o.metrics.zero_queries.slice(0, 8).map(z => `<div class="status-row"><span>${h(z.text)}</span><small>${z.n}회</small></div>`).join('') : '<p class="muted">없어요 👍</p>'}<p class="mt10"><button class="btn sm" data-go="feedback">사전 확장 후보 보기 →</button></p></div>
    </div>`;
  }},
  status: {title: '상태·오류', sub: '서버 자원, 워커 연결, 최근 30일 오류', auto: true, async render() {
    const [e, host] = await Promise.all([api('errors'), call('/host')]);
    const s = e.system, mem = s.memory_mb, hm = host.memory_mb, last = host.backups[host.backups.length - 1];
    const memLow = mem.available < 150, diskLow = s.disk_gb.free < 3;
    return `<div class="grid cards">${kpi(ago(s.service_uptime_s), '서비스 가동 시간')}${kpi(`${mem.available}MB`, `서비스 서버 여유 메모리 / ${mem.total}MB`, memLow ? 'alert' : '')}${kpi(`${s.disk_gb.free}GB`, '서비스 서버 남은 디스크', diskLow ? 'alert' : '')}${kpi(s.load ? s.load[0].toFixed(2) : '–', '부하 (1분)')}${kpi(`${s.db_mb}MB`, 'DB 크기')}${kpi(`${hm.available}MB`, '관리자 VM 여유 메모리')}${kpi(e.errors.length, '오류 (30일)', e.errors.length ? 'warn' : 'good')}</div>
    <div class="card mt12"><h3>연결 상태</h3><div class="status-list"><div class="status-row"><span>${dot(e.llm_online)}AI 워커 (AI 가이드·논문 요약)</span><small>${e.llm_online ? '연결됨' : '꺼짐 — 개발 VM의 tmux 세션 curri-llm 확인'}</small></div><div class="status-row"><span>${dot(e.embedding_online)}의미 검색 워커 (Kaggle)</span><small>${e.embedding_online ? '연결됨' : '꺼짐 — 첫 검색 때 자동 시작'}</small></div><div class="status-row"><span>${dot(e.mail_enabled)}메일</span><small>${e.mail_enabled ? 'SMTP 설정됨' : '미설정'}</small></div><div class="status-row"><span>${dot(!!last)}관리자 VM 백업</span><small>${last ? `${h(last.name)} · ${when(last.time)}` : '없음'}</small></div></div></div>
    ${section('서비스 오류', '같은 코드 위치가 반복되면 코드를 확인해야 해요. 요청 내용·개인정보는 남기지 않아요.')}${table([['시각', x => when(x.ts)], ['위치', x => h(x.place)], ['종류', x => pill(x.kind, 'red')], ['코드', x => `<code>${h(x.detail)}</code>`]], e.errors, {filter: e.errors.length > 8, empty: '오류가 없어요 👍'})}
    <div class="grid two mt12"><div>${section('실패한 메일')}${table([['종류', x => h(x.kind)], ['오류', x => h(x.error)], ['시도', x => x.attempts, 'num'], ['시각', x => when(x.created)]], e.failed_mail)}</div><div>${section('실패한 AI 작업')}${table([['종류', x => h(x.kind)], ['오류', x => h(x.error)], ['시도', x => x.attempts, 'num'], ['시각', x => when(x.created)]], e.failed_jobs)}</div></div>
    ${section('관리자 VM 백업', '매일 05:00 서비스 DB 사본을 받아 30일 보관')}${table([['파일', b => h(b.name)], ['크기', b => b.mb + 'MB', 'num'], ['시각', b => when(b.time)]], host.backups.slice().reverse())}`;
  }},
  users: {title: '회원', sub: '이메일은 일부만 보여요', async render() {
    const d = await api('users' + (PAGES.users.q ? '?q=' + encodeURIComponent(PAGES.users.q) : ''));
    const state = u => [u.email_verified && pill('인증', 'green'), u.suspended && pill('정지', 'red'), u.deleted && pill('탈퇴'), u.grad_status && pill('선배 ' + u.grad_status, 'amber'), u.dummy && pill('더미')].filter(Boolean).join(' ');
    return `<form id="user-search" class="filter mb12"><input name="q" value="${h(PAGES.users.q || '')}" placeholder="이메일·별명으로 서버에서 찾기"><button class="btn">검색</button></form>
    ${table([['ID', u => u.id, 'num'], ['이메일', u => h(u.email)], ['별명', u => h(u.nickname)], ['역할', u => u.role === 'graduate' ? pill('선배', 'dark') : '학생'], ['연구실', u => h(u.lab)], ['상태', state], ['가입', u => when(u.created)], ['', u => u.deleted ? '' : `<button class="btn sm ${u.suspended ? 'ok' : 'danger'}" data-suspend="${u.id}" data-on="${u.suspended ? 0 : 1}">${u.suspended ? '정지 해제' : '이용 정지'}</button>`]], d.users, {filter: true})}`;
  }},
  graduates: {title: '선배 인증', sub: '학교 메일 인증까지 끝난 신청이에요. 연구실 구성원 명단으로 소속을 확인한 뒤 승인하세요.', async render() {
    const d = await api('graduates');
    return table([['신청자', g => `<b>${h(g.nickname)}</b><br><span class="muted">${h(g.email)}</span>`], ['연구실', g => h(g.lab)], ['과정·분야', g => `${pill(g.program)}<br>${h(g.research)}`], ['메모', g => h(g.note)], ['가능 시간', g => h(g.availability)], ['', g => `<div class="inline"><button class="btn sm ok" data-grad="${g.id}" data-ok="1">승인</button><button class="btn sm danger" data-grad="${g.id}" data-ok="0">반려</button></div>`]], d.pending, {empty: '대기 중인 신청이 없어요'});
  }},
  reports: {title: '신고', sub: '숨김은 글만 가리고, 이용 제한은 작성자 로그인을 막아요', async render() {
    const d = await api('reports');
    return table([['대상', r => `${pill(r.kind)} #${r.ref_id}<br><span class="muted">작성자 ${h(r.author_id)}</span>`], ['내용', r => h(r.content)], ['사유', r => h(r.reason)], ['접수', r => when(r.created)], ['', r => `<div class="inline"><button class="btn sm danger" data-report="${r.id}" data-do="hide">숨김</button><button class="btn sm danger" data-report="${r.id}" data-do="suspend">숨김+이용 제한</button><button class="btn sm" data-report="${r.id}" data-do="dismiss">기각</button></div>`]], d.reports, {empty: '열린 신고가 없어요 👍'});
  }},
  feedback: {title: '피드백', sub: '최근 30일 학생 평가와 의견 · 검색 엔진에 돌려주는 신호', async render() {
    const d = await api('feedback');
    const k = d.by_kind, r = k.result || {up: 0, down: 0, n: 0}, g = k.guide || {up: 0, down: 0, n: 0}, s = k.search || {ratings: [0, 0, 0, 0, 0], n: 0}, m = k.meeting || {ratings: [0, 0, 0, 0, 0], n: 0}, sv = k.service || {ratings: [0, 0, 0, 0, 0], n: 0};
    const avg = x => x.n ? (x.ratings.reduce((a, c, i) => a + c * (i + 1), 0) / x.ratings.reduce((a, c) => a + c, 0) || 0).toFixed(1) : '–';
    const found = s.ratings[4], partial = s.ratings[2], missed = s.ratings[0] + s.ratings[1];
    const sig = d.signals || {};
    const comments = d.comments.map(c => `<div class="comment"><p>${h(c.comment)}</p><div class="meta">${pill({result: '추천 결과', search: '검색', guide: 'AI 가이드', meeting: '만남', service: '서비스'}[c.kind] || c.kind, c.status === 'new' ? 'amber' : '')}${c.rating ? `<span>${'★'.repeat(c.rating)}</span>` : ''}${c.helpful === 1 ? '👍' : c.helpful === 0 ? '👎' : ''}${c.lab ? `<span>${h(c.lab)}</span>` : ''}${c.query ? `<span>“${h(c.query)}”</span>` : ''}<span>${when(c.ts)}</span><span class="push">${c.status !== 'done' ? `<button class="btn sm" data-fb="${c.id}" data-status="done">처리 완료</button>` : pill('완료', 'green')}</span></div></div>`).join('');
    return `<div class="grid cards">${kpi(r.n ? pct(r.up, r.up + r.down) : '–', `추천 결과 👍 비율 (${r.n}건)`, r.n && r.up < r.down ? 'alert' : '')}${kpi(s.n ? pct(found, s.n) : '–', `검색 만족 "찾았어요" (${s.n}건)`)}${kpi(g.n ? pct(g.up, g.up + g.down) : '–', `AI 가이드 👍 비율 (${g.n}건)`)}${kpi(avg(m), `만남 평점 (${m.n}건)`)}${kpi(avg(sv), `서비스 평점 (${sv.n}건)`)}${kpi((sig.open || 0) + (sig.save || 0) + (sig.contact || 0), '암묵 신호 (열람·저장·연락)')}${kpi(d.evaluation_size, '평가셋 질의 수')}</div>
    <div class="grid three mt12">
      <div class="card"><h3>추천이 아쉬운 이유</h3>${bars((d.reasons.result || []).map(x => ({label: x.reason, n: x.n})), 'red')}</div>
      <div class="card"><h3>AI 가이드가 아쉬운 이유</h3>${bars((d.reasons.guide || []).map(x => ({label: x.reason, n: x.n})), 'red')}</div>
      <div class="card"><h3>검색 만족도</h3>${bars([{label: '찾았어요', n: found, tone: 'green'}, {label: '조금', n: partial}, {label: '아니요', n: missed, tone: 'red'}])}</div>
    </div>
    <div class="grid two mt12">
      <div class="card"><h3>👎가 많은 연구실 <small>자료 보강·검색 확인 대상</small></h3>${d.labs_down.length ? d.labs_down.map(l => `<div class="status-row"><span>${h(l.lab)}</span><small>👎 ${l.down} · 👍 ${l.up}</small></div>`).join('') : '<p class="muted">없어요.</p>'}</div>
      <div class="card"><h3>엔진에 반영되는 방식</h3><ul class="muted how"><li>👍·저장·커피챗은 같은 관심 검색에서 그 연구실을 올리고, 👎가 반복되면 내려요(‘rank’ 실험의 feedback 군).</li><li>👍·저장·연락이 쌓인 검색은 평가셋이 되어 <b>엔진 개선</b>에서 nDCG로 측정해요.</li><li>0건·불만족 검색어는 아래 사전 확장 후보로 올라와요.</li><li>AI 가이드 👎 이유는 ‘다시 받기’ 때 프롬프트에 넣어 다른 방향을 받아요.</li></ul></div>
    </div>
    ${section('의견', '새 의견은 처리 후 완료로 표시하세요', `<span class="muted">${d.comments.filter(c => c.status === 'new').length}건 새 의견</span>`)}<div class="card">${comments || '<p class="muted">아직 의견이 없어요.</p>'}</div>
    ${section('사전 확장 후보', '결과가 없거나 불만족한 검색어에서 사전에 없는 단어예요. 영어 연구 용어로 확장하면 사전 검색에 바로 반영돼요.')}
    ${table([['단어', c => `<b>${h(c.word)}</b>`], ['횟수', c => c.count, 'num'], ['출처', c => c.sources.map(x => pill(x, x === '결과 0건' ? 'amber' : 'red')).join(' ')], ['예시', c => c.examples.map(h).join('<br>')], ['', c => `<button class="btn sm" data-expand="${h(c.word)}">확장 추가</button>`]], d.candidates, {empty: '후보가 없어요'})}
    ${section('추가한 확장', '.local/expansions.json에 저장되고 서비스 재시작 뒤에도 유지돼요')}<div class="card"><form id="expand-form" class="inline mb10"><input class="field" name="term" placeholder="한국어 단어 (예: 드론제어)" required><input class="field wide" name="variants" placeholder="확장 표현, 쉼표로 (예: drone control, uav control)" required><button class="btn primary">추가</button></form>${Object.entries(d.expansions).map(([t, v]) => `<div class="status-row"><span><b>${h(t)}</b></span><small>${v.map(h).join(', ')}</small></div>`).join('') || '<p class="muted">아직 없어요.</p>'}</div>`;
  }},
  engine: {title: '엔진 개선', sub: '학생 피드백으로 만든 평가셋으로 검색 품질을 재요', async render() {
    const o = await api('overview');
    const arms = o.metrics.arms || {};
    const armRow = name => { const a = arms[name] || {}; return {arm: name, search: a.search || 0, explore: a.explore || 0, save: a.save || 0}; };
    const ev = PAGES.engine.result;
    return `<div class="grid two">
      <div class="card"><h3>피드백 재정렬 A/B <small>‘rank’ 실험 · 세션 수</small></h3>${table([['군', r => r.arm === 'feedback' ? pill('feedback 반영', 'green') : pill('기본')], ['검색', r => r.search, 'num'], ['열람', r => r.explore, 'num'], ['열람/검색', r => pct(r.explore, r.search), 'num']], [armRow('feedback'), armRow('base')])}<p class="muted small">같은 관심의 신호가 ${4}점 이상 쌓인 검색에서만 순서가 바뀌어요. 표본이 적을 때는 차이를 해석하지 마세요.</p></div>
      <div class="card"><h3>평가 실행</h3><p class="muted note mt0">평가셋 각 질의를 지금 엔진(캐시된 의미 검색 + 사전 검색)으로 다시 검색해 nDCG@10·MRR·Recall@10을 계산해요. 1분 정도 걸릴 수 있어요.</p><div class="inline"><button class="btn primary" data-eval>지금 평가하기</button><button class="btn" data-export>평가셋 내보내기 (JSON)</button></div></div>
    </div>
    ${ev ? `<div class="grid cards mt12">${kpi(ev.queries, '평가 질의')}${kpi(ev.ndcg10 ?? '–', 'nDCG@10 (엔진)')}${kpi(ev.ndcg10_feedback ?? '–', 'nDCG@10 (피드백 재정렬)')}${kpi(ev.mrr ?? '–', 'MRR')}${kpi(ev.recall10 ?? '–', 'Recall@10')}</div><p class="muted small">${h(ev.note)}</p>${section('점수가 낮은 질의', '사전 확장, 연구실 자료 보강, 해석기 규칙을 먼저 볼 곳이에요')}${table([['질의', r => h(r.query)], ['정답 수', r => r.relevant, 'num'], ['nDCG', r => r.ndcg, 'num'], ['피드백 후', r => r.ndcg_feedback, 'num'], ['MRR', r => r.mrr, 'num'], ['Recall@10', r => r.recall10, 'num']], ev.rows, {filter: true})}` : '<p class="muted mt14">아직 평가를 실행하지 않았어요.</p>'}`;
  }},
  ai: {title: 'AI 작업', sub: 'AI 연구 가이드와 논문 쉬운 요약 대기열', auto: true, async render() {
    const o = await api('overview'), c = o.llm.counts || {};
    return `<div class="grid cards">${kpi(o.llm.online ? '연결됨' : '꺼짐', 'AI 워커', o.llm.online ? 'good' : 'alert')}${kpi(c.queued || 0, '대기')}${kpi(c.running || 0, '처리 중')}${kpi(c.done || 0, '완료')}${kpi(c.failed || 0, '실패', c.failed ? 'warn' : '')}</div>
    <div class="inline my14"><button class="btn" data-prefill>전체 연구실 쉬운 요약 미리 만들기</button><button class="btn" data-watch-run>지켜보기 점검 지금 실행</button></div>
    ${table([['ID', j => j.id, 'num'], ['종류', j => pill(j.kind === 'guide' ? 'AI 가이드' : '쉬운 요약')], ['상태', j => pill(j.status, {done: 'green', failed: 'red', running: 'amber'}[j.status] || '')], ['시도', j => j.attempts, 'num'], ['초', j => j.seconds ?? '', 'num'], ['오류', j => h(j.error)], ['요청', j => when(j.created)]], o.llm.recent, {filter: true})}`;
  }},
  experiments: {title: '실험', sub: '세션마다 무작위로 고정 배정되는 비율', async render() {
    const o = await api('overview');
    return `<div class="card"><p class="muted note mt0">guide: R = AI 가이드, A = 기본 가이드만 · rank: feedback = 피드백 재정렬, base = 엔진 순서 그대로</p><textarea id="exp" class="field">${h(JSON.stringify(o.experiments, null, 1))}</textarea><div class="inline mt10"><button class="btn primary" data-exp-save>저장</button></div></div>`;
  }},
  mail: {title: '메일', sub: '인증·알림 메일 발송 기록 (받는 사람은 일부만 표시)', async render() {
    const d = await api('outbox');
    return `<div class="inline mb12">${pill(d.mail_enabled ? 'SMTP 설정됨' : 'SMTP 미설정', d.mail_enabled ? 'green' : 'red')}<button class="btn sm" data-mail-retry>보류·실패 메일 다시 보내기</button></div>
    ${table([['받는 사람', m => h(m.to_addr)], ['제목', m => h(m.subject)], ['종류', m => pill(m.kind)], ['상태', m => pill(m.status, {sent: 'green', failed: 'red', held: 'amber'}[m.status] || '') + (m.error ? ` <span class="muted">${h(m.error)}</span>` : '')], ['시각', m => when(m.created)]], d.outbox, {filter: true})}`;
  }},
  admins: {title: '관리자 계정', sub: '사람마다 계정을 따로 만들고 공유하지 마세요', async render() {
    const d = await call('/admins');
    return `${table([['이름', a => `<b>${h(a.name)}</b> ${a.name === d.me ? pill('나', 'dark') : ''}`], ['만든 날', a => when(a.created)], ['', a => a.name === d.me ? '' : `<button class="btn sm danger" data-admin-del="${h(a.name)}">삭제</button>`]], d.admins)}
    <div class="grid two mt12"><div class="card"><h3>관리자 추가</h3><form id="admin-add" class="inline"><input class="field" name="name" required pattern="[A-Za-z0-9_.\\-]{2,32}" placeholder="이름 (영문·숫자)"><input class="field" name="password" type="password" required minlength="12" placeholder="비밀번호 12자 이상" autocomplete="new-password"><button class="btn primary">추가</button></form></div>
    <div class="card"><h3>내 비밀번호 바꾸기</h3><form id="admin-pw" class="inline"><input class="field" name="current" type="password" required placeholder="현재 비밀번호" autocomplete="current-password"><input class="field" name="password" type="password" required minlength="12" placeholder="새 비밀번호 12자 이상" autocomplete="new-password"><button class="btn primary">변경</button></form></div></div>`;
  }},
  audit: {title: '감사 로그', sub: '관리자의 조회·처리 기록 (2년 보관)', async render() {
    const d = await api('audit');
    return table([['시각', a => when(a.ts)], ['관리자', a => h(a.admin)], ['작업', a => `<code>${h(a.action)}</code>`], ['내용', a => `<span class="muted">${h(a.detail)}</span>`]], d.audit, {filter: true});
  }},
};
const NAV = [['운영', ['overview', 'status']], ['사람', ['users', 'graduates', 'reports']], ['품질', ['feedback', 'engine', 'ai', 'experiments']], ['시스템', ['mail', 'admins', 'audit']]];

function paintNav() {
  $('tabs').innerHTML = NAV.map(([group, keys]) => `<div class="group">${group}</div>${keys.map(k => `<button data-tab="${k}" class="${k === current ? 'on' : ''}"><span>${PAGES[k].title}</span>${badges[k] ? `<span class="badge">${badges[k]}</span>` : ''}</button>`).join('')}`).join('');
}
async function show(tab, quiet = false) {
  current = tab; const page = PAGES[tab];
  $('side').classList.remove('open'); paintNav();
  $('title').textContent = page.title; $('subtitle').textContent = page.sub || '';
  if (!quiet) main.innerHTML = '<p class="muted pad">불러오는 중…</p>';
  try { main.innerHTML = await page.render(); main.querySelectorAll('[data-w]').forEach(el => { el.style.width = el.dataset.w + '%'; }); $('updated').textContent = '업데이트 ' + new Date().toLocaleTimeString('ko-KR', {hour: '2-digit', minute: '2-digit', second: '2-digit'}); }
  catch (e) { if (me) main.innerHTML = `<div class="card kpi alert"><b class="title15">불러오지 못했어요</b><span>${h(e.message)}</span></div>`; }
  history.replaceState(null, '', '#' + tab);
}
function renderLogin() {
  $('side').hidden = true; $('top').hidden = true; clearInterval(autoTimer);
  main.innerHTML = `<form id="login" class="login"><span class="mark">3</span><h1>운영 콘솔 로그인</h1><p class="muted m0">3분커리 관리자만 들어올 수 있어요.</p><label>관리자 이름<input name="name" required autocomplete="username" placeholder="예: admin"></label><label>비밀번호<input name="password" type="password" required autocomplete="current-password"></label><p class="error" id="login-error"></p><button class="btn primary">로그인</button></form>`;
}
function enter(name) {
  me = name; $('side').hidden = false; $('top').hidden = false; $('who').textContent = name;
  const tab = location.hash.slice(1); show(PAGES[tab] ? tab : 'overview');
  api('overview').then(o => { badges = {graduates: o.pending_graduates, reports: o.open_reports, feedback: o.feedback_new || 0}; paintNav(); }).catch(() => {});
}

// ---- events ----
document.addEventListener('input', e => {
  const id = e.target.dataset.filter; if (!id) return;
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll(`#${id} tbody tr`).forEach(tr => { tr.hidden = q && !tr.textContent.toLowerCase().includes(q); });
});
$('auto').addEventListener('change', e => {
  clearInterval(autoTimer);
  if (e.target.checked) autoTimer = setInterval(() => { if (me && !$('modal').open) show(current, true); }, 30000);
});
document.addEventListener('click', async e => {
  const b = e.target.closest('button'); if (!b) return;
  const d = b.dataset;
  if (d.tab) return show(d.tab);
  if (d.go) return show(d.go);
  if ('menu' in d) return $('side').classList.toggle('open');
  if ('refresh' in d) return show(current, true);
  if ('logout' in d) { await call('/logout', {}).catch(() => {}); me = null; return renderLogin(); }
  if (d.grad) {
    const ok = d.ok === '1';
    const note = await modal(ok ? {title: '선배 인증을 승인할까요?', text: '승인하면 연구실 상세에 선배로 소개되고 결과 메일이 가요.', okLabel: '승인'} : {title: '선배 인증을 반려할까요?', text: '사유는 신청자에게 메일로 전달돼요.', input: '반려 사유', okLabel: '반려', danger: true});
    if (note === null) return;
    return run(() => api('graduates/decide', {user_id: Number(d.grad), approve: ok, note: ok ? '' : note}), ok ? '승인했어요.' : '반려했어요.');
  }
  if (d.report) {
    const labels = {hide: '이 글을 숨길까요?', suspend: '글을 숨기고 작성자의 이용을 제한할까요?', dismiss: '신고를 기각할까요?'};
    if (!(await modal({title: labels[d.do], okLabel: '처리', danger: d.do !== 'dismiss'}))) return;
    return run(() => api('reports/resolve', {id: Number(d.report), action: d.do}), '처리했어요.');
  }
  if (d.suspend) {
    if (!(await modal({title: d.on === '1' ? '이 회원의 이용을 정지할까요?' : '정지를 해제할까요?', text: d.on === '1' ? '바로 로그아웃되고 다시 로그인할 수 없어요.' : '', okLabel: d.on === '1' ? '정지' : '해제', danger: d.on === '1'}))) return;
    return run(() => api('users/suspend', {user_id: Number(d.suspend), suspended: d.on === '1'}), '바꿨어요.');
  }
  if (d.adminDel) { if (!(await modal({title: `${d.adminDel} 관리자를 삭제할까요?`, okLabel: '삭제', danger: true}))) return; return run(() => call('/admins', {action: 'delete', name: d.adminDel}), '삭제했어요.'); }
  if (d.fb) return run(() => api('feedback/status', {id: Number(d.fb), status: d.status}), '완료로 표시했어요.');
  if (d.expand) {
    const v = await modal({title: `‘${d.expand}’ 확장 추가`, text: '같은 뜻의 영어 연구 용어나 다른 표기를 쉼표로 적어 주세요.', input: '예: drone control, uav'});
    if (!v) return;
    return run(() => api('expansions/add', {term: d.expand, variants: v}), '사전에 추가했어요. 다음 검색부터 반영돼요.');
  }
  if ('eval' in d) {
    b.disabled = true; b.textContent = '평가 중…';
    try { PAGES.engine.result = await api('feedback/eval'); toast('평가를 마쳤어요.'); } catch (err) { toast(err.message, true); }
    return show('engine', true);
  }
  if ('export' in d) { try { download(`curri-goldset-${new Date().toISOString().slice(0, 10)}.json`, await api('feedback/export')); } catch (err) { toast(err.message, true); } return; }
  if ('mailRetry' in d) return run(() => api('mail/retry', {}), '다시 보내기를 시작했어요.');
  if ('prefill' in d) return run(async () => { const r = await api('summaries/prefill', {}); toast(`${r.queued}곳 요약 작업을 넣었어요.`); });
  if ('watchRun' in d) return run(() => api('watch/run', {}), '지켜보기 점검을 시작했어요.');
  if ('expSave' in d) {
    let value; try { value = JSON.parse($('exp').value); } catch { return toast('JSON 형식이 올바르지 않아요.', true); }
    return run(() => api('experiments', {experiments: value}), '저장했어요.');
  }
});
document.addEventListener('submit', async e => {
  if (e.target.id === 'modal-form') return;
  e.preventDefault(); const f = new FormData(e.target);
  if (e.target.id === 'login') {
    try { enter((await call('/login', {name: f.get('name'), password: f.get('password')})).name); }
    catch (err) { $('login-error').textContent = err.message; }
  }
  else if (e.target.id === 'user-search') { PAGES.users.q = f.get('q'); show('users'); }
  else if (e.target.id === 'admin-add') run(() => call('/admins', {action: 'add', name: f.get('name'), password: f.get('password')}), '관리자를 추가했어요.');
  else if (e.target.id === 'admin-pw') run(() => call('/admins', {action: 'password', current: f.get('current'), password: f.get('password')}), '비밀번호를 바꿨어요.');
  else if (e.target.id === 'expand-form') run(() => api('expansions/add', {term: f.get('term'), variants: f.get('variants')}), '사전에 추가했어요.');
});
call('/me').then(r => r.name ? enter(r.name) : renderLogin()).catch(() => renderLogin());
