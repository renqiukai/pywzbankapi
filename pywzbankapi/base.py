from datetime import datetime
import json
from uuid import uuid4
import os
import requests
from loguru import logger
from .generate_signature import (
    encrypt_biz_content,
    build_sign_map,
    sign_payload,
    decrypt_biz_content,
)


def get_mesg_id():
    return str(uuid4()).replace("-", "")[:32]


def get_mesg_date():
    return datetime.now().strftime("%Y%m%d")


def get_mesg_time():
    return datetime.now().strftime("%H%M%S000")


class Base:

    def __init__(self, debug=False):

        private_key = "bf5e4387c88b536c203d3893a2f7fceeb2badcb6eb9e1e331197caf9372a335e"

        test_host = "https://zhihuitest.wzbank.cn/indApp/apiGateway"
        prod_host = "https://openapi.wzbank.cn/prdApiGW"

        self.host = test_host if debug else prod_host
        self.privateKey = private_key
        self.SM4Key = bytes.fromhex("2ABDBED2A873B983148F922CFA238205")
        self.SM4Iv = bytes.fromhex("F336C87E2373A3C792E59DBF23771BCD")

        self.appId = "bb800191-782c-41bc-920e-62f396008264"

    def request(
        self,
        endpoint: str,
        headers: dict,
        json_data: dict,
        method: str = "POST",
    ):
        url = f"{self.host}{endpoint}"
        headers = {
            "x-aob-appID": self.appId,
            "x-aob-bankID": "WZB",
            **headers,
        }

        json_data = {
            **json_data,
            "mesgId": get_mesg_id(),
            "mesgDate": get_mesg_date(),
            "mesgTime": get_mesg_time(),
        }
        logger.debug(
            {
                "msg": "请求信息",
                "接口地址": url,
                "请求头": headers,
                "请求体（加密前）": json_data,
            }
        )
        biz_content = encrypt_biz_content(json_data, self.SM4Key, self.SM4Iv)
        logger.debug({"msg": "SM4加密请求体", "请求体（加密后）": biz_content})
        sign_map = build_sign_map(headers, biz_content)
        signature = sign_payload(sign_map, self.privateKey)
        logger.debug({"msg": "请求签名", "sign": signature, "长度": len(signature)})
        headers["x-aob-signature"] = signature
        logger.debug({"msg": "请求完整内容", "headers": headers, "json": biz_content})
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=biz_content,
        )
        return self.response(response)

    def response(self, response: requests.Response):
        status_code = response.status_code
        if status_code != 200:
            logger.error(
                {
                    "msg": "请求失败",
                    "状态码": response.status_code,
                    "响应头": dict(response.headers),
                    "响应体": response.text,
                }
            )
            return
        response_json = response.json()
        biz_content_encrypted = response_json.get("bizContent", "")
        logger.debug(
            {"msg": "SM4加密响应体", "响应体（加密后）": biz_content_encrypted}
        )
        biz_content_decrypted = decrypt_biz_content(
            biz_content_encrypted, self.SM4Key, self.SM4Iv
        )
        logger.debug(
            {"msg": "SM4解密响应体", "响应体（解密后）": biz_content_decrypted}
        )
        return biz_content_decrypted

    def queryeaccountbalance(self, payAcctNo: str):
        """
        3.1.	账户余额查询接口
        """
        endpoint = "/V1/P01502/S01/queryeaccountbalance"
        data = {
            "payAcctNo": payAcctNo,
        }
        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def singletrans(
        self,
        payAcctNo: str,
        transAmt: str,
        payAcctName: str,
        rcvAcctNo: str,
        rcvAcctName: str,
        orderNo: str,
        inbankno: str,
        inbankname: str | None = None,
        curCode: str = "1",
        curType: str = "0",
        remark: str | None = None,
    ):
        """
        3.2.	银企直连单笔转账交易
        payAcctNo	Max32Text	付款账号	是	银企直连签约账号
        transAmt	Max32Text	交易金额	是	保留小数点后两位
        payAcctName	Max64Text	付款账号名称	是
        rcvAcctNo	Max32Text	收款账号	是
        rcvAcctName	Max64Text	收款户名	是
        inbankname	Max30Text	 入账总银行名称	否
        inbankno	Max30Text	 入账总银行行号	是
        curCode	Max1Text	交易货币代码	是	默认传1
        curType	Max1Text	钞汇类别	是	默认传0
        remark	Max64Text	摘要	否
        orderNo	Max30Text	发起方唯一业务标识	是

        """
        endpoint = "/V1/P01506/S01/singletrans"
        data = {
            "payAcctNo": payAcctNo,
            "transAmt": transAmt,
            "payAcctName": payAcctName,
            "rcvAcctNo": rcvAcctNo,
            "rcvAcctName": rcvAcctName,
            "orderNo": orderNo,
            "inbankno": inbankno,
            "curCode": curCode,
            "curType": curType,
        }
        if remark:
            data["remark"] = remark
        if inbankname:
            data["inbankname"] = inbankname
        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def selsingletrans(
        self,
        busCode: str,
        payAcctNo: str,
        startDate: str,
        bankSeqNo: str | None = None,
        orderNo: str | None = None,
    ):
        """
        3.3.	银企直连单笔转账结果查询交易
        busCode	Max1Text	功能码	是	1：通过交易流水查询 2：通过订单号查询
        payAcctNo	Max32Text	付款账号	是
        startDate	Max11Text	查询日期	是
        bankSeqNo	Max32Text	流水号	否	根据功能码选择上传对应字段
        orderNo	Max30Text	订单号	否	根据功能码选择上传对应字段
        """
        endpoint = "/V1/P01507/S01/selsingletrans"
        if busCode == "1" and not bankSeqNo:
            raise ValueError("busCode为1时，bankSeqNo不能为空")
        if busCode == "2" and not orderNo:
            raise ValueError("busCode为2时，orderNo不能为空")
        data = {
            "busCode": busCode,
            "payAcctNo": payAcctNo,
            "startDate": startDate,
        }
        if bankSeqNo:
            data["bankSeqNo"] = bankSeqNo
        if orderNo:
            data["orderNo"] = orderNo
        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def batchtrans(
        self,
    ):
        """
        todo:业务上暂时不用
        3.4.	银企直连批量转账交易
        transDate	Max11Text	交易日期	是
        orderNo	Max30Text	发起方唯一业务标识	是
        payAcctName	Max200Text	付款账号户名	是
        payAcctNo	Max32Text	付款账号	是
        batchNo	Max257Text	批量转账批次号	是
        sumAmt	Max32Text	交易总金额	是
        totalCnt	Max10Text	总数量	是
        dcFlag	Max2Text	转账方式	是	  1：汇总入账 2：单笔入账 --固定为2
        transList循环
        rcvAcctNo	Max10Text 	收款账号	否
        rcvAcctSeqno	Max40Text 	收款账户序号	否
        rcvAcctName	Max80Text 	收款户名	否
        revCertNo	Max10Text 	收款人证件号码	否
        inbankname	Max40Text 	 入账总银行名称	否
        inbankno	Max10Text 	 入账总银行行号	否
        transAmt	Max12Text 	转账金额	否
        busCode	Max12Text 	转账方式	否	1.行内转账 8.超网
        remark	Max12Text 	摘要	否
        reserve1	Max20Text	预留字段1	否
        reserve2	Max80Text	预留字段2	否
        """
        endpoint = "/V1/P01508/S01/batchtrans"
        data = {}
        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def selbatchtrans(
        self,
        payAcctNo: str,
        batchNo: str,
    ):
        """
        todo:业务上暂时不用
        3.5.	银企直连批量转账结果查询交易
        payAcctNo	Max32Text	付款账号	是
        batchNo	Max257Text	批量转账批次号	是
        """
        endpoint = "/V1/P01509/S01/selbatchtrans"
        data = {
            "payAcctNo": payAcctNo,
            "batchNo": batchNo,
        }
        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def queryhourdetails(
        self,
        payAcctNo: str,
        startDate: str,
        endDate: str,
    ):
        """
        3.6.	银企直连时间段明细查询申请
        payAcctNo	Max32Text	付款账号	是
        startDate	Max30Text	起始日期	是	yyyyMMddhhmmss例：20221001140000
        endDate	Max30Text	结束日期	是	yyyyMMddhhmmss
        """
        endpoint = "/V1/P01512/S01/queryhourdetails"
        data = {
            "payAcctNo": payAcctNo,
            "startDate": startDate,
            "endDate": endDate,
        }
        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def detailsreceipt(
        self,
        acctNo: str,
        transDate: str,
        transSeqno: str,
        transOperNo: str | None = None,
        transBrno: str | None = None,
    ):
        """
        3.7.	银企直连账务明细回单下载
        acctNo	Max32Text	银企直连签约账号	是
        transDate	Max30Text	交易日期	是	P01512返回字段
        transSeqno	Max30Text	核心流水号	是	P01512返回字段
        transOperNo	Max30Text	交易柜员	否	P01512返回字段
        transBrno	Max15Text	交易机构	否	P01512返回字段
        """
        endpoint = "/V1/P01513/S01/detailsreceipt"
        # 必填校验
        if not acctNo:
            raise ValueError("acctNo 不能为空")
        if not transDate:
            raise ValueError("transDate 不能为空")
        if not transSeqno:
            raise ValueError("transSeqno 不能为空")

        data = {
            "acctNo": acctNo,
            "transDate": transDate,
            "transSeqno": transSeqno,
        }
        if transOperNo:
            data["transOperNo"] = transOperNo
        if transBrno:
            data["transBrno"] = transBrno

        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def checkacct(
        self,
        payAcctNo: str,
        startDate: str,
        endDate: str,
    ):
        """
        3.8. 银企直连对账 - 对账文件下载
        payAcctNo Max32Text 银企直连签约账号 是
        startDate Max8Text 开始日期 是 yyyyMMdd
        endDate   Max8Text 结束日期 是 yyyyMMdd
        """
        endpoint = "/V1/P01518/S01/checkAcct"
        if not payAcctNo:
            raise ValueError("payAcctNo 不能为空")
        if not startDate:
            raise ValueError("startDate 不能为空")
        if not endDate:
            raise ValueError("endDate 不能为空")

        data = {
            "payAcctNo": payAcctNo,
            "startDate": startDate,
            "endDate": endDate,
        }
        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def checkresultupdate(
        self,
        payAcctNo: str,
        checkUser: str,
        billNo: str,
        billList: list[dict],
    ):
        """
        3.9. 银企直连对账结果更新
        payAcctNo: 银企直连签约账号 (必)
        checkUser: 对账人 (必)
        billNo: 账单编号 (必)
        billList: 账单循环列表 (必) - 每项为 dict 包含 acctNo, acctType, replyStatus, ccy, acctList 等
        """
        endpoint = "/V1/P01519/S01/checkResultUpdate"
        if not payAcctNo:
            raise ValueError("payAcctNo 不能为空")
        if not checkUser:
            raise ValueError("checkUser 不能为空")
        if not billNo:
            raise ValueError("billNo 不能为空")
        if not billList:
            raise ValueError("billList 不能为空")

        data = {
            "payAcctNo": payAcctNo,
            "checkUser": checkUser,
            "billNo": billNo,
            "billList": billList,
        }
        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def queryesubacctbalance(self, payAcctNo: str):
        """
        3.10. 子账户余额查询接口
        payAcctNo: 账号 (必)
        """
        endpoint = "/V1/P01520/S01/queryeSubacctBalance"
        if not payAcctNo:
            raise ValueError("payAcctNo 不能为空")

        data = {"payAcctNo": payAcctNo}
        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def queryhourdetails2(
        self,
        payAcctNo: str,
        startDate: str,
        endDate: str,
    ):
        """
        3.11. 交易明细查询（流水号匹配）
        payAcctNo, startDate, endDate 必填，日期格式 yyyyMMddhhmmss
        """
        endpoint = "/V1/P01522/S01/queryhourdetails2"
        if not payAcctNo:
            raise ValueError("payAcctNo 不能为空")
        if not startDate:
            raise ValueError("startDate 不能为空")
        if not endDate:
            raise ValueError("endDate 不能为空")

        data = {
            "payAcctNo": payAcctNo,
            "startDate": startDate,
            "endDate": endDate,
        }
        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def queryreceiptdetails(
        self,
        payAcctNo: str,
        startDate: str,
        endDate: str,
        merId: str,
        miniTransAmt: str | None = None,
        maxTransAmt: str | None = None,
    ):
        """
        3.12. 收单明细查询
        payAcctNo, startDate, endDate, merId 必填
        miniTransAmt, maxTransAmt 可选
        """
        endpoint = "/V1/P01523/S01/queryreceiptdetails"
        if not payAcctNo:
            raise ValueError("payAcctNo 不能为空")
        if not startDate:
            raise ValueError("startDate 不能为空")
        if not endDate:
            raise ValueError("endDate 不能为空")
        if not merId:
            raise ValueError("merId 不能为空")

        data = {
            "payAcctNo": payAcctNo,
            "startDate": startDate,
            "endDate": endDate,
            "merId": merId,
        }
        if miniTransAmt is not None:
            data["miniTransAmt"] = miniTransAmt
        if maxTransAmt is not None:
            data["maxTransAmt"] = maxTransAmt

        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def querybankinfos(
        self, type: str, bankName: str | None = None, bankNo: str | None = None
    ):
        """
        3.13. 行名行号查询
        type: 查询类型 (必) '0' 行名查询行号 (需 bankName), '1' 行号查询行名 (需 bankNo)
        """
        endpoint = "/V1/P01524/S01/querybankinfos"
        if not type:
            raise ValueError("type 不能为空")
        if type == "0" and not bankName:
            raise ValueError("type 为 0 时，bankName 不能为空")
        if type == "1" and not bankNo:
            raise ValueError("type 为 1 时，bankNo 不能为空")

        data = {"type": type}
        if bankName:
            data["bankName"] = bankName
        if bankNo:
            data["bankNo"] = bankNo

        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response

    def querycertexpiry(self, payAcctNo: str):
        """
        3.14. 证书有效期查询接口
        payAcctNo 必填
        """
        endpoint = "/V1/P01525/S01/queryCertExpiry"
        if not payAcctNo:
            raise ValueError("payAcctNo 不能为空")

        data = {"payAcctNo": payAcctNo}
        response = self.request(
            endpoint=endpoint,
            headers={},
            json_data=data,
            method="POST",
        )
        return response
