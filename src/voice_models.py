import os
import io
import torch
import numpy as np
import soundfile as sf
import librosa
from threading import Lock

# Voice Models
STT_MODEL_ID = "distil-whisper/distil-small.en"
TTS_MODEL_DIR = "models/voice"
PIPER_MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
PIPER_JSON_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"

VOICE_LLM_URL = "https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf"

_stt_processor = None
_stt_model = None
_tts_pipeline = None
_voice_llm = None

_voice_lock = Lock()

def _download_file(url, dest):
    import urllib.request
    import logging
    logging.getLogger('iris').info(f"[Voice] Downloading {os.path.basename(dest)}...")
    urllib.request.urlretrieve(url, dest)
    logging.getLogger('iris').info(f"[Voice] Downloaded {os.path.basename(dest)}")

def load_stt_model():
    global _stt_processor, _stt_model
    with _voice_lock:
        if _stt_model is not None:
            return _stt_processor, _stt_model
            
        import logging
        logging.getLogger('iris').info(f"[Voice] Loading STT model: {STT_MODEL_ID}")
        
        # Suppress the massive wall of harmless Whisper warnings
        logging.getLogger("transformers").setLevel(logging.ERROR)
        
        from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq
        
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        _stt_processor = AutoProcessor.from_pretrained(STT_MODEL_ID)
        _stt_model = AutoModelForSpeechSeq2Seq.from_pretrained(STT_MODEL_ID).to(device)
        
        return _stt_processor, _stt_model

def load_tts_model():
    global _tts_pipeline
    with _voice_lock:
        if _tts_pipeline is not None:
            return _tts_pipeline
            
        import logging
        logging.getLogger('iris').info("[Voice] Loading Piper TTS model")
        
        os.makedirs(TTS_MODEL_DIR, exist_ok=True)
        onnx_path = os.path.join(TTS_MODEL_DIR, "en_US-lessac-medium.onnx")
        json_path = os.path.join(TTS_MODEL_DIR, "en_US-lessac-medium.onnx.json")
        
        if not os.path.exists(onnx_path):
            _download_file(PIPER_MODEL_URL, onnx_path)
        if not os.path.exists(json_path):
            _download_file(PIPER_JSON_URL, json_path)
            
        from piper import PiperVoice
        
        # Load Piper using ONNX
        _tts_pipeline = PiperVoice.load(onnx_path, config_path=json_path, use_cuda=False)
        
        return _tts_pipeline

def load_voice_llm():
    global _voice_llm
    with _voice_lock:
        if _voice_llm is not None:
            return _voice_llm
            
        import logging
        logging.getLogger('iris').info("[Voice] Loading ultra-fast Conversational LLM (Llama-3.2-1B)")
        
        # Save as iris_008.gguf in the main models directory
        _root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        llm_path = os.path.join(_root_dir, "models", "iris_008.gguf")
        
        if not os.path.exists(llm_path):
            _download_file(VOICE_LLM_URL, llm_path)
            
        from llama_cpp import Llama
        # Use a very small context window specifically for Voice Chat to ensure instant loading
        _voice_llm = Llama(
            model_path=llm_path,
            n_ctx=2048,
            n_gpu_layers=-1, # Accelerate on Metal/GPU
            n_threads=4,     # CRITICAL: Prevent OS starvation on Macs by limiting threads
            verbose=False
        )
        return _voice_llm

def transcribe_audio(audio_data: bytes, original_filename: str) -> str:
    """Converts recorded audio bytes to text using Moonshine."""
    processor, model = load_stt_model()
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name
        
    try:
        audio_array, sr = librosa.load(tmp_path, sr=16000)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            
    inputs = processor(audio_array, return_tensors="pt", sampling_rate=16000)
    inputs = {k: v.to(device=device, dtype=model.dtype) if torch.is_floating_point(v) else v.to(device) for k, v in inputs.items()}
    
    with torch.no_grad():
        output = model.generate(**inputs)
        
    text = processor.decode(output[0], skip_special_tokens=True)
    return text.strip()

def synthesize_speech(text: str) -> str:
    """Converts text to speech using Piper TTS and returns a base64 encoded wav."""
    piper_voice = load_tts_model()
    
    import logging
    logger = logging.getLogger('iris')
    
    if not text.strip():
        return None
        
    try:
        logger.info("[Voice] Generating Piper TTS response...")
        
        import wave
        import io
        import base64
        
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wav_file:
            # synthesize_wav automatically sets format, channels, and sample rate
            piper_voice.synthesize_wav(text.strip(), wav_file)
            
        wav_bytes = wav_io.getvalue()
        b64_audio = base64.b64encode(wav_bytes).decode('utf-8')
        
        return f"data:audio/wav;base64,{b64_audio}"
        
    except Exception as e:
        logger.error(f"[Voice] TTS failed: {e}")
        return None
