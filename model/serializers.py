import datetime
import json
from typing import Any, Dict, List, Union
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm.exc import DetachedInstanceError


def model_to_dict(
    model_instance: Union[DeclarativeBase, List[DeclarativeBase]],
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    将SQLAlchemy模型实例转换为字典
    :param model_instance: SQLAlchemy模型实例或实例列表
    :return: 字典或字典列表
    """
    # 处理列表情况
    if isinstance(model_instance, list):
        return [single_model_to_dict(item) for item in model_instance]

    # 处理单个实例情况
    return single_model_to_dict(model_instance)


def single_model_to_dict(model_instance: DeclarativeBase) -> Dict[str, Any]:
    """
    将单个SQLAlchemy模型实例转换为字典
    :param model_instance: SQLAlchemy模型实例
    :return: 字典表示
    """
    result = {}
    try:
        for column in model_instance.__table__.columns:
            try:
                value = getattr(model_instance, column.name)
                if isinstance(value, datetime.datetime):
                    value = value.isoformat() if value else None
                elif isinstance(value, datetime.date):
                    value = value.isoformat() if value else None
                result[column.name] = value
            except DetachedInstanceError:
                # 处理与session分离的实例
                result[column.name] = None
    except Exception as e:
        # 如果出现其他错误，返回空字典或部分数据
        pass
    return result


def model_to_json(model_instance: Union[DeclarativeBase, List[DeclarativeBase]]) -> str:
    """
    将SQLAlchemy模型实例转换为JSON字符串
    :param model_instance: SQLAlchemy模型实例或实例列表
    :return: JSON字符串
    """
    return json.dumps(model_to_dict(model_instance), ensure_ascii=False, default=str)
