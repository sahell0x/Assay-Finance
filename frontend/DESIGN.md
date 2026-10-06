# Design plan — Assay

> **Current design: "Report Card" (October 2026).** The product is now branded **Assay** — to
> assay is to test whether something is what it claims to be. The mark is an "A" cut out of a
> solid tile with a rising green crossbar; the tile follows the theme (`components/brand.tsx`,
> `app/icon.svg`). The visual direction was chosen from
> three researched demos (modelled on how Simply Wall St, Morningstar and Koyfin present
> stock research) and replaces the Swiss Ledger look described below:
>
> - **Ground and planes:** warm cream page (`--paper #fffaf1`), white cards with soft
>   green-tinted shadows, generous radii (12px controls, 20–24px cards, pill buttons).
> - **Colour:** deep green (`--brand #123c33`) for every action; yellow is a highlighter
>   (`.mark`) and the ingot, never "average". Verdicts: green buy, amber hold, coral sell,
>   with brighter `*-fill` tones for bars and shapes.
> - **Type:** Manrope for the interface (tabular figures), Newsreader for memo prose only,
>   system mono for formulae only. No uppercase mono labels; section labels are `.pill`s.
> - **Signature visual:** `components/report-shape.tsx` — the five dimension scores drawn
>   as a pentagon, filled in the verdict colour, straight from the stored scorecard.
> - **Frame:** one header on every page (`site-header.tsx`), full footer on marketing
>   pages and slim footer in the app (`site-chrome.tsx`), split sign-in layout with a real
>   report card (`auth-layout.tsx`). Light is the default; dark is a deep-forest variant.
>
> Everything below is the earlier plan, kept for its reasoning (computed vs written
> registers, show the working, absence is information), which still holds.

---

Written before any component. Revised once against the brief (see **Review** below), then
built. Critiqued after the build (see **Critique**).

---

## 1. Subject, audience, job

An analyst's working instrument. Not a marketing page about AI, not a dashboard for
executives — the thing a person has open while deciding whether to put money into
something.

The vernacular it borrows from: **rating actions** (how agencies publish a decision — the
rating, the scale it sits on, the date, the reasoning), **tear sheets** (a dense strip of
the numbers you check first), and **worksheets** (visible arithmetic, aligned columns).

Audience: someone comfortable with financial statements who will scan a table of twelve
ratios in four seconds and then read 300 words of prose carefully. Those are two
different reading modes and the design has to serve both without compromising either.

The job: make it obvious, without being told, that the numbers were computed and the
prose was sourced.

---

## 2. Colour

One palette, defined once in OKLCH, expressed in two vocabularies that cannot drift
apart: shadcn's semantic names (`background`, `card`, `primary`, `border`…), which the
vendored components depend on, and this product's domain names (`paper`, `ink`, `rule`,
`buy`/`hold`/`sell`), which say what a thing *is* in equity research. Both are declared
in `app/globals.css` from the same raw values.

Cool neutrals, blue-leaning. Nothing warm anywhere — no cream, no clay, no sand. A warm
ground makes figures look printed rather than computed.

```
            light                     dark
paper       oklch(.984 .003 247)      oklch(.176 .014 258)   page ground
surface     oklch(1 0 0)              oklch(.214 .015 258)   raised planes
ink         oklch(.205 .018 254)      oklch(.965 .004 247)   primary text
ink-muted   oklch(.522 .016 252)      oklch(.672 .015 252)   secondary text
rule        oklch(.903 .006 250)      oklch(.302 .016 258)   borders
brand       oklch(.505 .155 251)      oklch(.702 .145 250)   interactive only
```

**Dark mode exists**, and it is selected rather than inverted: the same hues at a
different lightness, so the dark theme reads as the same product. The ground is a deep
blue-charcoal, never black — on true black a raised plane can only be lighter grey and
every surface ends up looking like a scrim.

Ratings are the only saturated family, and the boldness is spent there because the
rating is the one judgement the whole pipeline exists to produce. Colour is never the
only carrier: the word is always present.

