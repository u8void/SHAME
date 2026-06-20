
from .iris import (
    download_gguf,
    _MODEL_SOURCES,
    ask_stream,
    load_model,
    unload_model,
    solve_math,
    analyze_image,
    BookRetriever,
    ModelRole,
    TaskType,
    get_device,
    load_generation_config,
    generate_internal_code,
)
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
