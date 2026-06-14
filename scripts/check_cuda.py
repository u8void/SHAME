import torch

def check_pytorch_device():
    print(f"PyTorch Version: {torch.__version__}")
    
    # Check if CUDA (GPU support) is available
    cuda_available = torch.cuda.is_available()
    print(f"CUDA Available: {cuda_available}")
    
    if cuda_available:
        # Get the number of available GPUs
        device_count = torch.cuda.device_count()
        print(f"Number of GPUs detected: {device_count}")
        
        # Get the name of the current GPU
        current_device = torch.cuda.current_device()
        gpu_name = torch.cuda.get_device_name(current_device)
        print(f"Current GPU Device ID: {current_device}")
        print(f"GPU Model: {gpu_name}")
        
        # Set device to CUDA
        device = torch.device("cuda")
    else:
        print("CUDA is not available. PyTorch will run on the CPU.")
        # Set device to CPU
        device = torch.device("cpu")
        
    print(f"\nTarget device for tensors/models: {device}")

if __name__ == "__main__":
    check_pytorch_device()
