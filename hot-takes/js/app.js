/* ═══════════════════════════════════════════════════════════
   HOT TAKES — presentation engine
   Vanilla JS, no build step. Everything is keyboard-first so
   Dara can drive it from a clicker without touching the mouse.
   ═══════════════════════════════════════════════════════════ */
(() => {
'use strict';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

const slides = $$('.slide');
let current = 0;

// Derive the indices of the interactive slides so reordering the deck
// never breaks the shortcuts.
const indexOfSlide = cls => slides.findIndex(s => s.classList.contains(cls));
const EXHIBIT_SLIDE = indexOfSlide('slide--exhibit');
const REBUT_SLIDE   = indexOfSlide('slide--rebut');
const VERSUS_SLIDE  = indexOfSlide('slide--versus');

/* ── 1 · staged reveals ─────────────────────────────────── */
// Each .r element carries data-r (its step). Convert to a delay.
const STEP = 130;
$$('.r').forEach(el => {
  el.style.setProperty('--d', (parseInt(el.dataset.r || 1, 10) - 1) * STEP + 200);
});

// Split [data-split] copy into per-word spans so lines land word by word.
// This walks text nodes rather than slicing innerHTML on whitespace: a string
// split would cut inside `<i class="hot">` and spill the attribute as text,
// and would break the nesting of any inline tag spanning two words.
$$('[data-split]').forEach(el => {
  let n = 0;
  (function walk(node) {
    [...node.childNodes].forEach(child => {
      if (child.nodeType === Node.ELEMENT_NODE) return walk(child);
      if (child.nodeType !== Node.TEXT_NODE) return;

      const frag = document.createDocumentFragment();
      child.textContent.split(/(\s+)/).forEach(chunk => {
        if (!chunk) return;
        if (!chunk.trim()) return frag.append(chunk);   // keep the spacing
        const w = document.createElement('span');
        w.className = 'w';
        w.textContent = chunk;
        w.style.animationDelay = `${300 + n++ * 70}ms`;
        frag.append(w);
      });
      child.replaceWith(frag);
    });
  })(el);
});

/* ── 2 · slide activation ───────────────────────────────── */
const progressBar = $('#progressBar');
const slideNum    = $('#slideNum');
const slideTotal  = $('#slideTotal');
if (slideTotal) slideTotal.textContent = slides.length;
const notesBody   = $('#notesBody');

function activate(i, { restart = false } = {}) {
  const slide = slides[i];
  if (!slide) return;

  if (restart) {
    // Re-trigger CSS animations by ripping the class off for a frame.
    slide.classList.remove('is-live');
    void slide.offsetWidth;
  }
  slide.classList.add('is-live');

  if (i === current && !restart) return;
  current = i;

  progressBar.style.width = ((i + 1) / slides.length * 100) + '%';
  slideNum.textContent = String(i + 1).padStart(2, '0');
  notesBody.textContent = slide.dataset.notes || 'No notes for this slide.';
  $$('.ov-card').forEach((c, n) => c.classList.toggle('current', n === i));

  runSlideHooks(i, slide);
}

/* The observer keeps `current` honest when the user scrolls by hand. While a
   keyboard jump is still smooth-scrolling, slides the deck is merely passing
   through would otherwise steal `current` — so during a jump the observer only
   accepts the slide we actually asked for. Without this, holding the arrow key
   walks the deck backwards. */
let navTarget = null;

const io = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (!e.isIntersecting || e.intersectionRatio <= 0.55) return;
    const i = slides.indexOf(e.target);
    if (navTarget !== null) {
      if (i !== navTarget) return;
      navTarget = null;
    }
    activate(i);
  });
}, { threshold: [0.55] });
slides.forEach(s => io.observe(s));

function go(i) {
  const n = Math.max(0, Math.min(slides.length - 1, i));
  navTarget = n;
  slides[n].scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
  activate(n);
  // Safety valve: if the scroll never resolves (tab hidden, reduced motion),
  // stop suppressing the observer so manual scrolling still tracks.
  clearTimeout(go._t);
  go._t = setTimeout(() => { navTarget = null; }, 1400);
}
const next = () => go(current + 1);
const prev = () => go(current - 1);