```
        light                  dark
buy     oklch(.525 .135 152)   oklch(.745 .155 155)
hold    oklch(.585 .125 74)    oklch(.795 .140 80)
sell    oklch(.545 .175 25)    oklch(.700 .175 22)
```

`unreliable` is deliberately **not** a colour — it is a struck rule and an em dash,
because an unreliable number should not look like a number.

### 2.1 Charts

The categorical palette is validated rather than chosen by eye, in both modes, against
lightness band, chroma floor, CVD separation under protanopia and deuteranopia, a
normal-vision separation floor, and 3:1 contrast on the surface. Adjacent pairs for
lines and bars; all pairs across the first three slots, which is what the peer scatter
uses. Every check passes in both modes.

```
light   #2563eb  #0d9488  #c2410c  #7c3aed  #be185d
dark    #3b82f6  #0d9488  #ea580c  #8b5cf6  #be4d8f
```

Slots are assigned in fixed order and never cycled. The margin cascade is a separate,
single-hue ramp because gross, operating, net and free-cash-flow margin are one quantity
at successive deductions rather than four identities; it flips its anchor in dark mode.

Every chart colour is a `var()`, not a hex literal. SVG presentation attributes are CSS
values, so the charts follow the theme with no re-render and a palette change lands in
one file.

## 3. Type

**One sans for the entire interface. One serif, for the memo body only.** That is an
inversion of the usual serif-display cliché and it is justified by how the content is
actually consumed: everything except the memo is *scanned*, and the memo is *read*.

| Role | Face | Why this one |
|---|---|---|
| Interface, all of it | **Public Sans** | Drawn for dense civic data tables; true tabular lining figures; holds up at 12px. Not Inter — Inter is the reflex, and this needs a face chosen for number columns rather than for UI in general. |
| Memo prose only | **Spectral** | Commissioned for extended on-screen reading. Low stroke contrast, sturdy at 17px, slightly narrow set so a 66-character measure fits the column without going airy. |
| Formulae only | system mono stack | The one sanctioned monospace. `net_income / avg(total_equity)` **is** code; setting it in a proportional face would be wrong. Never used for labels, never for decoration. |

Scale — a ~1.22 ratio, with the two text sizes (13 UI, 17 memo) pinned first and the rest
derived around them:

```
11  micro     units, footnotes, axis ticks
12  small     column headers, metadata, badges
13  cell      inside data tables only                 ← density where it earns it
14  base      controls, body UI                       ← the workhorse
16  lead      intro paragraphs, card titles
17  memo      serif body, 1.72 line-height, ≤66ch     ← the only serif
21  section   panel and section headings
28  page      page titles
40  display   the landing headline
44  rating    the rating word — the one large thing
```

The first version pinned 13px as the single body size. That is right inside a table of
twelve ratios and wrong everywhere else: the product is also read by people who do not
read financial statements for a living, and 13px of running prose told them the page was
not for them. 13 is now held back for table cells, where density is the point, and 14 is
the workhorse. Tracking tightens as size grows (-0.02em on headings); at 40px the default
spacing is most of what makes a large heading look unset.

Weights: 400 for everything, 500 for table headers and labels, 600 for headings and the
rating word. Nothing heavier. Hierarchy comes from size, space and alignment.

**`font-variant-numeric: tabular-nums` on every numeric cell and readout.** A `.nums`
utility exists and is used everywhere a digit appears, including chart axes and tooltips.
Ragged digit columns are the fastest way to make a financial interface look amateur.

---

## 4. Layout

Left-aligned throughout. Nothing is centred except the inside of a badge. A 1248px
content maximum, 24px gutters, collapsing to one column at 900px.

### 4.1 Landing — the working product, already loaded

**Revised.** The first version made the memo the hero: a real one, server-rendered, with
the input above it, then an architecture diagram and a list of libraries to close. That
was written for a reader who already knew what an equity research memo was, and it ended
by telling a visitor what the thing is *built from* rather than what they get. The
architecture diagram now lives on `/how-it-works` and appears nowhere else.

