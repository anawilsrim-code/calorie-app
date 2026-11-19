"""Core pipeline: image -> Gemini Vision -> match Thai nutrition DB -> calories.

Customization layers (what to explain in the pitch):
  1. System prompt with rules (Thai food focus, JSON-only, portion rules)
  2. Few-shot examples inside the prompt
  3. RAG-lite: the menu list from nutrition_db.csv is injected into the prompt,
     and the model's answer is then matched back to the DB for exact numbers
"""
import json
import os
import difflib
from pathlib import Path

import pandas as pd
from google import genai
from google.genai import types

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")  # change if this model is retired
DB_PATH = Path(__file__).parent / "nutrition_db.csv"
PORTION_LABELS = {"เล็ก": 0.75, "กลาง": 1.0, "ใหญ่": 1.3}


def load_db() -> pd.DataFrame:
    return pd.read_csv(DB_PATH)


def get_client(api_key: str | None = None) -> genai.Client:
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("ไม่พบ GEMINI_API_KEY")
    return genai.Client(api_key=key)


# ---------- Prompts ----------
BASELINE_PROMPT = (
    "นี่คือรูปอาหาร บอกชื่อเมนูและแคลอรีโดยประมาณ ตอบเป็น JSON "
    '{"items":[{"menu":"...","kcal":0}]}'
)


def build_system_prompt(menu_names: list[str]) -> str:
    menus = ", ".join(menu_names)
    return f"""คุณคือนักกำหนดอาหาร (dietitian assistant) ผู้เชี่ยวชาญอาหารไทย
หน้าที่: ดูรูปอาหาร แล้วระบุรายการอาหารทุกอย่างที่เห็นในภาพ

กฎ:
1. เลือกชื่อเมนูจากรายการนี้เท่านั้นถ้ามีเมนูที่ตรง: [{menus}]
   ถ้าไม่มีเมนูที่ตรงเลย ให้ใส่ "menu": "อื่นๆ" และบอกชื่อจริงใน "note"
2. "portion" คืออัตราส่วนเทียบ 1 เสิร์ฟมาตรฐาน (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
   ประเมินจากขนาดจาน/ชามและปริมาณอาหารเทียบกับภาชนะ
3. แยกรายการเมื่อมีหลายอย่างบนโต๊ะ (เช่น ข้าวสวย + แกง + ไข่ดาว)
4. "confidence" เป็นเลข 0-1 ตามความมั่นใจ
5. ถ้าภาพไม่ใช่อาหาร ให้ตอบ items เป็น []
6. ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น

รูปแบบ:
{{"items":[{{"menu":"...","portion":1.0,"confidence":0.0,"note":""}}]}}

ตัวอย่าง:
- ภาพ: กะเพราหมูสับราดข้าว มีไข่ดาว 1 ฟองบนจานเดียว
  ตอบ: {{"items":[{{"menu":"ข้าวผัดกะเพราหมูสับไข่ดาว","portion":1.0,"confidence":0.85,"note":""}}]}}
- ภาพ: ส้มตำถ้วยเล็กครึ่งถ้วย + ไก่ย่างครึ่งตัว
  ตอบ: {{"items":[{{"menu":"ส้มตำไทย","portion":0.5,"confidence":0.8,"note":""}},{{"menu":"ไก่ย่าง","portion":1.0,"confidence":0.9,"note":""}}]}}
"""


# ---------- Gemini calls ----------
def _call_vision(client, image_bytes: bytes, mime: str, prompt: str, system: str | None = None) -> dict:
    resp = client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime), prompt],
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    return json.loads(resp.text)


def analyze_baseline(client, image_bytes: bytes, mime: str) -> dict:
    """Plain prompt, no DB. Used as the 'before' in evaluation."""
    return _call_vision(client, image_bytes, mime, BASELINE_PROMPT)


def analyze_customized(client, image_bytes: bytes, mime: str, db: pd.DataFrame) -> list[dict]:
    """Customized prompt + DB grounding. Returns rows with nutrition filled in."""
    system = build_system_prompt(db["menu"].tolist())
    data = _call_vision(client, image_bytes, mime, "วิเคราะห์อาหารในรูปนี้", system)
    return [ground_item(it, db) for it in data.get("items", [])]


# ---------- Grounding (match model output to DB) ----------
def match_menu(name: str, db: pd.DataFrame, cutoff: float = 0.6) -> str | None:
    if name in set(db["menu"]):
        return name
    hit = difflib.get_close_matches(name, db["menu"].tolist(), n=1, cutoff=cutoff)
    return hit[0] if hit else None


def ground_item(item: dict, db: pd.DataFrame) -> dict:
    matched = match_menu(item.get("menu", ""), db)
    out = {
        "menu": matched or item.get("menu", "อื่นๆ"),
        "portion": float(item.get("portion", 1.0)),
        "confidence": float(item.get("confidence", 0.0)),
        "note": item.get("note", ""),
        "in_db": matched is not None,
    }
    if matched:
        row = db[db["menu"] == matched].iloc[0]
        for col in ("kcal", "protein_g", "carb_g", "fat_g"):
            out[col] = float(row[col])
    else:
        for col in ("kcal", "protein_g", "carb_g", "fat_g"):
            out[col] = 0.0  # user must fill in manually
    return out


def scaled(item: dict) -> dict:
    p = item["portion"]
    return {k: round(item[k] * p, 1) for k in ("kcal", "protein_g", "carb_g", "fat_g")}


# ---------- Next-meal advice ----------
def suggest_next_meal(client, eaten: dict, goal_kcal: int, meals_left: int) -> str:
    remaining = max(goal_kcal - eaten["kcal"], 0)
    prompt = f"""ผู้ใช้กินไปแล้ววันนี้: {eaten['kcal']:.0f} kcal, โปรตีน {eaten['protein_g']:.0f} g,
คาร์บ {eaten['carb_g']:.0f} g, ไขมัน {eaten['fat_g']:.0f} g
เป้าหมายต่อวัน {goal_kcal} kcal เหลือประมาณ {remaining:.0f} kcal และเหลืออีก {meals_left} มื้อ
แนะนำมื้อถัดไป 2-3 ตัวเลือกเป็นอาหารไทยหาง่าย พร้อมแคลอรีโดยประมาณและเหตุผลสั้นๆ
ตอบเป็นภาษาไทย กระชับ ไม่เกิน 6 บรรทัด ห้ามวินิจฉัยโรคหรือให้คำแนะนำทางการแพทย์"""
    resp = client.models.generate_content(model=MODEL, contents=prompt)
    return resp.text
