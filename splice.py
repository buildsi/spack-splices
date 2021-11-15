# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
#
# spack python splice.py specA specB


import os
import sys
import shlex
from glob import glob
import json
import logging
import time
import subprocess

from symbolator.asp import PyclingoDriver, ABIGlobalSolverSetup, ABICompatSolverSetup
from symbolator.facts import get_facts
from symbolator.corpus import JsonCorpusLoader, Corpus

from spack.util.executable import which
import spack.binary_distribution as bindist
import spack.rewiring
import spack.bootstrap
from spack.spec import Spec

# Plan of action
# discover spack package already in container (e.g., here we have curl)
# based on that version, run splices and symbolator predictions (maybe libabigail too?)
# save it somewhere, compare predictions to actual MATRIX!


def read_json(filename):
    with open(filename, "r") as fd:
        content = json.loads(fd.read())
    return content


def write_json(content, filename):
    with open(filename, "w") as fd:
        fd.write(json.dumps(content, indent=4))


def splice_all_versions(specA_name, specB_name, transitive=True):
    """
    Perform a splice with a SpecA (a specific spec with a binary),
    and SpecB (the high level spec that is a dependency that we can test
    across versions).

    spack python splice.py curl@7.56.0 zlib
    """
    print("Concretizing %s" % specA_name)
    specA = Spec(specA_name).concretized()

    try:
        specA.package.do_install(force=True)
    except:
        sys.exit("We cannot install the original spec.")

    # Return list of spliced specs!
    splices = []

    # The second library we can try splicing all versions
    specB = Spec(specB_name)
    for version in specB.package.versions:
        if not version:
            continue
        splice_name = "%s@%s" % (specB_name, version)
        print("Testing splicing in %s" % splice_name)
        dep = Spec(splice_name).concretized()
        dep.package.do_install(force=True)
        spliced_spec = specA.splice(dep, transitive=transitive)

        # Exit early and tell the user if there was a splice issue
        # This would probably need a bug report
        if specA is spliced_spec or specA.dag_hash() == spliced_spec.dag_hash():
            sys.exit("There was an issue with splicing!")
        spack.rewiring.rewire(spliced_spec)

        # check that the prefix exists
        if not os.path.exists(spliced_spec.prefix):
            sys.exit(
                "%s does not exist, so there was a rewiring issue!"
                % spliced_spec.prefix
            )
        splices.append({"spec": spliced_spec, "specA": specA, "specB": splice_name})

    return splices


def prepare_splices(splices, spliced_lib):
    """
    Prepare each splice to also include binaries and libs involved.
    """

    def add_contenders(spec, loc="lib"):
        binaries = set()
        manifest = bindist.get_buildfile_manifest(spec.build_spec)
        for contender in manifest.get("binary_to_relocate"):
            if contender.startswith(loc):
                binaries.add(os.path.join(spec.prefix, contender))
        return binaries

    # Keep a lookup of corpora
    for splice in splices:
        splice["binaries"] = list(add_contenders(splice["spec"], "bin"))
        for key in ["libs", "corpora"]:
            if key not in splice:
                splice[key] = []
            if "predictions" not in splice:
                splice["predictions"] = {}

        if "libs" not in splice:
            splice["libs"] = []
        for dep in splice["spec"].dependencies():
            if dep.name == spliced_lib:
                splice["libs"].append(
                    {"dep": dep, "paths": list(add_contenders(dep, "lib"))}
                )

    return splices


def run_symbolator(splices):
    """
    Run symbolator to add to the predictions
    """
    # A corpora cache to not derive again if we already have
    corpora = {}

    # Create a set of predictions for each binary / lib combination
    for splice in splices:
        predictions = {}
        for binary in splice["binaries"]:
            if binary not in corpora:
                corpora[binary] = get_corpus(binary)
            predictions[binary] = {}
            for libset in splice["libs"]:
                for lib in libset["paths"]:
                    if lib not in corpora:
                        corpora[lib] = get_corpus(lib)

                    # Make the splice prediction with symbolator
                    sym_result = run_symbols_splice(corpora[binary], corpora[lib])
                    predictions[binary][lib] = (
                        True if not sym_result["missing"] else False
                    )
            if not predictions[binary]:
                del predictions[binary]
        if predictions:
            splice["predictions"]["symbolator"] = predictions
    return splices


def add_to_path(path):
    path = "%s:%s" % (path, os.environ["PATH"])
    os.putenv("PATH", path)
    os.environ["PATH"] = path


def run_actual(splices, command):
    """
    Run the actual binary (using command from command line)
    """
    # Actual is just a sanity check that the original works!
    actual = None
    for splice in splices:
        if actual == None:
            cmd = "%s/bin/%s" % (splice["specA"].prefix, command)
            print(cmd)
            res = run_command(cmd)
            if res["return_code"] != 0:
                sys.exit("Warning, original command %s does not work." % cmd)

        # Test the splice binary
        cmd = "%s/bin/%s" % (splice["spec"].prefix, command)
        res = run_command(cmd)
        splice["actual"] = True if res["return_code"] == 0 else False
    return splices


