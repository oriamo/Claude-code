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
| <kbd>A</kbd> / <kbd>B</kbd> | tally live votes on the game slide |
| <kbd>R</kbd> | reveal the game answer |
| <kbd>1</kbd>–<kbd>4</kbd> | flip a rebuttal card on "Come At Me" |
| <kbd>?</kbd> | shortcuts panel |

Swipe up/down works on phones. Slide 2's A/B keys only vote while slide 2 is
on screen — everywhere else <kbd>B</kbd> is blackout.

## What each slide does that a slide couldn't

| # | Slide | The move |
|---|---|---|
| 01 | Title | "SCAM" slams in and gets slashed in red; gold sheen sweeps the headline; real price tags drift up the background |
| 02 | Opening game | **Live audience vote.** Click or press A/B to tally hands, a split meter fills in real time, then <kbd>R</kbd> flips both cards to their verdict |
| 03 | Thesis | The line assembles word by word so the room reads at your pace |
| 04 | Double standard | A see-saw physically tips — "iconic" down, "too flashy" up — then the rigged-industry pyramid builds top-down |
| 05 | The math | Counters run $0→$800, $0→$10,000+, 0→12x, then a bar chart draws the gap and labels it **YOU ARE THE MARGIN** |
| 06 | Fake scarcity | Live fire burns along the bottom of the screen while the £28.6m and €481m counters climb |
| 07 | Diamonds | A timeline draws itself 1888 → 1980s, then an SVG line chart plummets to show lab-grown down 96% |
| 08 | It's not even good | Rows land alternately left/right while a scoreboard ticks **0–4** against the $2,000 bag |
| 09 | The money | The compounding curve draws from $3,000 to $30,188 next to the flat dashed line the bag never leaves |
| 10 | Come at me | Four 3D flip cards. Counterargument on the front, your answer on the back — flip live as people raise them |
| 11 | Uncomfortable part | The blank-logo test, staged: the logo disappears across three frames |
| 12 | Bonus take 01 | A receipt literally prints out and gets stamped **SETTLED IN VIBES** |
| 13 | Music taste | Equaliser bars run behind the four pillars of actual taste |
| 14 | The end | Mic drop with an impact ripple |

## Before you present

**Slide 2 needs your two photos.** The notes in the deck said to grab the same
model — one authentic, one high-quality replica. Two ways to do it:

1. **No editing:** click **⇄ Swap photos** on slide 2 and pick two images. They
   load instantly, just for that session.
2. **Permanent:** replace `assets/exhibit-a.png` and `assets/exhibit-b.png` and push.

The reveal currently labels **A = AUTHENTIC ($31,000)** and **B = 3% OF THE
PRICE ($5,000)**. If your photos put the fake on the left, swap the two
`verdict` blocks in `index.html` (search for `verdict--real`).

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
├── index.html          all 14 slides
├── css/styles.css      palette, layout, every animation
├── js/app.js           navigation, counters, vote game, notes, overview
└── assets/             exhibit-a.png, exhibit-b.png
```

Respects `prefers-reduced-motion` (animations collapse, content stays) and prints
to PDF with all reveals forced visible — a usable backup if the venue's wifi dies.
