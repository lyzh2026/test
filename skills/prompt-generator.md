---
name: product-prompt-generator
description: This skill should be used when the user wants to generate a comprehensive, structured AI prompt (for Gemini, Claude, ChatGPT, etc.) based on a product or software vision/description. Trigger phrases include "帮我生成 prompt", "生成开发 prompt", "把我的想法整理成 prompt", "generate a product prompt", "turn my idea into a prompt", "create a system prompt for my app/software/product". Use this skill whenever the user describes a product, app, tool, or software and wants a well-structured prompt to hand off to an AI model.
---

# Product Prompt Generator

## Overview

To convert a user's raw product vision or description into a well-structured, comprehensive AI prompt suitable for Gemini, Claude, ChatGPT, and other LLMs. The generated prompt should clearly communicate product positioning, tech stack, target audience, UI design, usage flow, and more — enabling the AI to fully understand and execute the product vision.

## Workflow

### Step 1: Extract and Clarify the Vision

Upon receiving the user's product description, extract key information across these dimensions. If any critical dimension is **unclear or missing**, ask ONE focused question (not a list) to gather the most important missing piece before proceeding.

**Core Dimensions to Identify:**

| Dimension | Key Questions |
|-----------|--------------|
| **产品定位 / Product Positioning** | What problem does it solve? What makes it unique? |
| **目标受众 / Target Audience** | Who are the users? Demographics, technical level, pain points |
| **核心功能 / Core Features** | What are the 3-5 must-have features? |
| **技术栈 / Tech Stack** | Frontend, backend, database, deployment preferences (or ask for recommendation) |
| **UI 风格 / UI Style** | Design aesthetic, color preferences, component library preferences |
| **使用场景 / Usage Scenarios** | When and how will users interact with the product? |
| **约束条件 / Constraints** | Budget, timeline, scale requirements, platform (web/mobile/desktop) |

**Decision Rule:** If the user's description already covers most dimensions (5+), proceed directly to prompt generation. If fewer than 3 dimensions are clear, ask for clarification on the most critical missing piece.

### Step 2: Generate the Structured Prompt

Use the template in `references/prompt_template.md` to construct the final prompt. Populate each section based on the extracted information.

**Prompt Generation Rules:**
- Write the prompt in the **same language** the user described their product (Chinese → Chinese prompt; English → English prompt). For mixed input, default to English for the generated prompt (wider AI compatibility).
- Be **specific and concrete** — avoid vague adjectives. Replace "modern UI" with "clean card-based layout with subtle shadows, 8px border radius, and a blue-gray color palette."
- Include **negative constraints** where helpful (e.g., "Do NOT use dark mode as default", "Avoid complex onboarding flows").
- Tailor the prompt to the most likely **target AI model** if the user specifies one (Claude → emphasize reasoning steps; Gemini → leverage multimodal references; ChatGPT → explicit structured output requests).

### Step 3: Present and Offer Refinement

Present the generated prompt in a **fenced code block** (for easy copy-paste), followed by:
1. A brief summary of key decisions made
2. 2-3 suggested customizations the user might want to adjust
3. An offer to regenerate with different emphasis (e.g., "more technical detail", "simpler for non-devs", "focus on MVP only")

## Resources

- `references/prompt_template.md` — The master template structure for generating prompts. Load this file when generating any product prompt.
