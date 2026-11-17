"""Implementation identity agrees across source metadata, CLI and MCP, not protocol version."""
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from aetiory import __version__
from aetiory.mcp import Server, PROTOCOL

class VersionContract(unittest.TestCase):
    def test_implementation_identity_does_not_change_the_wire_protocol(self):
        root = Path(__file__).resolve().parents[1]
        expected = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
        self.assertEqual(__version__, expected)
        result = subprocess.run([sys.executable, '-m', 'aetiory', '--version'],
            cwd=root, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), expected)
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            server = Server(workspace, workspace / 'state')
            result = server.dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': PROTOCOL, 'capabilities': {}, 'clientInfo': {'name': 'version-contract', 'version': '1'}}})
            self.assertEqual(result['serverInfo']['name'], 'aetiory')
            self.assertEqual(result['serverInfo']['version'], expected)
            self.assertEqual(result['protocolVersion'], '2025-11-25')

if __name__ == '__main__':
    unittest.main()
