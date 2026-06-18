"""
hardware_profile.py — Iris AI Auto Hardware Profiler
=====================================================
Detects the current device at startup and returns optimal llama.cpp
parameters with no manual configuration required.

Covers:
  - Apple Silicon (M1/M2/M3/M4, all variants, Air vs Pro vs Max vs Ultra)
  - NVIDIA GPU (CUDA, any VRAM size)
  - AMD GPU (ROCm)
  - CPU-only (Intel / AMD, any core count / RAM)
  - Windows / Linux / macOS

Call `get_hardware_profile()` — it returns a `HardwareProfile` dataclass
with all parameters ready to pass to llama.cpp's Llama().

Iris load_model() reads these instead of the flat values in iris.conf,
but iris.conf manual overrides still win when explicitly set.
"""

import os
import re
import sys
import platform
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum

# ── optional deps (graceful degradation) ─────────────────────────────────────
try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class AccelBackend(str, Enum):
    METAL   = "metal"    # Apple Silicon GPU (via llama.cpp Metal)
    CUDA    = "cuda"     # NVIDIA CUDA
    ROCM    = "rocm"     # AMD ROCm
    VULKAN  = "vulkan"   # Generic Vulkan (fallback GPU)
    CPU     = "cpu"      # No GPU acceleration


class ChipFamily(str, Enum):
    APPLE_M1        = "apple_m1"
    APPLE_M2        = "apple_m2"
    APPLE_M3        = "apple_m3"
    APPLE_M4        = "apple_m4"
    APPLE_UNKNOWN   = "apple_unknown"
    NVIDIA          = "nvidia"
    AMD             = "amd"
    INTEL_CPU       = "intel_cpu"
    AMD_CPU         = "amd_cpu"
    ARM_CPU         = "arm_cpu"
    UNKNOWN         = "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HardwareProfile:
    """All parameters needed to load a llama.cpp model optimally."""

    # ── identity ──
    chip_family: ChipFamily = ChipFamily.UNKNOWN
    backend: AccelBackend   = AccelBackend.CPU
    device_label: str       = "Unknown device"

    # ── RAM / VRAM ──
    total_ram_gb:  float = 8.0
    free_ram_gb:   float = 4.0
    total_vram_gb: float = 0.0   # 0 = unified / n/a

    # ── CPU ──
    physical_cores: int = 4
    perf_cores:     int = 4      # P-cores only (E-cores excluded for threads)
    logical_cores:  int = 4

    # ── llama.cpp tuning ──
    n_gpu_layers:    int  = -1
    n_threads:       int  = 4
    n_threads_batch: int  = 4
    n_batch:         int  = 512
    n_ubatch:        int  = 256
    flash_attn:      bool = True
    use_mmap:        bool = True
    use_mlock:       bool = False

    # ── context window ──
    # Per-role ctx ceilings; load_model picks the appropriate one.
    ctx_triage:    int = 1024
    ctx_control:   int = 8192
    ctx_math:      int = 4096
    ctx_code:      int = 8192
    ctx_reasoning: int = 8192
    ctx_general:   int = 8192
    ctx_vision:    int = 4096
    ctx_default:   int = 4096

    # ── KV cache ──
    kv_quant: str = "q8_0"   # "q4_0" | "q8_0" | "f16"

    # ── recommended size profile ──
    # Overrides iris.conf "size" if not explicitly set by user.
    recommended_size: str = "small"

    # ── diagnostics ──
    notes: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Internal detection helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ram_gb() -> tuple[float, float]:
    """Return (total_gb, free_gb)."""
    if _PSUTIL:
        vm = psutil.virtual_memory()
        return vm.total / 1e9, vm.available / 1e9
    try:
        if platform.system() == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            total = int(out.strip()) / 1e9
            # No easy free-RAM sysctl — use vm_stat
            vm = subprocess.check_output(["vm_stat"], text=True)
            pages_free = int(re.search(r"Pages free:\s+(\d+)", vm).group(1))
            pages_inactive = int(re.search(r"Pages inactive:\s+(\d+)", vm).group(1))
            page_size = 16384  # 16 KB on Apple Silicon
            free = (pages_free + pages_inactive) * page_size / 1e9
            return total, free
        elif platform.system() == "Linux":
            with open("/proc/meminfo") as f:
                mi = f.read()
            total = int(re.search(r"MemTotal:\s+(\d+)", mi).group(1)) * 1024 / 1e9
            avail = int(re.search(r"MemAvailable:\s+(\d+)", mi).group(1)) * 1024 / 1e9
            return total, avail
        elif platform.system() == "Windows":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                             ("dwMemoryLoad", ctypes.c_ulong),
                             ("ullTotalPhys", ctypes.c_ulonglong),
                             ("ullAvailPhys", ctypes.c_ulonglong),
                             ("ullTotalPageFile", ctypes.c_ulonglong),
                             ("ullAvailPageFile", ctypes.c_ulonglong),
                             ("ullTotalVirtual", ctypes.c_ulonglong),
                             ("ullAvailVirtual", ctypes.c_ulonglong),
                             ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return stat.ullTotalPhys / 1e9, stat.ullAvailPhys / 1e9
    except Exception:
        pass
    # POSIX fallback
    try:
        total = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 1e9
        return total, total * 0.4
    except Exception:
        return 8.0, 3.0


