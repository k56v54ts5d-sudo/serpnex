# Link Intelligence Platform
## Product Design Brief & UX Blueprint

**Prepared for:** Senior Product Design handoff (high-fidelity UI/UX)
**Document type:** Self-contained design brief — no further product clarification required
**Status:** Ready for design

---

## 0. How to read this document

This brief is written so a senior product designer can open Figma and start drawing without asking a single product question. Where a judgment call was needed, the decision was made and stated rather than left open. Anything marked *(assumption)* is a defensible default you may overrule with reason.

The product's entire identity reduces to one sentence, and every screen must serve it:

> **The user should never wonder what to do next.**

If a screen shows data without a decision attached, it is wrong. If a verdict appears without a traceable reason, it is wrong. If a reason appears without a recommended action, it is wrong. The unit of the product is not a metric — it is **Decision → Reason → Action.**

---

# PART ONE — PRODUCT FOUNDATION

## 1. Product architecture (full)

### 1.1 The core thesis the architecture must express

Competitors are **data explorers** — they hand the user everything and say "you figure it out." This product is a **decision system** — it does the figuring out and hands back a verdict the user can act on or defend to a client. The architecture is therefore organized around *objects that hold decisions*, not around datasets.

### 1.2 The object model (the spine of everything)

The product is built on a strict hierarchy. Every screen, route, and permission derives from this.

```
Workspace (the agency / the account)
│
├── Members (seats, roles, permissions)
├── Integrations (Google Search Console, billing)
│
└── Sites (a website being worked on — usually a client)
    │
    └── Pages (the central object — a target URL being optimized)
        │
        ├── Readiness Assessment      ← Module 1
        ├── Bottleneck Diagnosis      ← Module 2
        ├── Opportunities[]           ← Module 3 (many per page)
        │     └── Execution Plan      ← Module 4 (one per pursued opportunity)
        │            └── Tracked Link  ← Future: outcome loop
        │
        └── Forecast (expected impact, attached to the page)
```

**The Page is the hero object.** A user does not "use Module 1 then Module 2." A user opens a **Page Workspace** and the four questions are answered there, in order, as a guided vertical narrative. This single decision removes the biggest UX risk in the original spec — four disconnected tools that each demand the same URLs re-entered.

### 1.3 The four modules as a single narrative

Inside a Page Workspace the modules read as one strategist's report, top to bottom:

1. **Readiness** — "Is this page even worth linking to yet?" *(gate)*
2. **Bottleneck** — "If it's underperforming, what's actually holding it back — and is it even links?" *(diagnosis)*
3. **Opportunities** — "Here are specific link targets, each judged *for this page*." *(due diligence)*
4. **Execution** — "For the ones worth pursuing, here's exactly how to do it." *(playbook)*

Module 2 is the intellectual center of the product. It is the screen that makes a user say *"I've never seen a tool tell me that"* — because it can conclude **"links are not your problem here, stop building them."** Design must give Bottleneck the most editorial weight.

### 1.4 The intelligence layer (abstracted for design)

Designers do not need the data pipeline, but they must design for three truths it creates:

- **Analyses take real time** (seconds to ~1–2 minutes; multiple APIs + reasoning). The "running" state is a designed *experience*, not a spinner — see §12.2.
- **Confidence varies.** Every verdict carries a calibrated confidence level. The UI must express low/medium/high confidence honestly and never fake certainty.
- **Some pages have insufficient data** (brand-new pages, no GSC history). "Not enough signal yet" is a first-class outcome, not an error — see §12.4.

### 1.5 Account & access model

- **Workspace-level** billing, integrations, and member roles.
- **Roles:** Owner, Admin, Strategist (full analysis), Viewer (read-only — for clients or junior staff).
- **(Assumption)** Seat-based pricing with an analysis-volume component; clients can be invited as free Viewers to read forecasts and verdicts. This is a deliberate growth loop — agencies showing verdicts to clients *is* the marketing.

---

## 2. Information architecture

### 2.1 Content hierarchy (what nests in what)

