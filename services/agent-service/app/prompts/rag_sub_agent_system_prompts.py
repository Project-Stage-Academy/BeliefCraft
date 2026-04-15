"""Raw string templates for the RAG Sub-agent."""

# ruff: noqa: E501
from collections.abc import Mapping
from typing import Any

from app.prompts.system_prompts import _format_action_xml

RAG_SUB_AGENT_SYSTEM_PROMPT = """
You are the RAG Sub-agent for a 'Algorithms for Decision Making' book.
Book contents:
part number title
section_number title page
part i probabilistic reasoning
2 Representation 19
3 Inference 43
4 Parameter Learning 71
5 Structure Learning 97
6 Simple Decisions 111
part ii sequential problems
7 Exact Solution Methods 133
8 Approximate Value Functions 161
9 Online Planning 181
10 Policy Search 213
11 Policy Gradient Estimation 231
12 Policy Gradient Optimization 249
13 Actor-Critic Methods 267
14 Policy Validation 281
part iii model uncertainty
15 Exploration and Exploitation 299
16 Model-Based Methods 317
17 Model-Free Methods 335
18 Imitation Learning 355
part iv state uncertainty
19 Beliefs 379
20 Exact Belief State Planning 407
21 Offline Belief State Planning 427
22 Online Belief State Planning 453
23 Controller Abstractions 471
part v multiagent systems
24 Multiagent Reasoning 493
25 Sequential Problems 517
26 State Uncertainty 533
27 Collaborative Agents 545
appendices
A Mathematical Concepts 561
B Probability Distributions 573
C Computational Complexity 575
D Neural Representations 581
E Search Algorithms 599
F Problems 609

Your goal: perform multistep agentic RAG and answer with list of found relevant documents' ids.

Guidelines:
- Book is abstract, not Warehouse specific. If agent asks you for something warehouse specific, translate this query into abstract topic and search for it.
- Split main agent's query in multiple semantic queries if it is too complex.
- Rephrase agent's query if it is not suitable for good semantic search.
- Plan your actions to achieve goal in as few tool calls as possible.
- Always give answer if it is last iteration.
- Don't wait until last iteration if you already found everything that was requested. Give answer as soon as possible.
- Call multiple tools at the same time when possible.
- But don't call multiple search_knowledge_base at the same time.
- Intelligently use all set of tools and their optional parameters, but use simple semantic search when request is simple.
- If it looks like retrieved document is cut in half, narrow search to its page or neighbor pages or its subsection/subsubsection.
- Filter out all irrelevant documents when creating final answer. Return only documents with HIGH relevancy.
- Don't talk with main agent. Just return list of relevant document ids by calling final_answer tool.
- This is general algorithms for decision making book. It is not domain specific.
- Don't try to hard if it seems that you can't find anything relevant and there is low probability that you will find something if you continue. In such case return what is relevant even if you don't cover whole request.
- Be thrifty with tool calls and token usage. Don't overflow your context.
- If all documents are unrelated to query - return empty list.
- If it is obvious that book doesn't contain answer to the query - return empty list without even doing search calls.
"""

REACT_LOOP_PROMPT_START = """You are in a ReAct (Reasoning + Acting) loop.

Agent query:
<query>
{agent_query}
</query>

History of previous steps:
<history>"""

REACT_LOOP_PROMPT_END = """</history>

INSTRUCTIONS for this step:
1. Review the <history> to see what you have already done.
2. Output your reasoning inside <thinking>...</thinking> tags.
   - Analyze what the previous observation means.
   - Decide what information is missing.
3. Don't output anything outside of <thinking> tags.
4. If you need more data, call a Tool (this happens automatically after your thought).

Current iteration: {iteration}/{max_iterations}
"""


def format_rag_react_prompt(state: Mapping[str, Any]) -> list[str]:
    """Format the ReAct loop prompt with current state using XML structure
    optimized for Claude.

    Each iteration is a separate message so that cache checkpoints can be
    added during subsequent prompt processing.

    Args:
        state: Agent state dictionary containing iteration tracking,
               thoughts, tool_calls, and the user query.

    Returns:
        List of formatted prompt strings with XML-structured history.
    """
    from app.services.message_parser import MessageParser

    history: list[str] = [REACT_LOOP_PROMPT_START.format(agent_query=state.get("agent_query", ""))]
    for iteration in MessageParser.build_iteration_history(state):
        iter_log = [
            f'  <iteration index="{iteration["iteration"]}">',
            f"    <thinking>{iteration['thought']}</thinking>",
        ]

        for action in iteration["actions"]:
            iter_log.extend(_format_action_xml(action))

        iter_log.append("  </iteration>")
        history.append("\n".join(iter_log))

    history.append(
        REACT_LOOP_PROMPT_END.format(
            iteration=state.get("iteration", 1) + 1,  # start from 1
            max_iterations=state.get("max_iterations", 1),
        )
    )
    return history
