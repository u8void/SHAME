import os
import json
import argparse
import threading
import subprocess

from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename

from iris import load_model, get_device, generate_reply, solve_math, BookRetriever, analyze_image, MLX_MODEL_ID, HF_MODEL_ID, BACKEND

parser = argparse.ArgumentParser(description="Run the Iris AI Flask App")
parser.add_argument("--preview-only", action="store_true",
                    help="Launch UI without loading the AI model")
args, _ = parser.parse_known_args()

PREVIEW_MODE = args.preview_only

app = Flask(__name__)

LOGS_DIR          = "logs"
TRAIN_LOG_FILE    = "outputs/train_output.txt"
UPLOAD_DIR        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "bmp"}

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(TRAIN_LOG_FILE), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

model         = None
tokenizer     = None
device        = None
retriever     = None
_model_lock   = threading.Lock()
_model_ready  = threading.Event()
_retriever_lock   = threading.Lock()
_retriever_ready  = False
training_proc = None

def get_retriever():
    """Lazy-load the RAG index on first chat request.

    Kept out of init_model so it does not compete with model weights for
    unified memory during the critical startup window.
    """
    global retriever, _retriever_ready
    if _retriever_ready:
        return retriever
    with _retriever_lock:
        if _retriever_ready:
            return retriever
        print("[INFO] Lazy-loading RAG Knowledge Base...")
        try:
            retriever = BookRetriever(raw_data_dir="raw_data")
            retriever.load_and_index()
        except Exception as e:
            print(f"[WARNING] RAG load failed: {e}")
            retriever = None
        _retriever_ready = True
        return retriever

def init_model():
    """Load phi-4 + LoRA adapters in a background thread.

    Key changes vs the original:
    - Metal cache capped at 1 GB immediately after model load.
    - Warmup runs with non-streaming ``generate`` (avoids the stream_generate
      deadlock) so Metal JIT kernels compile BEFORE the first user message.
    - _model_ready is set AFTER warmup, guaranteeing the first real request
      is fast (~3-8 s) instead of triggering JIT compilation mid-response.
    - RAG is no longer loaded here; it lazy-loads on the first chat request
      so it does not compete with model weights for unified memory.
    """
    global model, tokenizer, device

    if PREVIEW_MODE:
        _model_ready.set()
        return

    with _model_lock:
        if model is not None:
            _model_ready.set()
            return
        try:
            print("[INFO] Loading Iris model (Unified Backend)...")
            model, tokenizer = load_model()
            device = get_device()

            if BACKEND == "mlx":
                try:
                    import mlx.core as mx
                    mx.metal.set_cache_limit(1 * 1024 * 1024 * 1024)
                    print("[INFO] MLX Metal cache capped at 1 GB.")
                except Exception:
                    pass

            print("[INFO] Warming up Metal kernels (first compile ~20-40 s on M2)...")
            try:
                if BACKEND == "mlx":
                    from mlx_lm import generate as _warmup_gen
                    _warmup_gen(model, tokenizer, prompt="hi", max_tokens=2, verbose=False)
                    print("[INFO] Metal warmup complete — model ready.")
                else:
                    print("[INFO] Non-MLX backend — skipping warmup.")
            except Exception as e:
                print(f"[INFO] Warmup failed ({e}) — first response may be slower.")

            print(f"[INFO] Iris ready. backend={BACKEND} device={device}")

        except Exception as e:
            print(f"[ERROR] Model loading failed: {e}")
        finally:
            _model_ready.set()

if not PREVIEW_MODE:
    threading.Thread(target=init_model, name="model-loader", daemon=True).start()
else:
    _model_ready.set()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    if not PREVIEW_MODE and not _model_ready.is_set():
        def _warming():
            yield 'data: {"type": "token", "content": "Iris is warming up - model loading takes 20-40s on first start. Please try again shortly."}\n\n'
        from flask import Response
        return Response(_warming(), mimetype="text/event-stream")

    if request.is_json:
        data = request.json
        image_file = None
    else:
        data = request.form
        image_file = request.files.get("image")

    chat_id      = data.get("chat_id", "unknown_chat")
    user_message = data.get("message", "").strip()
    history      = data.get("history", "")
    settings     = data.get("settings", {})

    if image_file and _allowed_file(image_file.filename):
        filename = secure_filename(image_file.filename)
        save_path = os.path.join(UPLOAD_DIR, filename)
        image_file.save(save_path)

        user_message = f"[IMAGE_UPLOADED: {save_path}] {user_message}"

    if not user_message and not image_file:
        return jsonify({"reply": "Please send a valid message."}), 400

    math_answer = solve_math(user_message)
    if math_answer is not None:
        return jsonify({"reply": math_answer})

    if PREVIEW_MODE:
        def preview_generate():
            mock_event = {"type": "action_result", "content": "[Preview Mode] Mock response."}
            yield f"data: {json.dumps(mock_event)}\n\n"
        resp = Response(preview_generate(), mimetype='text/event-stream')
        resp.headers['X-Accel-Buffering'] = 'no'
        resp.headers['Cache-Control']     = 'no-cache'
        resp.headers['Connection']        = 'keep-alive'
        return resp

    import controller
    controller.IS_INTERACTIVE = False
    from controller import ai_agent_handle

    frontend_messages = []
    if "messages" in data:
        try:
            frontend_messages = json.loads(data["messages"]) if isinstance(data["messages"], str) else data["messages"]
        except:
            pass

    agent_history = []
    for msg in frontend_messages[:-1][-6:]:
        role = "assistant" if msg.get("role") == "bot" else "user"
        agent_history.append({"role": role, "content": msg.get("content", "")})

    from flask import Response
    def generate():
        for event in ai_agent_handle(
            user_message,
            model,
            tokenizer,
            device,
            get_retriever(),
            agent_history
        ):
            yield f"data: {json.dumps(event)}\n\n"

    resp = Response(generate(), mimetype='text/event-stream')
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['Cache-Control']     = 'no-cache'
    resp.headers['Connection']        = 'keep-alive'
    return resp

@app.route("/analyze_image", methods=["POST"])
def analyze_image_route():
    """
    Accept a multipart POST with:
      - 'image'  : the image file
      - 'prompt' : (optional) question/instruction about the image
      - 'chat_id': (optional) session id for logging

    Returns: {"reply": "<analysis text>"}
    """
    if "image" not in request.files:
        return jsonify({"error": "No image file provided. Send it as 'image' field."}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "Empty filename."}), 400
    if not _allowed_file(file.filename):
        return jsonify({"error": f"Unsupported file type. Allowed: {ALLOWED_EXTENSIONS}"}), 415

    prompt  = request.form.get("prompt", "Describe this image in detail.").strip() or              "Describe this image in detail."
    chat_id = request.form.get("chat_id", "unknown_chat")

    filename  = secure_filename(file.filename)
    save_path = os.path.join(UPLOAD_DIR, filename)
    file.save(save_path)

    try:
        if PREVIEW_MODE:
            reply = f"[Preview Mode] Would analyse '{filename}' with prompt: {prompt}"
        else:
            reply = analyze_image(save_path, prompt)
    except Exception as e:
        reply = f"Image analysis failed: {e}"
    finally:

        try:
            os.unlink(save_path)
        except Exception:
            pass

    log_path = os.path.join(LOGS_DIR, f"{chat_id}.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"User [image]: {filename} | Prompt: {prompt}\nBot: {reply}\n\n")

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