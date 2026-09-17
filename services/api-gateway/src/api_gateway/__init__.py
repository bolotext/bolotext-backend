import argparse
import logging

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="bolotext API Gateway")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level.upper())
    uvicorn.run("api_gateway.app:app", host="0.0.0.0", port=8000, log_level=args.log_level.lower())


if __name__ == "__main__":
    main()
