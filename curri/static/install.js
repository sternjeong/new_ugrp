// 홈 화면에 추가 안내: 지금 쓰는 브라우저에 맞는 단계를 하나씩 보여 준다.
// 카카오톡 등 앱 안 브라우저는 홈 화면에 추가할 수 없어 먼저 휴대폰 브라우저로 여는 단계부터 안내한다.
(() => {
  const $ = id => document.getElementById(id);
  const ua = navigator.userAgent || '';
  const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const ipad = /iPad/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const android = /Android/.test(ua);
  const kakao = /KAKAOTALK/i.test(ua);
  const inApp = kakao || /NAVER\(inapp|Instagram|FBAN|FBAV|Line\/|everytimeApp|DaumApps/i.test(ua);
  const samsung = /SamsungBrowser/.test(ua);
  const iosChrome = ios && /CriOS/.test(ua);
  const mobile = ios || android;
  let deferred = null;  // Android Chrome: the browser's own install prompt
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); deferred = e; });
  window.addEventListener('appinstalled', () => { deferred = null; hide(); });

  const SHARE = '<svg class="install-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12M7.5 7.5 12 3l4.5 4.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 10H6.5A1.5 1.5 0 0 0 5 11.5v8A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5v-8A1.5 1.5 0 0 0 17.5 10H16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  const PLUS = '<svg class="install-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="3.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 8.5v7M8.5 12h7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  const DOTS = '<svg class="install-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="5" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="12" cy="19" r="1.8"/></svg>';
  const b = s => `<b>${s}</b>`;

  const browserFirst = () => [{
    title: kakao ? '카카오톡 안에서는 홈 화면에 추가할 수 없어요' : '이 앱 안에서는 홈 화면에 추가할 수 없어요',
    body: `먼저 휴대폰 브라우저(${ios ? '사파리' : '크롬·삼성 인터넷'})로 열어 주세요. 아래 버튼을 누르거나, 화면 ${ios ? '오른쪽 아래' : '오른쪽 위'} ${DOTS} 메뉴에서 ${b('다른 브라우저로 열기')}를 눌러요.`,
    action: kakao ? {label: '브라우저로 열기', run: () => { location.href = 'kakaotalk://web/openExternal?url=' + encodeURIComponent(location.origin + '/?source=homescreen-guide'); }} : null,
    copy: true,
  }];

  const iosSteps = () => iosChrome ? [
    {title: '주소창 오른쪽의 공유 버튼을 눌러요', body: `주소창 오른쪽에 있는 ${SHARE} 공유 버튼(네모에 위쪽 화살표)을 눌러요.`},
    {title: `목록을 내려서 ${b('홈 화면에 추가')}를 눌러요`, body: `${PLUS} 홈 화면에 추가가 안 보이면 목록을 끝까지 내리거나 ${b('더 보기')}를 눌러요.`},
    {title: `이름을 확인하고 ${b('추가')}를 눌러요`, body: '오른쪽 위 추가 버튼을 누르면 홈 화면에 3분커리 아이콘이 생겨요.'},
  ] : [
    {title: `화면 ${ipad ? '위쪽' : '아래쪽'}의 공유 버튼을 눌러요`, body: `${SHARE} 네모에 위쪽 화살표 모양이에요. 버튼이 안 보이면 화면을 살짝 위로 올리거나 주소창을 한 번 눌러요.`, pointer: !ipad},
    {title: `목록을 내려서 ${b('홈 화면에 추가')}를 눌러요`, body: `${PLUS} 홈 화면에 추가가 안 보이면 목록 맨 아래의 ${b('작업 편집')}에서 추가할 수 있어요.`},
    {title: `이름을 확인하고 ${b('추가')}를 눌러요`, body: '오른쪽 위 추가 버튼을 누르면 홈 화면에 3분커리 아이콘이 생겨요. 이제 아이콘을 눌러 앱처럼 열어요.'},
  ];

  const androidSteps = () => samsung ? [
    {title: `화면 아래쪽의 메뉴 ${b('≡')}를 눌러요`, body: '오른쪽 아래 줄 세 개 모양 버튼이에요.'},
    {title: `${b('현재 페이지 추가')}를 누른 뒤 ${b('홈 화면')}을 골라요`, body: `${PLUS} 메뉴에 ${b('홈 화면에 추가')}가 바로 보이면 그것을 눌러도 돼요.`},
    {title: `이름을 확인하고 ${b('추가')}를 눌러요`, body: '홈 화면에 3분커리 아이콘이 생겨요.'},
  ] : [
    {title: '오른쪽 위 메뉴를 눌러요', body: `주소창 오른쪽의 ${DOTS} 점 세 개 버튼이에요.`,
     action: deferred ? {label: '바로 추가하기', run: async () => { deferred.prompt(); const r = await deferred.userChoice; deferred = null; if (r.outcome === 'accepted') hide(); }} : null},
    {title: `${b('홈 화면에 추가')} 또는 ${b('앱 설치')}를 눌러요`, body: `${PLUS} 메뉴를 조금 내리면 있어요.`},
    {title: `이름을 확인하고 ${b('추가')}(또는 ${b('설치')})를 눌러요`, body: '홈 화면에 3분커리 아이콘이 생겨요. 이제 아이콘을 눌러 앱처럼 열어요.'},
  ];

  let guide = ios ? 'ios' : android ? 'android' : 'ios';
  let steps = [], at = 0;

  function build() {
    steps = [...(inApp ? browserFirst() : []), ...(guide === 'ios' ? iosSteps() : androidSteps())];
    at = Math.min(at, steps.length - 1);
  }

  function render() {
    $('install-lead').textContent = mobile ? '앱처럼 홈 화면 아이콘으로 바로 열 수 있어요. 순서대로 따라 해 보세요.'
      : '휴대폰에서 이 주소를 연 뒤 아래 순서대로 따라 하면 홈 화면에 아이콘이 생겨요.';
    $('install-steps').innerHTML = steps.map((s, i) => `<li class="${i === at ? 'current' : i < at ? 'done' : ''}" ${i === at ? 'aria-current="step"' : ''}>
      <span class="install-num">${i < at ? '✓' : i + 1}</span><div><p class="install-step-title">${s.title}</p>${i === at ? `<p class="install-step-body">${s.body}</p>${s.action ? `<button type="button" class="primary install-action" data-step-action>${s.action.label}</button>` : ''}${s.copy ? `<button type="button" class="secondary install-action" data-step-copy>주소 복사</button>` : ''}` : ''}</div></li>`).join('');
    $('install-count').textContent = `${at + 1} / ${steps.length}`;
    $('install-prev').disabled = at === 0;
    $('install-next').textContent = at === steps.length - 1 ? '다 했어요' : '다음';
    const other = guide === 'ios' ? 'android' : 'ios';
    $('install-switch').innerHTML = `<button type="button" class="text-button inline" id="install-other">${other === 'ios' ? '아이폰' : '안드로이드'} 안내 보기</button>`;
    $('install-pointer').hidden = !(steps[at] && steps[at].pointer && ios && !inApp);
    const act = $('install-steps').querySelector('[data-step-action]');
    if (act) act.onclick = () => steps[at].action.run();
    const copy = $('install-steps').querySelector('[data-step-copy]');
    if (copy) copy.onclick = async () => {
      try { await navigator.clipboard.writeText(location.origin); copy.textContent = '복사했어요. 브라우저 주소창에 붙여 넣어요'; }
      catch { copy.textContent = location.origin; }
    };
    $('install-other').onclick = () => { guide = other; at = inApp ? Math.min(at, 0) : 0; build(); render(); };
  }

  function open() {
    build(); at = 0; render();
    const d = $('install-dialog');
    if (!d.open) d.show();  // not modal: the browser buttons and the pointer stay visible while following the steps
    $('install-banner').hidden = true;
  }

  function hide() {
    $('install-dialog').open && $('install-dialog').close();
    $('install-pointer').hidden = true;
  }

  function remember(key) { try { localStorage.setItem(key, '1'); } catch {} }
  function recalled(key) { try { return localStorage.getItem(key) === '1'; } catch { return false; } }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('install-dialog')) return;
    if (standalone) { $('install-open').hidden = true; return; }
    $('install-open').onclick = open;
    $('install-close').onclick = hide;
    $('install-prev').onclick = () => { if (at > 0) { at -= 1; render(); } };
    $('install-next').onclick = () => { if (at < steps.length - 1) { at += 1; render(); } else { remember('install-banner-off'); hide(); } };
    $('install-dialog').addEventListener('close', () => { $('install-pointer').hidden = true; });
    $('install-banner-open').onclick = open;
    $('install-banner-x').onclick = () => { $('install-banner').hidden = true; remember('install-banner-off'); };
    if (mobile && !recalled('install-banner-off')) $('install-banner').hidden = false;
    if (new URLSearchParams(location.search).get('source') === 'homescreen-guide') open();  // opened from KakaoTalk: keep going
  });
})();
