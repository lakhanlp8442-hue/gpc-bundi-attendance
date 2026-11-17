import base64
import math
from urllib.parse import quote
import cv2
import numpy as np
from django.conf import settings


def decode_base64_image(base64_str):
    if ',' in base64_str:
        base64_str = base64_str.split(',', 1)[1]
    img_bytes = base64.b64decode(base64_str)
    np_arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    return img


def auto_crop_face_region(img):
    """
    YCrCb skin-tone clustering + center bias se chehre ka exact bounding box nikalta hai.
    Kisi external Haar XML ya ONNX model par depend nahi karta (100% offline & instant).
    """
    h_img, w_img = img.shape[:2]
    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)

    # Human skin color range in YCrCb (works across all Indian skin tones & lighting)
    lower_skin = np.array([0, 130, 75], dtype=np.uint8)
    upper_skin = np.array([255, 178, 132], dtype=np.uint8)
    skin_mask = cv2.inRange(ycrcb, lower_skin, upper_skin)

    # Noise clean karo
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel)
    skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        best_cnt = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(best_cnt)
        if area > (w_img * h_img * 0.03):
            x, y, w, h = cv2.boundingRect(best_cnt)
            if h > int(w * 1.35):
                h = int(w * 1.25)
            pad_x = int(w * 0.08)
            pad_y = int(h * 0.08)
            x1 = max(0, x - pad_x)
            y1 = max(0, y - pad_y)
            x2 = min(w_img, x + w + pad_x)
            y2 = min(h_img, y + h + pad_y)
            if (x2 - x1) > 40 and (y2 - y1) > 40:
                return img[y1:y2, x1:x2]

    # Fallback: Center-focused crop
    box_w = int(w_img * 0.50)
    box_h = int(h_img * 0.65)
    x1 = (w_img - box_w) // 2
    y1 = (h_img - box_h) // 2
    return img[y1 : y1 + box_h, x1 : x1 + box_w]


def compute_face_vector(face_bgr):
    """
    Lighting-invariant structural + spatial facial descriptor banata hai.
    """
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    norm_gray = clahe.apply(gray)
    norm_gray = cv2.GaussianBlur(norm_gray, (3, 3), 0)

    # 1. Coarse structural appearance (32x32)
    coarse = cv2.resize(norm_gray, (32, 32), interpolation=cv2.INTER_AREA).flatten().astype(np.float32)
    coarse = (coarse - np.mean(coarse)) / (np.std(coarse) + 1e-6)

    # 2. Facial edge/gradient structure
    gx = cv2.Sobel(cv2.resize(norm_gray, (32, 32)), cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(cv2.resize(norm_gray, (32, 32)), cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx**2 + gy**2).flatten()
    mag = (mag - np.mean(mag)) / (np.std(mag) + 1e-6)

    vec = np.concatenate([coarse * 0.6, mag * 0.4])
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def extract_face_embedding(base64_str):
    try:
        img = decode_base64_image(base64_str)
        if img is None:
            return None, "Invalid image frame received from camera."

        gray_check = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if np.std(gray_check) < 10.0:
            return None, "Camera frame too dark or covered. Please ensure proper light."

        face_crop = auto_crop_face_region(img)
        vec = compute_face_vector(face_crop)
        return vec.tolist(), None
    except Exception as e:
        return None, f"Face processing error: {str(e)}"


def verify_face_match(stored_embedding, live_base64_str, threshold=0.45):
    if not stored_embedding:
        return False, 0.0, "No registered Face ID found. Please click 'Re-Register Face' first."

    try:
        img = decode_base64_image(live_base64_str)
        if img is None:
            return False, 0.0, "Invalid camera frame."

        gray_check = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if np.std(gray_check) < 10.0:
            return False, 0.0, "Camera too dark. Please turn on light."

        v1 = np.array(stored_embedding, dtype=np.float32)

        base_crop = auto_crop_face_region(img)
        h, w = base_crop.shape[:2]
        dx = max(2, int(w * 0.06))
        dy = max(2, int(h * 0.06))

        candidates = [
            base_crop,
            base_crop[:, dx:],
            base_crop[:, : w - dx],
            base_crop[dy:, :],
            base_crop[: h - dy, :],
        ]

        best_sim = -1.0
        for cand in candidates:
            if cand.size == 0:
                continue
            v2 = compute_face_vector(cand)
            if v1.shape != v2.shape:
                return False, 0.0, "Old face format detected. Please click 'Re-Register Face' once to update."
            sim = float(np.dot(v1, v2))
            if sim > best_sim:
                best_sim = sim

        is_match = best_sim >= threshold
        if not is_match:
            return (
                False,
                round(best_sim, 3),
                f"Face did not match (Match: {int(max(best_sim, 0)*100)}%, Required: {int(threshold*100)}%). Look straight at camera.",
            )

        return True, round(best_sim, 3), None
    except Exception as e:
        return False, 0.0, f"Verification error: {str(e)}"


def verify_campus_geofence(lat, lon):
    campus_lat = float(settings.CAMPUS_LATITUDE)
    campus_lon = float(settings.CAMPUS_LONGITUDE)
    allowed_radius = float(settings.ALLOWED_RADIUS_METERS)

    R = 6371000.0
    phi1 = math.radians(campus_lat)
    phi2 = math.radians(float(lat))
    dphi = math.radians(float(lat) - campus_lat)
    dlambda = math.radians(float(lon) - campus_lon)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = round(R * c, 1)

    return distance <= allowed_radius, distance


def _format_indian_whatsapp_number(raw_number):
    digits = ''.join(ch for ch in str(raw_number or '') if ch.isdigit())
    if len(digits) == 10:
        return f"91{digits}"
    return digits


def build_low_attendance_whatsapp_url(student, pct):
    phone = _format_indian_whatsapp_number(student.parent_mobile)
    msg = (
        f"Dear Parent, this is an official alert from Govt. Polytechnic College, Bundi. "
        f"Your ward {student.user.get_full_name()} ({student.enrollment_id}) currently has "
        f"{pct}% attendance, which is below the mandatory 75% BTER requirement. "
        f"Please ensure regular class attendance."
    )
    return f"https://wa.me/{phone}?text={quote(msg)}"


def build_student_low_attendance_whatsapp_url(student, pct):
    phone = _format_indian_whatsapp_number(student.user.mobile)
    if not phone:
        return ""
    msg = (
        f"Dear {student.user.get_full_name()} ({student.enrollment_id}), "
        f"this is an official attendance warning from Govt. Polytechnic College, Bundi. "
        f"Your current attendance is {pct}%, which is below the mandatory 75% BTER norm. "
        f"Attend all upcoming lectures regularly to avoid debarment from BTER exams."
    )
    return f"https://wa.me/{phone}?text={quote(msg)}"