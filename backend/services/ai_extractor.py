import os
import re
import json
import base64
import time
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from dotenv import load_dotenv
import pymupdf

# Automatically load environment variables if present
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# Official Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_SDK_AVAILABLE = True
except ImportError:
    GENAI_SDK_AVAILABLE = False

from backend.services.field_extractor import mask_aadhaar, mask_id_number, parse_date
from backend.config import Config, calculate_gemini_cost

logger = logging.getLogger(__name__)

# Standard JSON schema instructions for AI document understanding
SYSTEM_PROMPT = """You are a universal document intelligence agent.
Analyze the provided document and extract structured identity data and all key-value attributes.
Supported document types include:
- KYC Identity: 'aadhaar', 'pan', 'passport', 'voter_id', 'driving_licence'
- Financial & Commercial: 'salary_slip', 'bank_statement', 'commercial_invoice', 'tax_form_16', 'utility_bill'
- Generic / Other: 'unknown' or specific document category

CRITICAL INSTRUCTIONS:
1. Extract ONLY facts visible on the document. NEVER invent, hallucinate, or extrapolate missing values.
2. For any field that is absent, cut off, unreadable, or blurry, set the value to null.
3. Dates must be formatted as YYYY-MM-DD if recognizable; otherwise return null.
4. Estimate field-level confidence as a decimal between 0.0 and 1.0. If a field is ambiguous or partially obscured, provide a low confidence (< 0.70).
5. If any mandatory identification field is low confidence, ambiguous, or missing, set manual_review_required to true.
6. Extract all discovered key-value attributes into the 'attributes' array with normalized 0-1000 bounding boxes [ymin, xmin, ymax, xmax] if discernible.
7. Return valid, well-formed JSON matching the exact schema below.

Output JSON Schema:
{
  "document_type": string,
  "applicant_name": string or null,
  "date_of_birth": "YYYY-MM-DD" or null,
  "gender": "MALE" | "FEMALE" | "TRANSGENDER" or null,
  "identification_number": string or null,
  "address": string or null,
  "father_name": string or null,
  "issue_date": "YYYY-MM-DD" or null,
  "expiry_date": "YYYY-MM-DD" or null,
  "attributes": [
    {
      "attribute_key": "snake_case_key",
      "display_label": "Human Readable Label",
      "attribute_value": "extracted text",
      "data_type": "string" | "date" | "number" | "currency" | "boolean",
      "confidence": float 0.0-1.0,
      "bounding_box": [ymin, xmin, ymax, xmax] or null
    }
  ],
  "field_confidence": {
    "document_type": float 0.0-1.0,
    "applicant_name": float 0.0-1.0,
    "date_of_birth": float 0.0-1.0,
    "gender": float 0.0-1.0,
    "identification_number": float 0.0-1.0,
    "address": float 0.0-1.0,
    "issue_date": float 0.0-1.0,
    "expiry_date": float 0.0-1.0
  },
  "source_evidence": {
    "page_number": 1,
    "text_snippet": string or null,
    "notes": string or null
  },
  "manual_review_required": boolean,
  "ambiguous_fields": [string]
}
"""


def build_system_prompt(learned_schema: Optional[Dict[str, Any]] = None) -> str:
    """
    Constructs the system prompt, dynamically injecting in-context learned schema
    guidelines, anchor phrases, regex hints, and sanitized few-shot exemplars when available.
    """
    if not learned_schema:
        return SYSTEM_PROMPT

    v = learned_schema.get("version", 1)
    prompt = SYSTEM_PROMPT + f"\n\n--- IN-CONTEXT LEARNED SCHEMA (Version {v}) ---\n"
    prompt += "Use the following employee-verified schema guidelines, target attributes, anchor phrases, and few-shot exemplars to guide extraction:\n"
    attrs = learned_schema.get("attribute_definitions", [])
    if attrs:
        prompt += f"Target Attributes Schema:\n{json.dumps(attrs, default=str)}\n"
    anchors = learned_schema.get("anchor_phrases", {})
    if anchors:
        prompt += f"Known Text Anchor Phrases:\n{json.dumps(anchors, default=str)}\n"
    few_shots = learned_schema.get("few_shot_examples", [])
    if few_shots:
        prompt += f"Few-Shot In-Context Examples:\n{json.dumps(few_shots, default=str)}\n"
    prompt += "--- END LEARNED SCHEMA ---\n"
    return prompt


