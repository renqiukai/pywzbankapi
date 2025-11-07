**温州银行开放平台 Python SDK（银企直连）**

- 版本：文档 V2.8（2024-12-25），SDK 草案
- 包名：`pywzbankapi`
- 网关：`https://openapi.wzbank.cn/prdApiGW/`
- 关键词：SM2/SM4 加签与加密、幂等、签名验证、请求/响应统一封装

本仓库旨在将温州银行开放平台“银企直连”接口封装为可直接调用的 Python 包，覆盖 v2.8 文档中的主要接口，并提供统一的安全、报文和错误处理。

注意：本 README 先行定义了 API 设计、使用方式与安全约定，便于后续落地开发。实现会严格遵循本文档的接口与参数约定。

**目录**

- 快速开始
- 安全与报文规范
- 客户端初始化与配置
- 通用请求参数与响应
- API 一览与示例
- 错误处理与重试
- 常见问题
- 变更记录（对应行方 v2.8）

**快速开始**

- 安装（预留）
  - pip 安装（发布后可用）：`pip install pywzbankapi`
  - 源码安装：在仓库根目录执行 `pip install -e .`

示例

```python
from pywzbankapi import WZBankClient

client = WZBankClient(
    app_id="your-app-id",         # x-aob-appID
    bank_id="WZB",                # x-aob-bankID，默认可为 "WZB"
    base_url="https://openapi.wzbank.cn/prdApiGW/",
    sm2_private_key_pem="...",    # 用于请求头/体 SM2 加签
    sm2_bank_public_key_pem="...",# 用于响应验签
    sm4_key_hex="00112233445566778899AABBCCDDEEFF",  # 128-bit key, hex
    sm4_iv_hex="00112233445566778899AABBCCDDEEFF",   # 128-bit iv, hex
    timeout=30,
)

# 账户余额查询（/V1/P01502/S01/queryeaccountbalance）
resp = client.query_account_balance(payAcctNo="1234567890123456")
print(resp)
```

**安全与报文规范**

- 协议与地址
  - 所有请求使用 HTTPS，网关为 `https://openapi.wzbank.cn/prdApiGW/`
  - 资源路径遵循：版本号/服务分类/场景编号/接口名称（如：`/V1/P01502/S01/queryeaccountbalance`）
- 报文与编码
  - 报文体为 JSON，UTF-8 编码
  - 数据接口 Content-Type：`application/json`
- 加密与签名
  - 请求：对“请求报文体 JSON”执行 SM4 加密，得到 hex 字符串，作为 `{"bizContent": "<hex>"}` 发送
  - 加签：用 SM2 对如下 JSON 串进行签名（顺序固定，字段包括请求头与 bizContent）：
    `{"x-aob-appID": "...", "x-aob-bankID": "WZB", "bizContent": "<hex>"}`
  - 请求头需包含：`x-aob-appID`、`x-aob-bankID`、`x-aob-signature`
  - 响应：SDK 自动验签（SM2）并对 `bizContent` 进行 SM4 解密
- 幂等与关联
  - 可传 `x-idempotency-key` 确保幂等
  - 可传 `x-aob-interaction-id` 追踪调用链路（UUID）

**客户端初始化与配置**

```python
from pywzbankapi import WZBankClient, CryptoProvider

crypto = CryptoProvider(
    sm2_private_key_pem="...",      # SM2 私钥（加签）
    sm2_bank_public_key_pem="...",  # 银行公钥（验签）
    sm4_key_hex="...",              # 128-bit Key（hex）
    sm4_iv_hex="...",               # 128-bit IV（hex）
)

client = WZBankClient(
    app_id="your-app-id",
    bank_id="WZB",
    base_url="https://openapi.wzbank.cn/prdApiGW/",
    crypto=crypto,
    timeout=30,
    debug=False,
)
```

**通用请求参数与响应**

- 请求体公共字段（置于被加密 JSON 内）
  - `mesgId` 请求流水号（建议 UUID）
  - `mesgDate` 请求日期（YYYYMMDD）
  - `mesgTime` 请求时间（hhmmssSSS）
  - `pageFlag`/`nowPage`/`pageNum` 分页可选
  - `extend1`/`extend2` 预留
- 响应体公共字段（解密后）
  - `dealCode` 返回码，`dealMsg` 返回信息
  - `totalNum`/`nowPage`/`pageNum` 分页

**API 一览与示例（v2.8）**
以下方法均自动处理：SM4 加密/解密、SM2 加签/验签、请求头与 `bizContent` 封装。示例仅展示必输字段，其他字段见方法 docstring。

1. 账户余额查询

- 方法：`client.query_account_balance(payAcctNo)`
- 路径：`/V1/P01502/S01/queryeaccountbalance`

```python
resp = client.query_account_balance(payAcctNo="1234567890123456")
# 返回：payAcctBal, curCode, curType, startDate, endDate, otherInfo, payAcctNo, payAcctUseBal
```

2. 单笔转账

- 方法：`client.single_transfer(...)`
- 路径：`/V1/P01506/S01/singletrans`
- 必输：`payAcctNo, transAmt, payAcctName, rcvAcctNo, rcvAcctName, inbankno, curCode=1, curType=0, orderNo, reserve2`

```python
resp = client.single_transfer(
    payAcctNo="付款账号",
    transAmt="100.00",
    payAcctName="付款户名",
    rcvAcctNo="收款账号",
    rcvAcctName="收款户名",
    inbankno="入账总行号",
    orderNo="业务唯一标识",
    remark="可选摘要",
    reserve2="业务保留字段",
)
# 返回：orderNo, bankSeqNo, workdate
```

