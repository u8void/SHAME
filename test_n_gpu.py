from transformers import TrainingArguments
args = TrainingArguments(output_dir="./tmp")
print("Before:", args.n_gpu)
args._n_gpu = 1
print("After:", args.n_gpu)
