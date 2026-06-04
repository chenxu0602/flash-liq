from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

MORPHO_BLUE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
IS_AUTHORIZED_SELECTOR = "0x65e4ad9e"
LIQUIDATE_TOPIC = "0xa4946ede45d0c6f06a0f5ce92c9ad3b4751452d2fe0e25010783bcab57a67e41"


class RpcError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthorizationCheck:
    authorizer: str
    authorizee: str
    authorized: bool


def check_morpho_authorization(
    *,
    rpc_url: str,
    authorizer: str,
    authorizee: str,
    morpho_address: str = MORPHO_BLUE,
    timeout: float = 30.0,
) -> AuthorizationCheck:
    result = eth_call(
        rpc_url=rpc_url,
        to=morpho_address,
        data=encode_is_authorized_call(authorizer, authorizee),
        timeout=timeout,
    )
    return AuthorizationCheck(
        authorizer=authorizer,
        authorizee=authorizee,
        authorized=decode_bool_result(result),
    )


def rpc_request(*, rpc_url: str, method: str, params: list[Any], timeout: float = 30.0) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    request = urllib.request.Request(
        rpc_url,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = sanitize_rpc_error_body(exc)
        raise RpcError(
            f"RPC HTTP error {exc.code}; check RPC connectivity and credentials" + detail
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RpcError("RPC request failed; check RPC connectivity and credentials") from exc
    except json.JSONDecodeError as exc:
        raise RpcError("RPC returned invalid JSON") from exc

    error = response_payload.get("error")
    if error is not None:
        raise RpcError(f"RPC {method} error: " + sanitize_rpc_error(error))

    if "result" not in response_payload:
        raise RpcError(f"RPC {method} returned no result")
    return response_payload["result"]


def eth_call(*, rpc_url: str, to: str, data: str, timeout: float) -> str:
    result = rpc_request(
        rpc_url=rpc_url,
        method="eth_call",
        params=[{"to": normalize_address(to), "data": data}, "latest"],
        timeout=timeout,
    )
    if not isinstance(result, str):
        raise RpcError("RPC eth_call returned no result")
    return result


def eth_block_number(*, rpc_url: str, timeout: float = 30.0) -> int:
    result = rpc_request(rpc_url=rpc_url, method="eth_blockNumber", params=[], timeout=timeout)
    if not isinstance(result, str):
        raise RpcError("RPC eth_blockNumber returned malformed result")
    return hex_to_int(result)


def eth_get_logs(
    *,
    rpc_url: str,
    address: str,
    from_block: int,
    to_block: int,
    topics: list[str | list[str] | None],
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    result = rpc_request(
        rpc_url=rpc_url,
        method="eth_getLogs",
        params=[
            {
                "address": normalize_address(address),
                "fromBlock": hex(from_block),
                "toBlock": hex(to_block),
                "topics": topics,
            }
        ],
        timeout=timeout,
    )
    if not isinstance(result, list):
        raise RpcError("RPC eth_getLogs returned malformed result")
    return [item for item in result if isinstance(item, dict)]


def encode_is_authorized_call(authorizer: str, authorizee: str) -> str:
    return (
        IS_AUTHORIZED_SELECTOR
        + encode_address_argument(authorizer)
        + encode_address_argument(authorizee)
    )


def encode_address_argument(address: str) -> str:
    normalized = normalize_address(address)
    return normalized[2:].rjust(64, "0")


def decode_bool_result(result: str) -> bool:
    if not isinstance(result, str) or not result.startswith("0x"):
        raise RpcError("RPC eth_call returned malformed bool result")
    value = result[2:].rjust(64, "0")
    if len(value) != 64:
        raise RpcError("RPC eth_call returned malformed bool result")
    decoded = int(value, 16)
    if decoded not in {0, 1}:
        raise RpcError("RPC eth_call returned non-bool result")
    return decoded == 1


def hex_to_int(value: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise RpcError("Malformed hex quantity")
    return int(value, 16)


def normalize_address(address: str) -> str:
    if not isinstance(address, str):
        raise RpcError("Address must be a string")
    value = address.strip()
    if value.startswith("0x"):
        value = value[2:]
    if len(value) != 40 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise RpcError("Invalid EVM address")
    return "0x" + value


def sanitize_rpc_error(error: Any) -> str:
    if isinstance(error, dict):
        message = str(error.get("message") or error.get("code") or "unknown error")
    else:
        message = str(error)
    return message.replace("\n", " ")[:240]


def sanitize_rpc_error_body(exc: urllib.error.HTTPError) -> str:
    body = exc.read().decode(errors="replace")
    if not body:
        return ""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return ": " + body.replace("\n", " ")[:240]

    error = payload.get("error") if isinstance(payload, dict) else None
    if error is None:
        return ""
    return ": " + sanitize_rpc_error(error)
