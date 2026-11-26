# A different exception is not the requested result

This is a fresh native run of the project's intentionally failing, owned synthetic CSV workload using current source `946ece2fdc94f1aa0d67f2f71aa551302a7baaa6`. Faultsplice is the current display name. The distribution/import remains `aetiory`, and current source installs both `faultsplice` and `aetiory` commands. Historical records retain their genuine Aetiory provenance.

## Open the complete reader

[Download reader.zip](reader.zip), extract it and open `reader/index.html` in a browser. It is self-contained HTML with inline code, styles, record and license notices. It performs no Python execution or external fetch. The accompanying `reader/experiment.json` can be reopened using **Open experiment**. Downloads reproduce the published original/alternate outcome bytes. Malformed imports refuse while the prior valid case remains visible and downloadable. This historical bundled viewer predates the current unsafe-integer import refusal; use the current Studio or a newly generated portable viewer for external records.

The bundle includes the exact owned source, nine-row input, record, case/control summaries, figures, README and license. Its manifest lists every included path and SHA256. The application package and interpreter are external, explicitly pinned above; a native replay plan is not embedded or claimed portable.

[Case and retained trial outcomes](case.json) · [Control checks](controls.json) · [Actual standalone-browser checks](browser-journey.json) · [Wide trace](paired-trials.svg) · [Portrait trace](paired-trials-mobile.svg).

## What ran

`planned_capacity` computes `len(rows) // workers`. Nine records and 128 workers produce 0, so `itertools.batched` raises `ValueError: n must be at least one`. Each paired trial starts a fresh owned computation and forks at that one live return:

- **Trial 1, return 0→None:** the alternate raises `TypeError`. Its artifact changes, but the exact exit/stdout goal is still false. The retained search class calls that selected-goal result `unchanged`; it does not mean identical exception bytes.
- **Trial 2, return 0→1:** the original parent keeps its ValueError. The alternate exits 0 with `{"batches":9,"records":9,"total":3370}`. Source files remain unchanged. The goal checks actual typed JSON values, not merely exit 0.

One return candidate was eligible; two of three planned replacement trials were attempted before confirmation. This is not an exhaustive search of all causes or all possible replacements. The accepted intervention was then freshly replayed. Both parent and alternate reproduced; fresh unchanged execution matched the original outcome bytes. Native children were reaped. The separate wrong-stdout goal remained `unresolved` and created no success viewer. A changed plan checksum refused, and an existing output destination refused without changing the retained diagnosis.

The evidence establishes diagnostic influence on this run. It does not repair the source, infer complete dataflow, prove general root cause or correctness, or certify performance on other inputs. A native fork copies live process memory; it does not roll back files, network activity or external effects.

## Run a fresh observation

Use trusted current-source Faultsplice/Aetiory on Linux or macOS with Python 3.12+ for this `itertools.batched` example. It has no runtime dependencies. From the extracted reader bundle, with an installed matching package:

```sh
faultsplice diagnose --script source/partition_records.py \
  --input inputs/records.csv \
  --arg "$(pwd)/inputs/records.csv" --arg 128 \
  --stdout-pointer '' \
  --stdout-equals '{"records":9,"batches":9,"total":3370}' \
  --out /tmp/faultsplice-new-observation
```

The output must not exist. `aetiory` is the compatible command alias. A fresh output has its own source, input, engine, interpreter and trace identities; do not rewrite an old replay plan to fit moved files. The existing full setup, replay/search/MCP contracts and limitations remain in the main repository documentation. Only run trusted synchronous workloads whose external effects you own; these guards are not an operating-system sandbox.

## Reader identity and provenance

The local native run's complete raw artifacts and replay records were checked before publication. The public reader replaces only task-owned absolute source-frame paths with repository-relative paths, following the repository's existing convention. Its displayed original-artifact SHA256 identifies that redacted reader copy. The record also retains the original recorded hash and explains that replay guards were established on the original bytes. It is an unauthenticated reader record, not a relocated native execution manifest or an attestation.

The fresh portable exporter now uses the same Faultsplice title, split mark, visible name and accessible home label as the current project. Distribution/import, commands and aliases, storage keys, routes, element IDs, controller behavior, artifact formats and genuine authorship remain intact. This is a visible identity correction, not an engine change or a source-level fix for the workload.

All original implementation and included-source notices remain. The owned CSV source/input are synthetic project examples under the original MIT terms. Complete repository license/provenance context is in `LICENSE.txt`; the self-contained reader also embeds its existing notices. This case does not execute or claim a new upstream bug in CPython, Manifold or any customer system.
