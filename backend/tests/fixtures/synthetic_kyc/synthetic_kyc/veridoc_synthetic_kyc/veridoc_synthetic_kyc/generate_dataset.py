#!/usr/bin/env python3
"""
VeriDoc AI - Synthetic KYC dataset generator.

Everything produced here is FICTIONAL and watermarked
"SYNTHETIC / NOT VALID FOR IDENTIFICATION". No real people, no valid identity
numbers, no emblems/seals/QR codes/holograms/security features.
Deterministic (fixed seeds): re-running reproduces the same dataset.
"""
import os, json, math, random, re, shutil, datetime as dt
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageChops
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

ROOT = os.environ.get("OUT_DIR", "/home/claude/veridoc_synthetic_kyc")
REF_DATE = dt.date(2026, 11, 23)          # "today" used for expiry logic
CARD = (1011, 638)                         # ID-1 card @ ~300 dpi
PASS = (1476, 1039)                        # passport data page @ ~300 dpi
DOCS = ["aadhaar", "pan", "passport", "voter_id", "driving_licence"]

# ----------------------------------------------------------------- fonts
FP = "/usr/share/fonts/truetype/"
FONTS = {
    "sans": "liberation/LiberationSans-Regular.ttf", "sansb": "liberation/LiberationSans-Bold.ttf",
    "narrow": "liberation/LiberationSansNarrow-Regular.ttf", "narrowb": "liberation/LiberationSansNarrow-Bold.ttf",
    "serif": "liberation/LiberationSerif-Regular.ttf", "serifb": "liberation/LiberationSerif-Bold.ttf",
    "mono": "liberation/LiberationMono-Regular.ttf", "monob": "liberation/LiberationMono-Bold.ttf",
    "ds": "dejavu/DejaVuSans.ttf", "dsb": "dejavu/DejaVuSans-Bold.ttf",
    "cond": "dejavu/DejaVuSansCondensed.ttf", "condb": "dejavu/DejaVuSansCondensed-Bold.ttf",
    "dmono": "dejavu/DejaVuSansMono.ttf", "dmonob": "dejavu/DejaVuSansMono-Bold.ttf",
}
_fc = {}
def font(k, s):
    if (k, s) not in _fc: _fc[(k, s)] = ImageFont.truetype(FP + FONTS[k], s)
    return _fc[(k, s)]

def lerp(a, b, t): return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
def shade(c, f): return tuple(max(0, min(255, int(v * f))) for v in c)
def D(iso): y, m, d = iso.split("-"); return f"{d}/{m}/{y}"
def addr_full(a): return f"{a['l1']}, {a['l2']}, {a['city']}, {a['state']} - {a['pin']}"

