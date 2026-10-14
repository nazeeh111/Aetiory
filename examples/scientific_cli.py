"""Source-specific reproduction of CPython #105712; see docs/EVIDENCE.md."""
import argparse
import json


def read_parameters():
    parser = argparse.ArgumentParser(prog='scientific-cli')
    parser.add_argument('-p', '--param', type=float, required=True)
    return parser.parse_args()


if __name__ == '__main__':
    parameters = read_parameters()
    print(json.dumps({'param': parameters.param}, sort_keys=True))
