import uuid

from canopy.mapping.matcher import AI, LocalAccount, StandardAccount
from canopy.mapping.suggest import suggest

STANDARD = [
    StandardAccount(uuid.uuid4(), "200", "Sales", "REVENUE", "REVENUE"),
    StandardAccount(uuid.uuid4(), "410", "Insurance", "EXPENSE", "EXPENSE"),
]


def loc(code, name, type_="EXPENSE"):
    return LocalAccount(uuid.uuid4(), code, name, type_, None)


def canned(answers: dict):
    """Fake completer: answers by the account name it finds on each L-line."""

    async def complete(system, user, schema):
        out = []
        for line in user.splitlines():
            if line.startswith("L"):
                ref, _code, name, *_ = [p.strip() for p in line.split("|")]
                if name in answers:
                    code, conf = answers[name]
                    out.append({"local_ref": ref, "group_code": code, "confidence": conf, "reasoning": "r"})
        return {"suggestions": out}

    return complete


async def test_valid_suggestion_is_kept_as_ai_match():
    a = loc("650", "Park Insurance")
    (m,) = await suggest(canned({"Park Insurance": ("410", 0.8)}), [a], STANDARD)
    assert (m.source, m.group_id, m.confidence) == (AI, STANDARD[1].id, 0.8)


async def test_invented_group_code_is_discarded():
    a = loc("650", "Park Insurance")
    (m,) = await suggest(canned({"Park Insurance": ("999", 0.9)}), [a], STANDARD)
    assert m.group_id is None and m.confidence == 0.0 and "doesn't exist" in m.reasoning


async def test_cross_class_suggestion_is_discarded():
    a = loc("650", "Park Insurance")  # EXPENSE
    (m,) = await suggest(canned({"Park Insurance": ("200", 0.95)}), [a], STANDARD)  # REVENUE
    assert m.group_id is None and "can't map" in m.reasoning


async def test_no_equivalent_and_skipped_accounts_still_get_a_row():
    a, b = loc("651", "Site Fund"), loc("652", "Forgotten")
    ma, mb = await suggest(canned({"Site Fund": (None, 0.7)}), [a, b], STANDARD)
    assert ma.group_id is None and ma.confidence == 0.7
    assert mb.group_id is None and mb.confidence == 0.0