What replaced it, in order — because a visitor decides whether to care before they decide
whether to understand:

1. **Hero.** One sentence a non-specialist finishes, the search as the largest element,
   and beside it a *specimen*: one finished analysis shrunk to the four things that
   define one — the verdict, the scale that produced it, a sentence in the memo's own
   voice, and the two counts that say where it came from.
2. **Showcase.** Six real companies as cards; choosing one swaps the entire product
   below it — tear sheet, every tab, every chart, the evidence and the trace. A visitor
   is *using* the thing before they have typed anything.
3. **Capabilities.** Ten things a run produces, named the way a user would name them,
   with the ones that are pages linking to those pages.
4. **How a run works.** Three plain steps. Numbered because it genuinely is a sequence:
   the quantitative stages have to finish before retrieval knows what to look for.
5. **Close.** An account offered on what it adds, not as the price of seeing anything.

```
┌────────────────────────────────────────────────────────────────────────┐
│ ● Equity Research   New analysis Dashboard Watchlist Compare History   │
│                              [🔍 Search a ticker ⌘K] [⚡3] [☾] [Sign in]│
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  Research any                          ┌──────────────────────────┐   │
│  public company                        │ PFE  Pfizer Inc.      ↗  │   │
│  in ninety seconds.                    │                          │   │
│                                        │ SELL   ├────●──┼───┼──┤  │   │
│  Type a ticker. You get a written      │ 4.3/10 0     5.0 7.5  10 │   │
│  investment case with a buy, hold or   │                          │   │
│  sell call — every figure computed     │ │ Pfizer's 4.268 out of  │   │
│  from the company's own filings.       │ │ 10 composite supports  │   │
│                                        │ │ a SELL…       (serif)  │   │
│  ┌───────────────────┐ ╔════════════╗  │ ┌───────────┬──────────┐ │   │
│  │ 🔍 Apple, MSFT… ⌘K│ ║  Analyze → ║  │ │ Ratios 37 │ Sources  │ │   │
│  └───────────────────┘ ╚════════════╝  │ │           │    20    │ │   │
│  3 free analyses left, no account.     │ └───────────┴──────────┘ │   │
│                                        └──────────────────────────┘   │
├────────────────────────────────────────────────────────────────────────┤
│  Look through one that is already done      [Open PFE on its own page] │
│  ╭─PFE──╮ ╭─KO───╮ ╭─JPM──╮ ╭─NVDA─╮ ╭─AAPL─╮ ╭─MSFT─╮                │
│  ┃ SELL │ │ HOLD │ │ HOLD │ │ BUY  │ │ HOLD │ │ HOLD │   ← click any  │
│  ┃ 4.3  │ │ 5.8  │ │ 5.4  │ │ 7.9  │ │ 6.0  │ │ 7.0  │                │
│  ┃ ▁▃▂▅▃│ │ ▅▃▆▂▄│ │ ▃▅▄▃▅│ │ ▇▆▅▇▄│ │ ▆▄▅▃▅│ │ ▇▅▆▄▆│                │
│  ╰──────╯ ╰──────╯ ╰──────╯ ╰──────╯ ╰──────╯ ╰──────╯                │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ PFE  Pfizer Inc.  SELL      $27.56  $157.09B  36.26x  4.3/10     │ │
│  │ Memo  Profitability  Liquidity  Growth  Peers  Evidence  Trace   │ │
│  │ ────                                                             │ │
│  │ [ the entire analysis, live and interactive ]                    │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Result page

A tear-sheet header (the numbers you check first), a left-aligned underline tab bar, then
the tab body. The header stays; the tabs scroll.

```
┌──────────────────────────────────────────────────────────────────────┐
│ AAPL  Apple Inc.        Technology · Consumer Electronics             │
│ $245.12   MCAP 4.77T   P/E 36.3   EV/EBITDA 25.8   COMPOSITE 6.0     │
├──────────────────────────────────────────────────────────────────────┤
│ Memo   Profitability   Liquidity   Growth   Peers   Evidence   Trace │
│ ────                                                                 │
├──────────────────────────────────────────────────────────────────────┤
```

### 4.3 The metric table and the derivation strip

The most distinctive thing in the interface. Every row opens in place to show the formula
and the statement lines that fed it — the interface never asks you to take a number on
trust.

```
  METRIC                        TTM      PEERS         5Y TREND
  ───────────────────────────────────────────────────────────────
  Gross margin                46.2%    ──●───  p71     ╱╱╲╱
  Operating margin            31.5%    ────●─  p88     ╱╱╱╱
  Return on equity           157.4%    ─────●  p99     ╱╲╱╱   ▾
  ┌─────────────────────────────────────────────────────────────┐
  │ net_income / avg(total_equity, prior_total_equity)          │  ← mono
  │                                                             │
  │ net_income                               93,736,000,000     │
  │ total_equity                             56,950,000,000     │
  │ prior_total_equity                       62,146,000,000     │
  │ avg_total_equity                         59,548,000,000     │
  └─────────────────────────────────────────────────────────────┘
  Net debt / EBITDA              —     ──────        —          ▾
                                 ↑ em dash, hover explains why
