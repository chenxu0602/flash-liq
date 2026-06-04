from __future__ import annotations

from flash_liq.curve_sdola import (
    ATTACK_BLOCK,
    FORK_BLOCK,
    LIQUIDATED_BORROWERS,
    replay_as_dict,
    replay_env_lines,
)


def test_replay_constants_are_historical_prefork() -> None:
    assert ATTACK_BLOCK == 24_566_937
    assert FORK_BLOCK == ATTACK_BLOCK - 1
    assert len(LIQUIDATED_BORROWERS) == 27


def test_replay_output_contains_required_contracts() -> None:
    replay = replay_as_dict()

    assert replay["controller"] == "0xaD444663c6C92B497225c6cE65feE2E7F78BFb86"
    assert replay["llamma"] == "0x0079885E248B572CdC4559A8B156745e2d8EA1f7"
    assert replay["sdola"] == "0xb45ad160634c528Cc3D2926d9807104FA3157305"


def test_replay_env_lines_do_not_include_secrets() -> None:
    env = "\n".join(replay_env_lines())

    assert "CURVE_SDOLA_FORK_BLOCK=24566936" in env
    assert "MAINNET_FORKING_URL" not in env
    assert "https://" not in env
