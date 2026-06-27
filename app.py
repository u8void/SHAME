import os, sys


def _ensure_open_interpreter():
    if os.environ.get("SKIP_OPEN_INTERPRETER") == "1":
        return
    try:
        import json
        with open("config/iris.conf", "r", encoding="utf-8") as f:
            if json.load(f).get("skip_open_interpreter", False):
                return
    except Exception:
        pass

    try:
        import interpreter  
    except ImportError:
        import subprocess as _sp
        print("\n[Iris] Installing open-interpreter — one-time setup...", flush=True)
        _sp.run([sys.executable, "-m", "pip", "install", "-q",
                 "--upgrade", "open-interpreter"], check=True)
        print("[Iris] open-interpreter installed ✓\n", flush=True)
_ensure_open_interpreter()


import os
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
os.environ["VECLIB_MAXIMUM_THREADS"] = "4"
os.environ["NUMEXPR_NUM_THREADS"] = "4"

import json
import uuid
import argparse
import threading
import subprocess
from flask import Flask, request, jsonify, render_template, Response
from werkzeug.utils import secure_filename
from src.logger import get_logger

logger = get_logger("app")

from src.iris import ask_stream, solve_math, BookRetriever, analyze_image


global_generation_lock = threading.Lock()

parser = argparse.ArgumentParser(description="Run the Iris AI Flask App")
parser.add_argument("--preview-only", action="store_true",
                    help="Launch UI without loading the AI model")
parser.add_argument("--pro", action="store_true",
                    help="Use Iris Pro multi-agent API pipeline")
parser.add_argument("--skip-control", action="store_true",
                    help="Skip loading the control model and routing to it")
args, _ = parser.parse_known_args()

PREVIEW_MODE = args.preview_only
PRO_MODE = args.pro

if args.skip_control:
    os.environ["SKIP_CONTROL"] = "1"

BACKEND = os.environ.get("IRIS_BACKEND", "cpu")
MLX_MODEL_ID = os.environ.get("IRIS_MODEL_ID", "iris_001.gguf")

app = Flask(__name__)

LOGS_DIR          = "logs"
TRAIN_LOG_FILE    = "outputs/train_output.txt"
UPLOAD_DIR        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "bmp"}

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(TRAIN_LOG_FILE), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


voice_history = []

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

retriever     = None
_retriever_lock   = threading.Lock()
_retriever_ready  = False
training_proc = None


import atexit as _atexit
def _shutdown_cleanup():
    
    if not PREVIEW_MODE:
        try:
            from src.iris import _force_unload_all_models
            logger.info("[Shutdown] Freeing all loaded models from memory...")
            _force_unload_all_models()
            logger.info("[Shutdown] All models freed.")
        except Exception as e:
            logger.warning(f"[Shutdown] Model cleanup error: {e}")

_atexit.register(_shutdown_cleanup)

def get_retriever():
    global retriever, _retriever_ready
    if _retriever_ready:
        return retriever
    with _retriever_lock:
        if _retriever_ready:
            return retriever
        logger.info("[INFO] Lazy-loading RAG Knowledge Base...")
        try:
            retriever = BookRetriever(raw_data_dir="raw_data")
            retriever.load_and_index()
        except Exception as e:
            logger.warning(f"[WARNING] RAG load failed: {e}")
            retriever = None
        _retriever_ready = True
        return retriever

@app.route("/")
def home():
    return render_template("index.html", pro_mode=PRO_MODE)