```

The peer rail is a 56px track with a centre tick at the median and a dot at the
percentile. It is not a progress bar — it has a midpoint, and a dot left of centre means
something different from an empty bar.

### 4.4 Pipeline

The one place motion is allowed. Ten nodes, left-aligned, illuminating in sequence as
events arrive. A hairline rail runs down the left edge; the active node's marker fills.
Completed nodes keep their duration and their one-line result.

```
  │● Fetch filings            ok   4.9s   coverage 100%, 5 periods
  │● Validate data            ok   0.0s
  │● Profitability            ok   0.0s   score 9.2, 10 metrics
  │◐ Liquidity & solvency     running
  │○ Growth
  │○ Peer comparison
  │○ Retrieve evidence
```

---

## 5. Principles

1. **Two registers.** Sans with tabular figures means *we computed this*. Spectral serif
   means *we read this and cited it*. The typography carries the product's central
   epistemological claim, so a reader absorbs it without being told.
2. **Show the working.** Every metric opens into its formula and its inputs. This is the
   affordance the whole design is arranged around.
3. **Make the rule visible.** The rating band draws the two thresholds and marks where the
   composite landed. The determinism is a thing you can *see*, not a claim in a README.
4. **Density where it earns it.** 32px rows, right-aligned tabular figures, 13px inside
   tables. A worksheet, not a brochure — but only in the parts that are scanned. Running
   prose is 14px, because a reader who does not do this for a living reads it too.
5. **Absence is information.** A missing value is an em dash with a reason attached.
   Never `0`, never `NaN`, never blank.
6. **Spend boldness once.** The rating block is the only large, saturated, memorable
   element. Everything else stays quiet.
7. **Nothing worth showing sits behind an account.** History, the watchlist, comparison
   and every tab of a finished analysis work against an anonymous cookie. An account
   raises the allowance and carries the work between devices; it does not unlock
   features. A product whose output you cannot see before signing up has nothing to sign
   up for.

---

## 6. Review of this plan against the brief

Worked through what I would produce for "build a nice financial dashboard" with no further
direction, to find where this plan was still sitting on a default.

**Changed — the hero.** First pass had a headline, a subhead, and the input centred over a
gradient-free but otherwise conventional hero, with the sample memo below the fold. That
is the default shape for any product page and it buries the only thing worth showing.
Revised: the memo is the hero. The heading is two lines, left-aligned, and the fold cuts
*inside* the memo so it is obvious there is a real document there.

**Changed — the dimension scores.** First pass had five donut charts, one per dimension.
Donuts are decoration: they encode one number in an area that is hard to compare across
five instances. Revised to a right-aligned bar rail in the scorecard, which makes the five
scores comparable at a glance and takes a quarter of the space.

**Changed — flag colours.** First pass used green/amber/red dots on metric rows. That is
the traffic-light treatment the brief rules out, and at twelve rows a column of coloured
dots is louder than the values. Revised: the flag tints the *value* itself by one step and
sets a 2px mark at the row's right edge; `unreliable` drops colour entirely and strikes
the rule, because an unreliable number should not look like a number.

**Changed — typefaces.** First pass said Inter and Source Serif, which is what I would pick
for anything. Revised to Public Sans (drawn for civic data tables, chosen for its figures
rather than for general UI) and Spectral (commissioned for on-screen long-form). Both are
choices about this content rather than reflexes.

**Kept, with a reason — monospace.** The brief bans monospace as decoration for small data
labels. It is kept for exactly one thing: the formula strings, which are code. Recorded
here so the critique pass can check the rule held.

**Kept — the peer rail.** Checked whether it was a progress bar wearing a hat. It is not:
it has a fixed midpoint tick, the dot can sit either side of it, and direction is
meaningful (left of centre on a valuation multiple is *good*). It encodes rank, which
nothing else on the row does.

**Decided — no dark mode.** The brief pins a light cool-neutral palette and says nothing
about dark. Building a second theme would double the surface area of every chart and table
for something unasked. Light only, with every colour set explicitly so nothing inherits
the host's theme.

---

## 7. Component inventory

```
app/
  layout.tsx                 tokens, fonts, header, footer
  page.tsx                   landing: input + live sample memo + architecture
  analyze/page.tsx           ticker autocomplete, peers, weight sliders
  analysis/[id]/page.tsx     pipeline → result tabs
  m/[slug]/page.tsx          public memo
  how-it-works/page.tsx      plain-English method and FAQ for users (engineering notes: docs/)
  dashboard|history|watchlist|compare/page.tsx
  login|signup/page.tsx

