
import gc
import os
import argparse
import threading
import subprocess

import torch
from flask import Flask, request, jsonify, render_template
from transformers import AutoModelForCausalLM, AutoTokenizer


from iris import USER_TOKEN, BOT_TOKEN, get_device, generate_reply, solve_math


parser = argparse.ArgumentParser(description="Run the Iris AI Flask App")
parser.add_argument("--preview-only", action="store_true",
                    help="Launch UI without loading the AI model")
parser.add_argument("--force-cpu", action="store_true",
                    help="Force CPU inference (overrides MPS auto-detect)")
args, _ = parser.parse_known_args()


PREVIEW_MODE = args.preview_only
FORCE_CPU    = args.force_cpu or os.environ.get("FORCE_CPU", "").lower() in ("1", "true", "yes")


app = Flask(__name__)

MERGED_MODEL_PATH = "./iris_merged_model"
BASE_MODEL_NAME   = "google/gemma-2-2b-it"
LOGS_DIR          = "logs"
TRAIN_LOG_FILE    = "outputs/train_output.txt"

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(TRAIN_LOG_FILE), exist_ok=True)


model         = None
tokenizer     = None
device        = None
_model_lock   = threading.Lock()
training_proc = None


def init_model():
    global model, tokenizer, device

    if PREVIEW_MODE or model is not None:
        return

    with _model_lock:
        if model is not None:
            return

        device = get_device(force_cpu=FORCE_CPU)
        print(f"[INFO] Device: {device}")

        model_path = MERGED_MODEL_PATH if os.path.exists(MERGED_MODEL_PATH) else BASE_MODEL_NAME
        if model_path == BASE_MODEL_NAME:
            print(f"[WARNING] Merged model not found — falling back to {BASE_MODEL_NAME}")
        else:
            print(f"[INFO] Loading model from {model_path}")


        dtype = torch.float32 if FORCE_CPU else torch.float16
        print(f"[INFO] Loading with dtype={dtype} ...")


        tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            use_fast=True,
        )
        tokenizer.pad_token = tokenizer.eos_token


        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
        )


        model.eval()
        for p in model.parameters():
            p.requires_grad_(False)


        model = model.to(device)

        gc.collect()
        if device.type == "mps":
            torch.mps.empty_cache()
        elif device.type == "cuda":
            torch.cuda.empty_cache()

        print("[INFO] Model ready.")


@app.before_request
def _ensure_model():
    init_model()



