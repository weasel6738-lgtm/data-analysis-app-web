# Architecture

## Request flow

1. React loads `/api/dashboard`, which is always marked `isSynthetic`.
2. A CSV upload is bounded before parsing. `analysis.py` calculates numeric
   summaries, a three-sigma baseline, run signals and Pearson correlations.
3. `/api/workflows` passes the structured result to `orchestration.py`.
4. The deterministic workflow first builds a safe baseline separating
   observations, hypotheses and next actions.
5. When explicitly configured, Microsoft Agent Framework can enrich any
   workflow. GitHub Copilot SDK can enrich the `report` workflow.
6. An adapter failure returns baseline output with `status=fallback`.

## Service boundaries

- **API:** validation, upload limits, HTTP errors, CORS and request IDs.
- **Analysis:** no network calls; deterministic and unit-testable.
- **Orchestration:** manufacturing workflow policy and prompt construction.
- **Integrations:** lazy SDK imports and provider-specific lifecycle.
- **UI:** visualization and user interaction; it never calculates authoritative
  control decisions.

## Data and safety

Uploaded CSV data is processed in memory and not persisted. The MVP has no user
identity, database, audit log or production equipment connection. Before
production use add enterprise authentication, authorization, encryption policy,
audit retention, malware/content scanning, observability and an approved data
egress policy. Correlation is labeled as a hypothesis source, never causality.
External AI providers are disabled by default.

## Extension points

`analysis.py` can be replaced by validated pandas/NumPy pipelines or a governed
feature service. Add workflow tools behind the Agent Framework agent rather than
allowing arbitrary code execution. A future equipment/FDC adapter should expose
read-only normalized events and keep control actions in a separately approved
system.
