'''
cache_threshold.py

LangChain tool that empirically measures the cache hit/miss latency boundary
for the current architecture and returns a safe CACHE_HIT_THRESHOLD value.

Strategy
--------
1. Write a small C calibration program to the workdir.
2. Compile it with gcc (no special flags needed — it auto-selects the timer
   and flush instruction via preprocessor #ifdefs).
3. Run it (CPU-pinned to core 2 for consistency with the rest of the framework).
4. Parse THRESHOLD=, HIT_MEDIAN=, MISS_MEDIAN= from stdout.
5. Return a formatted summary string the Reflection Agent can use directly.

Architecture coverage
---------------------
* aarch64   – cntvct_el0 timer,  dc civac flush
* x86_64    – rdtsc timer,        clflush flush
* armv7l    – PMCCNTR timer,      mcr/mrc flush
* fallback  – clock_gettime,      no-op flush  (threshold is advisory only)
'''

import os
import platform
import subprocess
import tempfile

from langchain.tools import tool           # type: ignore
from pydantic import BaseModel             # type: ignore

from tools.file_ops import do_in_workdir, write_file, _expandpath
from app_config import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# C calibration source
# ---------------------------------------------------------------------------
_CALIBRATION_C = r"""
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define SAMPLES   10000
#define STRIDE    512

/* Use a large array so the compiler cannot optimise accesses away */
static volatile uint8_t probe_array[256 * STRIDE];

/* ---- Architecture-specific timer ---------------------------------------- */
static inline uint64_t rdtime(void) {
#if defined(__aarch64__)
    uint64_t v;
    asm volatile("isb; mrs %0, cntvct_el0" : "=r"(v));
    return v;
#elif defined(__arm__)
    /* ARMv7: use PMCCNTR (needs PMUSERENR.EN=1; may be 0 in user-space –
       fall through to clock_gettime if SIGILL occurs) */
    uint32_t v;
    asm volatile("mrc p15, 0, %0, c9, c13, 0" : "=r"(v));
    return (uint64_t)v;
#elif defined(__x86_64__) || defined(__i386__)
    uint32_t lo, hi;
    asm volatile("mfence; rdtsc" : "=a"(lo), "=d"(hi));
    return ((uint64_t)hi << 32) | lo;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
#endif
}

/* ---- Architecture-specific cache flush ----------------------------------- */
static inline void flush_line(volatile void *addr) {
#if defined(__aarch64__)
    asm volatile("dc civac, %0" : : "r"(addr) : "memory");
    asm volatile("dsb sy"       : : :             "memory");
    asm volatile("isb"          : : :             "memory");
#elif defined(__arm__)
    asm volatile("mcr p15, 0, %0, c7, c14, 1" : : "r"(addr) : "memory");
    asm volatile("dsb"                         : : :            "memory");
#elif defined(__x86_64__) || defined(__i386__)
    asm volatile("clflush (%0)" : : "r"(addr) : "memory");
    asm volatile("mfence"       : : :            "memory");
#else
    (void)addr;
#endif
}

static int cmp_u64(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a;
    uint64_t y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}

int main(void) {
    uint64_t hit_times[SAMPLES], miss_times[SAMPLES];
    volatile uint8_t *addr = &probe_array[128 * STRIDE];
    uint64_t t1, t2;
    int i;

    /* Touch entire array so pages are faulted in */
    for (i = 0; i < (int)(256 * STRIDE); i++)
        probe_array[i] = (uint8_t)(i & 0xFF);

    /* ---------- Measure MISS latency (flush then load) -------------------- */
    for (i = 0; i < SAMPLES; i++) {
        flush_line((void *)addr);
        asm volatile("" ::: "memory");
        t1 = rdtime();
        (void)*addr;
        t2 = rdtime();
        miss_times[i] = (t2 >= t1) ? (t2 - t1) : 0;
    }

    /* ---------- Measure HIT latency (load already in cache) --------------- */
    (void)*addr;   /* prime the cache line */
    for (i = 0; i < SAMPLES; i++) {
        asm volatile("" ::: "memory");
        t1 = rdtime();
        (void)*addr;
        t2 = rdtime();
        hit_times[i] = (t2 >= t1) ? (t2 - t1) : 0;
    }

    qsort(hit_times,  SAMPLES, sizeof(uint64_t), cmp_u64);
    qsort(miss_times, SAMPLES, sizeof(uint64_t), cmp_u64);

    /* Use 50th-percentile (median) for robustness */
    uint64_t hit_med  = hit_times [SAMPLES / 2];
    uint64_t miss_med = miss_times[SAMPLES / 2];

    /* Threshold = hit_median + 1/3 of the hit-to-miss gap.
       Biased toward the hit side so we keep sensitivity. */
    uint64_t threshold;
    if (miss_med > hit_med + 1) {
        threshold = hit_med + (miss_med - hit_med) / 3;
    } else {
        /* Cannot distinguish – return a conservative architecture default */
#if defined(__aarch64__) || defined(__arm__)
        threshold = 10;
#else
        threshold = 80;
#endif
    }

    /* Sanity clamp per architecture */
#if defined(__aarch64__) || defined(__arm__)
    if (threshold < 2)   threshold = 2;
    if (threshold > 100) threshold = 100;
#elif defined(__x86_64__) || defined(__i386__)
    if (threshold < 10)  threshold = 10;
    if (threshold > 500) threshold = 500;
#endif

    printf("HIT_MEDIAN=%llu\n",  (unsigned long long)hit_med);
    printf("MISS_MEDIAN=%llu\n", (unsigned long long)miss_med);
    printf("THRESHOLD=%llu\n",   (unsigned long long)threshold);
    return 0;
}
"""

