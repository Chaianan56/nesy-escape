"""
key_check.py — ตรวจว่าคีย์ AI แต่ละตัวใช้ได้จริงหรือไม่ โดยไม่ใช้โควตา

เดิมหน้าต่าง "เลือกบริการ AI" ดูแค่ว่ามีคีย์เขียนไว้ใน .env หรือเปล่า
คีย์ที่พิมพ์ผิด หมดอายุ หรือถูกปิดสิทธิ์จึงขึ้นว่า "พร้อมใช้งาน" และปุ่มของบริการนั้นยังกดได้

ที่นี่ถามข้อมูลโมเดลหรือรายชื่อโมเดลจากผู้ให้บริการ ซึ่งต้องใช้คีย์แต่ไม่นับเป็นการเรียก AI
(Gemini: models.get, Groq/OpenAI: GET /v1/models) แล้วจำผลไว้ CHECK_TTL วินาที
ผลมีสามแบบ: True ใช้ได้, False ผู้ให้บริการปฏิเสธคีย์, None ติดต่อผู้ให้บริการไม่ได้
None ก็นับว่าใช้ไม่ได้ตอนนี้ (เรียกไปก็ไม่ถึง) แต่ตรวจใหม่หลัง RETRY_UNREACHABLE วินาที
เน็ตกระตุกครู่เดียวจึงไม่ทำให้คีย์หายไปนาน

การตรวจนี้รู้แค่ว่าคีย์ถูกต้อง ไม่รู้ว่าโควตาเหลือไหม โควตาดูจากผลการเรียกจริงใน gemini_client
ระหว่างรัน pytest ไม่ตรวจ (ไม่ต่อเน็ต) เว้นแต่ตั้ง KEY_CHECK=on
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

CHECK_TTL = 600          # ตรวจซ้ำทุก 10 นาที
RETRY_UNREACHABLE = 60   # ติดต่อไม่ได้ ลองใหม่เร็วกว่า
TIMEOUT_SECONDS = 6
# โควตารายวันของ Gemini free tier เริ่มนับใหม่ตอนเที่ยงคืนเวลาแปซิฟิก
QUOTA_RESET_ZONE = ZoneInfo("America/Los_Angeles")

OTHER_PROVIDERS = {
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1/models"),
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1/models"),
}

_results: dict[str, tuple[Optional[bool], float]] = {}   # ลายนิ้วมือของคีย์ -> (ผล, เวลาที่ตรวจ)


def _enabled() -> bool:
    setting = os.getenv("KEY_CHECK", "").strip().lower()
    if setting in ("0", "off", "false", "no"):
        return False
    return setting in ("1", "on", "true", "yes") or "pytest" not in sys.modules


def _fingerprint(provider: str, key: str) -> str:
    """จำผลด้วยแฮชของคีย์ ไม่เก็บตัวคีย์ และเปลี่ยนคีย์ใน .env แล้วจะตรวจใหม่เอง"""
    return hashlib.sha256(f"{provider}:{key}".encode()).hexdigest()[:16]


def gemini_key_of(client) -> Optional[str]:
    return getattr(getattr(client, "_api_client", None), "api_key", None)


def is_key_rejection(exc: BaseException) -> bool:
    """ผู้ให้บริการบอกว่าคีย์ใช้ไม่ได้ (ผิด หมดอายุ หรือไม่มีสิทธิ์) ไม่ใช่ปัญหาชั่วคราว"""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    text = str(exc).upper()
    return (code in (401, 403)
            or any(s in text for s in ("API_KEY_INVALID", "API KEY NOT VALID", "API KEY EXPIRED",
                                       "PERMISSION_DENIED", "UNAUTHENTICATED")))


def _check_gemini(client, model: str) -> Optional[bool]:
    try:
        from google.genai import types
        client.models.get(model=model, config=types.GetModelConfig(
            http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000)))
        return True
    except Exception as exc:
        return False if is_key_rejection(exc) else None


def _check_bearer(url: str, key: str) -> Optional[bool]:
    import httpx
    try:
        response = httpx.get(url, headers={"Authorization": "Bearer " + key},
                             timeout=httpx.Timeout(float(TIMEOUT_SECONDS), connect=4.0))
    except Exception:
        return None
    if response.status_code in (401, 403):
        return False
    return True if response.is_success else None


def refresh(gemini_clients: list, model: str, force: bool = False) -> None:
    """ตรวจคีย์ที่ยังไม่เคยตรวจหรือผลเก่ากว่า CHECK_TTL พร้อมกันทุกตัว (ใช้เวลาราวหนึ่งวินาที)"""
    if not _enabled():
        return
    now = time.time()
    jobs: list[tuple[str, Callable[[], Optional[bool]]]] = []

    def stale(fp: str) -> bool:
        if force or fp not in _results:
            return True
        outcome, checked_at = _results[fp]
        return now - checked_at > (CHECK_TTL if outcome is not None else RETRY_UNREACHABLE)

    for client in gemini_clients:
        key = gemini_key_of(client)
        if key and stale(fp := _fingerprint("gemini", key)):
            jobs.append((fp, lambda c=client: _check_gemini(c, model)))
    for provider, (env, url) in OTHER_PROVIDERS.items():
        key = os.getenv(env, "").strip()
        if key and stale(fp := _fingerprint(provider, key)):
            jobs.append((fp, lambda u=url, k=key: _check_bearer(u, k)))
    if not jobs:
        return
    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
        outcomes = list(pool.map(lambda job: job[1](), jobs))
    for (fp, _), outcome in zip(jobs, outcomes):
        _results[fp] = (outcome, time.time())


def gemini_valid(client) -> Optional[bool]:
    key = gemini_key_of(client)
    return _results.get(_fingerprint("gemini", key), (None, 0))[0] if key else None


def other_valid(provider: str) -> Optional[bool]:
    key = os.getenv(OTHER_PROVIDERS[provider][0], "").strip()
    return _results.get(_fingerprint(provider, key), (None, 0))[0] if key else None


def unreachable(provider: str, client=None) -> bool:
    """ตรวจแล้วแต่ติดต่อผู้ให้บริการไม่ได้"""
    key = gemini_key_of(client) if provider == "gemini" else os.getenv(OTHER_PROVIDERS[provider][0], "").strip()
    fp = _fingerprint(provider, key) if key else None
    return fp in _results and _results[fp][0] is None


def mark_gemini_invalid(client) -> None:
    """การเรียกจริงโดนปฏิเสธคีย์ จำไว้เลยโดยไม่ต้องรอรอบตรวจถัดไป"""
    key = gemini_key_of(client)
    if key:
        _results[_fingerprint("gemini", key)] = (False, time.time())


def daily_quota_resets_at(since: float) -> float:
    """เวลาที่โควตารายวันซึ่งหมดตอน since จะกลับมา (เที่ยงคืนถัดไปตามเวลาแปซิฟิก)"""
    hit = datetime.fromtimestamp(since, QUOTA_RESET_ZONE)
    midnight = (hit + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()