```
Home (Command Center)
Sites
  └ Site detail (portfolio of pages, prioritized)
      └ Page Workspace
          ├ Readiness
          ├ Bottleneck
          ├ Opportunities
          │   └ Opportunity detail (due-diligence report)
          │       └ Execution plan
          └ Forecast
Opportunities (cross-site library)
Campaigns / Tracking (future-gated)
Settings
  ├ Workspace
  ├ Members
  ├ Integrations
  └ Billing & Plan
```

### 2.2 IA principles specific to this product

- **One canonical place per object.** A given Opportunity lives under its Page; the cross-site Opportunities library is a *view*, not a second home.
- **Decisions are surfaced, data is buried.** Raw metrics are never a top-level destination. They live behind a "Show the evidence" disclosure on each verdict. The default depth a user sees is *verdict + reason + action*; one click deeper reveals supporting signals; the raw numbers are the third and final layer, deliberately hard to wander into.
- **Prioritization is the organizing logic of lists.** Every list of Pages or Opportunities is sorted by *what to do next*, never alphabetically or by raw score.

---

## 3. Navigation structure

### 3.1 Shell

A **persistent left sidebar** (Linear/Notion register), a **slim top context bar**, and a **global command action**. No top mega-nav, no nested horizontal tabs at the app level.

**Left sidebar (primary nav):**
- ⌘ **New Analysis** (primary action, pinned top — opens the command launcher)
- **Home**
- **Sites**
- **Opportunities**
- **Campaigns** *(locked badge until plan/phase unlocks)*
- — divider —
- **Settings**
- Workspace switcher + user avatar (bottom)

**Top context bar (within a Site or Page):**
breadcrumb (`Site / Page`), the page's live readiness badge, and contextual actions (Re-run, Share, Export). It is quiet — it orients, it doesn't decorate.

### 3.2 The command launcher (signature interaction)

`⌘K` / the **New Analysis** button opens a single input that accepts a URL and infers intent:

- Paste a **page URL** → offers "Run full page analysis" (Readiness + Bottleneck).
- Paste a **page URL + a guest-post URL** → offers "Evaluate this opportunity."
- Type a site name → jumps to it.

This is the product's front door. It reinforces *"ask the strategist a question,"* not *"navigate a tool."* It must feel instant and a little magic.

---

## 4. User journey map

Three primary journeys. Each is mapped as **Trigger → Steps → Emotional target → Exit state.**

### 4.1 Agency strategist — "Should we spend this client's link budget here?"

| Stage | What happens | Feeling target |
|---|---|---|
| Trigger | Monthly planning; client has a budget, 40 candidate pages | Overwhelmed → seeking control |
| Entry | Opens Site → sees pages auto-prioritized by readiness + opportunity | "It already did the triage" |
| Diagnose | Opens top page → Readiness ✅, Bottleneck = "Link authority (primary)" | "Now I know it's a links problem" |
| Quantify | Sees forecast: closing the gap ≈ +X positions ≈ $Y/mo | "I can sell this to my client" |
| Decide | Reviews 5 evaluated Opportunities, 2 Recommended | "I know which to buy" |
| Execute | Opens Execution plan → anchor + format + placement | "I know exactly how to brief the writer" |
| Exit | Exports a client-facing one-pager | Confident, accountable |

### 4.2 Freelance consultant — "Is this opportunity I was pitched any good?"

Trigger: a vendor emailed a guest-post offer. Enters page URL + guest URL in the launcher → gets a **due-diligence verdict** (Recommended / Conditions / Avoid) with reasons in 60 seconds. Exit: replies to the vendor with confidence. *Speed is the whole experience here* — this journey must be completable in under two minutes from cold open.

### 4.3 In-house marketer — "Why won't this page rank?"

Lower SEO fluency. Trigger: a priority page is stuck. Enters the page → **Bottleneck** explains in plain language ("Your content covers the topic well, but you're losing on authority vs. the top 3") with a prioritized fix list. Exit: a credible internal recommendation they can paste into a ticket. *Voice and plain-language explanation matter most here.*

