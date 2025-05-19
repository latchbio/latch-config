import os
from dataclasses import (
    MISSING,
    Field,
    dataclass,
    field,
    fields,
    is_dataclass,
)
from enum import Enum
from textwrap import indent
from types import UnionType
from typing import (
    Any,
    ClassVar,
    Literal,
    Protocol,
    Self,
    TypeVar,
    Union,
    get_args,
    get_origin,
)


@dataclass(frozen=True)
class DatabaseConnRetriesConfig:
    min_retry_time: float = 1
    max_retry_time: float = 2
    max_wait_time: float = 120


@dataclass(frozen=True)
class DatabaseTxRetriesConfig:
    delay_quant: float = 0.05
    max_wait_time: float = 30


@dataclass(frozen=True)
class PostgresConnectionConfig:
    host: str
    password: str

    conn_retries: DatabaseConnRetriesConfig
    tx_retries: DatabaseTxRetriesConfig

    port: str = "5432"
    dbname: str = "core"
    user: str = "postgres"

    pool_size: int = 20


@dataclass(frozen=True)
class DatadogConfig:
    service_version: str = field(metadata=dict(env_name_override="DD_VERSION"))
    deployment_environment: str = field(metadata=dict(env_name_override="DD_ENV"))
    service_name: str = field(metadata=dict(env_name_override="DD_SERVICE"))

    api_key: str = field(metadata=dict(env_name_override="DD_API_KEY"), default="")
    app_key: str = field(metadata=dict(env_name_override="DD_APP_KEY"), default="")


class LoggingMode(str, Enum):
    console = "console"
    console_json = "console_json"
    file_json = "file_json"


T = TypeVar("T")


class _IsDataclass(Protocol):
    __dataclass_fields__: ClassVar[dict[str, Field]]


DC = TypeVar("DC", bound=_IsDataclass)


class NestyError(Exception):
    def __init__(self, msg: str, children: list[Self] | None = None):
        self.msg = msg
        self.children = children

    def __str__(self):
        if self.children is None:
            return self.msg

        res: list[str] = [self.msg]
        for child in self.children:
            res.extend(indent(str(child), " -> "))

        return "\n".join(res)


def parse_config_val(t: type[T], v: Any) -> T:
    if t is type(None):
        if v is None:
            return v

        raise NestyError(f"value `{repr(v)}` is not assignable to `type(None)`")

    origin, args = get_origin(t), get_args(t)

    if origin is None:
        try:
            return t(v)
        except Exception as e:
            raise NestyError(
                f"value `{repr(v)}` is not assignable to type `{t}`: {e}"
            ) from e

    if origin in {Union, UnionType}:
        errors: list[NestyError] = []
        for arg in args:
            try:
                return parse_config_val(arg, v)
            except NestyError as e:
                errors.append(e)

        raise NestyError(
            f"value `{repr(v)}` is not assignable to union type `{t}`", errors
        )

    if origin is Literal:
        errors: list[NestyError] = []
        for arg in args:
            if v == arg:
                return v
            else:
                errors.append(
                    NestyError(f"value `{repr(v)}` is not equal to literal `{arg}`")
                )

        raise NestyError(
            f"value `{repr(v)}` is not assignable to literal type `{t}`", errors
        )

    raise NotImplementedError(f"config parsing is not implemented for type {t}")


def read_config(x: type[DC], env_prefix: str = "") -> DC:
    res = {}
    for f in fields(x):
        val = None

        typ = f.type
        if is_dataclass(typ):
            val = read_config(typ, env_prefix + f.name + "_")

        env_name = ""
        if val is None:
            env_name = env_prefix + f.metadata.get("env", f.name)
            env_name = f.metadata.get("env_name_override", env_name)

            env_val = os.environ.get(env_name)
            if env_val is not None:
                parser = f.metadata.get("parser")
                if parser is not None:
                    val = parser(env_val)
                else:
                    val = parse_config_val(typ, env_val)

        if val is None:
            if f.default != MISSING:
                val = f.default
            else:
                raise RuntimeError(f"missing value for '{f.name}' (${env_name})")

        res[f.name] = val

    return x(**res)
