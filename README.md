# Testing Splicing

This is a testing ground for splicing! You can use the workflow dispatch to run
a job (and upload artifacts, TBA for saving somewhere). Running locally, instructions are below.
For running on GitHub, you can add a file to [splices](splices) and then trigger the dispatch
event for the workflow. Each YAML file in splices should have the following:

```yaml
package: curl
splice: zlib
command: curl --head https://linuxize.com/
```

It's currently a flat list because we have one of each, and this can be adjusted as needed.
Each of these is considered one experiment. You should not include versions with the package
to be spliced, or the library to splice in, as they will be discovered programatically.
To then run the workflow, simply input "curl.yaml" as the splice variable in the GitHub
workflow interface.

## Build the container

Name it whatever you like.

```bash
$ docker build -t splice-test .
```

Or change the base image (but be aware the Dockerfile here is for Debian, see the [Dockerfile.centos](Dockerfile.centos)
for centos.

```bash
$ docker build --build-arg base=ghcr.io/buildsi/spack-ubuntu-18.04:latest splice-test .
```

Now shell into the container (the entrypoint is bash)

```bash
$ docker run -it splice-test
```

If you want to bind the script to change/update and run again:

```bash
$ docker run -it -v $PWD:/code splice-test
```

```bash
$ which spack
/opt/spack/bin/spack
```

This is where the spack install is located if you want to try tweaking things and then re-running.
Let's rum the splice script for curl and zlib (across all versions):

```bash
                         # binary  # splice                                  # command
$ spack python splice.py curl@7.78.0 zlib   --outfile spliced-curl-7.78.json curl --head https://linuxize.com/
```

This is going to concretize this version of curl, and then perform the splices (see [splice.py](splice.py) for how that works
and then prepare to generate predictions:

1. symbolator: will make predictions based on symbol sets
2. libabigail: makes predictions based on corpora diffs (and an internal representation)

And then the actual "does it work" is determined from running the original executable.
