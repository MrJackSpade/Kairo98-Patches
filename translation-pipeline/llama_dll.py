"""ctypes binding for the exact llama.cpp b11205 Windows DLL used by this pipeline."""
import ctypes as C
import mmap
import os
from pathlib import Path
import sys
import tempfile


class ModelParams(C.Structure):
    _fields_ = [
        ("devices", C.c_void_p), ("tensor_buft_overrides", C.c_void_p),
        ("n_gpu_layers", C.c_int32), ("split_mode", C.c_int32),
        ("load_mode", C.c_int32), ("lazy_mode", C.c_int32),
        ("main_gpu", C.c_int32), ("tensor_split", C.c_void_p),
        ("progress_callback", C.c_void_p), ("progress_callback_user_data", C.c_void_p),
        ("kv_overrides", C.c_void_p), ("vocab_only", C.c_bool),
        ("check_tensors", C.c_bool), ("use_extra_bufts", C.c_bool),
        ("no_host", C.c_bool), ("no_alloc", C.c_bool), ("load_mtp", C.c_bool),
    ]


class ContextParams(C.Structure):
    _fields_ = [
        ("n_ctx", C.c_uint32), ("n_batch", C.c_uint32), ("n_ubatch", C.c_uint32),
        ("n_seq_max", C.c_uint32), ("n_rs_seq", C.c_uint32),
        ("n_outputs_max", C.c_uint32), ("n_outputs_max_per_seq", C.c_uint32),
        ("n_threads", C.c_int32), ("n_threads_batch", C.c_int32),
        ("ctx_type", C.c_int32), ("rope_scaling_type", C.c_int32),
        ("pooling_type", C.c_int32), ("attention_type", C.c_int32),
        ("flash_attn_type", C.c_int32),
        ("rope_freq_base", C.c_float), ("rope_freq_scale", C.c_float),
        ("yarn_ext_factor", C.c_float), ("yarn_attn_factor", C.c_float),
        ("yarn_beta_fast", C.c_float), ("yarn_beta_slow", C.c_float),
        ("yarn_orig_ctx", C.c_uint32), ("defrag_thold", C.c_float),
        ("cb_eval", C.c_void_p), ("cb_eval_user_data", C.c_void_p),
        ("type_k", C.c_int32), ("type_v", C.c_int32),
        ("abort_callback", C.c_void_p), ("abort_callback_data", C.c_void_p),
        ("embeddings", C.c_bool), ("offload_kqv", C.c_bool),
        ("no_perf", C.c_bool), ("op_offload", C.c_bool),
        ("swa_full", C.c_bool), ("kv_unified", C.c_bool),
        ("samplers", C.c_void_p), ("n_samplers", C.c_size_t),
        ("ctx_other", C.c_void_p),
    ]


class Batch(C.Structure):
    _fields_ = [
        ("n_tokens", C.c_int32), ("token", C.POINTER(C.c_int32)),
        ("embd", C.POINTER(C.c_float)), ("pos", C.POINTER(C.c_int32)),
        ("n_seq_id", C.POINTER(C.c_int32)), ("seq_id", C.c_void_p),
        ("logits", C.POINTER(C.c_int8)),
    ]


class ChainParams(C.Structure):
    _fields_ = [("no_perf", C.c_bool)]


class ChatMessage(C.Structure):
    _fields_ = [("role", C.c_char_p), ("content", C.c_char_p)]


class TensorBuftOverride(C.Structure):
    _fields_ = [("pattern", C.c_char_p), ("buft", C.c_void_p)]


def bind(dll, name, restype, *argtypes):
    fn = getattr(dll, name)
    fn.restype = restype
    fn.argtypes = argtypes
    return fn


class DiskSnapshot:
    """One file-backed sequence state, removed when closed."""

    def __init__(self, file, mapping, size, token_count):
        self.file = file
        self.mapping = mapping
        self.size = size
        self.token_count = token_count

    def close(self):
        if self.mapping is not None:
            self.mapping.close()
            self.mapping = None
        if self.file is not None:
            self.file.close()
            self.file = None

    def __del__(self):
        self.close()