/* ── 3 · per-slide behaviour ────────────────────────────── */
const done = new Set();

function runSlideHooks(i, slide) {
  countUp(slide);                       // idempotent per element
  if (i === VERSUS_SLIDE && !done.has(i)) { done.add(i); runScoreboard(); }
}

/* animated counters — respects prefix/suffix/decimals */
function countUp(scope) {
  $$('[data-count-to]', scope).forEach(el => {
    if (el.dataset.counted) return;
    el.dataset.counted = '1';

    const target   = parseFloat(el.dataset.countTo);
    const decimals = parseInt(el.dataset.decimals || 0, 10);
    const prefix   = el.dataset.prefix || '';
    const suffix   = el.dataset.suffix || '';
    const fmt = v => prefix + v.toLocaleString('en-US', {
      minimumFractionDigits: decimals, maximumFractionDigits: decimals
    }) + suffix;

    if (reduced) { el.textContent = fmt(target); return; }

    const dur = 1500, t0 = performance.now(), delay = 350;
    const tick = now => {
      const p = Math.min(1, Math.max(0, (now - t0 - delay) / dur));
      const eased = 1 - Math.pow(1 - p, 4);      // easeOutQuart
      el.textContent = fmt(target * eased);
      if (p < 1) requestAnimationFrame(tick);
      else el.textContent = fmt(target);
    };
    requestAnimationFrame(tick);
  });
}

/* slide 08 — the 0–4 scoreboard ticks up as the rows land */
function runScoreboard() {
  const right = $('#scoreR');
  if (!right) return;
  if (reduced) { right.textContent = '4'; return; }
  let n = 0;
  const beat = setInterval(() => {
    n++;
    right.textContent = n;
    right.classList.remove('bump'); void right.offsetWidth; right.classList.add('bump');
    if (n >= 4) clearInterval(beat);
  }, 620);
}

/* ── 4 · slide 02: the exhibit ──────────────────────────── */
/* Every item hides its price behind a "$ ? ?" tag. Click one to turn just
   that tag over (the room guesses item by item), or press R for the lot.
   The wall total counts up as tags turn, so the number climbs live. */
const exhibits = $('#exhibits');
if (exhibits) {
  const items    = $$('.ex', exhibits);
  const totalEl  = $('#exTotal');
  const noteEl   = $('#exTotalNote');
  const revealBtn = $('#revealBtn');
  const money = n => '$' + Math.round(n).toLocaleString('en-US');

  let shown = 0;                                   // what the counter reads now
  let raf = null;

  function retotal() {
    const target = items
      .filter(el => el.classList.contains('turned'))
      .reduce((sum, el) => sum + Number(el.dataset.price || 0), 0);

    const turned = items.filter(el => el.classList.contains('turned')).length;
    noteEl.textContent = turned === 0        ? 'turn the tags over'
                       : turned < items.length ? `${turned} of ${items.length} revealed`
                       : 'six objects';
    revealBtn.innerHTML =
      (turned === items.length ? 'Hide tags' : 'Turn all tags') + ' <kbd>R</kbd>';

    if (reduced) { shown = target; totalEl.textContent = money(target); return; }

    cancelAnimationFrame(raf);
    const from = shown, t0 = performance.now(), dur = 650;
    const tick = now => {
      const pr = Math.min(1, (now - t0) / dur);
      shown = from + (target - from) * (1 - Math.pow(1 - pr, 3));
      totalEl.textContent = money(shown);
      if (pr < 1) raf = requestAnimationFrame(tick);
      else { shown = target; totalEl.textContent = money(target); }
    };
    raf = requestAnimationFrame(tick);
  }

  const turn = el => { el.classList.toggle('turned'); retotal(); };
  items.forEach(el => el.addEventListener('click', () => turn(el)));

  revealBtn.addEventListener('click', () => {
    const showAll = items.some(el => !el.classList.contains('turned'));
    items.forEach(el => el.classList.toggle('turned', showAll));
    retotal();
  });

  $('#resetBtn').addEventListener('click', () => {
    items.forEach(el => el.classList.remove('turned'));
    retotal();
  });

  // Drop in your own photos without editing any files.
  $('#swapInput').addEventListener('change', ev => {
    const imgs = $$('[data-swap]', exhibits);
    [...ev.target.files].slice(0, imgs.length).forEach((file, i) => {
      const url = URL.createObjectURL(file);
      imgs[i].addEventListener('load', () => URL.revokeObjectURL(url), { once: true });
      imgs[i].src = url;
    });
  });

  exhibits._turnOne = i => { if (items[i]) turn(items[i]); };
  exhibits._toggleAll = () => revealBtn.click();
  retotal();
}

