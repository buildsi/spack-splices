#!/usr/bin/env python

import random
import requests
import sys
import json

# To start we are just going to test one OS and container
containers = ["ghcr.io/buildsi/spack-ubuntu-18.04", "ghcr.io/buildsi/spack-ubuntu-20.04"]


def main(pkg, splice, command):

    print("Package: %s" % pkg)
    print("Splice: %s" % splice)
    print("Command: %s" % command)

    # Get versions of package
    versions = requests.get(
        "https://raw.githubusercontent.com/spack/packages/main/data/packages/%s.json"
        % pkg
    )
    if versions.status_code != 200:
        sys.exit("Failed to get package versions")
    versions = versions.json()
    versions = list(set([x["name"] for x in versions["versions"]]))

    # We will build up a matrix of containers and compilers
    matrix = []
    for container in containers:
        print(container)
        response = requests.get("https://crane.ggcr.dev/config/%s" % container)
        if response.status_code != 200:
            sys.exit(
                "Issue retrieving image config for % container: %s"
                % (container, response.reason)
            )
        config = response.json()
        labels = config["config"].get("Labels", {}).get("org.spack.compilers")
        if not labels:
            labels = ["all"]
        else:
            labels = [x for x in labels.strip(",").split(",") if x]
        # programatically get labels or default to "all compilers in the image"
        for label in labels:
            name = (
                container.split("/")[-1]
                .replace("spack", "")
                .replace(":", "-")
                .strip("-")
            )
            if "gcc" not in name and "clang" not in name:
                name = name + "-" + label.replace("@", "-")
            for version in versions:
                container_name = version + "-" + name
                matrix.append([container, label, container_name, pkg, version, splice, command])

    # We can only get up to 256 max - select randomly
    if len(matrix) >= 256:
        print(
            "Warning: original output is length %s and we can only run 256 jobs!"
            % len(matrix)
        )
        matrix = random.sample(matrix, 256)
    print(matrix)
    print("::set-output name=containers::%s\n" % json.dumps(matrix))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit("Please provide the package name as an argument!")
    # package         splice      
    main(sys.argv[1], sys.argv[2], " ".join(sys.argv[3:]))
