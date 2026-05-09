#!/usr/bin/env python3
import os, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from iris import chat, get_device   # your existing functions

CHECKPOINT = "./iris_merged_model"

def load_model(device, force_cpu=False):
    
    tokenizer = AutoTokenizer.from_pretrained(CHECKPOINT)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if device.type == "cuda":
        try:
            from transformers import BitsAndBytesConfig
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
            )
            model = AutoModelForCausalLM.from_pretrained(
                CHECKPOINT,
                quantization_config=bnb_config,
                device_map="auto",
                low_cpu_mem_usage=True,
            )
            print("Loaded in 4bit for CUDA")
        except ImportError:
            model = AutoModelForCausalLM.from_pretrained(
                CHECKPOINT,
                torch_dtype=torch.float16,
                low_cpu_mem_usage=True,
            ).to(device)
            print("Loaded in FP16 for CUDA (bitsandbytes not available)")
    elif device.type == "mps":
        model = AutoModelForCausalLM.from_pretrained(
            CHECKPOINT,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
        ).to(device)
    else:
        model = AutoModelForCausalLM.from_pretrained(
            CHECKPOINT,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
        ).to(device)

    model.eval()
    return model, tokenizer

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=["cuda", "mps", "cpu"], default=None)
    args = parser.parse_args()

    device = get_device(force_cpu=(args.device == "cpu"))
    print(f"Using device: {device}   |   Loading merged model …")

    model, tokenizer = load_model(device)
    chat(model, tokenizer, device)   # <-- directly uses your existing loop!