"""Defines actions of the state machine.

In this simple example we will just record chat history in the state and allow the user
to ask questions.

Using ollama to locally run an LLM.
"""

from beartype.typing import Tuple
from burr.core import ApplicationBuilder, State, action
from ollama import ChatResponse, chat

__all__ = ("app_graph",)


@action(reads=[], writes=["prompt", "chat_history"])
def human_input(state: State, prompt: str) -> Tuple[dict, State]:
    """Records user input into state history that is passed to ai agent."""
    chat_item = {"content": prompt, "role": "user"}

    return (
        {"prompt": prompt},
        state.update(prompt=prompt).append(chat_history=chat_item),
    )


@action(reads=["chat_history"], writes=["response", "chat_history"])
def ai_response(state: State) -> Tuple[dict, State]:
    """Queries ollama with user prompt and chat history."""
    response: ChatResponse = chat(model="llama3.2:1b", messages=state["chat_history"])
    content = response.message.content

    chat_item = {"content": content, "role": "assistant"}
    return (
        {"response": content},
        state.update(response=content).append(chat_history=chat_item),
    )


def app_graph() -> ApplicationBuilder:
    """Connects together the graph for the state machine, but does not built the app."""
    return (
        ApplicationBuilder()
        .with_actions(human_input=human_input, ai_response=ai_response)
        .with_transitions(
            ("human_input", "ai_response"), ("ai_response", "human_input")
        )
    )
