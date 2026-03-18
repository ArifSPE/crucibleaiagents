import json


def main() -> None:
    print(json.dumps({
        "status": "ok",
        "message": "Sample bot package executed",
    }))


if __name__ == "__main__":
    main()
