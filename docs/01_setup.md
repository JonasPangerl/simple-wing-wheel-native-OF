# 1. Setup

Two things to get right: an OpenFOAM v2606 you can run, and `env/project.env`
pointing at it.

---

## 1.1 Do you already have OpenFOAM v2606?

```bash
source /path/to/OpenFOAM-v2606/etc/bashrc
echo $FOAM_API            # want: 2606
which simpleFoam snappyHexMesh
```

If both tools resolve and `FOAM_API` is 2606, skip to [1.3](#13-configure-the-project).

On a cluster with environment modules, try `module avail openfoam` first — a
site-provided build saves you an hour.

---

## 1.2 Building OpenFOAM v2606 from source

Needed only if no v2606 is installed. Takes 1–3 hours on 20 cores and about
15 GB.

### Prerequisites

```bash
# compiler supporting C++17: gcc >= 10 (gcc 12 recommended)
gcc --version
# and these
for t in flex bison cmake make m4 mpicc; do command -v $t || echo "MISSING: $t"; done
```

Also needs `zlib` headers (`zlib-devel` / `zlib1g-dev`) and a working MPI. A
system OpenMPI is fine and usually preferable to building one.

> RHEL/Rocky 8 ships gcc 8.5, which is **too old**. Load a newer one
> (`module load gcc/12.2.0`) before you start.

### Download and unpack

```bash
mkdir -p ~/OpenFOAM && cd ~/OpenFOAM
curl -L -o OpenFOAM-v2606.tgz      https://dl.openfoam.com/source/v2606/OpenFOAM-v2606.tgz
curl -L -o ThirdParty-v2606.tar.gz https://dl.openfoam.com/source/v2606/ThirdParty-v2606.tar.gz

tar xzf OpenFOAM-v2606.tgz
tar xzf ThirdParty-v2606.tar.gz
```

`-L` matters: `dl.openfoam.com` redirects to SourceForge and without it you
get a 296-byte HTML redirect page instead of the tarball. Check the sizes —
the core is ~69 MB, ThirdParty ~370 MB.

### Pin compiler and MPI

Create `OpenFOAM-v2606/etc/prefs.sh`:

```bash
# load the toolchain this build should use
module unload gcc 2>/dev/null; module load gcc/12.2.0 2>/dev/null
module unload openmpi 2>/dev/null; module load mpi/openmpi-x86_64 2>/dev/null

export WM_COMPILER=Gcc
export WM_MPLIB=SYSTEMOPENMPI       # use the system MPI, do not build one
export WM_LABEL_SIZE=32
export WM_PRECISION_OPTION=DP
export WM_COMPILE_OPTION=Opt
```

Adjust the module names, or drop the `module` lines if your compiler and MPI
are already the default ones.

### Build

```bash
cd ~/OpenFOAM
source OpenFOAM-v2606/etc/bashrc
foamSystemCheck                     # must say PASS

cd ThirdParty-v2606 && ./Allwmake -j 20 2>&1 | tee ../log.ThirdParty
cd ../OpenFOAM-v2606 && ./Allwmake -j 20 -s 2>&1 | tee ../log.Allwmake

# run it a second time: it links what the first pass could not, and the
# second run is the one whose summary you can trust
./Allwmake -j 20 -s 2>&1 | tee ../log.Allwmake2
```

Two things that look like failures but are not:

- **`METIS ... Missing sources`** — optional decomposition library. `scotch`
  is built and is what this project uses.
- **Link errors from optional modules** (`adios`, `pbe`, `vdf`,
  `runTimePostProcessing`) on the *first* pass. They try to link before the
  core libraries exist. The second pass resolves them.

### Check it

```bash
source ~/OpenFOAM/OpenFOAM-v2606/etc/bashrc
echo $FOAM_API                      # 2606
which simpleFoam snappyHexMesh potentialFoam decomposePar
simpleFoam -help | head -3
```

---

## 1.3 Configure the project

```bash
cd /path/to/simple_wing_wheel_nativeOF
cp env/project.env.example env/project.env
$EDITOR env/project.env
```

The two entries that matter:

```bash
OPENFOAM_BASHRC="/home/you/OpenFOAM/OpenFOAM-v2606/etc/bashrc"
NP=8
```

`NP` is the number of MPI ranks **one case** uses. Meshing needs roughly
1.5 GB of RAM per million cells, and the baseline mesh is ~19 M cells, so
budget around 30 GB across the ranks. Running several cases at once is a
separate setting — see [06_campaign.md](06_campaign.md).

If your cluster needs modules loaded before OpenFOAM:

```bash
MODULES_TO_LOAD="gcc/12.2.0 mpi/openmpi-x86_64"
```

`env/project.env` is gitignored, so your paths stay out of the repository.

### Verify

```bash
source env/activate.sh
echo "api=$OF_API  NP=$NP"
```

Silence plus a sensible `api` and `NP` means you are set. `activate.sh`
refuses anything below api 2306 and warns on anything that is not 2606.

---

## 1.4 Common setup failures

| Symptom | Cause |
|---|---|
| `env/project.env does not exist` | you skipped the `cp` in 1.3 |
| `OPENFOAM_BASHRC does not point at a file` | typo, or a relative path — it must be absolute |
| `sourced ... but simpleFoam is not on the PATH` | OpenFOAM is unpacked but not built, or built for a different `WM_OPTIONS` |
| `OpenFOAM api 2212 is too old` | project needs ≥ 2306 for the `<case>/` include syntax |
| `mpirun: command not found` inside a run | MPI is not in `MODULES_TO_LOAD` and not in your default environment |

---

Next: [2. Geometry](02_geometry.md)
