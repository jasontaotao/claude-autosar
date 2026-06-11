"""BSW 配置数据模型。

所有公开 dataclass 均为 frozen（不可变），确保多线程 / 多 agent 共享时
不会产生隐藏副作用。修改通过返回新实例实现（参见 ``BSWModule.with_param``）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ParamType(Enum):
    """BSW 参数类型枚举。"""

    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    BOOLEAN = "boolean"
    ENUMERATION = "enumeration"


@dataclass(frozen=True)
class ParamValue:
    """参数值：原值字符串 + 类型标签。

    保持 ``raw`` 为字符串以避免精度损失（如 64 位整数、IEEE 754 边界值）。
    类型化访问通过 ``as_int`` / ``as_float`` / ``as_bool`` / ``as_str``。
    """

    raw: str
    type: ParamType

    def __post_init__(self) -> None:
        if not isinstance(self.raw, str):
            raise TypeError(f"raw must be str, got {type(self.raw).__name__}")
        if not isinstance(self.type, ParamType):
            raise TypeError(f"type must be ParamType, got {type(self.type).__name__}")

    def as_int(self) -> int:
        """按 INTEGER 类型取整数值。其它类型抛 TypeError。"""
        if self.type is not ParamType.INTEGER:
            raise TypeError(f"value is not integer: {self.type}")
        return int(self.raw)

    def as_float(self) -> float:
        """按 FLOAT 类型取浮点值。其它类型抛 TypeError。"""
        if self.type is not ParamType.FLOAT:
            raise TypeError(f"value is not float: {self.type}")
        return float(self.raw)

    def as_bool(self) -> bool:
        """按 BOOLEAN 类型取布尔值。接受 true/1/yes（大小写不敏感）。"""
        if self.type is not ParamType.BOOLEAN:
            raise TypeError(f"value is not boolean: {self.type}")
        return self.raw.strip().lower() in ("true", "1", "yes")

    def as_str(self) -> str:
        """原值字符串（任何类型均可）。"""
        return self.raw


@dataclass(frozen=True)
class BSWParam:
    """单个 BSW 配置参数：层级路径 + 值。

    path 必须是层级形式（至少含一个 ``/``），用于精确寻址：
        ``Mcu/McuClockSettingConfig_0/McuClockReferencePoint``
    """

    path: str
    value: ParamValue

    def __post_init__(self) -> None:
        if not self.path or "/" not in self.path:
            raise ValueError(f"path must be hierarchical (contain '/'), got {self.path!r}")
        if not isinstance(self.value, ParamValue):
            raise TypeError(f"value must be ParamValue, got {type(self.value).__name__}")


@dataclass(frozen=True)
class BSWModule:
    """BSW 模块配置：模块名 + 不可变参数集合 + 可选 vendor / version。

    不可变：``with_param`` 返回新实例，原对象不变。
    """

    name: str
    params: tuple[BSWParam, ...] = ()
    vendor: str | None = None
    version: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must be non-empty")
        if not isinstance(self.params, tuple):
            raise TypeError("params must be a tuple (immutable)")
        for p in self.params:
            if not isinstance(p, BSWParam):
                raise TypeError(f"params must contain BSWParam only, got {type(p).__name__}")

    def get(self, path: str) -> BSWParam | None:
        """按 path 查找参数；未找到返回 None。"""
        for p in self.params:
            if p.path == path:
                return p
        return None

    def with_param(self, param: BSWParam) -> BSWModule:
        """返回带新参数的新实例：同 path 则替换，否则追加。"""
        new_params = tuple(p for p in self.params if p.path != param.path)
        return BSWModule(
            name=self.name,
            params=new_params + (param,),
            vendor=self.vendor,
            version=self.version,
        )

    @classmethod
    def from_ecuc(cls, doc: object) -> BSWModule:
        """从 ECUCDocument 反序列化为 BSWModule。

        不可变：原 ECUCDocument 不受影响。
        故意接受 `object` 注解避免循环 import（`ecuc.py` 已反向 import 本模块）。
        """
        from autoc.core.bsw.ecuc import ECUCValue  # noqa: PLC0415

        params: list[BSWParam] = []
        for v in doc.values:  # type: ignore[attr-defined]
            assert isinstance(v, ECUCValue)
            params.append(
                BSWParam(
                    path=v.path,
                    value=ParamValue(raw=v.raw, type=_ECUC_TO_PARAM_TYPE[v.type]),
                )
            )
        return cls(name=doc.module_name, params=tuple(params))  # type: ignore[attr-defined]

    def to_ecuc(self, arxml_path: object) -> object:
        """把 BSWModule 序列化为 ECUCDocument（Sprint 4+ 的会话回放会用到）。

        故意返回 `object` 注解避免循环 import。
        """
        from autoc.core.bsw.ecuc import ECUCDocument, ECUCValue  # noqa: PLC0415

        values: list[ECUCValue] = []
        for p in self.params:
            if "/" not in p.path:
                raise ValueError(
                    f"BSWParam.path must be hierarchical (contain '/'), got {p.path!r}"
                )
            values.append(
                ECUCValue(
                    path=p.path,
                    raw=p.value.raw,
                    type=_PARAM_TO_ECUC_TYPE[p.value.type],  # type: ignore[arg-type]
                )
            )
        return ECUCDocument(
            path=arxml_path,  # type: ignore[arg-type]
            module_name=self.name,
            values=tuple(values),
        )


# ---------------------------------------------------------------------------
# ECUC ↔ ParamType 双向映射
# ---------------------------------------------------------------------------

_PARAM_TO_ECUC_TYPE: dict[ParamType, str] = {
    ParamType.INTEGER: "INTEGER",
    ParamType.FLOAT: "FLOAT",
    ParamType.STRING: "STRING",
    ParamType.BOOLEAN: "BOOLEAN",
    ParamType.ENUMERATION: "ENUMERATION",
}

_ECUC_TO_PARAM_TYPE: dict[str, ParamType] = {v: k for k, v in _PARAM_TO_ECUC_TYPE.items()}
