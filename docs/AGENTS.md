# Local agent tools

MCP, the Model Context Protocol, lets an agent client call local tools over a
documented interface. Aetiory provides newline-delimited JSON-RPC over standard
input/output, following the [MCP lifecycle and stdio specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).

Start a server with explicit trusted workspace and retained-state directories:

```sh
aetiory mcp --workspace /absolute/project --state /absolute/experiment-state
```

Client configuration uses the installed command and these arguments. This repo
does not write your client settings or request credentials. Any MCP client that
supports stdio can supply this command; a real specific desktop-client integration
has not been certified by these transport tests.

| Tool | Input | Output |
|---|---|---|
| `observe_program` | Workspace script, selected module paths, declared inputs, argument tokens, relative artifact | A session-local observation handle and parity receipt |
| `find_influence` | Observation handle and stable HTML id/sibling or JSON/literal pointer | Actual trial summary; an intervention handle only on confirmed influence |
| `inspect_experiment` | Server-created handle | Bounded recorded evidence and retained report path |
| `replay_experiment` | Server-created intervention handle | Fresh paired artifacts and unchanged-run parity |

An example observe call:

```json
{
  "script": "examples/compare_sources.py",
  "modules": {"difflib": "stdlib:difflib"},
  "inputs": ["examples/inputs/verifier-0.1.1.py", "examples/inputs/verifier-0.1.2.py"],
  "arguments": ["@input:0", "@input:1"],
  "artifact": "artifact.html"
}
```

`stdlib:NAME` resolves an installed Python source file without importing the named
module to discover it. Other selected files must be within the workspace;
traversal and symlink paths are refused. Literal argument strings are still
passed to trusted source, so these checks do not restrict all file access by
the executed program or create an OS sandbox.

Handles are random, session-local and bound to unchanged server-created report
bytes. Foreign plan paths cannot be submitted through a tool. Restarting the
server invalidates handles; retained receipts remain on disk for deliberate local
CLI inspection. Execution plans pin absolute paths, the engine and interpreter;
moving them requires a new observation.

Requests and responses are limited to 1 MiB of UTF-8 JSON per frame. Oversized
responses produce a small error while complete reports stay on disk. Calls are
sequential and time-bounded. Mid-call MCP cancellation is not supported; the
engine's process timeout handles its owned process group. Never advertise it as
an uploaded-code service or expose it to untrusted clients.

## Diagnose a failing standalone script

The fifth tool, `diagnose_program`, performs capture, bounded automatic return
search, fresh native replay, unchanged undo and portable export in one call.
`script` is a workspace file; additional `modules` are optional and can use
`stdlib:NAME` source declarations. It automatically observes the entry module.
`inputs` and `arguments` follow `observe_program`, including `@input:0`.

Pass both `stdout_pointer` and `stdout_equals` to require actual output, where
`stdout_equals` is a JSON string such as `"{\"count\":9}"`. No arbitrary predicate
code is evaluated. The response separates `diagnosed`, `unresolved` and
`refused`, with session handles and local receipt/viewer paths. Inspect the
`diagnosis` handle or replay its `intervention` handle. A diagnosed return is
not a source repair; engine capture success is distinct from target exit0.
