# Security policy

Aetiory executes explicitly trusted local Python with your user privileges.
Python audit checks, path checks and plan hashes are not an OS sandbox or author
authentication. Do not run unknown entry scripts or imported execution plans,
expose the MCP stdio server to untrusted clients, or use it for live external
side effects. The browser studio only reads records; it does not execute source.

Please report a demonstrated boundary failure privately through this repository's
GitHub security reporting channel when enabled. Include the affected version,
minimal trusted reproduction, expected boundary and observed result. Avoid private
data, large payloads and claims of criticality unsupported by the impact. Ordinary
correctness, setup and usability issues belong in Issues.

The supported release is the latest 0.1.x patch. A source-level repair or runtime
restriction is not complete protection from malicious Python/native code.