3. 单笔转账结果查询

- 方法：`client.query_single_transfer_result(...)`
- 路径：`/V1/P01507/S01/selsingletrans`

```python
resp = client.query_single_transfer_result(
    busCode="1",            # 1-按流水号, 2-按订单号
    payAcctNo="付款账号",
    startDate="YYYY-MM-DD",
    bankSeqNo="可选，配合 busCode",
    orderNo="可选，配合 busCode",
)
# 返回：dealStatus(0/1/2), setDate, bankSeqNo, transAmt, payAcctNo, rcvAcctNo, orderNo, failedReason
```

4. 批量转账

- 方法：`client.batch_transfer(...)`
- 路径：`/V1/P01508/S01/batchtrans`

```python
resp = client.batch_transfer(
    transDate="YYYY-MM-DD",
    orderNo="唯一业务标识",
    payAcctName="付款户名",
    payAcctNo="付款账号",
    batchNo="批次号",
    sumAmt="总金额",
    totalCnt="总数量",
    dcFlag="2",   # 固定单笔入账
    transList=[
        {
            "rcvAcctNo": "收款账号",
            "rcvAcctName": "收款户名",
            "transAmt": "10.00",
            "busCode": "8",  # 1行内, 8超网
            "remark": "摘要",
        }
    ],
)
# 返回体为空（以查询接口获取结果）
```

5. 批量转账结果查询

- 方法：`client.query_batch_transfer_result(payAcctNo, batchNo)`
- 路径：`/V1/P01509/S01/selbatchtrans`

6. 时间段明细查询申请

- 方法：`client.query_hour_details(payAcctNo, startDate, endDate)`
- 路径：`/V1/P01512/S01/queryhourdetails`

7. 账务明细回单下载

- 方法：`client.download_details_receipt(acctNo, transDate, transSeqno, transOperNo=None, transBrno=None)`
- 路径：`/V1/P01513/S01/detailsreceipt`

8. 银企直连对账（文件下载 URL）

- 方法：`client.check_account(payAcctNo, startDate, endDate)`
- 路径：`/V1/P01518/S01/checkAcct`
- 返回：`fileUrl`（浏览器直接 GET 即可下载）

9. 对账结果更新

- 方法：`client.update_check_result(payAcctNo, checkUser, billNo, billList)`
- 路径：`/V1/P01519/S01/checkResultUpdate`

```python
resp = client.update_check_result(
    payAcctNo="账号",
    checkUser="张三",
    billNo="账单编号",
    billList=[{
        "acctNo": "账号",
        "acctType": "1",   # 1存款,2贷款
        "replyStatus": "1", # 0初始;1相符;2不相符;3调节后相符
        "ccy": "CNY",
        "acctList": [
            {"transDate":"yyyyMMdd","dcType":"0","amount":"100.00","amtType":"1"}
        ]
    }]
)
```

10. 子账户余额查询

- 方法：`client.query_subacct_balance(payAcctNo)`
- 路径：`/V1/P01520/S01/queryeSubacctBalance`

11. 交易明细查询（流水号匹配）

- 方法：`client.query_hour_details2(payAcctNo, startDate, endDate)`
- 路径：`/V1/P01522/S01/queryhourdetails2`

12. 收单明细查询

- 方法：`client.query_receipt_details(payAcctNo, startDate, endDate, merId, miniTransAmt=None, maxTransAmt=None)`
- 路径：`/V1/P01523/S01/queryreceiptdetails`

13. 行名行号查询（v2.8 新增）

- 方法：`client.query_bank_infos(type, bankName=None, bankNo=None)`
- 路径：`/V1/P01524/S01/querybankinfos`
- 规则：`type=0` 时需传 `bankName`；`type=1` 时需传 `bankNo`

14. 证书有效期查询

- 方法：`client.query_cert_expiry(payAcctNo)`
- 路径：`/V1/P01525/S01/queryCertExpiry`

**错误处理与重试**

- SDK 将对非 2xx HTTP 状态、验签失败、解密失败抛出显式异常
- 业务返回（解密后）需检查 `dealCode` 与 `dealMsg`
- 可配置自动重试策略（如网络抖动、5xx）与幂等键 `x-idempotency-key`

**常见问题（FAQ）**

- 如何准备国密证书材料？
  - 从行方获取/对接：用于验签的银行 SM2 公钥；用于加签的企业 SM2 私钥；SM4 对称密钥与 IV（16 字节）
- Python 如何完成 SM2/SM4？
  - SDK 通过 `CryptoProvider` 解耦。你可以基于 `gmssl` 或其他国密库实现 `sign/verify/encrypt/decrypt` 四个方法并注入。
- 文件下载如何处理？
  - `checkAcct` 返回 `fileUrl`，可直接 `requests.get(fileUrl)` 下载。

**变更记录（对应行方 v2.8 摘要）**

- V2.7：收单明细查询商户号描述调整；余额查询新增 `payAcctUseBal`
- V2.8：新增行名行号查询 `/V1/P01524/S01/querybankinfos`

**致谢**

- 文档属性：开放平台接口说明（银企直连），版本号 v2.8，提交 2024-12-10
- 撰写：林建海；审核：金值

**免责声明**
本 SDK 为对接辅助工具。实际生产接入需与行方测试环境联调，确保证书、算法参数、签名/验签、加解密与业务字段完全匹配行方规范。

### 测试环境域名地址：

https://zhihuitest.wzbank.cn/indApp/apiGateway

### 生产环境域名地址：

https://openapi.wzbank.cn/prdApiGW
