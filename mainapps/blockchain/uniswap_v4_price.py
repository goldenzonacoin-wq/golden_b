from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext

from django.conf import settings
from eth_abi import encode
from web3 import Web3

getcontext().prec = 80

POSITION_MANAGER_ABI = [
    {
        "name": "getPoolAndPositionInfo",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [
            {
                "name": "poolKey",
                "type": "tuple",
                "components": [
                    {"name": "currency0", "type": "address"},
                    {"name": "currency1", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "tickSpacing", "type": "int24"},
                    {"name": "hooks", "type": "address"},
                ],
            },
            {"name": "info", "type": "uint256"},
        ],
    }
]

STATE_VIEW_ABI = [
    {
        "name": "getSlot0",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "poolId", "type": "bytes32"}],
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "protocolFee", "type": "uint24"},
            {"name": "lpFee", "type": "uint24"},
        ],
    }
]

DEFAULT_V4_DEPLOYMENTS = {
    137: {
        "position_manager": "0x1ec2ebf4f37e7363fdfe3551602425af0b3ceef9",
        "state_view": "0x5ea1bd7974c8a611cbab0bdcafcb1d9cc9b3ba5a",
    }
}


class UniswapV4PriceError(Exception):
    """Raised when a live Uniswap v4 price cannot be resolved."""


@dataclass(frozen=True)
class UniswapV4PriceSnapshot:
    token_price_usd: Decimal
    quote_symbol: str
    fee: int
    tick_spacing: int
    pool_id: str


def _get_chain_default(chain_id: int, field: str) -> str | None:
    deployment = DEFAULT_V4_DEPLOYMENTS.get(chain_id, {})
    return deployment.get(field)


