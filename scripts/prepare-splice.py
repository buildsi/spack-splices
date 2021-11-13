#!/usr/bin/env python

import os
import yaml
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(pkg):

    filename = os.path.join(root, "splices", pkg)
    if not os.path.exists(filename):
        sys.exit("%s does not exist." % filename)

    with open(filename, "r") as stream:
        content = yaml.safe_load(stream)

    for tag in ["package", "splice", "command"]:
        if tag not in content:
            sys.exit("%s not found in %s." % (tag, filename))

    # Envars are for this job
    print('echo "package=%s" >> $GITHUB_ENV' % content["package"])
    print('echo "splice=%s" >> $GITHUB_ENV' % content["splice"])
    print('echo "command=%s" >> $GITHUB_ENV' % content["command"])

    # Outputs are for the next
    print("::set-output name=package::%s\n" % content['package'])
    print("::set-output name=splice::%s\n" % content['splice'])
    print("::set-output name=command::%s\n" % content['command'])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Please provide the splice name (filename under splices) to parse.")
    main(sys.argv[1])