@app.route("/chat", methods=["POST"])
def chat():
    if request.is_json:
        data = request.json
        image_files = []
        doc_files = []
    else:
        data = request.form
        image_files = request.files.getlist("image")
        doc_files = request.files.getlist("document")

    chat_id      = data.get("chat_id", "unknown_chat")
    user_message = data.get("message", "").strip()
    history      = data.get("history", "")
    
    settings_raw = data.get("settings", {})
    if isinstance(settings_raw, str):
        try:
            settings = json.loads(settings_raw)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Settings JSON parse failed: {e}")
            return jsonify({"error": f"Invalid settings JSON: {e}"}), 400
    else:
        settings = settings_raw

    for image_file in image_files:
        if image_file and _allowed_file(image_file.filename):
            filename = f"{uuid.uuid4().hex}_{secure_filename(image_file.filename)}"
            save_path = os.path.join(UPLOAD_DIR, filename)
            image_file.save(save_path)
            user_message = f"[IMAGE_UPLOADED: {save_path}]\n{user_message}"

    actual_prompt = user_message if user_message else "Please provide a detailed, comprehensive summary and explanation of the attached documents."
    doc_sections = []

    
    parsed_docs = []
    for doc_file in doc_files:
        if doc_file:
            filename = f"{uuid.uuid4().hex}_{secure_filename(doc_file.filename)}"
            save_path = os.path.join(UPLOAD_DIR, filename)
            doc_file.save(save_path)
            try:
                from markitdown import MarkItDown
                md = MarkItDown()
                result = md.convert(save_path)
                parsed_docs.append((filename, result.text_content))
            except Exception as e:
                import logging
                logging.getLogger('iris').warning(f"Failed to parse document {filename} with MarkItDown: {e}")
                try:
                    with open(save_path, "r", encoding="utf-8") as f:
                        fallback_text = f.read()
                    parsed_docs.append((filename, fallback_text))
                except Exception:
                    parsed_docs.append((filename, f"[Failed to parse `{filename}`]"))

    if parsed_docs:
        if PRO_MODE:
            for filename, text in parsed_docs:
                doc_sections.append(f"Document `{filename}`:\n<document>\n{text}\n</document>")
        else:
            
            budget = 12000
            per_doc_budget = budget // max(1, len(parsed_docs))
            
            
            final_texts = {}
            remaining_docs = []
            for filename, text in parsed_docs:
                if len(text) <= per_doc_budget:
                    final_texts[filename] = text
                    budget -= len(text)
                else:
                    remaining_docs.append((filename, text))
            
            
            if remaining_docs:
                per_doc_budget = budget // len(remaining_docs)
                for filename, text in remaining_docs:
                    truncated = text[:per_doc_budget] + f"\n\n[DOCUMENT TRUNCATED DUE TO MAX {per_doc_budget} CHARS]"
                    final_texts[filename] = truncated

            
            for filename, _ in parsed_docs:
                doc_sections.append(f"Document `{filename}`:\n<document>\n{final_texts[filename]}\n</document>")

    if doc_sections:
        all_docs_text = "\n\n".join(doc_sections)
        user_message = f"I have attached {len(doc_files)} document(s). Here is the content:\n\n{all_docs_text}\n\nUser Prompt:\n{actual_prompt}"

    if not user_message and not image_files and not doc_files:
        return jsonify({"reply": "Please send a valid message."}), 400

    math_answer = solve_math(user_message)
    if math_answer is not None:
        def math_generate():
            yield f"data: {json.dumps({'type': 'token', 'content': math_answer})}\n\n"
        resp = Response(math_generate(), mimetype='text/event-stream')
        resp.headers['X-Accel-Buffering'] = 'no'
        resp.headers['Cache-Control']     = 'no-cache'
        resp.headers['Connection']        = 'keep-alive'
        return resp

    if PREVIEW_MODE:
        def preview_generate():
            mock_event = {"type": "action_result", "content": "[Preview Mode] Mock response."}
            yield f"data: {json.dumps(mock_event)}\n\n"
        resp = Response(preview_generate(), mimetype='text/event-stream')
        resp.headers['X-Accel-Buffering'] = 'no'
        resp.headers['Cache-Control']     = 'no-cache'
        resp.headers['Connection']        = 'keep-alive'
        return resp

    frontend_messages = []
    if "messages" in data:
        try:
            frontend_messages = json.loads(data["messages"]) if isinstance(data["messages"], str) else data["messages"]
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse message history: {e}")
            agent_history = []  

    agent_history = []
    for msg in frontend_messages[:-1][-6:]:
        role = "assistant" if msg.get("role") == "bot" else "user"
        agent_history.append({"role": role, "content": msg.get("content", "")})

    
    use_pro = str(data.get("use_pro", "")).lower() in ("true", "1", "yes")
    if PRO_MODE or use_pro:
        import asyncio
        import time
        import src.iris_pro as iris_pro
        def pro_generate():
            import queue
            import threading
            q = queue.Queue()
            
            def run_async():
                async def task():
                    mode = data.get("mode", "smart")
                    workspace_root = data.get("workspace_root", "")
                    try:
                        agen = iris_pro.ask_stream(user_message, agent_history, mode=mode, workspace_root=workspace_root)
                        async for event in agen:
                            q.put(event)
                    except Exception as e:
                        q.put(e)
                    finally:
                        q.put(None)
                asyncio.run(task())
                
            t = threading.Thread(target=run_async)
            t.start()
            
            try:
                while True:
                    item = q.get()
                    if item is None:
                        break
                    if isinstance(item, Exception):
                        raise item
                    yield f"data: {json.dumps(item)}\n\n"
            except Exception as e:
                err_msg = str(e)
                if not err_msg or "Timeout" in e.__class__.__name__:
                    err_msg = f"{e.__class__.__name__}: The API request took too long or dropped connection."
                yield f"data: {json.dumps({'type': 'text', 'content': f'Iris Pro Error: {err_msg}'})}\n\n"
        
        resp = Response(pro_generate(), mimetype='text/event-stream')
        resp.headers['X-Accel-Buffering'] = 'no'
        resp.headers['Cache-Control']     = 'no-cache'
        resp.headers['Connection']        = 'keep-alive'
        return resp

    from src import controller
    controller.IS_INTERACTIVE = False
    from src.controller import ai_agent_handle

    def generate():
        with global_generation_lock:
            try:
                yield f"data: {json.dumps({'type': 'status', 'content': 'Initializing...'})}\n\n"
                retriever_instance = get_retriever()
                
                for event in ai_agent_handle(
                    user_message,
                    retriever_instance,
                    agent_history,
                    settings=settings,
                    keep_loaded=False
                ):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                err_msg = str(e)
                yield f"data: {json.dumps({'type': 'token', 'content': f'\\n\\n> [ERROR] **Iris Error:** {err_msg}'})}\n\n"

    resp = Response(generate(), mimetype='text/event-stream')
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['Cache-Control']     = 'no-cache'
    resp.headers['Connection']        = 'keep-alive'
    return resp

