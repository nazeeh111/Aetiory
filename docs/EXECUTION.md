# Paired engine integration contract

`causal_engine.py` is a standard-library-only module. Import it and call `observe(args)`, `search(args)` or `replay(args)` with an `argparse.Namespace`, or invoke its CLI. `main()` prints a compact JSON result; handlers return the full receipt. `Refusal` is a controlled rejection. Exit0 means observed/influence_confirmed/reproduced, exit3 means refused/unresolved; argparse usage errors use exit2.

Current backend: real paired `os.fork`, not heap serialization. Supported proof workloads are explicit trusted synchronous Python entry scripts using selected source modules, with one Python thread and no nonstandard open streams at the split. Sources/inputs are read before computation and a relative artifact is written after it completes. There is no model/provider dependency, separately billed service, uploaded-code sandbox, implicit remote authority or external network endpoint.

## Observe

Namespace fields:

| Field | Value |
|---|---|
| script | Absolute/relative trusted entry script file |
| module | List of `module_name=/absolute/source.py` declarations,1..16 |
| input | List of declared input-file paths |
| arg | List of entry script arguments, at most64 and4096characters each |
| artifact | Relative produced artifact path; protocol names and parent traversal refused |
| out | New no-clobber directory |
| max_events | Integer1..500000, default300000 |
| timeout | Finite .01..300seconds per process group |

Two fresh processes execute an uninstrumented and a return-instrumented baseline. Acceptance requires identical complete artifact bytes. Source, entry, input, engine and interpreter identities are pinned. Module hooks record all evaluated return events. Event paths and small portable values are retained; larger complete portable values are hashed, not stored as intervention targets. Opaque values contribute explicit type/location markers, never fake serialized state. Actual source files remain unchanged.

Files: `manifest.json`, `observation.json`, `plain/`, `observed/trace.jsonl.gz`, complete artifacts and worker receipts. Trace is JSONL gzip containing shared ancestry records plus events. `load_events(path)` yields events with their shared path ancestry restored. Return count limit and512MiB uncompressed trace limit are explicit. Candidate hints are bounded hashes of small surrounding call-argument containers, not dataflow or replay guarantees.

## Search

Namespace fields: `observation`, `out`, `timeout`, `max_trials` (1..512), `seconds` (finite .01..600), and exactly one selector:

- JSON/literal: `pointer='/field/3/value'`, `encoding='json'|'literal'`, `html_id=None`, `html_next_sibling=0`, `start=None`, `end=None`. Pointers follow RFC6901. Literal parsing uses `ast.literal_eval`, not execution.
- Structural HTML: `html_id='from0_72'`, `html_next_sibling=1`, `pointer=None`, `encoding='json'`, `start=None`, `end=None`. The id must resolve uniquely. Following sibling means following **element** sibling, skipping text nodes. HtmlDiff's line-number cell id with sibling1 selects its actual code cell. Structural markup/content snapshots remain stable when preceding text offsets shift.
- Positional text: `start`, `end` as UTF-8 decoded character indices; `pointer=None`, `html_id=None`, `html_next_sibling=0`, `encoding='json'`. This is explicitly positional and cannot establish a changed logical element when earlier text shifts.

Search ranks candidates; it does not label value coincidence or ancestry as causality. At each candidate, a fresh observed worker computes the actual return and checks source/input/interpreter/engine/event/value/path/portable-prefix identity. The OS then copies that live process into parent/child. Parent retains the original return; child receives the portable replacement and switches to its own artifact/log directory. An accepted influence requires complete parent output equal to the original baseline, a valid child output, and a changed selected structural field/subtree. Failed and zero-effect trials are retained. A fresh uninstrumented undo must match baseline exactly.

Outputs: `search.json`, `intervention.json` if confirmed, `trial-0001/` etc, `fresh-undo/`. Search status `influence_confirmed` requires paired evidence and exact undo; otherwise `unresolved`. An experiment is a temporary return intervention, never a source repair or new native measurement.

## Intervention plan

Schema `causal-engine/1`, `kind='intervention'`, `backend='paired-os-fork'`, `prefix_scope='portable-values-and-opaque-markers'`.

- `manifest`, `manifest_hash`: exact identities and execution recipe.
- `event`: `id`, `module`, `site` (line:column), `function`, `value_hash`, `prefix_before`, `ancestry_hash`.
- `replacement`: typed portable value representation. Replacement type must match.
- `selector`, `baseline_artifact`.
- `trace_evidence`: observed value, actual path ancestry, scoped prefix label and prior opaque-return count.
- `observed_effect`: expected child artifact hash/size, paired parent artifact, selected change and collateral.
- `plan_hash`: SHA256 of canonical plan JSON before adding this field. Hashes check integrity, not author authenticity.

Opaque generators/objects may exist earlier in the run because **their actual live state is copied by fork**. Opaque return targets are refused. The portable prefix records all prior portable observations and opaque markers; it does not promise heap reconstruction across machines. Plans execute their explicitly trusted entry again and require both baseline and counterfactual to reproduce. Existing absolute paths/interpreter identities are strict: moving a plan to another environment requires a new verified observation, not silently rewriting identities.

## Replay

Namespace `plan`, `out`, `timeout`. Imported manifests use the same bounded shape/name/argument/budget validator as new observations. Supported selector shape is checked before launch. The packed trace value and path ancestry must hash to the guarded event, and its claimed prior opaque count must equal the actual count at the split. A fresh baseline must reproduce the recorded artifact and resolve the selector before the paired fork. The paired parent must match those bytes, the child must match the recorded counterfactual, and the actual selected values must differ. Collateral is derived again from the actual artifacts. A fresh no-intervention undo must reproduce baseline. Status `reproduced` means these checks passed for this experiment, not universal program correctness. `replay.json` contains `fresh_baseline`, `selector`, `selected_changed`, freshly derived `collateral`, the complete paired receipt and undo.

## Worker receipts and lifecycle

A paired run returns the parent receipt:

- `artifact`: parent baseline bytes/hash.
- `child`: child `ok`, `artifact`, `directory`, error and split details.
- `split`: checked event, actual path ancestry, bounded argument previews, scoped opaque examples and gate evidence.
- `child_pid`, `child_wait_status`, `child_reaped` from native waitpid.
- `events`, `prefix`, `prefix_scope`, `opaque_returns`, error/status.

All work runs in one new owned process group. Child retains that group, uses its own cwd and redirects stdout/stderr. Parent waits for its own child. Whole-process timeout and host exception cancellation share TERM/grace/remaining-group-KILL cleanup. The worker handles TERM by killing and natively waiting its child, retaining its receipt during grace. Timeout results include `worker_cleanup` where available; host cancellation preserves the on-disk receipt and then re-raises the original interruption. Abrupt host/OS KILL cannot promise a receipt. FD0/1/2 are the owned standard streams; every nonstandard open stream at split is refused. No trace file remains open in paired workers. Network, external child spawning, native ctypes loading, pre-split filesystem mutation and writes outside the active owned branch directory are refused. These Python-level checks implement the trusted computation contract and do not constitute an adversarial sandbox or rollback of arbitrary native/external effects.

## Verification

`python3 -m unittest discover -s tests -v` checks source/input/entry/interpreter drift, event/value/ancestry/prefix/plan tampering, opaque targets, user streams, multiple threads, paired timeout and actual SIGINT host cancellation with retained native child-reap receipts, re-sealed invalid/missing/unchanged selectors, forged/empty trace evidence, imported manifest bounds, no-clobber, selector ambiguity, positional-shift independence and portable-value bounds. Actual generic unmodified-program experiments and receipts are separate from these controlled protocol tests.
