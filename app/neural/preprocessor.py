"""
preprocessor.py — Text Preprocessing & Feature Extraction สำหรับ Neuro AI Layer

หน้าที่:
1. ทำ Text Normalization (ลบช่องว่างส่วนเกิน, จัดรูปแบบอักขระภาษาไทยและอังกฤษ)
2. ตรวจจับภาษา (Thai / English / Mixed)
3. ตัดคำและสกัด Feature:
   - ใช้ PyThaiNLP สำหรับภาษาไทย (Normalize อักขระซ้ำ, ตัดคำไทย)
   - ใช้ spaCy สำหรับภาษาอังกฤษ (Lemmatization, Tokenization)
4. สรุปผลลัพธ์เป็น PreprocessedFeature เพื่อส่งเสริมให้ Gemini API เข้าใจคำสั่งได้แม่นยำยิ่งขึ้น
"""

import re
from typing import List, Optional
from pydantic import BaseModel, Field

# ==============================================================================
# IMPORTS แบบยืดหยุ่น (Fallback หากยังไม่ได้ติดตั้ง pythainlp หรือ spacy)
# ==============================================================================
try:
    import pythainlp
    from pythainlp.util import normalize as thai_normalize
    from pythainlp.tokenize import word_tokenize as thai_word_tokenize
    PYTHAINLP_AVAILABLE = True
except ImportError:
    PYTHAINLP_AVAILABLE = False

try:
    import spacy
    try:
        nlp_en = spacy.load("en_core_web_sm")
    except Exception:
        nlp_en = None
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    nlp_en = None


# ==============================================================================
# DATA MODEL สำหรับผลลัพธ์การ Preprocess
# ==============================================================================
class PreprocessedFeature(BaseModel):
    """ผลลัพธ์หลังผ่านกระบวนการ Preprocessing & Feature Extraction"""
    raw_text: str = Field(..., description="ข้อความดิบดั้งเดิมจากผู้เล่น")
    normalized_text: str = Field(..., description="ข้อความที่ผ่านการทำ Normalization แล้ว")
    language: str = Field("th", description="ภาษาหลักที่ตรวจพบ ('th', 'en', 'mixed')")
    tokens: List[str] = Field(default_factory=list, description="รายการคำที่ตัดได้")
    keywords: List[str] = Field(default_factory=list, description="คำสำคัญ/คีย์เวิร์ดที่สกัดได้")


# ==============================================================================
# CLASS PREPROCESSOR
# ==============================================================================
class TextPreprocessor:
    """คลาสประมวลผลข้อความล่วงหน้าก่อนส่งให้ Gemini API"""

    @staticmethod
    def detect_language(text: str) -> str:
        """ตรวจจับว่าเป็นภาษาไทย ภาษาอังกฤษ หรือผสม"""
        has_thai = bool(re.search(r"[\u0E00-\u0E7F]", text))
        has_eng = bool(re.search(r"[a-zA-Z]", text))

        if has_thai and has_eng:
            return "mixed"
        elif has_thai:
            return "th"
        elif has_eng:
            return "en"
        return "th"

    @staticmethod
    def normalize(text: str) -> str:
        """ทำความสะอาดและจัดรูปแบบข้อความ"""
        # ลบ whitespace ส่วนเกิน
        text = re.sub(r"\s+", " ", text).strip()

        # ทำ Normalization ภาษาไทยด้วย PyThaiNLP (ถ้ามี)
        if PYTHAINLP_AVAILABLE:
            text = thai_normalize(text)

        return text

    def process(self, text: str) -> PreprocessedFeature:
        """ประมวลผลข้อความ สกัด tokens และ keywords

        Args:
            text (str): ข้อความดิบจากผู้เล่น

        Returns:
            PreprocessedFeature: ข้อมูลที่สกัดเรียบร้อยแล้ว
        """
        normalized_text = self.normalize(text)
        lang = self.detect_language(normalized_text)
        tokens: List[str] = []
        keywords: List[str] = []

        # ---------------------------------------------------------
        # 1) ภาษาไทย / Mixed: ใช้ PyThaiNLP
        # ---------------------------------------------------------
        if PYTHAINLP_AVAILABLE and lang in ("th", "mixed"):
            tokens = thai_word_tokenize(normalized_text, engine="newmm", keep_whitespace=False)
        
        # ---------------------------------------------------------
        # 2) ภาษาอังกฤษ: ใช้ spaCy
        # ---------------------------------------------------------
        if SPACY_AVAILABLE and nlp_en and lang in ("en", "mixed"):
            doc = nlp_en(normalized_text)
            en_tokens = [token.lemma_.lower() for token in doc if not token.is_space and not token.is_punct]
            tokens.extend(en_tokens)
        
        # Fallback หากไม่มี library ตัดคำ
        if not tokens:
            tokens = [w for w in normalized_text.split() if w]

        # สกัดคีย์เวิร์ด (กรองคำสั้น/คำหยุดเบื้องต้น)
        keywords = list(dict.fromkeys([t for t in tokens if len(t) > 1]))

        return PreprocessedFeature(
            raw_text=text,
            normalized_text=normalized_text,
            language=lang,
            tokens=tokens,
            keywords=keywords,
        )


# Singleton Instance สำหรับเรียกใช้งานสะดวก
preprocessor = TextPreprocessor()


def preprocess_text(text: str) -> PreprocessedFeature:
    """ฟังก์ชัน Utility สำหรับเรียกใช้งานแบบง่าย"""
    return preprocessor.process(text)