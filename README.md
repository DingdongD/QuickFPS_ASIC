# QuickFPS ASIC

QuickFPS ASIC is a synthesizable Verilog implementation of the QuickFPS
farthest-point-sampling datapath used by PointKAN-style point-cloud inference.
The current default point engine contains four parallel rows and four serial
distance-update PEs per row (`R=4`, `L=4`, 16 PEs total). It is an FPS engine,
not a GEMM systolic array.

## Architecture

- `RTL/point_engine`: FP32 distance update, row pipeline, and global farthest
  point selection.
- `RTL/bucket_engine`: bucket lower-bound distance, issue/defer/skip policy,
  FIFOs, bucket traversal, and the point-engine wrapper.
- `tb`: deterministic and randomized RTL/gate-level testbenches.
- `scripts`: Python golden checks and remote DC/VCS/PTPX flows.
- `reports`: selected current golden and strict PPA summaries. Large mapped
  netlists, SDF, VCD, and remote run directories are intentionally excluded.

The datapath uses `valid` propagation. No controller waits on a manually
configured PE delay. With the current registered PE, one PE accepts one point
per cycle. Its output signal is updated four clocks after input acceptance and
is observed by the next synchronous stage on the fifth clock. A row chains `L`
PEs, so the FSM-visible first-result latency is `5*L` cycles (`20` cycles for
`L=4`), as measured by the checked-in RTL testbench. Steady-state throughput
remains one point per row per cycle. The `R` rows operate in parallel.

For `point_engine_top`, the no-stall schedule is derived from FSM events:
merge-point loads, streamed point batches, observed `o_row_valid`, final
`far_valid`, and FIFO backpressure. It is not represented by a fixed latency
parameter. For each merge pass, `L` load cycles are followed by `Nbatch` issue
cycles and an FSM-visible `5*L` pipeline drain, where
`Nbatch = ceil(num_points / R)` in the current RTL. With no FIFO or memory
stalls, one bucket therefore takes `P*(Nbatch + 6*L) + 3` clocks from
descriptor acceptance back to idle, where
`P = ceil((merge_count + 1)/L)`. The fixed term covers collect, registered
coordinate capture, and push handoffs; actual completion remains controlled by
valid/full events rather than by a delay counter. Partial final batches are
masked lane by lane.

## Power Composition

An end-to-end PTPX run is not required for every design-space estimate, but
module powers must be converted to energy on a shared event timeline:

```text
E_total = sum(P_active[module] * active_cycles[module] / f)
        + sum(P_idle[module]   * idle_cycles[module]   / f)
```

`bucket_engine` and `point_engine_top` communicate through FIFOs and can
overlap. Their cycle counts and powers must therefore not be added blindly.
The system cycle count comes from producer/consumer valid, FIFO full/empty,
memory response, and output backpressure events. A top-level gate-VCD PTPX run
is still needed when interaction-dependent glitches, clock-tree power, or
signoff-quality total power is required.

## Validation Status

The checked-in current reports target TSMC 28 nm HPC+ BWP40P140 SSG 0.81 V,
125 C at 1 GHz. They use a DC mapped netlist, maximum-SDF gate VCS, an active
window gate VCD, and PTPX `read_vcd`/`update_power`.

- FP32 operators, `pe`, and `bucket_cd` pass randomized Python/RTL golden tests.
- The default 4x4 `point_engine` passes RTL and mapped-netlist gate-level golden
  tests (48 row results, zero mismatches).
- Six strict module points pass gate golden, gate timing checks, DC/PT setup and
  hold, constraint checks, 100% net annotation, 100% synthesis-invariant
  annotation, and at least 99.8% fully annotated leaf cells. The source data is
  `reports/quickfps_cycle_strict_1ghz_ppa.yaml`.
- `point_engine_top`: 39-cycle descriptor-to-push latency, 144251.23 um2 cell
  area, and 49.9 mW total power. Its setup slack is positive but only 0.001 ps.
- `bucket_decision_pipe`: II=1, first output latency 5 cycles, 37342.87 um2,
  18.5 mW, and 5.003 ps setup slack after guardbanded incremental mapping.
- Reader, writer, and ping-pong controller powers are 0.675, 0.746, and
  1.600 mW. The integrated streaming subsystem is 5004.22 um2 and 3.31 mW.
- The aggregate streaming subsystem is an alternative measurement to its DMA
  and controller leaves and must not be summed with them.

The simulator-ready module database is
`reports/quickfps_cycle_strict_1ghz_energy.json`. For the checked RTL workload,
the strict scheduler reports 760 cycles with the analytical DDR backend and
395 accelerator cycles with the pinned DRAMsim3 backend. Their characterized
logic energies are 11.014 nJ and 8.946 nJ respectively. SRAM macro, DDR
controller/PHY, DRAM-device, clock-tree, and routed-interconnect energy are not
included.

Run local golden tests with:

```bash
python3 scripts/run_quickfps_golden.py
```

The remote scripts require Synopsys tools and an SSH password supplied at
runtime, never stored in the repository:

```bash
export QUICKFPS_REMOTE_HOST='<user>@<host>'
export QUICKFPS_REMOTE_PORT='<ssh-port>'
export QUICKFPS_REMOTE_PASS='<password>'
bash scripts/run_remote_quickfps_strict_tops_1ghz_bg.sh
```

After the remote `DONE` marker appears, pull and collect the result with:

```bash
bash scripts/pull_quickfps_strict_tops_1ghz_results.sh <remote-run-directory>
python3 scripts/collect_strict_top_ppa.py <local-result-directory> <output.yaml>
```

`QUICKFPS_REMOTE_BASE` can override the default remote work base directory.

## Citation

If you use this code, please cite:

```bibtex
@inproceedings{yu2026himas,
  title={HIMAS: A Heterogeneous SRAM-RRAM In-Memory Accelerator for Scale-Adaptive PointKAN Inference},
  author={Yu, Xuliang and Zhao, Xinao and Cao, Zewen and Zhou, Yi and Wang, Qi and Zhao, Liang},
  booktitle={IEEE/ACM International Conference on Computer-Aided Design (ICCAD '26)},
  year={2026},
  month={October},
  address={New York, NY, USA},
  doi={10.1145/3831252.3833960},
  isbn={979-8-4007-2873-0/2026/11}
}
```