### 4.4 Cross-cutting "aha" moment

The single moment that converts a trial is **the first Bottleneck verdict that says something non-obvious** — especially *"links are not your problem."* Onboarding (§16) is engineered to reach this moment as fast as possible.

---

# PART TWO — SCREENS

## 5. Dashboard structure (Home / Command Center)

The Home screen is **not** a metrics dashboard. It is a **decision queue**. It answers one question on load: *"What should I work on next?"*

**Layout (top to bottom):**

1. **Greeting + command line.** A large, calm header with the New Analysis input front and center. Generous whitespace. This is the Stripe/Linear "one clear thing" opening.
2. **Priority worklist** — the core of Home. A ranked list of *recommended next actions across all sites*, each phrased as a decision, e.g.:
   - "📈 *acme.com/knives* is ready and link-limited — best ROI this week."
   - "⚠️ Stop linking *acme.com/guide* — bottleneck is content, not links."
   - "🔍 3 new opportunities await a verdict."
   Each row is a one-line decision with a single CTA. No charts.
3. **Recent verdicts** — a quiet feed of the last analyses, each a small verdict chip (page, outcome, confidence) for fast re-entry.
4. **(Optional, collapsed) Portfolio pulse** — *one* restrained summary strip: # pages ready, # link-limited, # opportunities pending. Numbers as quiet context, never as the centerpiece.

**Explicitly excluded from Home:** trend graphs, traffic charts, metric tiles, anything that looks like Ahrefs. If a designer is tempted to add a graph here, the answer is no.

---

## 6. Complete page inventory

**Auth & entry**
1. Sign up
2. Sign in
3. Forgot / reset password
4. Email verification / SSO callback

**Onboarding**
5. Onboarding wizard (connect GSC → add site → first analysis → aha reveal)

**Core app**
6. Home / Command Center
7. Sites list (portfolio)
8. Site detail (prioritized pages)
9. Page Workspace — Readiness section
10. Page Workspace — Bottleneck section
11. Page Workspace — Opportunities section (list)
12. Opportunity detail (due-diligence report)
13. Execution plan
14. Page Workspace — Forecast panel
15. Opportunities library (cross-site)
16. Campaigns / Tracking *(future-gated placeholder + teaser)*

**Account**
17. Settings — Workspace
18. Settings — Members & roles
19. Settings — Integrations (GSC)
20. Settings — Billing & Plan
21. Upgrade / plan comparison
22. Share / export (client-facing report view)

**System**
23. Global empty/loading/error variants (documented as states in §11–12, not separate routes)
24. 404 / permission-denied / analysis-failed

---

## 7. Wireframe descriptions (every page)

For each: **purpose · layout · key components · states.** All screens inherit the shell (§3) unless noted.

### 7.1 Sign up / Sign in (5,1–4)
**Purpose:** frictionless entry; signal premium-modern immediately.
**Layout:** centered single-column card on a quiet full-bleed background (subtle gradient/grain, Vercel-like). Left-aligned wordmark. Email + Google/SSO. One sentence of positioning under the logo: *"Decisions, not dashboards."*
**Components:** auth card, OAuth button, inline validation.
**States:** loading (button spinner), error (inline, never modal).

### 7.2 Onboarding wizard (5)
**Purpose:** reach the first verdict fast.
**Layout:** full-screen, one step per view, a thin progress rail at top, lots of air. Never more than one decision per screen.
**Steps:**
1. **Connect Google Search Console** — explained as "so we can see how your pages actually perform." Skippable, but with an honest note that diagnosis is weaker without it.
2. **Add your first site** — single URL field; we auto-detect pages in the background.
3. **Pick a target page** — we suggest 3–5 candidate pages (from GSC) framed as "let's diagnose one of these." User picks one.
4. **Watch it work** — the designed running state (§12.2): the strategist "thinking" with steps revealing.
5. **The reveal** — the first Bottleneck verdict, full-bleed, with a single CTA into the Page Workspace.
**Components:** stepper, integration card, page suggestion cards, the running-analysis experience, verdict reveal.