def wrap(d, text, f, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

# ----------------------------------------------------------------- applicants
APPS = [
 dict(id="APP001", slug="applicant_01_arvind_iyer", name="Arvind Raghunathan Iyer", surname="Iyer",
      given="Arvind Raghunathan", father="Raghunathan Subramanian Iyer", mother="Lalitha Raghunathan Iyer",
      gender="M", dob="1988-03-14", pob="Chennai", blood="B+", sc="TN", rto="07",
      addr=dict(l1="Flat 4B, Sample Residency", l2="17 Lotus Garden Street, Adyar", city="Chennai", state="Tamil Nadu", pin="600020"),
      ids=dict(aadhaar="0000 4821 7305", pan="SYNPI0000A", passport="Z0001001", voter="ZZZ0000101", dl="TN07 0000 0004417"),
      ppt=("2019-06-18", "2029-06-17", "Chennai"), dl=("2008-04-02", "2028-04-01"),
      constituency="Test Constituency 021 (Chennai South)", part="45",
      photo=dict(gender="M", skin=(176, 128, 98), hair=(25, 22, 22), style="short", shirt=(60, 80, 120), bg=(200, 215, 230), glasses=True, beard=0),
      var=0, profile="normal", over={}, errors=[]),
 dict(id="APP002", slug="applicant_02_meera_pillai", name="Meera Sundaram Pillai", surname="Pillai",
      given="Meera Sundaram", father="Sundaram Krishnan Pillai", mother="Janaki Sundaram Pillai",
      gender="F", dob="1993-11-02", pob="Bengaluru", blood="O+", sc="KA", rto="03",
      addr=dict(l1="No. 221, Fictional Heights", l2="5th Cross, Indiranagar", city="Bengaluru", state="Karnataka", pin="560038"),
      ids=dict(aadhaar="0000 6174 2093", pan="SYNPP0000B", passport="Z0001002", voter="ZZZ0000102", dl="KA03 0000 0007720"),
      ppt=("2021-02-11", "2031-02-10", "Bengaluru"), dl=("2012-01-20", "2032-01-19"),
      constituency="Test Constituency 154 (Bengaluru East)", part="112",
      photo=dict(gender="F", skin=(190, 140, 108), hair=(30, 22, 20), style="long", shirt=(140, 40, 70), bg=(226, 226, 226), glasses=False, beard=0),
      var=1, profile="normal", over={}, errors=[]),
 dict(id="APP003", slug="applicant_03_rohan_deshmukh", name="Rohan Kishor Deshmukh", surname="Deshmukh",
      given="Rohan Kishor", father="Kishor Anant Deshmukh", mother="Sunita Kishor Deshmukh",
      gender="M", dob="1991-02-27", pob="Pune", blood="A+", sc="MH", rto="12",
      addr=dict(l1="B-304, Demo Park Apartments", l2="Kothrud Road", city="Pune", state="Maharashtra", pin="411038"),
      ids=dict(aadhaar="0000 7731 8254", pan="SYNPD0000C", passport="Z0001003", voter="ZZZ0000103", dl="MH12 0000 0003051"),
      ppt=("2020-09-03", "2030-09-02", "Pune"), dl=("2011-07-15", "2031-07-14"),
      constituency="Test Constituency 210 (Pune City)", part="88",
      photo=dict(gender="M", skin=(160, 112, 84), hair=(40, 28, 22), style="short", shirt=(50, 90, 70), bg=(210, 220, 205), glasses=False, beard=1),
      var=0, profile="contains_errors",
      over={("voter_id", "name"): "Rohit Kishor Deshmukh",
            ("pan", "dob"): "22/07/1991",
            ("aadhaar", "aadhaar_number"): "0000 7731 825"},
      errors=[("voter_id", "name", "name_mismatch", "Given name printed as 'Rohit' instead of 'Rohan' (all other documents say Rohan)."),
              ("pan", "dob", "incorrect_dob", "PAN prints 22/07/1991; every other document says 27/02/1991."),
              ("aadhaar", "aadhaar_number", "invalid_id_format", "Aadhaar number has only 11 digits (should be 12).")]),
 dict(id="APP004", slug="applicant_04_fatima_sheikh", name="Fatima Zahra Sheikh", surname="Sheikh",
      given="Fatima Zahra", father="Abdul Rahim Sheikh", mother="Nasreen Abdul Sheikh",
      gender="F", dob="1996-05-19", pob="Hyderabad", blood="AB+", sc="TS", rto="09",
      addr=dict(l1="Door 8-2-120, Mock Enclave", l2="Road No. 12, Banjara Hills", city="Hyderabad", state="Telangana", pin="500034"),
      ids=dict(aadhaar="0000 9035 1168", pan="SYNPS0000D", passport="Z0001004", voter="ZZZ0000104", dl="TS09 0000 0005588"),
      ppt=("2022-12-05", "2032-12-04", "Hyderabad"), dl=("2016-03-09", "2036-03-08"),
      constituency="Test Constituency 066 (Hyderabad Central)", part="203",
      photo=dict(gender="F", skin=(205, 160, 128), hair=(35, 25, 22), style="bob", shirt=(40, 100, 110), bg=(235, 228, 215), glasses=True, beard=0),
      var=1, profile="normal", over={}, errors=[]),
 dict(id="APP005", slug="applicant_05_gurpreet_sandhu", name="Gurpreet Singh Sandhu", surname="Sandhu",
      given="Gurpreet Singh", father="Harbhajan Singh Sandhu", mother="Surjit Kaur Sandhu",
      gender="M", dob="1985-12-08", pob="Ludhiana", blood="O-", sc="PB", rto="10",
      addr=dict(l1="House 1127, Placeholder Colony", l2="Sector 32", city="Ludhiana", state="Punjab", pin="141010"),
      ids=dict(aadhaar="0000 3358 9402", pan="SYNPS0000E", passport="Z0001005", voter="ZZZ0000105", dl="PB10 0000 0002196"),
      ppt=("2013-05-10", "2023-05-09", "Jalandhar"), dl=("2014-08-02", "2024-08-01"),
      constituency="Test Constituency 063 (Ludhiana West)", part="31",
      photo=dict(gender="M", skin=(185, 140, 105), hair=(20, 18, 18), style="short", shirt=(110, 110, 118), bg=(240, 240, 240), glasses=False, beard=2),
      var=0, profile="contains_errors",
      over={("pan", "pan_number"): "SYNPS00000E",
            ("voter_id", "dob"): None,
            ("driving_licence", "address"): "FLAT 22, SAMPLE COLONY, MODEL TOWN, JALANDHAR, PUNJAB - 144003"},
      errors=[("passport", "date_of_expiry", "expired_document", "Passport expired on 09/05/2023 (before reference date 2026-11-23)."),
              ("driving_licence", "valid_till", "expired_document", "Licence validity ended 01/08/2024 (before reference date)."),
              ("driving_licence", "address", "address_mismatch", "DL prints a Jalandhar address; all other documents show Ludhiana."),
              ("voter_id", "dob", "missing_field", "Date of Birth line is absent from the Voter ID."),
              ("pan", "pan_number", "invalid_id_format", "PAN has 11 characters (extra digit); should be 10.")]),
]

# Degradation plan: (applicant, doc) -> (jpeg_quality, recipe)
DEG = {
 ("APP001", "pan"): (80, [dict(op="perspective", strength=0.05), dict(op="rotate", deg=8), dict(op="shadow", strength=0.35), dict(op="noise", sigma=6)]),
 ("APP002", "passport"): (70, [dict(op="gblur", sigma=2.4), dict(op="lowres", scale=0.45)]),
 ("APP002", "driving_licence"): (22, [dict(op="lowcontrast", alpha=0.6, beta=45), dict(op="noise", sigma=14)]),
 ("APP003", "voter_id"): (75, [dict(op="rotate", deg=-12), dict(op="saltpepper", amount=0.01)]),
 ("APP003", "aadhaar"): (80, [dict(op="motion", k=19, deg=15), dict(op="noise", sigma=5)]),
 ("APP004", "aadhaar"): (65, [dict(op="perspective", strength=0.08), dict(op="shadow", strength=0.5), dict(op="gblur", sigma=1.2), dict(op="rotate", deg=4)]),
 ("APP004", "voter_id"): (60, [dict(op="fax"), dict(op="saltpepper", amount=0.02)]),
 ("APP005", "driving_licence"): (80, [dict(op="rotate", deg=90), dict(op="rotate", deg=3), dict(op="noise", sigma=4)]),
 ("APP005", "passport"): (30, [dict(op="lowres", scale=0.5), dict(op="rotate", deg=-4)]),
}
CLEAN_JPG = {("APP001", "voter_id"), ("APP002", "pan"), ("APP003", "driving_licence"), ("APP004", "passport"), ("APP005", "aadhaar")}

# Sentinel identifier rules (deliberately NOT matching real-world valid ranges)
RULES = {
 "aadhaar": r"^0000 \d{4} \d{4}$",
 "pan": r"^SYNP[A-Z]0000[A-Z]$",
 "passport": r"^Z000\d{4}$",
 "voter_id": r"^ZZZ0000\d{3}$",
 "driving_licence": r"^[A-Z]{2}\d{2} 0000 \d{7}$",
}
ID_KEY = dict(aadhaar="aadhaar_number", pan="pan_number", passport="passport_number", voter_id="epic_number", driving_licence="dl_number")

# ----------------------------------------------------------------- synthetic portraits
def make_portrait(spec, seed):
    S = 2; W, H = 400 * S, 500 * S
    rnd = random.Random(seed)
    skin, hair, shirt, bg, style = spec["skin"], spec["hair"], spec["shirt"], spec["bg"], spec["style"]
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    for y in range(H): d.line([(0, y), (W, y)], fill=lerp(shade(bg, 1.08), shade(bg, 0.86), y / H))
    if style == "long": d.rounded_rectangle([185, 230, 615, 940], radius=190, fill=hair)
    if style == "bob": d.rounded_rectangle([190, 230, 610, 770], radius=170, fill=hair)
    d.rectangle([345, 580, 455, 790], fill=shade(skin, 0.86))
    d.ellipse([40, 735, 760, 1300], fill=shirt)
    d.polygon([(325, 748), (400, 880), (475, 748)], fill=shade(skin, 0.84))
    d.ellipse([210, 405, 248, 495], fill=shade(skin, 0.93)); d.ellipse([552, 405, 590, 495], fill=shade(skin, 0.93))
    d.ellipse([230, 225, 570, 645], fill=skin)
    # forehead / cheek shading
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sd = ImageDraw.Draw(sh)
    sd.ellipse([430, 260, 575, 640], fill=(60, 30, 20, 40))
    sh = sh.filter(ImageFilter.GaussianBlur(28)); img.paste(sh, (0, 0), sh); d = ImageDraw.Draw(img)
    # hair cap (bowl) via mask difference
    m1 = Image.new("L", (W, H), 0); ImageDraw.Draw(m1).ellipse([212, 185, 588, 480], fill=255)
    m2 = Image.new("L", (W, H), 0); ImageDraw.Draw(m2).ellipse([262, 292 if style != "short" else 285, 538, 660], fill=255)
    cap = ImageChops.subtract(m1, m2)
    if style in ("long", "bob"):   # side-parted fringe
        d2 = ImageDraw.Draw(cap); d2.polygon([(250, 300), (330, 255), (400, 250), (330, 330)], fill=255)
    img.paste(Image.new("RGB", (W, H), hair), (0, 0), cap); d = ImageDraw.Draw(img)
    if spec.get("beard"):
        mb = Image.new("L", (W, H), 0); ImageDraw.Draw(mb).ellipse([230, 225, 570, 645], fill=255)
        mc = Image.new("L", (W, H), 0); ImageDraw.Draw(mc).ellipse([225, 150, 575, 548], fill=255)
        beard = ImageChops.subtract(mb, mc)
        if spec["beard"] == 1: beard = beard.point(lambda v: int(v * 0.35))
        else: beard = beard.point(lambda v: int(v * 0.85))
        img.paste(Image.new("RGB", (W, H), shade(hair, 1.1) if spec["beard"] == 2 else shade(skin, 0.55)), (0, 0), beard); d = ImageDraw.Draw(img)
    eye_c = (45, 28, 20)
    for cx in (320, 480):
        d.ellipse([cx - 40, 405, cx + 40, 445], fill=(238, 236, 232))
        d.ellipse([cx - 17, 408, cx + 17, 442], fill=eye_c); d.ellipse([cx - 8, 418, cx + 8, 434], fill=(10, 8, 8))
        d.ellipse([cx + 3, 412, cx + 11, 420], fill=(240, 240, 240))
        d.arc([cx - 42, 398, cx + 42, 440], 195, 345, fill=shade(skin, 0.5), width=5)
        d.line([(cx - 48, 384), (cx - 5, 372), (cx + 48, 386)], fill=shade(hair, 1.0), width=11 if spec["gender"] == "M" else 8)
    d.line([(400, 430), (391, 520)], fill=shade(skin, 0.8), width=5)
    d.arc([372, 500, 428, 548], 20, 160, fill=shade(skin, 0.68), width=5)
    d.ellipse([378, 526, 394, 538], fill=shade(skin, 0.55)); d.ellipse([406, 526, 422, 538], fill=shade(skin, 0.55))
    lip = (168, 78, 86) if spec["gender"] == "F" else shade(skin, 0.7)
    d.ellipse([358, 586, 442, 620], fill=lerp(lip, skin, 0.15)); d.line([(352, 592), (400, 598), (448, 592)], fill=shade(lip, 0.65), width=5)
    if spec.get("glasses"):
        for cx in (320, 480): d.rounded_rectangle([cx - 56, 388, cx + 56, 460], radius=24, outline=(30, 30, 34), width=7)
        d.line([(376, 418), (424, 418)], fill=(30, 30, 34), width=6)
    img = img.resize((400, 500), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.9))
    a = np.asarray(img).astype(np.float32)
    xs = np.linspace(-1, 1, 400)[None, :]; ys = np.linspace(-1, 1, 500)[:, None]
    vig = 1.0 - 0.18 * (xs ** 2 + ys ** 2); light = 1.0 + 0.07 * xs
    a = a * (vig * light)[..., None] + np.random.default_rng(seed).normal(0, 4.5, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

# ----------------------------------------------------------------- drawing helpers
def paste_photo(f, ph, xy, size, gray=False):
    p = ph.resize(size, Image.LANCZOS)
    if gray: p = ImageOps.grayscale(p).convert("RGB")
    f.paste(p, xy); ImageDraw.Draw(f).rectangle([xy[0], xy[1], xy[0] + size[0], xy[1] + size[1]], outline=(70, 70, 70), width=3)

def dashed_box(d, box, text, col=(90, 90, 90)):
    x0, y0, x1, y1 = box
    for x in range(x0, x1, 16):
        d.line([(x, y0), (min(x + 8, x1), y0)], fill=col, width=3); d.line([(x, y1), (min(x + 8, x1), y1)], fill=col, width=3)
    for y in range(y0, y1, 16):
        d.line([(x0, y), (x0, min(y + 8, y1))], fill=col, width=3); d.line([(x1, y), (x1, min(y + 8, y1))], fill=col, width=3)
    cy = (y0 + y1) // 2
    for i, t in enumerate(text.split("\n")):
        d.text(((x0 + x1) // 2, cy + (i - (len(text.split("\n")) - 1) / 2) * 24), t, font=font("sansb", 18), fill=col, anchor="mm")

def signature(d, x, y, w, h, seed, color=(20, 30, 110)):
    r = random.Random(seed); n = 70; k = r.uniform(9, 15); pts = []
    for i in range(n):
        t = i / (n - 1)
        pts.append((x + t * w, y + h / 2 + math.sin(t * k) * h * 0.38 * (1 - 0.4 * t) + r.uniform(-3, 3)))
    d.line(pts, fill=color, width=3, joint="curve")

def watermark(img):
    img = img.convert("RGB"); W, H = img.size
    d = ImageDraw.Draw(img); bh = max(28, int(H * 0.052))
    d.rectangle([0, H - bh, W, H], fill=(190, 25, 25))
    d.text((W // 2, H - bh // 2), "SYNTHETIC / NOT VALID FOR IDENTIFICATION  -  OCR TEST DATA", font=font("sansb", int(bh * 0.52)), fill="white", anchor="mm")
    layer = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
    f = font("sansb", int(H * 0.065)); step = int(H * 0.27)
    for j, y in enumerate(range(0, H * 2, step)):
        for x in range(-W, W * 2, int(W * 0.78)):
            ld.text((x + (j % 2) * int(W * 0.39), y), "SYNTHETIC - NOT VALID", font=f, fill=(190, 25, 25, 34))
    layer = layer.rotate(22, resample=Image.BICUBIC).crop((W // 2, H // 2, W // 2 + W, H // 2 + H))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")

# ----------------------------------------------------------------- MRZ-style line (plain text, fictional)
def mrz_chk(s):
    w = [7, 3, 1]; t = 0
    for i, c in enumerate(s):
        v = int(c) if c.isdigit() else (ord(c) - 55 if c.isalpha() else 0)
        t += v * w[i % 3]
    return str(t % 10)

def mrz(app):
    sn = app["surname"].upper(); gn = app["given"].upper().replace(" ", "<")
    l1 = ("P<IND" + sn + "<<" + gn).ljust(44, "<")[:44]
    num = app["ids"]["passport"].ljust(9, "<"); yy = lambda iso: iso[2:4] + iso[5:7] + iso[8:10]
    dob, exp = yy(app["dob"]), yy(app["ppt"][1]); pn = "<" * 14
    c1, c2, c3, c4 = mrz_chk(num), mrz_chk(dob), mrz_chk(exp), "0"
    c5 = mrz_chk(num + c1 + dob + c2 + exp + c3 + pn + c4)
    return l1, num + c1 + "IND" + dob + c2 + app["gender"] + exp + c3 + pn + c4 + c5

# ----------------------------------------------------------------- field builders
DATE_KEYS = {"dob", "date_of_issue", "date_of_expiry", "issue_date", "valid_till"}
NAME_KEYS = {"name", "surname", "given_names", "father_name", "mother_name", "relation_name"}

def rendered_fields(a, doc):
    A = a["addr"]; M = a["gender"] == "M"; up = str.upper
    if doc == "aadhaar":
        r = dict(name=a["name"], dob=D(a["dob"]), gender="Male" if M else "Female", aadhaar_number=a["ids"]["aadhaar"],
                 care_of=f"{'S/O' if M else 'D/O'} {a['father']}", address=addr_full(A))
    elif doc == "pan":
        r = dict(pan_number=a["ids"]["pan"], name=up(a["name"]), father_name=up(a["father"]), dob=D(a["dob"]))
    elif doc == "passport":
        l1, l2 = mrz(a)
        r = dict(passport_number=a["ids"]["passport"], surname=up(a["surname"]), given_names=up(a["given"]), nationality="INDIAN",
                 sex=a["gender"], dob=D(a["dob"]), place_of_birth=up(a["pob"]), place_of_issue=up(a["ppt"][2]),
                 date_of_issue=D(a["ppt"][0]), date_of_expiry=D(a["ppt"][1]), father_name=up(a["father"]), mother_name=up(a["mother"]),
                 address=addr_full(A), mrz_line1=l1, mrz_line2=l2)
    elif doc == "voter_id":
        r = dict(epic_number=a["ids"]["voter"], name=a["name"], relation_type="Father", relation_name=a["father"],
                 gender="Male" if M else "Female", dob=D(a["dob"]), address=addr_full(A),
                 assembly_constituency=a["constituency"], part_number=a["part"])
    else:
        r = dict(dl_number=a["ids"]["dl"], name=up(a["name"]), guardian_name=f"{'S/O' if M else 'D/O'} {up(a['father'])}",
                 dob=D(a["dob"]), blood_group=a["blood"], address=up(addr_full(A)), issue_date=D(a["dl"][0]), valid_till=D(a["dl"][1]),
                 vehicle_classes="MCWG, LMV", issuing_authority=f"RTO {up(A['city'])} ({a['sc']}{a['rto']})")
    return r

def expected_fields(a, doc):
    out = {}
    for k, v in rendered_fields(a, doc).items():
        if k in DATE_KEYS:
            dd, mm, yy = v.split("/"); out[k] = f"{yy}-{mm}-{dd}"
        elif k in NAME_KEYS: out[k] = v.title() if v.isupper() else v
        else: out[k] = v
    return out

def printed_fields(a, doc):
    r = rendered_fields(a, doc)
    for (dc, fld), val in a["over"].items():
        if dc == doc: r[fld] = val
    return r

# ----------------------------------------------------------------- document renderers
def kv(d, x, y, label, value, vf, lf=None, gap=24, col=(20, 20, 20)):
    d.text((x, y), label, font=lf or font("sans", 20), fill=(105, 105, 105)); d.text((x, y + gap), value, font=vf, fill=col)

def r_aadhaar(r, ph, var):
    W, H = CARD; bg, acc = ((236, 246, 248), (0, 105, 125)) if var == 0 else ((251, 244, 233), (150, 65, 25))
    out = []
    f = Image.new("RGB", (W, H), bg); d = ImageDraw.Draw(f)
    d.rectangle([0, 0, W, 86], fill=acc)
    d.text((32, 43), "UNIQUE IDENTITY CARD  ·  AADHAAR-STYLE SPECIMEN", font=font("sansb", 30), fill="white", anchor="lm")
    px = 36 if var == 0 else W - 36 - 220; tx = 290 if var == 0 else 40
    paste_photo(f, ph, (px, 118), (220, 275))
    y = 118
    for lab, key, sz in [("Name", "name", 38), ("Date of Birth", "dob", 34), ("Gender", "gender", 34)]:
        if r.get(key) is None: continue
        kv(d, tx, y, lab, r[key], font("sansb", sz)); y += 90
    dashed_box(d, (790, 300, 940, 450) if var == 0 else (600, 125, 750, 275), "QR PLACEHOLDER\nNOT SCANNABLE")
    d.line([(40, 465), (W - 40, 465)], fill=acc, width=3)
    d.text((W // 2, 530), r["aadhaar_number"], font=font("dmonob", 66), fill=(20, 20, 20), anchor="mm")
    d.text((W // 2, 584), "Fictional specimen number - invalid by design", font=font("sans", 20), fill=(110, 110, 110), anchor="mm")
    out.append(f)
    b = Image.new("RGB", (W, H), bg); d = ImageDraw.Draw(b)
    d.rectangle([0, 0, W, 70], fill=acc); d.text((32, 35), "ADDRESS", font=font("sansb", 30), fill="white", anchor="lm")
    y = 105; d.text((40, y), r["care_of"], font=font("sansb", 30), fill=(20, 20, 20)); y += 46
    for ln in wrap(d, r["address"], font("sans", 30), W - 80): d.text((40, y), ln, font=font("sans", 30), fill=(20, 20, 20)); y += 42
    d.line([(40, 465), (W - 40, 465)], fill=acc, width=3)
    d.text((W // 2, 530), r["aadhaar_number"], font=font("dmonob", 52), fill=(20, 20, 20), anchor="mm")
    d.text((W // 2, 584), "Fictional specimen - not an official document", font=font("sans", 20), fill=(110, 110, 110), anchor="mm")
    out.append(b); return out

def r_pan(r, ph, var):
    W, H = CARD; bg, acc = ((214, 228, 246), (24, 52, 120)) if var == 0 else ((232, 240, 226), (40, 90, 50))
    f = Image.new("RGB", (W, H), bg); d = ImageDraw.Draw(f)
    d.rectangle([0, 0, W, 80], fill=acc)
    d.text((W // 2, 40), "INCOME TAX DEPARTMENT STYLE  ·  SYNTHETIC SPECIMEN", font=font("narrowb", 34), fill="white", anchor="mm")
    d.text((W // 2, 112), "PERMANENT ACCOUNT NUMBER CARD", font=font("serifb", 28), fill=acc, anchor="mm")
    px = W - 36 - 220 if var == 0 else 36; tx = 40 if var == 0 else 290
    paste_photo(f, ph, (px, 145), (220, 275), gray=(var == 1))
    kv(d, tx, 150, "Permanent Account Number", r["pan_number"], font("dmonob", 50), col=acc)
    kv(d, tx, 245, "Name", r["name"], font("narrowb", 36)); kv(d, tx, 330, "Father's Name", r["father_name"], font("narrowb", 36))
    if r.get("dob") is not None: kv(d, tx, 415, "Date of Birth", r["dob"], font("narrowb", 36))
    signature(d, tx + 10, 505, 300, 60, 11 + var); d.text((tx, 575), "Signature", font=font("sans", 18), fill=(105, 105, 105))
    return [f]

def r_voter(r, ph, var):
    W, H = CARD; bg, acc = ((250, 236, 240), (150, 30, 80)) if var == 0 else ((238, 236, 250), (60, 50, 140))
    f = Image.new("RGB", (W, H), bg); d = ImageDraw.Draw(f)
    d.rectangle([0, 0, W, 72], fill=acc)
    d.text((30, 36), "ELECTOR PHOTO IDENTITY CARD  ·  SYNTHETIC SPECIMEN", font=font("condb", 30), fill="white", anchor="lm")
    d.text((40, 96), "EPIC No.", font=font("sans", 22), fill=(105, 105, 105)); d.text((170, 90), r["epic_number"], font=font("dmonob", 46), fill=acc)
    px = 36 if var == 0 else W - 36 - 200; tx = 270 if var == 0 else 40
    paste_photo(f, ph, (px, 170), (200, 250))
    y = 165
    for lab, key in [("Elector's Name", "name"), ("Father's Name", "relation_name"), ("Sex", "gender"), ("Date of Birth", "dob")]:
        if r.get(key) is None: continue
        kv(d, tx, y, lab, r[key], font("cond", 34)); y += 85
    d.text((W // 2, 590), "Fictional specimen - no electoral validity", font=font("sans", 20), fill=(110, 110, 110), anchor="mm")
    b = Image.new("RGB", (W, H), bg); d = ImageDraw.Draw(b)
    d.rectangle([0, 0, W, 60], fill=acc); d.text((30, 30), "ADDRESS", font=font("condb", 28), fill="white", anchor="lm")
    y = 95
    for ln in wrap(d, r["address"], font("cond", 32), W - 80): d.text((40, y), ln, font=font("cond", 32), fill=(20, 20, 20)); y += 44
    kv(d, 40, 300, "Assembly Constituency No. & Name", r["assembly_constituency"], font("cond", 32)); kv(d, 40, 400, "Part No.", r["part_number"], font("cond", 32))
    kv(d, 500, 400, "Sample Print Date", "01/01/2024", font("cond", 32))
    return [f, b]

def r_dl(r, ph, var):
    W, H = CARD; f = Image.new("RGB", (W, H)); d = ImageDraw.Draw(f)
    c1, c2 = ((222, 240, 226), (200, 226, 240)) if var == 0 else ((250, 238, 214), (238, 222, 200))
    for x in range(W): d.line([(x, 0), (x, H)], fill=lerp(c1, c2, x / W))
    acc = (20, 80, 60) if var == 0 else (120, 60, 20)
    d.rectangle([0, 0, W, 74], fill=acc)
    d.text((30, 37), "DRIVING LICENCE  ·  SYNTHETIC SPECIMEN", font=font("sansb", 32), fill="white", anchor="lm")
    px = W - 36 - 190 if var == 0 else 36; tx = 40 if var == 0 else 260; vx = tx + 215
    paste_photo(f, ph, (px, 100), (190, 238))
    lf = font("sans", 20); vf = font("narrowb", 30)
    d.text((tx, 100), "DL No.", font=lf, fill=(95, 95, 95)); d.text((tx + 100, 90), r["dl_number"], font=font("dmonob", 38), fill=acc)
    rows = [("Name", "name"), ("S/D/W of", "guardian_name"), ("Date of Birth", "dob"), ("Blood Group", "blood_group")]
    y = 160
    for lab, key in rows:
        if r.get(key) is None: continue
        d.text((tx, y + 6), lab, font=lf, fill=(95, 95, 95)); d.text((vx, y), r[key], font=vf, fill=(20, 20, 20)); y += 46
    d.text((tx, y + 6), "Address", font=lf, fill=(95, 95, 95))
    for ln in wrap(d, r["address"], font("narrow", 28), (px - 20 if var == 0 else W - 40) - vx):
        d.text((vx, y), ln, font=font("narrow", 28), fill=(20, 20, 20)); y += 33
    y = max(y + 14, 440)
    d.text((tx, y + 6), "Issue Date", font=lf, fill=(95, 95, 95)); d.text((tx + 130, y), r["issue_date"], font=vf, fill=(20, 20, 20))
    d.text((tx + 400, y + 6), "Valid Till (NT)", font=lf, fill=(95, 95, 95)); d.text((tx + 560, y), r["valid_till"], font=vf, fill=(20, 20, 20))
    y += 50; d.text((tx, y + 6), "COV", font=lf, fill=(95, 95, 95)); d.text((tx + 130, y), r["vehicle_classes"], font=vf, fill=(20, 20, 20))
    signature(d, W - 330, 530, 240, 45, 31 + var)
    b = Image.new("RGB", (W, H), lerp(c1, c2, 0.5)); d = ImageDraw.Draw(b)
    d.rectangle([0, 0, W, 60], fill=acc); d.text((30, 30), "CLASSES OF VEHICLE AUTHORISED", font=font("sansb", 26), fill="white", anchor="lm")
    d.text((40, 100), "Class of Vehicle", font=font("sansb", 24), fill=(20, 20, 20)); d.text((420, 100), "Date of Issue", font=font("sansb", 24), fill=(20, 20, 20))
    for i, cov in enumerate(["MCWG", "LMV"]):
        yy = 150 + i * 55; d.line([(40, yy - 8), (W - 40, yy - 8)], fill=(120, 120, 120), width=2)
        d.text((40, yy), cov, font=font("monob", 30), fill=(20, 20, 20)); d.text((420, yy), r["issue_date"], font=font("mono", 30), fill=(20, 20, 20))
    d.text((40, 330), "Issuing Authority:", font=font("sansb", 24), fill=(20, 20, 20)); d.text((300, 330), r["issuing_authority"], font=font("mono", 28), fill=(20, 20, 20))
    d.text((40, 400), "Fictional specimen. No licence authority exists for this card.", font=font("sans", 22), fill=(105, 105, 105))
    return [f, b]

def r_passport(r, ph, var, a):
    W, H = PASS; bg = (246, 240, 224) if var == 0 else (232, 240, 246); acc = (110, 40, 40) if var == 0 else (30, 60, 110)
    f = Image.new("RGB", (W, H), bg); d = ImageDraw.Draw(f)
    for i in range(-H, W, 28): d.line([(i, 0), (i + H, H)], fill=shade(bg, 0.96), width=2)
    d.text((60, 50), "PASSPORT", font=font("serifb", 52), fill=acc); d.text((W - 60, 62), "SYNTHETIC SPECIMEN  ·  FICTIONAL", font=font("sansb", 26), fill=acc, anchor="rm")
    d.line([(60, 110), (W - 60, 110)], fill=acc, width=3)
    paste_photo(f, ph, (60, 150), (330, 412))
    x1, x2 = 440, 960; lf = font("sans", 20); vf = font("dsb", 30)
    kv(d, x1, 140, "Type", "P", vf); kv(d, x1 + 170, 140, "Country Code", "IND", vf); kv(d, x2, 140, "Passport No.", r["passport_number"], font("dmonob", 34))
    kv(d, x1, 225, "Surname", r["surname"], vf); kv(d, x1, 310, "Given Name(s)", r["given_names"], vf)
    kv(d, x1, 395, "Nationality", r["nationality"], vf); kv(d, x1 + 330, 395, "Sex", r["sex"], vf); kv(d, x2, 395, "Date of Birth", r["dob"], vf)
    kv(d, x1, 480, "Place of Birth", r["place_of_birth"], vf); kv(d, x2, 480, "Place of Issue", r["place_of_issue"], vf)
    kv(d, x1, 565, "Date of Issue", r["date_of_issue"], vf); kv(d, x2, 565, "Date of Expiry", r["date_of_expiry"], vf)
    signature(d, 80, 600, 280, 50, 41 + var)
    d.rectangle([40, 770, W - 40, 960], fill=(255, 255, 255), outline=acc, width=2)
    d.text((70, 805), r["mrz_line1"], font=font("mono", 47), fill=(20, 20, 20)); d.text((70, 880), r["mrz_line2"], font=font("mono", 47), fill=(20, 20, 20))
    b = Image.new("RGB", (W, H), bg); d = ImageDraw.Draw(b)
    for i in range(-H, W, 28): d.line([(i, 0), (i + H, H)], fill=shade(bg, 0.96), width=2)
    d.text((60, 50), "PARTICULARS OF FATHER / MOTHER / ADDRESS", font=font("serifb", 40), fill=acc)
    d.text((W - 60, 62), "SYNTHETIC SPECIMEN", font=font("sansb", 26), fill=acc, anchor="rm"); d.line([(60, 110), (W - 60, 110)], fill=acc, width=3)
    kv(d, 60, 150, "Name of Father / Legal Guardian", r["father_name"], vf); kv(d, 60, 240, "Name of Mother", r["mother_name"], vf)
    kv(d, 60, 330, "Name of Spouse", "-", vf); d.text((60, 420), "Address", font=lf, fill=(105, 105, 105)); y = 446
    for ln in wrap(d, r["address"], font("dsb", 30), W - 120): d.text((60, y), ln, font=font("dsb", 30), fill=(20, 20, 20)); y += 42
    kv(d, 60, 640, "Old Passport No.", "-", vf); kv(d, 700, 640, "File No.", "SYN0000000", font("dmonob", 30))
    d.text((60, 760), "Fictional specimen created for OCR testing. Not a travel document.", font=font("sans", 24), fill=(105, 105, 105))
    return [f, b]

RENDER = dict(aadhaar=r_aadhaar, pan=r_pan, voter_id=r_voter, driving_licence=r_dl)

# ----------------------------------------------------------------- degradations (OpenCV)
def to_cv(i): return cv2.cvtColor(np.array(i), cv2.COLOR_RGB2BGR)
def to_pil(a): return Image.fromarray(cv2.cvtColor(a, cv2.COLOR_BGR2RGB))
DESK = (205, 205, 198)
def rotate_cv(a, ang):
    h, w = a.shape[:2]; M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1)
    c, s = abs(M[0, 0]), abs(M[0, 1]); nw, nh = int(h * s + w * c), int(h * c + w * s)
    M[0, 2] += nw / 2 - w / 2; M[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(a, M, (nw, nh), flags=cv2.INTER_CUBIC, borderValue=DESK)
def apply_recipe(img, recipe, seed):
    a = to_cv(img); rng = np.random.default_rng(seed)
    for st in recipe:
        op = st["op"]; h, w = a.shape[:2]
        if op == "rotate": a = rotate_cv(a, st["deg"])
        elif op == "gblur": a = cv2.GaussianBlur(a, (0, 0), st["sigma"])
        elif op == "lowres":
            sm = cv2.resize(a, None, fx=st["scale"], fy=st["scale"], interpolation=cv2.INTER_AREA)
            a = cv2.resize(sm, (w, h), interpolation=cv2.INTER_LINEAR)
        elif op == "noise": a = np.clip(a.astype(np.float32) + rng.normal(0, st["sigma"], a.shape), 0, 255).astype(np.uint8)
        elif op == "saltpepper":
            m = rng.random(a.shape[:2]); a[m < st["amount"] / 2] = 0; a[m > 1 - st["amount"] / 2] = 255
        elif op == "motion":
            k = st["k"]; ker = np.zeros((k, k), np.float32); ker[k // 2, :] = 1; ker /= k
            M = cv2.getRotationMatrix2D((k / 2 - .5, k / 2 - .5), st["deg"], 1); ker = cv2.warpAffine(ker, M, (k, k)); ker /= ker.sum()
            a = cv2.filter2D(a, -1, ker)
        elif op == "lowcontrast": a = cv2.convertScaleAbs(a, alpha=st["alpha"], beta=st["beta"])
        elif op == "shadow":
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32); g = 1 - st["strength"] * (xx / w * 0.7 + yy / h * 0.3)
            a = np.clip(a.astype(np.float32) * g[..., None], 0, 255).astype(np.uint8)
        elif op == "perspective":
            m = 70; a = cv2.copyMakeBorder(a, m, m, m, m, cv2.BORDER_CONSTANT, value=DESK); h, w = a.shape[:2]; s = st["strength"]
            src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
            dst = np.float32([[s * w * .6, s * h * .25], [w - s * w * .15, 0], [w - s * w * .45, h - s * h * .3], [s * w * .1, h - s * h * .1]])
            a = cv2.warpPerspective(a, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=DESK)
        elif op == "fax":
            g = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
            g = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 12)
            a = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    return to_pil(a)

# ----------------------------------------------------------------- PDF
def make_pdf(path, images, kind, tmpdir):
    c = rl_canvas.Canvas(path, pagesize=A4); PW, PH = A4
    c.setTitle("SYNTHETIC KYC SPECIMEN - NOT VALID FOR IDENTIFICATION")
    def put(img, x, y, wpt):
        tp = os.path.join(tmpdir, f"_t{random.random()}.jpg"); img.convert("RGB").save(tp, quality=88)
        hpt = wpt * img.size[1] / img.size[0]
        if y - hpt < 40: pass
        c.drawImage(tp, x, y - hpt, wpt, hpt); os.remove(tp); return hpt
    def foot():
        c.setFont("Helvetica-Bold", 9); c.setFillColorRGB(.75, .1, .1)
        c.drawCentredString(PW / 2, 22, "SYNTHETIC SPECIMEN - NOT VALID FOR IDENTIFICATION - VeriDoc AI OCR test data")
    if kind == "card":
        y = PH - 70
        for im in images:
            wpt = 330 if max(im.size) < 1100 else 400
            if im.size[1] > im.size[0] * 1.2: wpt = 200
            hpt = put(im, (PW - wpt) / 2, y, wpt); y -= hpt + 35
        foot(); c.showPage()
    else:
        for im in images: put(im, 50, PH - 80, PW - 100); foot(); c.showPage()
    c.save()

# ----------------------------------------------------------------- main
def main():
    if os.path.exists(ROOT): shutil.rmtree(ROOT)
    os.makedirs(ROOT); tmp = os.path.join(ROOT, "_tmp"); os.makedirs(tmp)
    gt = dict(dataset=dict(name="VeriDoc AI - Synthetic KYC Test Dataset", version="1.0", generated_on=str(REF_DATE),
                           reference_date_for_expiry_checks=str(REF_DATE),
                           disclaimer="ALL DATA IS FICTIONAL. Every image/PDF is watermarked SYNTHETIC / NOT VALID FOR IDENTIFICATION. Identifier values are reserved sentinel patterns that cannot be valid real-world IDs.",
                           synthetic_identifier_rules=RULES,
                           conventions=dict(expected_fields="Correct, normalised truth (ISO dates, title-case names).",
                                            rendered_fields="Exact strings printed on the image, incl. deliberate errors. OCR should reproduce these.",
                                            name_comparison="Compare case-insensitively; PAN/Passport/DL print names in UPPERCASE.")),
              applicants=[])
    summary_rows = []
    for ai, a in enumerate(APPS):
        ph = make_portrait(a["photo"], seed=100 + ai)
        folder = os.path.join(ROOT, a["slug"]); os.makedirs(folder)
        ph.save(os.path.join(folder, "portrait_source.png"))
        canonical = dict(full_name=a["name"], dob=a["dob"], gender=a["gender"], father_name=a["father"], mother_name=a["mother"],
                         place_of_birth=a["pob"], address=dict(a["addr"]), address_full=addr_full(a["addr"]))
        app_gt = dict(applicant_id=a["id"], folder=a["slug"], profile_type=a["profile"], canonical_profile=canonical,
                      portrait_source=f"{a['slug']}/portrait_source.png", documents={})
        flags = []
        for doc in DOCS:
            dd = os.path.join(folder, doc); os.makedirs(dd)
            rend = printed_fields(a, doc); exp = expected_fields(a, doc)
            if doc == "passport": imgs = r_passport(rend, ph, a["var"], a); names = ["front", "address_page"]
            else:
                imgs = RENDER[doc](rend, ph, a["var"]); names = ["front", "back"][:len(imgs)]
            imgs = [watermark(i) for i in imgs]
            ext = "jpg" if (a["id"], doc) in CLEAN_JPG else "png"
            files, quality = [], []
            for n, im in zip(names, imgs):
                fn = f"{doc}_{n}.{ext}"
                im.save(os.path.join(dd, fn), **({"quality": 93} if ext == "jpg" else {}))
                files.append(f"{a['slug']}/{doc}/{fn}"); quality.append(dict(file=files[-1], quality="clean"))
            kind = "page" if doc == "passport" else "card"
            make_pdf(os.path.join(dd, f"{doc}.pdf"), imgs, kind, tmp); files.append(f"{a['slug']}/{doc}/{doc}.pdf")
            quality.append(dict(file=files[-1], quality="clean", note="image-only scan-style PDF (A4)"))
            if (a["id"], doc) in DEG:
                q, recipe = DEG[(a["id"], doc)]; dimgs = []
                for k, (n, im) in enumerate(zip(names, imgs)):
                    di = apply_recipe(im, recipe, seed=900 + ai * 10 + k); dimgs.append(di)
                    fn = f"{doc}_{n}_degraded.jpg"; di.save(os.path.join(dd, fn), quality=q)
                    files.append(f"{a['slug']}/{doc}/{fn}")
                    quality.append(dict(file=files[-1], quality="degraded", jpeg_quality=q, degradations=recipe,
                                        suggested_fix=[s["op"] for s in recipe]))
                make_pdf(os.path.join(dd, f"{doc}_degraded.pdf"), dimgs, kind, tmp); files.append(f"{a['slug']}/{doc}/{doc}_degraded.pdf")
                quality.append(dict(file=files[-1], quality="degraded", degradations=recipe, note="PDF built from degraded images"))
            idv = rend[ID_KEY[doc]]; fmt_ok = bool(re.match(RULES[doc], idv))
            validity = dict(id_matches_synthetic_pattern=fmt_ok)
            if doc in ("passport", "driving_licence"):
                ek = "date_of_expiry" if doc == "passport" else "valid_till"
                validity["expiry_date"] = exp[ek]; validity["is_expired_on_reference_date"] = dt.date.fromisoformat(exp[ek]) < REF_DATE
            missing = [k for k, v in rend.items() if v is None]
            validity["missing_fields"] = missing
            errs = []
            for (dc, fld, typ, note) in a["errors"]:
                if dc != doc: continue
                errs.append(dict(field=fld, error_type=typ, printed_value=rend.get(fld), correct_value=None if typ in ("expired_document", "missing_field") and fld != "address" else exp.get(fld),
                                 description=note))
            if not fmt_ok: flags.append(f"invalid_id_format:{doc}")
            if validity.get("is_expired_on_reference_date"): flags.append(f"expired:{doc}")
            for m in missing: flags.append(f"missing_field:{doc}.{m}")
            for k in list(rend):
                if rend[k] is None: rend[k] = None
            app_gt["documents"][doc] = dict(layout_variant=a["var"], files=files, image_quality=quality, expected_fields=exp,
                                            rendered_fields=rend, intentional_errors=errs, validation=validity)
        # cross-document checks
        norm = lambda s: re.sub(r"[^a-z]", "", s.lower())
        D_ = app_gt["documents"]
        names = {"aadhaar": D_["aadhaar"]["rendered_fields"]["name"], "pan": D_["pan"]["rendered_fields"]["name"],
                 "passport": D_["passport"]["rendered_fields"]["given_names"] + " " + D_["passport"]["rendered_fields"]["surname"],
                 "voter_id": D_["voter_id"]["rendered_fields"]["name"], "driving_licence": D_["driving_licence"]["rendered_fields"]["name"]}
        dobs = {k: D_[k]["rendered_fields"].get("dob") for k in DOCS if D_[k]["rendered_fields"].get("dob")}
        dobs["passport"] = D_["passport"]["rendered_fields"]["dob"]
        addrs = {k: D_[k]["rendered_fields"]["address"] for k in ("aadhaar", "passport", "voter_id", "driving_licence")}
        name_ok = len({norm(v) for v in names.values()}) == 1; dob_ok = len(set(dobs.values())) == 1
        addr_ok = len({norm(v) for v in addrs.values()}) == 1
        if not name_ok: flags.append("name_mismatch")
        if not dob_ok: flags.append("dob_mismatch")
        if not addr_ok: flags.append("address_mismatch")
        app_gt["cross_document_expectations"] = dict(name_consistent=name_ok, dob_consistent=dob_ok, address_consistent=addr_ok,
                                                     names_as_printed=names, dobs_as_printed=dobs, expected_flags=sorted(set(flags)),
                                                     expected_decision="PASS" if not flags else "FLAG_FOR_REVIEW")
        gt["applicants"].append(app_gt)
        summary_rows.append((a["id"], a["name"], a["profile"], ", ".join(sorted(set(flags))) or "none"))
    shutil.rmtree(tmp)
    json.dump(gt, open(os.path.join(ROOT, "ground_truth.json"), "w"), indent=2, ensure_ascii=False)
    return summary_rows

if __name__ == "__main__":
    for row in main(): print(row)
