# Additional Devpost answers — draft

Technical answers follow the repository and saved provider records. Numeric
ratings are suggested assessments for the owner to review. Event attendance,
eligibility, additional AI tools, and first-person learning/career statements
need the owner's confirmation. Nothing here submits or attests on their behalf.

## 1. Existing project: significant updates

Not applicable: DocDrift was developed during the hackathon period; this
repository's history starts on October 14, 2026. Development included the
Nemotron repair agent through Nebius Token Factory, independent verification on
Nebius Sandboxes, durable execution recovery, evidence exports, and a hosted demo.

## 2. Public code repository

https://github.com/Iljaadam/DocDrift

The repository is public, has an MIT license, and includes README setup/run
instructions. It identifies NVIDIA Nemotron and Token Factory as the inference
path, Nebius Sandboxes as the hosted verification backend, and Docker as the
local execution backend. MIT is [OSI approved](https://opensource.org/license/mit).

## 3. Working demo

https://iljas-vps.tail2832de.ts.net:8443

The demo requires the shared judge login, supplied in private testing
instructions. Judges need no provider account or API key. They can start a
fresh repair or inspect an existing review and download its evidence ZIP.
Fresh runs use a shared attempt allowance displayed by the app.

## 4. Models used and size/variant choice

We used NVIDIA Nemotron 3 Super through the Token Factory model ID
`nvidia/nemotron-3-super-120b-a12b`. The family has 120 billion total parameters
and 12 billion active parameters, according to [NVIDIA's model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8).
The model card's precision label does not establish the hosted endpoint's precision.

Our main requirements were Python source reasoning, instruction following, and
native structured tool calls. Super was available through our account and passed
our initial tool-calling probe, so we concentrated the bounded repair evaluation
on that variant. We did not run a size/variant cost-performance comparison.

## 5. Nemotron output quality

Suggested rating: **8/10**.

With source-reading and execution tools, Nemotron produced focused repairs that
passed independent checks and preserved healthy examples. Both one-shot and
agent strategies verified 2/2 reserved held-out cases. On a separate exploratory
owned fixture, the agent verified 1/1 while one-shot verified 0/1.

Limitations included a plausible but invalid API guess in that one-shot proposal
and an early agent response that returned raw code instead of the requested
submission tool. Feedback allowed the agent to recover. Our tasks were small,
English-language Python fixtures; multilingual performance was not evaluated.

## 6. Fine-tuning, prompt engineering, or out of the box

We used the pretrained model with task-specific prompt engineering and tool
orchestration, without fine-tuning. The system prompt requests minimal changes,
preservation of meaningful API calls and input/output behavior, and a replacement
for one Markdown code span. Tools support file listing, source reading, isolated
Python probes, and replacement submission.

The implementation uses temperature 0, bounded calls/tokens/candidates, and
feedback from rejected submissions. Frozen acceptance profiles, expected outputs,
and the known repair stay outside the agent's accessible repository. Final
verification is independent of the model's explanation.

## 7. Comparison with other models

We did not run a controlled comparison with other model families, so we cannot
claim that Nemotron outperformed them. Our recorded comparisons used the same
Nemotron model in one-shot and tool-using agent modes, alongside an execution-only
baseline without a model.

The original development and reserved held-out cases tied at 2/2 for both model
strategies. The separate source-inspection development case favored the agent
1/1 versus 0/1. The agent had iterative tools and a larger call allowance; these
small results support a workflow observation, not a cross-model ranking.

## 8. Most valuable Nebius capabilities and infrastructure

Token Factory's managed inference API let us integrate Nemotron through standard
chat-completion and tool-call requests without deploying model weights or managing
an inference GPU server. Reported token usage supported our bounded repair loop.

Nebius Sandboxes supplied disposable execution for original-failure reproduction,
candidate checks, and healthy regressions. We used an existing Python 3.12 image
with a non-root user and networking disabled, and recorded operation IDs/results
for recovery and exported evidence.

The web controller and single worker run on an existing Ubuntu ARM64 VPS. We did
not provision Nebius AI Cloud GPU instances, choose a GPU type, or configure
model-serving autoscaling. The underlying Token Factory inference hardware was
not selected or exposed to us. Scaling was deliberately limited to one worker
and a durable shared attempt allowance.

## 9. Likelihood of recommending Nemotron on Nebius

Suggested rating: **8/10**.

The managed inference API and standard tool-call format worked well for our small
coding-agent project. Token usage reporting and isolated execution helped us
make repairs inspectable and bounded. Clearer per-model metadata, Sandbox image
failure diagnostics, and billing/credit-coverage documentation would improve the
experience. Sandbox billing coverage remains unverified for our account.

## 10. Inference experience compared with other environments

Suggested rating: **8/10** for this project's integration experience.

Token Factory made it straightforward to call Nemotron from our Python client
without maintaining an inference server. We developed verification locally with
Docker and later ran the saved proposal and fresh jobs on Nebius Sandboxes.

That execution-backend experience is not a like-for-like comparison of inference
speed or cost. We did not run the same Nemotron checkpoint locally or on another
cloud for a controlled inference benchmark. The rating reflects API integration
and the overall development workflow.

## 11. Additional platform improvements

- Machine-readable per-model metadata for context limits, supported tool/structured-output
  features, model revision, and pricing.
- Clearer reasoning-token accounting and recommended request settings per model.
- Structured Sandbox image-import diagnostics identifying the failed registry
  operation and a safe cause classification; our first import failed with HTTP 404.
- Explicit Sandbox compute/image/storage pricing, promotional-credit coverage,
  and request/operation-linked usage reporting and spending controls.

## 12. What we hope to see from the Nemotron team

Continued improvements in coding and tool-use reliability across smaller and
mid-sized variants: accurate source-grounded API changes, dependable function
calling, and stable output formats. Versioned releases and reproducible agent
recipes would help developers validate upgrades. Documentation-repair benchmarks
covering healthy-example preservation and misleading-patch rejection would be
especially useful for our use case.

## 13. Tavily

**No.** DocDrift made no functional runtime call to the Tavily API.

## 14. Builders & Brews city

Owner confirmation required. Select the actual participating city only if
attending its event in person; otherwise choose the form's not-attending/N/A
option or leave the optional city field blank.

## 15. Age-of-majority declaration

Owner confirmation required. Check the statement only if the owner and every
teammate satisfy it. Project records do not establish personal eligibility.

## 16. No promotion-entity employment/representation/agency declaration

Owner confirmation required. Check the statement only if it is true for the
owner and every teammate, including the specified sponsor/organizer affiliates.

## 17. AI tools used during development

NVIDIA Nemotron was the runtime repair model, accessed through Nebius Token
Factory. OpenAI Codex assisted with implementation, debugging, tests, security
review, documentation, and deployment work. Repository commit co-authorship also
records Claude Opus 5.5 assistance, alongside the shared Claude Code/Codex handoff.
Confirm the exact Claude product name and disclose any additional tools used.

The development assistants were not alternative runtime models in the controlled
repair comparisons.

## 18. Level of learning

Suggested level: **High / substantial**; owner should confirm this description.

The project provided practical experience with tool-using agents, source-grounded
prompting, independent behavioral verification, immutable inputs, Sandbox execution,
and durable recovery. A central lesson was that successful process execution can
still produce the wrong behavior, and that varied checks and honest baselines
are essential for evaluating a repair agent.

## 19. AI value applicable to a career

Suggested answer, if accurate for the owner: **Yes.**

The project provided reusable experience in integrating model APIs, designing
bounded agent workflows, evaluating outputs against independent checks, and
building inspectable evidence. These skills can transfer to developer tooling,
test automation, and other AI-assisted engineering workflows.
