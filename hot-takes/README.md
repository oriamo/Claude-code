# Hot Takes — *Designer Products Are A Scam*

An animated presentation site built from `hot_takes.pptx`. Same argument, same
tone, same palette (ink `#121212` · gold `#C9A227` · blood `#B4231E`, Cambria +
Calibri) — just things a slide deck physically can't do.

**Live:** https://oriamo.github.io/Claude-code/ *(after the one-time Pages setup below)*

---

## Driving it

Keyboard-first, so it works off a clicker with no mouse.

| Key | Does |
|---|---|
| <kbd>→</kbd> <kbd>↓</kbd> <kbd>Space</kbd> | next slide |
| <kbd>←</kbd> <kbd>↑</kbd> | previous slide |
| <kbd>F</kbd> | fullscreen |
| <kbd>N</kbd> | speaker notes (pulled straight from the .pptx notes) |
| <kbd>O</kbd> | slide overview — jump anywhere |
| <kbd>B</kbd> | blackout — kill the screen so the room looks at you |
| <kbd>R</kbd> | turn every price tag on the exhibit |
| <kbd>1</kbd>–<kbd>6</kbd> | turn one exhibit tag · flip one rebuttal card |
| <kbd>?</kbd> | shortcuts panel |

Swipe up/down works on phones. Number keys mean "the nth thing on this slide" —
an exhibit tag on slide 2, a rebuttal card on slide 10 — and do nothing anywhere else.

## What each slide does that a slide couldn't

| # | Slide | The move |
|---|---|---|
| 01 | Title | "SCAM" slams in and gets slashed in red; gold sheen sweeps the headline; real price tags drift up the background |
| 02 | **The exhibit** | Six objects, every price hidden behind a `$ ? ?` tag. The room shouts guesses, you turn tags over one at a time, and the wall total counts up live to **$41,170** |
| 03 | Thesis | The line assembles word by word, over a spinning record sleeve for *Money Can't Buy Happiness* |
| 04 | Double standard | A see-saw physically tips — "iconic" down, "too flashy" up — then the rigged-industry pyramid builds top-down |
| 05 | The math | Counters run $0→$800, $0→$10,000+, 0→12x, then a bar chart draws the gap and labels it **YOU ARE THE MARGIN** |
| 06 | Fake scarcity | Live fire burns along the bottom of the screen while the £28.6m and €481m counters climb |
| 07 | Diamonds | A timeline draws itself 1888 → 1980s, then an SVG line chart plummets to show lab-grown down 96% |
| 08 | It's not even good | Rows land alternately left/right while a scoreboard ticks **0–4** against the $2,000 bag |
| 09 | The money | The compounding curve draws to $30,188, the over-normalisation line lands word by word, and the *Allonsy* cue ripples like an equaliser |
| 10 | Come at me | Four 3D flip cards. Counterargument on the front, your answer on the back — flip live as people raise them |
| 11 | Uncomfortable part | The blank-logo test, staged: the logo disappears across three frames |
| 12 | Bonus 01 — the claim | A receipt prints out and gets stamped **SETTLED IN VIBES** |
| 13 | Bonus 01 — the receipts | A message thread types itself out over three weeks, beside three claims and one you concede before anyone can throw it |
| 14 | Bonus 02 — the claim | Equaliser bars run behind the four pillars of actual taste |
| 15 | Bonus 02 — the proof | A Wrapped-style top 5 fills in, then gets stamped **THIS IS JUST THE CHART**, and the room gets tested live |
| 16 | The end | Mic drop with an impact ripple |

## Before you present

**Swap the two exhibit photos for whatever your room will react to hardest.**
Items 01 and 02 are your openers; 03–06 are placards that need no image.

1. **No editing:** click **⇄ Swap photos** on slide 2 and pick two images. They
   load instantly, just for that session.
2. **Permanent:** replace `assets/exhibit-a.png` and `assets/exhibit-b.png` and push.

To change a price, edit that item's `data-price` **and** its `.ex-price` text in
`index.html` — the running total adds up `data-price`, so they have to match.

**The album cover on slide 3.** Drop the real artwork in at `assets/mcbh.jpg` and
it replaces the drawn sleeve automatically — no code change. Until you do, the
drawn sleeve stands in. (I couldn't fetch the real cover from here, and shipping
someone else's artwork into a public repo is your call to make, not mine.)

Rehearse with <kbd>N</kbd> open on a second screen — every speaker note from the
original deck is in there, including the "18 hours by hand" rebuttal and the
kill-shot diamond line.

## Deploying (one-time setup)

The workflow at `.github/workflows/deploy-hot-takes.yml` publishes this folder
to GitHub Pages on every push. It needs the Pages source flipped to Actions once:

1. Repo **Settings → Pages**
2. **Build and deployment → Source:** select **GitHub Actions**
3. Done — the next push (or **Actions → Deploy Hot Takes site → Run workflow**)
   publishes to `https://oriamo.github.io/Claude-code/`

## Running locally

It's static — no build, no dependencies.

```bash
cd hot-takes
python3 -m http.server 8000
# → http://localhost:8000
```

Opening `index.html` directly works too, except **⇄ Swap photos**, which needs a
server. Chrome or Safari fullscreen (<kbd>F</kbd>) is the intended presenting mode.

## Files

```
hot-takes/
├── index.html          all 16 slides
├── css/styles.css      palette, layout, every animation
├── js/app.js           navigation, counters, exhibit, notes, overview
└── assets/             exhibit-a.png, exhibit-b.png
```

Respects `prefers-reduced-motion` (animations collapse, content stays) and prints
to PDF with all reveals forced visible — a usable backup if the venue's wifi dies.
