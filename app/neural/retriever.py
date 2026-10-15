"""
app/neural/retriever.py — Dynamic kNN Few-Shot Retriever & N-gram Semantic Candidate Scorer

หน้าที่:
1. Character N-gram Tokenizer สำหรับภาษาไทย (ไม่พึ่งพาช่องว่างคำ)
2. KNNExampleRetriever: ดึง Top-K Few-shot Examples ที่ใกล้เคียงกับข้อความของผู้เล่นมากที่สุดจาก Memory Bank
3. Semantic Candidate Scorer: คำนวณคะแนนความเกี่ยวข้องของ Entity สำหรับ Dynamic Pruning
"""

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
BANK_PATH = DATA_DIR / "neural_training_bank.json"


def get_char_ngrams(text: str, n_range: Tuple[int, int] = (2, 3)) -> Set[str]:
    """สกัด Character N-grams จากข้อความภาษาไทย (เช่น 2-gram และ 3-gram)

    ข้อดีสำหรับภาษาไทย:
    - ไม่ต้องตัดคำด้วยช่องว่าง
    - ทนทานต่อการพิมพ์ผิด (Typo), คำย่อ, และคำติดกัน
    """
    clean = re.sub(r"[\s\.,\/#!$%\^&\*;:{}=\-_`~()\"']", "", text.lower())
    if not clean:
        return set()
    ngrams = set()
    for n in range(n_range[0], n_range[1] + 1):
        if len(clean) >= n:
            for i in range(len(clean) - n + 1):
                ngrams.add(clean[i : i + n])
        else:
            ngrams.add(clean)
    return ngrams


def calculate_ngram_similarity(text_a: str, text_b: str, n_range: Tuple[int, int] = (2, 3)) -> float:
    """คำนวณ Dice Coefficient ระหว่างสองข้อความโดยใช้ Character N-grams

    Dice = 2 * |A ∩ B| / (|A| + |B|)
    ค่าคืนเป็น 0.0 (ไม่เกี่ยวข้องกัน) ถึง 1.0 (ตรงกันเป๊ะ)
    """
    grams_a = get_char_ngrams(text_a, n_range)
    grams_b = get_char_ngrams(text_b, n_range)
    if not grams_a or not grams_b:
        return 0.0
    intersection = len(grams_a.intersection(grams_b))
    return (2.0 * intersection) / (len(grams_a) + len(grams_b))


