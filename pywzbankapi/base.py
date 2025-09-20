from __future__ import annotations

import json
from typing import Any, Dict, Optional

import requests
from loguru import logger


class WZBankError(Exception):
    """Base exception for WZBank client errors."""


class HTTPError(WZBankError):
    """Raised when HTTP status is not 2xx."""

    def __init__(self, status_code: int, body: Optional[str] = None):
        super().__init__(f"HTTP {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class SignatureError(WZBankError):
    """Raised when response signature verification fails."""


class DecryptError(WZBankError):
    """Raised when response bizContent decryption fails."""


class CryptoProvider:
    """Abstraction of SM2/SM4 operations used by the client.

    Provide concrete implementations that conform to these methods.

    Expected behaviors:
    - sign(data) -> returns signature text (DER hex or base64 as required by bank)
    - verify(data, signature) -> returns True if signature matches
    - encrypt(plaintext) -> returns hex string of SM4-encrypted ciphertext
    - decrypt(cipher_hex) -> returns plaintext bytes

    Note: Banks may require a specific JSON canonicalization for signing. This
    SDK builds the signature payload in a deterministic way; adapt verify/sign
    to match bank-side expectations if needed.
    """

    def __init__(
        self,
        sm2_private_key_pem: Optional[str] = None,
        sm2_bank_public_key_pem: Optional[str] = None,
        sm4_key_hex: Optional[str] = None,
        sm4_iv_hex: Optional[str] = None,
    ) -> None:
        self.sm2_private_key_pem = sm2_private_key_pem
        self.sm2_bank_public_key_pem = sm2_bank_public_key_pem
        self.sm4_key_hex = sm4_key_hex
        self.sm4_iv_hex = sm4_iv_hex

    # --- SM2 ---
    def sign(self, data: bytes) -> str:
        raise NotImplementedError("Provide SM2 sign implementation")

    def verify(self, data: bytes, signature: str) -> bool:
        raise NotImplementedError("Provide SM2 verify implementation")

    # --- SM4 ---
    def encrypt(self, plaintext: bytes) -> str:
        raise NotImplementedError("Provide SM4 encrypt implementation (return hex string)")

    def decrypt(self, cipher_hex: str) -> bytes:
        raise NotImplementedError("Provide SM4 decrypt implementation (accept hex string)")


class WZBankClient:
    """Wenzhou Bank Open Platform client (银企直连).

    Handles:
    - Biz JSON SM4 encryption into bizContent hex
    - SM2 signing of header+body canonical payload
    - HTTP POST and response parsing
    - Optional response signature verification and bizContent decryption
    """

    def __init__(
        self,
        app_id: str,
        bank_id: str = "WZB",
        base_url: str = "https://openapi.wzbank.cn/prdApiGW/",
        crypto: Optional[CryptoProvider] = None,
        sm2_private_key_pem: Optional[str] = None,
        sm2_bank_public_key_pem: Optional[str] = None,
        sm4_key_hex: Optional[str] = None,
        sm4_iv_hex: Optional[str] = None,
        timeout: int = 30,
        debug: bool = False,
    ) -> None:
        self.app_id = app_id
        self.bank_id = bank_id
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.debug = debug

        if crypto is None:
            crypto = CryptoProvider(
                sm2_private_key_pem=sm2_private_key_pem,
                sm2_bank_public_key_pem=sm2_bank_public_key_pem,
                sm4_key_hex=sm4_key_hex,
                sm4_iv_hex=sm4_iv_hex,
            )
        self.crypto = crypto

        self.session = requests.Session()

    # --- public high-level methods (endpoints can be built on top) ---
    def post(
        self,
        path: str,
        body: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        verify_response_signature: bool = True,
    ) -> Dict[str, Any]:
        """POST with required SM4/SM2 processing.

        - path: e.g., "V1/P01502/S01/queryeaccountbalance" (with or without leading slash)
        - body: dict of the clear JSON to encrypt as bizContent
        - headers: extra headers to include
        - verify_response_signature: verify bank signature if provided
        """
        if path.startswith("/"):
            path = path[1:]
        url = self.base_url + path

        # 1) Encrypt body to bizContent hex
        biz_hex = self._encrypt_body_to_biz(body)

        # 2) Build signature over canonical payload
        signature_payload = self._build_signature_payload(self.app_id, self.bank_id, biz_hex)
        signature = self.crypto.sign(signature_payload)

        # 3) Build headers and JSON body
        req_headers = self._build_headers(signature, headers)
        json_body = {"bizContent": biz_hex}

        if self.debug:
            logger.debug(
                {
                    "url": url,
                    "headers": {k: (v if k != "x-aob-signature" else "***masked***") for k, v in req_headers.items()},
                    "body": json_body,
                }
            )

        resp = self.session.post(url, headers=req_headers, json=json_body, timeout=self.timeout)
        if not (200 <= resp.status_code < 300):
            body_text = None
            try:
                body_text = resp.text
            except Exception:
                pass
            raise HTTPError(resp.status_code, body_text)

        # 4) Parse JSON body
        try:
            resp_json = resp.json()
        except ValueError as e:
            raise HTTPError(resp.status_code, f"Invalid JSON response: {resp.text}") from e

        # 5) Optional verify response signature
        bank_sig = resp.headers.get("x-aob-signature")
        if verify_response_signature and bank_sig:
            # Bank typically signs the response body. Use canonical JSON for verification.
            response_payload = self._canonical_json_bytes({"bizContent": resp_json.get("bizContent")})
            ok = False
            try:
                ok = self.crypto.verify(response_payload, bank_sig)
            except NotImplementedError:
                # If verify isn't implemented, skip but warn.
                logger.warning(
                    "CryptoProvider.verify not implemented; skipping response signature verification."
                )
                ok = True
            if not ok:
                raise SignatureError("Response signature verification failed")

        # 6) Decrypt bizContent
        biz_hex_resp = resp_json.get("bizContent")
        if biz_hex_resp is None:
            # Some endpoints might return raw JSON without encryption, but per spec it should be encrypted.
            if self.debug:
                logger.warning("No bizContent in response; returning original JSON body.")
            return resp_json  # fallback

        try:
            plaintext = self.crypto.decrypt(biz_hex_resp)
            data = json.loads(plaintext.decode("utf-8"))
        except NotImplementedError:
            raise DecryptError("CryptoProvider.decrypt not implemented; cannot decrypt bizContent")
        except Exception as e:
            raise DecryptError(f"Failed to decrypt/parse bizContent: {e}") from e

        if self.debug:
            logger.debug({"response": data})
        return data

    # --- convenience wrappers for documented endpoints (names mirror README) ---
    def query_account_balance(self, payAcctNo: str, **common: Any) -> Dict[str, Any]:
        """账户余额查询 (/V1/P01502/S01/queryeaccountbalance)

        必输: payAcctNo(账号)
        返回: payAcctBal, curCode, curType, startDate, endDate, otherInfo, payAcctNo, payAcctUseBal
        """
        if not payAcctNo:
            raise WZBankError("payAcctNo is required")
        body = {**self._common_body_defaults(), **common, "payAcctNo": payAcctNo}
        return self.post("V1/P01502/S01/queryeaccountbalance", body)

    def single_transfer(self, **kwargs: Any) -> Dict[str, Any]:
        """单笔转账 (/V1/P01506/S01/singletrans)

        必输: payAcctNo, transAmt, payAcctName, rcvAcctNo, rcvAcctName, inbankno,
             curCode(默认'1'), curType(默认'0'), orderNo, reserve2
        选填: inbankname, remark, reserve1
        返回: orderNo, bankSeqNo, workdate
        """
        required = [
            "payAcctNo",
            "transAmt",
            "payAcctName",
            "rcvAcctNo",
            "rcvAcctName",
            "inbankno",
            "orderNo",
            "reserve2",
        ]
        data = {**self._common_body_defaults(), **kwargs}
        for k in required:
            if not data.get(k):
                raise WZBankError(f"{k} is required")
        if "curCode" not in data or data.get("curCode") in (None, ""):
            data["curCode"] = "1"
        if "curType" not in data or data.get("curType") in (None, ""):
            data["curType"] = "0"
        body = data
        return self.post("V1/P01506/S01/singletrans", body)

    def query_single_transfer_result(self, **kwargs: Any) -> Dict[str, Any]:
        body = {**self._common_body_defaults(), **kwargs}
        return self.post("V1/P01507/S01/selsingletrans", body)

    def batch_transfer(self, **kwargs: Any) -> Dict[str, Any]:
        body = {**self._common_body_defaults(), **kwargs}
        return self.post("V1/P01508/S01/batchtrans", body)

    def query_batch_transfer_result(
        self, payAcctNo: str, batchNo: str, **common: Any
    ) -> Dict[str, Any]:
        body = {**self._common_body_defaults(), **common, "payAcctNo": payAcctNo, "batchNo": batchNo}
        return self.post("V1/P01509/S01/selbatchtrans", body)

    def query_hour_details(
        self, payAcctNo: str, startDate: str, endDate: str, **common: Any
    ) -> Dict[str, Any]:
        body = {
            **self._common_body_defaults(),
            **common,
            "payAcctNo": payAcctNo,
            "startDate": startDate,
            "endDate": endDate,
        }
        return self.post("V1/P01512/S01/queryhourdetails", body)

    def download_details_receipt(
        self,
        acctNo: str,
        transDate: str,
        transSeqno: str,
        transOperNo: Optional[str] = None,
        transBrno: Optional[str] = None,
        **common: Any,
    ) -> Dict[str, Any]:
        body = {
            **self._common_body_defaults(),
            **common,
            "acctNo": acctNo,
            "transDate": transDate,
            "transSeqno": transSeqno,
        }
        if transOperNo is not None:
            body["transOperNo"] = transOperNo
        if transBrno is not None:
            body["transBrno"] = transBrno
        return self.post("V1/P01513/S01/detailsreceipt", body)

    def check_account(self, payAcctNo: str, startDate: str, endDate: str, **common: Any) -> Dict[str, Any]:
        body = {**self._common_body_defaults(), **common, "payAcctNo": payAcctNo, "startDate": startDate, "endDate": endDate}
        return self.post("V1/P01518/S01/checkAcct", body)

    def update_check_result(self, **kwargs: Any) -> Dict[str, Any]:
        body = {**self._common_body_defaults(), **kwargs}
        return self.post("V1/P01519/S01/checkResultUpdate", body)

    def query_subacct_balance(self, payAcctNo: str, **common: Any) -> Dict[str, Any]:
        body = {**self._common_body_defaults(), **common, "payAcctNo": payAcctNo}
        return self.post("V1/P01520/S01/queryeSubacctBalance", body)

    def query_hour_details2(self, payAcctNo: str, startDate: str, endDate: str, **common: Any) -> Dict[str, Any]:
        body = {**self._common_body_defaults(), **common, "payAcctNo": payAcctNo, "startDate": startDate, "endDate": endDate}
        return self.post("V1/P01522/S01/queryhourdetails2", body)

    def query_receipt_details(self, **kwargs: Any) -> Dict[str, Any]:
        body = {**self._common_body_defaults(), **kwargs}
        return self.post("V1/P01523/S01/queryreceiptdetails", body)

    def query_bank_infos(
        self, type: str, bankName: Optional[str] = None, bankNo: Optional[str] = None, **common: Any
    ) -> Dict[str, Any]:
        body = {**self._common_body_defaults(), **common, "type": type}
        if type == "0":
            if not bankName:
                raise WZBankError("type=0 requires bankName")
            body["bankName"] = bankName
        elif type == "1":
            if not bankNo:
                raise WZBankError("type=1 requires bankNo")
            body["bankNo"] = bankNo
        return self.post("V1/P01524/S01/querybankinfos", body)

    def query_cert_expiry(self, payAcctNo: str, **common: Any) -> Dict[str, Any]:
        body = {**self._common_body_defaults(), **common, "payAcctNo": payAcctNo}
        return self.post("V1/P01525/S01/queryCertExpiry", body)

    # --- internal helpers ---
    def _common_body_defaults(self) -> Dict[str, Any]:
        # Caller should supply real mesgId/mesgDate/mesgTime if needed.
        return {}

    def _encrypt_body_to_biz(self, body: Dict[str, Any]) -> str:
        try:
            plaintext = self._canonical_json_bytes(body)
            return self.crypto.encrypt(plaintext)
        except NotImplementedError:
            raise DecryptError("CryptoProvider.encrypt not implemented; cannot encrypt request body")

    def _build_signature_payload(self, app_id: str, bank_id: str, biz_hex: str) -> bytes:
        # Keep key order as specified by the bank documentation.
        payload = {
            "x-aob-appID": app_id,
            "x-aob-bankID": bank_id,
            "bizContent": biz_hex,
        }
        return self._canonical_json_bytes(payload)

    def _build_headers(self, signature: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-aob-appID": self.app_id,
            "x-aob-bankID": self.bank_id,
            "x-aob-signature": signature,
        }
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _canonical_json_bytes(obj: Dict[str, Any]) -> bytes:
        # Use separators to avoid spaces; keep insertion order for dict
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
