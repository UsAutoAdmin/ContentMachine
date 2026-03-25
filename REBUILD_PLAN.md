# ContentMachine Rebuild Plan

## Working product definition

ContentMachine is evolving from a reel transcription utility into an internal operations console that supports Part Scout across:

1. Content intelligence
2. Content production
3. Inbox / communication monitoring
4. Customer success workflows

The current repository already contains the seed of module 1 and part of module 2.

## Current reality

The codebase is functional but structurally immature:

- `app.py` combines routes, HTML, CSS, JavaScript, and product logic
- UI is server-rendered via large inline strings
- the only durable core entity is `videos`
- transcription and performance tracking are the strongest implemented features
- broader ops concepts are implied but not yet modeled in code

## Rebuild goals

### Product goals
- turn ContentMachine into a coherent ops console, not a pile of pages
- preserve and improve the strongest existing workflows
- create space for future Part Scout support modules without turning the app into spaghetti
- make daily usage fast, obvious, and low-friction

### Engineering goals
- separate backend routes, services, templates, and static assets
- create clear domain boundaries
- keep local-first workflows for transcription where needed
- keep deployability simple
- make iterative additions safer and faster

## Target information architecture

### Core navigation
- Dashboard
- Content Lab
- Performance
- Inbox
- Customer Success
- Tools

### Proposed module intent

#### Dashboard
A high-level operating view:
- today’s priorities
- content pipeline status
- inbox/customer alerts
- quick stats

#### Content Lab
- reel/research transcription
- idea extraction
- script drafting support
- teleprompter
- bulk analysis workflows

#### Performance
- performance database
- transcript search
- pattern analysis
- top-performing content characteristics
- import/export and data hygiene

#### Inbox
- email monitoring queue
- classification and follow-up states
- important conversations and action items

#### Customer Success
- customer issues
- recurring friction themes
- response workflows
- escalation notes

#### Tools
- utilities that do not deserve top-level product status but are still useful

## Target engineering architecture

A likely structure:

```text
ContentMachine/
  app/
    main.py
    config.py
    routes/
      pages.py
      api_videos.py
      api_transcribe.py
      api_bulk.py
    services/
      transcription.py
      transcript_similarity.py
      analytics.py
    repositories/
      videos.py
    templates/
      base.html
      dashboard.html
      content_lab.html
      performance.html
      inbox.html
      customer_success.html
      partials/
    static/
      css/
      js/
      img/
  data/
  tests/
  scripts/
  README.md
```

This structure may change during implementation, but the principles should remain:
- thin routes
- reusable services
- separated presentation
- explicit data/repository layer

## Migration strategy

### Phase 1 — Structural rebuild without product expansion
Goal: preserve existing behavior while making the codebase sane.

- move inline HTML into templates
- move inline JS/CSS into static assets
- split route handlers out of `app.py`
- isolate database access
- isolate transcription logic cleanly
- keep existing features working end-to-end

### Phase 2 — Product shell and dashboard unification
Goal: replace the disconnected pages with a coherent app shell.

- create shared layout/navigation
- build a proper dashboard landing page
- reposition current features into clearer modules
- improve visual consistency and workflow handoff between pages

### Phase 3 — Content intelligence upgrades
Goal: strengthen the best existing module.

- richer performance analytics
- tagging / categorization
- better duplicate detection
- transcript extraction insights
- better bulk workflow visibility and history

### Phase 4 — Inbox and customer success foundations
Goal: start modeling the broader Part Scout support workflows.

- define entities and workflow states
- add inbox queues and CS records
- connect alerts/tasks into the dashboard

## Guardrails for rebuild work

- do not preserve weak structure just because it already exists
- preserve useful workflows unless replacement is clearly better
- favor clarity over cleverness
- avoid introducing unnecessary framework complexity
- keep the product usable during transition when possible
- prefer incremental commits with working checkpoints

## Immediate next actions

1. inventory current UI/page responsibilities
2. create new app structure scaffold
3. migrate one vertical slice first (likely Performance or Transcribe)
4. verify routes still run
5. continue page-by-page migration

## Decision authority

Chase explicitly authorized full control over ContentMachine, including complete rebuilds where they materially improve the system.
