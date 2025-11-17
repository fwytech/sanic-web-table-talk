import logging
import logging.config
import os

from dotenv import load_dotenv


def load_env():
    """
    加载日志配置文件
    """
    log_dir = "logs"
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        raise

    with open("config/logging.conf", encoding="utf-8") as f:
        logging.config.fileConfig(f)

    # 根据环境变量 ENV 的值选择加载哪个 .env 文件
    dotenv_path = f'.env.{os.getenv("ENV","dev")}'
    logging.info(f"""====当前配置文件是:{dotenv_path}====""")
    load_dotenv(dotenv_path)
