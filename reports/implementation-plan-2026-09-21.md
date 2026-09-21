# MKC implementation-plan report

- generated_at: 2026-09-21T02:10:45.502984+00:00
- generated_by: mkc-reports-v1
- source DB counts — contradictions: 0, decisions: 0, documents: 2159, entities: 157, entity_relations: 0, experiments: 0, knowledge_objects: 198, reports: 2, research_items: 0, sources: 144

## 1. Current state per source repo

### InvestigationSuite
- commits: 4 (branch `main`)
- documents: 28 — code: 13, data: 1, markdown: 5, other: 5, test: 1, text: 1, yaml: 2
- knowledge objects: 0 — none
- state distribution: n/a

### MomentoFX
- commits: 14 (branch `main`)
- documents: 706 — code: 409, config: 3, data: 2, html: 6, json: 89, markdown: 103, other: 23, test: 20, text: 4, yaml: 47
- knowledge objects: 0 — none
- state distribution: n/a

### MomentoFresh
- commits: 74 (branch `main`)
- documents: 96 — code: 78, config: 2, html: 1, json: 1, markdown: 9, other: 1, text: 2, yaml: 2
- knowledge objects: 0 — none
- state distribution: n/a

### MomentoRabbit
- commits: 2 (branch `main`)
- documents: 1 — markdown: 1
- knowledge objects: 0 — none
- state distribution: n/a

### MomentoV5
- commits: 2 (branch `main`)
- documents: 497 — code: 390, config: 2, data: 7, html: 9, json: 26, markdown: 40, other: 11, test: 10, text: 2
- knowledge objects: 0 — none
- state distribution: n/a

### avfs-backend
- commits: 3 (branch `main`)
- documents: 3 — markdown: 2, other: 1
- knowledge objects: 49 — experiment: 1, fact: 48
- state distribution: experiment: 1, idea: 48

### azuredev-3867
- commits: 0 (branch `main`)
- documents: 0 — none
- knowledge objects: 0 — none
- state distribution: n/a

### momento-core
- commits: 25 (branch `main`)
- documents: 750 — code: 401, config: 3, data: 2, html: 6, json: 89, markdown: 159, other: 23, test: 17, text: 3, yaml: 47
- knowledge objects: 0 — none
- state distribution: n/a

### momento-core3
- commits: 3 (branch `main`)
- documents: 12 — code: 5, config: 1, data: 1, json: 1, markdown: 2, test: 2
- knowledge objects: 0 — none
- state distribution: n/a

### momentocore2
- commits: 7 (branch `main`)
- documents: 66 — code: 39, config: 2, html: 1, json: 8, markdown: 3, other: 1, text: 1, yaml: 11
- knowledge objects: 149 — experiment: 3, fact: 48, hypothesis: 1, module: 96, observation: 1
- state distribution: experiment: 3, hypothesis: 1, idea: 48, implemented: 96, observed: 1

## 2. Blockers

### High-mention entities with no research or validation (269)
- Dict — mentioned in 68 objects, not researched or validated
- List — mentioned in 45 objects, not researched or validated
- Any — mentioned in 35 objects, not researched or validated
- Optional — mentioned in 31 objects, not researched or validated
- Returns — mentioned in 31 objects, not researched or validated
- MomentoCore — mentioned in 27 objects, not researched or validated
- Args — mentioned in 23 objects, not researched or validated
- Check — mentioned in 17 objects, not researched or validated
- Round — mentioned in 17 objects, not researched or validated
- Signal — mentioned in 17 objects, not researched or validated
- Kafka — mentioned in 16 objects, not researched or validated
- WAIT — mentioned in 15 objects, not researched or validated
- WebSocket — mentioned in 15 objects, not researched or validated
- BaseAgent — mentioned in 14 objects, not researched or validated
- Calculate — mentioned in 14 objects, not researched or validated
- DataFrame — mentioned in 13 objects, not researched or validated
- Detect — mentioned in 13 objects, not researched or validated
- Initialize — mentioned in 13 objects, not researched or validated
- MarketDetector — mentioned in 13 objects, not researched or validated
- Add — mentioned in 12 objects, not researched or validated
- Execute — mentioned in 12 objects, not researched or validated
- Purple — mentioned in 12 objects, not researched or validated
- MODERATE — mentioned in 11 objects, not researched or validated
- Moonshot — mentioned in 11 objects, not researched or validated
- Pink — mentioned in 11 objects, not researched or validated

## 3. Prioritized next steps

1. Open research threads for the most-mentioned unvalidated entities.
   - reason: 'Dict' appears in 68 objects with no research item or validation.
2. Write markdown documentation for the most-depended code modules.
   - reason: 1385 code/test document(s) have no linked markdown document.

---

Auto-generated from MKC registry; verify before acting.
