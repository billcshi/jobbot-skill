# Model-provider and host compatibility

JobBot's workflow, prompts, JSON records, rendering, and validation are portable across Claude/Anthropic, OpenAI, DeepSeek, and other capable models. No provider SDK or fixed model endpoint is required by the core. This is a compatibility contract, not a claim that bundled clients have connected every provider.

## Keep three layers separate

1. **Skill contract:** tasks, facts, artifacts, scores, feedback, schemas, hashes, budgets, and independent review. These are provider-neutral local files.
2. **Host execution:** actual sub-agents, isolated sessions, file/vision/browser tools, runtime model selection, identities, concurrency and usage receipts.
3. **Model/provider:** the selected model's modalities, context/output limits, structured-output behavior, effort controls, availability and cost.

A provider name does not establish host multi-agent support, and an API shape that resembles another provider's does not establish identical capabilities. Do not assume a DeepSeek or Claude model is available in a particular OpenAI host, or switch providers merely because compatible settings exist.

## Capability-based routing

Before a batch or document loop, inspect available host tools and the relevant model/account capabilities. Optionally record observations under `runtime/<session-id>/capabilities.json`, with observation time, source, host, actual model IDs/routes, modality limits, and unknown fields. This is an agent-maintained diagnostic snapshot, not an automatic detector. Refresh it when model/host configuration changes; unknown capability is not support.

| Task | Required capability | Portable route |
| --- | --- | --- |
| Main writing and rewriting | Strong text reasoning, access to confirmed facts | User's chosen primary/high-capability writing model |
| Job-match judgments | Text and faithful structured output | Dedicated scorer sub-agent; an authorized isolated session may serve as the producer when the host supports it |
| Content/ATS review | Independent text context and required source content | One-shot session or sub-agent |
| Visual review/source reading | Actual image input with every necessary page | Vision-capable session or agent; attach bytes/images, not just paths |
| Discovery | Appropriate API, search, page-reading or computer-use tools | Host capabilities, independent of the selected text model's brand |
| LaTeX/PDF, hashes and numeric gates | Local standard-library/system tools | Scripts; no provider/model invocation |

No independent execution route means review remains pending. No vision means visual review remains unavailable; extracted text cannot substitute for images. OCR is not a universal requirement or a solution for a missing visual reviewer. An isolated session must be genuinely separate from the primary conversation, not the primary switching its role prompt.

## Portable configuration

Keep requested provider/model IDs opaque, validated strings. Use the host's actual catalog and parameter mapping, not a hardcoded model-name allowlist. `agents.scoring.provider`/`model`/`reasoning_effort` configure scoring preferences; `document_quality.review_provider`/`review_model` and `visual_provider`/`visual_model` configure document reviewers. Null inherits the authorized host choice and does not guarantee low cost or vision.

Provider IDs such as `anthropic`, `openai`, and `deepseek` identify requested routes; they are not credentials or permission to transmit candidate data. Claude is the model family under Anthropic; use the actual host's naming rather than inferring provider from an arbitrary model alias. Writing stays on the user's chosen primary model, with any model change handled by the actual host and existing user authorization. A model name in a prompt does not select it.

Map reasoning/effort and structured-output controls to what the selected model actually supports. Do not forward OpenAI-specific effort names or JSON-schema parameters blindly to another provider. When native structured output is unavailable, request one JSON response and validate locally. Empty, truncated, malformed or semantically incomplete output is a failed/pending task, not zero or an invented successful review; use bounded correction attempts.

All active scoring and review calls share the configured global limit even if some use sub-agents and others use direct isolated sessions. Track route-specific host limits as well. Replacing a sub-agent with a session does not reset attempts, authorize an unlimited parallel pool, or change the PDF/hash/independence rules.

Retain actual provider/model/session identity, requested settings, input/output hashes and exposed usage in execution receipts. Mark unreported values unknown. Never copy API keys into workspace files/prompts or add a new provider account as an implicit cost optimization. Existing host integrations are preferred; optional direct clients would need their own explicitly scoped implementation.

## Official capability references

Consult current provider documentation for the selected model, not a static assumption that all models of a brand share the same features:

- OpenAI documents image input through its model APIs: [Images and vision](https://developers.openai.com/api/docs/guides/images-vision).
- Anthropic documents text/image Messages requests and image content blocks: [Messages](https://platform.claude.com/docs/en/api/http/messages), [Vision](https://platform.claude.com/docs/en/build-with-claude/vision).
- DeepSeek documents model metadata, structured JSON output, and vision for supported models; do not label the whole provider text-only: [Models](https://api-docs.deepseek.com/api/list-models/), [JSON Output](https://api-docs.deepseek.com/guides/json_mode/), [Vision](https://api-docs.deepseek.com/guides/vision/).

These are implementation references, not runtime dependencies or evidence of the user's model access. The current helpers validate policy and local results; they do not ship Claude/OpenAI/DeepSeek network adapters, query account access, select a model, discover capabilities, or dispatch provider requests.
