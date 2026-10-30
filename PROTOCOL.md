# Study 15: recorded coverage before an inspection risk queue

## Decision and acceptance criteria

Can a team safely interpret the absence of a national evaluation or stack-test record as a negative training label? Measure where recorded observations exist, separate actual on-site evaluations from off-site reviews, and preserve unresolved or absent test outcomes. Deliver an inspectable current-snapshot coverage audit, group summaries, a practical data-review recommendation and reproducible evidence. No facility-level compliance accusation or enforcement queue.

Success requires exact source receipts and rights, reconciled minimal projections, retained exclusions, independent SQL/arithmetic checks, all planned windows/groups, readable figures and manuscript, finite edge-case fixtures, offline replay, bounded privacy/canonical checks and exact-head Linux/merge/tag evidence. A count audit has no learned model or tuning; do not claim ML optimization, calibration, propensity correction or a protected forecast test.

## Source and pre-retrieval boundary

EPA ECHO official downloads list ICIS-AIR_downloads.zip, approximately 64 MB, refreshed weekly. Before this protocol only the downloads page, ICIS-Air dictionary, About the Data page and a HEAD request were read. HEAD on 30 October 2026 returned 200, Content-Length 69872864 and Last-Modified 25 October 2026. No event rows, coverage summaries or outcome counts were examined. Capture the complete ZIP once using the published bulk link, not robotic service queries. Retain request start/end UTC, HTTP status, URL, headers, bytes, SHA256 and each selected member hash. Inspect original header schemas before extraction; fail on missing required fields. No fallback data source or tuned cohort after outcomes.

Use ICIS-AIR_FACILITIES.csv, ICIS-AIR_FCES_PCES.csv and ICIS-AIR_STACK_TESTS.csv. Current facility fields: program ID, state, EPA region, pollutant class code, operating status code. Evaluation fields: program ID, activity ID, state/EPA flag, monitor type code, actual end date. Stack-test fields: same five event fields plus stack-test status code. Drop names, addresses, coordinates, expressive descriptions and all other unused fields from public projections. Replace program/activity identities with complete SHA256 keys; these are exposure minimization, not an anonymity guarantee. Raw originals and identity mappings stay private.

## Fixed cohort and data handling

Current snapshot operating status OPR, in the fifty US states or DC, with a nonempty program ID. This is a current reported cohort, not a historical active-facility population; survivor selection and entry dates remain unknown. Retain all source rows and exclusion counts. For each table, collapse exact duplicate selected rows, retaining multiplicity. If the same facility key has conflicting selected attributes, exclude every conflicting row from the cohort and report it. Event identity is (program ID,activity ID); exact repeated selected records collapse, while conflicting selected event records are excluded and counted. Missing event keys are excluded with reasons. Keep orphan events and invalid dates in explicit audit counts; do not silently inner-join them away.

Dates accept only dictionary MM/DD/YYYY or ISO YYYY-MM-DD, with optional all-zero time suffix; record format counts. Unknown dates do not enter a calendar window and remain separately reported. Trim field whitespace and uppercase categorical codes; retain raw selected tokens in the minimal source projection so normalization is inspectable. No numeric missing-value imputation.

## Windows, observation categories and denominators

Use all five individual calendar years 2021,2022,2023,2024,2025 and their combined inclusive 2021-01-01 through 2025-12-31 window. Use the same current cohort denominator for every window; do not interpret this as historical inspection rates or legally required frequencies. Dates after 2025 and before 2021 are reported outside the study window, not censored negatives.

For evaluations retain every monitor code. FOO is full on-site; FFO full off-site; PCE,POC,POI,POM,POR are partial on-site; PFF partial off-site. Unknown codes are separate. Dictionary duplicates POI descriptions, so use the code's broad partial on-site category without inventing a finer subtype. Report full on-site, any on-site, off-site-only and no dated evaluation coverage; no record does not prove no real-world inspection.

For stack tests count PSS,FAI,PEN,INC,NA,blank and other status tokens separately. Facility categories per window: no dated stack record; at least one FAI (including mixed pass/fail); PSS only (at least one PSS, no FAI or unresolved/NA/unknown token); PSS plus unresolved/NA/unknown; records with no PSS or FAI. Also export mixed pass/fail counts and facilities with any observed PSS or FAI. These are recorded test categories, not current legal compliance, equivalent inspection outcomes or calibrated risk labels. No result is assigned to an absent facility-year.

Primary summaries are exact counts and fractions, overall and by all observed pollutant classes and all fifty states plus DC. Retain zero-denominator groups as undefined, never zero percent. Export per-facility window counts, group summaries, source/event exclusions and a full group-level missing-coverage list. Do not name or rank individual facilities for risk. Compare full on-site and any on-site coverage to show definition sensitivity, not choose a preferred favorable result. Report all annual and combined windows; no post-hoc top subgroup selection. Counts describe this captured cohort, so no sampling confidence intervals or significance tests are warranted. No population failure-prevalence estimate, inverse weighting, counterfactual inspection benefit, random-selection assumption or causal interpretation.

## Independent checks and release

Independently reconcile selected source cells against the private ZIP using a separate reader, and independently rebuild eligibility, identity conflicts, calendar joins and group counts with Pandas/SQLite rather than importing analysis helpers. Hand-authored tests cover duplicates, conflicting identities, missing dates, year boundaries, no records, off-site-only, mixed status and unknown outcomes. Public offline replay must reproduce canonical tables/documents without network or changes to originals. Check every plotted value and SVG geometry; rebuild manuscript numbers from exported observations. Inspect all figures and rendered pages. Canonical Git hashes and approved independent paper scope must pass bounded publication checks, exact candidate/main Linux runs, tested/merged tree identity and a remote annotated tag.

## Interpretation and prior work

EPA warns national data are generally more complete for larger facilities; smaller-facility inspections may exist only in state systems, and self-reporting also establishes some compliance information. This audit cannot establish the mechanism behind a missing record. Selective-label evaluation is established work, including Lakkaraju et al. (KDD 2017); environmental inspection allocation is established work, including Hino, Benami and Brooks (Nature Sustainability 2018). No exhaustive novelty claim or new statistical estimator. Read those primary sources before interpreting the audit; do not copy their benefit estimates into this study.

Practical next step: reconcile low-coverage groups with state/local records, establish the required test/inspection universe, define comparable outcomes and obtain a defensible observation design before training or evaluating a risk model. The broader historical proposal is retained in the program register and is not the executable scope here.
