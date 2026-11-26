<a name="aetiory"></a>

# Faultsplice

> **Faultsplice, distributed as Aetiory.** The distribution and import remain `aetiory`. New installs provide both `faultsplice` and `aetiory` commands; existing releases and recorded evidence retain their Aetiory provenance.

**A changed failure is not success. Check the output you actually need.**

Faultsplice tests alternate values at a selected live Python return. A native fork preserves an unchanged parent beside the alternate child; fresh replay and an unchanged control check the result. It observes diagnostic influence on one trusted run, without editing the workload's source.

[Run the complete CSV case](#try-the-complete-csv-investigation) · [Download this offline reader](docs/presentation/reader.zip) · [Inspect the recorded studio](https://nazeeh111.github.io/Aetiory/) · [Agent tools](docs/AGENTS.md)

<picture>
  <source media="(max-width: 600px)" srcset="docs/presentation/paired-trials-mobile.png">
  <img src="docs/presentation/paired-trials.png" alt="Two actual paired trials of the same zero-capacity return. Replacing 0 with None changes ValueError to TypeError but fails the goal. Replacing 0 with 1 exits successfully with 9 records, 9 batches and total 3370. Fresh replay reproduces both outcomes and an unchanged control preserves the original failure. This is diagnostic evidence, not a source repair.">
</picture>

The fresh owned case has **9 records and 128 workers**. Floor allocation returns 0. The first replacement, `None`, produces a different exception. The second, `1`, preserves all nine records and their total of 3370. The accepted goal requires the complete stdout value, not just exit 0. [Exact trial record, controls and scope](docs/presentation/README.md).

## Carry a readable investigation

[Download reader.zip](docs/presentation/reader.zip), extract it and open **reader/index.html** offline. Follow **Result → Return → Checks**, save/reopen the record, and download the actual published outcomes. The fresh standalone page displays Faultsplice while preserving the `aetiory` package/import and compatible commands. The browser inspects retained evidence; it cannot run Python or establish fresh replay.

The linked reader is a historical capture. Its import control predates the current unsafe-integer refusal; use the current Studio or a newly generated portable viewer for external records with large numeric integers. The reader bundle includes its source/input, hashes and notices. Absolute task-owned frame paths are redacted for publication; the record distinguishes the published artifact hash from the original execution hash. The native run was guarded before redaction. Moving source/interpreter files requires a new observation rather than rewriting an old plan.

[Actual reopened desktop reader](docs/presentation/reader-desktop.png) · [Actual 390px reader](docs/presentation/reader-mobile.png) · [Full reproduction and limits](docs/presentation/README.md)

## Start locally

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-1755ad?logo=python&logoColor=white)](docs/EXECUTION.md)
[![Linux · macOS](https://img.shields.io/badge/native_fork-Linux_%C2%B7_macOS-334155)](docs/EXECUTION.md)
[![No runtime dependencies](https://img.shields.io/badge/runtime_dependencies-0-334155)](pyproject.toml)
[![MIT](https://img.shields.io/badge/license-MIT-334155)](LICENSE)

Python 3.11+ on Linux or macOS. Use trusted, synchronous Python programs with
fork-compatible state. A native process fork copies live computational memory;
it does not roll back files, network activity or other external effects.

```sh
git clone https://github.com/nazeeh111/Aetiory.git
cd Aetiory
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --no-deps .
faultsplice --help  # `aetiory` is an equivalent command
```

Run these commands from a source checkout. This unreleased source version
provides both commands. `faultsplice --version` and `aetiory --version` report 0.2.3.dev0, the same implementation version sent in MCP initialization. The historical 0.2.2 wheel on Releases provides only
`aetiory`; use `aetiory --help` with that wheel. The source build needs
setuptools; the wheel has no runtime dependencies. Nothing registers an agent integration
or changes your application settings automatically.

## Try the complete CSV investigation

From a source checkout after installing Aetiory, use Python 3.12+ for this example
(it uses `itertools.batched`). Every output directory must be new.

```sh
faultsplice diagnose --script examples/partition_records.py \
  --input examples/inputs/records.csv \
  --arg "$(pwd)/examples/inputs/records.csv" --arg 128 \
  --stdout-pointer '' \
  --stdout-equals '{"records":9,"batches":9,"total":3370}' \
  --out experiments/batching
```

Open `experiments/batching/viewer/index.html` offline. Use **Result → Return →
Checks** to follow the same investigation:

| Inspect | Actual installed Python 3.14 run |
|---|---|
| Original | `ValueError: n must be at least one`, exit 1 |
| Selected return | `planned_capacity`, line 10: `0 → 1` |
| Alternate | Exit 0, 9 records, 9 batches, total 3370 |
| Replay and control | Fresh paired replay reproduced both outcomes; fresh unchanged run matched the original bytes |

![Actual selected return 0 to 1 beside the unchanged Python source](docs/images/return.png)

This run tested two paired trials from one eligible return candidate. It is an
owned workload with a retained defect. It is not an upstream bug, a customer
case, or a correctness proof for other inputs. Reproduction records the local
interpreter and source identities; different versions require a new observation.

## Diagnose your own failure

Run a trusted standalone source file unchanged:

```sh
aetiory diagnose --script your_program.py --out experiments/failure
```

Exit 0 alone does not establish that the program did the right thing. For JSON
stdout, require the value you actually need:

```sh
aetiory diagnose --script your_program.py --out experiments/failure \
  --stdout-pointer /result --stdout-equals '{"count":9,"checksum":45}'
```

The entry is observed with real `__main__` identity. Select additional source
modules with `--module name=/absolute/source.py`, declare file inputs with
`--input`, and pass each target argument with `--arg=VALUE`.

`diagnosis.json` distinguishes `diagnosed`, `unresolved` and `refused`; CLI exit
codes are 0, 2 and 3 respectively. A target exception is a captured outcome; an
engine refusal, unsupported stream, quota exhaustion or timeout is not.
Stdout and stderr are each limited to 128 KiB of strict UTF-8, including output
emitted before the split. Retained trials, source context, observed callers,
fresh replay and unchanged control stay together in the portable viewer.

For separate capture and search, use `observe --capture-outcome`, then
`search --successful-exit` with an optional stdout predicate.

## From an artifact to an experiment

Your entry script reads declared inputs, calls explicitly selected Python modules,
then writes a relative artifact. Sources stay unchanged; instrumentation happens
in memory. Each output directory must be new.

```sh
aetiory observe \
  --script examples/compare_sources.py \
  --module "difflib=/absolute/path/to/your/python/stdlib/difflib.py" \
  --input examples/inputs/verifier-0.1.1.py \
  --input examples/inputs/verifier-0.1.2.py \
  --arg /absolute/path/to/examples/inputs/verifier-0.1.1.py \
  --arg /absolute/path/to/examples/inputs/verifier-0.1.2.py \
  --artifact artifact.html --out experiments/observed

aetiory search --observation experiments/observed/observation.json \
  --html-id from0_72 --html-next-sibling 1 \
  --out experiments/searched --max-trials 128 --seconds 600

aetiory replay --plan experiments/searched/intervention.json \
  --out experiments/replayed

aetiory export --observation experiments/observed/observation.json \
  --search experiments/searched/search.json --replay experiments/replayed/replay.json \
  --out experiments/viewer
```

The export is one self-contained HTML file and a companion JSON record. Open the
HTML offline, inspect actual values and download the exact original/alternate
artifact bytes. Sharing is voluntary; inspect the record for your own sensitive
source or data before sharing it. There is no telemetry or automatic upload.

For a complete reproduction without manually resolving paths:

```sh
python examples/run_cases.py --out experiments/cases
```

This runs both real examples against the current installed Python's unmodified
standard-library sources. It retains failed/no-effect trials too. Different
interpreters or input versions require new observations; an old plan is not
silently relocated or rewritten. Large traces and repeated executions can take
minutes. An unresolved search is an honest result.

## Two failure investigations

| Program | Original outcome | Verified alternate |
|---|---|---|
| Scientific CLI through unchanged CPython 3.13 `argparse` | Negative scientific notation is interpreted as an option; exit 2 | The upstream option classifier returns `None`; exit 0 and actual parsed `param=-3e12` |
| Owned CSV partitioner, 9 records over 128 workers | Floor allocation returns 0; `itertools.batched` raises `ValueError` | The entry's capacity return becomes 1; all 9 records and the full total remain verified |

The first reproduces [CPython#105712](https://github.com/python/cpython/issues/105712),
not a newly discovered defect. Python 3.14 already accepts this input, and passing
`-p=-3e12` is a simpler workaround. The second is an owned workload with a
retained defect, not a reported upstream bug or production customer. Both require
actual output, preserve the original failure and perform fresh replay/undo.

## Two concrete questions

| Question | Real input | What the experiment measures |
|---|---|---|
| Why did this HTML diff use an inline highlight? | The complete released Solidrift 0.1.1 and 0.1.2 verifier sources, through CPython `difflib` | Automatic upstream return search; stable code-cell selection and measured collateral |
| Which formatter return controls this nested value? | A full native geometry report, through CPython `pprint` | One selected parsed value changes, while other parsed fields stay equal |

The second experiment alters a rendered representation. It does not change or
repair the underlying native geometry. These examples establish the mechanism
on recorded runs, not complete causal understanding of arbitrary software.

## What makes a result count

1. Plain and instrumented baselines have identical complete artifact bytes.
2. Source, declared input, engine and interpreter identities still match.
3. The expected event, value, observed call ancestry and scoped return prefix match.
4. The paired parent reproduces the original artifact; the child changes the
   selected stable HTML element or parsed JSON/literal path.
5. A fresh replay reproduces both artifacts, and fresh unchanged execution matches
   the baseline. Native children are reaped; incomplete trials remain incomplete.

Candidate ranking is a search hint. Matching values or neighboring containers
do not establish influence. The prefix hashes complete portable observations
and explicit opaque type/location markers. It does not serialize the whole heap;
opaque objects, including paused Python iterators, are copied by the native fork.
Recorded hashes check consistency, not author authenticity.

## Supported boundary

The current engine is for trusted, single-threaded Python computation. At a split,
nonstandard open streams are refused. Python-level checks refuse network calls,
external child spawning and writes outside the active branch directory. These
checks are not an operating-system sandbox and do not protect you from malicious
source or arbitrary native code. Do not use it for live payment, device, browser,
GUI or network sessions.

Only explicitly selected Python source-module returns are instrumented. Native
extension internals, complete dataflow, global minimal explanations, source fixes
and arbitrary heap reconstruction are outside this release. Fixed text offsets
are available in the CLI but can shift when earlier output changes; use stable
HTML ids or parsed pointers for semantic selection.

## Inspect and contribute

```sh
python -m pip install '.[test]'
python -m pytest -q tests
node aetiory/web/checks.mjs
node aetiory/web/controller-checks.mjs
node aetiory/web/failure-checks.mjs
node aetiory/web/portable-check.mjs aetiory/web/recorded-proof.html
```

See [evidence](docs/EVIDENCE.md), [the execution contract](docs/EXECUTION.md),
[the browser record schema](aetiory/web/API.md) and [security reporting](SECURITY.md).
Useful issues include a small trusted example, exact source/input identities,
observed versus expected behavior, and a retained refusal or trial receipt.

MIT for the original implementation. CPython source excerpts retain the PSF
license; native sample provenance retains its Manifold Apache-2.0 notice.
[License and included-source terms](LICENSE) explain each included item.

### Unresolved investigations

Search, diagnose, and MCP summaries expose `termination_reason`, `coverage`, and
`next_action`. Coverage counts candidate replacements from the recorded trace;
it is not a count of every possible cause. Completed trials require a successful
paired parent and reaped child, baseline parity, and a readable selected result.
Refused, timed-out, failed, mismatched and selector-error trials remain separate.
A retry with a larger budget starts the search again rather than continuing it.

For an unresolved search, `aetiory export --observation OBSERVATION.json --search
SEARCH.json --out DIRECTORY` writes `investigation.json` with the recorded
observation, search and partial trial receipts. The paths in the record refer to
the original local run; the export does not embed those run directories or
establish a repair. Confirmed results still use the existing HTML export and
require guarded replay for the final diagnostic conclusion. The source audit hook
is a product guard, not an operating-system sandbox.
