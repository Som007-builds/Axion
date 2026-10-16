"""
Apply human labels to contradicts_review.csv using the 3-question rubric:
  Q1: Are they about the SAME specific thing? (same benchmark, model, method, measurement) → if no → UNRELATED
  Q2: If yes — do they roughly agree? → SUPPORTS
  Q3: If yes — do they genuinely conflict on the same setup? → CONTRADICTS
"""
import csv

# pair_id → human_label
# Reasoning applied per pair below.

labels = {
    # 0: CoT beats standard vs L2M beats CoT — different methods being compared, but both about math prompting performance. L2M says it beats CoT → genuinely conflicts with "CoT achieves better results"
    0: "CONTRADICTS",
    # 1: GPT-3 davinci beats ada on arithmetic vs GPT-3 struggles on >3 digit addition — different aspects of GPT-3 arithmetic (model scale vs digit length). Not same specific setup.
    1: "UNRELATED",
    # 2: creating rationales is hard vs L2M beats CoT at math — completely different topics (data creation difficulty vs prompting method comparison)
    2: "UNRELATED",
    # 3: CoT reduces error on HellaSwag vs L2M beats CoT on Non-football task — different benchmarks (HellaSwag vs Non-football)
    3: "UNRELATED",
    # 4: "proposed method" achieves SOTA on GSM8K vs CoT achieves SOTA on GSM8K — both claim SOTA on GSM8K → agree
    4: "SUPPORTS",
    # 5: Method improves accuracy 74.4%→82.1% on GSM8K vs PaLM standard prompting gets 55% on GSM8K — different methods (improved method vs standard prompting), not contradicting
    5: "UNRELATED",
    # 6: +100M params → 5% perplexity improvement vs 128M outperforms 16M by 12% accuracy — different models, different metrics (perplexity vs accuracy), different comparisons
    6: "UNRELATED",
    # 7: synergy between interpretability and performance vs L2M improves interpretability over CoT — different topics (general claim vs specific method comparison)
    7: "UNRELATED",
    # 8: CoT gets only 16% on SCAN vs CoT can achieve SOTA on certain benchmarks — same method (CoT), but different benchmarks (SCAN vs "certain benchmarks"). Claim B is vague. Both can be true simultaneously.
    8: "UNRELATED",
    # 9: L2M outperforms CoT on compositional generalization vs CoT improves performance on a range of tasks — not contradictory; CoT improving on "a range" doesn't exclude L2M being better on specific tasks
    9: "UNRELATED",
    # 10: L2M requires no training/finetuning vs few-shot prompting doesn't improve with scale — completely different claims (method requirement vs scaling behavior)
    10: "UNRELATED",
    # 11: L2M reduces annotated examples needed vs few-shot prompting doesn't improve with scale — different topics
    11: "UNRELATED",
    # 12: Model response time 150ms on 10 concurrent queries vs TTS inference 35ms on A100 — completely different models/systems (general model vs TTS)
    12: "UNRELATED",
    # 13: creating rationales is hard vs 30% of model-generated skills need refinement — different topics (rationale creation vs skill refinement)
    13: "UNRELATED",
    # 14: OPT 125M-175B vs experiments use ~10M param models — different model families entirely
    14: "UNRELATED",
    # 15: OPT 125M-175B vs model has 34M params — different model families
    15: "UNRELATED",
    # 16: OPT 125M-175B vs 3.5B parameter reduction via fine-tuning — different model families, different topics
    16: "UNRELATED",
    # 17: 2.1% perplexity improvement on C4 full vs. 20% perplexity increase with 10% more compute — different models, different datasets, different experimental setups
    17: "UNRELATED",
    # 18: best hyperparams: lr 0.002, batch 64, patience 5 vs lr 1e-4, 140 RL iterations — different models entirely
    18: "UNRELATED",
    # 19: ensemble +4.2% accuracy on PASCAL VOC vs SkillOpt outperforms on 52/52 cells across six benchmarks — completely different systems and benchmarks
    19: "UNRELATED",
    # 20: data pruning −20% model size on SQuAD vs Shannon perspective −25% model size — different methods, different benchmarks
    20: "UNRELATED",
    # 21: fine-tuning on reasoning is critical for LLM self-improvement vs LLMs need ≥500M params for optimal F1 — different claims (method importance vs size requirement)
    21: "UNRELATED",
    # 22: LLMs fail at Python code execution (≤30% accuracy) vs method improves LM accuracy by 5pp — different tasks (code execution vs general accuracy on labeled data)
    22: "UNRELATED",
    # 23: Models execute programs at 85%+ success vs 30% of skills need refinement — different things (program execution vs skill stability)
    23: "UNRELATED",
    # 24: −21.1% parameters vs −25% model size (Shannon) — different methods, different contexts
    24: "UNRELATED",
    # 25: framework scales to 3.2B params vs model has 34M params with 25.8% capacity increase — different systems entirely
    25: "UNRELATED",
    # 26: framework scales to 3.2B params vs 3.5B parameter reduction via fine-tuning — different systems
    26: "UNRELATED",
    # 27: framework scales to 3.2B params vs SkillOpt optimizer has 50M params — different systems
    27: "UNRELATED",
    # 28: experiments use ~10M param models vs model has 34M params — different experiment contexts
    28: "UNRELATED",
    # 29: LaMo inference 24.5 fps on A100 vs TTS inference 35ms on A100 — completely different systems (video vs TTS)
    29: "UNRELATED",
    # 30: LaMo inference 24.5 fps on A100 vs TTS inference 35.6ms on A100 — different systems (video vs TTS)
    30: "UNRELATED",
    # 31: LaMo 256x256@30fps vs model generates 81 frames 480×832 — different video generation models, different specs
    31: "UNRELATED",
    # 32: LaMo 512M params, 128 GPU-hours vs framework scales to 3.2B without time increase — different systems
    32: "UNRELATED",
    # 33: method needs ~20 hours per video gen vs approach takes 34 min for 10s video — different methods for different tasks
    33: "UNRELATED",
    # 34: method needs ~20 hours per video gen vs Geo-Align reduces runtime by 30% — different methods
    34: "UNRELATED",
    # 35: proposed approach outperforms on video realism vs existing V2V methods struggle with camera trajectories — one says "ours is better", other says "existing methods struggle" — could be supportive (ours overcomes what others struggle with)
    35: "UNRELATED",
    # 36: distillation reduces errors by 30% vs 30% of skills need refinement — completely different topics
    36: "UNRELATED",
    # 37: LaMo inference 12.7ms vs approach takes 34 min for 10s video — different systems (LaMo inference vs video processing pipeline)
    37: "UNRELATED",
    # 38: −14.5% params for EMA model vs experiments use ~10M params — different systems
    38: "UNRELATED",
    # 39: TTS inference 35.6ms on A100 vs video approach takes 34 min on V100 — completely different systems (TTS vs video)
    39: "UNRELATED",
    # 40: TTS inference 35.6ms vs LaMo inference 12.7ms — different systems (TTS vs video model)
    40: "UNRELATED",
    # 41: TTS inference 35ms on A100 vs video approach 34 min on V100 — different systems
    41: "UNRELATED",
    # 42: TTS inference 35ms vs post-training 130 hours on 64 A800s — different things entirely (inference time vs training time)
    42: "UNRELATED",
    # 43: Model response 150ms vs TTS inference 35.6ms — different systems
    43: "UNRELATED",
    # 44: Model response 150ms vs code change inference 12ms — different systems
    44: "UNRELATED",
    # 45: CoT model 530M params vs largest LM 1.5B params — different models
    45: "UNRELATED",
    # 46: CoT model 530M params vs Looped Diffusion 340M params — different models
    46: "UNRELATED",
    # 47: OPT 125M-175B vs SkillOpt smaller than 5.4B GPT by ≥1.8B — different model families
    47: "UNRELATED",
    # 48: +100M params → 5% perplexity vs 15% absolute accuracy improvement on perplexity — different models, different datasets; same metric (perplexity) but different magnitudes. Not same experiment.
    48: "UNRELATED",
    # 49: +100M params → 5% perplexity vs noisy channel gives 10% perplexity improvement on 1B model — different methods and scales, but both about perplexity improvement. Not same specific setup.
    49: "UNRELATED",
    # 50: 35.7% latency reduction vs Looped Diffusion 20% latency reduction — different systems
    50: "UNRELATED",
    # 51: −22.1% inference time on SQuAD vs 1.2x speedup (345M model) — different methods, different models
    51: "UNRELATED",
    # 52: 2.5:1 success/failure ratio vs optimal ratio is domain-specific — B says ratio depends on domain, A reports one specific ratio. Not contradictory.
    52: "UNRELATED",
    # 53: −21.1% params vs −20% model size without accuracy loss — different methods, but both about model size reduction with similar magnitudes. Could be supports if same thing, but they're different systems.
    53: "UNRELATED",
    # 54: −21.1% params vs VeriTrace needs 120M params (−30%) — different systems
    54: "UNRELATED",
    # 55: −25% model size without performance loss (Shannon) vs larger model improves performance — potentially contradictory: one says you can shrink without loss, other says bigger is better. But they're about different approaches/contexts.
    55: "UNRELATED",
    # 56: −25% model size (Shannon) vs increasing capacity 50%→2000% lets you reduce dataset 30% — different topics (model compression vs data-compute tradeoff)
    56: "UNRELATED",
    # 57: framework scales to 3.2B vs VeriTrace needs 120M params — different frameworks
    57: "UNRELATED",
    # 58: 12% robustness improvement on MNIST vs 2.1% F1 improvement on MNIST — same dataset (MNIST)! Different metrics (robustness vs F1) and different magnitudes. Not measuring same thing exactly.
    58: "UNRELATED",
    # 59: noisy channel +20% peak memory vs method −8% peak memory — different methods applied to different systems. Not same method/model.
    59: "UNRELATED",
    # 60: scaling >2B params → 2% latency increase vs 50% more params → 25% latency increase — both about scaling params and latency. Different specific setups but same phenomenon. The magnitudes differ greatly (2% vs 25%) which could be contradictory, but they're different models at different scales.
    60: "UNRELATED",
    # 61: scaling >2B → 2% latency increase vs Looped Diffusion achieves 20% latency reduction — different systems (scaling analysis vs specific model)
    61: "UNRELATED",
    # 62: scaling law +5% F1 on multiclass vs ORPQUANT maintains 92.1% F1 with 50% size reduction — different systems, different approaches
    62: "UNRELATED",
    # 63: scaling law +5% F1 vs CodeChange model +10% F1 — different systems, different datasets
    63: "UNRELATED",
    # 64: test on ImageNet/CIFAR-100/SVHN/IMDB vs evaluate on UNO-1M dataset — different datasets, different methods
    64: "UNRELATED",
    # 65: ~10M param models vs VeriTrace 120M params — different systems
    65: "UNRELATED",
    # 66: ~10M param models vs largest LM 1.5B params — different systems
    66: "UNRELATED",
    # 67: LLM scaling not strictly monotonic vs model scale not correlated with performance — both say scaling doesn't reliably help. Same topic, same direction.
    67: "SUPPORTS",
    # 68: LaMo 512M, 128 GPU-hours vs system scaling −30% training time for 1.1B models — different systems
    68: "UNRELATED",
    # 69: method needs ~20 hours per video gen vs Few-step Generators need 3 hours to train — different things (generation time vs training time)
    69: "UNRELATED",
    # 70: diffusion model −30% compute vs method −30% compute compared to traditional scaling — both claim 30% compute reduction. Could be same or different methods. Different papers/contexts.
    70: "UNRELATED",
    # 71: 34M param model vs VeriTrace 120M params — different systems
    71: "UNRELATED",
    # 72: post-training 130 hours on 64 A800s vs Few-step Generators 3 hours on single V100 — different systems
    72: "UNRELATED",
    # 73: model generates 81 frames 480×832 vs LaMo 256x256@30fps — different video models. Same as pair 31 reversed.
    73: "UNRELATED",
    # 74: post-training 130h on 64 A800s vs training on 8 H100s with lr 1e-5 — different systems
    74: "UNRELATED",
    # 75: post-training 130h on 64 A800s vs Few-step Generators 3h on V100 — different systems
    75: "UNRELATED",
    # 76: constant lr 1e-4, 140 RL iterations vs frontier optimizer needs 500 iterations (200 with lr schedule) — different models/optimizers entirely
    76: "UNRELATED",
    # 77: training 2h per RL iteration on 64 A800s vs training 3h45m on single CPU — different systems, different hardware
    77: "UNRELATED",
    # 78: post-training 130h on 64 A800s vs Few-step Generators 3h on V100 — different systems (same as 75)
    78: "UNRELATED",
    # 79: post-training 130h on 64 A800s vs model reduces training time 25% on V100 — different systems
    79: "UNRELATED",
    # 80: post-training 130h on 64 A800s vs training 3h45m on single CPU — different systems (same as 77)
    80: "UNRELATED",
    # 81: −30% data augmentation needed vs data aug gives 12% improvement on GRB dataset — different contexts (reduction in augmentation need vs augmentation benefit)
    81: "UNRELATED",
    # 82: −30% data augmentation needed vs −25% training data needed — both about data efficiency. Different methods, different datasets. Similar direction.
    82: "UNRELATED",
    # 83: video processing 34 min on V100 vs Few-step Generators 3h training on V100 — different things (inference vs training)
    83: "UNRELATED",
    # 84: video processing 34 min on V100 vs model reduces training time 25% on V100 — different things (processing time vs training time reduction)
    84: "UNRELATED",
    # 85: PiD 62.5% win rate over 2 rounds vs experiment caps at 3-5 rounds — completely different things (win rate vs round count)
    85: "UNRELATED",
    # 86: PSNR difference 1.05 dB vs ORPQUANT PSNR improvement 1.2 dB — different systems, but both about PSNR improvement over baseline. Close magnitudes. Different methods/datasets though.
    86: "UNRELATED",
    # 87: image quality preferred 62.1% of time vs visual quality +10% over baselines — different metrics, different systems
    87: "UNRELATED",
    # 88: dual-scoring +17.9% F0 accuracy vs framework +10% F1 — different metrics (F0 accuracy vs F1), different systems
    88: "UNRELATED",
    # 89: TTS inference 35.6ms on A100 vs code change inference 12ms on V100 — different systems
    89: "UNRELATED",
    # 90: TTS inference 35.6ms vs post-training 130h on A800s — inference vs training, different systems
    90: "UNRELATED",
    # 91: neither scale nor plausibility predicts downstream utility vs scaling beyond threshold degrades fine-tuning — both about scaling not reliably helping. B goes further (degradation). Same topic, roughly agree.
    91: "SUPPORTS",
    # 92: GPT-5.4 judge accuracy 46.4% (random) vs SkillOpt +38.9% on SpreadsheetBench for GPT-5.5 — different tasks (judging/selection vs task performance), different model versions
    92: "UNRELATED",
    # 93: 1.8B outperforms 1.5B by 5.4% on GLUE vs 220M→440M gives 15% increase on GLUE — same benchmark (GLUE), both about scaling improving accuracy. Different model sizes, different improvement magnitudes. Both say bigger is better on GLUE. 
    93: "SUPPORTS",
    # 94: BERT-large −40% memory bandwidth vs noisy channel +20% peak memory — different models, different measurements (bandwidth vs peak memory)
    94: "UNRELATED",
    # 95: TTS model 2.1GB memory on A100 vs post-training 130h on 64 A800s — different things (memory footprint vs training time)
    95: "UNRELATED",
    # 96: CoT improves on arithmetic/commonsense/symbolic vs L2M outperforms CoT on symbolic manipulation — same topic (symbolic reasoning). CoT says it improves, L2M says it beats CoT. A tension exists: A says CoT helps on symbolic, B says L2M beats CoT on symbolic. This is a genuine contradiction.
    96: "CONTRADICTS",
    # 97: OPT-175B comparable to GPT-3 vs GPT-3 lower performance than LaMDA/PaLM on symbolic reasoning — if OPT≈GPT-3, and GPT-3 is worse than LaMDA/PaLM, that's not a contradiction. Different claims.
    97: "UNRELATED",
    # 98: LMSI on UL2 improves reasoning but not as much as PaLM-540B vs PaLM-540B achieves 82.1% outperforming LaMDA — both reference PaLM-540B performance. A says PaLM gets better improvement than UL2. B gives specific PaLM number. These are complementary, not contradictory.
    98: "UNRELATED",
    # 99: data aug +2.5% on GLUE dev set vs scratchpad +25% accuracy — different methods (data augmentation vs scratchpad), different magnitudes. Not same thing.
    99: "UNRELATED",
    # 100: data pruning −20% model size on SQuAD vs inference time −22.1% on SQuAD v2.0 — same benchmark family (SQuAD). But one is about model size, other about inference time. Not conflicting.
    100: "UNRELATED",
    # 101: 24.5% self-improvement on C4 vs LLMs fail at Python code execution (≤30%) — completely different tasks (language modeling vs code execution)
    101: "UNRELATED",
    # 102: CoT −15.6% MSE on MATH vs L2M solves math better than CoT — same topic (math reasoning), claims tension: CoT works well (A) but L2M beats CoT (B). B doesn't say CoT is bad, just that L2M is better.
    102: "UNRELATED",
    # 103: F1 93.4% on few-shot QA vs few-shot prompting doesn't improve with scale — A reports good few-shot performance, B says few-shot doesn't scale. Not necessarily contradictory (A could be at one specific scale).
    103: "UNRELATED",
    # 104: text-davinci-002 beats zero-shot by 33.8% vs few-shot doesn't improve with scale — A compares few-shot to zero-shot (specific model, specific task), B is about scaling behavior. Not directly contradictory.
    104: "UNRELATED",
    # 105: OPT 125M-175B vs SkillOpt optimizer 50M params — different systems entirely
    105: "UNRELATED",
    # 106: early stopping −30% training time on WMT vs SkillOpt meta update adds ≤30min — different systems, different topics
    106: "UNRELATED",
    # 107: BERT-large −40% memory bandwidth vs 20% perplexity increase with 10% more compute — different models, different measurements
    107: "UNRELATED",
    # 108: −31.4% compute cost vs −20% model size — different things (compute cost vs model size), different methods
    108: "UNRELATED",
    # 109: +12.5% F1 on 'Science' domain vs +10% F1 on test set — different systems, different datasets
    109: "UNRELATED",
    # 110: 34.7% knowledge coverage in 'Animals' vs models ≤30% on spatial numerical — different tasks, different models
    110: "UNRELATED",
    # 111: −20% model size vs 3.5B parameter reduction — different methods, different contexts
    111: "UNRELATED",
    # 112: +20M params → 10% quality degradation vs scaling beyond threshold degrades performance — both about scaling causing degradation. Same phenomenon, different contexts. Agree in direction.
    112: "SUPPORTS",
    # 113: LaMo 0.35x compute overhead on V100 vs approach takes 34 min for video on V100 — different systems
    113: "UNRELATED",
    # 114: LaMo inference 12.7ms vs PiD inference 210ms on GB200 — different models, different GPUs
    114: "UNRELATED",
    # 115: TTS 2.1GB on A100 vs PiD 13GB peak on RTX 5090 — different models, different GPUs
    115: "UNRELATED",
    # 116: correlation 0.7 (iterations vs perplexity) vs correlation 0.85 (performance vs training samples) — different relationships being measured (iterations vs samples)
    116: "UNRELATED",
    # 117: ensemble +4.2% on PASCAL VOC vs ensemble +5% on GRB dataset — different datasets, but both about ensemble method improvements. Similar magnitudes.
    117: "UNRELATED",
    # 118: data aug +2.5% on GLUE vs data aug +12% on GRB — different datasets, different magnitudes. Same technique name but different contexts.
    118: "UNRELATED",
    # 119: single-line training +23.4% on MBPP-aug vs data aug +12% on GRB — different everything
    119: "UNRELATED",
    # 120: −35.7% latency on real queries vs −25% tool latency vs Claude Code — different systems
    120: "UNRELATED",
    # 121: −22.1% inference time on SQuAD vs +50% params → +25% inference time — different models. A reduces time, B says scaling increases it. Not same model.
    121: "UNRELATED",
    # 122: +10% F1 on test set vs +20% F1 on multimodal dataset (PRISM) — different systems, different datasets
    122: "UNRELATED",
    # 123: −20% model size vs increasing capacity 50→2000% reduces dataset need 30% — different approaches/topics
    123: "UNRELATED",
    # 124: 1.8B outperforms 1.5B by 5.4% on GLUE (scaling helps) vs model scale not correlated with performance — same topic (scaling vs performance). A says scaling helps on GLUE, B says scale doesn't correlate. Genuine conflict.
    124: "CONTRADICTS",
    # 125: 1.5B param model gets 4.23 BLEU on WikiText103 vs 345M model gets 17.42 perplexity on WikiText103 — same benchmark but different metrics (BLEU vs perplexity) and different model sizes. Not contradictory.
    125: "UNRELATED",
    # 126: diffusion model −30% compute vs Looped Diffusion −15% compute — different models. Both reduce compute but different amounts. If they were about the same model, 30% vs 15% would conflict, but they're different.
    126: "UNRELATED",
    # 127: LaMo 0.35x overhead on V100 vs model −25% training time on V100 — different systems
    127: "UNRELATED",
    # 128: synthetic camera trajectories −30% training time vs lower lr → −0.5% accuracy on synthetic data — different topics (training time vs accuracy effect of lr)
    128: "UNRELATED",
    # 129: post-training 130h on 64 A800s vs model −25% training time on V100 — different systems
    129: "UNRELATED",
    # 130: constant lr 1e-4, 140 iterations vs frontier optimizer 500 iterations (200 with schedule) — different systems
    130: "UNRELATED",
    # 131: Geo-Align 2.1GB memory on 8-GPU vs −20% memory for 770M models on V100 — different systems
    131: "UNRELATED",
    # 132: constant lr 1e-4, 140 RL iterations vs frontier optimizer 500/200 iterations — different systems (same as 130)
    132: "UNRELATED",
    # 133: PiD inference 210ms on GB200 vs LaMo 24.5 fps on A100 — different systems, different GPUs
    133: "UNRELATED",
    # 134: PSNR difference 1.05 dB vs PSNR improvement 3.2 dB — different systems, different scales of improvement
    134: "UNRELATED",
    # 135: DMD2 distills to 4 steps vs model uses T=25 denoising timesteps — different models (DMD2 vs Geo-Align). Different number of steps. But they're about different systems.
    135: "UNRELATED",
    # 136: FID 12.45 on PiD 4K validation vs FID 12.5 on CelebA — same metric, very close values! But different datasets (PiD 4K validation vs CelebA) and different models.
    136: "UNRELATED",
    # 137: −14.5% params for EMA vs VeriTrace −30% params — different systems
    137: "UNRELATED",
    # 138: TTS inference 35.6ms vs training 2h per RL iteration — inference vs training, different systems
    138: "UNRELATED",
    # 139: TTS inference 35ms on A100 vs code change inference 12ms on V100 — different systems
    139: "UNRELATED",
    # 140: skill utility independent of model scale vs skills transfer across model scales — both about skills and model scale. A says utility is scale-independent, B says skills transfer across scales. These actually agree (both say scale doesn't matter for skills).
    140: "SUPPORTS",
    # 141: CoT improves on arithmetic/commonsense/symbolic vs L2M beats CoT at math — same as pair 0/96 area. CoT improves ≠ CoT is best. Not directly contradictory here since A says "improves" and B says L2M is better. But A includes "arithmetic" (≈math). Not a strict contradiction since both could be true (CoT improves over baseline, L2M improves over CoT).
    141: "UNRELATED",
    # 142: CoT improves on symbolic reasoning vs L2M surpasses CoT on symbolic manipulation — same specific topic (symbolic reasoning). A says CoT helps, B says L2M beats CoT. Tension but both can be true (CoT helps, L2M helps more). Not a direct contradiction.
    142: "UNRELATED",
    # 143: CoT beats standard prompting on arithmetic vs L2M surpasses both standard and CoT — both can be true simultaneously. L2M > CoT > standard. Not contradictory.
    143: "UNRELATED",
    # 144: PaLM standard prompting worse on GSM8K vs proposed method SOTA on GSM8K — different methods (standard prompting vs "proposed method"). Compatible: standard is worse, proposed is better.
    144: "UNRELATED",
    # 145: finetuned GPT-3 worse than PaLM CoT on GSM8K vs proposed method SOTA on GSM8K — different methods. Not contradictory.
    145: "UNRELATED",
    # 146: few-shot prompting doesn't improve with scale vs L2M enables efficient learning — different methods
    146: "UNRELATED",
    # 147: 85.2% on WebQA with CoT vs L2M beats CoT by 13.4% on Non-football — different benchmarks
    147: "UNRELATED",
    # 148: +25% on CIRCA vs +12.5% F1 on Science domain — different benchmarks, different systems
    148: "UNRELATED",
    # 149: CoT −40% compute overhead vs L2M outperforms CoT on symbolic manipulation — different aspects (compute vs accuracy)
    149: "UNRELATED",
    # 150: OPT-175B comparable to GPT-3 vs GPT-3 struggles on >3 digit addition — A makes general capability claim, B makes specific weakness claim. Not contradictory (something can be comparable and still struggle).
    150: "UNRELATED",
    # 151: method improves 74.4→82.1% on GSM8K vs finetuned GPT-3 worse than PaLM CoT on GSM8K — different methods being discussed
    151: "UNRELATED",
    # 152: 100M transformer +2.5% on GLUE vs larger Transformer (128M) outperforms smaller (16M) by 12% — different experimental setups (augmentation technique vs scaling comparison)
    152: "UNRELATED",
    # 153: 100M transformer +2.5% on GLUE vs Transformer −25% accuracy on algorithmic reasoning vs RNN — different tasks (GLUE NLU vs algorithmic reasoning)
    153: "UNRELATED",
    # 154: adversarial training −12.2% error on CIFAR-10 vs neural nets 40% error on code semantics — different tasks entirely
    154: "UNRELATED",
    # 155: data pruning −20% model size on SQuAD vs scratchpad pruning −30% model size with 2.1% compute reduction — different methods, but both about model compression. Not same system.
    155: "UNRELATED",
    # 156: data pruning −20% model size on SQuAD vs calibration improves with model size — different topics (pruning vs calibration scaling)
    156: "UNRELATED",
    # 157: Transformer −25% accuracy on algorithmic reasoning vs RNN vs fine-tuned 3B LLM +10% reasoning — different comparisons (Transformer vs RNN on algorithms vs fine-tuned LLM reasoning)
    157: "UNRELATED",
    # 158: neural net traces 24.6% of tasks perfectly vs neural-symbolic models need >15K examples for SCAN — different topics
    158: "UNRELATED",
    # 159: GPT-4/Codex Faithful CoT SOTA on 7 datasets vs GPT-3 lower on symbolic reasoning — different models (GPT-4 vs GPT-3), different claims
    159: "UNRELATED",
    # 160: −35.7% latency reduction vs L2M requires 2.5x fewer queries on NQ — different systems, different metrics
    160: "UNRELATED",
    # 161: L2M beats CoT by 13.4% on Non-football vs CoT can achieve SOTA on certain benchmarks — both can be true (CoT achieves SOTA on some, L2M beats it on others)
    161: "UNRELATED",
    # 162: L2M requires 2.5x fewer queries on NQ vs CoT achieves SOTA on some benchmarks — different aspects
    162: "UNRELATED",
    # 163: calibration improves with few-shot prompting vs few-shot doesn't improve with scale — A is about calibration improving with few-shot (vs zero-shot), B is about few-shot not improving with model scale. Different dimensions (few-shot vs zero-shot, vs scaling). Not contradictory.
    163: "UNRELATED",
    # 164: correlation 0.7 (iterations vs perplexity) vs SkillOpt needs only 10 iterations for stable training — different systems
    164: "UNRELATED",
    # 165: model response 150ms vs scaling >2B params adds 2% latency — different contexts
    165: "UNRELATED",
    # 166: OPT 125M-175B vs models 1M-10M don't outperform 100k on ImageNet — different model families, different benchmarks
    166: "UNRELATED",
    # 167: improves general reasoning of 540B LLM vs LLMs need ≥500M for optimal F1 — A uses 540B (which is ≥500M), so not contradictory
    167: "UNRELATED",
    # 168: 128M Transformer outperforms 16M by 12% vs 1M-10M don't outperform 100k on ImageNet — different tasks and model ranges. B specifically about ImageNet, A about unspecified task. Could indicate contradiction on scaling if same context, but different benchmarks.
    168: "UNRELATED",
    # 169: standard GNNs fail on programs with loops (70%+ error) vs model-generated skills fail on ≥2 tasks — different systems, different topics
    169: "UNRELATED",
    # 170: −35.7% latency vs 10x larger VLM +40ms latency — different systems
    170: "UNRELATED",
    # 171: +7 reasoning steps → +18.2% F1 on MultiNLI vs framework +10% F1 on test set — different systems, different benchmarks
    171: "UNRELATED",
    # 172: calibration improves with model size vs −25% model size without performance loss — different topics (calibration scaling vs model compression)
    172: "UNRELATED",
    # 173: skill document −20% manual rewriting vs skill extraction takes 60% of total time — different aspects of skill pipeline
    173: "UNRELATED",
    # 174: law prediction accuracy 0.847 vs GPT-5.4 judge accuracy 46.4% — different tasks (scaling law prediction vs LLM selection)
    174: "UNRELATED",
    # 175: ~10M param models vs SkillOpt smaller than 5.4B GPT by ≥1.8B — different systems
    175: "UNRELATED",
    # 176: diffusion model −30% compute vs PiD terminates latent diffusion early — different systems. Not directly comparable.
    176: "UNRELATED",
    # 177: −14.5% params for EMA vs 34M params with 25.8% capacity increase — different systems
    177: "UNRELATED",
    # 178: TTS inference 35ms on A100 vs training 2h per RL iteration on A800s — inference vs training
    178: "UNRELATED",
    # 179: TTS inference 35ms vs LaMo inference 12.7ms — different systems (TTS vs video)
    179: "UNRELATED",
    # 180: OPT-175B 1/7th carbon of GPT-3 vs −75.2% carbon when scaling 100→1000 nodes — different contexts (model development vs node scaling)
    180: "UNRELATED",
    # 181: −23.1% worst-case coverage after 100 epochs vs +15% absolute accuracy improvement on perplexity — different metrics, different models
    181: "UNRELATED",
    # 182: 540B LLM self-training +1.1-7.7% on 6 datasets vs LLMs need ≥500M params — A uses 540B (which satisfies B's requirement). Not contradictory.
    182: "UNRELATED",
    # 183: early stopping −30% training time on WMT vs doubling params 512M→4G doubles convergence steps on WikiText103 — different topics (early stopping vs scaling convergence)
    183: "UNRELATED",
    # 184: F1 85.5 on IMDB with 250M params vs F1 92.1 on Mobile GUI with 2048 params — different benchmarks, different model sizes
    184: "UNRELATED",
    # 185: adversarial training −12.2% error on CIFAR-10 vs robustness +4.5% with scaling law on adversarial attacks — both about adversarial robustness. Different methods, different benchmarks.
    185: "UNRELATED",
    # 186: BERT-large −40% memory bandwidth vs method −8% peak memory of LM inference — different models, different measurements
    186: "UNRELATED",
    # 187: greedy decoding correct trace 42% vs models ≤30% on spatial numerical — different tasks (program tracing vs spatial understanding)
    187: "UNRELATED",
    # 188: −35.7% latency reduction vs scaling >2B → +2% latency — different systems (latency reduction method vs scaling analysis)
    188: "UNRELATED",
    # 189: Faithful CoT achieves SOTA on complex reasoning vs more recursions/sleep improves performance — both say improvements are possible. Not contradictory.
    189: "UNRELATED",
    # 190: models struggle with P(IK) calibration on new tasks vs model-generated skills fail on ≥2 tasks — different types of failure, different systems
    190: "UNRELATED",
    # 191: compact skills transfer across scales vs skill utility is scale-independent but task-dependent — both about skills and scale. A says skills transfer, B says utility is scale-independent. These agree.
    191: "SUPPORTS",
    # 192: SkillOpt training ≤30min in 80% of cases vs model training 3h45m on single CPU — different systems, different hardware
    192: "UNRELATED",
    # 193: −30% compute vs traditional scaling vs larger model improves performance — different topics (compute reduction vs scaling benefits)
    193: "UNRELATED",
    # 194: framework scales to 3.2B without training time increase vs system scaling −30% training time for 1.1B — different frameworks, but both about efficient scaling. Not contradictory.
    194: "UNRELATED",
    # 195: scaling >2B → +2% latency vs 8.4x latency reduction with 32-layer vs 16-layer Transformer — A says more params increases latency, B says a deeper model reduces it. These are about different dimensions (parameter count vs layer architecture) and possibly different optimizations.
    195: "UNRELATED",
    # 196: LaMo 512M, 128 GPU-hours vs 34M params with 25.8% capacity increase — different systems
    196: "UNRELATED",
    # 197: +20M params → 10% quality degradation vs scaling beyond threshold degrades — same phenomenon (scaling degradation), different papers. Agree.
    197: "SUPPORTS",
    # 198: 140 RL iterations with constant lr 1e-4 vs frontier optimizer 500/200 iterations — different systems (same as 130/132)
    198: "UNRELATED",
    # 199: −43.1% scale drift vs LaMo −3.1% macro motion drift loss — different metrics, different systems, different magnitudes
    199: "UNRELATED",
    # 200: −3.5B params via efficient fine-tuning vs scaling beyond threshold degrades fine-tuning — A does parameter-efficient fine-tuning, B warns about scaling. Not directly contradictory (one reduces params, other warns about adding too many).
    200: "UNRELATED",
    # 201: post-training 130h on 64 A800s vs training on 8 H100s with lr 1e-5 — different systems
    201: "UNRELATED",
    # 202: Geo-Align FID 34.1 on NYU Depth vs PiD FID 12.45 on validation set — different systems, different datasets. PiD gets much lower (better) FID.
    202: "UNRELATED",
    # 203: traditional VAE decoders amplify artifacts vs VAE detail capture improved with framework — both about VAEs. A says VAEs have artifact problems, B says a specific framework improves VAEs. Not contradictory (B is a solution to A's problem).
    203: "UNRELATED",
    # 204: PiD 13GB peak memory on RTX 5090 vs Geo-Align 2.1GB on 8-GPU cluster — different systems, different GPUs
    204: "UNRELATED",
    # 205: image quality preferred 62.1% vs PSNR +12% with real+synthetic fusion — different metrics, different systems
    205: "UNRELATED",
    # 206: effects held across multiple ablations vs ablation of interpretive update demonstrates necessity — different experiments, different systems
    206: "UNRELATED",
    # 207: model-generated skills +20% across 5 domains vs SkillOpt +25% task-specific improvement — both about skills improving performance. Different systems but same direction.
    207: "SUPPORTS",
    # 208: meta-skill prior outperforms baselines in all cells vs SkillOpt best/tied on 52/52 cells — both claim comprehensive superiority. Could be same or related system. Same direction.
    208: "SUPPORTS",
    # 209: GPT-5.4 judge 46.4% (random) vs SkillOpt scores 72.1%/62.8% on OfficeQA for GPT-5.5/5.4 — A is about judging/selection accuracy, B is about task performance with skills. Different tasks.
    209: "UNRELATED",
    # 210: GPT-5.4 judge 46.4% (random) vs SkillOpt outperforms LLM skill baselines by ≥10.2% on CodeQA — A about judge accuracy, B about task performance. Different.
    210: "UNRELATED",
    # 211: Friedman test shows format effect non-significant vs model yields enhancements across all metrics in Table 1 — different tests, different contexts
    211: "UNRELATED",
    # 212: data aug +2.5% on GLUE vs −30% data augmentation needed — different perspectives but not contradictory (one says aug helps, other says less is needed). Different systems.
    212: "UNRELATED",
    # 213: −31.4% compute cost vs −25% model size (Shannon) — different approaches, different things (compute vs model size)
    213: "UNRELATED",
    # 214: LLMs fail at Python code execution (≤30%) vs LMs produce well-calibrated token probabilities on-distribution — different tasks (code execution vs token probability calibration)
    214: "UNRELATED",
    # 215: CoT struggles on harder symbolic problems vs CoT improves on symbolic reasoning — SAME TOPIC (CoT on symbolic reasoning). A says it struggles on harder problems, B says it improves performance. Genuine tension: A qualifies that CoT fails beyond exemplar difficulty, B says CoT helps. Real contradiction.
    215: "CONTRADICTS",
    # 216: scaling >2B → +2% latency vs 10x larger VLM → +40ms latency — both about scaling increasing latency. Different models, different magnitudes, but same direction. Supports.
    216: "SUPPORTS",
    # 217: best hyperparams lr 0.002, batch 64 vs larger batch 128 reduces training time 42.9% — different systems
    217: "UNRELATED",
    # 218: perplexity 15.2→12.9 over 50 iterations vs Looped Diffusion perplexity 20.5 after 50 epochs on WikiText103 — different models, different datasets (unspecified vs WikiText-103). Not same experiment.
    218: "UNRELATED",
    # 219: −21.1% params vs scratchpad pruning −30% model size — different methods
    219: "UNRELATED",
    # 220: 100M transformer +2.5% on GLUE vs scaling 220M→440M +15% on GLUE — same benchmark (GLUE). A uses data augmentation on fixed-size model, B scales model size. Different approaches. Both show improvement on GLUE but via different means. Not contradictory.
    220: "UNRELATED",
    # 221: scaling law +5% F1 vs PRISM +20% F1 — different systems
    221: "UNRELATED",
    # 222: 540B LLM self-training +1.1-7.7% vs LLMs need ≥500M params — not contradictory
    222: "UNRELATED",
    # 223: early stopping −30% training time on WMT vs PRISM −12% training time over 50 epochs — different systems, different benchmarks
    223: "UNRELATED",
}

# Read CSV
in_path = "eval/Data/contradicts_review.csv"
rows = []
with open(in_path, "r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        pid = int(row["pair_id"])
        row["human_label"] = labels.get(pid, "")
        rows.append(row)

# Write to temp then replace
import os
tmp_path = in_path + ".tmp"
with open(tmp_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

try:
    os.replace(tmp_path, in_path)
except PermissionError:
    print(f"WARNING: Could not replace {in_path} (file may be locked). Labeled file saved as {tmp_path}")


# Stats
from collections import Counter
counts = Counter(labels.values())
print("Label distribution:")
for label in ("CONTRADICTS", "SUPPORTS", "UNRELATED"):
    print(f"  {label}: {counts.get(label, 0)}")
print(f"  Total labeled: {sum(counts.values())}")
