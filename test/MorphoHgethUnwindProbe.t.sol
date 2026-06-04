// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface Vm {
    function createSelectFork(string calldata url) external returns (uint256);
    function createSelectFork(string calldata url, uint256 blockNumber) external returns (uint256);
    function envAddress(string calldata name) external returns (address);
    function envBytes32(string calldata name) external returns (bytes32);
    function envOr(string calldata name, uint256 defaultValue) external returns (uint256);
    function envOr(string calldata name, address defaultValue) external returns (address);
    function deal(address account, uint256 newBalance) external;
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

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IERC4626 is IERC20 {
    function asset() external view returns (address);
    function previewRedeem(uint256 shares) external view returns (uint256);
    function redeem(uint256 shares, address receiver, address owner) external returns (uint256 assets);
}

interface IWETH is IERC20 {
    function deposit() external payable;
}

interface IRsEthRateProvider {
    function rsETHPrice() external view returns (uint256);
}

interface IBalancerV3Router {
    function querySwapSingleTokenExactIn(
        address pool,
        IERC20 tokenIn,
        IERC20 tokenOut,
        uint256 exactAmountIn,
        address sender,
        bytes calldata userData
    ) external returns (uint256 amountOut);
}

contract MorphoHgethUnwindProbeTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    address private constant MAINNET_MORPHO = 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb;
    address private constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address private constant HGETH = 0xc824A08dB624942c5E5F330d56530cD1598859fD;
    address private constant RSETH_RATE_PROVIDER = 0x349A73444b1a310BAe67ef67973022020d70020d;
    address private constant BALANCER_V3_AGGREGATOR_ROUTER =
        0x309abcAeFa19CA6d34f0D8ff4a4103317c138657;
    address private constant BALANCER_RSETH_HGETH_POOL =
        0x6649a010CBcF5742E7a13a657Df358556b3e55cF;

    event LiquidationResult(
        uint256 seizedHgeth,
        uint256 repaidLoanAssets,
        uint256 loanBalanceSpent,
        uint256 hgethBalanceAfter
    );
    event HgethAccountingValue(
        address vaultAsset,
        uint256 previewRsEthOut,
        uint256 rsEthPrice,
        uint256 wethEquivalent,
        int256 profitBeforeGas
    );
    event BalancerHgethQuote(
        address router,
        address pool,
        uint256 hgethIn,
        uint256 rsEthOut,
        uint256 wethEquivalent,
        int256 profitBeforeGas
    );
    event BalancerQuoteFailed(address router, address pool, bytes reason);
    event HgethRedeemResult(uint256 sharesIn, uint256 assetsOut, uint256 assetBalanceDelta);
    event HgethRedeemFailed(uint256 sharesIn, bytes reason);

    error EmptyPosition(bytes32 marketId, address borrower);
    error UnexpectedCollateral(address actualCollateral);
    error UnexpectedLoanToken(address actualLoanToken);
    error LiquidationDidNotSeizeCollateral();
    error LiquidationDidNotRepay();
    error TheoreticalUnwindNotProfitable(uint256 wethEquivalent, uint256 repaidAssets);

    receive() external payable {}

    function test_full_liquidation_and_hgeth_theoretical_unwind() external {
        _selectFork();

        bytes32 marketId = vm.envBytes32("MORPHO_MARKET_ID");
        address borrower = vm.envAddress("MORPHO_BORROWER");

        IMorpho morpho = IMorpho(MAINNET_MORPHO);
        MarketParams memory marketParams = morpho.idToMarketParams(marketId);
        if (marketParams.loanToken != WETH) revert UnexpectedLoanToken(marketParams.loanToken);
        if (marketParams.collateralToken != HGETH) revert UnexpectedCollateral(marketParams.collateralToken);

        (, uint128 borrowShares, uint128 collateral) = morpho.position(marketId, borrower);
        if (borrowShares == 0 && collateral == 0) revert EmptyPosition(marketId, borrower);

        uint256 repaidShares = vm.envOr("MORPHO_REPAID_SHARES", uint256(borrowShares));
        uint256 loanTokenDeal = vm.envOr("MORPHO_LOAN_TOKEN_DEAL", uint256(1_000_000 ether));

        IERC20 loanToken = IERC20(marketParams.loanToken);
        IERC4626 hgeth = IERC4626(marketParams.collateralToken);

        vm.deal(address(this), loanTokenDeal);
        IWETH(marketParams.loanToken).deposit{value: loanTokenDeal}();
        loanToken.approve(MAINNET_MORPHO, type(uint256).max);

        uint256 loanBefore = loanToken.balanceOf(address(this));
        uint256 hgethBefore = hgeth.balanceOf(address(this));
        (uint256 seizedHgeth, uint256 repaidAssets) =
            morpho.liquidate(marketParams, borrower, 0, repaidShares, "");
        uint256 loanSpent = loanBefore - loanToken.balanceOf(address(this));
        uint256 hgethAfter = hgeth.balanceOf(address(this));

        if (seizedHgeth == 0 || hgethAfter <= hgethBefore) revert LiquidationDidNotSeizeCollateral();
        if (repaidAssets == 0 || loanSpent == 0) revert LiquidationDidNotRepay();

        emit LiquidationResult(seizedHgeth, repaidAssets, loanSpent, hgethAfter);

        address vaultAsset = hgeth.asset();
        uint256 previewRsEthOut = hgeth.previewRedeem(seizedHgeth);
        uint256 rsEthPrice = IRsEthRateProvider(RSETH_RATE_PROVIDER).rsETHPrice();
        uint256 wethEquivalent = previewRsEthOut * rsEthPrice / 1e18;
        int256 profitBeforeGas = int256(wethEquivalent) - int256(repaidAssets);

        emit HgethAccountingValue(
            vaultAsset, previewRsEthOut, rsEthPrice, wethEquivalent, profitBeforeGas
        );

        if (wethEquivalent <= repaidAssets) {
            revert TheoreticalUnwindNotProfitable(wethEquivalent, repaidAssets);
        }

        _quoteBalancerHgethToRsEth(hgeth, vaultAsset, seizedHgeth, rsEthPrice, repaidAssets);
        _tryRedeemHgeth(hgeth, vaultAsset, seizedHgeth);
    }

    function _selectFork() private {
        uint256 forkBlock = vm.envOr("MORPHO_FORK_BLOCK", uint256(0));
        if (forkBlock == 0) {
            vm.createSelectFork("mainnet");
        } else {
            vm.createSelectFork("mainnet", forkBlock);
        }
    }

    function _quoteBalancerHgethToRsEth(
        IERC4626 hgeth,
        address vaultAsset,
        uint256 hgethIn,
        uint256 rsEthPrice,
        uint256 repaidAssets
    ) private {
        address router = vm.envOr("BALANCER_V3_ROUTER", BALANCER_V3_AGGREGATOR_ROUTER);
        address pool = vm.envOr("HGETH_RSETH_POOL", BALANCER_RSETH_HGETH_POOL);
        if (router == address(0) || pool == address(0)) return;

        try IBalancerV3Router(router).querySwapSingleTokenExactIn(
            pool, IERC20(address(hgeth)), IERC20(vaultAsset), hgethIn, address(this), ""
        ) returns (uint256 rsEthOut) {
            uint256 wethEquivalent = rsEthOut * rsEthPrice / 1e18;
            emit BalancerHgethQuote(
                router,
                pool,
                hgethIn,
                rsEthOut,
                wethEquivalent,
                int256(wethEquivalent) - int256(repaidAssets)
            );
        } catch (bytes memory reason) {
            emit BalancerQuoteFailed(router, pool, reason);
        }
    }

    function _tryRedeemHgeth(IERC4626 hgeth, address vaultAsset, uint256 shares) private {
        uint256 assetBefore = IERC20(vaultAsset).balanceOf(address(this));

        try hgeth.redeem(shares, address(this), address(this)) returns (uint256 assetsOut) {
            uint256 assetAfter = IERC20(vaultAsset).balanceOf(address(this));
            emit HgethRedeemResult(shares, assetsOut, assetAfter - assetBefore);
        } catch (bytes memory reason) {
            emit HgethRedeemFailed(shares, reason);
        }
    }
}
