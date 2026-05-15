# Built-in imports
import os
import re
import subprocess
import logging
import platform
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
# Langchain imports
from langchain.tools import tool # type: ignore
from pydantic import BaseModel, Field # type: ignore

# Local imports
from tools.file_ops import do_in_workdir
from app_config import get_logger

log = get_logger(__name__)

class ExtractSystemInfoInput(BaseModel):
    """This tool takes no arguments."""
    pass # end of ExtractSystemInfoInput

def _get_architecture() -> str:
    """Get the system architecture (e.g., 'aarch64', 'x86_64', 'armv7l')."""
    return platform.machine()

def _run(cmd: list[str]) -> tuple[str, str, int]:
    ret = subprocess.run(cmd, capture_output=True, text=True)
    return (ret.stdout or ""), (ret.stderr or ""), ret.returncode

def _filter_cache_lines(s: str) -> str:
    lines = []
    for line in s.splitlines():
        L = line.strip()
        if any(k in L for k in [
            "CACHE", "LEVEL", "DCACHE", "ICACHE",
            "L1d", "L1i", "L2", "L3", "cache", "linesize", "line size"
        ]):
            lines.append(line)
    return "\n".join(lines)

def _has_complete_cache_info(text: str) -> bool:
    """Return True only when text reports BOTH a non-zero cache size AND associativity.

    For cache-timing attacks (e.g., Prime+Probe) we need size, associativity (ways),
    and set count.  This function checks that a source provides at least the
    first two so the caller can decide whether to fall through to sysfs.

    Two format variants are handled:
    - getconf:  'LEVEL1_DCACHE_SIZE   0' / 'LEVEL1_DCACHE_ASSOC   0'
        On ARM64, the kernel does not populate _SC_LEVEL*_CACHE_SIZE / _ASSOC
        via sysconf(), so these are always 0.  LINESIZE may be non-zero but
        must NOT be mistaken for a size value (_LINESIZE ends in SIZE, so a
        naive r'SIZE\\s+\\d+' regex would match it — we enumerate exact token
        names to avoid that false positive).
    - sysfs:    'size = 64K' / 'ways (assoc) = 4'
        Always complete on Linux for both x86 and ARM64.
    """
    # getconf: explicit token names ending in _SIZE (excludes _LINESIZE)
    _GETCONF_SIZE  = re.compile(
        r'\b(?:DCACHE_SIZE|ICACHE_SIZE|CACHE_SIZE)\s+(\d+)', re.IGNORECASE)
    # sysfs: 'size              = 64K'  (captures leading digits before unit)
    _SYSFS_SIZE    = re.compile(r'\bsize\s*=\s*(\d+)', re.IGNORECASE)
    # sysfs / getconf assoc: 'ways (assoc) = 4'  or  getconf ASSOC token
    _ASSOC         = re.compile(
        r'\b(?:DCACHE_ASSOC|ICACHE_ASSOC|CACHE_ASSOC)\s+(\d+)'
        r'|(?:ways|assoc)\s*(?:\([^)]*\))?\s*=\s*(\d+)',
        re.IGNORECASE)

    has_size = False
    has_assoc = False
    for line in text.splitlines():
        if not has_size:
            for pat in (_GETCONF_SIZE, _SYSFS_SIZE):
                m = pat.search(line)
                if m and int(m.group(1)) != 0:
                    has_size = True
                    break
        if not has_assoc:
            m = _ASSOC.search(line)
            if m:
                val = next(v for v in m.groups() if v is not None)
                if int(val) != 0:
                    has_assoc = True
        if has_size and has_assoc:
            return True
    return False

def _collect_via_getconf() -> tuple[str, str]:
    # Try `getconf -a /`
    cmd = ["getconf", "-a", "/"]
    log.info(f"[+] Running command: {' '.join(cmd)}")
    out, err, rc = _run(cmd)
    if rc == 0 and out.strip():
        return _filter_cache_lines(out), err

    # Fallback: query common variables individually
    vars_to_try = [
        "LEVEL1_DCACHE_SIZE", "LEVEL1_DCACHE_ASSOC", "LEVEL1_DCACHE_LINESIZE",
        "LEVEL1_ICACHE_SIZE", "LEVEL1_ICACHE_ASSOC", "LEVEL1_ICACHE_LINESIZE",
        "LEVEL2_CACHE_SIZE",  "LEVEL2_CACHE_ASSOC",  "LEVEL2_CACHE_LINESIZE",
        "LEVEL3_CACHE_SIZE",  "LEVEL3_CACHE_ASSOC",  "LEVEL3_CACHE_LINESIZE",
        "LEVEL1_DCACHE_SETS", "LEVEL2_CACHE_SETS",   "LEVEL3_CACHE_SETS",
    ]
    lines = []
    errs = []
    for var in vars_to_try:
        for form in ([var], [var, "/"]):
            cmd = ["getconf"] + form
            log.info(f"[+] Running command: {' '.join(cmd)}")
            o, e, rc = _run(cmd)
            if rc == 0 and o.strip():
                lines.append(f"{var}: {o.strip()}")
                break
            if e:
                errs.append(f"{' '.join(cmd)} -> {e.strip()}")
    return "\n".join(lines), "\n".join(errs)