/* ── 4b · slide 03: use the real cover art if it is present ─ */
/* Drop the sleeve image in at assets/mcbh.jpg and it takes over from the
   drawn sleeve; until then the drawn one stands in. */
const sleeveArt = $('.sleeve-art');
if (sleeveArt) {
  sleeveArt.addEventListener('load', () => {
    if (!sleeveArt.naturalWidth) return;
    sleeveArt.hidden = false;
    $('.sleeve-drawn')?.remove();
  });
  sleeveArt.src = sleeveArt.getAttribute('src');   // re-kick after the listener is on
}

/* ── 4c · slide 09: the cue line bounces letter by letter ── */
const cue = $('[data-letters]');
if (cue && !reduced) {
  cue.innerHTML = [...cue.textContent].map((ch, i) =>
    ch === ' ' ? ' '
      : `<span class="ltr" style="animation-delay:${i * 58}ms">${ch}</span>`
  ).join('');
}

/* ── 5 · slide 10: rebuttal flip cards ──────────────────── */
$$('.flip').forEach(card =>
  card.addEventListener('click', () => card.classList.toggle('flipped')));

/* ── 6 · slide 13: equaliser bars ───────────────────────── */
const eq = $('.eq');
if (eq && !reduced) {
  for (let i = 0; i < 44; i++) {
    const bar = document.createElement('i');
    bar.style.setProperty('--h', (25 + Math.random() * 70) + '%');
    bar.style.animationDelay = (-Math.random() * 1.1) + 's';
    bar.style.animationDuration = (0.55 + Math.random() * 0.85) + 's';
    eq.appendChild(bar);
  }
}

/* ── 7 · slide 01: drifting price tags ──────────────────── */
const tagBox = $('.tags');
if (tagBox && !reduced) {
  const PRICES = ['$31,000', '$10,000', '$5,000', '~$800', '£28.6m', '€481m',
                  '12x', '$3,000', '$30,188', '96%', '$60', '$2,000'];
  PRICES.forEach((p, i) => {
    const t = document.createElement('span');
    t.className = 'tag';
    t.textContent = p;
    t.style.left = (4 + Math.random() * 92) + '%';
    t.style.setProperty('--rot', (Math.random() * 24 - 12) + 'deg');
    t.style.animationDuration = (26 + Math.random() * 22) + 's';
    t.style.animationDelay = (-i * 3.4) + 's';
    tagBox.appendChild(t);
  });
}

