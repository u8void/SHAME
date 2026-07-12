import torch
import torch.nn as nn
from transformers import Trainer, TrainingArguments

class DummyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.linear = nn.Linear(10, 10)
    def forward(self, input_ids, labels=None):
        return {"loss": torch.tensor(1.0, requires_grad=True)}

model = DummyModel()
model.is_model_parallel = True

args = TrainingArguments(output_dir="./tmp", report_to="none")
print("Original n_gpu:", args.n_gpu)
try:
    args._n_gpu = 1
    print("Modified n_gpu:", args.n_gpu)
except Exception as e:
    print("Cannot modify _n_gpu", e)

trainer = Trainer(model=model, args=args)
wrapped = trainer._wrap_model(trainer.model_wrapped)
print("Is DataParallel:", isinstance(wrapped, nn.DataParallel))

