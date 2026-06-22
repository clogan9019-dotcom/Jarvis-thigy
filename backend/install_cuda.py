"""
CUDA Fix for faster-whisper on Windows
Run this to fix cublas64_12.dll errors
"""

import os
import subprocess
import sys
import shutil
import urllib.request
import tempfile
import glob

def get_cuda_version():
    """Check CUDA version from nvidia-smi"""
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if 'CUDA Version:' in line:
                return line.split('CUDA Version:')[1].strip().split('.')[0]
        return "Unknown"
    except:
        return "Unknown"

def find_cuda_bin():
    """Find CUDA bin directory"""
    candidates = []
    
    cuda_path = os.environ.get('CUDA_PATH')
    if cuda_path:
        candidates.append(os.path.join(cuda_path, 'bin'))
    
    base = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if os.path.isdir(base):
        for d in os.listdir(base):
            if d.startswith('v'):
                candidates.append(os.path.join(base, d, 'bin'))
    
    for candidate in reversed(sorted(candidates)):
        if os.path.isdir(candidate):
            return candidate
    
    return None

def find_7z_exe():
    """Find 7-zip executable"""
    # Check common locations
    paths = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    
    # Check PATH
    try:
        result = subprocess.run(['where', '7z'], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().split('\n')[0]
    except:
        pass
    
    return None

def extract_with_7z(archive, output_dir):
    """Extract using 7-zip command line"""
    seven_zip = find_7z_exe()
    if not seven_zip:
        return False, "7-zip not found"
    
    try:
        result = subprocess.run(
            [seven_zip, 'x', archive, f'-o{output_dir}', '-y'],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            return True, "Success"
        else:
            return False, result.stderr
    except Exception as e:
        return False, str(e)

def extract_with_zipfile(archive, output_dir):
    """Try to extract what we can with Python's zipfile"""
    # The .7z might contain a .zip inside
    try:
        import zipfile
        with zipfile.ZipFile(archive, 'r') as zf:
            zf.extractall(output_dir)
        return True, "zipfile"
    except:
        pass
    
    # Try other Python libraries
    for lib_name, extractor in [
        ('py7zr', lambda a, d: _extract_py7zr(a, d)),
    ]:
        try:
            __import__(lib_name)
            success, msg = extractor(archive, output_dir)
            if success:
                return True, msg
        except ImportError:
            continue
    
    return False, "No extractor available"

def _extract_py7zr(archive, output_dir):
    """Extract using py7zr"""
    try:
        import py7zr
        # Check for BCJ2 compression
        with py7zr.SevenZipFile(archive, 'r') as archive:
            names = archive.getnames()
            # Filter out files that would need BCJ2
            safe_files = [n for n in names if not _needs_bcj2(n)]
            
            if len(safe_files) < len(names):
                print(f"   ⚠️  Some files require unsupported BCJ2 compression")
                print(f"   📁 Extracting {len(safe_files)} of {len(names)} files")
            
            for name in safe_files:
                archive.extract(target=os.path.join(output_dir, name))
        
        return True, "py7zr (partial)"
    except Exception as e:
        return False, str(e)

def _needs_bcj2(filename):
    """Check if file likely needs BCJ2 compression"""
    # BCJ2 is typically used for .exe files in 7z archives
    ext = os.path.splitext(filename)[1].lower()
    return ext in ['.exe', '.dll']

def download_and_install_libs():
    """Download cuBLAS + cuDNN libs and install to CUDA bin"""
    
    cuda_bin = find_cuda_bin()
    if not cuda_bin:
        print("❌ Could not find CUDA bin directory!")
        print("   Please install CUDA from: https://developer.nvidia.com/cuda-downloads")
        return False
    
    print(f"📁 CUDA bin: {cuda_bin}")
    
    # Try 7-zip first
    seven_zip = find_7z_exe()
    if seven_zip:
        print(f"✅ Found 7-zip at: {seven_zip}")
        use_7z = True
    else:
        print("⚠️  7-zip not found - will try Python extraction")
        use_7z = False
    
    temp_dir = tempfile.mkdtemp()
    archive_path = os.path.join(temp_dir, "cuBLAS.7z")
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    
    url = "https://github.com/Purfview/whisper-standalone-win/releases/download/libs/cuBLAS.and.cuDNN_CUDA12_win_v2.7z"
    
    print(f"\n📥 Downloading CUDA libraries...")
    print(f"   URL: {url}")
    print(f"   (This is ~500MB, may take a minute)")
    
    try:
        # Use urllib with progress
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        urllib.request.urlretrieve(url, archive_path)
    except Exception as e:
        print(f"❌ Download failed: {e}")
        print("\n💡 Manual download:")
        print("   1. Go to: https://github.com/Purfview/whisper-standalone-win/releases/tag/libs")
        print("   2. Download: cuBLAS.and.cuDNN_CUDA12_win_v2.7z")
        print("   3. Extract to: C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v13.3\\bin\\")
        return False
    
    print(f"✅ Downloaded ({os.path.getsize(archive_path) // (1024*1024)} MB)")
    
    # Extract
    print("\n📦 Extracting...")
    
    if use_7z:
        success, msg = extract_with_7z(archive_path, extract_dir)
        if success:
            print(f"✅ Extracted with 7-zip")
        else:
            print(f"⚠️  7-zip failed: {msg}")
            use_7z = False
    
    if not use_7z:
        success, msg = extract_with_zipfile(archive_path, extract_dir)
        if success:
            print(f"✅ Extracted with Python ({msg})")
        else:
            print(f"❌ Extraction failed: {msg}")
            print("\n💡 Please install 7-zip from: https://7-zip.org")
            print("   Then run: 7z x cuBLAS.7z -oextracted")
            return False
    
    # List extracted files
    dll_files = []
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith('.dll'):
                dll_files.append(os.path.join(root, file))
    
    print(f"📁 Found {len(dll_files)} DLL files")
    
    # Copy to CUDA bin
    copied = 0
    skipped = 0
    for dll_path in dll_files:
        filename = os.path.basename(dll_path)
        dst = os.path.join(cuda_bin, filename)
        
        if os.path.exists(dst):
            skipped += 1
            continue
        
        try:
            shutil.copy2(dll_path, dst)
            copied += 1
            print(f"   ✅ {filename}")
        except Exception as e:
            print(f"   ⚠️  Failed: {filename} - {e}")
    
    print(f"\n✅ Installed {copied} new DLLs")
    print(f"   ⏭️  Skipped {skipped} existing files")
    print(f"   📁 Destination: {cuda_bin}")
    
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
    
    cuda_version = get_cuda_version()
    print(f"\n🔍 Your GPU CUDA version: {cuda_version}")
    
    cuda_bin = find_cuda_bin()
    if cuda_bin:
        print(f"📁 CUDA bin directory: {cuda_bin}")
        
        cublas_path = os.path.join(cuda_bin, 'cublas64_12.dll')
        if os.path.exists(cublas_path):
            print(f"✅ cublas64_12.dll already exists!")
            print(f"\n✨ CUDA should work! Restart the backend:")
            print(f"   python main.py")
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
    print("   3. If still issues, run: python main.py")
    print("="*50)

if __name__ == "__main__":
    main()