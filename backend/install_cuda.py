"""
CUDA Fix for faster-whisper on Windows
Run this to fix cublas64_12.dll errors
"""

import os
import subprocess
import sys
import shutil
import zipfile
import urllib.request
import tempfile

def get_cuda_version():
    """Check CUDA version from nvidia-smi"""
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if 'CUDA Version:' in line:
                version = line.split('CUDA Version:')[1].strip().split('.')[0]
                return f"CUDA {version}"
        return "Unknown"
    except:
        return "Unknown"

def find_cuda_bin():
    """Find CUDA bin directory"""
    candidates = []
    
    # Check CUDA_PATH env var
    cuda_path = os.environ.get('CUDA_PATH')
    if cuda_path:
        candidates.append(os.path.join(cuda_path, 'bin'))
    
    # Check Program Files
    base = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if os.path.isdir(base):
        for d in os.listdir(base):
            if d.startswith('v'):
                candidates.append(os.path.join(base, d, 'bin'))
    
    # Find the highest version
    for candidate in reversed(sorted(candidates)):
        if os.path.isdir(candidate):
            return candidate
    
    return None

def download_and_install_libs():
    """Download cuBLAS + cuDNN libs and install to CUDA bin"""
    
    cuda_bin = find_cuda_bin()
    if not cuda_bin:
        print("❌ Could not find CUDA bin directory!")
        print("   Please install CUDA from: https://developer.nvidia.com/cuda-downloads")
        return False
    
    print(f"📁 CUDA bin: {cuda_bin}")
    
    # Download the DLLs package
    url = "https://github.com/Purfview/whisper-standalone-win/releases/download/libs/cuBLAS.and.cuDNN_CUDA12_win_v2.7z"
    
    temp_dir = tempfile.mkdtemp()
    archive_path = os.path.join(temp_dir, "cuBLAS.7z")
    extract_dir = os.path.join(temp_dir, "extracted")
    
    print(f"\n📥 Downloading CUDA libraries from Purfview's repo...")
    print(f"   URL: {url}")
    
    try:
        urllib.request.urlretrieve(url, archive_path)
    except Exception as e:
        print(f"❌ Download failed: {e}")
        print("\n💡 Alternative: Manually download from:")
        print("   https://github.com/Purfview/whisper-standalone-win/releases/tag/libs")
        return False
    
    print(f"✅ Downloaded to: {archive_path}")
    print("\n📦 Extracting...")
    
    try:
        import py7zr
        with py7zr.SevenZipFile(archive_path, 'r') as archive:
            archive.extractall(extract_dir)
    except ImportError:
        print("Installing py7zr...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'py7zr'], check=True)
        import py7zr
        with py7zr.SevenZipFile(archive_path, 'r') as archive:
            archive.extractall(extract_dir)
    
    print(f"✅ Extracted to: {extract_dir}")
    
    # Copy DLLs to CUDA bin
    copied = 0
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith('.dll'):
                src = os.path.join(root, file)
                dst = os.path.join(cuda_bin, file)
                
                # Don't overwrite existing files (keep newer versions)
                if os.path.exists(dst):
                    continue
                
                try:
                    shutil.copy2(src, dst)
                    copied += 1
                    print(f"   📋 Copied: {file}")
                except Exception as e:
                    print(f"   ⚠️  Could not copy {file}: {e}")
    
    print(f"\n✅ Copied {copied} new DLLs to {cuda_bin}")
    
    # Cleanup
    try:
        shutil.rmtree(temp_dir)
    except:
        pass
    
    return True

def check_ctranslate2():
    """Check ctranslate2 version"""
    try:
        import ctranslate2
        print(f"\n📦 ctranslate2 version: {ctranslate2.__version__}")
    except:
        print("\n⚠️  ctranslate2 not installed")

def main():
    print("╔══════════════════════════════════════════════════════╗")
    print("║         J.A.R.V.I.S CUDA Setup for faster-whisper    ║")
    print("╚══════════════════════════════════════════════════════╝")
    
    # Check CUDA version
    cuda_version = get_cuda_version()
    print(f"\n🔍 Your GPU CUDA version: {cuda_version}")
    
    # Find CUDA bin
    cuda_bin = find_cuda_bin()
    if cuda_bin:
        print(f"📁 CUDA bin directory: {cuda_bin}")
        
        # Check if cublas64_12.dll exists
        cublas_path = os.path.join(cuda_bin, 'cublas64_12.dll')
        if os.path.exists(cublas_path):
            print(f"✅ cublas64_12.dll already exists!")
        else:
            print(f"❌ cublas64_12.dll NOT found")
            print("\n🚀 Installing CUDA libraries...")
            download_and_install_libs()
    else:
        print("❌ CUDA not found!")
        print("\n📥 Please install CUDA:")
        print("   https://developer.nvidia.com/cuda-downloads")
    
    check_ctranslate2()
    
    print("\n" + "="*50)
    print("✅ CUDA setup complete!")
    print("\n📋 Next steps:")
    print("   1. Restart Python (or restart the JARVIS backend)")
    print("   2. The wake word should now use GPU acceleration")
    print("   3. If still issues, try: pip install --force-reinstall ctranslate2")
    print("="*50)

if __name__ == "__main__":
    main()