import os
import argparse
import threading
import subprocess

from flask import Flask, request, jsonify, render_template

# Added BookRetriever to the import list
from iris import load_model, get_device, generate_reply, solve_math, BookRetriever, MLX_MODEL_ID, HF_MODEL_ID, BACKEND

parser = argparse.ArgumentParser(description="Run the Iris AI Flask App")
parser.add_argument("--preview-only", action="store_true",
                    help="Launch UI without loading the AI model")
args, _ = parser.parse_known_args()

PREVIEW_MODE = args.preview_only

app = Flask(__name__)

LOGS_DIR          = "logs"
TRAIN_LOG_FILE    = "outputs/train_output.txt"

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(TRAIN_LOG_FILE), exist_ok=True)

model         = None
tokenizer     = None
device        = None
retriever     = None  # Added global retriever
_model_lock   = threading.Lock()
training_proc = None

def init_model():
    """Load phi-4 + LoRA adapters via MLX (once, thread-safe)."""
    global model, tokenizer, device, retriever

    if PREVIEW_MODE or model is not None:
        return

    with _model_lock:
        if model is not None:
            return

        print("[INFO] Loading Iris model (Unified Backend)...")
        model, tokenizer = load_model()
        device = get_device()
        
        print("[INFO] Initializing RAG Knowledge Base...")
        retriever = BookRetriever(raw_data_dir="raw_data")
        retriever.load_and_index()
        
        print(f"[INFO] Model ready. device={device}")

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

    math_answer = solve_math(user_message)
    if math_answer is not None:
        log_path = os.path.join(LOGS_DIR, f"{chat_id}.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"User: {user_message}\nBot: {math_answer}\n\n")
        return jsonify({"reply": math_answer})

    if PREVIEW_MODE:
        reply = "[Preview Mode] Mock response — AI model disabled."
    else:
        import controller
        controller.IS_INTERACTIVE = False
        from controller import ai_agent_handle
        frontend_messages = data.get("messages", [])

        agent_history = []
        for msg in frontend_messages[:-1]:
            role = "assistant" if msg.get("role") == "bot" else "user"
            agent_history.append({"role": role, "content": msg.get("content", "")})

        reply = ai_agent_handle(
            user_message,
            model,
            tokenizer,
            device,
            retriever, # Pass the retriever to the controller
            agent_history
        )

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
        "--model",       str(data.get("model_name",  MLX_MODEL_ID)),
        "--epochs",      str(data.get("epochs",       3)),
        "--lr",          str(data.get("lr",           "2e-4")),
        "--max-pairs",   str(data.get("max_pairs",    5000)),
        "--md-dir",      str(data.get("md_dir",       "training")),
        "--max-length",  str(data.get("max_length",   64)),
        "--batch-size",  str(data.get("batch_size",   1)),
        "--accum-steps", str(data.get("accum_steps",  8)),
        "--output-dir",  str(data.get("output_dir",   "./iris_lora_adapter")),
    ]

    device_choice = data.get("device") or ("cpu" if BACKEND == "cpu" else None)
    if device_choice:
        cmd.extend(["--device", device_choice])
    if data.get("no_bst"):            cmd.append("--no-bst")
    if data.get("no_dd"):             cmd.append("--no-dd")
    if data.get("no_md"):             cmd.append("--no-md")
    if data.get("use_chat_template"): cmd.append("--use-chat-template")

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
    mode_label = "PREVIEW MODE" if PREVIEW_MODE else "MLX (phi-4-4bit + LoRA adapters)"
    print(f"[INFO] Starting Iris AI — {mode_label}")

    port = int(os.environ.get("PORT", "5050"))
    app.run(debug=False, host="127.0.0.1", port=port)