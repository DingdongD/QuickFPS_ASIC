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
`Nbatch = num_points / R` in the current RTL. With no FIFO or memory stalls, one
bucket therefore takes approximately `P*(Nbatch + 6*L) + 2` clocks from
descriptor acceptance back to idle, where
`P = ceil((merge_count + 1)/L)`. The two final clocks are the collect and push
handoffs; actual completion remains controlled by valid/full events rather
than by this formula. The current wrapper requires `num_points` to be divisible
by `R`; partial final batches are not yet masked.

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

The checked-in current reports target TSMC 28 nm HPC+ at 1 GHz.

- FP32 operators, `pe`, and `bucket_cd` pass randomized Python/RTL golden tests.
- The default 4x4 `point_engine` passes RTL and mapped-netlist gate-level golden
  tests (48 row results, zero mismatches).
- `pe`, `bucket_cd`, and `point_engine` have gate-level VCD PTPX results with
  100% net annotation in the selected reports.
- `point_engine_top` and `bucket_engine` now have independent strict
  post-synthesis gate-VCD PTPX points in
  `reports/quickfps_strict_tops_1ghz_ppa_20260803_190839.yaml`.
- `point_engine_top`: 38-cycle descriptor-to-push latency, 139604.09 total cell
  area, 49.5 mW total PTPX power, 100% net annotation, and 99.872% fully
  annotated leaf cells.
- `bucket_engine`: 49-cycle start-to-done latency, 32899.99 total cell area,
  18.8 mW total PTPX power, 100% net annotation, and 99.834% fully annotated
  leaf cells.
- Both strict tops pass mapped-netlist golden checks, DC/PTPX setup and hold,
  physical design-rule checks, and 100% synthesis-invariant annotation. These
  are zero-delay post-synthesis activity results, not post-layout signoff.
- `point_engine_top` contains the complete 4x4 `point_engine`; their module
  powers are alternative hierarchy measurements and must not be added.

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
