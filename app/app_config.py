import logging
import os
import sys

# Global app state
class AppConfig:
    UUID: str = None                    # ID for the current run
    MODEL: dict = None                  # Name of the current LLM model
    ATTACK_VECTORS: str = None          # List of attack vectors
    TARGET_LANGUAGES: str = None        # List of target languages
    TARGET_FILE_EXTENSION: str = None   # List of target file extension
    SELECTED_MODEL_KEY: str = None      # Key of the selected model
    VICTIM_FUNCTION: int = 1            # Victim function number, default is 1
    TEMPLATE_NUMBER: int = 3            # <- default template number (3..11)
    SEEDS: list[int] = None             # Seeds for the LLM model
    NUM_SEEDS: int = 100                  # Number of seeds to generate
    PROG_REF_CNT: int = 8               # Maximum number of calls to the reflection agent
    PROG_EVA_CNT: int = 7              # Maximum number of calls to the Evaluator agent
    RECURSION_LIMIT: int = 70         # Maximum number nodes to be executed
    LOG_LEVEL: int = logging.DEBUG      # Logging level
    LOG_FORMAT: str = '%(asctime)s %(name)-18s %(levelname)-6s %(message)s'
    LOG_DATE_FORMAT: str = '%Y-%m-%d %H:%M:%S'
    pass # end of AppState


config: AppConfig = AppConfig()

def get_logger(name: str) -> logging.Logger:
    ROOTDIR = os.path.expanduser(f'~/workdir/logs')
    os.makedirs(ROOTDIR, mode=0o755, exist_ok=True)
    LOGFILE = f"{config.UUID}.log"
    LOGFILEPATH = os.path.join(ROOTDIR, LOGFILE)

    log = logging.getLogger(name)
    # Avoid duplicate handlers if get_logger() is called multiple times
    if log.handlers:
        return log
    log.setLevel(config.LOG_LEVEL)

    file_handler = logging.FileHandler(LOGFILEPATH)
    file_handler.setLevel(logging.DEBUG)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(config.LOG_LEVEL)

    formatter = logging.Formatter(config.LOG_FORMAT, config.LOG_DATE_FORMAT)
    file_handler.setFormatter(formatter)
    stdout_handler.setFormatter(formatter)

    log.addHandler(stdout_handler)
    log.addHandler(file_handler)

    # Prevent double-logging via the root logger
    log.propagate = False

    return log
