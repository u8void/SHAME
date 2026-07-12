import torch
from transformers import AutoModelForCausalLM
from peft import get_peft_model, LoraConfig, TaskType

print("Loading dummy...")
model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen1.5-0.5B", device_map="auto", torch_dtype=torch.float16)
print("Base map:", getattr(model, "hf_device_map", None))
config = LoraConfig(r=8, target_modules=["q_proj", "v_proj"], task_type=TaskType.CAUSAL_LM)
peft_model = get_peft_model(model, config)
print("PEFT map:", getattr(peft_model, "hf_device_map", None))
