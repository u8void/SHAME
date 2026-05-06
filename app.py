import os
import sys
import argparse
import threading
import torch
import subprocess
from flask import Flask, request, jsonify, render_template
from transformers import AutoModelForCausalLM, AutoTokenizer

from iris import USER_TOKEN, BOT_TOKEN, get_device, generate_reply

# Parse arguments to enable preview mode
parser = argparse.ArgumentParser(description="Run the Iris AI Flask App")
parser.add_argument("--preview-only", action="store_true", help="Launch UI without loading the AI model")
args, unknown = parser.parse_known_args()
PREVIEW_MODE = args.preview_only

app = Flask(__name__)

MODEL_NAME = "microsoft/DialoGPT-medium"
CHECKPOINT = "gpt2_sft_chatbot_best.pt"
LOGS_DIR = "logs"
TRAIN_LOG_FILE = "train_output.txt"

os.makedirs(LOGS_DIR, exist_ok=True)

model = None
tokenizer = None
device = None
_model_init_lock = threading.Lock()
training_proc = None

def init_model():
    """Load once in the process that actually serves HTTP."""
    global model, tokenizer, device
    
    if PREVIEW_MODE:
        return 
        
    if model is not None:
        return
    with _model_init_lock:
        if model is not None:
            return
        device = get_device(
            force_cpu=os.environ.get("FORCE_CPU", "").lower() in ("1", "true", "yes")
        )
        print("Loading tokenizer and model...")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            low_cpu_mem_usage=True,
            dtype=torch.float32,
        )
        model = model.to(device)

        if os.path.exists(CHECKPOINT):
            print(f"Loading trained weights from {CHECKPOINT}")
            model.load_state_dict(torch.load(CHECKPOINT, map_location=device))
        else:
            print("Warning: No custom checkpoint found. Using base model.")

@app.before_request
def _ensure_model_loaded():
    init_model()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json or {}
    chat_id = data.get('chat_id', 'unknown_chat')
    user_message = data.get('message', '')
    history = data.get('history', '')

    if not user_message:
        return jsonify({'reply': "Please send a valid message."}), 400

    if PREVIEW_MODE:
        reply = "[Preview Mode] This is a mock response to test the UI design. The AI model is currently disabled."
    else:
        turn = f"{USER_TOKEN} {user_message}\n{BOT_TOKEN} "
        prompt = history + turn
        reply = generate_reply(model, tokenizer, prompt, device)

    # Logging works in both modes
    log_filepath = os.path.join(LOGS_DIR, f"{chat_id}.txt")
    with open(log_filepath, "a", encoding="utf-8") as f:
        f.write(f"User: {user_message}\nBot: {reply}\n\n")

    return jsonify({'reply': reply})

@app.route('/train', methods=['POST'])
def train():
    global training_proc
    if training_proc is not None and training_proc.poll() is None:
        return jsonify({'status': 'already_running'})

    data = request.json or {}
    
    model_name = str(data.get('model_name', 'microsoft/DialoGPT-medium'))
    checkpoint = str(data.get('checkpoint', 'gpt2_sft_chatbot_best.pt'))
    epochs = str(data.get('epochs', 5))
    lr = str(data.get('lr', '3e-5'))
    bst_size = str(data.get('bst_size', 10000))
    dd_size = str(data.get('dd_size', 30000))
    md_dir = str(data.get('md_dir', 'training'))
    max_length = str(data.get('max_length', 128))
    batch_size = str(data.get('batch_size', 4))
    accum = str(data.get('accum', 4))
    weight_decay = str(data.get('weight_decay', 0.01))
    warmup_ratio = str(data.get('warmup_ratio', 0.05))
    sample_max_new_tokens = str(data.get('sample_max_new_tokens', 50))
    force_cpu = data.get('device') == 'cpu'
    resume = data.get('resume', False)
    keep_best_only = data.get('keep_best_only', False)
    no_bst = data.get('no_bst', False)
    no_dd = data.get('no_dd', False)
    no_md = data.get('no_md', False)
    chat_after_train = data.get('chat_after_train', False)

    cmd = [
        "python3", "train.py",
        "--model-name", model_name,
        "--checkpoint", checkpoint,
        "--epochs", epochs,
        "--lr", lr,
        "--bst-size", bst_size,
        "--dd-size", dd_size,
        "--md-dir", md_dir,
        "--max-length", max_length,
        "--batch-size", batch_size,
        "--accum", accum,
        "--weight-decay", weight_decay,
        "--warmup-ratio", warmup_ratio,
        "--sample-max-new-tokens", sample_max_new_tokens,
    ]
    
    if force_cpu:
        cmd.append("--force-cpu")
    if resume:
        cmd.append("--resume")
    if keep_best_only:
        cmd.append("--keep-best-only")
    if no_bst:
        cmd.append("--no-bst")
    if no_dd:
        cmd.append("--no-dd")
    if no_md:
        cmd.append("--no-md")
    if chat_after_train:
        cmd.append("--chat-after-train")

    with open(TRAIN_LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"Running: {' '.join(cmd)}\n")

    training_proc = subprocess.Popen(cmd, stdout=open(TRAIN_LOG_FILE, "a"), stderr=subprocess.STDOUT)
    
    return jsonify({'status': 'started'})

@app.route('/train_logs', methods=['GET'])
def get_logs():
    if not os.path.exists(TRAIN_LOG_FILE):
        return jsonify({'logs': ''})
    with open(TRAIN_LOG_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    return jsonify({'logs': content})

@app.route('/train_status', methods=['GET'])
def train_status():
    running = training_proc is not None and training_proc.poll() is None
    return jsonify({'running': running})

@app.route('/stop_train', methods=['POST'])
def stop_train():
    global training_proc
    if training_proc is None or training_proc.poll() is not None:
        return jsonify({'status': 'not_running'})

    try:
        training_proc.terminate()
        training_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        training_proc.kill()
        training_proc.wait(timeout=5)

    return jsonify({'status': 'stopped'})

if __name__ == '__main__':
    if PREVIEW_MODE:
        print("🚀 Starting server in PREVIEW MODE (AI Model Disabled)")
    else:
        print("🚀 Starting server normally (AI Model Enabled)")

    port = int(os.environ.get("PORT", "5050"))
    app.run(debug=True, host="127.0.0.1", port=port)