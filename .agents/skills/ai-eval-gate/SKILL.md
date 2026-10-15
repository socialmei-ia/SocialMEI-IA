---
name: ai-eval-gate
description: Define a go/no-go evaluation gate for SocialMEI AI, purchase-intent, chatbot or multimodal changes before pilot or release.
---

1. Define the exact AI behavior and downstream decision.
2. List high-risk failure modes.
3. Build representative PT-BR scenarios, including short/noisy WhatsApp language, ambiguity, missing context and tool failures.
4. Separate sentiment from purchase intent when relevant.
5. Define expected output schema, acceptable uncertainty and human-confirmation cases.
6. Include privacy, latency and cost checks when applicable.
7. Define regression thresholds and what requires human review.
8. Do not approve a score or percentage without evidence that its calibration/meaning is understood.

Return READY, NEEDS DATA or BLOCKED with evidence gaps.