class DirectLlama:
    def __init__(self, model_path, context_tokens=16384, kv_on_gpu=True, gpu_layers=99,
                 cpu_tensor_patterns=(), progress=None, threads=None,
                 interrupt_requested=None):
        self.model_path = Path(model_path)
        self.interrupt_requested = interrupt_requested
        runtime = Path(__file__).resolve().parent / "runtime" / "llama"
        if progress:
            progress.start("loading llama.cpp and CUDA libraries")
        self._dll_dir = os.add_dll_directory(str(runtime))
        # Windows' backend loader needs CUDA and its dependencies resident first.
        self.cuda = C.CDLL(str(runtime / "ggml-cuda.dll"))
        self.ggml = C.CDLL(str(runtime / "ggml.dll"))
        self.ggml_base = C.CDLL(str(runtime / "ggml-base.dll"))
        self.lib = C.CDLL(str(runtime / "llama.dll"))
        self._bind()
        LOG_CALLBACK = C.CFUNCTYPE(None, C.c_int, C.c_char_p, C.c_void_p)
        def log_errors(level, message, _):
            if level == 4:
                sys.stderr.write(message.decode("utf-8", errors="replace"))
        self._log_callback = LOG_CALLBACK(log_errors)
        self.llama_log_set(self._log_callback, None)
        if progress:
            progress.finish()
            progress.start("initializing llama.cpp backends")
        self.ggml_backend_load_all_from_path(os.fsencode(str(runtime)))
        self.llama_backend_init()
        params = self.llama_model_default_params()
        params.n_gpu_layers = gpu_layers
        if interrupt_requested:
            LOAD_PROGRESS = C.CFUNCTYPE(C.c_bool, C.c_float, C.c_void_p)
            self._load_progress_callback = LOAD_PROGRESS(
                lambda _fraction, _data: not interrupt_requested())
            params.progress_callback = C.cast(self._load_progress_callback, C.c_void_p).value
        if cpu_tensor_patterns:
            cpu_buft = self.ggml_backend_cpu_buffer_type()
            if not cpu_buft:
                raise RuntimeError("llama.cpp has no CPU tensor buffer")
            self._pattern_bytes = [pattern.encode("utf-8") for pattern in cpu_tensor_patterns]
            overrides = (TensorBuftOverride * (len(self._pattern_bytes) + 1))()
            for index, pattern in enumerate(self._pattern_bytes):
                overrides[index] = TensorBuftOverride(pattern, cpu_buft)
            self._tensor_overrides = overrides
            params.tensor_buft_overrides = C.cast(overrides, C.c_void_p).value
        if progress:
            progress.finish()
            progress.start("loading model weights into RAM/VRAM")
        self.model = self.llama_model_load_from_file(os.fsencode(str(model_path)), params)
        if interrupt_requested and interrupt_requested():
            self.close()
            raise KeyboardInterrupt
        if not self.model:
            raise RuntimeError("llama.dll could not load model")
        if progress:
            progress.finish()
            progress.start(f"allocating {context_tokens:,}-token context and KV cache")
        cparams = self.llama_context_default_params()
        cparams.n_ctx = context_tokens
        cparams.n_batch = 2048
        cparams.n_ubatch = 512
        if threads is not None:
            cparams.n_threads = threads
        self.threads = cparams.n_threads
        self.batch_threads = cparams.n_threads_batch
        cparams.flash_attn_type = 1
        cparams.type_k = 8  # GGML_TYPE_Q8_0
        cparams.type_v = 8
        cparams.offload_kqv = kv_on_gpu
        self.ctx = self.llama_init_from_model(self.model, cparams)
        if interrupt_requested and interrupt_requested():
            self.close()
            raise KeyboardInterrupt
        if not self.ctx:
            self.llama_model_free(self.model)
            raise RuntimeError("llama.dll could not initialize context")
        self.vocab = self.llama_model_get_vocab(self.model)
        self.context_tokens = context_tokens
        self.tokens_used = 0

    def _check_interrupt(self):
        if self.interrupt_requested and self.interrupt_requested():
            raise KeyboardInterrupt

    def _bind(self):
        lib = self.lib
        self.ggml_backend_cpu_buffer_type = bind(self.ggml_base, "ggml_backend_cpu_buffer_type", C.c_void_p)
        self.llama_log_set = bind(lib, "llama_log_set", None, C.c_void_p, C.c_void_p)
        self.ggml_backend_load_all_from_path = bind(self.ggml, "ggml_backend_load_all_from_path", None, C.c_char_p)
        self.llama_backend_init = bind(lib, "llama_backend_init", None)
        self.llama_model_default_params = bind(lib, "llama_model_default_params", ModelParams)
        self.llama_context_default_params = bind(lib, "llama_context_default_params", ContextParams)
        self.llama_model_load_from_file = bind(lib, "llama_model_load_from_file", C.c_void_p, C.c_char_p, ModelParams)
        self.llama_model_free = bind(lib, "llama_model_free", None, C.c_void_p)
        self.llama_init_from_model = bind(lib, "llama_init_from_model", C.c_void_p, C.c_void_p, ContextParams)
        self.llama_free = bind(lib, "llama_free", None, C.c_void_p)
        self.llama_model_get_vocab = bind(lib, "llama_model_get_vocab", C.c_void_p, C.c_void_p)
        self.llama_model_chat_template = bind(lib, "llama_model_chat_template", C.c_char_p, C.c_void_p, C.c_char_p)
        self.llama_chat_apply_template = bind(lib, "llama_chat_apply_template", C.c_int32, C.c_char_p,
                                              C.POINTER(ChatMessage), C.c_size_t, C.c_bool, C.c_void_p, C.c_int32)
        self.llama_tokenize = bind(lib, "llama_tokenize", C.c_int32, C.c_void_p, C.c_char_p,
                                   C.c_int32, C.POINTER(C.c_int32), C.c_int32, C.c_bool, C.c_bool)
        self.llama_token_to_piece = bind(lib, "llama_token_to_piece", C.c_int32, C.c_void_p, C.c_int32,
                                         C.c_void_p, C.c_int32, C.c_int32, C.c_bool)
        self.llama_batch_get_one = bind(lib, "llama_batch_get_one", Batch, C.POINTER(C.c_int32), C.c_int32)
        self.llama_decode = bind(lib, "llama_decode", C.c_int32, C.c_void_p, Batch)
        self.llama_get_memory = bind(lib, "llama_get_memory", C.c_void_p, C.c_void_p)
        self.llama_memory_clear = bind(lib, "llama_memory_clear", None, C.c_void_p, C.c_bool)
        self.llama_memory_seq_rm = bind(lib, "llama_memory_seq_rm", C.c_bool,
                                        C.c_void_p, C.c_int32, C.c_int32, C.c_int32)
        self.llama_state_seq_get_size = bind(lib, "llama_state_seq_get_size", C.c_size_t,
                                              C.c_void_p, C.c_int32)
        self.llama_state_seq_get_data = bind(lib, "llama_state_seq_get_data", C.c_size_t,
                                              C.c_void_p, C.c_void_p, C.c_size_t, C.c_int32)
        self.llama_state_seq_set_data = bind(lib, "llama_state_seq_set_data", C.c_size_t,
                                              C.c_void_p, C.c_void_p, C.c_size_t, C.c_int32)
        self.llama_sampler_chain_default_params = bind(lib, "llama_sampler_chain_default_params", ChainParams)
        self.llama_sampler_chain_init = bind(lib, "llama_sampler_chain_init", C.c_void_p, ChainParams)
        self.llama_sampler_chain_add = bind(lib, "llama_sampler_chain_add", None, C.c_void_p, C.c_void_p)
        self.llama_sampler_init_grammar = bind(lib, "llama_sampler_init_grammar", C.c_void_p,
                                               C.c_void_p, C.c_char_p, C.c_char_p)
        self.llama_sampler_init_greedy = bind(lib, "llama_sampler_init_greedy", C.c_void_p)
        self.llama_sampler_sample = bind(lib, "llama_sampler_sample", C.c_int32, C.c_void_p, C.c_void_p, C.c_int32)
        self.llama_sampler_free = bind(lib, "llama_sampler_free", None, C.c_void_p)
        self.llama_vocab_is_eog = bind(lib, "llama_vocab_is_eog", C.c_bool, C.c_void_p, C.c_int32)

    def close(self):
        if getattr(self, "ctx", None):
            self.llama_free(self.ctx)
            self.ctx = None
        if getattr(self, "model", None):
            self.llama_model_free(self.model)
            self.model = None

    def reset(self):
        self.llama_memory_clear(self.llama_get_memory(self.ctx), True)
        self._check_interrupt()
        self.tokens_used = 0

    def rewind(self, token_count):
        if not self.llama_memory_seq_rm(self.llama_get_memory(self.ctx), 0, token_count, -1):
            raise RuntimeError("llama.cpp cannot rewind this model's partial sequence")
        self.tokens_used = token_count

    def snapshot(self):
        size = self.llama_state_seq_get_size(self.ctx, 0)
        buffer = C.create_string_buffer(size)
        copied = self.llama_state_seq_get_data(self.ctx, buffer, size, 0)
        if copied == 0:
            raise RuntimeError("llama.cpp could not snapshot the prefix")
        return buffer, copied, self.tokens_used

    def snapshot_to_disk(self, directory, max_bytes):
        size = self.llama_state_seq_get_size(self.ctx, 0)
        if not 0 < size <= max_bytes:
            raise ValueError(f"cache state needs {size / 1073741824:.1f} GiB; "
                             f"disk checkpoint limit is {max_bytes / 1073741824:.1f} GiB")
        file = tempfile.TemporaryFile(dir=directory)
        mapping = None
        try:
            file.truncate(size)
            mapping = mmap.mmap(file.fileno(), size, access=mmap.ACCESS_WRITE)
            first_byte = C.c_char.from_buffer(mapping)
            try:
                copied = self.llama_state_seq_get_data(self.ctx, C.byref(first_byte), size, 0)
            finally:
                del first_byte
            if copied == 0:
                raise RuntimeError("llama.cpp could not save the cache state")
            mapping.flush()
            return DiskSnapshot(file, mapping, copied, self.tokens_used)
        except BaseException:
            if mapping is not None:
                mapping.close()
            file.close()
            raise

    def restore(self, snapshot):
        if isinstance(snapshot, DiskSnapshot):
            self.reset()
            first_byte = C.c_char.from_buffer(snapshot.mapping)
            try:
                restored = self.llama_state_seq_set_data(
                    self.ctx, C.byref(first_byte), snapshot.size, 0)
            finally:
                del first_byte
            if not restored:
                raise RuntimeError("llama.cpp could not restore the disk cache state")
            self.tokens_used = snapshot.token_count
            return
        buffer, size, token_count = snapshot
        self.reset()
        if not self.llama_state_seq_set_data(self.ctx, buffer, size, 0):
            raise RuntimeError("llama.cpp could not restore the prefix")
        self.tokens_used = token_count

    def tokenize(self, text, add_special=False):
        raw = text.encode("utf-8")
        size = max(32, len(raw) + 8)
        tokens = (C.c_int32 * size)()
        count = self.llama_tokenize(self.vocab, raw, len(raw), tokens, size, add_special, True)
        self._check_interrupt()
        if count < 0:
            size = -count
            tokens = (C.c_int32 * size)()
            count = self.llama_tokenize(self.vocab, raw, len(raw), tokens, size, add_special, True)
            self._check_interrupt()
        if count < 0:
            raise RuntimeError("llama_tokenize failed")
        return list(tokens[:count])

    def decode_tokens(self, tokens, on_progress=None):
        for offset in range(0, len(tokens), 512):
            part = tokens[offset:offset + 512]
            if self.tokens_used + len(part) > self.context_tokens:
                raise ValueError("llama context is full")
            arr = (C.c_int32 * len(part))(*part)
            result = self.llama_decode(self.ctx, self.llama_batch_get_one(arr, len(part)))
            self._check_interrupt()
            if result != 0:
                raise RuntimeError(f"llama_decode failed with code {result}")
            self.tokens_used += len(part)
            if on_progress:
                on_progress(offset + len(part), len(tokens))

    def prefill(self, text, initial=False, on_progress=None):
        tokens = self.tokenize(text, add_special=initial)
        if on_progress:
            on_progress(0, len(tokens))
        self.decode_tokens(tokens, on_progress=on_progress)
        return len(tokens)

    def token_piece(self, token):
        buf = C.create_string_buffer(8192)
        count = self.llama_token_to_piece(self.vocab, token, buf, len(buf), 0, False)
        if count < 0:
            raise RuntimeError("llama_token_to_piece failed")
        return buf.raw[:count]

    def chat_prompt(self, system, user):
        if "deepseek-v4" in str(self.model_path).lower():
            # DeepSeek V4's official chat-mode encoding has no Jinja template.
            return ("<｜begin▁of▁sentence｜>" + system +
                    "<｜User｜>" + user + "<｜Assistant｜></think>")
        if "gemma-4" in str(self.model_path).lower():
            # The bundled C chat formatter cannot evaluate Gemma 4's Jinja
            # template. This is its two-message, thinking-disabled text form.
            return ("<|turn>system\n" + system + "<turn|>\n"
                    "<|turn>user\n" + user + "<turn|>\n"
                    "<|turn>model\n<|channel>thought\n<channel|>")
        template = self.llama_model_chat_template(self.model, None)
        if not template:
            raise RuntimeError("model has no chat template")
        messages = (ChatMessage * 2)(ChatMessage(b"system", system.encode("utf-8")),
                                     ChatMessage(b"user", user.encode("utf-8")))
        needed = self.llama_chat_apply_template(template, messages, 2, True, None, 0)
        if needed <= 0:
            raise RuntimeError("llama.dll cannot apply this model's chat template")
        buf = C.create_string_buffer(needed + 1)
        count = self.llama_chat_apply_template(template, messages, 2, True, buf, len(buf))
        if count <= 0:
            raise RuntimeError("llama.dll chat template failed")
        rendered = buf.raw[:count].decode("utf-8")
        # llama_chat_apply_template does not expose the Qwen Jinja
        # enable_thinking=false option. Close its default thinking block
        # before prefilling the constrained JSON answer.
        if "qwen" in str(self.model_path).lower():
            rendered += "<think>\n</think>\n\n"
        return rendered

    def sample_json_string(self, grammar, max_tokens=3000, on_piece=None, on_token=None):
        chain = self.llama_sampler_chain_init(self.llama_sampler_chain_default_params())
        grammar_sampler = self.llama_sampler_init_grammar(self.vocab, grammar.encode("utf-8"), b"root")
        if not grammar_sampler:
            self.llama_sampler_free(chain)
            raise RuntimeError("llama.dll rejected JSON string grammar")
        self.llama_sampler_chain_add(chain, grammar_sampler)
        self.llama_sampler_chain_add(chain, self.llama_sampler_init_greedy())
        pieces = []
        escaped = False
        try:
            for index in range(max_tokens):
                token = self.llama_sampler_sample(chain, self.ctx, -1)
                self._check_interrupt()
                if self.llama_vocab_is_eog(self.vocab, token):
                    raise ValueError("model stopped before closing the English JSON string")
                piece = self.token_piece(token)
                pieces.append(piece)
                self.decode_tokens([token])
                if on_token:
                    on_token(index + 1)
                data = b"".join(pieces)
                start = len(data) - len(piece)
                for offset, char in enumerate(piece):
                    if escaped:
                        escaped = False
                    elif char == 92:
                        escaped = True
                    elif char == 34:
                        if on_piece:
                            on_piece(piece[:offset])
                        position = start + offset
                        return '"' + data[:position + 1].decode("utf-8"), data[position + 1:]
                if on_piece:
                    on_piece(piece)
            preview = b"".join(pieces).decode("utf-8", errors="replace")
            raise ValueError(f"English field reached max_tokens without a closing quote: {preview[:400]!r}")
        finally:
            self.llama_sampler_free(chain)
