"""Creates an instance of the app.

The state is persisted in a postgres database.
"""

from burr.core import Application
from burr.integrations.persisters.postgresql import PostgreSQLPersister

from burr_agent import app_graph


def create_chat_app(app_id: int, user: str) -> Application:
    """Creating unique chat app for each user."""
    partition_key = f"new_burr_user_{user}"

    postgres_persister = PostgreSQLPersister.from_values(
        "postgres",
        "postgres",
        "my_password",
        "localhost",
        54320,
        table_name="llm_chats",
    )
    postgres_persister.initialize()
    return (
        app_graph()
        .initialize_from(
            initializer=postgres_persister,
            resume_at_next_action=True,
            default_state={"chat_history": []},
            default_entrypoint="human_input",
        )
        .with_state_persister(postgres_persister)
        .with_identifiers(app_id=str(app_id), partition_key=partition_key)
        .build()
    )
