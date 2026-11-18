from functools import cache


@cache
def get_device() -> str:
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def gpu_name() -> str | None:
    try:
        import torch
    except ImportError:
        return None
    return torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
