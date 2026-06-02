import sys
import os
import csv
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.iris import ask_stream, ModelRole

def run_inference(prompt: str, role: ModelRole) -> tuple[str, float]:
    history = [{"role": "user", "content": prompt}]
    start_t = time.time()
    
    full_response = ""
    try:
        for event in ask_stream(prompt, history, force_role=role):
            if event["type"] == "raw_response":
                full_response = event["content"]
                break
            elif event["type"] == "token" and not full_response:
                # We will use raw_response if available, otherwise just accumulate
                full_response += event["content"]
    except FileNotFoundError as e:
        full_response = f"ERROR: Model file missing ({e})"
    except Exception as e:
        full_response = f"ERROR: {e}"
            
    end_t = time.time()
    return full_response, round(end_t - start_t, 2)

def append_to_csv(csv_path: str, row_dict: dict, fieldnames: list[str]):
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row_dict)