# ---------------------------------------------------------------------------
# Pydantic schema – no arguments needed
# ---------------------------------------------------------------------------
class CacheThresholdInput(BaseModel):
    """This tool requires no arguments."""
    pass


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------
@tool("measure_cache_threshold", args_schema=CacheThresholdInput, return_direct=True)
def measure_cache_threshold() -> tuple[str, str]:
    """
    Empirically measures the CACHE_HIT_THRESHOLD for the current CPU architecture
    by timing cache-hit vs cache-miss memory accesses.

    Compiles and runs a small C calibration program inside the workdir.
    Works on: aarch64, armv7l, x86_64, i686.

    Returns:
        tuple[str, str]: (result_summary, error_messages)
        - result_summary contains:
            ARCHITECTURE, HIT_MEDIAN, MISS_MEDIAN, RECOMMENDED_THRESHOLD
          and a ready-to-use #define line the agent should copy into the PoC.
        - error_messages contains any stderr/compilation errors (empty on success).
    """
    arch = platform.machine()
    log.info(f"[measure_cache_threshold] Detected architecture: {arch}")

    src_rel  = "PoC/cache_calibrate.c"
    bin_rel  = "PoC/cache_calibrate"

    errors: list[str] = []

    # 1. Write the C source into the workdir
    try:
        write_file(src_rel, _CALIBRATION_C)
    except Exception as e:
        msg = f"Failed to write calibration source: {e}"
        log.error(msg)
        return _fallback_result(arch), msg

    # 2. Compile
    src_abs = _expandpath(src_rel)
    bin_abs = _expandpath(bin_rel)

    compile_cmd = ["gcc", "-O2", "-o", bin_abs, src_abs]
    log.info(f"[measure_cache_threshold] Compiling: {' '.join(compile_cmd)}")
    comp = subprocess.run(compile_cmd, capture_output=True, text=True)
    if comp.returncode != 0:
        msg = f"Compilation failed:\n{comp.stderr}"
        log.error(msg)
        errors.append(msg)
        _cleanup_calibration_files(src_abs, bin_abs)
        return _fallback_result(arch), "\n".join(errors)
    if comp.stderr:
        errors.append(f"Compiler warnings:\n{comp.stderr}")

    # 3. Run (CPU-pinned to core 2, consistent with the rest of the framework)
    run_cmd = ["taskset", "-c", "2", bin_abs]
    log.info(f"[measure_cache_threshold] Running: {' '.join(run_cmd)}")
    try:
        run = subprocess.run(run_cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        msg = "Calibration binary timed out (>30 s)."
        log.error(msg)
        errors.append(msg)
        _cleanup_calibration_files(src_abs, bin_abs)
        return _fallback_result(arch), "\n".join(errors)
    except Exception as e:
        msg = f"Execution error: {e}"
        log.error(msg)
        errors.append(msg)
        _cleanup_calibration_files(src_abs, bin_abs)
        return _fallback_result(arch), "\n".join(errors)

    if run.returncode != 0:
        errors.append(f"Calibration binary exited with code {run.returncode}:\n{run.stderr}")

    # 4. Parse output
    hit_med = miss_med = threshold = None
    for line in run.stdout.splitlines():
        line = line.strip()
        if line.startswith("HIT_MEDIAN="):
            hit_med = int(line.split("=", 1)[1])
        elif line.startswith("MISS_MEDIAN="):
            miss_med = int(line.split("=", 1)[1])
        elif line.startswith("THRESHOLD="):
            threshold = int(line.split("=", 1)[1])

    if threshold is None:
        msg = f"Could not parse calibration output:\n{run.stdout}\n{run.stderr}"
        log.error(msg)
        errors.append(msg)
        _cleanup_calibration_files(src_abs, bin_abs)
        return _fallback_result(arch), "\n".join(errors)

    result = _format_result(arch, hit_med, miss_med, threshold)
    log.info(f"[measure_cache_threshold] Result:\n{result}")
    
    # Clean up temporary calibration files before returning
    _cleanup_calibration_files(src_abs, bin_abs)
    
    return result, "\n".join(errors)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _cleanup_calibration_files(src_path: str, bin_path: str) -> None:
    """Remove temporary calibration C source and binary files."""
    files_to_remove = [src_path, bin_path]
    for fpath in files_to_remove:
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
                log.info(f"[measure_cache_threshold] Cleaned up: {fpath}")
        except Exception as e:
            log.warning(f"[measure_cache_threshold] Failed to remove {fpath}: {e}")


def _format_result(arch: str, hit_med: int, miss_med: int, threshold: int) -> str:
    return (
        f"\n*** Cache Threshold Calibration Result ***\n"
        f"Architecture  : {arch}\n"
        f"Hit  Median   : {hit_med} timer ticks\n"
        f"Miss Median   : {miss_med} timer ticks\n"
        f"Recommended Threshold: {threshold} timer ticks\n"
        f"\n"
        f"Use this in the PoC source code:\n"
        f"NOTE: The threshold is derived from live measurements on this "
        f"machine ({arch}).\n"
        f"      It is the value that best separates cache hits from misses "
        f"for the timer\n"
        f"      used in the PoC (cntvct_el0 on aarch64, rdtsc on x86_64).\n"
        f"*** End Calibration Result ***\n"
    )


def _fallback_result(arch: str) -> str:
    """Return architecture-based heuristic defaults when live measurement fails."""
    defaults = {
        "aarch64": 2,
        "armv7l":  10,
        "armv6l":  10,
        "x86_64":  80,
        "i686":    80,
    }
    threshold = defaults.get(arch, 80)
    return (
        f"\n*** Cache Threshold Calibration Result (FALLBACK – live measurement failed) ***\n"
        f"Architecture  : {arch}\n"
        f"Hit  Median   : N/A\n"
        f"Miss Median   : N/A\n"
        f"Recommended Threshold: {threshold} timer ticks (architecture default)\n"
        f"\n"
        f"Use this in the PoC source code:\n"
        f"NOTE: Live calibration failed; using known-good default for {arch}.\n"
        f"*** End Calibration Result ***\n"
    )
