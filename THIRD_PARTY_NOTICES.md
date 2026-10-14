# Included source and evidence

The engine, agent adapter, exporter, viewer and entry scripts are original Aetiory
implementation under MIT.

Recorded source context comes from CPython 3.14.7's unmodified `difflib.py` and
`pprint.py`. Python's source license and bundled notices are retained in
`licenses/PSF.txt`; source hashes accompany the experiments. Local reproductions
use the current installed Python source rather than downloading another runtime.

The sample verifier sources are full released Solidrift 0.1.1 and 0.1.2 files,
original work by Nazeeh Abdul-Hadi under MIT. The geometry report is recorded native
Solidrift evidence derived from its Manifold case, not a new native measurement
made by Aetiory. Solidrift's Manifold fixtures retain Apache-2.0 provenance and its
license is included in `licenses/Manifold-Apache-2.0.txt`. The original Offset3.obj and Offset4.obj fixture provenance is pinned to
Manifold commit 761661c15bacb6c8459d682c715de84591d51774. No ownership over those
fixtures is claimed.

Tracing, dynamic program slicing and process fork have long-standing precedents.
noWorkflow, Whyline and mature debuggers already expose useful execution evidence.
Aetiory's contribution is the particular artifact-selection, automatic paired
return trial, guarded replay and portable evidence workflow. No first-in-history
or universal superiority claim is made.
