from __future__ import annotations

from pathlib import Path

from tools.validate_sprint29_nexyra import read_env, validate


ROOT = Path(__file__).resolve().parents[1]


def test_final_example_reserves_8766_for_nexyra_copilot() -> None:
    values = read_env(ROOT / ".env.nexyra.example").values
    assert values["ATLAS_COPILOT_PORT"] == "8766"
    assert values["ATLAS_NEXYRA_URL"] == "http://127.0.0.1:8000"


def test_final_validator_accepts_matching_distinct_tokens(tmp_path: Path) -> None:
    atlas_env = tmp_path / "atlas.env"
    nexyra_root = tmp_path / "nexyra"
    nexyra_root.mkdir()
    nexyra_env = nexyra_root / ".env"

    atlas_env.write_text(
        "\n".join(
            [
                "ATLAS_NEXYRA_URL=http://127.0.0.1:8000",
                "ATLAS_NEXYRA_TOKEN=integration-secret",
                "ATLAS_NEXYRA_WORKSPACE_ID=WS-DEMO",
                "ATLAS_NEXYRA_ACTOR_USER_ID=USR-ADMIN",
                "ATLAS_COPILOT_TOKEN=copilot-secret",
                "ATLAS_COPILOT_PORT=8766",
            ]
        ),
        encoding="utf-8",
    )
    nexyra_env.write_text(
        "\n".join(
            [
                "ATLAS_INTEGRATION_TOKEN=integration-secret",
                "ATLAS_COPILOT_TOKEN=copilot-secret",
                "ATLAS_COPILOT_BRIDGE_URL=http://127.0.0.1:8766",
            ]
        ),
        encoding="utf-8",
    )

    assert validate(atlas_env, nexyra_env, online=False) == 0