@app.route("/analyze_image", methods=["POST"])
def analyze_image_route():
    
    save_path = None
    
    if "image" not in request.files:
        return jsonify({"error": "No image file provided. Send it as 'image' field."}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "Empty filename."}), 400
    if not _allowed_file(file.filename):
        return jsonify({"error": f"Unsupported file type. Allowed: {ALLOWED_EXTENSIONS}"}), 415

    prompt  = request.form.get("prompt", "Describe this image in detail.").strip() or              "Describe this image in detail."
    chat_id = request.form.get("chat_id", "unknown_chat")

    filename  = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    save_path = os.path.join(UPLOAD_DIR, filename)
    file.save(save_path)

    try:
        if PREVIEW_MODE:
            reply = f"[Preview Mode] Would analyse '{filename}' with prompt: {prompt}"
        else:
            with global_generation_lock:
                reply = analyze_image(save_path, prompt)
    except Exception as e:
        reply = f"Image analysis failed: {e}"
    finally:
        if save_path:
            try:
                os.unlink(save_path)
            except Exception:
                pass

    log_path = os.path.join(LOGS_DIR, f"{chat_id}.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"User [image]: {filename} | Prompt: {prompt}\nBot: {reply}\n\n")

    return jsonify({"reply": reply})

@app.route("/api/voice/init", methods=["GET"])
def voice_init_endpoint():
    
    import src.voice_models as vm
    
    vm.load_stt_model()
    vm.load_tts_model()
    vm.load_voice_llm()
    
    
    audio_b64_url = vm.synthesize_speech("Hi, How can I assist you today?")
    
    return jsonify({"status": "ready", "audio_url": audio_b64_url})

@app.route("/api/voice", methods=["POST"])
def voice_chat_endpoint():
    global voice_history
    try:
        if "audio" not in request.files:
            return jsonify({"error": "No audio file uploaded"}), 400

        audio_file = request.files["audio"]
        audio_bytes = audio_file.read()

        
        import src.voice_models as vm
        user_text = vm.transcribe_audio(audio_bytes, audio_file.filename)
        logger.info(f"[Voice] STT: {user_text[:120]}")

        if not user_text or not user_text.strip():
            return jsonify({"error": "Could not understand audio."}), 400
            
        VOICE_IDENTITY = (
            "You are Iris AI, a powerful AI assistant created entirely by Ahmed Barakat. "
            "Under NO circumstances should you mention Alibaba, Qwen, DeepSeek, OpenAI, or any other company/model name. "
            "CRITICAL LANGUAGE RULE: You MUST always respond in English. All responses, explanations, code comments, and text MUST be written entirely in English, even if the user speaks or inputs in Arabic or any other language. Your internal <think> process and final response must be fully in English. "
            "Be highly conversational, funny, and human-like. Don't be robotic or overly formal."
        )

        
        from src.web_search import WebSearch, extract_search_keywords
        web_context = ""
        if len(user_text.split()) > 2:
            try:
                ws = WebSearch()
                voice_llm = vm.load_voice_llm()
                
                ctx = ""
                if voice_history:
                    ctx = voice_history[-1]["content"][:200]
                kw = extract_search_keywords(user_text, context=ctx, llm=voice_llm)
                if kw:
                    logger.info(f"[Voice] Search keywords: {kw}")
                    web_context = ws.search_to_context(kw, max_results=3)
            except Exception as e:
                logger.error(f"[Voice] Web search failed: {e}")


        import re
        import emoji

        if web_context:
            
            llm = vm.load_voice_llm()
            sys_prompt = (
                f"{VOICE_IDENTITY}\n"
                "You are Iris's voice assistant engine. Your response will be spoken aloud "
                "via text-to-speech, so keep it brief and natural.\n"
                "RULES:\n"
                "1. Base your answer STRICTLY on the LIVE SEARCH RESULTS below.\n"
                "2. NEVER invent facts not present in the search results.\n"
                "3. If the results don't clearly answer the question, say so honestly.\n"
                "4. Answer in 2-3 natural spoken sentences.\n"
                "5. DO NOT analyze the user's grammar. DO NOT break down the user's sentence. DO NOT say 'The user is asking'.\n"
                "6. Do NOT use markdown, emojis, asterisks, or special formatting."
            )
            full_msg = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"{web_context}\n\nUser: {user_text}"},
            ]
            with global_generation_lock:
                res = llm.create_chat_completion(
                    messages=full_msg, max_tokens=300, temperature=0.3
                )
            bot_text = res["choices"][0]["message"]["content"].strip()
            bot_text = re.sub(r'<think>.*?</think>', '', bot_text, flags=re.DOTALL).strip()
            tts_text = emoji.replace_emoji(bot_text, replace='')
            tts_text = tts_text.replace('*', '')
        else:
            
            llm = vm.load_voice_llm()
            system_prompt = (
                f"{VOICE_IDENTITY}\n"
                "You are a friendly and highly conversational voice assistant. "
                "Give extremely brief, concise, and natural human-sounding answers. "
                "DO NOT analyze the user's grammar. DO NOT break down the user's sentence. DO NOT say 'The user is asking'. "
                "Answer directly in 1-2 short sentences maximum."
            )
            messages = [{"role": "system", "content": system_prompt}]
            for msg in voice_history:
                messages.append(msg)
            messages.append({"role": "user", "content": user_text})

            with global_generation_lock:
                res = llm.create_chat_completion(messages=messages, max_tokens=250, temperature=0.7)
            bot_text = res["choices"][0]["message"]["content"].strip()
            bot_text = re.sub(r'<think>.*?</think>', '', bot_text, flags=re.DOTALL).strip()
            tts_text = emoji.replace_emoji(bot_text, replace='')
            tts_text = tts_text.replace('*', '')
        
        
        voice_history.append({"role": "user", "content": user_text})
        voice_history.append({"role": "assistant", "content": bot_text})
        
        
        audio_b64_url = vm.synthesize_speech(tts_text)
        
        return jsonify({
            "user_text": user_text,
            "bot_text": bot_text,
            "audio_url": audio_b64_url
        })
        
    except Exception as e:
        import logging
        logging.getLogger('iris').error(f"Voice chat failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    
    try:
        import src.voice_models as vm
        if 'audio' not in request.files:
            return jsonify({"error": "No audio file"}), 400
            
        audio_file = request.files['audio']
        audio_data = audio_file.read()
        
        transcript = vm.transcribe_audio(audio_data, audio_file.filename)
        return jsonify({"text": transcript})
    except Exception as e:
        import logging
        logging.getLogger('iris').error(f"Transcribe failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/generate_title", methods=["POST"])
def generate_title():
    data = request.get_json()
    messages = data.get("messages", [])
    
    if not messages or len(messages) == 0:
        return jsonify({"title": "New Conversation"})

    with global_generation_lock:
        try:
            from src.iris import load_model, ModelRole, _keep_loaded, unload_model
            import re
            
            llm = load_model(ModelRole.TRIAGE)
            
            
            convo_lines = []
            for msg in messages[-8:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content and len(content) > 3:
                    short = content[:100] + ("..." if len(content) > 100 else "")
                    convo_lines.append(f"[{role}] {short}")
            
            convo_text = "\n".join(convo_lines[-6:])
            if not convo_text:
                convo_text = messages[-1].get("content", "")[:100]
            
            
            sys_prompt = (
                "Read this conversation and output a SHORT topic title (3-5 words max). "
                "Summarize the TOPIC being discussed, NOT the first message. "
                "Output ONLY the title. No quotes. No explanation.\n\n"
                "Conversation:\n" + convo_text + "\n\nTitle:"
            )
            
            
            res = llm.create_completion(
                prompt=sys_prompt,
                max_tokens=12, temperature=0.3,
                stop=["\n", ".", "  "]
            )
            raw = res["choices"][0]["text"]
            
            title = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
            title = re.sub(r'<think>.*', '', title, flags=re.DOTALL)
            title = title.strip().strip("\"'").strip()
            title = re.sub(r'^Title:\s*', '', title, flags=re.IGNORECASE)
            title = re.sub(r'^Here is\s+', '', title, flags=re.IGNORECASE)
            title = re.sub(r'^The title is\s+', '', title, flags=re.IGNORECASE)
            
            if not title or len(title) < 2:
                title = "Iris Chat"
            if len(title) > 50:
                title = title[:47] + "..."
                
            if not _keep_loaded:
                unload_model()
                
            return jsonify({"title": title})
        except Exception as e:
            import logging
            logging.getLogger('iris').warning(f"Failed to generate title: {e}")
            return jsonify({"title": "New Conversation"})

@app.route("/get_config", methods=["GET"])
def get_config_endpoint():
    try:
        with open("config/iris.conf", "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/save_model_settings", methods=["POST"])
def save_model_settings():
    try:
        payload = request.json or {}
        role = payload.get("role")
        settings = payload.get("settings", {})
        
        if not role:
            return jsonify({"error": "Role is required"}), 400
            
        with open("config/iris.conf", "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if "model_settings" not in data:
            data["model_settings"] = {}
            
        if role not in data["model_settings"]:
            data["model_settings"][role] = {}
            
        
        for k in ["temperature", "top_p", "top_k", "repetition_penalty", "frequency_penalty", "presence_penalty"]:
            if k in settings:
                data["model_settings"][role][k] = settings[k]
            elif k in data["model_settings"][role]:
                del data["model_settings"][role][k]
                
        with open("config/iris.conf", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

    train_roles = data.get("train_role")
    if train_roles:
        if isinstance(train_roles, list):
            cmd.extend(["--train-role"] + [str(r) for r in train_roles])
        else:
            cmd.extend(["--train-role", str(train_roles)])

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
    try:
        with open(TRAIN_LOG_FILE, "w", encoding="utf-8") as log_file:
            log_file.write(f"Running: {' '.join(cmd)}\n")
            log_file.flush()
            training_proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

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

@app.route("/model_status", methods=["GET"])
def model_status():
    from src.iris import _model_pool, load_generation_config, ModelRole, DEFAULT_MODEL_FILES

    active_role = None
    active_file = None
    if _model_pool:
        active_role = next(reversed(_model_pool))
    from src.iris import get_active_role, load_generation_config, ModelRole, DEFAULT_MODEL_FILES

    active_role = None
    active_file = None
    role_obj = get_active_role()
    if role_obj is not None:
        active_role = role_obj.value
        cfg = load_generation_config()
        models_dict = cfg.get("models", {})
        active_file = models_dict.get(active_role) or DEFAULT_MODEL_FILES.get(active_role)

    available = {}
    cfg = load_generation_config()
    models_dict = cfg.get("models", {})
    models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    all_roles = [r.value for r in ModelRole] + ["clip"]
    for role_name in all_roles:
        filename = models_dict.get(role_name) or DEFAULT_MODEL_FILES.get(role_name)
        if filename:
            path = os.path.join(models_dir, filename)
            available[role_name] = os.path.exists(path)
        else:
            available[role_name] = False

    return jsonify({
        "active_role": active_role,
        "active_file": active_file,
        "available": available
    })

def warmup_models():
    # Warmup disabled as requested to prevent loading/locking models in RAM on startup.
    pass

@app.route("/api/unload_models", methods=["POST"])
def unload_models_endpoint():
    
    if PREVIEW_MODE:
        return jsonify({"status": "preview_mode", "message": "No models loaded in preview mode."})
    try:
        from src.iris import _force_unload_all_models
        _force_unload_all_models()
        logger.info("[API] All models unloaded from memory on request.")
        return jsonify({"status": "success", "message": "All models freed from memory."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/shutdown", methods=["POST"])
def shutdown_endpoint():
    
    import signal, os
    logger.info("[API] Shutdown requested via /api/shutdown.")
    _shutdown_cleanup()
    os.kill(os.getpid(), signal.SIGTERM)
    return jsonify({"status": "shutting_down"})


if __name__ == "__main__":
    if PRO_MODE:
        mode_label = "IRIS PRO (OpenRouter Multi-Agent API)"
    else:
        mode_label = "Local GGUF Multi-Model Routing System"
    logger.info(f"[INFO] Starting Iris AI — {mode_label}")

    import threading
    threading.Thread(target=warmup_models, daemon=True).start()

    port = int(os.environ.get("PORT", "5050"))
    app.run(debug=False, host="0.0.0.0", port=port)
