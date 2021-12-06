# Testing Splicing

This is a testing ground for splicing! You can use the workflow dispatch to run
a job (and upload artifacts, TBA for saving somewhere). Running locally, you should use the [spliced](https://github.com/buildsi/spliced)
library. For either case, you can add a file to [splices](splices) and then trigger the dispatch
event for the workflow. 

Each YAML file in splices should have the following:

```yaml
package: curl
splice: zlib
command: curl --head https://linuxize.com/
```

It's currently a flat list because we have one of each, and this can be adjusted as needed.
Each of these is considered one experiment. You should not include versions with the package
to be spliced, or the library to splice in, as they will be discovered programatically.
The above says "Take the binary 'curl' for the package curl, and replace the chosen version of
zlib with all other versions of zlib." You can also ask to splice in a totally different dependency,
for example "Take the hdf5 package, and replace openmpi with mpich." 

```yaml
package: hdf4
splice: openmpi
replace: mpich
...
```
When you don't include a "replace" field, the replacement library is implied to be the same as the spliced one.
To then run the workflow, simply input "curl.yaml" as the splice variable in the GitHub
workflow interface.

## Build the container

Name it whatever you like.

```bash
$ docker build -t splice-test .
```

Now shell into the container (the entrypoint is bash)

```bash
$ docker run -it splice-test
```

The command line client "spliced" should already be installed, and you can always re-pull to update it.

## Generate splice runs

In GitHub workflows, we would generate a matrix of runs. However since we are manually testing, let's just sploot out a list and we can
choose one that we like. As stated above, a splicing experiment is determined by a YAML configuration file. So if we have a set in [splices](splices)
we can shell into the container and bind and they will be there:

```bash
$ docker run -it -v $PWD:/code splice-test
```

Here they are:

```bash
$ ls /code/splices/
```

Note that spack and spliced are on the path

```bash
$ which spack
/opt/spack/bin/spack

$ which spliced
/usr/local/bin/spliced
```

Now let's generate a set of commands to play with!

```bash
$ spliced command /code/splices/curl.yaml
...
spliced splice --package curl@7.74.0 --splice zlib --runner spack --replace zlib --experiment curl curl --head https://linuxize.com/
```

This is going to concretize this version of curl, and then perform the splices (see [splice.py](splice.py) for how that works
and then prepare to generate predictions:

1. symbolator: will make predictions based on symbol sets
2. libabigail: makes predictions based on corpora diffs (and an internal representation)

And then the actual "does it work" is determined from running the original executable. The command
can be written verbatim in the markdown, and for more complex commands you can write (and reference) a script
under [tests](tests).