### 7.3 Sites list / portfolio (7)
**Purpose:** choose a client/site.
**Layout:** a clean list (not a grid of heavy cards). Each row: site name, favicon, a compact status summary (*"6 pages · 2 ready · 1 link-limited"*), last-analyzed time.
**Sort:** by attention needed, not alphabetical.
**States:** empty ("Add your first site"), loading (skeleton rows).

### 7.4 Site detail — prioritized pages (8)
**Purpose:** the agency's triage view — *"where do I spend this site's budget?"*
**Layout:** header with site name + "Analyze a page" action. Below, a **prioritized page list**. Each row is a *decision row*: page path, readiness badge, primary bottleneck tag, and a one-line recommendation (*"Ready + link-limited — high ROI"* / *"Fix content first"*). A subtle priority indicator (rank or a quiet bar) orders them.
**Key design note:** this list is the portfolio-allocation feature in disguise. It must read as a worklist, not a table of stats.
**States:** empty (no pages analyzed yet → prompt to run first), loading, mixed (some pages analyzed, some pending).

### 7.5 Page Workspace — overview & Readiness (9)
**Purpose:** the hub object; first answers *"is this page ready?"*
**Layout:** a **single scrolling narrative** with a sticky left mini-nav (Readiness · Bottleneck · Opportunities · Execution · Forecast). The page opens on a **Verdict Header** for Readiness.
**Readiness section components:**
- **Verdict Header:** large `Ready` / `Not Ready` with the muted semantic color, confidence indicator beside it, and a single-sentence rationale.
- **Reason block:** 2–4 plain-language reasons (content sufficiency, intent coverage, internal authority, etc.), each a short line with an optional "show evidence" disclosure.
- **Action checklist:** if Not Ready, prioritized fixes as checkable items ("Expand section on X," "Add 3 internal links from category pages"). Each action carries a priority tag (P1/P2).
**States:** running, ready-verdict, not-ready-verdict, insufficient-data, error.

### 7.6 Page Workspace — Bottleneck (10) — *the centerpiece*
**Purpose:** *"what's actually preventing this page from ranking — and is it even links?"*
**Layout:** the most editorial screen in the product. Generous, confident.
**Components:**
- **Primary Constraint, stated as a headline:** e.g. *"Link authority is your primary constraint."* or, critically, *"Links won't help here — your bottleneck is search-intent mismatch."*
- **Constraint Breakdown:** a single restrained horizontal bar segmenting the gap (e.g., Authority 60% · Content 25% · Internal links 15%). This is the *only* chart-like element allowed prominence in the product, because it directly encodes a decision. No axes, no legends-as-decoration — labeled segments only.
- **Secondary constraints:** listed briefly beneath.
- **Competitive context line:** "vs. the current top 3, you're closest on content, furthest on referring domains." One sentence, plain language.
- **Recommended action + expected priority:** the explicit "do this next."
- **"Show the evidence" disclosure:** reveals the supporting signals (competitor RD counts, content gap notes) — buried by default.
**States:** running, verdict (links-primary / not-links / mixed), insufficient-data.

### 7.7 Page Workspace — Opportunities list (11)
**Purpose:** *"which link targets are worth it for THIS page?"*
**Layout:** intro line tying back to the bottleneck ("Since this page is link-limited, here are evaluated targets"). Then a list of **Opportunity Verdict Cards**.
**Opportunity Verdict Card:** guest site name + favicon, the verdict pill (`Recommended` / `With conditions` / `Avoid`), one-line reason, confidence. Tapping opens the due-diligence detail.
**Empty state:** "No opportunities evaluated yet — paste a guest-post URL to assess one," with the inline input present.
**States:** empty, evaluating (a card in running state), populated (sorted best-first).