def get_live_uniswap_v4_price() -> UniswapV4PriceSnapshot:
    rpc_url = getattr(settings, "KYC_PAYMENT_RPC_URL", None) or getattr(settings, "ETHEREUM_RPC_URL", None)
    if not rpc_url:
        raise UniswapV4PriceError("Polygon RPC URL is not configured.")

    try:
        chain_id = int(getattr(settings, "KYC_PAYMENT_CHAIN_ID", "137"))
    except (TypeError, ValueError) as exc:
        raise UniswapV4PriceError("KYC payment chain ID is invalid.") from exc

    position_token_id = getattr(settings, "UNISWAP_V4_POSITION_TOKEN_ID", None)
    if not position_token_id:
        raise UniswapV4PriceError("UNISWAP_V4_POSITION_TOKEN_ID is not configured.")

    try:
        position_token_id = int(position_token_id)
    except (TypeError, ValueError) as exc:
        raise UniswapV4PriceError("UNISWAP_V4_POSITION_TOKEN_ID must be an integer.") from exc

    token_address = getattr(settings, "KYC_PAYMENT_TOKEN_ADDRESS", None) or getattr(settings, "TOKEN_CONTRACT_ADDRESS", None)
    if not token_address or not Web3.is_address(token_address):
        raise UniswapV4PriceError("The payment token address is not configured correctly.")

    quote_token_address = getattr(settings, "UNISWAP_V4_QUOTE_TOKEN_ADDRESS", None)
    if not quote_token_address or not Web3.is_address(quote_token_address):
        raise UniswapV4PriceError("UNISWAP_V4_QUOTE_TOKEN_ADDRESS is not configured correctly.")

    try:
        token_decimals = int(getattr(settings, "KYC_PAYMENT_TOKEN_DECIMALS", "18"))
        quote_token_decimals = int(getattr(settings, "UNISWAP_V4_QUOTE_TOKEN_DECIMALS", "6"))
    except (TypeError, ValueError) as exc:
        raise UniswapV4PriceError("Token decimals configuration is invalid.") from exc

    position_manager_address = (
        getattr(settings, "UNISWAP_V4_POSITION_MANAGER_ADDRESS", None)
        or _get_chain_default(chain_id, "position_manager")
    )
    state_view_address = (
        getattr(settings, "UNISWAP_V4_STATE_VIEW_ADDRESS", None)
        or _get_chain_default(chain_id, "state_view")
    )
    if not position_manager_address or not Web3.is_address(position_manager_address):
        raise UniswapV4PriceError("Uniswap v4 PositionManager address is not configured correctly.")
    if not state_view_address or not Web3.is_address(state_view_address):
        raise UniswapV4PriceError("Uniswap v4 StateView address is not configured correctly.")

    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if not web3.is_connected():
        raise UniswapV4PriceError("Unable to connect to the configured Polygon RPC endpoint.")

    position_manager = web3.eth.contract(
        address=Web3.to_checksum_address(position_manager_address),
        abi=POSITION_MANAGER_ABI,
    )
    state_view = web3.eth.contract(
        address=Web3.to_checksum_address(state_view_address),
        abi=STATE_VIEW_ABI,
    )

    try:
        pool_key, _ = position_manager.functions.getPoolAndPositionInfo(position_token_id).call()
    except Exception as exc:  # noqa: BLE001
        raise UniswapV4PriceError("Unable to read Uniswap pool metadata from the position NFT.") from exc

    currency0, currency1, fee, tick_spacing, hooks = pool_key
    token_checksum = Web3.to_checksum_address(token_address)
    quote_checksum = Web3.to_checksum_address(quote_token_address)
    currencies = {
        Web3.to_checksum_address(currency0).lower(),
        Web3.to_checksum_address(currency1).lower(),
    }
    if token_checksum.lower() not in currencies or quote_checksum.lower() not in currencies:
        raise UniswapV4PriceError("The configured Uniswap v4 position does not match the token/quote pair.")

    try:
        encoded_pool_key = encode(
            ["address", "address", "uint24", "int24", "address"],
            [currency0, currency1, fee, tick_spacing, hooks],
        )
        pool_id = web3.keccak(encoded_pool_key)
    except Exception as exc:  # noqa: BLE001
        raise UniswapV4PriceError("Unable to derive the Uniswap v4 pool ID.") from exc

    try:
        sqrt_price_x96, _tick, _protocol_fee, _lp_fee = state_view.functions.getSlot0(pool_id).call()
    except Exception as exc:  # noqa: BLE001
        raise UniswapV4PriceError("Unable to read live Uniswap v4 pool state.") from exc

    currency0_checksum = Web3.to_checksum_address(currency0)
    currency1_checksum = Web3.to_checksum_address(currency1)
    if currency0_checksum.lower() == token_checksum.lower():
        currency0_decimals = token_decimals
        currency1_decimals = quote_token_decimals
    elif currency0_checksum.lower() == quote_checksum.lower():
        currency0_decimals = quote_token_decimals
        currency1_decimals = token_decimals
    else:
        raise UniswapV4PriceError("Unexpected token ordering returned by the Uniswap v4 position.")

    sqrt_price = Decimal(sqrt_price_x96)
    raw_ratio = (sqrt_price / Decimal(2**96)) ** 2
    decimals_adjustment = Decimal(10) ** (currency0_decimals - currency1_decimals)
    human_token1_per_token0 = raw_ratio * decimals_adjustment

    if currency0_checksum.lower() == token_checksum.lower() and currency1_checksum.lower() == quote_checksum.lower():
        token_price_in_quote = human_token1_per_token0
    elif currency0_checksum.lower() == quote_checksum.lower() and currency1_checksum.lower() == token_checksum.lower():
        if human_token1_per_token0 == 0:
            raise UniswapV4PriceError("The Uniswap pool returned a zero price.")
        token_price_in_quote = Decimal(1) / human_token1_per_token0
    else:
        raise UniswapV4PriceError("Unexpected token ordering returned by the Uniswap v4 position.")

    if token_price_in_quote <= 0:
        raise UniswapV4PriceError("The Uniswap pool returned an invalid token price.")

    return UniswapV4PriceSnapshot(
        token_price_usd=token_price_in_quote.quantize(Decimal("0.00000001")),
        quote_symbol=getattr(settings, "UNISWAP_V4_QUOTE_TOKEN_SYMBOL", "USDC"),
        fee=int(fee),
        tick_spacing=int(tick_spacing),
        pool_id=pool_id.hex(),
    )
