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
    global model, tokenizer, device
    
    # Skip model loading entirely if we are just previewing the design
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

    # Return a mock response instantly if in preview mode
    if PREVIEW_MODE:
        reply = "[Preview Mode] This is a mock response to test the UI design. The AI model is currently disabled."
    else:
        turn = f"{USER_TOKEN} {user_message}\n{BOT_TOKEN} "
        prompt = history + turn
        reply = generate_reply(model, tokenizer, prompt, device)

    # Logging still works in preview mode to test the file creation logic
    log_filepath = os.path.join(LOGS_DIR, f"{chat_id}.txt")
    with open(log_filepath, "a", encoding="utf-8") as f:
        f.write(f"User: {user_message}\nBot: {reply}\n\n")

    return jsonify({'reply': reply})

@app.route('/train', methods=['POST'])
def train():
    global training_proc
    data = request.json or {}
    
    # Extract parameters from request[cite: 2]
    epochs = str(data.get('epochs', 10))
    lr = str(data.get('lr', '5e-6'))
    subset = str(data.get('subset', 50000))
    force_cpu = data.get('device') == 'cpu'
    resume = data.get('resume', False)

    # Build command based on iris.py flags
    cmd = ["python3", "iris.py", "--epochs", epochs, "--lr", lr, "--subset", subset]
    
    if force_cpu:
        cmd.append("--force-cpu")
    if resume:
        cmd.append("--resume")

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

if __name__ == '__main__':
    if PREVIEW_MODE:
        print("Starting server in PREVIEW MODE (AI Model Disabled)")
    else:
        print("Starting server normally (AI Model Enabled)")
        
    app.run(debug=True, port=5000)