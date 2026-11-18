import base64
import os
import sys

# Default Mantra MFS100 Driver DLL path on Windows
MANTRA_DLL_DIR = r"C:\Program Files\Mantra\MFS100\Driver\MFS100Test"
MANTRA_DLL_PATH = os.path.join(MANTRA_DLL_DIR, "MANTRA.MFS100.dll")

MFS100_AVAILABLE = False
MFS100 = None
FingerData = None

if sys.platform == "win32" and os.path.exists(MANTRA_DLL_PATH):
    try:
        if MANTRA_DLL_DIR not in os.environ.get("PATH", ""):
            os.environ["PATH"] = MANTRA_DLL_DIR + os.pathsep + os.environ.get("PATH", "")
        import clr
        clr.AddReference(MANTRA_DLL_PATH)
        from MANTRA import MFS100, FingerData  # type: ignore
        MFS100_AVAILABLE = True
    except Exception:
        MFS100_AVAILABLE = False


def _run_autocapture(scanner, timeout_ms=10000):
    """
    MANTRA.MFS100.dll ke C# 'out FingerData' signature ke hisaab se AutoCapture call karta hai.
    Returns: (ret_code, finger_data)
    """
    # Standard MANTRA.MFS100.dll signature: int AutoCapture(out FingerData, int Timeout, bool ShowPreview)
    try:
        res = scanner.AutoCapture(None, timeout_ms, True)
        if isinstance(res, tuple):
            return int(res[0]), res[1]
    except TypeError:
        pass

    # Fallback signature: int AutoCapture(ref FingerData, int Timeout, bool ShowPreview, bool DetectFinger)
    try:
        fd = FingerData() if FingerData is not None else None
        res = scanner.AutoCapture(fd, timeout_ms, True, True)
        if isinstance(res, tuple):
            return int(res[0]), res[1]
    except TypeError:
        pass

    # Fallback signature: int AutoCapture(out FingerData, int Timeout, bool ShowPreview, bool DetectFinger)
    res = scanner.AutoCapture(None, timeout_ms, True, True)
    if isinstance(res, tuple):
        return int(res[0]), res[1]
    return -1, None


def _run_match_iso(scanner, stored_bytes, live_bytes):
    """
    MANTRA.MFS100.dll ke C# 'out int Score' signature ke hisaab se MatchISO call karta hai.
    Returns: (ret_code, score)
    """
    # Standard signature: int MatchISO(byte[] FirstTemplate, byte[] SecondTemplate, out int Score)
    try:
        res = scanner.MatchISO(stored_bytes, live_bytes, 0)
        if isinstance(res, tuple):
            return int(res[0]), int(res[1])
    except TypeError:
        pass

    # Fallback signature: int MatchISO(byte[] FirstTemplate, byte[] SecondTemplate)
    res = scanner.MatchISO(stored_bytes, live_bytes)
    if isinstance(res, tuple):
        return int(res[0]), int(res[1])
    return 0, int(res)


def capture_mfs100_fingerprint(quality=60, timeout_ms=10000):
    """
    Mantra MFS100 USB scanner se live fingerprint capture karke Base64 ISO template return karta hai.
    Returns: (iso_b64, quality_score, error_message)
    """
    if sys.platform != "win32":
        return None, 0, "Mantra MFS100 USB scanner sirf local Windows PC par support karta hai (Cloud par Face ID use karein)."

    if not MFS100_AVAILABLE or MFS100 is None:
        return None, 0, f"MANTRA.MFS100.dll nahi mili ({MANTRA_DLL_PATH}). Mantra Driver check karein."

    scanner = None
    try:
        scanner = MFS100()
        init_ret = scanner.Init()
        if init_ret != 0:
            err_msg = scanner.GetErrorMsg(init_ret)
            return None, 0, f"Scanner Init Failed ({init_ret}): {err_msg}"

        if not scanner.IsConnected():
            return None, 0, "Mantra MFS100 device USB se connected nahi hai!"

        ret, finger_data = _run_autocapture(scanner, timeout_ms=timeout_ms)
        if ret != 0 or finger_data is None:
            err_msg = scanner.GetErrorMsg(ret)
            return None, 0, f"Fingerprint capture failed ({ret}): {err_msg}"

        cap_quality = int(finger_data.Quality)
        if cap_quality < quality:
            return None, cap_quality, f"Fingerprint quality kam hai ({cap_quality}%). Ungli saaf karke dobara rakhein (Min: {quality}%)."

        iso_bytes = bytes(finger_data.ISOTemplate)
        iso_b64 = base64.b64encode(iso_bytes).decode("utf-8")
        return iso_b64, cap_quality, None

    except Exception as e:
        return None, 0, f"MFS100 Hardware Error: {str(e)}"
    finally:
        if scanner is not None:
            try:
                scanner.Uninit()
            except Exception:
                pass


def verify_mfs100_fingerprint(stored_iso_b64, match_threshold=1400):
    """
    Live finger scan karke database mein saved ISO template se match score check karta hai.
    Returns: (is_match, score, error_message)
    """
    if not stored_iso_b64:
        return False, 0, "Is student ka Fingerprint registered nahi hai. Pehle Fingerprint Register karein."

    if sys.platform != "win32" or not MFS100_AVAILABLE or MFS100 is None:
        return False, 0, "Mantra MFS100 hardware local Windows machine par available nahi hai."

    scanner = None
    try:
        stored_bytes = base64.b64decode(stored_iso_b64)
        scanner = MFS100()
        init_ret = scanner.Init()
        if init_ret != 0:
            return False, 0, f"Scanner Init Failed: {scanner.GetErrorMsg(init_ret)}"

        if not scanner.IsConnected():
            return False, 0, "Mantra MFS100 USB se connected nahi hai."

        ret, finger_data = _run_autocapture(scanner, timeout_ms=10000)
        if ret != 0 or finger_data is None:
            return False, 0, f"Finger scan failed: {scanner.GetErrorMsg(ret)}"

        live_bytes = bytes(finger_data.ISOTemplate)
        match_ret, score = _run_match_iso(scanner, stored_bytes, live_bytes)
        if match_ret != 0:
            return False, 0, f"ISO Match Error: {scanner.GetErrorMsg(match_ret)}"

        if score < match_threshold:
            return False, score, f"Fingerprint match nahi hua (Score: {score}, Required: {match_threshold})."

        return True, score, None

    except Exception as e:
        return False, 0, f"Fingerprint Verification Error: {str(e)}"
    finally:
        if scanner is not None:
            try:
                scanner.Uninit()
            except Exception:
                pass