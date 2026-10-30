// Decorative document-start intro. Independent of app.js and API readiness.
// No storage, navigation, focus management, or native PWA splash changes.
let started = false;

export function startBrandIntro() {
  if (started) return;
  started = true;
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  if (document.hidden || motion.matches) return;
  const root = document.documentElement;
  // Missing CSS must never expose an unstyled overlay.
  if (getComputedStyle(root).getPropertyValue('--brand-intro-ready').trim() !== '1') return;
  const intro = document.createElement('div');
  intro.id = 'brand-intro';
  intro.className = 'brand-intro';
  // Rings sit on the real ribbon (anchors measured on the unmodified logo.png),
  // stepping up the river where the stone skips: (44,83) → (66,60) → (86,48).
  intro.innerHTML = `
    <div class="brand-intro__content" aria-hidden="true">
      <div class="brand-intro__mark">
        <img src="/static/logo.png" width="128" height="128" alt="">
        <svg viewBox="0 0 128 128" fill="none" aria-hidden="true">
          <g class="brand-intro__ripple" style="--delay: 180ms; transform-origin: 44px 83px">
            <ellipse cx="44" cy="83" rx="18" ry="5.5"/>
            <ellipse cx="44" cy="83" rx="11" ry="3.4"/>
          </g>
          <g class="brand-intro__ripple" style="--delay: 560ms; transform-origin: 66px 60px">
            <ellipse cx="66" cy="60" rx="13" ry="4"/>
            <ellipse cx="66" cy="60" rx="8" ry="2.5"/>
          </g>
          <g class="brand-intro__ripple" style="--delay: 900ms; transform-origin: 86px 48px">
            <ellipse cx="86" cy="48" rx="9.5" ry="3"/>
            <ellipse cx="86" cy="48" rx="6" ry="2"/>
          </g>
          <ellipse class="brand-intro__stone" cx="0" cy="0" rx="3.5" ry="2"/>
        </svg>
      </div>
      <div class="brand-intro__title">VB Typer</div>
      <div class="brand-intro__caption">Sua voz, em palavras.</div>
    </div>
    <button class="brand-intro__skip" type="button">Pular introdução</button>`;
  const events = new AbortController();
  const timer = setTimeout(dismiss, 1800);
  function dismiss() {
    clearTimeout(timer);
    events.abort();
    intro.remove();
  }
  // Dismiss on intent, without cancelling input or stealing focus.
  for (const name of ['pointerdown', 'keydown', 'focusin']) {
    document.addEventListener(name, dismiss, { capture: true, signal: events.signal });
  }
  intro.querySelector('button').addEventListener('click', dismiss, { signal: events.signal });
  intro.querySelector('img').addEventListener('error', dismiss, { signal: events.signal });
  motion.addEventListener('change', dismiss, { signal: events.signal });
  document.addEventListener('visibilitychange', dismiss, { signal: events.signal });
  document.body.append(intro);
}

startBrandIntro();
