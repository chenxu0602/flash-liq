from __future__ import annotations

from dataclasses import asdict, dataclass


ATTACK_TX = "0xb93506af8f1a39f6a31e2d34f5f6a262c2799fef6e338640f42ab8737ed3d8a4"
ATTACK_BLOCK = 24_566_937
FORK_BLOCK = ATTACK_BLOCK - 1

CONTROLLER = "0xaD444663c6C92B497225c6cE65feE2E7F78BFb86"
LLAMMA = "0x0079885E248B572CdC4559A8B156745e2d8EA1f7"
ORACLE = "0x88822eE517Bfe9A1b97bf200b0b6D3F356488fF2"
SDOLA = "0xb45ad160634c528Cc3D2926d9807104FA3157305"
DOLA_SAVINGS = "0xE5f24791E273Cb96A1f8E5B67Bc2397F0AD9B8B4"
CURVE_POOL = "0xff17dAb22F1E61078aBa2623c89cE6110E878B3c"
CRVUSD_AGG = "0x18672b1b0c623a30089A280Ed9256379fb0E4E62"
DOLA = "0x865377367054516e17014CcdED1e7d814EDC9ce4"
CRVUSD = "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E"

LLAMMA_CRVUSD_IN = 13_250_000 * 10**18
DOLA_DONATION = 190_777 * 10**18
LIQUIDATION_FUNDING = 12_000_000 * 10**18

LIQUIDATED_BORROWERS = (
    "0x2b083a0aa6b808a31e9ac749772a285f5cd34fbe",
    "0xcbcc2b2ecd195ebef03fcb7c7564e4e906485a14",
    "0xba5aa2a3dbbbb4c7c3a8950fc6251bb8020cf844",
    "0x145e305a6e8979cbefcb75993f7ae5270856c1d2",
    "0xf60de76791c2f09995df52aa1c6e2e7dcf1e75d7",
    "0xe9c0df9bd4607850d410c957fec11ec209de5ef6",
    "0x8db98764ada29b55a23f7a8cb07be6f74f0d0e75",
    "0xc6c77b16a85c3946e0bdfc71fdb7efd3d89359d0",
    "0x5b860e2d38f723d5370cf21f82d6adad31ef0b7d",
    "0xb152fc7e9ddf01a942685e390a74009cd2b9ca52",
    "0xe170ed9d77792397271d564c7161351d69fe9300",
    "0x8fc5777d607171b42a61fed4c74242e54677903f",
    "0x80c67fe70d7d6cc488782439fad381d8646640c4",
    "0x9bf8af305152faddd81c70f8599148e9fc6efa20",
    "0x21ab0875611da0235bc5b6405b8a08268d859700",
    "0x6ce50491faa9fac1dc883a2769ab129e75eb0a75",
    "0xc69f65d2720df32c244163e0f608284415aaef4b",
    "0x6db248100cf4908429ab671f33d105311ed7fef8",
    "0xc8233a46f57add754f32cf9e25a85aae8a7d5f29",
    "0xc8801ffaaa9dfcce7299e7b4eb616741ea01f5de",
    "0x57f845829140d9d9d8e357fa0d9f943483a12fc5",
    "0xd4ffcd8b6b7ec90f4eac001125f4a7b21dc0f781",
    "0x3e258aae11d7ea394b2eb1176ccd54d9eb83861b",
    "0x6ef36f7130d00addf40ce9b040da0bc02491d2e1",
    "0x2d57740ee18594bcbfa845703fad49882e1567d9",
    "0xadbafae28c3041ecb74456cd7fb9097bd1287308",
    "0x8467241838bc761d9ef4f8ae6790ede292fba2f9",
)


@dataclass(frozen=True)
class CurveSdolaReplay:
    attack_tx: str
    attack_block: int
    fork_block: int
    controller: str
    llamma: str
    oracle: str
    sdola: str
    dola_savings: str
    curve_pool: str
    crvusd_agg: str
    dola: str
    crvusd: str
    llamma_crvusd_in: int
    dola_donation: int
    liquidation_funding: int
    borrowers: tuple[str, ...]


def get_curve_sdola_replay() -> CurveSdolaReplay:
    return CurveSdolaReplay(
        attack_tx=ATTACK_TX,
        attack_block=ATTACK_BLOCK,
        fork_block=FORK_BLOCK,
        controller=CONTROLLER,
        llamma=LLAMMA,
        oracle=ORACLE,
        sdola=SDOLA,
        dola_savings=DOLA_SAVINGS,
        curve_pool=CURVE_POOL,
        crvusd_agg=CRVUSD_AGG,
        dola=DOLA,
        crvusd=CRVUSD,
        llamma_crvusd_in=LLAMMA_CRVUSD_IN,
        dola_donation=DOLA_DONATION,
        liquidation_funding=LIQUIDATION_FUNDING,
        borrowers=LIQUIDATED_BORROWERS,
    )


def replay_as_dict() -> dict[str, object]:
    return asdict(get_curve_sdola_replay())


def replay_env_lines() -> list[str]:
    replay = get_curve_sdola_replay()
    return [
        f"CURVE_SDOLA_FORK_BLOCK={replay.fork_block}",
        f"CURVE_SDOLA_CONTROLLER={replay.controller}",
        f"CURVE_SDOLA_LLAMMA={replay.llamma}",
        f"CURVE_SDOLA_ORACLE={replay.oracle}",
        f"CURVE_SDOLA_SDOLA={replay.sdola}",
        f"CURVE_SDOLA_DOLA_SAVINGS={replay.dola_savings}",
        f"CURVE_SDOLA_DOLA={replay.dola}",
        f"CURVE_SDOLA_CRVUSD={replay.crvusd}",
        f"CURVE_SDOLA_LLAMMA_CRVUSD_IN={replay.llamma_crvusd_in}",
        f"CURVE_SDOLA_DOLA_DONATION={replay.dola_donation}",
        f"CURVE_SDOLA_LIQUIDATION_FUNDING={replay.liquidation_funding}",
    ]
