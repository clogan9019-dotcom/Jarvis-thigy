"""
  System Stats Tool - CPU, RAM, GPU, Disk, Network usage. No API keys needed.
  """
  import time


  def get_system_stats() -> dict:
      """Return current PC hardware usage stats."""
      stats = {"ok": True}

      # CPU
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

      # RAM
      try:
          import psutil
          vm = psutil.virtual_memory()
          sw = psutil.swap_memory()
          stats["ram"] = {
              "total_gb": round(vm.total / 1e9, 2),
              "used_gb": round(vm.used / 1e9, 2),
              "available_gb": round(vm.available / 1e9, 2),
              "percent": vm.percent,
              "swap_used_gb": round(sw.used / 1e9, 2),
              "swap_total_gb": round(sw.total / 1e9, 2),
          }
      except Exception as e:
          stats["ram"] = {"error": str(e)}

      # GPU — tries pynvml, then GPUtil, then nvidia-smi subprocess
      gpu_ok = False

      if not gpu_ok:
          try:
              import pynvml
              pynvml.nvmlInit()
              gpus = []
              for i in range(pynvml.nvmlDeviceGetCount()):
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
                      "name": name,
                      "load_percent": util.gpu,
                      "vram_used_mb": round(mem.used / 1_048_576, 1),
                      "vram_total_mb": round(mem.total / 1_048_576, 1),
                      "vram_free_mb": round(mem.free / 1_048_576, 1),
                      "temp_c": temp,
                  })
              pynvml.nvmlShutdown()
              stats["gpu"] = gpus
              gpu_ok = True
          except Exception:
              pass

      if not gpu_ok:
          try:
              import GPUtil
              gpus = GPUtil.getGPUs()
              stats["gpu"] = [
                  {
                      "name": g.name,
                      "load_percent": round(g.load * 100, 1),
                      "vram_used_mb": round(g.memoryUsed, 1),
                      "vram_total_mb": round(g.memoryTotal, 1),
                      "vram_free_mb": round(g.memoryFree, 1),
                      "temp_c": g.temperature,
                  }
                  for g in gpus
              ]
              gpu_ok = True
          except Exception:
              pass

      if not gpu_ok:
          try:
              import subprocess
              fields = "name,utilization.gpu,memory.used,memory.total,memory.free,temperature.gpu"
              out = subprocess.check_output(
                  ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                  timeout=5, text=True
              )
              gpus = []
              for line in out.strip().splitlines():
                  parts = [p.strip() for p in line.split(",")]
                  if len(parts) >= 6:
                      def _f(v):
                          try:
                              return float(v)
                          except Exception:
                              return None
                      gpus.append({
                          "name": parts[0],
                          "load_percent": _f(parts[1]),
                          "vram_used_mb": _f(parts[2]),
                          "vram_total_mb": _f(parts[3]),
                          "vram_free_mb": _f(parts[4]),
                          "temp_c": _f(parts[5]),
                      })
              stats["gpu"] = gpus
              gpu_ok = True
          except Exception as e:
              stats["gpu"] = {"error": f"All GPU methods failed: {e}"}

      # Disk
      try:
          import psutil
          disks = []
          for part in psutil.disk_partitions(all=False):
              try:
                  usage = psutil.disk_usage(part.mountpoint)
                  disks.append({
                      "device": part.device,
                      "mountpoint": part.mountpoint,
                      "total_gb": round(usage.total / 1e9, 2),
                      "used_gb": round(usage.used / 1e9, 2),
                      "free_gb": round(usage.free / 1e9, 2),
                      "percent": usage.percent,
                  })
              except Exception:
                  pass
          stats["disk"] = disks
      except Exception as e:
          stats["disk"] = {"error": str(e)}

      # Network speed (sample over 0.5s)
      try:
          import psutil
          net1 = psutil.net_io_counters()
          time.sleep(0.5)
          net2 = psutil.net_io_counters()
          stats["network"] = {
              "send_speed_kbps": round((net2.bytes_sent - net1.bytes_sent) / 1e3 / 0.5, 1),
              "recv_speed_kbps": round((net2.bytes_recv - net1.bytes_recv) / 1e3 / 0.5, 1),
              "bytes_sent_total_mb": round(net2.bytes_sent / 1e6, 2),
              "bytes_recv_total_mb": round(net2.bytes_recv / 1e6, 2),
          }
      except Exception as e:
          stats["network"] = {"error": str(e)}

      # Top CPU processes
      try:
          import psutil
          procs = sorted(
              psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
              key=lambda p: p.info.get("cpu_percent") or 0,
              reverse=True
          )[:8]
          stats["top_processes"] = [
              {
                  "pid": p.info["pid"],
                  "name": p.info["name"],
                  "cpu_pct": round(p.info.get("cpu_percent") or 0, 1),
                  "mem_pct": round(p.info.get("memory_percent") or 0, 2),
              }
              for p in procs
          ]
      except Exception as e:
          stats["top_processes"] = {"error": str(e)}

      return stats


  def get_system_summary() -> str:
      """One-line summary of current system load."""
      s = get_system_stats()
      parts = []
      if "percent" in s.get("cpu", {}):
          parts.append(f"CPU {s['cpu']['percent']}%")
      if "percent" in s.get("ram", {}):
          parts.append(f"RAM {s['ram']['percent']}% ({s['ram']['used_gb']}/{s['ram']['total_gb']} GB)")
      gpu = s.get("gpu")
      if isinstance(gpu, list) and gpu:
          g = gpu[0]
          parts.append(f"GPU {g.get('load_percent', 0)}% | VRAM {g.get('vram_used_mb', 0)}/{g.get('vram_total_mb', 0)} MB | {g.get('temp_c', '?')}°C")
      disk = s.get("disk")
      if isinstance(disk, list) and disk:
          d = disk[0]
          parts.append(f"Disk {d.get('percent', 0)}% ({d.get('used_gb', 0)}/{d.get('total_gb', 0)} GB)")
      return " | ".join(parts) if parts else "Stats unavailable"
  