def _cpu_cores() -> tuple[int, int, int]:
    """Return (physical, perf_cores, logical)."""
    logical = os.cpu_count() or 4

    if _PSUTIL:
        try:
            physical = psutil.cpu_count(logical=False) or logical // 2
        except Exception:
            physical = logical // 2
    else:
        physical = logical // 2

    # Apple Silicon P/E core split via sysctl
    perf = physical
    if platform.system() == "Darwin":
        try:
            p = subprocess.check_output(
                ["sysctl", "-n", "hw.perflevel0.physicalcpu"], text=True
            ).strip()
            perf = int(p)
        except Exception:
            # Fallback heuristic: ~half cores are P-cores on M-series
            perf = max(4, physical // 2)

    return physical, perf, logical


def _detect_apple_chip() -> tuple[ChipFamily, str]:
    """Detect M-series chip generation and variant."""
    try:
        brand = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip()
    except Exception:
        brand = ""

    if not brand:
        try:
            brand = subprocess.check_output(
                ["sysctl", "-n", "hw.model"], text=True
            ).strip()
        except Exception:
            brand = ""

    label = brand or "Apple Silicon"
    low = brand.lower()

    if "m4" in low:
        return ChipFamily.APPLE_M4, label
    if "m3" in low:
        return ChipFamily.APPLE_M3, label
    if "m2" in low:
        return ChipFamily.APPLE_M2, label
    if "m1" in low:
        return ChipFamily.APPLE_M1, label
    return ChipFamily.APPLE_UNKNOWN, label


def _detect_nvidia() -> tuple[bool, float, str]:
    """Return (found, vram_gb, label)."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )
        lines = [l.strip() for l in out.strip().splitlines() if l.strip()]
        if not lines:
            return False, 0.0, ""
        name, vram_mib = lines[0].rsplit(",", 1)
        vram_gb = float(vram_mib.strip()) / 1024
        return True, vram_gb, name.strip()
    except Exception:
        return False, 0.0, ""


def _detect_amd_gpu() -> tuple[bool, str]:
    """Crude ROCm/AMD GPU check."""
    try:
        out = subprocess.check_output(["rocm-smi", "--showproductname"],
                                      text=True, timeout=5)
        if "GPU" in out or "Radeon" in out:
            return True, out.splitlines()[0].strip()
    except Exception:
        pass
    return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# Context window sizing
# ─────────────────────────────────────────────────────────────────────────────

def _ctx_for_ram(
    total_ram_gb: float,
    model_size_gb: float = 4.0,
    backend: AccelBackend = AccelBackend.CPU,
) -> dict:
    """
    Calculate safe per-role context window sizes given available memory.

    The KV cache for a 7B Q4 model is ~48 bytes/token (Q8_0).
    At 8192 ctx that's ~390 MB. We leave headroom for the OS, model
    weights, and output buffer.
    """
    # Unified memory (Apple Silicon) = RAM = VRAM, so budget is tight
    if backend == AccelBackend.METAL:
        budget_gb = total_ram_gb - model_size_gb - 2.5   # OS + overhead
    elif backend in (AccelBackend.CUDA, AccelBackend.ROCM):
        budget_gb = total_ram_gb - 2.0   # system RAM, GPU has its own VRAM
    else:
        budget_gb = total_ram_gb - model_size_gb - 2.0

    budget_gb = max(budget_gb, 0.5)

    # Scale ctx linearly with budget
    if budget_gb < 1.5:
        base = 2048
    elif budget_gb < 3.0:
        base = 4096
    elif budget_gb < 6.0:
        base = 8192
    elif budget_gb < 12.0:
        base = 16384
    else:
        base = 32768

    return {
        "ctx_triage":    min(1024, base),
        "ctx_control":   min(base, 8192),
        "ctx_math":      min(base, 8192),
        "ctx_code":      base,
        "ctx_reasoning": base,
        "ctx_general":   base,
        "ctx_vision":    min(base, 4096),
        "ctx_default":   min(base, 4096),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Per-backend tuning tables
# ─────────────────────────────────────────────────────────────────────────────

def _apple_silicon_params(
    chip: ChipFamily, total_ram_gb: float, perf_cores: int
) -> dict:
    """
    Tuned llama.cpp parameters for Apple Silicon.

    Key insights:
    - n_threads = perf_cores only (E-cores cause stalls on llama.cpp decode)
    - n_threads_batch = perf_cores (parallel prompt processing)
    - n_batch = 512 is sweet spot for M-series Metal; 2048 causes longer
      kernel stalls because Metal can't overlap compute and memory well at
      large batch sizes with small models
    - n_ubatch = 256 fits the M-series L2/L3 slice cache
    - flash_attn=True always (Metal supports it; big win for long contexts)
    - use_mlock=False (unified memory, locking wastes address space)

    Variant-specific notes:
    - Air (passive cooling): same settings, OS throttles automatically
    - Pro/Max/Ultra: more GPU cores + memory bandwidth; n_batch can go higher
    """
    is_pro_max_ultra = total_ram_gb >= 32  # Air tops at 24 GB; Pro starts at 18 GB

    threads = max(4, min(perf_cores, 8))

    if is_pro_max_ultra:
        # More memory bandwidth → larger batch profitable
        n_batch  = 1024
        n_ubatch = 512
        kv_quant = "f16"   # Bandwidth to spare, quality over compression
    elif total_ram_gb >= 16:
        n_batch  = 512
        n_ubatch = 256
        kv_quant = "f16"
    else:
        # 8 GB Air / base M-series
        n_batch  = 512
        n_ubatch = 256
        kv_quant = "q8_0"

    # M4 has improved Neural Engine and memory controller
    if chip == ChipFamily.APPLE_M4:
        n_batch  = min(n_batch * 2, 2048)
        n_ubatch = min(n_ubatch * 2, 512)

    return dict(
        n_gpu_layers=-1,
        n_threads=1,          # Inference is on GPU. CPU spins waste energy.
        n_threads_batch=threads, # Prompt eval uses multiple threads
        n_batch=n_batch,
        n_ubatch=n_ubatch,
        flash_attn=True,
        use_mmap=True,
        use_mlock=False,
        kv_quant=kv_quant,
    )


def _nvidia_params(vram_gb: float, system_ram_gb: float, logical_cores: int) -> dict:
    """
    CUDA-optimised parameters.

    - n_gpu_layers=-1 (all layers on GPU)
    - n_batch=2048 (CUDA benefits from large batch; more parallelism)
    - n_ubatch=512
    - flash_attn=True (cuDNN flash attention is fast)
    - KV quant: q8_0 for <8 GB VRAM, f16 otherwise
    """
    cpu_threads = min(logical_cores, 8)
    kv_quant = "f16" if vram_gb >= 10 else "q8_0"

    return dict(
        n_gpu_layers=-1,
        n_threads=cpu_threads,
        n_threads_batch=cpu_threads,
        n_batch=2048,
        n_ubatch=512,
        flash_attn=True,
        use_mmap=True,
        use_mlock=False,
        kv_quant=kv_quant,
    )


def _amd_gpu_params(system_ram_gb: float, logical_cores: int) -> dict:
    """ROCm / AMD GPU — conservative defaults (ROCm flash-attn support varies)."""
    cpu_threads = min(logical_cores, 8)
    return dict(
        n_gpu_layers=-1,
        n_threads=cpu_threads,
        n_threads_batch=cpu_threads,
        n_batch=1024,
        n_ubatch=512,
        flash_attn=False,  # ROCm flash-attn support is llama.cpp version dependent
        use_mmap=True,
        use_mlock=False,
        kv_quant="q8_0",
    )


def _cpu_only_params(total_ram_gb: float, physical_cores: int, logical_cores: int) -> dict:
    """
    CPU-only inference.

    - All layers on CPU (n_gpu_layers=0)
    - Use all physical cores for threads (hyperthreading doesn't help here)
    - Small batch (CPU memory latency dominates)
    - No flash attention (CPU path is slower, overhead not worth it)
    - use_mlock=True if enough RAM (prevents swap thrashing mid-generation)
    """
    threads = min(physical_cores, 16)  # diminishing returns past 16
    mlock = total_ram_gb >= 16         # only lock if we have headroom

    # Smaller batches reduce cache pressure on CPU
    if total_ram_gb >= 32:
        n_batch  = 512
        n_ubatch = 256
    elif total_ram_gb >= 16:
        n_batch  = 256
        n_ubatch = 128
    else:
        n_batch  = 128
        n_ubatch = 64

    return dict(
        n_gpu_layers=0,
        n_threads=threads,
        n_threads_batch=threads,
        n_batch=n_batch,
        n_ubatch=n_ubatch,
        flash_attn=False,
        use_mmap=True,
        use_mlock=mlock,
        kv_quant="q4_0",   # CPU memory bandwidth is the bottleneck — go small
    )


# ─────────────────────────────────────────────────────────────────────────────
# Size profile recommendation
# ─────────────────────────────────────────────────────────────────────────────

def _recommend_size(total_ram_gb: float, vram_gb: float, backend: AccelBackend) -> str:
    """
    Map available memory to a size profile string matching config/sizes/*.json.

    For CUDA the bottleneck is VRAM (models must fit there).
    For Apple Silicon / CPU the bottleneck is unified / system RAM.
    """
    if backend == AccelBackend.CUDA and vram_gb > 0:
        memory = vram_gb
    elif backend == AccelBackend.METAL:
        # Apple Silicon: unified memory shared between CPU and GPU
        memory = total_ram_gb
    else:
        memory = total_ram_gb

    # Thresholds tuned to the model sizes in each *.json config:
    #   tiny:   ≤3B models  → needs ~3–4 GB
    #   small:  ≤7B models  → needs ~5–8 GB
    #   medium: ≤14B models → needs ~10–16 GB
    #   large:  ≤32B models → needs ~20–26 GB
    #   max:    ≤70B models → needs ~40–48 GB
    if memory < 6:
        return "tiny"
    elif memory < 12:
        return "small"
    elif memory < 22:
        return "medium"
    elif memory < 40:
        return "large"
    else:
        return "max"


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

_cached_profile: Optional[HardwareProfile] = None
_profile_lock = threading.Lock()


def get_hardware_profile(force_refresh: bool = False) -> HardwareProfile:
    """
    Detect hardware and return an optimal HardwareProfile.

    Result is cached after the first call (detection takes ~50 ms).
    Pass force_refresh=True to re-detect (e.g. after hardware change).
    """
    global _cached_profile
    with _profile_lock:
        if _cached_profile is not None and not force_refresh:
            return _cached_profile
        _cached_profile = _build_profile()
        return _cached_profile


def _build_profile() -> HardwareProfile:
    p = HardwareProfile()
    system = platform.system()

    # ── RAM ──────────────────────────────────────────────────────────────────
    p.total_ram_gb, p.free_ram_gb = _ram_gb()

    # ── CPU cores ────────────────────────────────────────────────────────────
    p.physical_cores, p.perf_cores, p.logical_cores = _cpu_cores()

    # ── Backend detection ────────────────────────────────────────────────────
    if system == "Darwin" and platform.machine() in ("arm64", "aarch64"):
        # Apple Silicon
        chip, label = _detect_apple_chip()
        p.chip_family   = chip
        p.backend       = AccelBackend.METAL
        p.device_label  = label
        p.total_vram_gb = 0.0   # unified; share RAM figure

        params = _apple_silicon_params(chip, p.total_ram_gb, p.perf_cores)
        p.notes.append(f"Apple Silicon Metal backend — perf_cores={p.perf_cores}")

    else:
        # Try NVIDIA first
        nvidia_found, nvidia_vram, nvidia_label = _detect_nvidia()
        if nvidia_found:
            p.chip_family   = ChipFamily.NVIDIA
            p.backend       = AccelBackend.CUDA
            p.device_label  = nvidia_label
            p.total_vram_gb = nvidia_vram
            params = _nvidia_params(nvidia_vram, p.total_ram_gb, p.logical_cores)
            p.notes.append(f"NVIDIA CUDA — VRAM={nvidia_vram:.1f} GB")
        else:
            # Try AMD GPU
            amd_found, amd_label = _detect_amd_gpu()
            if amd_found:
                p.chip_family  = ChipFamily.AMD
                p.backend      = AccelBackend.ROCM
                p.device_label = amd_label
                params = _amd_gpu_params(p.total_ram_gb, p.logical_cores)
                p.notes.append("AMD ROCm GPU detected")
            else:
                # CPU-only
                machine = platform.machine().lower()
                cpu_brand = ""
                try:
                    if system == "Linux":
                        with open("/proc/cpuinfo") as f:
                            for line in f:
                                if "model name" in line:
                                    cpu_brand = line.split(":", 1)[1].strip()
                                    break
                    elif system == "Windows":
                        import winreg
                        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
                        cpu_brand = winreg.QueryValueEx(key, "ProcessorNameString")[0]
                except Exception:
                    pass

                low = cpu_brand.lower()
                if "intel" in low:
                    p.chip_family = ChipFamily.INTEL_CPU
                elif "amd" in low or "ryzen" in low:
                    p.chip_family = ChipFamily.AMD_CPU
                elif "arm" in machine or "aarch" in machine:
                    p.chip_family = ChipFamily.ARM_CPU

                p.backend      = AccelBackend.CPU
                p.device_label = cpu_brand or f"{p.physical_cores}-core CPU"
                params = _cpu_only_params(p.total_ram_gb, p.physical_cores, p.logical_cores)
                p.notes.append(f"CPU-only — {p.physical_cores} cores, {p.total_ram_gb:.1f} GB RAM")

    # ── Apply tuning params ───────────────────────────────────────────────────
    p.n_gpu_layers    = params["n_gpu_layers"]
    p.n_threads       = params["n_threads"]
    p.n_threads_batch = params["n_threads_batch"]
    p.n_batch         = params["n_batch"]
    p.n_ubatch        = params["n_ubatch"]
    p.flash_attn      = params["flash_attn"]
    p.use_mmap        = params["use_mmap"]
    p.use_mlock       = params["use_mlock"]
    p.kv_quant        = params["kv_quant"]

    # ── Context windows ───────────────────────────────────────────────────────
    # Estimate a typical model size for the recommended profile
    ctx_vals = _ctx_for_ram(p.total_ram_gb, model_size_gb=4.0, backend=p.backend)
    for key, val in ctx_vals.items():
        setattr(p, key, val)

    # ── Size profile ─────────────────────────────────────────────────────────
    p.recommended_size = _recommend_size(p.total_ram_gb, p.total_vram_gb, p.backend)

    p.notes.append(
        f"RAM={p.total_ram_gb:.1f} GB  size={p.recommended_size}  "
        f"ctx_default={p.ctx_default}  kv={p.kv_quant}  "
        f"threads={p.n_threads}  batch={p.n_batch}/{p.n_ubatch}  "
        f"flash_attn={p.flash_attn}"
    )
    return p


def apply_to_config(cfg: dict, hw: Optional[HardwareProfile] = None) -> dict:
    """
    Merge hardware-derived defaults into a loaded iris.conf dict.

    iris.conf explicit values always win — hardware profile only fills
    in keys that are absent or set to "auto".
    """
    if hw is None:
        hw = get_hardware_profile()

    def _auto_or_missing(key, fallback):
        v = cfg.get(key)
        if v is None or str(v).lower() == "auto":
            cfg[key] = fallback

    _auto_or_missing("n_gpu_layers",    hw.n_gpu_layers)
    _auto_or_missing("n_threads",       hw.n_threads)
    _auto_or_missing("n_threads_batch", hw.n_threads_batch)
    _auto_or_missing("n_batch",         hw.n_batch)
    _auto_or_missing("n_ubatch",        hw.n_ubatch)
    _auto_or_missing("flash_attn",      hw.flash_attn)
    _auto_or_missing("use_mlock",       hw.use_mlock)

    # Context allocation
    # Keep it as "auto" so that load_model can apply role-specific ceilings instead of a flat default.

    # Size profile (only if not explicitly set)
    if cfg.get("size", "auto") in ("auto", "", None):
        cfg["size"] = hw.recommended_size

    # KV quant: only override if compressed_attention.kv_quant is "auto"
    ca = cfg.setdefault("compressed_attention", {})
    if ca.get("kv_quant", "auto").lower() == "auto":
        ca["kv_quant"] = hw.kv_quant

    return cfg


def ctx_for_role(role_name: str, hw: Optional[HardwareProfile] = None) -> int:
    """Return the optimal n_ctx for a given role string, e.g. 'code', 'triage'."""
    if hw is None:
        hw = get_hardware_profile()
    mapping = {
        "triage":    hw.ctx_triage,
        "router":    hw.ctx_triage,
        "control":   hw.ctx_control,
        "math":      hw.ctx_math,
        "code":      hw.ctx_code,
        "reasoning": hw.ctx_reasoning,
        "reviewer":  hw.ctx_reasoning,
        "general":   hw.ctx_general,
        "vision":    hw.ctx_vision,
    }
    return mapping.get(role_name, hw.ctx_default)


def summary() -> str:
    """Human-readable one-liner for logging."""
    hw = get_hardware_profile()
    return (
        f"[HW] {hw.device_label} | {hw.backend.value.upper()} | "
        f"RAM={hw.total_ram_gb:.1f}GB | size={hw.recommended_size} | "
        f"ctx={hw.ctx_default} | kv={hw.kv_quant} | "
        f"threads={hw.n_threads} | batch={hw.n_batch}/{hw.n_ubatch} | "
        f"flash={hw.flash_attn}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLI: python -m src.hardware_profile
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    hw = get_hardware_profile()
    print(summary())
    print()
    print(json.dumps({
        "device":        hw.device_label,
        "backend":       hw.backend.value,
        "chip_family":   hw.chip_family.value,
        "total_ram_gb":  round(hw.total_ram_gb, 1),
        "total_vram_gb": round(hw.total_vram_gb, 1),
        "physical_cores":  hw.physical_cores,
        "perf_cores":      hw.perf_cores,
        "recommended_size": hw.recommended_size,
        "n_gpu_layers":    hw.n_gpu_layers,
        "n_threads":       hw.n_threads,
        "n_threads_batch": hw.n_threads_batch,
        "n_batch":         hw.n_batch,
        "n_ubatch":        hw.n_ubatch,
        "flash_attn":      hw.flash_attn,
        "use_mlock":       hw.use_mlock,
        "kv_quant":        hw.kv_quant,
        "ctx_triage":      hw.ctx_triage,
        "ctx_code":        hw.ctx_code,
        "ctx_reasoning":   hw.ctx_reasoning,
        "ctx_default":     hw.ctx_default,
        "notes":           hw.notes,
    }, indent=2))
