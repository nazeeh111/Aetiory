# Read-only experiment-view/1 consumer

The viewer reads `demo.json` beside index.html or an imported UTF-8 JSON file.
It executes no Python, source, HTML, candidate search or native fork. No account,
telemetry, external fonts or browser compute service is needed. The native CLI
owns execution and must generate this record from actual retained artifacts.
The bundled public CSV example replaces local checkout paths in exception frames
with repository-relative paths. Its artifact hash checks the published bytes;
the recorded execution guards describe the original run before this redaction.

The envelope is `{ "schema": "experiment-view/1", "experiments": [ ... ] }`.
Each experiment has the following required fields:

```text
id: unique bounded string
title, summary: bounded strings
mode: "recorded" | "imported"
status: "accepted" | "no_effect" | "refused" | "partial"
selector: {kind:"html-id-following-element-sibling", id:string, sibling:0..16}
       or {kind:"literal-json-pointer"|"json-pointer", pointer:string}
artifacts: {
  before: {text:string, media_type:string, sha256:64-hex-string|null},
  after:  {text:string, media_type:string, sha256:64-hex-string|null}|null
}
event: {
  id: nonnegative safe integer, site:string, occurrence:positive safe integer,
  ancestry:[{function:string, line:positive integer, first_line?:integer}],
  portable_expected:JSON value, portable_replacement:JSON value,
  prefix_before:64-hex-string|null, value_hash:64-hex-string|null,
  args_preview?:JSON value
}|null
source: {name:string, sha256:64-hex-string|null,
         start_line:positive integer, text:string}|null
changes: [{path:string, before:JSON value, after:JSON value, selected:boolean}]
guards: {
  plain_observed_equal:true|false|null,
  parent_matches_original:true|false|null,
  selected_changed:true|false|null,
  source_inputs_preserved:true|false|null,
  fresh_undo_equal:true|false|null,
  child_reaped:true|false|null
}
limitations:[string], provenance:[string]
```

`source.text` is a context excerpt beginning at start_line; source.sha256
identifies the WHOLE source, not the excerpt. Ancestry is observed call navigation,
not inferred dataflow. `changes` must contain actual semantic differences from
the original/alternate outputs. `selected` distinguishes the original target
from collateral. Sibling 0 selects the anchored element itself; 1 selects its
next element sibling, ignoring intervening text nodes. The label for 0 is
`#id (element)`.
HTML snapshots may be structured tag/attrs/content JSON values from the core,
or tag/attrs/children values from the earlier prototype. `content` takes
precedence when both arrays are present.
Only td/span snapshot text and three recorded diff classes are recognized for a
safe code-diff display. The viewer constructs its own span elements and assigns
textContent; it ignores output attributes, URLs and all other tags. Complete
outputs remain literal text and are never inserted as live HTML. Parsed paths follow
JSON Pointer escaping. Their values must be derived by the CLI parser, not from
shifted character offsets or an invented model response.

The browser verifies UTF-8 artifact-text hashes via WebCrypto where available.
Only matching actual artifact text is downloadable; alternate downloads are
disabled for partial/refused records. Accepting a recorded effect requires status
accepted, six explicit recorded passes, both artifact hashes matching, a retained
selected changed value and a retained return replacement. Missing, contradictory,
no-effect, partial or unavailable checks remain visible as incomplete/refused
evidence. Receipt flags and source identities are records, not authenticated
claims. Imports are always labelled unauthenticated even if their mode says
recorded. Browser checks never claim to rerun the program or verify opaque state.

Limits: an 8 MiB file, 1–12 experiments, output strings <=1,048,576 characters,
512 changed fields, 96 ancestry frames, value nesting <=40 and <=4096 items per
collection. Source context <=100,000 characters. The previous valid experiment
survives a malformed import. New selection invalidates any pending hash result;
asynchronous completion cannot overwrite a newer selected case. Imported bytes,
values, source and argument previews are assigned only with textContent.

For a portable viewer, inline the JSON at build time via an application/json
script with id embedded-record, escaping <, > and & as JSON Unicode escapes,
and inline the trusted CSS and module JS. The embedded-record route skips fetch
entirely. `_make_portable.py` demonstrates this packaging from an existing record,
with exclusive/no-clobber output. The resulting HTML opens offline, including
file://, and retains import/export and actual-output byte downloads. Separate
index/app/style files need a local static server because browsers restrict file
module loading. No source execution occurs either way. The native exporter refuses
numeric integers outside +/- 9007199254740991 so the browser cannot silently round
recorded values. Keep their exact typed native plans for local inspection.
For byte-non-UTF8
artifacts, an explicit binary representation/version extension is needed; do not
decode lossily and present matching text hashes as original-byte fidelity.

`_build_recorded.py` adapts only existing paired proof receipts and artifacts.
Its two current cases are labelled recorded prototypes with manually pinned
earlier-observed events. Final automatic engine cases should replace demo.json
without changing this display-only contract.
