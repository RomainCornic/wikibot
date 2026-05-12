# logger.py

import logging
import sys
from pathlib import Path


class ColorFormatter(logging.Formatter):
    """
    Logger coloré pour terminal.
    """

    COLORS = {
        logging.DEBUG: "\033[90m",  # Gris
        logging.INFO: "\033[94m",  # Bleu
        logging.WARNING: "\033[93m",  # Jaune
        logging.ERROR: "\033[91m",  # Rouge
        logging.CRITICAL: "\033[95m",  # Magenta
    }

    RESET = "\033[0m"

    FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    def format(self, record):
        log_fmt = self.COLORS.get(record.levelno, "") + self.FORMAT + self.RESET
        formatter = logging.Formatter(
            log_fmt,
            datefmt="%H:%M:%S",
        )
        return formatter.format(record)


def setup_logger(
    name: str = "app",
    level: int = logging.INFO,
    log_file: str | None = None,
) -> logging.Logger:
    """
    Crée un logger propre avec :
    - couleurs terminal
    - fichier optionnel
    - niveaux DEBUG/INFO/WARNING/ERROR/CRITICAL
    """

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(level)

    #
    # Console handler
    #
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ColorFormatter())

    logger.addHandler(console_handler)

    #
    # File handler optionnel
    #
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)

        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler.setFormatter(file_formatter)

        logger.addHandler(file_handler)

    logger.propagate = False

    return logger