class AIDocumentExtractor:
    """
    Modular AI Document Extraction Service supporting multimodal document understanding
    via Google Gemini, OpenAI, or safe local mock extraction.
    
    Adheres to privacy rules:
    - Never logs full customer identity numbers.
    - Masks Aadhaar numbers immediately.
    - Requires company authorization for external transmission.
    - Gracefully falls back to local PyMuPDF + Tesseract OCR when credentials are unconfigured or unavailable.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 30,
        enabled: bool = True,
        db_path: Optional[str] = None
    ):
        self.enabled = enabled
        self.db_path = db_path
        self.provider = (provider or os.getenv("AI_PROVIDER", "gemini")).lower()
        self.timeout = timeout or int(os.getenv("AI_TIMEOUT", 30))

        # Resolve credentials based on provider
        if self.provider == "openai":
            self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
            self.model = model or os.getenv("AI_MODEL", "gpt-4o-mini")
            self.genai_client = None
        else:  # default to gemini
            self.api_key = api_key if api_key is not None else (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
            self.model = model or os.getenv("GEMINI_MODEL") or os.getenv("AI_MODEL", Config.GEMINI_MODEL)
            self.genai_client = None
            if GENAI_SDK_AVAILABLE and self.api_key and len(self.api_key.strip()) > 5:
                try:
                    self.genai_client = genai.Client(api_key=self.api_key)
                except Exception as e:
                    logger.warning(f"Could not initialize Google GenAI SDK client: {e}")
                    self.genai_client = None

        # Pricing configuration
        self.price_input = Config.GEMINI_PRICE_PER_M_INPUT_TOKENS
        self.price_output = Config.GEMINI_PRICE_PER_M_OUTPUT_TOKENS

    def _record_api_attempt(
        self,
        document_id: Optional[str],
        applicant_id: Optional[str],
        channel: str,
        status: str,
        prompt_tokens: Optional[int] = None,
        candidate_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        estimated_cost: Optional[float] = None,
        latency_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        request_type: str = "multimodal_extraction",
        page_number: int = 1,
        input_modality: str = "multimodal",
        transmitted_image_bytes: bool = False,
        transmitted_text: bool = False,
        per_page_estimated_cost: Optional[float] = None,
        pricing_version: str = "gemini-3.5-flash-lite-2026-v1"
    ) -> None:
        """
        Safely record an individual Gemini request-level API attempt in SQLite/PostgreSQL.
        Errors during logging are swallowed and logged as warnings so AI extraction never fails due to logging.
        """
        if self.provider != "gemini":
            return
        try:
            from backend.database.db import insert_ai_usage_log
            insert_ai_usage_log({
                "document_id": document_id,
                "applicant_id": applicant_id,
                "provider": "gemini",
                "model": self.model,
                "prompt_tokens": prompt_tokens,
                "candidate_tokens": candidate_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": estimated_cost,
                "latency_ms": latency_ms,
                "status": status,
                "error_message": self._sanitize_error(error_message) if error_message else None,
                "request_type": request_type,
                "channel": channel,
                "page_number": page_number,
                "input_modality": input_modality,
                "transmitted_image_bytes": transmitted_image_bytes,
                "transmitted_text": transmitted_text,
                "per_page_estimated_cost": per_page_estimated_cost or estimated_cost,
                "pricing_version": pricing_version,
            }, db_path=self.db_path)
        except Exception as e:
            logger.warning(f"Failed to record AI usage log attempt: {e}")

    @staticmethod
    def _is_retryable_error(exc: Exception) -> Tuple[bool, Optional[float]]:
        """Determine if an exception is transient (429/500/502/503/timeout) and extract Retry-After if present."""
        msg = str(exc).upper()
        # Never retry permanent client/auth errors
        if any(code in msg for code in ("400 ", "401 ", "403 ", "404 ", "INVALID_ARGUMENT", "PERMISSION_DENIED", "UNAUTHENTICATED", "API_KEY_INVALID")):
            return False, None
        retry_after = None
        resp = getattr(exc, "response", None)
        if resp is not None and hasattr(resp, "headers"):
            ra = resp.headers.get("Retry-After")
            if ra:
                try:
                    retry_after = float(ra)
                except ValueError:
                    pass
        if any(code in msg for code in ("429", "500", "502", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "TIMEOUT", "TIMED OUT", "CONNECTION")):
            return True, retry_after
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True, retry_after
        return False, None

    def _call_with_retry(self, fn, max_retries: int = 3, base_delay: float = 1.0):
        """Execute a Gemini API call with exponential backoff, jitter, and Retry-After support."""
        import random
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                retryable, retry_after = self._is_retryable_error(exc)
                if not retryable or attempt >= max_retries:
                    raise
                delay = retry_after if retry_after is not None else (base_delay * (2 ** attempt) + random.uniform(0.0, 0.5))
                logger.warning(f"Transient Gemini API error (attempt {attempt + 1}/{max_retries + 1}): {self._sanitize_error(str(exc))}. Retrying in {delay:.2f}s...")
                time.sleep(delay)
        raise last_exc

    @staticmethod
    def _sanitize_error(error_str: str) -> str:
        """Strip API keys and sensitive tokens from error messages."""
        if not error_str:
            return ""
        sanitized = re.sub(r"AIza[0-9A-Za-z_-]{30,}", "AIza[MASKED_KEY]", str(error_str))
        sanitized = re.sub(r"key=[^&\s'\"]+", "key=[MASKED_KEY]", sanitized)
        sanitized = re.sub(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer [MASKED_TOKEN]", sanitized)
        return sanitized

    def is_configured(self) -> bool:
        """Check whether the configured provider has valid credentials without leaking secrets."""
        if not self.enabled:
            return False
        if self.provider == "mock":
            return True
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of the AI extraction service without revealing secrets."""
        configured = self.is_configured()
        sdk_name = "google-genai SDK" if (self.provider == "gemini" and GENAI_SDK_AVAILABLE) else "standard"
        if not self.enabled:
            msg = "AI extraction is explicitly disabled in configuration (AI_EXTRACTION_ENABLED=False)."
        elif self.provider == "mock":
            msg = "AI extraction running in simulated mock mode for testing."
        elif configured:
            msg = f"AI extraction active via Google Gemini ({sdk_name}) using model '{self.model}'."
        else:
            msg = f"AI extraction credentials not configured for provider '{self.provider}'. Local OCR pipeline will be used."

        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model,
            "sdk": sdk_name,
            "configured": configured,
            "timeout_seconds": self.timeout,
            "status_message": msg
        }

    def extract_from_file(
        self,
        file_path: Path | str,
        mime_type: Optional[str] = None,
        original_filename: Optional[str] = None,
        preextracted_text: Optional[str] = None,
        document_id: Optional[str] = None,
        applicant_id: Optional[str] = None,
        learned_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute AI multimodal structured extraction on a document file.
        
        Args:
            file_path: Path to PDF, JPG, PNG document
            mime_type: MIME type (e.g. 'application/pdf', 'image/jpeg')
            original_filename: Source filename for reference
            preextracted_text: Optional text already extracted via PyMuPDF
            document_id: Database document identifier for usage telemetry
            applicant_id: Applicant identifier for usage telemetry
            learned_schema: Optional active versioned schema for in-context few-shot prompt injection
            
        Returns:
            Dict containing success status, extracted standardized KYC fields,
            and provider metadata or fallback flags.
        """
        path = Path(file_path)
        if not path.exists():
            return {
                "success": False,
                "error": f"File not found on disk: {path.name}",
                "fallback_required": True,
                "fields": None
            }

        if not self.is_configured():
            logger.info("AI extraction not configured; requesting local OCR fallback.")
            return {
                "success": False,
                "error": f"AI credentials not configured for provider '{self.provider}'.",
                "fallback_required": True,
                "fields": None
            }

        start_time = time.time()
        try:
            # 1. Prepare visual or textual representation
            image_bytes, rendered_mime, page_num = self._prepare_document_media(path)

            # 2. Dispatch to provider
            usage_dict = None
            if self.provider == "mock":
                raw_json = self._mock_extraction(path, original_filename or path.name, preextracted_text, learned_schema=learned_schema)
            elif self.provider == "openai":
                raw_json = self._call_openai(image_bytes, rendered_mime, preextracted_text)
            else:
                call_res = self._call_gemini(
                    image_bytes,
                    rendered_mime,
                    preextracted_text,
                    document_id=document_id,
                    applicant_id=applicant_id,
                    learned_schema=learned_schema
                )
                if isinstance(call_res, tuple) and len(call_res) == 2:
                    raw_json, usage_dict = call_res
                else:
                    raw_json, usage_dict = call_res, None

            latency_ms = int((time.time() - start_time) * 1000)

            # Token usage & Cost estimation
            prompt_tokens = usage_dict.get("prompt_tokens") if usage_dict else None
            candidate_tokens = usage_dict.get("candidate_tokens") if usage_dict else None
            total_tokens = usage_dict.get("total_tokens") if usage_dict else None

            estimated_cost = calculate_gemini_cost(
                prompt_tokens,
                candidate_tokens,
                self.price_input,
                self.price_output
            )

            # 3. Normalize into the standardized schema
            standardized = self._normalize_ai_response(raw_json, page_num=page_num)
            standardized["provider_metadata"] = {
                "provider": self.provider,
                "model": self.model,
                "latency_ms": latency_ms,
                "source_page": page_num,
                "prompt_tokens": prompt_tokens,
                "candidate_tokens": candidate_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": estimated_cost,
                "cost_available": estimated_cost is not None
            }

            logger.info(
                f"[AI_TELEMETRY] provider={self.provider} model={self.model} "
                f"status=SUCCESS latency_ms={latency_ms} doc_type={standardized.get('document_type', 'unknown')} "
                f"manual_review={standardized.get('manual_review_required')}"
            )

            return {
                "success": True,
                "error": None,
                "fallback_required": False,
                "fields": standardized,
                "raw_response": raw_json
            }

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            safe_error = self._sanitize_error(str(e))
            logger.warning(
                f"[AI_TELEMETRY] provider={self.provider} model={self.model} "
                f"status=FAILED latency_ms={latency_ms} error={safe_error}. Triggering local fallback."
            )
            return {
                "success": False,
                "error": f"AI extraction error: {safe_error}",
                "fallback_required": True,
                "fields": None
            }

    def _prepare_document_media(self, path: Path) -> Tuple[bytes, str, int]:
        """
        Convert file to image bytes suitable for multimodal vision APIs.
        For PDFs, renders the first page using PyMuPDF pixmap.
        """
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            doc = pymupdf.open(str(path))
            try:
                if len(doc) == 0:
                    raise ValueError("PDF contains no pages.")
                page = doc[0]
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                return img_bytes, "image/png", 1
            finally:
                doc.close()
        elif suffix in (".jpg", ".jpeg"):
            with open(path, "rb") as f:
                return f.read(), "image/jpeg", 1
        elif suffix == ".png":
            with open(path, "rb") as f:
                return f.read(), "image/png", 1
        else:
            with open(path, "rb") as f:
                return f.read(), "application/octet-stream", 1

    def _call_gemini(
        self,
        image_bytes: bytes,
        mime_type: str,
        preextracted_text: Optional[str] = None,
        document_id: Optional[str] = None,
        applicant_id: Optional[str] = None,
        learned_schema: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Execute multimodal extraction via the official Google GenAI SDK (with REST fallback).
        Captures usage_metadata from SDK or usageMetadata from REST when available.
        Records individual request-level attempts in SQLite.
        Returns (parsed_fields_dict, usage_dict).
        """
        clean_mime = mime_type if mime_type.startswith("image/") else "image/png"
        sdk_err_context = None
        system_instructions = build_system_prompt(learned_schema)

        # 1. Primary: Use official Google GenAI SDK if initialized
        if self.genai_client is not None and GENAI_SDK_AVAILABLE:
            t_sdk = time.time()
            try:
                contents = [
                    types.Part.from_bytes(data=image_bytes, mime_type=clean_mime),
                    system_instructions
                ]
                if preextracted_text:
                    contents.append(f"Embedded digital text extracted from document:\n---\n{preextracted_text[:4000]}\n---")

                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
                response = self._call_with_retry(
                    lambda: self.genai_client.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config
                    )
                )
                latency_sdk = int((time.time() - t_sdk) * 1000)
                if not response or not response.text:
                    raise ValueError("Empty response received from Google Gemini API.")

                parsed = self._safe_parse_json(response.text)

                # Capture usage_metadata from Gemini SDK response (Requirement 1 & 4)
                usage_dict = None
                usage_meta = getattr(response, "usage_metadata", None)
                if usage_meta is not None:
                    p_tokens = getattr(usage_meta, "prompt_token_count", None)
                    c_tokens = getattr(usage_meta, "candidates_token_count", None)
                    t_tokens = getattr(usage_meta, "total_token_count", None)
                    if p_tokens is not None or c_tokens is not None or t_tokens is not None:
                        usage_dict = {
                            "prompt_tokens": p_tokens,
                            "candidate_tokens": c_tokens,
                            "total_tokens": t_tokens
                        }

                cost = calculate_gemini_cost(
                    usage_dict.get("prompt_tokens") if usage_dict else None,
                    usage_dict.get("candidate_tokens") if usage_dict else None,
                    self.price_input,
                    self.price_output
                )

                self._record_api_attempt(
                    document_id=document_id,
                    applicant_id=applicant_id,
                    channel="google-genai SDK",
                    status="success",
                    prompt_tokens=usage_dict.get("prompt_tokens") if usage_dict else None,
                    candidate_tokens=usage_dict.get("candidate_tokens") if usage_dict else None,
                    total_tokens=usage_dict.get("total_tokens") if usage_dict else None,
                    estimated_cost=cost,
                    latency_ms=latency_sdk,
                    error_message=None
                )
                return parsed, usage_dict

            except Exception as sdk_err:
                latency_sdk = int((time.time() - t_sdk) * 1000)
                safe_sdk_err = self._sanitize_error(str(sdk_err))
                sdk_err_context = safe_sdk_err
                logger.warning(f"Google GenAI SDK call failed: {safe_sdk_err}. Retrying via REST fallback.")
                self._record_api_attempt(
                    document_id=document_id,
                    applicant_id=applicant_id,
                    channel="google-genai SDK",
                    status="error",
                    prompt_tokens=None,
                    candidate_tokens=None,
                    total_tokens=None,
                    estimated_cost=None,
                    latency_ms=latency_sdk,
                    error_message=safe_sdk_err
                )
                # Fall through to REST fallback below

        # 2. Secondary: Direct HTTP REST fallback
        t_rest = time.time()
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            b64_data = base64.b64encode(image_bytes).decode("utf-8")
            prompt_parts: List[Dict[str, Any]] = [
                {"text": SYSTEM_PROMPT}
            ]
            if preextracted_text:
                prompt_parts.append({
                    "text": f"Embedded digital text extracted from document:\n---\n{preextracted_text[:4000]}\n---"
                })
            prompt_parts.append({
                "inline_data": {
                    "mime_type": clean_mime,
                    "data": b64_data
                }
            })

            payload = {
                "contents": [{"parts": prompt_parts}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.1
                }
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                res_body = json.loads(response.read().decode("utf-8"))

            latency_rest = int((time.time() - t_rest) * 1000)
            candidates = res_body.get("candidates", [])
            if not candidates:
                raise ValueError("No response candidate returned by Gemini API.")

            part_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
            parsed = self._safe_parse_json(part_text)

            # Capture usageMetadata from REST fallback response (Requirement 2 & 4)
            usage_dict = None
            usage_meta = res_body.get("usageMetadata")
            if isinstance(usage_meta, dict):
                p_tokens = usage_meta.get("promptTokenCount")
                c_tokens = usage_meta.get("candidatesTokenCount")
                t_tokens = usage_meta.get("totalTokenCount")
                if p_tokens is not None or c_tokens is not None or t_tokens is not None:
                    usage_dict = {
                        "prompt_tokens": p_tokens,
                        "candidate_tokens": c_tokens,
                        "total_tokens": t_tokens
                    }

            cost = calculate_gemini_cost(
                usage_dict.get("prompt_tokens") if usage_dict else None,
                usage_dict.get("candidate_tokens") if usage_dict else None,
                self.price_input,
                self.price_output
            )

            self._record_api_attempt(
                document_id=document_id,
                applicant_id=applicant_id,
                channel="REST API",
                status="success",
                prompt_tokens=usage_dict.get("prompt_tokens") if usage_dict else None,
                candidate_tokens=usage_dict.get("candidate_tokens") if usage_dict else None,
                total_tokens=usage_dict.get("total_tokens") if usage_dict else None,
                estimated_cost=cost,
                latency_ms=latency_rest,
                error_message=None
            )
            return parsed, usage_dict

        except Exception as rest_err:
            latency_rest = int((time.time() - t_rest) * 1000)
            safe_rest_err = self._sanitize_error(str(rest_err))
            self._record_api_attempt(
                document_id=document_id,
                applicant_id=applicant_id,
                channel="REST API",
                status="error",
                prompt_tokens=None,
                candidate_tokens=None,
                total_tokens=None,
                estimated_cost=None,
                latency_ms=latency_rest,
                error_message=safe_rest_err
            )
            if sdk_err_context:
                raise RuntimeError(f"{sdk_err_context} (REST fallback also failed: {safe_rest_err})")
            raise

    def verify_model_support(self) -> Dict[str, Any]:
        """
        Verify the configured model ID against a real API request and report whether it is supported.
        Requirement 11: Real API verification without exposing secrets.
        """
        if not self.is_configured():
            return {
                "supported": False,
                "configured": False,
                "model": self.model,
                "provider": self.provider,
                "message": "AI credentials not configured."
            }

        t0 = time.time()
        try:
            if self.provider == "gemini":
                if self.genai_client is not None and GENAI_SDK_AVAILABLE:
                    res = self.genai_client.models.generate_content(
                        model=self.model,
                        contents="ping"
                    )
                    latency = int((time.time() - t0) * 1000)
                    meta = getattr(res, "usage_metadata", None)
                    p_tok = getattr(meta, "prompt_token_count", None) if meta else None
                    c_tok = getattr(meta, "candidates_token_count", None) if meta else None
                    t_tok = getattr(meta, "total_token_count", None) if meta else None
                    cost = calculate_gemini_cost(p_tok, c_tok, self.price_input, self.price_output)

                    self._record_api_attempt(
                        document_id=None,
                        applicant_id=None,
                        channel="google-genai SDK",
                        status="success",
                        prompt_tokens=p_tok,
                        candidate_tokens=c_tok,
                        total_tokens=t_tok,
                        estimated_cost=cost,
                        latency_ms=latency,
                        request_type="model_verification"
                    )

                    return {
                        "supported": True,
                        "configured": True,
                        "model": self.model,
                        "provider": "gemini",
                        "channel": "google-genai SDK",
                        "latency_ms": latency,
                        "message": f"Model '{self.model}' verified successfully via Google GenAI SDK.",
                        "usage_metadata_available": meta is not None
                    }
                else:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
                    data = json.dumps({"contents": [{"parts": [{"text": "ping"}]}]}).encode("utf-8")
                    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        body = json.loads(response.read().decode("utf-8"))
                        latency = int((time.time() - t0) * 1000)
                        u_meta = body.get("usageMetadata", {})
                        p_tok = u_meta.get("promptTokenCount")
                        c_tok = u_meta.get("candidatesTokenCount")
                        t_tok = u_meta.get("totalTokenCount")
                        cost = calculate_gemini_cost(p_tok, c_tok, self.price_input, self.price_output)

                        self._record_api_attempt(
                            document_id=None,
                            applicant_id=None,
                            channel="REST API",
                            status="success",
                            prompt_tokens=p_tok,
                            candidate_tokens=c_tok,
                            total_tokens=t_tok,
                            estimated_cost=cost,
                            latency_ms=latency,
                            request_type="model_verification"
                        )

                        return {
                            "supported": True,
                            "configured": True,
                            "model": self.model,
                            "provider": "gemini",
                            "channel": "REST API",
                            "latency_ms": latency,
                            "message": f"Model '{self.model}' verified successfully via REST endpoint.",
                            "usage_metadata_available": "usageMetadata" in body
                        }
            else:
                return {
                    "supported": True,
                    "configured": True,
                    "model": self.model,
                    "provider": self.provider,
                    "message": f"Provider '{self.provider}' configured."
                }
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            safe_err = self._sanitize_error(str(e))
            self._record_api_attempt(
                document_id=None,
                applicant_id=None,
                channel="google-genai SDK" if (self.genai_client is not None and GENAI_SDK_AVAILABLE) else "REST API",
                status="error",
                prompt_tokens=None,
                candidate_tokens=None,
                total_tokens=None,
                estimated_cost=None,
                latency_ms=latency,
                error_message=safe_err,
                request_type="model_verification"
            )
            return {
                "supported": False,
                "configured": True,
                "model": self.model,
                "provider": self.provider,
                "latency_ms": latency,
                "message": f"Model verification failed: {safe_err}"
            }

    def _call_openai(self, image_bytes: bytes, mime_type: str, preextracted_text: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute vision extraction via OpenAI chat/completions REST API.
        """
        url = "https://api.openai.com/v1/chat/completions"
        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64_data}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all structured KYC identity fields from this document."},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }
        ]
        if preextracted_text:
            messages.append({
                "role": "user",
                "content": f"Embedded text in document: {preextracted_text[:3000]}"
            })

        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            res_body = json.loads(response.read().decode("utf-8"))

        choices = res_body.get("choices", [])
        if not choices:
            raise ValueError("No response returned by OpenAI API.")
        content = choices[0].get("message", {}).get("content", "{}")
        return self._safe_parse_json(content)

    def _mock_extraction(
        self,
        path: Path,
        filename: str,
        preextracted_text: Optional[str] = None,
        learned_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Safe mock extraction for automated testing and offline development.
        Extracts heuristically from synthetic text or path to simulate multimodal AI output,
        augmented by in-context learned schema attributes.
        """
        fname = filename.lower()
        text = preextracted_text or ""
        if not text and path.exists() and path.suffix.lower() == ".pdf":
            try:
                doc = pymupdf.open(str(path))
                text = "".join(p.get_text() for p in doc)
                doc.close()
            except Exception:
                pass

        # Determine type
        doc_type = "unknown"
        # Check synonyms in filename or text
        synonym_map = {
            "salary_slip": ["salary", "payslip", "pay slip"],
            "bank_statement": ["bank", "statement", "passbook"],
            "commercial_invoice": ["invoice", "tax invoice", "bill to"],
            "tax_form_16": ["form 16", "form_16", "form16"],
            "utility_bill": ["electricity", "utility", "water bill"],
            "passport": ["passport"],
            "voter_id": ["voter", "epic"],
            "driving_licence": ["driving", "licence", "license"],
            "pan": ["pan card", "form 49a"],
            "aadhaar": ["aadhaar", "aadhar", "uidai"],
        }
        for t, syns in synonym_map.items():
            if any(s in fname for s in syns) or any(s in text.lower() for s in syns):
                doc_type = t
                break

        if doc_type == "unknown" and text:
            from backend.services.classifier import DocumentClassifier
            cls_res = DocumentClassifier.classify(text)
            if cls_res["classified_type"] != "unknown":
                doc_type = cls_res["classified_type"]

        # Simulate field detection
        name = None
        id_num = None
        dob = None
        gender = None
        exp = None
        mock_attributes = []

        if "neha" in fname or "neha kapoor" in text.lower():
            name = "NEHA KAPOOR"
            dob = "1993-11-14"
            gender = "FEMALE"
            if doc_type == "passport":
                id_num = "J4567890"
                exp = "2033-08-30"
            elif doc_type == "voter_id":
                id_num = "WXY1234567"
            elif doc_type == "pan":
                id_num = "ABCPK5566K"
            elif doc_type == "aadhaar":
                id_num = "XXXX-XXXX-9812"
            elif doc_type == "driving_licence":
                id_num = "DL-0120150078901"
                exp = "2035-08-30"

        elif "aarav" in fname or "aarav mehta" in text.lower():
            name = "AARAV MEHTA"
            dob = "1991-03-22"
            gender = "MALE"
            id_num = "ABCDE1234F" if doc_type == "pan" else "XXXX-XXXX-4321"

        elif "dev" in fname or "dev patel" in text.lower():
            name = "DEV PATEL"
            dob = "1988-10-12"
            gender = "MALE"
            if "expired" in fname or doc_type == "passport":
                id_num = "M8765432"
                exp = "2020-01-10"
            else:
                id_num = "DPXYZ1234K"

        # Specialized mock data for business/financial document types
        if doc_type == "salary_slip":
            name = name or "RAHUL SHARMA"
            id_num = "EMP-9021"
            mock_attributes = [
                {"attribute_key": "employee_name", "display_label": "Employee Name", "attribute_value": name, "data_type": "string", "confidence": 0.96, "bounding_box": [120, 200, 150, 450]},
                {"attribute_key": "employee_id", "display_label": "Employee ID", "attribute_value": id_num, "data_type": "string", "confidence": 0.95, "bounding_box": [160, 200, 185, 350]},
                {"attribute_key": "basic_salary", "display_label": "Basic Salary", "attribute_value": "45000.00", "data_type": "currency", "confidence": 0.94, "bounding_box": [300, 500, 325, 600]},
                {"attribute_key": "net_salary", "display_label": "Net Salary", "attribute_value": "68500.00", "data_type": "currency", "confidence": 0.98, "bounding_box": [550, 500, 580, 620]},
                {"attribute_key": "gross_salary", "display_label": "Gross Salary", "attribute_value": "75000.00", "data_type": "currency", "confidence": 0.93, "bounding_box": [500, 500, 525, 620]},
            ]
        elif doc_type == "bank_statement":
            name = name or "PRIYA VERMA"
            id_num = "987654321012"
            mock_attributes = [
                {"attribute_key": "account_holder_name", "display_label": "Account Holder Name", "attribute_value": name, "data_type": "string", "confidence": 0.95, "bounding_box": [100, 150, 130, 400]},
                {"attribute_key": "account_number", "display_label": "Account Number", "attribute_value": id_num, "data_type": "string", "confidence": 0.97, "bounding_box": [140, 150, 165, 380]},
                {"attribute_key": "ifsc_code", "display_label": "IFSC Code", "attribute_value": "HDFC0001234", "data_type": "string", "confidence": 0.96, "bounding_box": [170, 150, 195, 320]},
                {"attribute_key": "closing_balance", "display_label": "Closing Balance", "attribute_value": "142500.50", "data_type": "currency", "confidence": 0.95, "bounding_box": [600, 600, 630, 750]},
            ]
        elif doc_type == "commercial_invoice":
            name = name or "ACME ENTERPRISES"
            id_num = "INV-2026-089"
            exp = "2026-12-31"
            mock_attributes = [
                {"attribute_key": "invoice_number", "display_label": "Invoice Number", "attribute_value": id_num, "data_type": "string", "confidence": 0.98, "bounding_box": [80, 650, 110, 850]},
                {"attribute_key": "bill_to_name", "display_label": "Bill To", "attribute_value": name, "data_type": "string", "confidence": 0.94, "bounding_box": [150, 100, 180, 350]},
                {"attribute_key": "total_amount", "display_label": "Total Amount", "attribute_value": "45000.00", "data_type": "currency", "confidence": 0.97, "bounding_box": [650, 600, 680, 780]},
                {"attribute_key": "gstin", "display_label": "GSTIN", "attribute_value": "27AABCB1234F1Z5", "data_type": "string", "confidence": 0.96, "bounding_box": [120, 100, 145, 350]},
            ]
        elif doc_type == "utility_bill":
            name = name or "ANIL KUMAR"
            id_num = "CN-8849201"
            exp = "2026-12-15"
            mock_attributes = [
                {"attribute_key": "consumer_name", "display_label": "Consumer Name", "attribute_value": name, "data_type": "string", "confidence": 0.95, "bounding_box": [110, 100, 140, 350]},
                {"attribute_key": "consumer_number", "display_label": "Consumer Number", "attribute_value": id_num, "data_type": "string", "confidence": 0.97, "bounding_box": [150, 100, 175, 300]},
                {"attribute_key": "bill_amount", "display_label": "Bill Amount", "attribute_value": "2450.00", "data_type": "currency", "confidence": 0.96, "bounding_box": [450, 500, 480, 650]},
            ]

        # Enrich mock attributes from learned_schema if present
        if learned_schema and text:
            attr_defs = learned_schema.get("attribute_definitions", [])
            anchors = learned_schema.get("anchor_phrases", {})
            regexes = learned_schema.get("regex_patterns", {})
            existing_attr_keys = {a.get("attribute_key") for a in mock_attributes if isinstance(a, dict)}
            for ad in attr_defs:
                ak = ad.get("attribute_key")
                if not ak or ak in existing_attr_keys:
                    continue
                extracted_val = None
                # Check regex
                rx = regexes.get(ak) or ad.get("regex_pattern")
                if rx:
                    try:
                        rm = re.search(rx, text)
                        if rm:
                            extracted_val = rm.group(0).strip()
                    except Exception:
                        pass
                # Check anchor phrases
                if not extracted_val and ak in anchors:
                    for anc in anchors[ak]:
                        pattern = re.escape(anc) + r"\s*([^\n\r]+)"
                        try:
                            am = re.search(pattern, text, re.IGNORECASE)
                            if am:
                                extracted_val = am.group(1).strip()
                                break
                        except Exception:
                            pass
                if extracted_val:
                    mock_attributes.append({
                        "attribute_key": ak,
                        "display_label": ad.get("display_label") or ak.replace("_", " ").title(),
                        "attribute_value": extracted_val,
                        "data_type": ad.get("data_type", "string"),
                        "confidence": 0.96,
                        "bounding_box": ad.get("typical_bbox") or [200, 100, 230, 400]
                    })

        # Ambiguity check
        is_kyc = doc_type in ("aadhaar", "pan", "passport", "voter_id", "driving_licence")
        manual_review = False
        ambiguous = []
        if is_kyc and (not id_num or not name):
            manual_review = True
            ambiguous.append("mandatory_field_missing")
        elif not is_kyc and doc_type != "unknown" and not mock_attributes and not id_num:
            manual_review = True
            ambiguous.append("mandatory_field_missing")
        if exp and exp < "2026-01-01":
            manual_review = True
            ambiguous.append("expired_document")

        return {
            "document_type": doc_type,
            "applicant_name": name,
            "date_of_birth": dob,
            "gender": gender,
            "identification_number": id_num,
            "address": "Delhi, India" if name else None,
            "father_name": "SUNIL KAPOOR" if "kapoor" in fname else None,
            "issue_date": "2023-08-31" if doc_type == "passport" else None,
            "expiry_date": exp,
            "attributes": mock_attributes,
            "field_confidence": {
                "document_type": 0.98 if doc_type != "unknown" else 0.30,
                "applicant_name": 0.95 if name else 0.0,
                "date_of_birth": 0.92 if dob else 0.0,
                "gender": 0.95 if gender else 0.0,
                "identification_number": 0.96 if id_num else 0.0,
                "address": 0.85 if name else 0.0,
                "issue_date": 0.90 if doc_type == "passport" else 0.0,
                "expiry_date": 0.92 if exp else 0.0
            },
            "source_evidence": {
                "page_number": 1,
                "text_snippet": (text[:120].strip() or f"Visual inspection of {filename}"),
                "notes": "Simulated AI visual understanding."
            },
            "manual_review_required": manual_review,
            "ambiguous_fields": ambiguous
        }

    def _normalize_ai_response(self, raw: Dict[str, Any], page_num: int = 1) -> Dict[str, Any]:
        """
        Validate, normalize and enforce safety requirements on AI outputs:
        - Strict Aadhaar masking.
        - Canonical date formatting.
        - Field confidence bounds.
        - Dual-key compatibility (applicant_name <-> name, date_of_birth <-> dob, identification_number <-> id_number).
        - Dynamic attribute synthesis with normalized bounding boxes.
        """
        doc_type = str(raw.get("document_type", "unknown")).lower().strip()
        cleaned_doc_type = re.sub(r"[^a-z0-9_]", "_", doc_type).strip("_")
        if not cleaned_doc_type:
            cleaned_doc_type = "unknown"
        doc_type = cleaned_doc_type

        raw_id = raw.get("identification_number")
        id_number = str(raw_id).strip() if raw_id else None
        masked_id = None

        if id_number:
            # Privacy enforcement: mask Aadhaar numbers immediately
            if doc_type == "aadhaar" or len(re.sub(r"\D", "", id_number)) == 12:
                id_number = mask_aadhaar(id_number)
                masked_id = id_number
            else:
                masked_id = mask_id_number(id_number, 4)

        # Dates
        dob = parse_date(raw.get("date_of_birth"))
        issue_date = parse_date(raw.get("issue_date"))
        expiry_date = parse_date(raw.get("expiry_date"))

        # Gender normalization
        raw_gender = str(raw.get("gender", "")).upper()
        if "FEMALE" in raw_gender or raw_gender == "F":
            gender = "FEMALE"
        elif "MALE" in raw_gender or raw_gender == "M":
            gender = "MALE"
        elif "TRANS" in raw_gender:
            gender = "TRANSGENDER"
        else:
            gender = None

        applicant_name = raw.get("applicant_name")
        if applicant_name:
            applicant_name = re.sub(r"\s+", " ", str(applicant_name)).strip().upper()

        father_name = raw.get("father_name")
        if father_name:
            father_name = re.sub(r"\s+", " ", str(father_name)).strip().upper()

        address = raw.get("address")
        if address:
            address = re.sub(r"\s+", " ", str(address)).strip()

        # Field confidence
        raw_conf = raw.get("field_confidence") or {}
        field_confidence = {}
        for k in ["document_type", "applicant_name", "date_of_birth", "gender", "identification_number", "address", "issue_date", "expiry_date"]:
            val = raw_conf.get(k)
            try:
                field_confidence[k] = max(0.0, min(1.0, float(val))) if val is not None else 0.0
            except (ValueError, TypeError):
                field_confidence[k] = 0.0

        # Dynamic Universal Attributes List
        raw_attributes = raw.get("attributes") or []
        normalized_attributes: List[Dict[str, Any]] = []
        seen_attr_keys = set()

        if isinstance(raw_attributes, list):
            for attr in raw_attributes:
                if not isinstance(attr, dict):
                    continue
                k = str(attr.get("attribute_key") or attr.get("name") or "").strip().lower().replace(" ", "_")
                k = re.sub(r"[^a-z0-9_]", "", k)
                v = str(attr.get("attribute_value") or attr.get("value") or "").strip()
                if not k or not v:
                    continue
                lbl = str(attr.get("display_label") or attr.get("label") or k.replace("_", " ").title())
                dtype = str(attr.get("data_type") or "string").lower()
                if dtype not in ("string", "date", "number", "currency", "boolean"):
                    dtype = "string"
                try:
                    c_score = max(0.0, min(1.0, float(attr.get("confidence") or attr.get("confidence_score") or 0.90)))
                except (ValueError, TypeError):
                    c_score = 0.85

                bbox = attr.get("bounding_box") or attr.get("bbox")
                bbox_dict = None
                if isinstance(bbox, list) and len(bbox) == 4:
                    bbox_dict = {
                        "ymin": max(0, min(1000, int(bbox[0]))),
                        "xmin": max(0, min(1000, int(bbox[1]))),
                        "ymax": max(0, min(1000, int(bbox[2]))),
                        "xmax": max(0, min(1000, int(bbox[3]))),
                    }
                elif isinstance(bbox, dict) and all(coord in bbox for coord in ("ymin", "xmin", "ymax", "xmax")):
                    bbox_dict = {
                        "ymin": max(0, min(1000, int(bbox["ymin"]))),
                        "xmin": max(0, min(1000, int(bbox["xmin"]))),
                        "ymax": max(0, min(1000, int(bbox["ymax"]))),
                        "xmax": max(0, min(1000, int(bbox["xmax"]))),
                    }

                normalized_attributes.append({
                    "attribute_key": k,
                    "display_label": lbl,
                    "attribute_value": v,
                    "data_type": dtype,
                    "confidence_score": c_score,
                    "bounding_box": bbox_dict,
                    "page_number": int(attr.get("page_number", page_num)),
                    "provenance": attr.get("provenance", f"ai_{self.provider}"),
                    "is_custom": bool(attr.get("is_custom", False))
                })
                seen_attr_keys.add(k)

        # Synthesize top-level identity fields into normalized_attributes if not present
        field_mappings = [
            ("applicant_name", "Applicant Name", applicant_name, "string", field_confidence.get("applicant_name", 0.90)),
            ("identification_number", "ID Number", masked_id or id_number, "string", field_confidence.get("identification_number", 0.90)),
            ("date_of_birth", "Date of Birth", dob, "date", field_confidence.get("date_of_birth", 0.85)),
            ("gender", "Gender", gender, "string", field_confidence.get("gender", 0.85)),
            ("address", "Address", address, "string", field_confidence.get("address", 0.80)),
            ("father_name", "Father's Name", father_name, "string", 0.80),
            ("issue_date", "Date of Issue", issue_date, "date", field_confidence.get("issue_date", 0.80)),
            ("expiry_date", "Date of Expiry", expiry_date, "date", field_confidence.get("expiry_date", 0.85)),
        ]
        for key, label, val, dtype, conf in field_mappings:
            if val and key not in seen_attr_keys:
                normalized_attributes.append({
                    "attribute_key": key,
                    "display_label": label,
                    "attribute_value": str(val),
                    "data_type": dtype,
                    "confidence_score": conf,
                    "bounding_box": None,
                    "page_number": page_num,
                    "provenance": f"ai_{self.provider}",
                    "is_custom": False
                })
                seen_attr_keys.add(key)

        # Review triggers: low confidence or missing mandatory fields
        manual_review = bool(raw.get("manual_review_required", False))
        ambiguous = list(raw.get("ambiguous_fields") or [])

        is_kyc = doc_type in ("aadhaar", "pan", "passport", "voter_id", "driving_licence")
        if is_kyc:
            if not applicant_name or field_confidence.get("applicant_name", 0) < 0.70:
                manual_review = True
                if "applicant_name" not in ambiguous:
                    ambiguous.append("applicant_name")

            if not id_number or field_confidence.get("identification_number", 0) < 0.70:
                manual_review = True
                if "identification_number" not in ambiguous:
                    ambiguous.append("identification_number")
        else:
            if not normalized_attributes and not id_number and not applicant_name:
                manual_review = True
                if "document_attributes_missing" not in ambiguous:
                    ambiguous.append("document_attributes_missing")

        source_evidence = raw.get("source_evidence") or {}
        source_evidence["page_number"] = page_num

        return {
            # Standardized schema fields
            "document_type": doc_type,
            "applicant_name": applicant_name,
            "date_of_birth": dob,
            "gender": gender,
            "identification_number": id_number,
            "masked_id": masked_id,
            "address": address,
            "father_name": father_name,
            "issue_date": issue_date,
            "expiry_date": expiry_date,
            "attributes": normalized_attributes,
            "extraction_method": f"ai_{self.provider}",
            "field_confidence": field_confidence,
            "source_evidence": source_evidence,
            "manual_review_required": manual_review,
            "ambiguous_fields": ambiguous,

            # Backward-compatibility aliases for local validation & UI
            "name": applicant_name,
            "dob": dob,
            "id_number": id_number,
            "extra_fields": {
                "address": address,
                "date_of_issue": issue_date,
                "ai_confidence": field_confidence,
                "father_name": father_name
            }
        }

    def classify_document(
        self,
        file_path: Path,
        mime_type: Optional[str] = None,
        original_filename: Optional[str] = None,
        document_id: Optional[str] = None,
        applicant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        AI-first multimodal document classification using registered PostgreSQL document types.
        Returns document_type, subtype, issuing_authority, language, is_readable,
        is_incomplete_or_damaged, confidence, reasoning, and usage telemetry.
        """
        t0 = time.time()
        if not self.is_configured():
            return {"success": False, "document_type": "unknown", "confidence": 0.0, "error": "Gemini AI is not configured."}
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "document_type": "unknown", "confidence": 0.0, "error": f"File not found: {path.name}"}

        # Load registered active document types dynamically from PostgreSQL
        registered_types = []
        try:
            from backend.database.db import list_document_types
            for dt in list_document_types(active_only=True, db_path=self.db_path):
                tk = dt.get("type_key") or dt.get("id")
                if tk and tk != "unknown":
                    registered_types.append(f"{tk} ({dt.get('display_name', tk)})")
        except Exception:
            pass
        types_str = ", ".join(registered_types) if registered_types else "aadhaar, pan, passport, voter_id, driving_licence, salary_slip, bank_statement, commercial_invoice, tax_form_16, utility_bill"

        prompt = (
            "You are a document classification specialist. Classify the provided document image/PDF.\n"
            f"Registered document types: {types_str}.\n"
            "If the document does not clearly match any registered type, set document_type to 'unknown'. Do NOT invent types.\n"
            "Return valid JSON matching:\n"
            '{"document_type": "type_key or unknown", "subtype": string or null, "issuing_authority": string or null, '
            '"language": string or null, "is_readable": boolean, "is_incomplete_or_damaged": boolean, '
            '"confidence": float 0.0-1.0, "reasoning": "concise evidence"}'
        )

        try:
            raw_bytes = path.read_bytes()
            ext = path.suffix.lower()
            actual_mime = mime_type or ("application/pdf" if ext == ".pdf" else ("image/png" if ext == ".png" else "image/jpeg"))
            if self.provider == "mock":
                return {"success": True, "document_type": "pan", "confidence": 0.95, "is_readable": True, "is_incomplete_or_damaged": False, "reasoning": "Mock classification", "latency_ms": 1}

            parts = [types.Part.from_bytes(data=raw_bytes, mime_type=actual_mime), prompt]
            response = self._call_with_retry(
                lambda: self.genai_client.models.generate_content(
                    model=self.model,
                    contents=parts,
                    config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json")
                )
            )
            latency_ms = int((time.time() - t0) * 1000)
            parsed = self._safe_parse_json(response.text)
            usage = getattr(response, "usage_metadata", None)
            p_tok = getattr(usage, "prompt_token_count", 0) or 0 if usage else 0
            c_tok = getattr(usage, "candidates_token_count", 0) or 0 if usage else 0
            t_tok = getattr(usage, "total_token_count", p_tok + c_tok) or 0 if usage else 0
            cost = calculate_gemini_cost(p_tok, c_tok)
            self._record_api_attempt(
                document_id=document_id, applicant_id=applicant_id, channel="sdk",
                prompt_tokens=p_tok, candidate_tokens=c_tok, total_tokens=t_tok,
                estimated_cost=cost, latency_ms=latency_ms, status="success",
                request_type="multimodal_classification", input_modality="multimodal"
            )
            return {
                "success": True,
                "document_type": str(parsed.get("document_type") or "unknown").lower().strip(),
                "subtype": parsed.get("subtype"),
                "issuing_authority": parsed.get("issuing_authority"),
                "language": parsed.get("language"),
                "is_readable": bool(parsed.get("is_readable", True)),
                "is_incomplete_or_damaged": bool(parsed.get("is_incomplete_or_damaged", False)),
                "confidence": float(parsed.get("confidence", 0.0)),
                "reasoning": parsed.get("reasoning", ""),
                "latency_ms": latency_ms,
                "tokens": {"prompt": p_tok, "candidate": c_tok, "total": t_tok, "cost": cost}
            }
        except Exception as e:
            latency_ms = int((time.time() - t0) * 1000)
            self._record_api_attempt(
                document_id=document_id, applicant_id=applicant_id, channel="sdk",
                latency_ms=latency_ms, status="error", error_message=str(e),
                request_type="multimodal_classification", input_modality="multimodal"
            )
            return {"success": False, "document_type": "unknown", "confidence": 0.0, "error": self._sanitize_error(str(e)), "latency_ms": latency_ms}

    @staticmethod
    def _safe_parse_json(text: str) -> Dict[str, Any]:
        """Safely parse JSON from raw text, removing markdown code fences if present."""
        clean = text.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*", "", clean)
            clean = re.sub(r"\s*```$", "", clean)
        return json.loads(clean.strip())
