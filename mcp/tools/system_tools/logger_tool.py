"""Logger Tool — structured stdout + file logging for the pipeline."""

import logging
import os
from pathlib import Path
from mcp.base_tool import BaseTool


class LoggerTool(BaseTool):
    name = "logger_tool"
    description = "Provides structured logging for agent pipeline steps."

    def __init__(self, log_file: str = "data/outputs/Phase1/pipeline.log"):
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_file),
            ],
        )
        self.logger = logging.getLogger("AgenticAI.Phase1")

    def run(self, level: str = "info", message: str = "", **kwargs) -> None:
        msg = message
        if kwargs:
            msg += " | " + " ".join(f"{k}={v}" for k, v in kwargs.items())
        getattr(self.logger, level.lower(), self.logger.info)(msg)
