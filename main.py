"""Application entry point for the KASBench Load Generator service."""

import uvicorn

from kasbench_load_generator.app import app
from kasbench_load_generator import config

if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT)
