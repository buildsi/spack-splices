#!/usr/bin/env python

import os
import re
import yaml
import json
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

    experiment = re.sub("([.]yaml|[.]yml)", "", pkg)

    # If we don't have a replace, the implied replacement is the same lib
    replace = content.get('replace', content['splice'])
    print("::set-output name=experiment::%s\n" % experiment)
    print("::set-output name=package::%s\n" % content["package"])
    print("::set-output name=splice::%s\n" % content["splice"])
    print("::set-output name=command::%s\n" % content["command"])
    print("::set-output name=replace::%s\n" % replace)    


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Please provide the splice name (filename under splices) to parse.")
    main(sys.argv[1])