components/
  rating-block.tsx           THE bold element: rating word + band rule
  band-rule.tsx              0–10 scale with threshold marks
  metric-table.tsx           dense table, expandable derivation strip
  derivation-strip.tsx       formula (mono) + inputs ledger
  peer-rail.tsx              percentile dot on a midpoint track
  pipeline.tsx               SSE-driven node checklist, the one motion
  tear-sheet.tsx             sticky header strip of key figures
  scorecard-rail.tsx         five dimension bars + composite
  memo-body.tsx              serif prose with citation markers
  evidence-list.tsx          sources with type, date, relevance
  charts/                    margin-trend, dupont-waterfall, gauges,
                             ccc-bar, revenue-growth, peer-scatter, score-history
  ui/                        shadcn primitives, restyled to tokens
```

---

## 8. Critique

Worked through the banned list in the brief item by item against the built interface,
with screenshots open. Where a check could be made mechanically it was — grepping is more
reliable than remembering.

| # | Banned pattern | Verdict |
|---|---|---|
| 1 | Warm cream ground, high-contrast serif display, terracotta accent | **Pass, with a note.** Ground is `#F7F8F8` (cool), the serif is body-only and never a display face, the accent is a deep slate blue. See the note below on the HOLD ochre. |
| 2 | Near-black ground with one acid accent | **Pass.** Light only; no saturated accent anywhere. |
| 3 | Broadsheet pastiche — hairline rules everywhere, zero radius, faux columns | **Pass.** Radius is 2-3px, not 0. Counted the rules on the landing page: three, each separating a different *kind* of content (input from output, heading from document, document from architecture). None decorative. |
| 4 | The SaaS card kit — identical rounded cards, one shadow under each | **Pass.** `.panel` is a 1px border with **no shadow**. Shadows exist on exactly four elements — tooltip, dialog, autocomplete dropdown, chart tooltip — all of which genuinely float. Verified by grep. |
| 5 | Tracked-out ALL-CAPS eyebrow labels | **Pass.** Grep found `uppercase` only on ticker *input fields*, where it is correct; `input::placeholder` explicitly resets the transform so the placeholder sentence is not shouted. No `tracking-wide` anywhere. |
| 6 | Meta strings joined with middle dots | **Failed, fixed.** Two: the page-title template and a `" · replay"` badge on the pipeline. Both rewritten. Grep now returns nothing. |
| 7 | `→` appended to link and button text | **Pass.** Grep: none. |
| 8 | Monospace for small data labels as decoration | **Pass, by exception.** Mono appears in one place: the derivation strip's formula and its input field names, which are the identifiers *from that formula*. Setting `net_income / avg(total_equity)` in a proportional face would be wrong. Declared in §6 before building so this pass could check it held. |
| 9 | Accenting one word in a headline | **Pass.** No headline carries a coloured or italicised word. |
| 10 | Purple/blue gradient hero; gradient washes as decoration | **Pass.** One `linear-gradient` in the codebase: the sweep inside the loading skeleton, which is an animation, not ornament. |
| 11 | Emoji in headings or section markers | **Pass.** Grep over the emoji ranges: none. |
| 12 | `01 / 02 / 03` markers unless genuinely sequential | **Pass.** One numbered list — the pipeline preview on `/analyze` — which is a real sequence, rendered as plain `1.` rather than styled `01 /` markers. |
| 13 | Fade-and-slide-up on every section; hover lift on every card | **Pass.** Grep for `hover:scale`, `hover:-translate`, `animate-in`, `fade-in`: none. Three animations exist in total — the pipeline's active-node pulse, the derivation strip opening, and the skeleton shimmer. Two answer a user action; one is the single orchestrated moment. `prefers-reduced-motion` disables all of them. |

