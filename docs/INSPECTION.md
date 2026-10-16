# Reproduce the inspection

The current screenshots come from an installed0.2.2 candidate on macOS with
CPython3.14.7. The recorded public studio retains its four original experiments;
its JSON and original/alternate artifact bytes are unchanged.

1. Install the wheel in a fresh virtual environment outside the source tree.
2. From the checkout, run the complete CSV command in [the README](../README.md#try-the-complete-csv-investigation), using a new output directory.
3. Open the generated `viewer/index.html`. It embeds the exact exported record,
   viewer code, styles and licenses, and can be inspected offline.
4. Choose **Result** for the original exception and actual alternate stdout,
   **Return** for `planned_capacity` and its source, then **Checks** for the
   recorded paired parent and fresh unchanged control.
5. Select `/stdout` with the keyboard. The sticky context should identify it as
   collateral; choosing the original target restores that distinction.

The retained run tested two paired trials from one eligible return candidate.
The successful replacement was0→1, with exact output of9 records,9 batches and
total3370. Fresh native replay reproduced the alternate and original outcomes;
a fresh unchanged run matched the baseline bytes. The source and CSV were not
edited. This owned workload intentionally retains its floor-allocation defect.

`diagnosis.png` and `return.png` are actual1280×720 browser captures of that
installed export, at the Result and Return anchors. The390px layout was also
operated: branch panels stack, source text remains12px, the document has no
horizontal overflow, and a single case spans the navigation width. These are
specific browser checks, not general accessibility or platform certification.

The browser cannot execute Python. Its checks compare retained record bytes,
not a newly reproduced experiment. Imports remain unauthenticated, source and
outputs render literally, and failed or absent guard checks block acceptance.
Observed callers provide navigation rather than complete causal dataflow.

The earlier `studio.png` remains as historical presentation evidence. Existing
release assets and engine behavior are unchanged by the inspection revision.
