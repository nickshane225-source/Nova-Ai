---
name: performance-profiling
description: Measure baselines, identify CPU/memory bottlenecks using profilers, and validate optimizations with data.
triggers: performance profiling, benchmark, hotspot, memory leak, profile code, cprofile, timeit, পারফরম্যান্স, গতি অপটিমাইজ
---

## When to use
Use when a subsystem exhibits high latency, unresponsiveness, excessive memory consumption, or slow request turnaround.

## Procedure
1. **Define the target metric**: Establish specific, measurable criteria (e.g. latency P99 < 50ms, memory growth < 5MB/hour).
2. **Measure the current baseline**: Capture execution timing before modifying code using standard library `timeit` or `cProfile`.
3. **Isolate the hotspot**: Identify the exact function or loop consuming disproportionate CPU time or heap allocations.
4. **Change ONE variable at a time**: Apply a single targeted optimization (e.g. in-memory caching, indexing, algorithmic reduction).
5. **Re-measure under identical conditions**: Run the profiler again against the baseline workload and verify the delta.
6. **Retain only proven gains**: Revert changes that introduce complexity without statistically measurable performance improvements.

## Checklist
- [ ] Was an initial baseline measured and recorded before code changes?
- [ ] Were CPU hotspots identified using `cProfile` or high-resolution timers?
- [ ] Did only one single change get introduced per benchmark run?
- [ ] Do all automated unit tests still pass after the optimization?

## Output format
- **Metric Target**: Measured metric, workload definition.
- **Baseline vs Optimized Table**: Function, Calls, Total Time, Delta.
- **Code Optimization**: Concise diff showing the winning change.

## Example
```python
import cProfile, pstats
profiler = cProfile.Profile()
profiler.enable()
# Run target routine: load_skills("developer")
profiler.disable()
stats = pstats.Stats(profiler).sort_stats("cumulative")
stats.print_stats(10)
# Result: mtime caching reduced cumulative load time from 42ms to 0.12ms (-99.7%)
```
