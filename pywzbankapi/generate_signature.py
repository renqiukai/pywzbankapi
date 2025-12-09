"""
Generate x-aob-signature 和 bizContent（完全复刻 ApiGateway2.java / SMHelper.sign），只计算不发请求。

依赖：`python3 -m venv .venv && .venv/bin/pip install gmssl`
运行：`.venv/bin/python generate_signature.py`
"""

import json
import os
from binascii import unhexlify
from collections import OrderedDict
import random

from gmssl import sm2, sm3, sm4


USER_ID = b"1234567812345678"  # Java SM2.signWithEncode 默认ID

# SM2 标准曲线参数（与 BouncyCastle 默认一致）
SM2_A = "FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC"
SM2_B = "28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93"
SM2_G = (
    "32c4ae2c1f1981195f9904466a39c9948fe30bbff2660be1715a4589334c74c7"
    "bc3736a2f4f6779c59bdcee36b692153d0a9877cc62a474002df32e52139f0a0"
)


def sm3_digest(data: bytes) -> str:
    return sm3.sm3_hash(list(data)).upper()


def sm2_za(public_key_hex: str, user_id: bytes = USER_ID) -> bytes:
    """计算 SM2 ZA = SM3(ENTL || ID || a || b || Gx || Gy || Px || Py)"""
    if public_key_hex.startswith("04"):
        public_key_hex = public_key_hex[2:]
    px_hex, py_hex = public_key_hex[:64], public_key_hex[64:]
    entl = (len(user_id) * 8).to_bytes(2, byteorder="big")
    msg = b"".join(
        [
            entl,
            user_id,
            unhexlify(SM2_A),
            unhexlify(SM2_B),
            unhexlify(SM2_G[:64]),
            unhexlify(SM2_G[64:]),
            unhexlify(px_hex),
            unhexlify(py_hex),
        ]
    )
    return unhexlify(sm3_digest(msg))


def encrypt_biz_content(
    body: OrderedDict, SM4_KEY: bytes, SM4_IV: bytes
) -> OrderedDict:
    """
    等价 SMHelper.encrypt(StringUtil.writeJsonObject(body), SM4Key, SM4Iv)
    -> SM4/CBC/PKCS5Padding（gmssl CryptSM4.crypt_cbc 内置补码），输出大写16进制。
    """
    cipher = sm4.CryptSM4()
    cipher.set_key(SM4_KEY, sm4.SM4_ENCRYPT)
    plaintext = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    encrypted = cipher.crypt_cbc(SM4_IV, plaintext)
    return OrderedDict(bizContent=encrypted.hex().upper())


def decrypt_biz_content(biz_content: str, SM4_KEY: bytes, SM4_IV: bytes) -> OrderedDict:
    """
    等价 SMHelper.decrypt(bizContent, SM4Key, SM4Iv)
    -> SM4/CBC/PKCS5Padding（gmssl CryptSM4.crypt_cbc 内置补码），输入大写16进制。
    """
    cipher = sm4.CryptSM4()
    cipher.set_key(SM4_KEY, sm4.SM4_DECRYPT)
    encrypted_bytes = unhexlify(biz_content)
    decrypted = cipher.crypt_cbc(SM4_IV, encrypted_bytes)
    decrypted_json = json.loads(decrypted.decode("utf-8"))
    return OrderedDict(decrypted_json)


def build_sign_map(headers: dict, biz_content: OrderedDict) -> OrderedDict:
    sign_fields = [
        "Authorization",
        "x-aob-appID",
        "x-aob-bankID",
        "x-aob-customer-last-logger-time",
        "x-aob-customer-ip-address",
        "x-aob-interaction-id",
        "x-aob-access-token",
        "x-customer-user-agent",
        "x-idempotency-key",
    ]
    sign_map = OrderedDict()
    for key in sign_fields:
        value = headers.get(key)
        if value:
            sign_map[key] = value
    if biz_content:
        sign_map.update(biz_content)
    return sign_map


def sign_payload(sign_map: OrderedDict, PRIVATE_KEY: str) -> str:
    # 与 Java 的 StringUtil.writeJsonObject 一致：UTF-8，无空格，保持键顺序
    sign_string = json.dumps(sign_map, ensure_ascii=False, separators=(",", ":"))

    # SM2 签名前置哈希：SM3(ZA || sign_string)
    public_key = get_public_key_from_private(PRIVATE_KEY)
    za = sm2_za(public_key, USER_ID)
    e_hex = sm3_digest(za + sign_string.encode("utf-8"))

    sm2_crypt = sm2.CryptSM2(private_key=PRIVATE_KEY, public_key=public_key, asn1=True)
    n_int = int(sm2.default_ecc_table["n"], 16)
    k_int = random.randrange(1, n_int)  # 与 Java SecureRandom 一致的区间 [1, n-1]
    random_hex_str = f"{k_int:064x}"
    signature_der = sm2_crypt.sign(unhexlify(e_hex), random_hex_str)
    return signature_der.upper()


def get_public_key_from_private(PRIVATE_KEY: str) -> str:
    """Derive uncompressed public key (hex, with 04 prefix) from the private key, matching SMHelper.generatePubKeyByPriKey."""
    crypt = sm2.CryptSM2(private_key=PRIVATE_KEY, public_key="", asn1=False)
    pub_no_prefix = crypt._kg(int(PRIVATE_KEY, 16), sm2.default_ecc_table["g"])
    return "04" + pub_no_prefix


def main():
    APP_ID = "bb800191-782c-41bc-920e-62f396008264"
    PRIVATE_KEY = "bf5e4387c88b536c203d3893a2f7fceeb2badcb6eb9e1e331197caf9372a335e"
    SM4_KEY = bytes.fromhex("2ABDBED2A873B983148F922CFA238205")
    SM4_IV = bytes.fromhex("F336C87E2373A3C792E59DBF23771BCD")
    path = "/V1/P01502/S01/queryeaccountbalance"
    headers = OrderedDict()
    headers["x-aob-bankID"] = "WZB"
    headers["x-aob-appID"] = APP_ID

    body = OrderedDict()
    body["payAcctNo"] = "733000120190056868"
    body["mesgId"] = "318e8a918a184db9838f6700ad42f701"
    body["mesgDate"] = "20251202"
    body["mesgTime"] = "110608000"

    biz_content = encrypt_biz_content(body, SM4_KEY, SM4_IV)
    content = decrypt_biz_content(
        biz_content["bizContent"], SM4_KEY, SM4_IV
    )  # 测试解密正确性
    sign_map = build_sign_map(headers, biz_content)
    signature = sign_payload(sign_map, PRIVATE_KEY)
    headers["x-aob-signature"] = signature

    print(f"Derived public key: {get_public_key_from_private(PRIVATE_KEY)}")
    print(f"Path: {path}")
    print(f"Headers: {headers}")
    print(f"Body (plain): {body}")
    print(f"Body (encrypted bizContent): {biz_content}")
    print(f"Decrypted bizContent: {content}")


if __name__ == "__main__":
    main()
