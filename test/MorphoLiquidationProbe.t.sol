// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface Vm {
    function createSelectFork(string calldata url) external returns (uint256);
    function envAddress(string calldata name) external returns (address);
    function envBytes32(string calldata name) external returns (bytes32);
    function envOr(string calldata name, uint256 defaultValue) external returns (uint256);
}

struct MarketParams {
    address loanToken;
    address collateralToken;
    address oracle;
    address irm;
    uint256 lltv;
}

interface IMorpho {
    function idToMarketParams(bytes32 id) external view returns (MarketParams memory);
    function position(bytes32 id, address user)
        external
        view
        returns (uint256 supplyShares, uint128 borrowShares, uint128 collateral);
    function liquidate(
        MarketParams calldata marketParams,
        address borrower,
        uint256 seizedAssets,
        uint256 repaidShares,
        bytes calldata data
    ) external returns (uint256 seizedAssetsOut, uint256 repaidAssetsOut);
}

contract MorphoLiquidationProbeTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    address private constant MAINNET_MORPHO = 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb;

    error LiquidationReachedCallback(uint256 repaidAssets, bytes data);
    error LiquidationUnexpectedlySucceeded(uint256 seizedAssets, uint256 repaidAssets);
    error LiquidationDidNotReachCallback(
        bytes32 marketId,
        address borrower,
        uint128 borrowShares,
        uint128 collateral,
        bytes revertData
    );
    error EmptyPosition(bytes32 marketId, address borrower);

    function test_morpho_liquidation_reaches_callback() external {
        vm.createSelectFork("mainnet");

        bytes32 marketId = vm.envBytes32("MORPHO_MARKET_ID");
        address borrower = vm.envAddress("MORPHO_BORROWER");
        uint256 seizedAssets = vm.envOr("MORPHO_SEIZED_ASSETS", uint256(0));
        uint256 repaidShares = vm.envOr("MORPHO_REPAID_SHARES", uint256(0));

        IMorpho morpho = IMorpho(MAINNET_MORPHO);
        MarketParams memory marketParams = morpho.idToMarketParams(marketId);
        (, uint128 borrowShares, uint128 collateral) = morpho.position(marketId, borrower);

        if (borrowShares == 0 && collateral == 0) revert EmptyPosition(marketId, borrower);
        if (seizedAssets == 0 && repaidShares == 0) {
            repaidShares = 1;
        }

        try morpho.liquidate(marketParams, borrower, seizedAssets, repaidShares, hex"01")
            returns (uint256 seizedAssetsOut, uint256 repaidAssetsOut)
        {
            revert LiquidationUnexpectedlySucceeded(seizedAssetsOut, repaidAssetsOut);
        } catch (bytes memory reason) {
            if (_selectorOf(reason) == LiquidationReachedCallback.selector) return;
            revert LiquidationDidNotReachCallback(
                marketId, borrower, borrowShares, collateral, reason
            );
        }
    }

    function onMorphoLiquidate(uint256 repaidAssets, bytes calldata data) external pure {
        revert LiquidationReachedCallback(repaidAssets, data);
    }

    function _selectorOf(bytes memory reason) private pure returns (bytes4 selector) {
        if (reason.length < 4) return bytes4(0);

        assembly {
            selector := mload(add(reason, 0x20))
        }
    }
}
