#!/usr/bin/env python3
"""Optional baseline: run Tesseract on every image (raw vs OpenCV-preprocessed) and
report how often the document's identifier (from ground_truth.json) is recovered.
Usage: python ocr_baseline.py [dataset_dir]   (needs: tesseract, pytesseract, opencv-python)"""
import sys, os, json, re, cv2, numpy as np, pytesseract

root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
gt = json.load(open(os.path.join(root, "ground_truth.json")))
ID_KEY = dict(aadhaar="aadhaar_number", pan="pan_number", passport="passport_number", voter_id="epic_number", driving_licence="dl_number")
norm = lambda s: re.sub(r"[^A-Z0-9]", "", s.upper())
lenient = lambda s: norm(s).replace("O", "0").replace("I", "1").replace("L", "1").replace("S", "5")
SIDES_WITH_ID = ("front",)   # ID number is printed on the front side (Aadhaar back repeats it)

def preprocess(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    g = cv2.createCLAHE(2.0, (8, 8)).apply(g)
    g = cv2.fastNlMeansDenoising(g, None, 12)
    # deskew with Tesseract OSD fallback to minAreaRect
    try:
        osd = pytesseract.image_to_osd(g, config="--psm 0 -c min_characters_to_try=5")
        rot = int(re.search(r"Rotate: (\d+)", osd).group(1))
        if rot: g = np.rot90(g, k=(360 - rot) // 90)
    except Exception: pass
    th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(th < 128)).astype(np.float32)
    if len(coords) > 100:
        ang = cv2.minAreaRect(coords[:, ::-1].copy())[-1]; ang = -(90 + ang) if ang < -45 else -ang
        if abs(ang) < 25:
            h, w = g.shape; M = cv2.getRotationMatrix2D((w / 2, h / 2), -ang, 1)
            g = cv2.warpAffine(g, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)
    return cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 15)

from collections import defaultdict
stat = defaultdict(lambda: [0, 0, 0]); tot = hit_raw = hit_pre = 0
for a in gt["applicants"]:
    for doc, d in a["documents"].items():
        target = norm(str(d["rendered_fields"][ID_KEY[doc]]))
        for q in d["image_quality"]:
            f = q["file"]
            if not f.lower().endswith((".png", ".jpg")): continue
            if not (any(f"_{s}." in f or f"_{s}_" in f for s in SIDES_WITH_ID) or (doc == "aadhaar" and "_back" in f)): continue
            img = cv2.imread(os.path.join(root, f))
            txt = lambda im: pytesseract.image_to_string(im, config="--psm 6") + " " + pytesseract.image_to_string(im, config="--psm 11")
            raw, pre = lenient(txt(img)), lenient(txt(preprocess(img)))
            t = lenient(target); r_, p_ = t in raw, t in pre
            tot += 1; hit_raw += r_; hit_pre += p_; st = stat[q["quality"]]; st[0] += 1; st[1] += r_; st[2] += p_
            print(f"{q['quality']:8s} raw={'Y' if r_ else '-'} pre={'Y' if p_ else '-'}  {f}")
print(f"\nID recovered (lenient O/0, I/1 matching): raw {hit_raw}/{tot}, preprocessed {hit_pre}/{tot}")
for k, (n, a, b) in stat.items(): print(f"  {k:8s} n={n}  raw={a}  preprocessed={b}")
