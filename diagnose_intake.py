"""
diagnose_intake.py
Run this from your restiq/ project root:  python diagnose_intake.py

It inspects agents/intake.py (and cleans up __pycache__) to find out
exactly why Python is throwing 'cannot contain null bytes'.
"""
import os
import shutil
import sys

TARGET = os.path.join("agents", "intake.py")

def main():
    if not os.path.exists(TARGET):
        print(f"❌ Could not find {TARGET} relative to current directory: {os.getcwd()}")
        print("   Run this script from your restiq/ project root.")
        sys.exit(1)

    raw = open(TARGET, "rb").read()
    print(f"File: {TARGET}")
    print(f"Size on disk: {len(raw)} bytes")

    null_count = raw.count(b"\x00")
    print(f"Null byte count: {null_count}")

    if null_count > 0:
        first_idx = raw.index(b"\x00")
        print(f"⚠️  First null byte at offset {first_idx}.")
        print(f"   Context: {raw[max(0,first_idx-30):first_idx+30]!r}")
        # Detect UTF-16 pattern (alternating null bytes is classic UTF-16)
        even_nulls = sum(1 for i in range(0, len(raw), 2) if raw[i:i+1] == b"\x00")
        odd_nulls = sum(1 for i in range(1, len(raw), 2) if raw[i:i+1] == b"\x00")
        if even_nulls > len(raw) * 0.3 or odd_nulls > len(raw) * 0.3:
            print("   👉 Pattern strongly suggests this file is saved as UTF-16, not UTF-8.")
            print("      Your editor is silently auto-detecting and displaying it fine,")
            print("      but Python's default UTF-8 source reading chokes on it.")
    else:
        print("✅ No null bytes found in the raw file on disk.")

    # Check BOM
    if raw[:3] == b"\xef\xbb\xbf":
        print("ℹ️  File has a UTF-8 BOM at the start.")
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        print("⚠️  File starts with a UTF-16 BOM (\\xff\\xfe or \\xfe\\xff).")
        print("    This IS your bug. Re-save the file as UTF-8 (no BOM).")

    # Check line endings
    crlf = raw.count(b"\r\n")
    lf_only = raw.count(b"\n") - crlf
    print(f"CRLF line endings: {crlf}, bare LF: {lf_only}")

    # Check __pycache__ for stale/corrupt bytecode
    cache_dir = os.path.join("agents", "__pycache__")
    if os.path.isdir(cache_dir):
        stale = [f for f in os.listdir(cache_dir) if f.startswith("intake.")]
        if stale:
            print(f"⚠️  Found cached bytecode: {stale}")
            print("   Deleting __pycache__ to rule out a corrupted .pyc as the cause...")
            shutil.rmtree(cache_dir)
            print("   Done. Try running your program again.")
        else:
            print("No cached intake bytecode found.")
    else:
        print("No __pycache__ directory present yet.")

    # Try the actual parse Python would do
    print("\nAttempting compile() exactly as the interpreter would...")
    try:
        text = raw.decode("utf-8")
        compile(text, TARGET, "exec")
        print("✅ compile() succeeded — file parses cleanly as UTF-8 text.")
    except SyntaxError as e:
        print(f"❌ SyntaxError reproduced: {e}")
    except UnicodeDecodeError as e:
        print(f"❌ UnicodeDecodeError: {e}")
        print("   This confirms the file is NOT valid UTF-8 — likely UTF-16 or corrupted.")

if __name__ == "__main__":
    main()