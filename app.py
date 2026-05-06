import os
import threading
import torch
from flask import Flask, request, jsonify, render_template
from transformers import AutoModelForCausalLM, AutoTokenizer

from iris import USER_TOKEN, BOT_TOKEN, get_device, generate_reply

app = Flask(__name__)

MODEL_NAME = "microsoft/DialoGPT-medium"
CHECKPOINT = "gpt2_sft_chatbot_best.pt"

model = None
tokenizer = None
device = None
_model_init_lock = threading.Lock()


def init_model():
    """Load once in the process that actually serves HTTP (not the reloader parent)."""
    global model, tokenizer, device
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
    user_message = data.get('message', '')
    history = data.get('history', '')

    if not user_message:
        return jsonify({'reply': "Please send a valid message."}), 400

    turn = f"{USER_TOKEN} {user_message}\n{BOT_TOKEN} "
    prompt = history + turn

    reply = generate_reply(model, tokenizer, prompt, device)

    return jsonify({'reply': reply})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