@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data         = request.json or {}
    chat_id      = data.get("chat_id", "unknown_chat")
    user_message = data.get("message", "").strip()
    history      = data.get("history", "")
    settings     = data.get("settings", {})

    if not user_message:
        return jsonify({"reply": "Please send a valid message."}), 400

    # ── Math fast-path: solve equations/arithmetic with sympy ───────────────
    math_answer = solve_math(user_message)
    if math_answer is not None:
        log_path = os.path.join(LOGS_DIR, f"{chat_id}.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"User: {user_message}\nBot: {math_answer}\n\n")
        return jsonify({"reply": math_answer})
    # ────────────────────────────────────────────────────────────────────────

    if PREVIEW_MODE:
        reply = "[Preview Mode] Mock response — AI model disabled."
    else:
        # Use the Agent Controller to handle the conversation and actions
        import controller
        controller.IS_INTERACTIVE = False
        from controller import ai_agent_handle
        frontend_messages = data.get("messages", [])
        
        # Convert frontend messages to the format expected by ai_agent_handle
        agent_history = []
        for msg in frontend_messages[:-1]: # exclude last message as it's the one we're processing
            role = "assistant" if msg.get("role") == "bot" else "user"
            agent_history.append({"role": role, "content": msg.get("content", "")})
            
        reply = ai_agent_handle(
            user_message, 
            model, 
            tokenizer, 
            device, 
            agent_history
        )
        
        # The ai_agent_handle takes care of generation and tool mapping.
        if device.type == "mps":
            torch.mps.empty_cache()

    log_path = os.path.join(LOGS_DIR, f"{chat_id}.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"User: {user_message}\nBot: {reply}\n\n")

    return jsonify({"reply": reply})


@app.route("/train", methods=["POST"])
def train():
    global training_proc

    if training_proc is not None and training_proc.poll() is None:
        return jsonify({"status": "already_running"})

    data = request.json or {}

    cmd = [
        "python3", "train.py",
        "--model-name",  str(data.get("model_name",  BASE_MODEL_NAME)),
        "--epochs",      str(data.get("epochs",       3)),
        "--lr",          str(data.get("lr",           "2e-4")),
        "--max-pairs",   str(data.get("max_pairs",    5000)),
        "--md-dir",      str(data.get("md_dir",       "training")),
        "--max-length",  str(data.get("max_length",   64)),
        "--batch-size",  str(data.get("batch_size",   1)),
        "--accum-steps", str(data.get("accum_steps",  8)),
        "--output-dir",  str(data.get("output_dir",   "./iris_lora_adapter")),
    ]

    device_choice = data.get("device") or ("cpu" if FORCE_CPU else None)
    if device_choice:
        cmd.extend(["--device", device_choice])
    if data.get("no_bst"):            cmd.append("--no-bst")
    if data.get("no_dd"):             cmd.append("--no-dd")
    if data.get("no_md"):             cmd.append("--no-md")
    if data.get("use_chat_template"): cmd.append("--use-chat-template")
    
    # Reasoning Parameters
    if data.get("claude_reasoning"):
        cmd.extend(["--claude-reasoning", str(data.get("claude_reasoning"))])
    if data.get("dolci_think"):
        cmd.extend(["--dolci-think", str(data.get("dolci_think"))])
    if data.get("deepthink"):
        cmd.extend(["--deepthink", str(data.get("deepthink"))])
    if data.get("openhermes"):
        cmd.extend(["--openhermes", str(data.get("openhermes"))])
    if data.get("orca_math"):
        cmd.extend(["--orca-math", str(data.get("orca_math"))])
    if data.get("strip_reasoning"):
        cmd.append("--strip-reasoning")

    os.makedirs(os.path.dirname(TRAIN_LOG_FILE), exist_ok=True)
    log_file = open(TRAIN_LOG_FILE, "w", encoding="utf-8")
    log_file.write(f"Running: {' '.join(cmd)}\n")
    log_file.flush()

    training_proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
    return jsonify({"status": "started"})


@app.route("/train_logs", methods=["GET"])
def get_logs():
    if not os.path.exists(TRAIN_LOG_FILE):
        return jsonify({"logs": ""})
    with open(TRAIN_LOG_FILE, "r", encoding="utf-8") as f:
        return jsonify({"logs": f.read()})


@app.route("/train_status", methods=["GET"])
def train_status():
    running = training_proc is not None and training_proc.poll() is None
    return jsonify({"running": running})


@app.route("/stop_train", methods=["POST"])
def stop_train():
    global training_proc

    if training_proc is None or training_proc.poll() is not None:
        return jsonify({"status": "not_running"})

    try:
        training_proc.terminate()
        training_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        training_proc.kill()
        training_proc.wait()

    return jsonify({"status": "stopped"})


import json

@app.route("/get_settings", methods=["GET"])
def get_settings():
    config_path = os.path.join("config", "iris.conf")
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
    except Exception:
        pass
    return jsonify({})

@app.route("/save_settings", methods=["POST"])
def save_settings():
    data = request.json or {}
    config_path = os.path.join("config", "iris.conf")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = {}
    except Exception:
        config = {}
        
    config.update(data)
    
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        
    return jsonify({"status": "success"})

if __name__ == "__main__":
    mode_label = "PREVIEW MODE" if PREVIEW_MODE else (
        "CPU float32" if FORCE_CPU else "MPS float16"
    )
    print(f"[INFO] Starting Iris AI — {mode_label}")

    port = int(os.environ.get("PORT", "5050"))
    app.run(debug=False, host="127.0.0.1", port=port)
