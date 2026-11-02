from content_factory.tasks import IDEA, REVISION, parse_update

IDEAS = -100
DRAFTS = -200


def post(chat_id, **fields):
    return {"update_id": 1, "channel_post": {"message_id": 7, "chat": {"id": chat_id}, **fields}}


def test_message_in_ideas_channel_becomes_idea():
    task = parse_update(post(IDEAS, text=" An idea "), IDEAS, DRAFTS)
    assert (task.kind, task.text, task.message_id) == (IDEA, "An idea", 7)


def test_caption_is_used_when_there_is_no_text():
    assert parse_update(post(IDEAS, caption="From a photo"), IDEAS, DRAFTS).text == "From a photo"


def test_other_channels_are_ignored():
    assert parse_update(post(-999, text="Do something"), IDEAS, DRAFTS) is None


def test_private_messages_are_ignored():
    update = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": IDEAS}, "text": "x"}}
    assert parse_update(update, IDEAS, DRAFTS) is None


def test_new_draft_does_not_trigger_a_run():
    assert parse_update(post(DRAFTS, text="A finished draft"), IDEAS, DRAFTS) is None


def test_reply_in_drafts_becomes_revision_with_quote():
    task = parse_update(
        post(DRAFTS, text="Shorter", reply_to_message={"text": "Long draft"}, quote={"text": "Long"}),
        IDEAS, DRAFTS,
    )
    assert (task.kind, task.text, task.original, task.quote) == (REVISION, "Shorter", "Long draft", "Long")


def test_empty_message_is_ignored():
    assert parse_update(post(IDEAS), IDEAS, DRAFTS) is None