/* ── 8 · ambient gold dust ──────────────────────────────── */
const canvas = $('#dust');
if (canvas && !reduced) {
  const ctx = canvas.getContext('2d');
  let motes = [], w = 0, h = 0;

  const size = () => {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    w = canvas.width  = innerWidth  * dpr;
    h = canvas.height = innerHeight * dpr;
    canvas.style.width = innerWidth + 'px';
    canvas.style.height = innerHeight + 'px';
    motes = Array.from({ length: Math.round(innerWidth / 22) }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      r: (Math.random() * 1.6 + 0.35) * dpr,
      vy: -(Math.random() * 0.22 + 0.05) * dpr,
      vx: (Math.random() - 0.5) * 0.12 * dpr,
      a: Math.random() * 0.5 + 0.12,
      phase: Math.random() * Math.PI * 2
    }));
  };

  const draw = t => {
    ctx.clearRect(0, 0, w, h);
    motes.forEach(m => {
      m.y += m.vy;
      m.x += m.vx + Math.sin(t / 2600 + m.phase) * 0.18;
      if (m.y < -10) { m.y = h + 10; m.x = Math.random() * w; }
      ctx.beginPath();
      ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(201,162,39,${m.a * (0.6 + 0.4 * Math.sin(t / 1400 + m.phase))})`;
      ctx.fill();
    });
    requestAnimationFrame(draw);
  };

  size();
  addEventListener('resize', size);
  requestAnimationFrame(draw);
}

/* ── 9 · overview grid ──────────────────────────────────── */
const overview = $('#overview');
const ovGrid   = $('#ovGrid');
slides.forEach((s, i) => {
  const title = ($('.h2', s) || $('.title-stack', s) || $('.big-line', s) ||
                 $('.thesis', s) || $('.end-line', s) || $('.bonus-take', s));
  const btn = document.createElement('button');
  btn.className = 'ov-card';
  btn.type = 'button';
  btn.innerHTML = `<span class="ov-n">${String(i + 1).padStart(2, '0')}</span>
                   <span class="ov-t">${(title ? title.textContent : '').trim().slice(0, 74)}</span>`;
  btn.addEventListener('click', () => { toggleOverview(false); go(i); });
  ovGrid.appendChild(btn);
});
function toggleOverview(force) {
  const open = force ?? overview.hidden;
  overview.hidden = !open;
}

/* ── 10 · notes + help + blackout ───────────────────────── */
const notes = $('#notes');
function toggleNotes(force) {
  const open = force ?? !document.body.classList.contains('notes-open');
  notes.hidden = false;
  document.body.classList.toggle('notes-open', open);
}
$('#notesClose').addEventListener('click', () => toggleNotes(false));

const help = $('#help');
const toggleHelp = force => { help.hidden = !(force ?? help.hidden); };
$('#helpBtn').addEventListener('click', () => toggleHelp(true));
$('#helpClose').addEventListener('click', () => toggleHelp(false));
help.addEventListener('click', e => { if (e.target === help) toggleHelp(false); });

function fullscreen() {
  document.fullscreenElement
    ? document.exitFullscreen()
    : document.documentElement.requestFullscreen?.();
}

/* ── 11 · keyboard ──────────────────────────────────────── */
addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;

  if (k === 'Escape') {
    if (!help.hidden) return toggleHelp(false);
    if (!overview.hidden) return toggleOverview(false);
    if (document.body.classList.contains('notes-open')) return toggleNotes(false);
    return;
  }

  switch (k) {
    case 'ArrowRight': case 'ArrowDown': case ' ': case 'PageDown':
      e.preventDefault(); next(); return;
    case 'ArrowLeft': case 'ArrowUp': case 'PageUp':
      e.preventDefault(); prev(); return;
    case 'Home': e.preventDefault(); go(0); return;
    case 'End':  e.preventDefault(); go(slides.length - 1); return;
  }

  switch (k.toLowerCase()) {
    case 'f': fullscreen(); break;
    case 'n': toggleNotes(); break;
    case 'o': toggleOverview(); break;
    case 'b': document.body.classList.toggle('is-black'); break;
    case '?': case '/': toggleHelp(true); break;
    case 'r': if (current === EXHIBIT_SLIDE) exhibits?._toggleAll(); break;
  }

  // Number keys mean "the nth thing on this slide" — an exhibit tag here,
  // a rebuttal card there. Both are gated on the slide being on screen.
  if (/^[1-9]$/.test(k)) {
    if (current === EXHIBIT_SLIDE) exhibits?._turnOne(Number(k) - 1);
    else if (current === REBUT_SLIDE && k <= '4') {
      $(`.flip[data-flip="${k}"]`)?.classList.toggle('flipped');
    }
  }
});

/* ── 12 · touch swipe ───────────────────────────────────── */
let touchY = null;
addEventListener('touchstart', e => { touchY = e.changedTouches[0].clientY; }, { passive: true });
addEventListener('touchend', e => {
  if (touchY === null) return;
  const dy = touchY - e.changedTouches[0].clientY;
  if (Math.abs(dy) > 70) dy > 0 ? next() : prev();
  touchY = null;
}, { passive: true });

/* ── 13 · boot ──────────────────────────────────────────── */
// Land on slide 1 fresh even if the browser restored a scroll position.
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
addEventListener('load', () => {
  scrollTo(0, 0);
  activate(0, { restart: true });
});
activate(0);

})();