### What the rendered output revealed that the source did not

Reviewing screenshots rather than code caught five things that typechecked cleanly:

1. **Every `bg-[--color-x]` class was dead.** Tailwind v4 compiles that syntax to
   `background-color: --color-accent` — a bare custom-property name, which is invalid and
   dropped. The primary button had no fill. Found by reading the compiled stylesheet.
   Moved to the `@theme`-generated utilities.
2. **The metric table came back shuffled.** Postgres reorders JSONB keys, so margins were
   interleaved with returns on capital. Blocks now carry an explicit display order.
3. **The DuPont labels sat at the wrong end of each bar** — saying asset turnover took
   Microsoft's product *up* to 40% when it took it *down* to 18%. Labels now sit at the
   running value, with dashed connectors at the hand-off levels.
4. **The cash-cycle chart drew one solid green bar** for any company whose payables exceed
   its gross cycle, which is most large ones. Rebuilt as two rows against a shared zero.
5. **The valuation scatter was flattened onto its baseline** by a single peer at 2,913x
   EBITDA.

### Notes and accepted tensions

**The HOLD ochre.** On a HOLD memo, `#8A6A1F` is the warmest and most saturated thing on
screen — a 44px word and a 2px rule. It is not the banned terracotta: it is one of three
semantic rating colours, it is earned by the content, and the same slot holds a muted
green or a muted red for the other two ratings. Kept, deliberately.

**The dataviz colour rules.** An external validator was run over the chart palette. It
fails its chroma floor and its categorical-separation checks — necessarily, because those
checks require saturated hues and this brief requires muted cool neutrals. The brief wins.
Where the conflict actually bit — four margin lines that must be tellable apart — the fix
was the *form*, not the colour: margins are one quantity at successive deductions, so a
single-hue cascade is the honest encoding; the one pair that can genuinely cross is
separated by a dash; and every line is labelled at its end, so identity never rests on
colour alone. Every series colour was then checked to clear 3:1 contrast against the
surface, which it does.

**The dual axis on revenue and growth.** Also against general advice, and used anyway
because the second series is the *derivative of the first* rather than an unrelated
measure. Both axes are labelled with their units and the growth axis has a visible zero.

