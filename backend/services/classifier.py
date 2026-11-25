import re
from typing import Dict, Any, List, Tuple


class DocumentClassifier:
    """
    Classifies Indian KYC documents into one of 5 supported types:
    - pan (Permanent Account Number / Form 49A)
    - aadhaar (Unique Identification Authority of India)
    - passport (Republic of India Passport)
    - voter_id (Election Commission of India / EPIC)
    - driving_licence (State Transport / Ministry of Road Transport)
    """

    # Keyword rules with positive weights (supports OCR variations and spacing)
    KEYWORD_RULES = {
        "pan": [
            ("INCOME TAX DEPARTMENT", 35),
            ("INCOMETAX DEPARTMENT", 35),
            ("INCOME TAX", 20),
            ("PERMANENT ACCOUNT NUMBER", 35),
            ("PERMANENT ACCOUNT NO", 35),
            ("PERMANENT ACCOUNT", 25),
            ("ACCOUNT NUMBER", 15),
            ("PAN CARD", 30),
            ("FORM 49A", 30),
            ("GOVT. OF INDIA", 15),
            ("GOVT OF INDIA", 15),
            ("GOVERNMENT OF INDIA", 15),
            ("FATHER'S NAME", 10),
            ("FATHERS NAME", 10),
            ("DATE OF BIRTH", 10),
            ("SIGNATURE", 5),
            ("PAN", 15),
        ],
        "aadhaar": [
            ("UNIQUE IDENTIFICATION AUTHORITY OF INDIA", 40),
            ("UNIQUE IDENTIFICATION", 30),
            ("AUTHORITY OF INDIA", 20),
            ("UIDAI", 35),
            ("GOVERNMENT OF INDIA", 20),
            ("GOVT OF INDIA", 15),
            ("AADHAAR", 35),
            ("AADHAR", 35),
            ("ADHAAR", 30),
            ("AADHAAR NO", 30),
            ("AADHAR NO", 30),
            ("ENROLMENT NO", 25),
            ("ENROLLMENT NO", 25),
            ("MERA AADHAAR", 30),
            ("MERI PEHCHAN", 25),
            ("VID", 20),
            ("HELP@UIDAI", 20),
            ("DOB", 10),
            ("YEAR OF BIRTH", 15),
            ("FEMALE", 10),
            ("MALE", 10),
        ],
        "passport": [
            ("REPUBLIC OF INDIA", 35),
            ("PASSPORT", 40),
            ("PASSEPORT", 30),
            ("PASSPORT NO", 35),
            ("PASSPORT NUMBER", 35),
            ("TYPE P", 25),
            ("CODE IND", 25),
            ("NATIONALITY", 20),
            ("PLACE OF BIRTH", 20),
            ("PLACE OF ISSUE", 20),
            ("DATE OF ISSUE", 20),
            ("DATE OF EXPIRY", 25),
            ("MINISTRY OF EXTERNAL AFFAIRS", 35),
            ("EXTERNAL AFFAIRS", 25),
            ("GIVEN NAME", 15),
            ("SURNAME", 15),
            ("P<IND", 35),
        ],
        "voter_id": [
            ("ELECTION COMMISSION OF INDIA", 40),
            ("ELECTION COMMISSION", 35),
            ("ELECTOR PHOTO IDENTITY CARD", 40),
            ("ELECTOR'S PHOTO IDENTITY CARD", 40),
            ("ELECTORS PHOTO IDENTITY CARD", 40),
            ("ELECTOR", 30),
            ("ELECTORAL", 25),
            ("EPIC", 35),
            ("EPIC NO", 35),
            ("EPIC NUMBER", 35),
            ("PHOTO IDENTITY CARD", 30),
            ("BHARAT NIRVACHAN AAYOG", 35),
            ("BHARAT NIRVACHAN", 35),
            ("NIRVACHAN", 25),
            ("IDENTITY CARD", 20),
            ("ASSEMBLY CONSTITUENCY", 25),
            ("PARLIAMENTARY CONSTITUENCY", 20),
            ("ELECTOR'S NAME", 25),
            ("ELECTORS NAME", 25),
        ],
        "driving_licence": [
            ("DRIVING LICENCE", 40),
            ("DRIVING LICENSE", 40),
            ("UNION OF INDIA", 25),
            ("MOTOR VEHICLES", 30),
            ("MOTOR VEHICLE", 25),
            ("LICENCE TO DRIVE", 35),
            ("LICENSE TO DRIVE", 35),
            ("VALIDITY", 20),
            ("NON-TRANSPORT", 25),
            ("TRANSPORT", 20),
            ("DL NO", 35),
            ("DL NUMBER", 35),
            ("AUTHORISED TO DRIVE", 25),
            ("FORM 7", 20),
            ("SARATHI", 25),
        ],
    }

    # Regex patterns that strongly identify document types
    PATTERN_RULES = {
        "pan": [
            re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE),
            re.compile(r"PAN[:\s\-\#]*([A-Z]{5}[0-9]{4}[A-Z])", re.IGNORECASE),
        ],
        "aadhaar": [
            re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"),
            re.compile(r"\b\d{4}-\d{4}-\d{4}\b"),
            re.compile(r"\b[X\d]{4}\s[X\d]{4}\s\d{4}\b", re.IGNORECASE),
            re.compile(r"\b[X\d]{4}-[X\d]{4}-\d{4}\b", re.IGNORECASE),
            re.compile(r"\b\d{12}\b"),
            re.compile(r"VID[:\s]*\d{4}\s\d{4}\s\d{4}\s\d{4}", re.IGNORECASE),
        ],
        "passport": [
            re.compile(r"\b[A-Z][0-9]{7}\b", re.IGNORECASE),
            re.compile(r"P<[A-Z]{3}", re.IGNORECASE),
            re.compile(r"PASSPORT[\s\w]*[:\s\-\#]*([A-Z][0-9]{7})", re.IGNORECASE),
        ],
        "voter_id": [
            re.compile(r"\b[A-Z]{3}[\s\-]?[0-9]{7}\b", re.IGNORECASE),
            re.compile(r"\b[A-Z]{2}[0-9]{8}\b", re.IGNORECASE),
            re.compile(r"EPIC[:\s\-\#]*([A-Z0-9\s\-]{10,12})", re.IGNORECASE),
        ],
        "driving_licence": [
            re.compile(r"\b[A-Z]{2}[-\s]?[0-9]{2}[-\s]?[0-9]{11}\b", re.IGNORECASE),
            re.compile(r"\b[A-Z]{2}[0-9]{13,15}\b", re.IGNORECASE),
            re.compile(r"\bDL[-\s]?[A-Z0-9]{8,16}\b", re.IGNORECASE),
            re.compile(r"DL\s*NO[:\s\-]*([A-Z0-9\-]+)", re.IGNORECASE),
        ],
    }

    @classmethod
    def classify(cls, text: str) -> Dict[str, Any]:
        """
        Classify document text based on weighted keyword occurrences and regex patterns.
        """
        if not text or not text.strip():
            return {
                "classified_type": "unknown",
                "confidence": 0.0,
                "matched_keywords": [],
                "matched_patterns": [],
                "scores": {k: 0.0 for k in cls.KEYWORD_RULES.keys()},
            }

        # Normalize text for matching
        upper_text = text.upper()
        # Cleaned text with single spaces and punctuation stripped for loose matching
        clean_norm_text = re.sub(r"[^\w\s]", " ", upper_text)
        clean_norm_text = " ".join(clean_norm_text.split())

        raw_scores: Dict[str, float] = {k: 0.0 for k in cls.KEYWORD_RULES.keys()}
        matched_keywords_by_type: Dict[str, List[str]] = {k: [] for k in cls.KEYWORD_RULES.keys()}
        matched_patterns_by_type: Dict[str, List[str]] = {k: [] for k in cls.KEYWORD_RULES.keys()}

        # 1. Match Keywords
        for doc_type, rules in cls.KEYWORD_RULES.items():
            for kw, weight in rules:
                clean_kw = " ".join(re.sub(r"[^\w\s]", " ", kw).split())
                if kw in upper_text or clean_kw in clean_norm_text:
                    raw_scores[doc_type] += weight
                    matched_keywords_by_type[doc_type].append(kw)

        # 2. Match Regex Patterns (High-impact score booster: +50 points)
        for doc_type, patterns in cls.PATTERN_RULES.items():
            for pattern in patterns:
                matches = pattern.findall(text)
                if matches:
                    raw_scores[doc_type] += 50
                    sample_match = matches[0] if isinstance(matches[0], str) else str(matches[0])
                    matched_patterns_by_type[doc_type].append(sample_match)

        # 3. Direct Pattern Override: If explicit KYC pattern matches and doc has supporting context
        if matched_patterns_by_type["pan"] and raw_scores["pan"] >= 50:
            raw_scores["pan"] += 25
        if matched_patterns_by_type["aadhaar"] and raw_scores["aadhaar"] >= 50:
            raw_scores["aadhaar"] += 25
        if matched_patterns_by_type["passport"] and raw_scores["passport"] >= 50:
            raw_scores["passport"] += 25
        if matched_patterns_by_type["voter_id"] and raw_scores["voter_id"] >= 50:
            raw_scores["voter_id"] += 25
        if matched_patterns_by_type["driving_licence"] and raw_scores["driving_licence"] >= 50:
            raw_scores["driving_licence"] += 25

        # Find highest scoring type
        best_type = "unknown"
        best_score = 0.0

        for doc_type, score in raw_scores.items():
            if score > best_score:
                best_score = score
                best_type = doc_type

        # Lower threshold: 18 points is sufficient for sparse/concise synthetic documents
        if best_score < 18:
            best_type = "unknown"
            confidence = round(min(best_score / 60.0, 0.25), 2)
        else:
            # Map 18 to 100+ -> 0.50 to 0.99
            confidence = round(min(0.50 + (best_score / 120.0) * 0.49, 0.99), 2)

        return {
            "classified_type": best_type,
            "confidence": confidence,
            "matched_keywords": matched_keywords_by_type.get(best_type, []),
            "matched_patterns": matched_patterns_by_type.get(best_type, []),
            "scores": {k: round(v, 1) for k, v in raw_scores.items()},
        }
