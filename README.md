# kernel-glossary-tools

This is an experimental, LLM-generated version of [0xff07/kernel-glossary](https://github.com/0xff07/kernel-glossary). The Claude Code plugin creates ad-hoc write-ups for exploring Linux kernel source code, each grounded in one pinned kernel tree.

I use this for two things:

1. **Linearize code reading.** Reading Linux kernel source code usually means jumping back and forth between functions and files. The plugin helps find an order to read the code in, so that understanding the kernel becomes a relatively linear experience.
2. **Temporary save points.** The pages track what I have touched while exploring the kernel but not yet fully explored, and serve as a base camp for exploring further.

Existing pages under [docs/](docs/) can be read without installing the plugin.

> **!!! STOP: BEYOND THIS POINT YOU ARE ON YOUR OWN !!!**
>
> These pages are not authoritative sources of kernel knowledge. Check the source yourself.

<details>
<summary>Expectations and precautions</summary>

- **Proper expectations.** You know this is not an authoritative source of kernel knowledge.
- **Self-rescue skills.** You can read C code and find your way through the source even when an explanation is an LLM hallucination.
- **Baseline experience.** You already have some familiarity with the subsystem you are exploring.
- **Human engagement.** Reading these pages is not the same as participating in the kernel community. That means interacting with its people.
- **No upstream submission.** Unverified AI patches create noise and waste maintainers' time. Do not attempt to upstream any documentation from this project unless you are intimately familiar with that area.

</details>

## Install

You need Claude Code with the Workflow tool and a kernel source checkout. From the kernel source root, clone this repository and install the plugin's Python dependencies:

```sh
git clone https://github.com/0xff07/kernel-glossary-tools.git \
  .claude/skills/kernel-glossary
cd .claude/skills/kernel-glossary
python3 -m venv .venv
.venv/bin/pip install -r tools/qa/requirements.txt -r tools/campaign/requirements.txt
cd ../../..
```

Start Claude Code from the kernel source root. Accept the workspace trust dialog if prompted, then run `/skills` and confirm that `kernel-glossary:plan-campaign`, `kernel-glossary:write-campaign` and `kernel-glossary:write-topic` are loaded.

The kernel checkout must match the campaign's pinned commit. See the [setup notes](manual/setup.md) for another checkout or install location, environment variables and optional research tools.

## How it works

Work is organized into **campaigns**: plans for a set of related pages against one pinned kernel tree. Each campaign defines the page catalog and scope boundaries, then groups the pages into named **batches** such as `B1` and `B2`.

Plan and review the campaign first, then write its pages one batch at a time. Each batch selects pages from that plan, so you can continue the same campaign across multiple writing runs. Even a single-page request starts with a plan: a plan of one page, which the topic skill below makes for you.

## Plan a campaign

In Claude Code, invoke the planning skill with a short campaign name and describe what you want to explore:

```text
/kernel-glossary:plan-campaign <campaign> <what you want to explore>
```

The planner records the campaign under `campaigns/`. Review the proposed scope and page catalog before approving it. Approval finishes the planning step; writing starts with a separate command.

Invoking a skill opts in to its workflow.

## Write the first batch

Use the campaign name and a batch ID from the approved plan:

```text
/kernel-glossary:write-campaign <campaign> B1
```

The skill prepares the briefs, runs one writer per page, then checks the results. Its finish step commits each new page that passes the gate and collects findings for the planner to fold back into the plan. Read the per-page results and review any remaining candidates or open issues.

For proofreading, name an existing page explicitly:

```text
/kernel-glossary:write-campaign <campaign> <page-id> stage=proofread
```

## Write one page on a topic

For a single page on its own, without planning a campaign, name the topic, or discuss it first and invoke the skill without one:

```text
/kernel-glossary:write-topic <what the page is about>
```

The skill reads the tree with you, records the topic as a plan of one page under `campaigns/`, shows you the scope it wrote and, on your go, produces the page through the same workflow, checks and commit as a batch. The plan stays, so the page can be proofread later like any other. Every request starts a new plan that stands alone: neither the skill nor the brief it prepares reads an existing campaign or page, and the skill asks you for the architecture and the kernel configuration when the conversation has not named them.

The [workflow notes](manual/workflow.md) explain page selection, stages and the files involved. The [rule maintenance notes](manual/rules.md) cover editing rules and running QA. These guides describe the existing implementation; the skills, scripts and guidelines define its behavior.
