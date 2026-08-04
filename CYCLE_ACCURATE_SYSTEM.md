# QuickFPS cycle-accurate system model

This branch extends the functional QuickFPS core with the timing and power
infrastructure needed before a physical-design flow.  Place-and-route and DFT
are intentionally outside this milestone.

## Implemented hierarchy

```text
CPU preprocessing
  KD-tree leaves + bucket-contiguous coordinates + bucket metadata
                    |
                    v
Algorithm trace
  issue / defer / implicit-skip decision for every bucket and iteration
                    |
                    v
Python cycle model
  Bucket CD pipeline -> decision FIFO -> bucket FIFO
                    -> Point-Engine -> ping-pong chunks
                    -> AXI bursts -> DRAM transactions
                    -> far-point FIFO -> next iteration
                    |
                    +--> analytical banked DDR timing
                    +--> official DRAMsim3 timing
                    +--> PTPX energy-per-active-cycle database
```

The RTL side contains the corresponding timing units:

- `bucket_decision_pipe.v`: four-stage bucket-distance pipeline with reserved
  FIFO credits and an II=1 input path;
- `pingpong_chunk_ctrl.v`: two-slot chunk scheduler with independently held
  coordinate-read, MDT-read, compute, and MDT-write handshakes;
- `axi_burst_reader.v` and `axi_burst_writer.v`: INCR bursts, 4 KiB boundary
  handling, AXI backpressure, response checking, and partial final write
  strobes;
- `quickfps_stream_subsystem.v`: integration of two read DMAs, one write DMA,
  the ping-pong scheduler, and the existing Point-Engine command interface;
- `sram_1r1w_sync.v`: a latency-parameterized synchronous SRAM adapter for
  macro replacement;
- `sram_1r1w_ptpx.v`: a fixed wrapper for gate-level activity and PTPX.

## Timing contracts validated against RTL

### Bucket front end

The C-model uses the same admission rule as `bucket_decision_pipe.v`:

```text
reserved = CD entries in flight + decisions in the output FIFO
in_ready = reserved < decision_fifo_depth
```

The validated default is:

```text
bucket_cd latency       = 4 cycles
bucket input II         = 1 cycle
bucket decision credits = 8
```

A decision written by the CD pipeline becomes consumable from the registered
FIFO on the next cycle.  Consumer backpressure therefore stops new admissions
without dropping or reordering decisions.

### Point-Engine

For one bucket or chunk:

```text
point_batches = ceil(point_count / 4)
merge_passes  = ceil((merge_count + 1) / 4)
latency       = merge_passes * (4 + point_batches + 20) + 2 + 1
```

The constants correspond to four merge-load cycles, a 4-column chain of
five-cycle PEs, two collect/push control cycles, and one registered SRAM
request stage. The existing RTL test case with 48 points and three buffered
references is exactly 39 cycles.

### Memory hierarchy

The model separates three granularities:

1. one ping-pong chunk command;
2. one AXI burst, bounded by `dma_bus_bytes * dma_max_burst_beats` and a 4 KiB
   boundary;
3. one DRAM transaction, 64 B by default.

Consequently, the reported `axi_bursts` and `dram_transactions` are not the
same quantity.  DRAMsim3 receives exactly one request per configured DRAM
transaction.

## Functional and cycle regression

```bash
bash scripts/run_functional_core_tests.sh
PYTHONPATH=cmodel python3 -m unittest discover -s cmodel/tests -v
```

The RTL runner writes one log per test into `build/functional/` and VCD activity
into `build/activity/`.  It covers:

- deterministic Max-Tree tie breaking;
- partial Point-Engine batches;
- the 39-cycle Point-Engine contract;
- end-to-end functional FPS sequence;
- credit-safe bucket decision backpressure;
- ping-pong chunk scheduling;
- synchronous SRAM activity;
- standalone and concurrent AXI DMA traffic;
- the integrated stream subsystem.

## Generate a workload from CPU preprocessing

```bash
cmake -S HOST -B build/host -DCMAKE_BUILD_TYPE=Release
cmake --build build/host --parallel

build/host/quickfps_preprocess \
  --input HOST/test_points.xyz \
  --buckets 2 \
  --samples 4 \
  --out build/preprocessed

PYTHONPATH=cmodel python3 cmodel/generate_workload.py \
  --preprocessed build/preprocessed \
  --samples 4 \
  --output build/quickfps_workload.json
```

The workload contains the exact per-iteration bucket actions and the expected
sampled sequence.  The timing model consumes these actions; it does not replace
the functional FPS golden model.

## Analytical DDR timing

```bash
PYTHONPATH=cmodel python3 -m quickfps_cycle.cli \
  --workload build/quickfps_workload.json \
  --chunk-points 256 \
  --bucket-decision-fifo-depth 8 \
  --bucket-fifo-depth 8 \
  --far-fifo-depth 8 \
  --output build/cycle_result.json
```

The analytical backend models queue capacity, channels, banks, open rows,
row-hit/miss timing, read/write latency, and per-stream active cycles.

## Official DRAMsim3 backend

The bridge fetches a pinned revision of the official repository rather than
copying its source into this project:

