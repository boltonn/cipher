"""Vendored crypto-address checksum validation.

Reference implementations only -- base58check (BIP-13), bech32 / bech32m
(BIP-173 / BIP-350), EIP-55 keccak, and CryptoNote base58 for Monero. No
crypto-address library; Keccak-256 comes from pycryptodome.
"""

import hashlib
from dataclasses import dataclass

from Crypto.Hash import keccak as _keccak


def _keccak256(data: bytes) -> bytes:
    return _keccak.new(digest_bits=256, data=data).digest()


_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(_B58_ALPHABET)}
_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_CN_FULL_BLOCK_SIZE = 8
_CN_ENCODED_BLOCK_SIZES = (0, 2, 3, 5, 6, 7, 9, 10, 11)


class CryptoInvalid(Exception):
    """The address does not pass its checksum / structural rules."""


@dataclass(frozen=True, slots=True)
class CryptoInfo:
    currency: str
    network: str
    address_format: str


def _b58_decode(value: str) -> bytes:
    num = 0
    for ch in value:
        idx = _B58_INDEX.get(ch)
        if idx is None:
            raise CryptoInvalid(f"bad base58 char {ch!r}")
        num = num * 58 + idx
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    pad = len(value) - len(value.lstrip("1"))
    return b"\x00" * pad + raw


def _b58check_payload(value: str) -> bytes:
    data = _b58_decode(value)
    if len(data) < 5:
        raise CryptoInvalid("base58check too short")
    payload, checksum = data[:-4], data[-4:]
    if hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] != checksum:
        raise CryptoInvalid("base58check checksum mismatch")
    return payload


def _bech32_polymod(values: list[int]) -> int:
    generator = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i in range(5):
            chk ^= generator[i] if ((top >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_verify(hrp: str, data: list[int]) -> str | None:
    const = _bech32_polymod(_bech32_hrp_expand(hrp) + data)
    if const == 1:
        return "bech32"
    if const == 0x2BC830A3:
        return "bech32m"
    return None


def _validate_btc_bech32(value: str) -> CryptoInfo:
    lowered = value.lower()
    if lowered != value and value.upper() != value:
        raise CryptoInvalid("mixed-case bech32")
    pos = lowered.rfind("1")
    hrp, data_part = lowered[:pos], lowered[pos + 1 :]
    if hrp not in ("bc", "tb") or len(data_part) < 6:
        raise CryptoInvalid("bad bech32 hrp")
    try:
        data = [_BECH32_CHARSET.index(c) for c in data_part]
    except ValueError as exc:
        raise CryptoInvalid("bad bech32 char") from exc
    spec = _bech32_verify(hrp, data)
    if spec is None:
        raise CryptoInvalid("bech32 checksum mismatch")
    witver = data[0]
    if witver == 0 and spec != "bech32":
        raise CryptoInvalid("v0 must be bech32")
    if witver != 0 and spec != "bech32m":
        raise CryptoInvalid("v1+ must be bech32m")
    return CryptoInfo("BTC", "bitcoin", spec)


def _validate_btc_base58(value: str) -> CryptoInfo:
    payload = _b58check_payload(value)
    version = payload[0]
    if version == 0x00:
        return CryptoInfo("BTC", "bitcoin", "p2pkh")
    if version == 0x05:
        return CryptoInfo("BTC", "bitcoin", "p2sh")
    raise CryptoInvalid(f"unknown BTC version byte {version:#x}")


def _validate_tron(value: str) -> CryptoInfo:
    payload = _b58check_payload(value)
    if payload[0] != 0x41 or len(payload) != 21:
        raise CryptoInvalid("bad TRON payload")
    return CryptoInfo("TRX", "tron", "base58check")


def _validate_eth(value: str) -> CryptoInfo:
    body = value[2:]
    if len(body) != 40:
        raise CryptoInvalid("bad ETH length")
    if body == body.lower() or body == body.upper():
        return CryptoInfo("ETH", "evm", "hex")
    digest = _keccak256(body.lower().encode()).hex()
    for ch, dg in zip(body, digest[:40], strict=True):
        if ch.isalpha() and (ch.isupper() != (int(dg, 16) >= 8)):
            raise CryptoInvalid("EIP-55 checksum mismatch")
    return CryptoInfo("ETH", "evm", "eip55")


def _cn_b58_decode_block(data: str) -> bytes:
    num = 0
    for ch in data:
        idx = _B58_INDEX.get(ch)
        if idx is None:
            raise CryptoInvalid("bad monero base58 char")
        num = num * 58 + idx
    size = _CN_ENCODED_BLOCK_SIZES.index(len(data))
    out = num.to_bytes(_CN_FULL_BLOCK_SIZE, "big")[-size:] if size else b""
    if int.from_bytes(out, "big") != num and size:
        raise CryptoInvalid("monero base58 overflow")
    return out


def _cn_b58_decode(value: str) -> bytes:
    full, tail = divmod(len(value), 11)
    result = b""
    for i in range(full):
        result += _cn_b58_decode_block(value[i * 11 : i * 11 + 11]).rjust(_CN_FULL_BLOCK_SIZE, b"\x00")
    if tail:
        result += _cn_b58_decode_block(value[full * 11 :])
    return result


def _validate_xmr(value: str) -> CryptoInfo:
    if len(value) not in (95, 106):
        raise CryptoInvalid("bad XMR length")
    raw = _cn_b58_decode(value)
    if len(raw) < 5:
        raise CryptoInvalid("XMR too short")
    payload, checksum = raw[:-4], raw[-4:]
    if _keccak256(payload)[:4] != checksum:
        raise CryptoInvalid("XMR checksum mismatch")
    return CryptoInfo("XMR", "monero", "monero")


def identify_crypto(value: str) -> CryptoInfo:
    """Validate a crypto address and return its currency / network / format, else raise."""
    if value.startswith("0x") or value.startswith("0X"):
        return _validate_eth(value)
    if value.lower().startswith(("bc1", "tb1")):
        return _validate_btc_bech32(value)
    if value.startswith("T") and 30 < len(value) < 40:
        return _validate_tron(value)
    if value.startswith(("1", "3")):
        return _validate_btc_base58(value)
    if value.startswith("4") or value.startswith("8"):
        return _validate_xmr(value)
    raise CryptoInvalid("unrecognised crypto address shape")
