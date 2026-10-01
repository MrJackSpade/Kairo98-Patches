# DeepSeek expert-cache benchmark

One completed generation per build in each comparison, run back to back on 2026-09-27 with the same English prompt in `english-prompt.txt` and the same DeepSeek-V4-Flash-0731 UD-Q3_K_M GGUF (119.3 GiB across four shards). Hardware: one RTX 3090 24 GiB and 128 GiB system RAM. Each generation was capped at 256 tokens with a fixed seed and greedy sampling.

## Corrected comparison: standard translation placement and full context

| Build | Placement | Context | Generation tokens/s |
|---|---|---:|---:|
| Bundled llama.cpp b11205 / `95887577a` | Pipeline fitter: 44 GPU layers, 39 CPU tensor overrides | 262,144 | 3.7 |
| `memoriaru/llama.cpp` `555d1ec`, with CPU-KV budget correction | 44 GPU layers, all MoE experts on CPU, 28 cache slots per expert tensor | 262,144 | 4.0 |

The cache configuration was **1.08x faster (+8%)** in this single run. The standard placement used about 22.2 GiB of VRAM, the cache placement about 22.5 GiB. The standard fitter had too little free VRAM to add a useful cache without moving some static GPU experts to CPU, so the cache arm reallocates VRAM from permanently resident experts to cache slots. This changes placement while keeping the model and its expert routing unchanged. The two builds also differ in llama.cpp revision, so the measured change cannot be attributed solely to caching.

During the cache run, a spot check showed 35.7 GiB of physical RAM and 79.7 GiB of commit headroom free. This is not a peak-memory measurement and does not establish headroom for a full translation.

The cache branch's VRAM budget counted the full-context KV allocation as GPU memory even with `-nkvo` (KV in system RAM). The local source change in `cpu-kv-budget.patch` skips that GPU reservation when KV offload is disabled. This makes the cache setting usable at the pipeline's 262,144-token context. It does not reserve system RAM for KV.

Both arms used `-f .benchmark/english-prompt.txt -n 256 -st -c 262144 -ngl 44 -ctk q8_0 -ctv q8_0 -nkvo -fa on -b 2048 -ub 512 -t 4 -tb 4 --temp 0 -s 42 --ignore-eos --simple-io --no-display-prompt`. The baseline added the exact `-ot` tensor patterns in `standard-placement.json`; the cache arm added `-cmoe -mec 28`. The command is reproducible with `standard-pair.py`. Timing logs are `standard-current.log` and `standard-cache.log`.

## Earlier exploratory comparison

At 8K context with **all** experts on CPU in both arms, the bundled build reached 3.4 tokens/s and the unmodified cache branch with 16 slots reached 4.8 tokens/s (+41%). This isolated the cache under a different placement, but did not represent the translation pipeline's fitted placement. Logs are `current.log` and `cache.log`. The corrected comparison above supersedes it for this project's current setup.