### 7.8 Opportunity detail — due-diligence report (12)
**Purpose:** make the user feel they're reading a vetting memo, not an SEO audit.
**Layout & voice:** structured like diligence. Verdict at top; then themed sections written as findings, each a short paragraph + a green/amber/red read:
- **Relevance fit** (market / topic / intent / language match — *for this specific page*)
- **Placement quality** (will the link sit naturally in real content?)
- **Authority worth passing** (the guest site's own backlink support — kept lightweight)
- **Risk flags** (link-selling footprints, bad neighborhood, instability)
- **Bottom line:** the verdict restated with the decisive reason.
**Components:** verdict header, diligence sections, risk banner, "evidence" disclosures per section, primary CTA → "Build the execution plan."
**States:** running, verdict, error.

### 7.9 Execution plan (13)
**Purpose:** the playbook — *"how exactly to build this link."*
**Layout:** a clean prescriptive card stack, each a single clear recommendation:
- **Target page confirmation** (which of the site's pages this link should point to — may differ from the one the user started on; surfaced as a recommendation).
- **Anchor strategy** (branded / partial / generic / contextual) — *portfolio-aware*: notes the page's current anchor mix and what to add next to keep it natural.
- **Article format** (case study / comparison / tutorial / guide / research).
- **Placement** (intro / body / supporting section) with a one-line "why here."
- **Risk warnings** (e.g., "Good opportunity — but don't build yet; page isn't ready" / "A different page would benefit more").
**Components:** recommendation cards, copy-to-brief action (export the plan as a writer brief), risk banner.
**States:** standard, "page-not-ready" override (the plan is shown but gated with a warning).

### 7.10 Forecast panel (14)
**Purpose:** translate the decision into business value the agency shows clients.
**Layout:** a compact, premium panel within the Page Workspace: *"Closing the authority gap (~N quality referring domains over ~3 months) should move this page from position ~7 → ~3–4, ≈ +$Y/mo."* A confidence band is shown honestly. One small gap-bar (current vs. target RDs) is permitted. Strictly framed as a projection, not a promise.

### 7.11 Opportunities library (15)
**Purpose:** cross-site view of all evaluated opportunities; reusable vendor intelligence.
**Layout:** filterable list (by verdict, by site, by date). Each row a compact verdict chip. Useful for agencies who get the same vendor offers repeatedly.

### 7.12 Campaigns / Tracking (16) — future-gated
**Purpose:** placeholder for the outcome loop. Until unlocked, a single elegant teaser screen: "Coming: track built links and watch the forecast prove out." Designed now so the nav slot and mental model exist early.

### 7.13 Settings (17–20)
Standard, restrained. **Integrations** screen centers GSC connection status with honest copy about what diagnosis quality depends on it. **Members** uses simple role rows. **Billing** shows current plan, usage against limits (analyses used / seats), and the upgrade entry.

### 7.14 Share / export (22)
**Purpose:** the growth loop — a clean, **client-facing** read-only report: the verdict, the bottleneck, the forecast, the recommendation, *with raw metrics stripped out entirely* and optional workspace branding. Exportable as a link or PDF. This view is where the product sells itself to the agency's clients.

---

## 8. Mobile experience considerations

Mobile is **review & decide**, not deep work. Agencies run analyses at the desk; they *check verdicts* on the phone.

- **Priority order on mobile:** Home worklist, recent verdicts, and the verdict screens (Readiness/Bottleneck/Opportunity) read beautifully. Heavy authoring (briefing, settings) degrades gracefully or is gently deprioritized.
- **Verdict-first stacking:** every analysis screen collapses to verdict → reason → action vertically; the "evidence" disclosures stay collapsed by default on mobile to protect focus.
- **The Constraint Breakdown bar** remains (it's one bar — it travels well). The forecast panel stacks below.
- **Command launcher** becomes a full-screen sheet from a bottom FAB.
- **Bottom tab bar** on mobile: Home · Sites · New (center FAB) · Opportunities · Settings.
- **RTL/Arabic:** layouts must mirror cleanly (see §9.6) — critical for the GCC market; verdict headers, breakdown bars, and disclosures all need RTL-correct alignment and iconography.

---

# PART THREE — DESIGN SYSTEM

## 9. SaaS design system recommendations

Reference register: **Linear's restraint, Stripe's trust, Vercel's contrast, Notion's calm.** The system must feel like an expensive instrument, not a busy tool.

### 9.1 Color

- **Neutrals do the heavy lifting.** A near-monochrome canvas: a soft off-white/paper light theme and a true deep-charcoal dark theme (ship both; dark is the hero for the "premium tool" feel). Borders are hairline and low-contrast.
- **Semantic verdict palette — muted and sophisticated, never alarm-bell:**
  - *Go / Ready / Recommended* → deep, slightly desaturated **forest green**.
  - *Conditions / caution* → warm **ochre/amber**, not neon yellow.
  - *Avoid / Not ready* → muted **clay-red/terracotta**, not fire-engine red.
  - *Neutral / insufficient data* → slate grey.
  Verdict color appears as a small accent (badge, pill, a thin status edge), **never as a filled alarm banner**. Premium = restraint.
- **One brand accent** (a confident, slightly unexpected hue — e.g., a deep electric indigo or a refined teal) used sparingly for primary actions and the wordmark.

### 9.2 Typography

- **Large, editorial type for verdicts.** Verdict headers are display-scale (think 32–44px) — the verdict should feel *spoken by a strategist*.
- A clean **geometric/grotesk sans** for UI (Inter, or a more characterful grotesk for the wordmark and verdicts to avoid the default-SaaS look — *the design should not read as a template*).
- **Monospace** reserved exclusively for raw data inside "evidence" disclosures — it visually signals "this is the underlying data, not the decision."
- Tight, deliberate scale; long-form reasoning text gets comfortable line length (~64–72ch) and generous line height.

### 9.3 Spacing & layout

- **8pt base grid**, but generous — this product breathes. Whitespace is a feature; it signals confidence and focus.
- Content max-width on reading screens (~720–820px) so verdicts read like a memo, not a spreadsheet.
- Single-column narratives over multi-column dashboards everywhere.

### 9.4 Elevation, radius, motion

- **Flat-ish with hairline borders** over heavy shadows (Linear register). Shadows only for true overlays.
- Medium radius (~8–12px); soft but not playful.
- **Motion is fast and purposeful** (120–200ms). The one place motion gets expressive is the **analysis-running** and **verdict-reveal** moments (§12) — a brief, satisfying resolve that rewards the wait. Nowhere else should animation draw attention.

### 9.5 Voice & tone (part of the design system — non-negotiable)

The product *is* its voice. Every string is the strategist talking.

- **Decisive, plain, senior.** "Don't build links here yet — fix the content first." Not "Content score: 62/100."
- **Confident but honest about uncertainty.** "Likely," "based on the current top 3," explicit confidence levels.
- **No jargon without translation** (the in-house marketer must follow it).
- **Never alarmist, never hype.** Calm authority.
- Microcopy is a design deliverable, not an afterthought — wireframes should ship with real strings.

### 9.6 RTL / localization (first-class)

Given the GCC focus: full **RTL support** and Arabic typography from day one. Mirror layouts, breakdown bars, disclosure chevrons, and progress rails. Choose UI and display fonts with strong Arabic counterparts. Treat this as a system foundation, not a later "i18n pass."

---

## 10. Component library recommendations

Built on a headless base (e.g., Radix primitives) so behavior is solid and styling is fully custom — **do not ship a recognizable off-the-shelf component look.** Signature components carry the product's identity:

**Signature (product-defining):**
- **Verdict Header** — the large outcome + confidence + one-line rationale unit. Variants per outcome and per module.
- **Confidence Indicator** — an honest low/med/high treatment (a calm segmented pip or label, never a loud gauge).
- **Reasoning Disclosure ("Show the evidence")** — the progressive-depth control that hides raw data by default. Used everywhere a verdict appears.
- **Action Checklist** — prioritized, checkable recommended actions with P1/P2 tags.
- **Constraint Breakdown Bar** — the single segmented bar for the bottleneck gap.
- **Opportunity Verdict Card** — Recommended/Conditions/Avoid card.
- **Due-Diligence Section** — finding-style block with a green/amber/red read.
- **Risk Warning Banner** — quiet, inline, never a red modal.
- **Forecast Callout** — the business-value projection panel with confidence band.
- **Command Launcher** — the ⌘K URL-intent input.

**Standard:**
- Buttons (primary/secondary/ghost), inputs, badges/pills, priority tags, list rows (decision-row variant), sidebar nav items, breadcrumb, skeletons, toast, modal/sheet, stepper, integration card, empty-state block, avatar/role chips, plan-comparison table.

**Data-viz philosophy:** there is almost none, by design. Permitted: the constraint breakdown bar, the forecast gap-bar, and tiny inline sparklines inside evidence disclosures. Forbidden: dashboards, multi-series charts, metric-tile grids.

---

## 11. Empty states

Each empty state is an *invitation to the next decision*, never a dead end.

- **No sites:** "Add your first site and we'll find pages worth diagnosing." + Add Site CTA.
- **Site with no analyzed pages:** "Pick a page and we'll tell you what's holding it back." + page suggestions from GSC.
- **No opportunities on a page:** inline "Paste a guest-post URL to get a verdict" with the input present.
- **Opportunities library empty:** brief explanation + deep link to a page to evaluate one.
- **Campaigns (gated):** the future-teaser (§7.12).
- **Search/filter no results:** plain "Nothing matches" + clear filters.

Visual treatment: a small restrained illustration or icon, one line of value-framed copy, one CTA. No empty bar charts.

## 12. Loading states

### 12.1 Routine loads
Skeleton rows/blocks that match final layout. Instant, calm, no spinners-on-white.

### 12.2 The analysis-running experience *(signature)*
When an analysis runs (seconds to ~2 min), do **not** show a spinner. Show the **strategist thinking** — a sequence of reasoning steps revealing as they complete:

> "Reading the page…" ✓
> "Comparing against the current top 3…" ✓
> "Checking your Search Console signals…" ✓
> "Weighing content vs. authority vs. intent…" ⟳

This (a) makes the wait feel like *work being done for you*, (b) builds trust by showing the reasoning path, and (c) reinforces the strategist metaphor better than any copy could. It resolves into the verdict reveal. This is one of the product's most important screens — treat it as a feature, not a state.

### 12.3 Re-run
A subtle inline "Updating…" on the existing verdict so prior results stay readable while refreshing.

### 12.4 Insufficient data *(a real outcome, not an error)*
When a page is too new / lacks GSC history: an honest, non-failing state — "Not enough signal yet to diagnose confidently. Here's what we *can* say, and what to connect/wait for." Offers partial value + a clear path (connect GSC, return later).

## 13. Success states

- **Verdict reveal:** the rewarding resolve after running — verdict header animates in cleanly. The success *is* the decision.
- **Action completed** (e.g., fix checked off, plan exported): quiet toast + state change; never a celebratory interruption (premium tools don't throw confetti at professionals — *(assumption, override only with restraint)*).
- **Opportunity assessed / plan exported:** inline confirmation + the obvious next step surfaced.

## 14. Error states

Honest, calm, recoverable. Never a red wall.

- **Page can't be crawled / inaccessible:** explain plainly, offer retry, suggest checking the URL.
- **GSC not connected (where it matters):** framed as a quality limitation with a one-click connect, not a hard failure.
- **Analysis failed (API/timeout):** "We couldn't finish — your usage wasn't counted. Try again." Retry primary.
- **Permission denied (Viewer hitting an action):** explain the role limit gently, point to the Owner.
- **404 / broken route:** quiet, branded, link home.
- **Quota reached:** routes into the upgrade flow (§16) — framed as a value moment, not a block.

Error tone matches the voice: senior, calm, specific about the fix.

---

# PART FOUR — GROWTH & SCALE

## 15. Onboarding flow (detailed)

**Goal:** shortest path to the first non-obvious verdict (the aha, §4.4). Target: first verdict within ~3 minutes of signup.

1. **Sign up** → minimal friction (Google preferred).
2. **One-line promise** restated: "We'll tell you what's holding a page back — and whether links will fix it."
3. **Connect GSC** (step, skippable with honest trade-off copy).
4. **Add first site** → background page discovery.
5. **Suggested target pages** (3–5 from GSC) → "Let's diagnose one."
6. **Run** → the strategist-thinking experience.
7. **Aha reveal** → the Bottleneck verdict, full-bleed, ideally non-obvious.
8. **Guided next step** → "Want to see which links would actually help? Evaluate an opportunity." → seeds Module 3.
9. **Soft account nudges** (invite a teammate, add a client as Viewer) — *after* value, never before.

Onboarding is **value-first**: no tour of features, no tooltips marathon. The product proves itself by producing one good decision.

## 16. Upgrade flow

**Model *(assumption)*:** Free trial / limited Free → **Solo** → **Agency** → **Scale**, differentiated by analyses/month, sites, seats, client-Viewer reports, and (later) campaign tracking.

**Principles:**
- **Upgrade prompts attach to value moments, never to walls.** Triggers: hitting the monthly analysis cap, adding a 2nd/Nth site, inviting a teammate or client-Viewer, exporting a branded client report, opening locked Campaigns.
- **The paywall sells the next decision, not features:** "You've used your analyses this month — upgrade to keep diagnosing pages." Show the *value just experienced*, then the plan.
- **Plan comparison page:** clean three-column table, decisions-per-tier framed in user language ("Diagnose unlimited pages," "Invite clients to view forecasts," "Track outcomes"). No feature-matrix sprawl.
- **In-context upgrade sheet** (not a full redirect) when a trigger fires, so the user stays in flow.
- **Billing screen** shows usage against limits honestly so upgrades feel earned, not extracted.

## 17. Future scalability considerations

Design the system today so these slot in without re-architecture:

- **Outcome loop / Campaigns (the moat):** the Campaigns nav slot and Tracked-Link object already exist (§7.12). Future screens: tracked links, predicted-vs-actual lift, model self-calibration surfaced as rising confidence. Design the data model and nav now; build later.
- **Portfolio allocation view:** elevate the Site-detail prioritization into a workspace-wide "where should this month's budget go" planner across all clients. The decision-row component already supports it.
- **Client-facing reports & white-label:** mature the Share/export view into branded, scheduled client reports — a primary agency retention and growth lever.
- **Bulk analysis:** evaluate many pages/opportunities at once; results flow into the same prioritized lists.
- **Team collaboration:** comments/assignments on verdicts and actions (Linear-style) for agency workflows.
- **Alerts/monitoring:** "this page just became link-limited" notifications — turns a tool into a habit.
- **Arabic/GCC market depth:** RTL is foundational (§9.6); future SERP/forecast intelligence tuned for Arabic markets is a defensible wedge the design must not block.
- **API / integrations:** so agencies pipe verdicts into their own stacks.

Architectural guardrails for the designer: keep the **Page as the hero object**, keep **Decision → Reason → Action** as the invariant pattern, and keep **raw data behind disclosures** — every future feature must obey these three or it doesn't belong in this product.

---

## Appendix A — Design "definition of done" checklist

A screen is ready when:
- [ ] It leads with a **decision**, not a metric.
- [ ] Every verdict has a **confidence** treatment and a **traceable reason**.
- [ ] Every reason resolves into a **recommended action**.
- [ ] Raw data is **disclosed, not displayed** by default.
- [ ] Copy sounds like a **senior strategist**, plain enough for an in-house marketer.
- [ ] It works in **dark mode and RTL**.
- [ ] Its **empty, loading, success, and error** states are designed.
- [ ] Nothing on it resembles a **traditional SEO dashboard**.

## Appendix B — Stated assumptions (override with reason)
- Seat-based pricing + analysis-volume metering; clients invited as free Viewers.
- Dark theme is the hero; light theme shipped alongside.
- No celebratory/confetti success moments — restrained confirmations for a professional audience.
- Plan tiers Solo / Agency / Scale.
- GSC is the primary first-party integration at launch.
