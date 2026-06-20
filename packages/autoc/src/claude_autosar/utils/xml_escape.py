"""XML 文本转义工具。

Sprint 12 审计修复（HIGH-1 / HIGH-2）：surgical patch 在写回字节时，必须把
lxml 解码后的 ``elem.text``（含裸 ``&``、``<``、``>``）重新转义为合法 XML 文本，
否则产生畸形输出。

集中在一个工具便于：
- 单点审计：所有 XML 写回都走同一份转义函数
- 测试隔离：针对边界字符（``&``、``&amp;``、``&#xD;``、``"``、``'``）
  单独验证

实现要点：
- 直接用 :func:`xml.sax.saxutils.escape` 默认行为（转 ``&`` ``<`` ``>``，
  **不**转 ``"`` ``'``，因为这两个字符在元素文本里是合法的，强制转义
  反而会让原本合法的 XML 文本多出无用字符）。
- **不能**传 ``{'&': '&amp;'}`` —— :func:`xml.sax.saxutils.escape` 会先做一次
  ``&`` → ``&amp;``，然后再迭代 entities 替换一次，导致 ``&`` → ``&amp;amp;``
  双重转义（这是 Python 标准库本身的实现细节，3.11+ 仍如此）。
"""

from __future__ import annotations

from xml.sax.saxutils import escape as _sax_escape


def escape_xml_text(text: str) -> str:
    """转义 XML 元素文本中的特殊字符。

    只转 ``&`` ``<`` ``>``，**不**转 ``"`` ``'``（它们在元素文本里是合法的）。

    Examples:
        >>> escape_xml_text("Tom & Jerry")
        'Tom &amp; Jerry'
        >>> escape_xml_text("5 < 10")
        '5 &lt; 10'
        >>> escape_xml_text('She said "hi"')
        'She said "hi"'

    Note:
        不接受 ``None``；调用方需自行判空。
    """
    return _sax_escape(text)