def run_libabigail(splices):
    """
    Run libabigail to add to the predictions
    """
    abi = spack.spec.Spec("libabigail+docs")
    abi.concretize()
    add_to_path(os.path.join(abi.prefix, "bin"))
    os.listdir(os.path.join(abi.prefix, "bin"))
    abicompat = spack.util.executable.which("abicompat")
    if not abicompat:
        sys.exit("abicompat not found, make sure you do spack install libabigail+docs")

    for splice in splices:
        if not splice["libs"]:
            continue

        predictions = {}
        for binary in splice["binaries"]:
            predictions[binary] = {}
            for libset in splice["libs"]:
                for lib in libset["paths"]:
                    libprefix = os.path.basename(lib).split(".")[0]
                    # Find the original library path from SpecA spliced into
                    # This could be dangerous as it assumes .so
                    originals = glob(
                        "%s*so" % os.path.join(libset["dep"].prefix, "lib", libprefix)
                    )
                    if not originals:
                        print(
                            "Warning, original comparison library not found for %s"
                            % lib
                        )
                        continue
                    if len(originals) > 1:
                        print(
                            "Warning, more than one library found to match %s, using the first"
                            % lib
                        )
                        print("\n".join(originals))
                    original = originals[0]

                    # Run abicompat to make a prediction
                    res = run_command("%s %s %s" % (abicompat.path, original, lib))
                    print(res)
                    predictions[binary][lib] = (
                        res["result"] == "" and res["return_code"] == 0
                    )
            if not predictions[binary]:
                del predictions[binary]

        if predictions:
            splice["predictions"]["libabigail"] = predictions
    return splices


def get_corpus(path):
    """
    Given a path, generate a corpus
    """
    setup = ABICompatSolverSetup()
    corpus = Corpus(path)
    return setup.get_json(corpus, system_libs=True, globals_only=True)


def run_symbol_solver(corpora):
    """
    A helper function to run the symbol solver.
    """
    driver = PyclingoDriver()
    setup = ABIGlobalSolverSetup()
    return driver.solve(
        setup,
        corpora,
        dump=False,
        logic_programs=get_facts("missing_symbols.lp"),
        facts_only=False,
        # Loading from json already includes system libs
        system_libs=False,
    )


def get_spec_id(spec):
    """Get a quasi identifier for the spec, with the name, version, hash, spackmon id"""
    return "%s@%s/%s:%s" % (
        spec["name"],
        spec["version"],
        spec["full_hash"],
        spec["id"],
    )


def run_symbols_splice(A, B):
    """
    Given two results, each a corpora with json values, perform a splice
    """
    result = {
        "missing": [],
        "selected": [],
    }

    # Spliced libraries will be added as corpora here
    loader = JsonCorpusLoader()
    loader.load(A)
    corpora = loader.get_lookup()

    # original set of symbols without splice
    corpora_result = run_symbol_solver(list(corpora.values()))

    # Now load the splices separately, and select what we need
    splice_loader = JsonCorpusLoader()
    splice_loader.load(B)
    splices = splice_loader.get_lookup()

    # If we have the library in corpora, delete it, add spliced libraries
    # E.g., libz.so.1.2.8 is just "libz" and will be replaced by anything with the same prefix
    corpora_lookup = {key.split(".")[0]: corp for key, corp in corpora.items()}
    splices_lookup = {key.split(".")[0]: corp for key, corp in splices.items()}

    # Keep a lookup of libraries names
    corpora_libnames = {key.split(".")[0]: key for key, _ in corpora.items()}
    splices_libnames = {key.split(".")[0]: key for key, _ in splices.items()}

    # Splices selected
    selected = []

    # Here we match based on the top level name, and add splices that match
    # (this assumes that if a lib is part of a splice corpus set but not included, we don't add it)
    for lib, corp in splices_lookup.items():

        # ONLY splice in those known
        if lib in corpora_lookup:

            # Library A was spliced in place of Library B
            selected.append([splices_libnames[lib], corpora_libnames[lib]])
            corpora_lookup[lib] = corp

    spliced_result = run_symbol_solver(list(corpora_lookup.values()))

    # Compare sets of missing symbols
    result_missing = [
        "%s %s" % (os.path.basename(x[0]).split(".")[0], x[1])
        for x in corpora_result.answers.get("missing_symbols", [])
    ]
    spliced_missing = [
        "%s %s" % (os.path.basename(x[0]).split(".")[0], x[1])
        for x in spliced_result.answers.get("missing_symbols", [])
    ]

    # these are new missing symbols after the splice
    missing = [x for x in spliced_missing if x not in result_missing]
    result["missing"] = missing
    result["selected"] = selected
    return result


def run_command(cmd):
    cmd = shlex.split(cmd)
    output = subprocess.Popen(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    res = output.communicate()[0]
    if isinstance(res, bytes):
        res = res.decode("utf-8")
    return {"result": res, "return_code": output.returncode}


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(
            "Usage:\nspack python splice.py curl@7.56.0 zlib spliced.json curl -I --http2 -s https://linuxize.com/"
        )

    # Ensure we have debug flags added
    os.putenv("SPACK_ADD_DEBUG_FLAGS", "true")
    os.environ["SPACK_ADD_DEBUG_FLAGS"] = "true"

    # TODO make a better command line parser

    splices = splice_all_versions(sys.argv[1], sys.argv[2])

    # The remainder of arguments constitute the test command
    command = " ".join(sys.argv[4:])

    # Add to each splice the list of binaries and libs
    # TODO need to see why debug not present for zlib
    splices = prepare_splices(splices, sys.argv[2])
    splices = run_symbolator(splices)
    splices = run_libabigail(splices)
    splices = run_actual(splices, command)

    # Create a nice little data structure of results
    for splice in splices:
        splice["spec"] = str(splice["spec"])
        splice["specA"] = str(splice["specA"])
        splice["command"] = command
        for libset in splice["libs"]:
            libset["dep"] = str(libset["dep"])

    with open(sys.argv[3], "w") as fd:
        fd.write(json.dumps(splices, indent=4))
