import os
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from enum import Enum
from typing import TypeVar


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
class DatabaseConfig:
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
    service_name: str = field(
        default="nucleus_data", metadata=dict(env_name_override="DD_SERVICE")
    )


class LoggingMode(str, Enum):
    console = "console"
    console_json = "console_json"
    file_json = "file_json"


@dataclass(frozen=True)
class Config:
    database: DatabaseConfig
    datadog: DatadogConfig
    logging_mode: LoggingMode = LoggingMode.console_json


T = TypeVar("T")


def read_config(x: type[T], env_prefix: str = "") -> T:
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
                    val = typ(env_val)

        if val is None:
            if f.default != MISSING:
                val = f.default
            else:
                raise RuntimeError(f"missing value for '{f.name}' (${env_name})")

        res[f.name] = val

    return x(**res)
