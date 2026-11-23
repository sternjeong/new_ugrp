// Light/dark theme. Loaded before the page paints so a saved dark choice never flashes white.
// The choice lives in localStorage (this browser only); without one the page is light.
(() => {
  const KEY = 'curri-theme', root = document.documentElement;
  const saved = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
  const apply = theme => {
    const dark = theme === 'dark';
    root.dataset.theme = dark ? 'dark' : 'light';
    const meta = document.querySelector('meta[name=theme-color]');
    if (meta) meta.content = dark ? '#171716' : '#ffffff';
    const button = document.getElementById('theme-toggle');
    if (button) { button.querySelector('.theme-label').textContent = dark ? '라이트 모드' : '다크 모드'; button.setAttribute('aria-pressed', String(dark)); }
  };
  apply(saved());
  document.addEventListener('DOMContentLoaded', () => apply(root.dataset.theme));
  document.addEventListener('click', event => {
    if (!event.target.closest('#theme-toggle')) return;
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem(KEY, next); } catch {}
    apply(next);
  });
  // Another tab changed the theme: follow it.
  window.addEventListener('storage', event => { if (event.key === KEY) apply(event.newValue); });
})();
