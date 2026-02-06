# Built-in imports
import os
import subprocess
import logging
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
# Langchain imports
from langchain.tools import tool # type: ignore
from pydantic import BaseModel, Field # type: ignore

# Local imports
from tools.file_ops import do_in_workdir
from app_config import get_logger

log = get_logger(__name__)

class ExtractCacheInfoInput(BaseModel):
    """This tool takes no arguments."""
    pass # end of ExtractCacheInfoInput

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

def _collect_via_lscpu() -> tuple[str, str]:
    cmd = ["lscpu"]
    log.info(f"[+] Running command: {' '.join(cmd)}")
    out, err, rc = _run(cmd)
    if rc != 0:
        return "", err
    return _filter_cache_lines(out), err

def _collect_via_sysfs() -> tuple[str, str]:
    base = "/sys/devices/system/cpu/cpu0/cache"
    if not os.path.isdir(base):
        return "", ""
    lines = []
    try:
        for entry in sorted(os.listdir(base)):
            idx_path = os.path.join(base, entry)
            if not entry.startswith("index") or not os.path.isdir(idx_path):
                continue
            def readf(name):
                p = os.path.join(idx_path, name)
                try:
                    with open(p, "r") as f:
                        return f.read().strip()
                except Exception:
                    return ""
            level = readf("level")
            ctype = readf("type")  # Data/Instruction/Unified
            size  = readf("size")  # e.g., "32K"
            ways  = readf("ways_of_associativity")
            line  = readf("coherency_line_size")
            sets  = readf("number_of_sets")
            lines.append(f"{entry}: level={level} type={ctype} size={size} ways={ways} line_size={line} sets={sets}")
        return "\n".join(lines), ""
    except Exception as e:
        return "", str(e)

@tool("collect_cacheinfo", args_schema=ExtractCacheInfoInput, return_direct=True)
def collect_cacheinfo() -> tuple[str, str]:
    '''
    Collect CPU cache information (robust across distros).
    Tries in order: getconf -a /, individual getconf vars, lscpu, sysfs.
    Returns (stdout, stderr).
    '''
    # Try getconf
    out, err = _collect_via_getconf()
    if out.strip():
        output = f"""
    *** Cache Info Output Start ***
    {out}
    *** Cache Info Output End ***
    **************************
    *** Cache Info Error Start ***
    {err}
    *** Cache Info Error End ***
    """
        print(output)
        return out, err

    # Fallback: lscpu
    out, err2 = _collect_via_lscpu()
    if out.strip():
        output = f"""
    *** Cache Info Output Start ***
    {out}
    *** Cache Info Output End ***
    **************************
    *** Cache Info Error Start ***
    {err2}
    *** Cache Info Error End ***
    """
        print(output)
        return out, err + ("\n" if err and err2 else "") + err2

    # Fallback: sysfs
    out, err3 = _collect_via_sysfs()
    output = f"""
    *** Cache Info Output Start ***
    {out}
    *** Cache Info Output End ***
    **************************
    *** Cache Info Error Start ***
    {err}\n{err2}\n{err3}
    *** Cache Info Error End ***
    """
    print(output)
    return out, "\n".join(filter(None, [err, err2, err3]))