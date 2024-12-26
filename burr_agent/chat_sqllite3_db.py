"""Creates an instance of the app.

The state is persisted in a local sql3lite database.
"""

from burr.core import Application, persistence

from burr_agent import app_graph


def create_chat_app(app_id: int, user: str) -> Application:
    """Creating unique chat app for each user."""
    partition_key = f"new_burr_user_{user}"

    sqllite_persister = persistence.SQLLitePersister(
        db_path="./sqlite.db", table_name="llm_chats"
    )
    sqllite_persister.initialize()

    return (
        app_graph()
        .initialize_from(
            initializer=sqllite_persister,
            resume_at_next_action=True,
            default_state={"chat_history": []},
            default_entrypoint="human_input",
        )
        .with_state_persister(sqllite_persister)
        .with_identifiers(app_id=str(app_id), partition_key=partition_key)
        .build()
    )
