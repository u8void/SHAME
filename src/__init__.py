
from .iris import ask_stream
from .iris_rag import BookRetriever
from .iris_engine import (
    download_gguf,
    _MODEL_SOURCES,
    load_model,
    unload_model,
    ModelRole,
    TaskType,
    get_device,
    load_generation_config,
)

from .iris_vision import analyze_image
from .iris_coding import generate_internal_code
from .syntax_checker import check_syntax, extract_code_blocks
from .context_compactor import (
    estimate_tokens,
    compact_light,
    compact_context,
    auto_compact_for_role,
    CompactionLevel,
)

from .grpo_trainer import (
    train_with_grpo,
    GRPOConfig,
    GRPOTrainer,
    GRPOMetrics,
    GRPOSample,
    GRPODataset,
    RewardScorer,
    RewardDomain,
    GGUFPolicyBridge,
)
