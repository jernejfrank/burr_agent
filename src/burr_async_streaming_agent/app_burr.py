"""State machine governing the chatbot interaction."""

import asyncio
import copy

import ollama
from beartype.typing import AsyncGenerator, Optional, Tuple
from burr.core import ApplicationBuilder, State, default, persistence, when
from burr.core.action import action, streaming_action
from burr.core.graph import GraphBuilder

MODES = [
    "answer_question",
    "generate_poem",
    "generate_code",
    "unknown",
]


@action(reads=[], writes=["chat_history", "prompt"])
def process_prompt(state: State, prompt: str) -> Tuple[dict, State]:
    result = {"chat_item": {"role": "user", "content": prompt, "type": "text"}}
    return result, state.wipe(keep=["prompt", "chat_history"]).append(
        chat_history=result["chat_item"]
    ).update(prompt=prompt)


@action(reads=["prompt"], writes=["safe"])
def check_safety(state: State) -> Tuple[dict, State]:
    result = {"safe": "unsafe" not in state["prompt"]}  # quick hack to demonstrate
    return result, state.update(safe=result["safe"])


def _get_ollama_client():
    return ollama.AsyncClient()


@action(reads=["prompt"], writes=["mode"])
async def choose_mode(state: State) -> Tuple[dict, State]:
    prompt = (
        f"You are a chatbot. You've been prompted this: {state["prompt"]}. You have "
        f"the  capability of responding in the following modes: {", ".join(MODES)}. "
        "Please respond with *only* a single word representing the mode that most "
        "accurately corresponds to the prompt. For instance, if the prompt is 'write a "
        "poem about Alexander Hamilton and Aaron Burr', the mode would be "
        "'generate_poem'. If the prompt is 'what is the capital of France', the mode "
        " would be 'answer_question'.And so on, for every mode. If none of these modes "
        "apply, please respond with 'unknown'. Omit any * in your output. "
    )

    result = await _get_ollama_client().chat(
        model="llama3.2:1b",
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": prompt},
        ],
        stream=False,
    )
    content = result.message.content
    mode = content.lower()  # type: ignore
    if mode not in MODES:
        new_mode = "unknown"
    else:
        new_mode = mode
    result = {"mode": new_mode, "llm_mode": mode}
    return result, state.update(**result)


@streaming_action(reads=["prompt", "chat_history"], writes=["response"])
async def prompt_for_more(
    state: State,
) -> AsyncGenerator[Tuple[dict, Optional[State]], None]:
    """Not streaming, as we have the result immediately."""
    result = {
        "response": {
            "content": (
                "None of the response modes I support apply to your "
                "question. Please clarify?"
            ),
            "type": "text",
            "role": "assistant",
        }
    }
    for word in result["response"]["content"].split():
        await asyncio.sleep(0.1)
        yield {"delta": word + " "}, None
    yield result, state.update(**result).append(chat_history=result["response"])


@streaming_action(reads=["prompt", "chat_history", "mode"], writes=["response"])
async def chat_response(
    state: State, prepend_prompt: str, model: str = "llama3.2:1b"
) -> AsyncGenerator[Tuple[dict, Optional[State]], None]:
    """Streaming action, as we don't have the result immediately."""
    chat_history = copy.deepcopy(state["chat_history"])
    chat_history[-1]["content"] = f"{prepend_prompt}: {chat_history[-1]["content"]}"
    chat_history_api_format = [
        {
            "role": chat["role"],
            "content": chat["content"],
        }
        for chat in chat_history
    ]
    client = _get_ollama_client()
    result = await client.chat(
        model=model, messages=chat_history_api_format, stream=True
    )
    buffer = []
    async for chunk in result:
        chunk_str = chunk["message"]["content"]
        if chunk_str is None:
            continue
        buffer.append(chunk_str)
        yield (
            {
                "delta": chunk_str,
            },
            None,
        )

    result = {
        "response": {"content": "".join(buffer), "type": "text", "role": "assistant"},
        "modified_chat_history": chat_history,
    }
    yield result, state.update(**result).append(chat_history=result["response"])


@streaming_action(reads=["prompt", "chat_history"], writes=["response"])
async def unsafe_response(state: State) -> Tuple[dict, State]:  # type: ignore
    result = {
        "response": {
            "content": "I am afraid I can't respond to that...",
            "type": "text",
            "role": "assistant",
        }
    }
    for word in result["response"]["content"].split():
        await asyncio.sleep(0.1)
        yield {"delta": word + " "}, None  # type: ignore
    yield result, state.update(**result).append(chat_history=result["response"])  # type: ignore


graph = (
    GraphBuilder()
    .with_actions(
        prompt=process_prompt,
        check_safety=check_safety,
        unsafe_response=unsafe_response,
        decide_mode=choose_mode,
        generate_code=chat_response.bind(
            prepend_prompt=(
                "Please respond with *only* code and no other text "
                "(at all) to the following"
            ),
        ),
        answer_question=chat_response.bind(
            prepend_prompt="Please answer the following question",
        ),
        generate_poem=chat_response.bind(
            prepend_prompt="Please generate a poem based on the following prompt",
        ),
        prompt_for_more=prompt_for_more,
    )
    .with_transitions(
        ("prompt", "check_safety", default),
        ("check_safety", "decide_mode", when(safe=True)),
        ("check_safety", "unsafe_response", default),
        ("decide_mode", "generate_code", when(mode="generate_code")),
        ("decide_mode", "answer_question", when(mode="answer_question")),
        ("decide_mode", "generate_poem", when(mode="generate_poem")),
        ("decide_mode", "prompt_for_more", default),
        (
            [
                "answer_question",
                "generate_poem",
                "generate_code",
                "prompt_for_more",
                "unsafe_response",
            ],
            "prompt",
        ),
    )
    .build()
)


def application(app_id: Optional[str] = None):
    sqllite_persister = persistence.SQLLitePersister(
        db_path="./sqlite.db", table_name="streaming_chat"
    )
    sqllite_persister.initialize()

    app = (
        ApplicationBuilder().with_identifiers(app_id=app_id)
        if app_id
        else ApplicationBuilder()
    )
    return (
        app.initialize_from(
            initializer=sqllite_persister,
            resume_at_next_action=True,
            default_state={"chat_history": []},
            default_entrypoint="prompt",
        )
        .with_graph(graph)
        .with_tracker(project="demo_chatbot_streaming")
        .with_state_persister(sqllite_persister)
        .build()
    )


TERMINAL_ACTIONS = [
    "answer_question",
    "generate_code",
    "prompt_for_more",
    "unsafe_response",
    "generate_poem",
]
if __name__ == "__main__":
    app = application()
    app.visualize(
        output_file_path="statemachine",
        include_conditions=True,
        view=True,
        format="png",
    )
