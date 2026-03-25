from app.repositories.command_state import add_message, add_task, get_state, update_task

HELP_TEXT = (
    "I can currently handle lightweight dashboard commands like: "
    "'add task <title>', 'complete task <id>', 'show tasks', 'status', and general notes."
)


def handle_command(message: str) -> dict:
    text = (message or "").strip()
    if not text:
        return {"reply": "Say something specific and I’ll log or route it.", "state": get_state()}

    add_message("user", text)
    lowered = text.lower()

    if lowered.startswith("add task "):
        title = text[9:].strip()
        state = add_task(title)
        reply = f"Added task: {title}"
    elif lowered.startswith("complete task "):
        raw = text[14:].strip()
        try:
            task_id = int(raw)
            state = update_task(task_id, "done")
            reply = f"Marked task {task_id} complete."
        except ValueError:
            state = get_state()
            reply = "Use 'complete task <id>'."
    elif lowered in {"show tasks", "list tasks"}:
        state = get_state()
        tasks = state.get("tasks", [])
        if tasks:
            reply = "Tasks:\n" + "\n".join(f"#{t['id']} [{t['status']}] {t['title']}" for t in tasks)
        else:
            reply = "No tasks yet."
    elif lowered == "status":
        state = get_state()
        reply = (
            f"Messages logged: {len(state.get('messages', []))}. "
            f"Tasks tracked: {len(state.get('tasks', []))}."
        )
    else:
        state = get_state()
        reply = (
            "Captured. I’m treating this as dashboard-native communication. "
            "Right now I can persist the note and track lightweight tasks while the deeper command routing is being built.\n\n"
            + HELP_TEXT
        )

    state = add_message("assistant", reply)
    return {"reply": reply, "state": state}
