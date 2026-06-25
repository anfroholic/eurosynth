# Refactor plan — rebuild eurosynth on the Docker-based starter kit

**Goal:** restructure this repo *as if it had been started from*
[evezor/wafer_space_docker_based_starter_kit](https://github.com/evezor/wafer_space_docker_based_starter_kit),
and rebuild the GDSII using **that repo's tooling** (a fully Docker-based flow)
instead of our current Nix-primary flow. The custom synth design (spine + 5
engines + SPI port) stays exactly as-is; only the **build system** changes.

This is a shared-understanding doc. Nothing is executed until the "Decisions to
confirm" section is settled.

---

## Why this is a small, safe change

Both repos descend from the same
[wafer.space gf180mcu-project-template](https://github.com/wafer-space/gf180mcu-project-template),
so they already share the same skeleton: `src/chip_top.sv`, `src/chip_core.sv`,
`librelane/{config.yaml,slots,macros,pdn}`, `cocotb/`, `ip/`, the **same PDK**
(`gf180mcuD`) pinned to the **same commit** (`019cf7a3e0de79bb0e4b6213758882d283c65816`).

The only real difference is *how the toolchain is delivered*:

| Concern            | eurosynth today                                  | Starter kit (target)                                            |
|--------------------|--------------------------------------------------|-----------------------------------------------------------------|
| Simulation         | Docker (`docker/Dockerfile.sim`, `scripts/sim.sh`) | Docker (`docker/Dockerfile.sim`) via `docker-compose`           |
| **Hardening**      | **Nix** (`flake.nix` → `nix develop` → `make librelane`) | **Docker** (`docker/Dockerfile.harden` = LibreLane image + `pmap` shim) |
| Orchestration      | Makefile calls `librelane`/`ciel` directly (assumes Nix shell) | `docker-compose.yml` + `.env`; Makefile drives compose          |
| PDK fetch          | `ciel enable` → `./gf180mcu`                      | `make pdk` → `ciel` *inside the harden container* → `./pdk`      |
| Config surface     | env vars / flags                                 | `.env` (`SLOT`, `PDK`, `SCL`, `PAD`, `SRAM`, `PDK_ROOT`)         |
| Default slot       | `1x0p5`                                           | `1x1` (we keep **`1x0p5`**)                                      |

Net: we are **adding a Docker hardening path and a compose/.env front-door**, and
demoting Nix to an optional fallback. No RTL, no `librelane/config.yaml`, no pin
changes.

---

## File-level plan

### Add (ported from the starter kit, adapted to eurosynth)
- `docker/Dockerfile.harden` — `FROM ghcr.io/librelane/librelane:3.1.0.dev2` plus
  the `pmap` shim the GF180 KLayout decks need. Ported close to verbatim.
- `docker-compose.yml` — two services (`sim`, `harden`); live-mounts the repo at
  `/work` and the PDK at `/pdk`; reads knobs from `.env`. Adapt the default
  `SLOT` to **`1x0p5`**.
- `.env.example` — design knobs, with `SLOT=1x0p5` and `PDK_ROOT=./pdk`.
- `scripts/harden.sh` — Path A wrapper: `docker compose run --rm harden ...`
  running the same `librelane` invocation we use today.
- `scripts/gen_defines.sh` — writes `src/generated_defines.svh` (replaces the
  Makefile's `$(file …)` block; identical content, container-friendly).

### Rewrite
- `Makefile` → the starter kit's Docker front-door: `build-sim`, `build-harden`,
  `pdk`, `defines`, `sim`, `harden`, `harden-nix` (Path B), `open-klayout`,
  `open-openroad`, `clean`. Adaptations:
  - `DEFAULT_SLOT = 1x0p5` (not `1x1`).
  - `PDK_ROOT = ./pdk` (not `./gf180mcu`).
  - `make sim` runs **our** standalone testbenches (KS golden, spine round-trip,
    `chip_core` elaboration) — not the template's `tb_chip_core.sv`.
  - Keep our `librelane/config.yaml` untouched (custom `VERILOG_FILES`, PDN, DRC
    worker bounds, antenna repair — all the hard-won signoff tuning stays).

### Update (minor)
- `docker/Dockerfile.sim` / `scripts/sim.sh` — keep, but align the image tag with
  what `docker-compose` builds (today it's `eurosynth-sim`).
- `.gitignore` — switch the ignored PDK dir `gf180mcu/` → `pdk/` (already ignores
  `final/`, `generated_defines.svh`).

### Keep unchanged
- All RTL (`src/*.sv`, `src/*.svh`), `tb/`, `models/`, `cocotb/`, `ip/`,
  `librelane/` config + slots + macros + pdn, the docs.

### Remove (Docker-only, per locked decision)
- `flake.nix` / `flake.lock` / `shell.nix` — deleted. Docker is the only build
  path. The harden image tag is pinned in `docker/Dockerfile.harden` /
  overridable via `.env` (`LIBRELANE_IMAGE`) so we can match the LibreLane that
  produced the clean signoff if results drift.

---

## Build & rebuild commands (after the refactor)

**This Windows host has no `make`** (the old Makefile ran inside the Nix shell).
So the **`scripts/*.sh` wrappers are the primary entry points** — they need only
`docker` + `docker compose`, which are present. The Makefile is a thin convenience
layer for Linux/Mac/WSL that calls the same scripts.

```bash
cp .env.example .env              # (once) knobs; SLOT defaults to 1x0p5

bash scripts/sim_all.sh           # fast, no-PDK green check (our standalone TBs)
bash scripts/pdk.sh               # fetch gf180mcuD into ./pdk (~4 GB, one-time)
bash scripts/harden.sh            # RTL -> GDSII via Docker; views saved to ./final/
```

(`docker compose run` auto-builds the images on first use via `pull_policy: build`;
`scripts/sim_all.sh` and friends just work cold.) On a make-equipped host the same
steps are `make sim` / `make pdk` / `make harden`.

Output lands in `final/` (`gds/chip_top.gds`, `nl/`, `def/`, `manufacturability.rpt`,
`metrics.json`, render). We then snapshot a clean signoff the way
`final_roster_v7/` is committed today.

---

## Risks / watch-items

- **Hardening is heavy on Windows + Docker Desktop.** ~4 GB PDK download, then a
  multi-hour OpenROAD/KLayout run; the full 5-engine roster is *tight on the half
  slot* (it's why `config.yaml` bounds DRC/antenna workers to 6 to avoid OOM).
  Expect to babysit the first run.
- **`pmap` shim** must be present in `Dockerfile.harden` or the GF180 KLayout
  decks error out — port it carefully.
- **Reproducing the *clean* signoff** (DRC/LVS/hold/antenna = 0) depends on the
  exact LibreLane image vs. the Nix-pinned LibreLane that produced
  `final_roster_v7`. If results drift, we pin the harden image tag in `.env`
  (`LIBRELANE_IMAGE=…`) to match.
- **Path/mount quirks** on Git Bash are already handled (`MSYS_NO_PATHCONV=1`),
  carry that into `harden.sh`.

---

## Decisions (locked)

1. **Nix** — *removed.* Docker-only; delete `flake.nix`/`flake.lock`/`shell.nix`.
2. **Hardening target** — the **full 5-engine roster** (matches `final_roster_v7`).
3. **Execution** — set up the Docker flow, verify the `make sim` green check, then
   kick off `make pdk` + `make harden` and babysit to a finished, signed-off GDS.
4. **Branch/scope** — work on `docker-harmonize` with normal commits (no history
   rewrite).

---

## Proposed step sequence (once decisions are settled)

1. Port `Dockerfile.harden`, `docker-compose.yml`, `.env.example`,
   `scripts/harden.sh`, `scripts/gen_defines.sh`.
2. Rewrite `Makefile` (Docker front-door, `SLOT=1x0p5` default, our sim TBs).
3. Align `Dockerfile.sim`/`sim.sh` tags; fix `.gitignore` (`pdk/`).
4. `make build-sim && make sim` → confirm the green check in the new flow.
5. `make build-harden && make pdk` → image + PDK.
6. `make harden SLOT=1x0p5` → rebuild GDS; verify signoff = all-zero.
7. Snapshot the deliverable; update `NOTES.md`/`README.md` build instructions to
   the Docker commands.
