"""Reading instagram_accounts.yaml, which is edited by hand and so arrives in many shapes."""

from pathlib import Path

from instagram_agent.accounts import parse_accounts


def test_a_bare_username_is_an_account():
    assert [a.username for a in parse_accounts("accounts:\n  - ubtalmaty\n")] == ["ubtalmaty"]


def test_a_mapping_carries_the_hint_and_the_city():
    account = parse_accounts(
        """
        accounts:
          - username: ubtalmaty
            hint: "announces a Saturday coffee ride"
            city: Almaty
        """
    )[0]
    assert (account.username, account.hint, account.city) == ("ubtalmaty", "announces a Saturday coffee ride", "Almaty")


def test_a_pasted_profile_link_is_reduced_to_the_username():
    # What copying an account out of the Instagram app actually gives you.
    text = "accounts:\n  - https://www.instagram.com/ubtalmaty?igsh=dnNnZ25odDFsbWFs\n"
    assert [a.username for a in parse_accounts(text)] == ["ubtalmaty"]


def test_an_at_handle_is_accepted():
    assert [a.username for a in parse_accounts("accounts:\n  - '@kcfkz'\n")] == ["kcfkz"]


def test_a_disabled_account_is_left_out():
    text = "accounts:\n  - username: paused\n    enabled: false\n  - username: live\n"
    assert [a.username for a in parse_accounts(text)] == ["live"]


def test_the_same_account_written_twice_is_read_once():
    text = "accounts:\n  - ubtalmaty\n  - https://instagram.com/UBTAlmaty/\n"
    assert [a.username for a in parse_accounts(text)] == ["ubtalmaty"]


def test_malformed_entries_are_skipped_rather_than_raising():
    text = "accounts:\n  - ''\n  - 42\n  - username: ''\n  - good_one\n"
    assert [a.username for a in parse_accounts(text)] == ["good_one"]


def test_an_empty_or_broken_file_yields_no_accounts():
    assert parse_accounts("") == []
    assert parse_accounts("just a string") == []
    assert parse_accounts("accounts: not-a-list") == []


def test_a_plain_list_without_the_accounts_key_still_reads():
    assert [a.username for a in parse_accounts("- ubtalmaty\n- kcfkz\n")] == ["ubtalmaty", "kcfkz"]


def test_the_shipped_accounts_file_parses_and_names_only_real_accounts():
    accounts = parse_accounts(Path("instagram_accounts.yaml").read_text(encoding="utf-8"))
    assert accounts, "the shipped file should carry at least one enabled account"
    assert all(a.username and " " not in a.username for a in accounts)


def test_the_enabled_names_are_what_a_workflow_builds_its_jobs_from():
    from instagram_agent.accounts import enabled_usernames

    text = "accounts:\n  - live_one\n  - username: paused\n    enabled: false\n  - '@second'\n"
    assert enabled_usernames(text) == ["live_one", "second"]


def test_the_shipped_file_names_the_accounts_the_workflow_will_run():
    from instagram_agent.accounts import enabled_usernames

    names = enabled_usernames(Path("instagram_accounts.yaml").read_text(encoding="utf-8"))
    assert names, "an empty list would leave the workflow with no jobs to run"
    assert len(names) == len(set(names))
