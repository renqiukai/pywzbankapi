"""
付款账号：
733000120190056868
瓯江实验室
"""

from pywzbankapi.base import Base
from loguru import logger
from uuid import uuid4
from random import randint


def get_order_no():
    return str(randint(100000, 999999))


payAcctNo = "733000120190056868"
payAcctName = "瓯江实验室"


def testcase():
    """
    行名行号查询
    """
    b = Base(debug=True)
    b.querybankinfos(type="0", bankName="中国工商银行")


def testcase1():
    """
    查询账户余额
    733000120190056868 瓯江实验室
    """
    b = Base(debug=True)
    b.queryeaccountbalance("733000120190056868")


def testcase2():
    """
    行内对公收款账号:
    账号： 733000120102044561
    户名： 临沂市误畦得利石材厂
    行名： 温州银行股份有限公司营业部
    行号： 313333007331
    """

    b = Base(debug=True)
    b.singletrans(
        payAcctNo=payAcctNo,
        transAmt="0.01",
        payAcctName=payAcctName,
        rcvAcctNo="733000120102044561",
        rcvAcctName="临沂市误畦得利石材厂",
        orderNo=get_order_no(),
        inbankno="313333007331",
        inbankname="温州银行股份有限公司营业部",
    )


def testcase3():
    """
    行内对私收款账号：
    账号：
    6231120100000000024
    户名：夏沽
    行名：温州银行股份有限公司营业部
    行号：313333007331
    """

    b = Base(debug=True)
    b.singletrans(
        payAcctNo=payAcctNo,
        transAmt="0.01",
        payAcctName=payAcctName,
        rcvAcctNo="6231120100000000024",
        rcvAcctName="夏沽",
        orderNo=get_order_no(),
        inbankno="313333007331",
        inbankname="温州银行股份有限公司营业部",
    )


def testcase4():
    """
    跨行对私收款账号:
    账号： 9558800000123456
    户名： 刘刘
    行名： 中国工商银行总行清算中心
    行号： 102100000030
    """

    b = Base(debug=True)
    b.singletrans(
        payAcctNo=payAcctNo,
        transAmt="0.01",
        payAcctName=payAcctName,
        rcvAcctNo="9558800000123456",
        rcvAcctName="刘刘",
        orderNo=get_order_no(),
        inbankno="102100000030",
        inbankname="中国工商银行总行清算中心",
    )


def testcase5():
    """
    跨行对公收款账号:
    账号： 9558851202043960996
    户名： 上海上海市嘉定县复兴门大街955号
    行名： 中国工商银行总行清算中心
    行号： 102100099996
    """

    b = Base(debug=True)
    b.singletrans(
        payAcctNo=payAcctNo,
        transAmt="0.01",
        payAcctName=payAcctName,
        rcvAcctNo="9558851202043960996",
        rcvAcctName="上海上海市嘉定县复兴门大街955号",
        orderNo=get_order_no(),
        inbankno="102100099996",
        inbankname="中国工商银行总行清算中心",
    )


if __name__ == "__main__":
    # testcase()
    # testcase1()
    # testcase2()
    # testcase3()
    # testcase4()
    testcase5()