class KNNExampleRetriever:
    """Retriever สำหรับค้นหาตัวอย่าง Few-shot จาก Memory Bank (In-Context Learning)

    ความสามารถ:
    - In-memory Indexing: รันรวดเร็วระดับ < 1 ms
    - Zero External Dependencies: ทำงานด้วย pure Python
    - Active Learning: สามารถเพิ่มตัวอย่างใหม่เข้า Bank แบบไดนามิกได้ทันที
    """

    def __init__(self, bank_file: Optional[Path] = None):
        self.bank_file = bank_file or BANK_PATH
        self.examples: List[Dict[str, Any]] = []
        self._load_bank()

    def _load_bank(self):
        if self.bank_file.exists():
            try:
                data = json.loads(self.bank_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.examples = data
            except Exception:
                self.examples = []
        if not self.examples:
            self.examples = self._default_fallback_bank()

    def add_example(self, example: Dict[str, Any], persist: bool = False):
        """เพิ่มตัวอย่างใหม่เข้า Memory Bank สำหรับ Active Learning"""
        self.examples.append(example)
        if persist:
            try:
                self.bank_file.write_text(
                    json.dumps(self.examples, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

    def retrieve(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """ค้นหาตัวอย่างที่มีความคล้ายคลึงทางภาษากับ query สูงสุด Top-K"""
        if not query or not self.examples:
            return self.examples[:k]

        q_lower = query.lower().strip()
        scored: List[Tuple[float, Dict[str, Any]]] = []

        # สกัดลักษณะพิเศษของคำถาม เช่น มีคำว่า 'แล้ว', 'และ' (บ่งบอก sequence) หรือคำนอกเกม
        has_sequence_hint = any(w in q_lower for w in ("แล้ว", "และ", "ก่อนแล้วค่อย", "ต่อด้วย"))

        for ex in self.examples:
            target_text = ex.get("query", "")
            base_score = calculate_ngram_similarity(q_lower, target_text)

            # ให้ Priority Boost หากประเภทคำสั่งสอดคล้องกับโครงสร้างประโยค
            boost = 1.0
            if has_sequence_hint and ex.get("action") == "sequence":
                boost += 0.35
            if not has_sequence_hint and ex.get("action") == "sequence":
                boost -= 0.15

            # ถ้ามีคำสำคัญตรงกันเป๊ะ เพิ่มน้ำหนักพิเศษ
            for word in ("เผา", "ทำลาย", "จับ", "กล่าวหา", "ปลดล็อก", "รหัส", "สรุป", "ถาม", "คุย"):
                if word in q_lower and word in target_text:
                    boost += 0.2

            final_score = base_score * boost
            scored.append((final_score, ex))

        # เรียงลำดับจากคะแนนมากไปน้อย
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:k]]

    def retrieve_mmr(
        self, query: str, k: int = 5, lambda_param: float = 0.65
    ) -> List[Dict[str, Any]]:
        """Maximal Marginal Relevance (MMR) Retrieval:
        สมดุลระหว่างความเกี่ยวข้อง (Relevance ต่อ Query) และความหลากหลาย (Diversity ไม่ให้ Action/เป้าหมายซ้ำกันเกินไป)
        MMR = argmax_{d in C} [ lambda * Sim(d, query) - (1 - lambda) * max_{s in S} Sim(d, s) ]
        """
        if not query or not self.examples:
            return self.examples[:k]

        q_lower = query.lower().strip()
        has_sequence_hint = any(w in q_lower for w in ("แล้ว", "และ", "ก่อนแล้วค่อย", "ต่อด้วย"))

        # 1. ให้คะแนนความเกี่ยวข้อง (Relevance) ของทุกตัวอย่าง
        candidate_scores: List[Tuple[float, Dict[str, Any]]] = []
        for ex in self.examples:
            target_text = ex.get("query", "")
            base_score = calculate_ngram_similarity(q_lower, target_text)

            boost = 1.0
            if has_sequence_hint and ex.get("action") == "sequence":
                boost += 0.35
            if not has_sequence_hint and ex.get("action") == "sequence":
                boost -= 0.15

            for word in ("เผา", "ทำลาย", "จับ", "กล่าวหา", "ปลดล็อก", "รหัส", "สรุป", "ถาม", "คุย"):
                if word in q_lower and word in target_text:
                    boost += 0.2

            final_rel = base_score * boost
            candidate_scores.append((final_rel, ex))

        # เรียงตาม Relevance และเลือก Pool ผู้สมัครที่ดีที่สุด Top-M
        candidate_scores.sort(key=lambda x: x[0], reverse=True)
        pool = candidate_scores[: max(k * 4, 20)]

        if not pool:
            return []

        # 2. ทำการคัดเลือกแบบ MMR
        selected: List[Dict[str, Any]] = [pool[0][1]]
        remaining = pool[1:]

        while len(selected) < k and remaining:
            best_idx = -1
            best_mmr_score = -float("inf")

            for idx, (rel_score, cand) in enumerate(remaining):
                max_sim_to_selected = 0.0
                cand_action = cand.get("action")
                cand_query = cand.get("query", "")

                for sel in selected:
                    sim_text = calculate_ngram_similarity(cand_query, sel.get("query", ""))
                    if cand_action and cand_action == sel.get("action"):
                        sim_text = max(sim_text, 0.45)
                    if sim_text > max_sim_to_selected:
                        max_sim_to_selected = sim_text

                mmr_score = (lambda_param * rel_score) - ((1.0 - lambda_param) * max_sim_to_selected)
                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_idx = idx

            if best_idx >= 0:
                selected.append(remaining[best_idx][1])
                remaining.pop(best_idx)
            else:
                break

        return selected

    def _default_fallback_bank(self) -> List[Dict[str, Any]]:
        """ตัวอย่างสำรองฉุกเฉินกรณีไม่มีไฟล์ bank"""
        return [
            {"query": "ตรวจดูนาฬิกาพก", "action": "examine", "target": "pocket_watch", "confidence": 0.95},
            {"query": "คุยกับกิเดียนเรื่องบัญชี", "action": "interrogate", "target": "gideon_hart", "topic": "account", "confidence": 0.95},
            {"query": "เดินไปตู้ 4 ชั้นหนึ่ง", "action": "move", "target": "first_class_car", "confidence": 0.95},
            {"query": "ปลดกระเป๋าเอกสาร 1923", "action": "unlock", "target": "dossier_bag", "code": "1923", "confidence": 0.95},
            {"query": "เดินไปตู้ 4 แล้วตรวจกระเป๋า", "action": "sequence", "alternatives": ["move first_class_car", "examine dossier_bag"], "confidence": 0.9},
        ]


# Global Singleton
_RETRIEVER_INSTANCE: Optional[KNNExampleRetriever] = None


def get_retriever() -> KNNExampleRetriever:
    global _RETRIEVER_INSTANCE
    if _RETRIEVER_INSTANCE is None:
        _RETRIEVER_INSTANCE = KNNExampleRetriever()
    return _RETRIEVER_INSTANCE


# ==============================================================================
# Semantic Candidate Scorer สำหรับ Entity Pruning
# ==============================================================================

def score_entity_candidate(query: str, entity_id: str, entity_data: Dict[str, Any]) -> float:
    """คำนวณคะแนนความเกี่ยวข้อง (0.0 - 1.0) ระหว่างข้อความผู้เล่นกับ Entity

    ตรวจสอบทั้ง:
    - ID โดยตรง
    - ชื่อภาษาไทย (name_th)
    - รายการคำพ้อง (aliases)
    - ตำแหน่ง/บทบาท (role)
    """
    if not query:
        return 0.0

    q_clean = query.lower()
    id_clean = entity_id.lower()

    # 1. เช็กการกล่าวถึง ID หรือชื่อย่อตรงๆ
    if id_clean in q_clean:
        return 1.0

    scores = []

    # 2. ตรวจสอบชื่อไทย
    name_th = entity_data.get("name_th", "")
    if name_th:
        # ตัดวงเล็บภาษาอังกฤษออก เช่น 'นาฬิกาพก (Pocket Watch)' -> 'นาฬิกาพก'
        th_clean = re.sub(r"\(.*?\)", "", name_th).strip()
        if th_clean and th_clean in q_clean:
            return 0.95
        scores.append(calculate_ngram_similarity(q_clean, th_clean))

    # 3. ตรวจสอบ Aliases
    aliases = entity_data.get("aliases", [])
    for alias in aliases:
        if alias and alias.lower() in q_clean:
            return 0.92
        scores.append(calculate_ngram_similarity(q_clean, str(alias)))

    # 4. ตรวจสอบ Role (เช่น 'แพทย์', 'พนักงานตู้')
    role = entity_data.get("role", "")
    if role and role.lower() in q_clean:
        scores.append(0.85)

    return max(scores) if scores else 0.0
