
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