def _collect_via_sysfs() -> tuple[str, str]:
    """Read cache topology from /sys/devices/system/cpu/cpu0/cache/.

    This is the authoritative source on ARM64 because the kernel exposes
    CCSIDR_EL1 / CLIDR_EL1 register values here even though it does NOT
    bridge them into the POSIX sysconf() interface that getconf relies on.
    Each index* subdirectory corresponds to one cache level/type.
    """
    base = "/sys/devices/system/cpu/cpu0/cache"
    if not os.path.isdir(base):
        return "", f"sysfs cache path not found: {base}"
    lines = []
    try:
        for entry in sorted(os.listdir(base)):
            idx_path = os.path.join(base, entry)
            if not entry.startswith("index") or not os.path.isdir(idx_path):
                continue

            def readf(name, idx_path=idx_path):
                p = os.path.join(idx_path, name)
                try:
                    with open(p, "r") as f:
                        return f.read().strip()
                except Exception:
                    return "N/A"

            level = readf("level")
            ctype = readf("type")           # Data / Instruction / Unified
            size  = readf("size")           # e.g. "64K"
            ways  = readf("ways_of_associativity")
            line  = readf("coherency_line_size")
            sets  = readf("number_of_sets")

            # Derive set-index bit width for cache attack calculations
            try:
                n_sets = int(sets)
                set_bits = n_sets.bit_length() - 1 if n_sets and (n_sets & (n_sets - 1)) == 0 else "N/A"
            except (ValueError, TypeError):
                set_bits = "N/A"

            lines.append(
                f"L{level} {ctype} cache ({entry}):\n"
                f"  size              = {size}\n"
                f"  ways (assoc)      = {ways}\n"
                f"  coherency_line_sz = {line} B\n"
                f"  sets              = {sets}  [index bits = {set_bits}]"
            )

        return "\n".join(lines), ""
    except Exception as e:
        return "", str(e)

@tool("collect_system_info", args_schema=ExtractSystemInfoInput, return_direct=True)
def collect_system_info() -> tuple[str, str, str]:
    '''
    Collect system information including CPU architecture and cache hierarchy.

    Returns:
        tuple: (cache_info, architecture, error_messages)
        - cache_info: CPU cache information (L1/L2/L3 sizes, associativity, line sizes)
        - architecture: System architecture (e.g., 'aarch64', 'x86_64', 'armv7l')
        - error: Any error messages from collection attempts
    '''
    arch = _get_architecture()
    log.info(f"[*] Detected Architecture: {arch}")

    # --- Source 1: getconf ---
    # Reliable on x86 (populated from CPUID leaf 0x4) but returns all-zeros on
    # ARM64 because the kernel does not map CCSIDR_EL1/CLIDR_EL1 into POSIX
    # sysconf(). We therefore validate that the values are actually non-zero
    # before accepting getconf output.
    out, err = _collect_via_getconf()
    if out.strip() and _has_complete_cache_info(out):
        log.info("[*] Cache info source: getconf")
        output = f"""
    *** System Info Output Start ***
    Architecture: {arch}
    *** Cache Info Start ***
    {out}
    *** Cache Info End ***
    **************************
    *** Error Messages Start ***
    {err}
    *** Error Messages End ***
    """
        print(output)
        return out, arch, err

    log.info("[*] getconf returned zero/empty cache values — falling through to sysfs")

    # --- Source 2: sysfs (authoritative fallback, always complete on Linux) ---
    # /sys/devices/system/cpu/cpu0/cache/index* exposes the kernel's parsed
    # view of CCSIDR_EL1/CLIDR_EL1 on ARM64 and CPUID on x86. This path is
    # always correct and includes size, associativity, line size, and set count.
    out3, err3 = _collect_via_sysfs()
    log.info("[*] Cache info source: sysfs")
    combined_err = "\n".join(filter(None, [err, err3]))
    output = f"""
    *** System Info Output Start ***
    Architecture: {arch}
    *** Cache Info Start ***
    {out3}
    *** Cache Info End ***
    **************************
    *** Error Messages Start ***
    {combined_err}
    *** Error Messages End ***
    """
    print(output)
    return out3, arch, combined_err


# Backward compatibility: keep the old function name as an alias
@tool("collect_cacheinfo", args_schema=ExtractSystemInfoInput, return_direct=True)
def collect_cacheinfo() -> tuple[str, str]:
    '''
    [DEPRECATED] Use collect_system_info() instead.
    Collect CPU cache information (robust across distros).
    Tries in order: getconf -a /, individual getconf vars, sysfs.
    Returns (stdout, stderr).
    '''
    cache_info, arch, err = collect_system_info()
    output = f"""
    *** Cache Info Output Start ***
    {cache_info}
    *** Cache Info Output End ***
    **************************
    *** Cache Info Error Start ***
    {err}
    *** Cache Info Error End ***
    """
    print(output)
    return cache_info, err