```text
https://github.com/umd-memsys/DRAMsim3.git
commit 29817593b3389f1337235d63cac515024ab8fd6e
```

Build it with:

```bash
sudo apt-get install cmake g++ libconfig++-dev
bash scripts/build_dramsim3_bridge.sh
```

Then run:

```bash
LIB=$(find build/dramsim3_bridge \
  -name 'libquickfps_dramsim3_bridge.so' -print -quit)
CFG=build/dramsim3_bridge/_deps/dramsim3_external-src/configs/DDR4_8Gb_x8_2400.ini

PYTHONPATH=cmodel python3 -m quickfps_cycle.cli \
  --workload build/quickfps_workload.json \
  --dramsim3-lib "$LIB" \
  --dramsim3-config "$CFG" \
  --dramsim3-output-dir build/dramsim3_stats \
  --output build/cycle_dramsim3.json
```

The C bridge preserves request tags even when multiple transactions use the
same address and direction.  Python remains responsible for mapping a parent
AXI range to 64 B DRAM transactions.

## RTL-to-C-model cycle validation

```bash
python3 cmodel/validate_rtl_cycles.py \
  --log-dir build/functional \
  --workload build/quickfps_workload.json \
  --cycle-result build/cycle_result.json \
  --reorder-map build/preprocessed/reorder_map.txt \
  --output build/rtl_cycle_validation.json
```

The validator checks:

- Point-Engine accept-to-push latency;
- bucket pipeline II=1, minimum latency, order, and credit stalls;
- ping-pong read/compute/write causality and slot order;
- integrated AXI traffic;
- functional sampled sequence;
- consistency of C-model timing constants with the RTL trace.

## VCD-driven DC and PrimeTime PX

`ptpx/cycle_modules.json` defines the characterization set.  By default, leaf
modules are characterized separately so their energies can be composed without
counting the integrated stream subsystem twice.

```bash
python3 scripts/run_ptpx_manifest.py \
  --target-db /path/to/standard_cells.db \
  --cell-verilog /path/to/standard_cells.v \
  --ppa-output build/ptpx_strict_ppa.yaml \
  --output build/ptpx_energy.json
```

The command runs:

1. Design Compiler at the requested 1 ns clock;
2. mapped-netlist VCS simulation with SDF and module-specific VCD activity;
3. PrimeTime PX using the mapped netlist and VCD;
4. strict rejection unless gate golden, DC/PT timing, physical constraints,
   100% net annotation, leaf-cell annotation, and analysis coverage pass;
5. conversion from gate-VCD total power to pJ per characterized active cycle.

The JSON also carries cell area, process, characterization clock, module
instance count, and composition group.  The simulator rejects a database whose
clock does not match `--clock-hz`.  The current idle value is a leakage-only
lower bound because no dedicated idle gate VCD is characterized yet.

To characterize the aggregate streaming subsystem instead of its leaves:

```bash
python3 scripts/run_ptpx_manifest.py \
  --target-db /path/to/standard_cells.db \
  --cell-verilog /path/to/standard_cells.v \
  --modules quickfps_stream_subsystem \
  --output build/stream_subsystem_energy.json
```

The aggregate result must not be summed with reader, writer, and ping-pong leaf
results.

Use a generated database during cycle simulation:

```bash
PYTHONPATH=cmodel python3 -m quickfps_cycle.cli \
  --workload build/quickfps_workload.json \
  --ptpx-energy build/ptpx_energy.json \
  --output build/cycle_energy_result.json
```

The estimator combines cycle counters with per-module active and idle energy.
Two physical reader instances are accounted for independently through
`coord_read_busy_cycles` and `dist_read_busy_cycles`.

The checked-in strict database is
`reports/quickfps_cycle_strict_1ghz_energy.json`; its full acceptance and PPA
record is `reports/quickfps_cycle_strict_1ghz_ppa.yaml`. The energy loader
rejects both a characterization-clock mismatch and a mismatch between the RTL
cycle-validation record and the configured bucket/Point-Engine timing model.

For `build/quickfps_workload_39.json`, the validated outputs are:

| Memory backend | Accelerator cycles | Characterized logic energy |
| --- | ---: | ---: |
| Analytical banked DDR | 760 | 11.014 nJ |
| Pinned official DRAMsim3 | 395 | 8.946 nJ |

The energy column composes `point_engine_top`, `bucket_decision_pipe`, two AXI
readers, one AXI writer, and `pingpong_chunk_ctrl`. It intentionally excludes
the alternative aggregate top, SRAM macro, DDR controller/PHY, and DRAM-device
energy.

## Deliberate boundary

This milestone does not claim:

- placement, routing, clock-tree synthesis, extraction, IR drop, or EM;
- scan insertion, ATPG, JTAG, or SRAM MBIST;
- compiler-macro SRAM energy unless supplied separately;
- clock-tree, routed interconnect, and realistic idle-clock dynamic power;
- a physical AXI interconnect or DDR PHY/controller implementation.

It does provide the synthesizable DMA/control modules, gate-VCD/PTPX flow, an
official DRAMsim3 timing path, and a Python cycle model whose critical timing
contracts are checked against RTL traces.
