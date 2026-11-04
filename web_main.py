"""Server locale della versione browser. Non pubblica l'applicazione."""
import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="LottoPredict AI · versione web locale")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    if args.data_dir:
        os.environ["LOTTOPREDICT_DATA_DIR"] = str(args.data_dir.resolve())
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    import uvicorn
    uvicorn.run("web.app:create_app", factory=True, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
