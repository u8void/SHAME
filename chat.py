import os

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from iris import chat, get_device


def main():
    checkpoint = "gpt2_sft_chatbot_best.pt"
    model_name = "microsoft/DialoGPT-medium"

    device = get_device()
    print(f"Using device: {device}   |   FP32")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        low_cpu_mem_usage=True,
        dtype=torch.float32,
    ).to(device)

    if os.path.exists(checkpoint):
        model.load_state_dict(torch.load(checkpoint, map_location=device))
        print(f"Loaded checkpoint '{checkpoint}'.")
    else:
        print("No checkpoint found, using base model.")

    chat(model, tokenizer, device)


if __name__ == "__main__":
    main()
