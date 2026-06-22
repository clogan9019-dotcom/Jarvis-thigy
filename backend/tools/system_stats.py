"""
System Stats Tool - Reads CPU, RAM, GPU, Disk, Network usage locally.
No API keys needed. Uses psutil + GPUtil (NVIDIA).
"""
import json
import time


def get_system_stats() -> dict:
    """
    Return current PC hardware usage stats.
    CPU, RAM, GPU (NVIDIA), disk, network, top processes.
    """
    stats = {}

    # ── CPU ──────────────────────────────────────────────────────────────────
    try:
        import psutil
        stats["cpu"] = {
            "percent": psutil.cpu_percent(interval=0.5),
            "cores_logical": psutil.cpu_count(logical=True),
            "cores_physical": psutil.cpu_count(logical=False),
            "freq_mhz": round(psutil.cpu_freq().current, 1) if psutil.cpu_freq() else None,
            "per_core_percent": psutil.cpu_percent(interval=0, percpu=True),
        }
    except Exception as e:
        stats["cpu"] = {"error": str(e)}

    # ── RAM ──────────────────────────────────────────────────────────────────
    try:
        import psutil
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        stats["ram"] = {
            "total_gb":     round(vm.total / 1e9, 2),
            "used_gb":      round(vm.used  / 1e9, 2),
            "available_gb": round(vm.available / 1e9, 2),
            "percent":      vm.percent,
            "swap_used_gb": round(sw.used / 1e9, 2),
            "swap_total_gb":round(sw.total / 1e9, 2),
        }
    except Exception as e:
        stats["ram"] = {"error": str(e)}

    # ── GPU (tries pynvml → GPUtil → nvidia-smi subprocess) ──────────────────
      try:
          import pynvml
          pynvml.nvmlInit()
          count = pynvml.nvmlDeviceGetCount()
          gpus = []
          for i in range(count):
              h = pynvml.nvmlDeviceGetHandleByIndex(i)
              mem = pynvml.nvmlDeviceGetMemoryInfo(h)
              util = pynvml.nvmlDeviceGetUtilizationRates(h)
              try:
                  temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
              except Exception:
                  temp = None
              name = pynvml.nvmlDeviceGetName(h)
              if isinstance(name, bytes):
                  name = name.decode()
              gpus.append({
                  "name":          name,
                  "load_percent":  util.gpu,
                  "vram_used_mb":  round(mem.used  / 1_048_576, 1),
                  "vram_total_mb": round(mem.total / 1_048_576, 1),
                  "vram_free_mb":  round(mem.free  / 1_048_576, 1),
                  "temp_c":        temp,
              })
          pynvml.nvmlShutdown()
          stats["gpu"] = gpus
      except Exception:
          # ── GPUtil fallback ──────────────────────────────────────────────────
          try:
              import GPUtil
              gpus = GPUtil.getGPUs()
              stats["gpu"] = [
                  {
                      "name":          g.name,
                      "load_percent":  round(g.load * 100, 1),
                      "vram_used_mb":  round(g.memoryUsed, 1),
                      "vram_total_mb": round(g.memoryTotal, 1),
                      "vram_free_mb":  round(g.memoryFree, 1),
                      "temp_c":        g.temperature,
                  }
                  for g in gpus
              ] if gpus else []
          except Exception:
              # ── nvidia-smi subprocess fallback (always works if drivers installed) ──
              try:
                  import subprocess as _sp
                  fields = "name,utilization.gpu,memory.used,memory.total,memory.free,temperature.gpu"
                  out = _sp.check_output(
                      ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                      timeout=5, text=True
                  )
                  gpus = []
                  for line in out.strip().splitlines():
                      parts = [p.strip() for p in line.split(",")]
                      if len(parts) >= 6:
                          gpus.append({
                              "name":          parts[0],
                              "load_percent":  float(parts[1]) if parts[1] != "[N/A]" else None,
                              "vram_used_mb":  float(parts[2]) if parts[2] != "[N/A]" else None,
                              "vram_total_mb": float(parts[3]) if parts[3] != "[N/A]" else None,
                              "vram_free_mb":  float(parts[4]) if parts[4] != "[N/A]" else None,
                              "temp_c":        float(parts[5]) if parts[5] != "[N/A]" else None,
                          })
                  stats["gpu"] = gpus
              except Exception as e:
                  stats["gpu"] = {"error": f"nvidia-smi failed: {e}"}

      # ── Disk ─────────────────────────────────────────────────────────────────
    try:
        import psutil
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device":     part.device,
                    "mountpoint": part.mountpoint,
                    "fstype":     part.fstype,
                    "total_gb":   round(usage.total / 1e9, 2),
                    "used_gb":    round(usage.used  / 1e9, 2),
                    "free_gb":    round(usage.free  / 1e9, 2),
                    "percent":    usage.percent,
                })
            except Exception:
                pass
        stats["disk"] = disks
    except Exception as e:
        stats["disk"] = {"error": str(e)}

    # ── Network ───────────────────────────────────────────────────────────────
    try:
        import psutil
        net1 = psutil.net_io_counters()
        time.sleep(0.5)
        net2 = psutil.net_io_counters()
        stats["network"] = {
            "bytes_sent_total_mb":  round(net2.bytes_sent / 1e6, 2),
            "bytes_recv_total_mb":  round(net2.bytes_recv / 1e6, 2),
            "send_speed_kbps":      round((net2.bytes_sent - net1.bytes_sent) / 1e3 / 0.5, 1),
            "recv_speed_kbps":      round((net2.bytes_recv - net1.bytes_recv) / 1e3 / 0.5, 1),
        }
    except Exception as e:
        stats["network"] = {"error": str(e)}

    # ── Top CPU processes ─────────────────────────────────────────────────────
    try:
        import psutil
        procs = []
        for p in sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
            key=lambda x: x.info.get("cpu_percent") or 0,
            reverse=True
        )[:8]:
            procs.append({
                "pid":     p.info["pid"],
                "name":    p.info["name"],
                "cpu_pct": round(p.info.get("cpu_percent") or 0, 1),
                "mem_pct": round(p.info.get("memory_percent") or 0, 2),
            })
        stats["top_processes"] = procs
    except Exception as e:
        stats["top_processes"] = {"error": str(e)}

    stats["ok"] = True
    return stats


def get_system_summary() -> str:
    """Return a human-readable one-line summary of current system load."""
    s = get_system_stats()
    parts = []
    if "cpu" in s and "percent" in s["cpu"]:
        parts.append(f"CPU {s['cpu']['percent']}%")
    if "ram" in s and "percent" in s["ram"]:
        parts.append(f"RAM {s['ram']['percent']}% ({s['ram']['used_gb']}/{s['ram']['total_gb']} GB)")
    if isinstance(s.get("gpu"), list) and s["gpu"]:
        g = s["gpu"][0]
        parts.append(f"GPU {g.get('load_percent',0)}% VRAM {g.get('vram_used_mb',0)}/{g.get('vram_total_mb',0)} MB {g.get('temp_c','?')}°C")
    if isinstance(s.get("disk"), list) and s["disk"]:
        d = s["disk"][0]
        parts.append(f"Disk C: {d.get('percent',0)}% ({d.get('used_gb',0)}/{d.get('total_gb',0)} GB)")
    return " | ".join(parts) if parts else "Stats unavailable"
