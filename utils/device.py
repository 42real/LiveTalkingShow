import torch
import os

_CONFIGURED = False


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configure_torch_performance():
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    if not torch.cuda.is_available():
        return

    torch.backends.cudnn.benchmark = _env_flag("LIVETALKING_CUDNN_BENCHMARK", True)
    use_tf32 = _env_flag("LIVETALKING_TORCH_TF32", True)
    torch.backends.cuda.matmul.allow_tf32 = use_tf32
    torch.backends.cudnn.allow_tf32 = use_tf32

    precision = os.getenv("LIVETALKING_FLOAT32_MATMUL_PRECISION", "high").strip()
    if hasattr(torch, "set_float32_matmul_precision") and precision:
        torch.set_float32_matmul_precision(precision)

def initialize_device():
    configure_torch_performance()
    if torch.cuda.is_available():
        return torch.device('cuda')
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device('mps')
    else:
        return torch.device('cpu')
