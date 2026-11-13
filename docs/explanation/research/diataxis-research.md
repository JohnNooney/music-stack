# Diátaxis documentation framework — research

Research date: 2026-11-13. Sources: the official Diátaxis site <https://diataxis.fr>
(all pages in its two nav sections — "Applying Diátaxis" and "Understanding
Diátaxis" — fetched in full), the site's own precursor at
<https://documentation.divio.com> (the author's earlier presentation, linked
from the site's colophon), and the git history of the site's official source
repo <https://github.com/evildmp/diataxis-documentation-framework>, which
contains two pages removed from the live site in its Aug-2026 restructure:
`complex-hierarchies.rst` (the "Diátaxis in complex hierarchies" page the
site's navigation used to carry) and `adoption.rst`. No third-party summaries
were used; every claim below carries its URL.

> **TL;DR — Documentation should be organised around four distinct user
> needs, kept strictly separate:** *tutorials* (learning-oriented: a
> lesson, serves study), *how-to guides* (goal-oriented: directions for a
> real-world task, serves work), *reference* (information-oriented: austere
> technical description, serves work) and *explanation* (understanding-oriented:
> discursive context, serves study) — §1. They sit on a 2×2 map whose axes are
> action/cognition × acquisition/application; blurring the boundaries is "at
> the heart of a vast number of problems in documentation" — §2. Structure
> means a Home landing page over four top-level sections, each with a landing
> page that *introduces* rather than lists; keep lists ≤ ~7 items and add
> hierarchy layers inside sections when needed — §3. Adoption is deliberately
> iterative: do **not** create four empty folders; pick one page, apply the
> compass, fix one thing, publish, repeat — the four-fold top-level structure
> should *emerge* — §4. Each type has prescribed language ("we will…",
> conditional imperatives, neutral statements of fact, "the reason for x is…")
> — §5.

---

## 1. The four documentation types

The homepage: "Diátaxis identifies four distinct needs, and four corresponding
forms of documentation - *tutorials*, *how-to guides*, *technical reference*
and *explanation*. It places them in a systematic relationship, and proposes
that documentation should itself be organised around the structures of those
needs." — https://diataxis.fr/

The map page gives the canonical comparison table
(https://diataxis.fr/map/):

| | Tutorials | How-to guides | Reference | Explanation |
|---|---|---|---|---|
| what they do | introduce, educate, lead | guide | state, describe, inform | explain, clarify, discuss |
| answers the question | "Can you teach me to…?" | "How do I…?" | "What is…?" | "Why…?" |
| oriented to | learning | goals | information | understanding |
| purpose | provide a learning experience | help achieve a particular goal | describe the machinery | illuminate a topic |
| form | a lesson | a series of steps | dry description | discursive explanation |
| analogy | teaching a child how to cook | a recipe in a cookery book | information on a food packet | an article on culinary social history |

### 1.1 Tutorials — learning-oriented, serves *acquisition* of skill

Source: https://diataxis.fr/tutorials/ (supplemented by
https://diataxis.fr/start-here/ and https://diataxis.fr/tutorials-how-to/).

- **Definition.** "A tutorial is an *experience* that takes place under the
  guidance of a tutor. A tutorial is always *learning-oriented*." It is "a
  lesson", a *practical activity* in which the learner learns **by doing**;
  it serves the user's study, not their work. The user's need is skill
  acquisition; what the user *does* is not necessarily what they *learn*
  (through doing they acquire facts, understanding, familiarity, names of
  things, workflows).
- **The teacher's contract.** Nearly all responsibility sits with the
  teacher; the pupil's only duty is to be attentive and follow directions.
  The exercise must be *meaningful*, *successful* (completable), *logical*
  and *usefully complete* (encountering all needed actions/concepts/tools).
- **Rules/key principles the site lists:**
  - *Don't try to teach* — "the first rule of teaching is simply: don't try
    to teach." Give the learner things to *do*; "allow learning to take
    place". The site lists the "anti-pedagogical temptations": **abstraction,
    generalisation, explanation, choices, information**.
  - *Show the learner where they'll be going* — state the goal up front ("In
    this tutorial we will create and deploy…"), but never "In this tutorial
    you will learn…" — called "presumptuous and a very poor pattern".
  - *Deliver visible results early and often* — every step should produce a
    comprehensible result.
  - *Maintain a narrative of the expected* — keep confirming the learner is
    on track ("You will notice that…", show expected output, flag likely
    failure signs).
  - *Point out what the learner should notice* — close the loop on details
    the learner is too focused to see.
  - *Target the feeling of doing* — tie purpose and action together.
  - *Encourage and permit repetition* — repeatable steps reaffirm success;
    "repetition is not the best teacher - sometimes it's the *only* teacher".
  - *Ruthlessly minimise explanation* — "A tutorial is not the place for
    explanation." Give the minimal line ("We're using HTTPS because it's
    more secure") and *link* to the long explanation.
  - *Focus on the concrete* — this problem, this action, this result;
    general patterns emerge from concrete steps, not vice versa.
  - *Ignore options and alternatives* — one managed path to a successful
    conclusion; diversions cost learner and writer cognitive work.
  - *Aspire to perfect reliability* — the tutorial must work "for every
    user, every time"; you are "required to be present, but condemned to be
    absent", so the tutorial must be constructed so things *can't* go wrong.
    Flaws are found only by watching real users run it.
- **Failure modes warned against:** conflating tutorials with how-to guides
  ("the single most common conflation made in software product
  documentation" — https://diataxis.fr/tutorials-how-to/); overloading
  tutorials with explanation (start-here calls this out explicitly);
  offering choices/alternatives; "teaching by telling". Tutorials are also
  the hardest type to maintain — changes "cascade through the entire story"
  of an end-to-end journey.

### 1.2 How-to guides — goal-oriented, serves *application* of skill

Source: https://diataxis.fr/how-to-guides/ (supplemented by
https://diataxis.fr/tutorials-how-to/).

- **Definition.** "How-to guides are *directions* that guide the reader
  through a problem or towards a result. How-to guides are *goal-oriented*."
  They help the user "get something done, correctly and safely" — they
  concern *work*, "navigating from one side to the other of a real-world
  problem-field". They serve the application of skill for an
  **already-competent user** who knows what they want to achieve.
- **Must be addressed to a human goal, not the machinery.** "How-to guides
  must be written from the perspective of the user, not of the machinery."
  Each guide answers a human project; a guide defined by "operations the
  tool can perform" is "mostly useless information" — the site contrasts the
  useless "select options and press *Deploy*" pattern with addressing what
  the user actually needs to decide.
- **Not merely procedures.** Real problems don't always reduce to a linear
  procedure; sequences "sometimes need to fork and overlap, and they have
  multiple entry and exit-points", and the guide may rely on the user's
  judgement.
- **Rules/key principles the site lists** ("focused on tasks or problems;
  assume the user knows what they want to achieve; action and only action;
  no digression, explanation, teaching"):
  - *Address real-world complexity* — stay adaptable to a range of cases,
    not just the one narrow one written down.
  - *Omit the unnecessary* — "practical usability is more helpful than
    completeness"; unlike a tutorial a how-to needn't be end-to-end, and can
    start/end "in some reasonable, meaningful place".
  - *Provide a set of instructions* — an *executable solution* expressed as
    actions (including thinking/judgement steps).
  - *Describe a logical sequence* — order imposed by dependency, or by what
    best sets up the user's environment/thinking.
  - *Seek flow* — ground sequences in the user's activity patterns; good
    how-to docs "anticipate" the user.
  - *Pay attention to naming* — titles must say exactly what the guide
    shows. Good: *How to integrate application performance monitoring*;
    bad: *Integrating application performance monitoring*; very bad:
    *Application performance monitoring*. "Search engines appreciate good
    titles just as much as humans do."
- **Failure modes warned against:** conflating with tutorials; padding with
  explanation or reference "for completeness" ("if they're important, link
  to them"); writing at the "turn the tap clockwise" level; treating the
  guide as a feature tour of the tool. Tutorials-how-to adds the contrast:
  the how-to path *can't* be managed (real world), must prepare for the
  unexpected, may fork/branch, takes a *general* approach and *assumes
  familiarity* — where a tutorial manages the path, eliminates the
  unexpected, is concrete/particular and familiarises
  (https://diataxis.fr/tutorials-how-to/). Also worth noting: how-to vs
  tutorial is **not** basic vs advanced — a how-to can cover a basic
  procedure and a tutorial can be advanced; the difference is study vs work.

### 1.3 Reference — information-oriented, serves *application* of skill

Source: https://diataxis.fr/reference/ (supplemented by
https://diataxis.fr/reference-explanation/).

- **Definition.** "Reference guides are *technical descriptions* of the
  machinery and how to operate it. Reference material is
  *information-oriented*." It contains *propositional/theoretical
  knowledge* consulted in *work* — "facts" that are "accurate, complete,
  reliable … free of distraction and interpretation" (start-here). "The only
  purpose of a reference guide is to describe, as succinctly as possible,
  and in an orderly way"; it is led by the product, not the user.
- **Rules/key principles the site lists:**
  - *Describe and only describe* — "neutral description is the key
    imperative". Style: **austere and uncompromising; neutrality,
    objectivity, factuality**. "One hardly *reads* reference material; one
    *consults* it." It must be authoritative, no doubt or ambiguity.
  - *Adopt standard patterns* — consistency is what makes reference usable;
    put material "where they expect to find it, in a format that they are
    familiar with". Not the place for stylistic flourish.
  - *Respect the structure of the machinery* — "the structure of the
    documentation should mirror the structure of the product", like a map
    mirrors territory; the logical/conceptual arrangement of the code should
    show through in the docs (start-here: if a method is part of a class in
    a module, the docs should show that relationship).
  - *Provide examples* — examples illustrate without sliding into
    instruction or explanation.
- **Failure modes warned against:** instruction/explanation/opinion
  creeping in ("describe and only describe… instead, link to how-to guides,
  explanation and introductory tutorials"); believing auto-generated
  reference "is all the documentation required"; explanation sprinkled into
  reference — "bad for the reference, interrupted and obscured by
  digressions … bad for the explanation too"
  (https://diataxis.fr/reference-explanation/).

### 1.4 Explanation — understanding-oriented, serves *acquisition* of skill

Source: https://diataxis.fr/explanation/ (supplemented by
https://diataxis.fr/reference-explanation/).

- **Definition.** "Explanation is a discursive treatment of a subject, that
  permits *reflection*. Explanation is *understanding-oriented*." It
  "deepens and broadens the reader's understanding… brings clarity, light
  and context", provides *background and context*, "joins things together",
  answers *why?* and *Can you tell me about…?* Like reference it is
  propositional knowledge, but it serves *study* (acquisition), not work —
  "the only kind of documentation that it might make sense to read in the
  bath".
- **Rules/key principles the site lists** ("things to discuss": the bigger
  picture; history; choices, alternatives, possibilities; reasons and
  justifications):
  - *Make connections* — weave a web of understanding, even to things
    outside the immediate topic.
  - *Provide context* — design decisions, historical reasons, technical
    constraints, implications, examples.
  - *Talk about the subject* — explanation is *around* its topic; titles
    should accept an implicit "**About**" (*About user authentication*).
  - *Admit opinion and perspective* — explanation "can and must consider
    alternatives", counter-examples, even weigh contrary opinions; treat it
    as *discussion*.
  - *Keep explanation closely bounded* — bound the scope with a real or
    imagined *why* question.
- **Naming flexibility.** "Your explanation documentation doesn't need to be
  called *Explanation*." The site's own alternatives: *Discussion*,
  *Background*, *Conceptual guides*, *Topics*.
- **Failure modes warned against:** explanation "tends to absorb other
  things" — instruction or technical description creeping in "interferes
  with the explanation itself, and removes them from view in the correct
  place"; and the opposite failure — explanation never written, "scattered
  in small parcels in other sections" because it isn't explicitly recognised.
  Not being urgent ≠ not important: "it's not a luxury".

## 2. The underlying model — two axes, strict separation

### The two axes (foundations)

Source: https://diataxis.fr/foundations/ and https://diataxis.fr/map/.

- A skill/craft has two dimensions: **action** (practical knowledge, knowing
  *how* — what we do) vs **cognition** (theoretical knowledge, knowing
  *that* — what we think); and the practitioner's relationship to their
  craft splits into **acquisition** (being *at study*) vs **application**
  (being *at work*).
- Crossing the two dimensions gives a *complete* 2×2 "map of the territory
  of craft" — "this is why there are necessarily four quarters… not three,
  or five. It is not an arbitrary number."
- The map of user needs (foundations table): tutorials serve *learning* —
  user acquires craft, docs inform action; how-to guides serve *goals* —
  user applies craft, docs inform action; reference serves *information* —
  user applies craft, docs inform cognition; explanation serves
  *understanding* — user acquires craft, docs inform cognition.
- Orientation shorthand (start-here/map): tutorials & how-to guides =
  action; reference & explanation = cognition; tutorials & explanation =
  acquisition (study); how-to guides & reference = application (work).

### The compass — the decision tool

Source: https://diataxis.fr/compass/.

| If the content… | …and serves the user's… | …then it belongs to… |
|---|---|---|
| informs action | acquisition of skill | a tutorial |
| informs action | application of skill | a how-to guide |
| informs cognition | application of skill | reference |
| informs cognition | acquisition of skill | explanation |

- Ask two questions — *action or cognition?* *acquisition or application?* —
  and the table yields the home for any content. Apply it both to unwritten
  needs and to existing docs "that perhaps need to be moved or improved",
  at sentence level or whole-document level. Useful synonyms the site gives:
  action = practical steps/doing; cognition = theoretical/propositional
  knowledge/thinking; acquisition = study; application = work.

### Why keep the four separate — and what happens when you don't

Source: https://diataxis.fr/map/ (the "Blur" section), plus
https://diataxis.fr/tutorials-how-to/ and https://diataxis.fr/.

- Each quadrant has an affinity with its neighbours (both action, both work,
  both propositional, both study), producing "a natural tendency to blur the
  distinctions". When they blur, "the different kinds of documentation bleed
  into each other. Writing style and content make their way into
  inappropriate places," and structural problems follow that make the
  discipline harder to keep.
- Worst case: "a complete or partial collapse of tutorials and how-to guides
  into each other, making it impossible to meet the needs served by either."
- Start-here: "Crossing or blurring the boundaries described in the map is
  at the heart of a vast number of problems in documentation."
- The map also frames a *cycle of interaction*: learn (tutorial) → put the
  skill to work (how-to) → consult facts while working (reference) → reflect
  away from work (explanation) → repeat. Users may enter the docs anywhere,
  but the ordering "corresponds to the way that people actually do become
  expert in a craft."
- The divio precursor puts the motivation bluntly: "if its documentation is
  not good enough, people will not use it", and "any attempt at
  documentation that fails to maintain this structure suffers, as it's
  pulled in different directions at once" —
  https://documentation.divio.com/introduction/.
- Quality framing (https://diataxis.fr/quality/): the site distinguishes
  *functional quality* (accuracy, completeness, consistency, usefulness,
  precision — objective, measurable, independent) from *deep quality* (feels
  good to use, flow, fits human needs, anticipates the user — subjective,
  interdependent, conditional on functional quality). Diátaxis "cannot
  address functional quality" but "lays down conditions for the possibility
  of deep quality", and applying it *exposes* lapses in functional quality
  (e.g. mirroring code structure in reference makes gaps visible).

## 3. Practical structure guidance — directories, landing pages, hierarchy

Sources: the live pages cited below plus the **removed** page *Diátaxis in
complex hierarchies*, last published at https://diataxis.fr/complex-hierarchies/
and still in the official repo's git history (`complex-hierarchies.rst`,
removed in commit `c953482`, Aug 2026 restructure — the current site has no
equivalent page, so treat this as authoritative-but-archived first-party
guidance).

### Top-level grouping and naming

- The site's canonical arrangement (complex-hierarchies): a **Home landing
  page** over four top-level sections named **Tutorial**, **How-to guides**,
  **Reference** and **Explanation**, each with its own **landing page**,
  under which the individual documents sit:
  `Home → Tutorial {Part 1,2,3} / How-to guides {Install, Deploy, Scale} /
  Reference {CLI, endpoints, API} / Explanation {best practice, security,
  performance}`.
- But four top-level folders are the *typical outcome*, not the law. The
  workflow page is explicit: "Getting started with Diátaxis does not require
  you to think about dividing up your documentation into four sections. **It
  certainly does not mean that you should create empty structures for
  tutorials/howto guides/reference/explanation with nothing in them. Don't
  do that.**" — https://diataxis.fr/how-to-use-diataxis/. Complex-hierarchies
  agrees: "Diátaxis is not a scheme into which documentation must be placed
  - four boxes… this does not mean that there must be simply four divisions
  of documentation in the hierarchy."
- Section names are flexible: explanation may be called *Discussion*,
  *Background*, *Conceptual guides* or *Topics*
  (https://diataxis.fr/explanation/).
- Within how-to sections, individual page titles should be "How to X" forms
  (§1.2, https://diataxis.fr/how-to-guides/); explanation page titles should
  read as "About X" (https://diataxis.fr/explanation/).

### Landing pages and contents pages (complex-hierarchies)

- **Landing/contents pages give an overview, not a bare list.** "The content
  of a landing page itself should read like an overview… it should not
  simply present lists of other content, it should introduce them." Use
  headings plus short introductory text per group, with the links nested
  beneath — "you are always authoring for a human user, not fulfilling the
  demands of a scheme."
- **Lists:** "lists longer than a few items are very hard for humans to
  read, unless they have an inherent mechanical order… *seven items seems to
  be a comfortable general limit*" — break longer tables of contents into
  smaller ones.
- **Add hierarchy layers inside sections when large:** e.g. make *Install* a
  sub-landing-page under *How-to guides* with *Local installation / Docker /
  Virtual machine / Linux container* beneath it.
- **When a second dimension collides with the four types** (per-audience:
  users vs developers vs contributors; per-platform: land/sea/air;
  per-cloud), either structure is legitimate — quadrant-first
  (`tutorial → per-audience`) or audience-first (`per-audience → four
  quadrants`). Decide by **user-first thinking**: "What we must document is
  the product *as it is for the user*." It's fine to mix — e.g. let
  developer tutorial content follow on from user-facing material while
  separating contributors' how-to guides entirely — "as long as there *is*
  arrangement according to Diátaxis principles, that documentation does not
  muddle up its different forms and purposes." And: "documentation should be
  as complex as it needs to be", provided complex structures remain "logical
  and incorporate patterns that fit the needs of users".

### README files, tables, diagrams, indexes

- **READMEs: no dedicated guidance exists on the current site** (checked all
  live pages and the repo's RST sources — no README section). The honest
  reading from first-party material: the *Home landing page* in the
  complex-hierarchies model plays the README role (an overview that
  introduces the four sections), and the removed `structure.rst` explicitly
  noted the system "is respected" even in very minimal documentation — it
  cites a single-README project ("Getting started with Java and
  Spring-boot") containing only tutorial, how-to and reference material as a
  valid partial application. So: a repo README ≈ a landing page +
  whatever subset of the four types fits; quadrants needn't all be present.
- **Tables:** treated as signature *reference* form — "lists of things… and
  tables of information, will generally turn out to belong in *reference*"
  (https://diataxis.fr/reference-explanation/). Rule of thumb from the same
  page: if it's boring and unmemorable → reference; if you could read it in
  the bath → explanation.
- **Diagrams:** the site uses the 2×2 map itself as the organising diagram;
  beyond that it says only that examples/illustrations are legitimate in
  reference ("just as an encyclopaedia might contain illustrations") —
  https://diataxis.fr/reference/ and /reference-explanation/.
- **Indexes:** no index-specific guidance found in any first-party page;
  the closest is the landing-page/overview guidance above.

## 4. Adoption and migration into an existing project

Sources: https://diataxis.fr/how-to-use-diataxis/ (the workflow page — this
*is* the adoption guidance), https://diataxis.fr/application/,
https://diataxis.fr/start-here/, https://diataxis.fr/compass/,
https://diataxis.fr/quality/, and the removed `structure.rst`/`adoption.rst`
in the site repo history.

- **Guide, not plan.** "The structure it proposes is not intended to be a
  *plan*… It's a *guide*, a map to help you check that you're in the right
  place." Don't restructure top-down; "Diátaxis changes the structure of
  your documentation **from the inside**" — keep making principled small
  improvements until "the changes you have made will appear to demand that
  you move material under a certain Diátaxis heading".
- **The workflow loop** (verbatim from the site):
  1. Look at what's in front of you right now (any page, paragraph,
     sentence — pick at random if needed; don't go hunting for the worst
     problems).
  2. Assess it against Diátaxis standards: *what user need does this serve?
     how well? what can be added/moved/removed/changed? does its language
     and logic match this mode of documentation?*
  3. Decide on *one* next action that produces an immediate improvement.
  4. Do it and *consider it completed* — publish/commit it. Then loop.
- **Iterate, publish small.** "Every step in the right direction is worth
  publishing immediately"; resist both the big-bang rewrite ("tear it all
  down") and hoarding a large batch of fixes. Model: **well-formed organic
  growth** — structure emerges from healthy cells; docs are "never finished"
  but should be "always complete" at every stage.
- **Don't wait to understand it.** "You will not understand it until you
  have started using it"; apply one idea to something however small, then
  iterate between work and reflection (application page). Start-here: "The
  best way to get started with Diátaxis is by applying it."
- **Partial adoption is valid.** The removed structure page stressed the
  system is respected "however minimal or even incomplete" the docs — a
  project legitimately fielding only some quadrants still benefits, and the
  skeleton "helps guide the expansion of the material as it develops".
  (Contrast with the workflow page's warning against *empty scaffolding*:
  partial types are fine, empty headings are not.)
- **Auditing existing docs:** run the compass over existing pages — does the
  content inform action or cognition, and does the user need acquisition or
  application? Apply it "at the level of sentences and words, or… an entire
  document" (https://diataxis.fr/compass/). Expect misplaced material:
  explanation scattered inside other sections, tutorials/how-to conflated,
  explanation sprinkles inside reference — the named conflation patterns are
  in §1's failure modes. The quality page notes that simply applying the
  framework "exposes" problems that were previously obscured.
- **Splitting a doc that mixes types:** the site's prescription is
  separation + linking, not blending — e.g. in a tutorial keep one minimal
  explanatory line and "provide a link or reference to that explanation, so
  that it's available, but doesn't get in the way"
  (https://diataxis.fr/tutorials/); in how-to guides "Refer to the x
  reference guide for a full list of options" rather than polluting the
  guide (https://diataxis.fr/how-to-guides/); in reference "link to how-to
  guides, explanation and introductory tutorials" instead of describing
  tasks (https://diataxis.fr/reference/).
- **Adoption evidence:** the live homepage carries testimonials (Vonage,
  Gatsby, Cloudflare); the removed `adoption.rst` listed ~50 adopters
  (Django, NumPy, Cloudflare Workers, Canonical "all of Canonical's product
  documentation", Gatsby, Gensim, BBC News Labs, Sourcegraph…).
- **The author's own caveat:** the colophon (https://diataxis.fr/colophon/)
  says of the earlier divio presentation "I still agree with most of it,
  though there are several aspects that I now think I got wrong" — the
  diataxis.fr pages are the current canonical statement.

## 5. Language and style rules per doc type

Each type page carries an explicit "language of" section — quoted
prescriptions below.

- **Tutorials** (https://diataxis.fr/tutorials/): first-person plural —
  "**We**…" (affirms tutor/learner relationship); "In this tutorial, we
  will…"; imperative steps with no ambiguity: "First, do x. Now, do y. Now
  that you have done y, do z."; minimal inline explanation — "We must always
  do x before we do y because… *(see Explanation for more details)*";
  expectation-setting — "The output should look something like…",
  "Notice that… Remember that… Let's check…"; close by describing (mildly
  admiring) what the learner accomplished.
- **How-to guides** (https://diataxis.fr/how-to-guides/): "This guide shows
  you how to…" up front; **conditional imperatives** — "If you want x, do y.
  To achieve w, do z."; defer to reference for completeness — "Refer to the
  x reference guide for a full list of options."
- **Reference** (https://diataxis.fr/reference/): neutral factual statements
  — "Django's default logging configuration inherits Python's defaults…";
  dry enumerations — "Sub-commands are: a, b, c, d, e, f."; warnings as
  flat imperatives — "You must use a. You must not apply b unless c. Never
  d." Language should be austere, objective, standard-patterned; no opinion
  or instruction beyond warnings.
- **Explanation** (https://diataxis.fr/explanation/): discursive and
  perspectival — "The reason for x is because historically, y…"; judgements
  and opinions — "W is better than z, because…"; analogy/context — "An x in
  system y is analogous to a w in system z. However…"; weighed alternatives —
  "Some users prefer w (because z). This can be a good approach, but…";
  unfolding internals — "An x interacts with a y as follows:…".
- **Voice/optionality summary:** tutorials take a managed single path with
  *no* options; how-to guides may fork and offer alternatives ("If this,
  then that") and assume competence — optionality lives in how-tos and
  explanation, completeness lives in tutorials (end-to-end encounter) and
  reference (exhaustive description), never in how-tos (where "practical
  usability is more helpful than completeness").

## How this repo ended up mapping to it (repo observation, not site content)

The repo's docs were reorganised during this session along the quadrant
model; the layout adopted matches the conventions above:

- `docs/how-to/` — task guides (`setup.md`, `wire-lidarr-stack.md`,
  `add-music.md`, `cut-over-union-root.md`, `migrate-library.md`,
  `upgrade-images.md`); `docs/reference/` — `library-layout.md`,
  `settings.md`, the two tool docs and `lidarr-stack.md`, with root
  `CONTEXT.md` treated as reference vocabulary; `docs/explanation/` —
  `architecture.md`, `dedup_music.md`, and `adr/`, `specs/`, `research/`
  subfolders (ADR/spec/research material nests inside the quadrant, which
  the complex-hierarchies page sanctions as added hierarchy).
- No `tutorials/` directory was created — consistent with the workflow
  page's rule against empty quadrant scaffolding; `docs/README.md` notes
  `setup.md` is the closest thing to a first-run walkthrough.
- `docs/README.md` plays the Home landing-page role: it introduces each
  section in a sentence rather than only listing links — the
  complex-hierarchies "overview, not a bare list" pattern.

## Sources

- Diátaxis homepage: https://diataxis.fr/
- Start here (five-minute primer): https://diataxis.fr/start-here/
- Applying Diátaxis (section index): https://diataxis.fr/application/
- Tutorials: https://diataxis.fr/tutorials/
- How-to guides: https://diataxis.fr/how-to-guides/
- Reference: https://diataxis.fr/reference/
- Explanation: https://diataxis.fr/explanation/
- The compass: https://diataxis.fr/compass/
- Workflow ("Diátaxis as a guide to work"): https://diataxis.fr/how-to-use-diataxis/
- Understanding Diátaxis (theory index): https://diataxis.fr/theory/
- Foundations (the two axes): https://diataxis.fr/foundations/
- The map (axes table, blur, collapse, cycle): https://diataxis.fr/map/
- Quality (functional vs deep quality): https://diataxis.fr/quality/
- Tutorials vs how-to guides: https://diataxis.fr/tutorials-how-to/
- Reference vs explanation: https://diataxis.fr/reference-explanation/
- Colophon (authorship, precursor link): https://diataxis.fr/colophon/
- Removed page — *Diátaxis in complex hierarchies* (last live at
  https://diataxis.fr/complex-hierarchies/; source at
  https://github.com/evildmp/diataxis-documentation-framework blob
  `complex-hierarchies.rst`, removed in commit `c953482`, Aug 2026; readable
  via `git show c953482^:complex-hierarchies.rst`)
- Removed page — *Who's using Diátaxis?* (`adoption.rst`, removed in commits
  `06039c6`/`0d13678`; last live version cited in §4)
- Removed page — *The structure* (`structure.rst`, removed in `2d553c8`;
  minimal-documentation/partial-quadrant examples cited in §4)
- First-party precursor site: https://documentation.divio.com/ (esp.
  https://documentation.divio.com/introduction/), incl. the author's PyCon
  Australia 2017 video presentation linked from its index
- Site source repo: https://github.com/evildmp/diataxis-documentation-framework
