"""Run the Test Set and compute metrics: Baseline vs Customized.

Usage:
    export GEMINI_API_KEY=...
    python evaluate.py

Needs test_set/labels.csv with columns:
    filename,true_menu,true_kcal
where true_kcal = kcal computed from the weighed food (ground truth), and
true_menu is a name that exists in nutrition_db.csv. Images go in test_set/.
Writes results.csv and prints a summary you can paste into the Metrics sheet.
"""
import difflib
import mimetypes
import time
from pathlib import Path

import pandas as pd
import analyzer as an

TEST_DIR = Path("test_set")


def name_correct(pred: str, truth: str) -> bool:
    return truth in pred or pred in truth or difflib.SequenceMatcher(None, pred, truth).ratio() >= 0.6


def main():
    labels = pd.read_csv(TEST_DIR / "labels.csv")
    db = an.load_db()
    client = an.get_client()
    rows = []
    for _, r in labels.iterrows():
        path = TEST_DIR / r["filename"]
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        data = path.read_bytes()
        rec = {"filename": r["filename"], "true_menu": r["true_menu"], "true_kcal": r["true_kcal"]}

        # --- Baseline ---
        try:
            b = an.analyze_baseline(client, data, mime)["items"]
            rec["base_menu"] = ", ".join(i["menu"] for i in b)
            rec["base_kcal"] = sum(float(i["kcal"]) for i in b)
            rec["base_correct"] = any(name_correct(i["menu"], r["true_menu"]) for i in b)
        except Exception as e:
            rec.update(base_menu="ERROR", base_kcal=None, base_correct=False)
            print("baseline error", r["filename"], e)

        # --- Customized ---
        try:
            t0 = time.time()
            c = an.analyze_customized(client, data, mime, db)
            rec["cust_seconds"] = round(time.time() - t0, 1)
            rec["cust_menu"] = ", ".join(i["menu"] for i in c)
            rec["cust_kcal"] = sum(an.scaled(i)["kcal"] for i in c)
            rec["cust_correct"] = any(name_correct(i["menu"], r["true_menu"]) for i in c)
        except Exception as e:
            rec.update(cust_menu="ERROR", cust_kcal=None, cust_correct=False)
            print("custom error", r["filename"], e)
        rows.append(rec)
        time.sleep(1)  # be gentle with rate limits

    df = pd.DataFrame(rows)
    df.to_csv("results.csv", index=False, encoding="utf-8-sig")

    def stats(prefix):
        ok = df.dropna(subset=[f"{prefix}_kcal"])
        err = (ok[f"{prefix}_kcal"] - ok["true_kcal"]).abs()
        return {
            "Top-1 Accuracy": df[f"{prefix}_correct"].mean(),
            "MAE (kcal)": err.mean(),
            "MAPE": (err / ok["true_kcal"]).mean(),
            "n": len(df),
        }

    summary = pd.DataFrame({"Baseline": stats("base"), "Customized": stats("cust")})
    print(summary.round(3))
    summary.to_csv("summary.csv", encoding="utf-8-sig")


if __name__ == "__main__":
    main()