### Still on the list

- The trace tab's stage rows showed raw node names (`news rag`) until this pass. Fixed by
  mapping through the pipeline's own labels, but it is a reminder that system vocabulary
  leaks wherever a payload is rendered without translation.
- Offline mode's placeholder narrative is honest but unlovely. With a key configured it
  never appears; without one it is the correct thing to show.

---

## 9. Second pass

The first build satisfied the brief and failed the audience. The brief said "an analyst's
working instrument"; the product is also used by people who have never read a 10-K, and
three things followed from taking that seriously.

**The landing page was documentation.** It closed with an architecture diagram and a
four-column list of libraries. Accurate, and addressed to a reader deciding whether to
clone the repository rather than one deciding whether to trust a rating. The diagram moved
to `/how-it-works`; the front door now shows the working product with six real companies
loaded into it. See §4.1.

**The interface hid its own features.** `site-header.tsx` marked Dashboard, Watchlist,
History and Compare as account-only, and the four page components each rendered a
sign-in wall. The backend had never required an account for history — `deps.py` says in
its own docstring that anonymous visitors get the full feature set — so the gate was
frontend-only for two of them and a genuine backend restriction for the other two. The
restriction is gone: watchlists gained an `anon_id` alongside `user_id` (migration 0002),
compare became owner-scoped, and signing up now carries the watchlist across as well as
the analyses. A visitor can use everything and loses nothing by waiting.

**Dark mode was declined, and that was the wrong call.** The first pass argued a second
theme doubled the surface area of every chart and table for something unasked. It did
double it — and the exercise found that nine chart components had hardcoded hex, that
`.panel`, the tooltips and three tables had baked-in near-whites, and that the usage
meter was painting its pips in a colour that had quietly become a wash. Those were latent
defects in the light theme's construction, not costs of the dark one. Everything is a
token now.

### What the second build changed structurally

- **shadcn/ui, properly installed**, replacing nine hand-rolled primitives; the product's
  own extensions (`Hint`, `ratingTone`, `SkeletonTable`, the rating tones on `Badge`) are
  layered on top rather than kept alongside.
- **One palette, two vocabularies**, in one file, so a colour cannot mean one thing to a
  `Card` and another to a metric table. Two names collided with shadcn's and were
  migrated rather than aliased: `text-muted` → `text-muted-foreground`, `*-accent` →
  `*-primary`.
- **One search.** A ⌘K command palette owned by a provider, reachable from the header,
  the hero and the closing call to action. It carries recent analyses as well as ticker
  search, because reopening something already run is the commonest reason to search and
  costs nothing from the allowance.
- **The dual-axis chart is gone.** Revenue and its growth rate shared an x-axis and had
  two y-scales. The original defence — growth is the derivative of revenue, not an
  unrelated measure — is true and still insufficient: the crossings a reader sees remain
  artefacts of where the axes were pinned. Two stacked panels on one shared x say the
  same thing and cannot mislead, and growth gained a real zero line with negative bars
  below it.
- **The chart palette now passes its validator.** The first pass recorded that it failed
  the chroma floor and categorical-separation checks, necessarily, because the brief
  demanded muted cool neutrals. With that constraint lifted for the chart layer
  specifically, every check passes in both modes — including all-pairs across the three
  slots the peer scatter uses.

### One defect found by looking rather than by testing

Rendering the growth tab in dark mode showed the memo narrative reading `[provider
unavailable] … BadRequestError: 'temperature' does not support 0.3 with this model`. The
configured models accept only their default temperature and answer a 400 to anything
else, so every narrative, the sentiment call and both critic passes had been falling back
to placeholder text. The figures were never affected — they are computed in Python, which
is the whole architecture — but the writing was gone and the verifier was not running.
`ModelRouter` now retries once without the parameter and remembers the refusal per model,
so one probe is paid per process rather than one failed request per call. Four tests cover
it, including that an unrelated 400 still degrades rather than silently retrying.
